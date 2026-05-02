"""
Agent v2.2 — Hybrid router with three-strike channel enforcement
================================================================
Graph:
  [router] → suggest_switch or force_reset → [format]
           → matches channel → [cardholder|merchant|dispute|loyalty]
           → [validate] → [execute] → [format]
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, TypedDict

import anthropic
from langgraph.graph import StateGraph, END

from config import settings
from executor import execute_query, is_safe_sql, export_to_excel
from prompts import (
    ROUTER_PROMPT,
    CARDHOLDER_PROMPT, MERCHANT_PROMPT,
    DISPUTE_PROMPT, LOYALTY_PROMPT
)
from logger import log_query

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# ── Switch / menu keywords ────────────────────────────────────
CONFIRM_SWITCH_WORDS = {
    "yes", "da", "ok", "okay", "switch", "prebaci",
    "yes please", "da molim", "confirm", "potvrdi"
}
MENU_WORDS = {
    "menu", "meni", "back", "nazad", "home", "početak", "restart"
}

# ── Mismatch escalation messages ──────────────────────────────
MISMATCH_RESPONSES = {
    1: {
        "en": "This seems like it belongs to a different channel. "
              "Reply 'yes' to switch or continue here.",
        "sr": "Ovo izgleda kao zahtev za drugi kanal. "
              "Odgovorite 'da' za prelaz ili nastavite ovde.",
    },
    2: {
        "en": "I notice your questions don't match your selected channel. "
              "For the best experience, reply 'yes' to switch "
              "or 'menu' to return to the main menu.",
        "sr": "Vaša pitanja ne odgovaraju odabranom kanalu. "
              "Odgovorite 'da' za prelaz ili 'meni' za povratak na početak.",
    },
    3: {
        "en": "To protect your data and ensure the best service, "
              "I am returning you to the channel selector. "
              "Please choose the channel that matches your request.",
        "sr": "Radi zaštite vaših podataka, vraćam vas na izbor kanala. "
              "Molimo odaberite odgovarajući kanal.",
    },
}

# ── Agent state ───────────────────────────────────────────────
class AgentState(TypedDict):
    # Input
    session_id:          str
    user_message:        str
    history:             List[Dict]
    last_sql:            Optional[str]
    last_rows:           List[Dict]
    start_time:          float

    # Role management
    role:                Optional[str]
    pending_role:        Optional[str]
    mismatch_count:      int
    language:            str

    # Routing flags
    suggest_switch:      bool
    switch_message:      Optional[str]
    force_reset:         bool

    # SQL output
    sql:                 Optional[str]
    db_result:           Optional[Dict]
    answer:              str
    error:               Optional[str]
    latency_ms:          Optional[int]

    # Image attachment (for dispute receipt OCR)
    image_data:          Optional[Dict]  # {base64, type}

    # Path-specific
    export_requested:    bool
    dispute_found:       bool
    reversal_recommended:bool
    original_tx_id:      Optional[str]
    duplicate_tx_id:     Optional[str]
    confidence:          float
    missing_points:      int
    credit_recommended:  bool
    pan_enrolled:        bool

# ── Helpers ───────────────────────────────────────────────────
def call_claude(system: str, messages: List[Dict], max_tokens: int = 1024) -> str:
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages
    )
    return response.content[0].text.strip()

def parse_json_response(raw: str) -> Dict:
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())

def safe_parse(raw: str) -> tuple:
    try:
        parsed = parse_json_response(raw)
        return parsed, parsed.get("answer", raw), None
    except (json.JSONDecodeError, ValueError, KeyError):
        return None, raw, "no_sql"

def build_messages(state: AgentState) -> List[Dict]:
    messages = list(state["history"])
    content  = state["user_message"]
    if state["last_sql"]:
        content += f"\n\nPrevious SQL for context:\n{state['last_sql']}"
        if state["last_rows"]:
            content += f"\nPrevious query returned {len(state['last_rows'])} rows."
    messages.append({"role": "user", "content": content})
    return messages

def is_switch_confirmation(msg: str) -> bool:
    return msg.strip().lower() in CONFIRM_SWITCH_WORDS

def is_menu_request(msg: str) -> bool:
    return msg.strip().lower() in MENU_WORDS

# ── NODE 1: Hybrid Router ─────────────────────────────────────
def router_node(state: AgentState) -> AgentState:
    current_role   = state.get("role")
    pending_role   = state.get("pending_role")
    mismatch_count = state.get("mismatch_count", 0)
    user_message   = state["user_message"]
    language       = state.get("language", "en")

    # User requests main menu
    if is_menu_request(user_message):
        logger.info(f"[{state['session_id']}] Menu reset requested")
        return {
            **state,
            "role":           None,
            "pending_role":   None,
            "mismatch_count": 0,
            "suggest_switch": False,
            "force_reset":    True,
            "answer":         MISMATCH_RESPONSES[3][language],
            "error":          "no_sql",
        }

    # User confirming suggested switch
    if pending_role and is_switch_confirmation(user_message):
        logger.info(f"[{state['session_id']}] Switch confirmed: {current_role} → {pending_role}")
        answer = (
            f"Prebačeni ste na kanal {pending_role.title()}. Kako mogu pomoći?"
            if language == "sr"
            else f"Switched to {pending_role.title()} channel. How can I help you?"
        )
        return {
            **state,
            "role":           pending_role,
            "pending_role":   None,
            "mismatch_count": 0,
            "suggest_switch": False,
            "switch_message": None,
            "force_reset":    False,
            "answer":         answer,
            "error":          "no_sql",
        }

    # Call router LLM
    try:
        router_input = (
            f"current_channel: {current_role or 'none'}\n"
            f"message: {user_message}"
        )
        raw = call_claude(
            system=ROUTER_PROMPT,
            messages=[{"role": "user", "content": router_input}],
            max_tokens=512
        )
        parsed        = parse_json_response(raw)
        detected_role = parsed.get("detected_role", current_role or "CARDHOLDER")
        confidence    = float(parsed.get("confidence", 0.0))
        suggest       = parsed.get("suggest_switch", False)
        switch_msg    = parsed.get("switch_message")
        language      = parsed.get("language", language)

        logger.info(
            f"[{state['session_id']}] Router: current={current_role} "
            f"detected={detected_role} conf={confidence:.2f} "
            f"suggest={suggest} mismatches={mismatch_count}"
        )

        # No role yet — set it from detection
        if not current_role:
            return {
                **state,
                "role":           detected_role,
                "language":       language,
                "mismatch_count": 0,
                "suggest_switch": False,
                "switch_message": None,
                "force_reset":    False,
                "error":          None,
            }

        # Check for mismatch
        is_mismatch = (
            suggest
            and confidence >= 0.85
            and detected_role != current_role
        )

        # Message matches channel — reset mismatch counter and proceed
        if not is_mismatch:
            return {
                **state,
                "role":           current_role,
                "language":       language,
                "mismatch_count": 0,
                "pending_role":   None,
                "suggest_switch": False,
                "switch_message": None,
                "force_reset":    False,
                "error":          None,
            }

        # Mismatch — apply strike policy
        new_count = mismatch_count + 1
        logger.info(
            f"[{state['session_id']}] Strike {new_count}: "
            f"{current_role} → {detected_role}"
        )

        # Strike 3 — force reset
        if new_count >= 3:
            msg = MISMATCH_RESPONSES[3].get(language, MISMATCH_RESPONSES[3]["en"])
            return {
                **state,
                "role":           None,
                "pending_role":   None,
                "mismatch_count": 0,
                "suggest_switch": False,
                "force_reset":    True,
                "answer":         msg,
                "error":          "no_sql",
            }

        # Strike 1 or 2 — suggest switch
        fallback = MISMATCH_RESPONSES[new_count].get(
            language, MISMATCH_RESPONSES[new_count]["en"]
        )
        final_msg = switch_msg or fallback
        return {
            **state,
            "role":           current_role,
            "pending_role":   detected_role,
            "language":       language,
            "mismatch_count": new_count,
            "suggest_switch": True,
            "switch_message": final_msg,
            "force_reset":    False,
            "answer":         final_msg,
            "error":          "no_sql",
        }

    except Exception as e:
        logger.error(f"Router error: {e}")
        return {
            **state,
            "role":           current_role or "CARDHOLDER",
            "language":       language,
            "mismatch_count": mismatch_count,
            "suggest_switch": False,
            "force_reset":    False,
            "error":          None,
        }

# ── NODE 2a: Cardholder ───────────────────────────────────────
def cardholder_node(state: AgentState) -> AgentState:
    try:
        messages            = build_messages(state)
        raw                 = call_claude(system=CARDHOLDER_PROMPT, messages=messages)
        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql":    parsed.get("sql") if parsed else None,
            "answer": answer,
            "error":  err,
        }
    except Exception as e:
        logger.error(f"Cardholder node error: {e}")
        return {**state, "sql": None,
                "answer": "Sorry, could not process your request.", "error": str(e)}

# ── NODE 2b: Merchant ─────────────────────────────────────────
def merchant_node(state: AgentState) -> AgentState:
    try:
        messages            = build_messages(state)
        raw                 = call_claude(system=MERCHANT_PROMPT, messages=messages)
        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql":              parsed.get("sql") if parsed else None,
            "answer":           answer,
            "export_requested": parsed.get("export_requested", False) if parsed else False,
            "error":            err,
        }
    except Exception as e:
        logger.error(f"Merchant node error: {e}")
        return {**state, "sql": None,
                "answer": "Sorry, could not process your request.", "error": str(e)}

# ── NODE 2c: Dispute ──────────────────────────────────────────
def dispute_node(state: AgentState) -> AgentState:
    try:
        messages = build_messages(state)
        image    = state.get("image_data")

        # If image attached — use Claude Vision
        if image and image.get("base64"):
            # Replace last user message with vision content
            vision_content = [
                {
                    "type": "image",
                    "source": {
                        "type":       "base64",
                        "media_type": image.get("type", "image/png"),
                        "data":       image["base64"],
                    }
                },
                {
                    "type": "text",
                    "text": (
                        f"{state['user_message']}\n\n"
                        "Please read the receipt image above carefully. "
                        "Extract: merchant name, amount, date, time, "
                        "card last 4 digits, approval code. "
                        "Then search the database for this transaction "
                        "and check for duplicates."
                    )
                }
            ]
            # Replace last message with vision content
            vision_messages = list(state["history"])
            vision_messages.append({"role": "user", "content": vision_content})
            raw = call_claude(system=DISPUTE_PROMPT, messages=vision_messages)
        else:
            raw = call_claude(system=DISPUTE_PROMPT, messages=messages)

        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql":                   parsed.get("sql") if parsed else None,
            "answer":                answer,
            "dispute_found":         parsed.get("dispute_found", False) if parsed else False,
            "confidence":            parsed.get("confidence", 0.0) if parsed else 0.0,
            "reversal_recommended":  parsed.get("reversal_recommended", False) if parsed else False,
            "original_tx_id":        parsed.get("original_transaction_id") if parsed else None,
            "duplicate_tx_id":       parsed.get("duplicate_transaction_id") if parsed else None,
            "error":                 err,
        }
    except Exception as e:
        logger.error(f"Dispute node error: {e}")
        return {**state, "sql": None,
                "answer": "Sorry, could not process your dispute.", "error": str(e)}

# ── NODE 2d: Loyalty ──────────────────────────────────────────
def loyalty_node(state: AgentState) -> AgentState:
    try:
        messages            = build_messages(state)
        raw                 = call_claude(system=LOYALTY_PROMPT, messages=messages)
        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql":                parsed.get("sql") if parsed else None,
            "answer":             answer,
            "pan_enrolled":       parsed.get("pan_enrolled", False) if parsed else False,
            "missing_points":     parsed.get("missing_points", 0) if parsed else 0,
            "credit_recommended": parsed.get("credit_recommended", False) if parsed else False,
            "error":              err,
        }
    except Exception as e:
        logger.error(f"Loyalty node error: {e}")
        return {**state, "sql": None,
                "answer": "Sorry, could not process your loyalty query.", "error": str(e)}

# ── NODE 3: Validator ─────────────────────────────────────────
def validate_node(state: AgentState) -> AgentState:
    sql = state.get("sql")
    if not sql:
        return {**state, "error": "no_sql"}
    if not is_safe_sql(sql):
        return {**state, "sql": None,
                "answer": "I can only run read-only queries.", "error": "unsafe_sql"}
    return {**state, "error": None}

# ── NODE 4: Executor ──────────────────────────────────────────
def execute_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return state
    result = execute_query(state["sql"])
    return {
        **state,
        "db_result":  result,
        "latency_ms": int((time.time() - state["start_time"]) * 1000),
    }

# ── NODE 5: Formatter ─────────────────────────────────────────
def format_node(state: AgentState) -> AgentState:
    db_result  = state.get("db_result") or {}
    rows       = db_result.get("rows", [])
    row_count  = db_result.get("row_count", 0)
    answer     = state["answer"]
    latency_ms = int((time.time() - state["start_time"]) * 1000)

    if db_result.get("success") and row_count == 0:
        answer = (
            "Nema pronađenih transakcija za ovaj upit."
            if state.get("language") == "sr"
            else "No transactions found matching your query."
        )
    elif db_result.get("success") and str(row_count) not in answer:
        answer = f"{answer} ({row_count} result{'s' if row_count != 1 else ''})"
    elif not db_result.get("success") and db_result.get("error"):
        answer = f"Query could not be executed: {db_result['error']}"
        rows   = []

    excel_file = None
    if state.get("export_requested") and rows:
        try:
            excel_file = export_to_excel(rows)
        except Exception as e:
            logger.error(f"Excel export error: {e}")

    log_query(
        session_id   = state["session_id"],
        user_message = state["user_message"],
        role         = state.get("role", "UNKNOWN"),
        sql          = state.get("sql"),
        row_count    = row_count,
        latency_ms   = latency_ms,
        error        = state.get("error"),
    )

    return {
        **state,
        "answer":      answer,
        "db_result":   {"success": True, "rows": rows, "row_count": row_count},
        "latency_ms":  latency_ms,
        "_excel_file": excel_file,
    }

# ── Routing decisions ─────────────────────────────────────────
def route_after_router(state: AgentState) -> str:
    if state.get("suggest_switch") or state.get("force_reset") or state.get("error") == "no_sql":
        return "format"
    role = state.get("role", "CARDHOLDER")
    return {
        "CARDHOLDER": "cardholder",
        "MERCHANT":   "merchant",
        "DISPUTE":    "dispute",
        "LOYALTY":    "loyalty",
    }.get(role, "cardholder")

def should_execute(state: AgentState) -> str:
    if state.get("error") in ("no_sql", "unsafe_sql"):
        return "skip"
    return "execute"

# ── Build graph ───────────────────────────────────────────────
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("router",     router_node)
    graph.add_node("cardholder", cardholder_node)
    graph.add_node("merchant",   merchant_node)
    graph.add_node("dispute",    dispute_node)
    graph.add_node("loyalty",    loyalty_node)
    graph.add_node("validate",   validate_node)
    graph.add_node("execute",    execute_node)
    graph.add_node("format",     format_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "format":     "format",
            "cardholder": "cardholder",
            "merchant":   "merchant",
            "dispute":    "dispute",
            "loyalty":    "loyalty",
        }
    )

    for path in ["cardholder", "merchant", "dispute", "loyalty"]:
        graph.add_edge(path, "validate")

    graph.add_conditional_edges(
        "validate", should_execute,
        {"execute": "execute", "skip": "format"}
    )

    graph.add_edge("execute", "format")
    graph.add_edge("format",  END)

    return graph.compile()

GRAPH = build_graph()

# ── Public interface ──────────────────────────────────────────
async def run_agent(
    session_id:    str,
    user_message:  str,
    session_store,
    image_data:    dict = None,
) -> Dict[str, Any]:

    session = session_store.get_or_create(session_id)

    initial_state: AgentState = {
        "session_id":          session_id,
        "user_message":        user_message,
        "history":             list(session["history"]),
        "last_sql":            session.get("last_sql"),
        "last_rows":           session.get("last_rows", []),
        "start_time":          time.time(),
        "role":                session.get("role"),
        "pending_role":        session.get("pending_role"),
        "mismatch_count":      session.get("mismatch_count", 0),
        "language":            session.get("language", "en"),
        "suggest_switch":      False,
        "switch_message":      None,
        "force_reset":         False,
        "image_data":          image_data,
        "sql":                 None,
        "db_result":           None,
        "answer":              "",
        "error":               None,
        "latency_ms":          None,
        "export_requested":    False,
        "dispute_found":       False,
        "reversal_recommended":False,
        "original_tx_id":      None,
        "duplicate_tx_id":     None,
        "confidence":          0.0,
        "missing_points":      0,
        "credit_recommended":  False,
        "pan_enrolled":        False,
    }

    final_state = GRAPH.invoke(initial_state)

    db_result = final_state.get("db_result") or {}
    rows      = db_result.get("rows", [])
    row_count = db_result.get("row_count", 0)
    role      = final_state.get("role")

    # Update session
    session_store.update(
        session_id        = session_id,
        user_message      = user_message,
        assistant_message = final_state["answer"],
        sql               = final_state.get("sql"),
        rows              = rows,
        role              = role,
        language          = final_state.get("language", "en"),
    )

    # Persist extra fields
    session_data                   = session_store.get_or_create(session_id)
    session_data["pending_role"]   = final_state.get("pending_role")
    session_data["mismatch_count"] = final_state.get("mismatch_count", 0)

    if final_state.get("force_reset"):
        session_store.reset_to_menu(session_id)

    return {
        "answer":               final_state["answer"],
        "sql":                  final_state.get("sql"),
        "rows":                 rows,
        "row_count":            row_count,
        "role":                 role,
        "language":             final_state.get("language", "en"),
        "latency_ms":           final_state.get("latency_ms"),
        "suggest_switch":       final_state.get("suggest_switch", False),
        "switch_message":       final_state.get("switch_message"),
        "pending_role":         final_state.get("pending_role"),
        "force_reset":          final_state.get("force_reset", False),
        "mismatch_count":       final_state.get("mismatch_count", 0),
        "dispute_found":        final_state.get("dispute_found", False),
        "reversal_recommended": final_state.get("reversal_recommended", False),
        "original_tx_id":       final_state.get("original_tx_id"),
        "duplicate_tx_id":      final_state.get("duplicate_tx_id"),
        "confidence":           final_state.get("confidence", 0.0),
        "missing_points":       final_state.get("missing_points", 0),
        "credit_recommended":   final_state.get("credit_recommended", False),
        "pan_enrolled":         final_state.get("pan_enrolled", False),
        "export_file":          final_state.get("_excel_file"),
    }
