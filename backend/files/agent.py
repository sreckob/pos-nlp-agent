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
import re
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END

from config import settings
from executor import execute_query, is_safe_sql, export_to_excel
from llm_client import complete, complete_vision
from prompts import (
    ROUTER_PROMPT,
    CARDHOLDER_PROMPT,
    MERCHANT_PROMPT,
    DISPUTE_PROMPT,
    LOYALTY_PROMPT,
)
from logger import log_query

logger = logging.getLogger(__name__)

# ── Switch / menu keywords ────────────────────────────────────
CONFIRM_SWITCH_WORDS = {
    "yes",
    "da",
    "ok",
    "okay",
    "switch",
    "prebaci",
    "yes please",
    "da molim",
    "confirm",
    "potvrdi",
}
MENU_WORDS = {"menu", "meni", "back", "nazad", "home", "početak", "restart"}

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
    session_id: str
    user_message: str
    history: List[Dict]
    last_sql: Optional[str]
    last_rows: List[Dict]
    start_time: float

    # Role management
    role: Optional[str]
    pending_role: Optional[str]
    mismatch_count: int
    language: str

    # Routing flags
    suggest_switch: bool
    switch_message: Optional[str]
    force_reset: bool

    # SQL output
    sql: Optional[str]
    db_result: Optional[Dict]
    answer: str
    error: Optional[str]
    latency_ms: Optional[int]

    # Image attachment (for dispute receipt OCR)
    image_data: Optional[Dict]  # {base64, type}

    # Path-specific
    export_requested: bool
    dispute_found: bool
    reversal_recommended: bool
    original_tx_id: Optional[str]
    duplicate_tx_id: Optional[str]
    confidence: float
    missing_points: int
    credit_recommended: bool
    pan_enrolled: bool
    pan_masked: Optional[str]


# ── Helpers ───────────────────────────────────────────────────
def call_claude(system: str, messages: List[Dict], max_tokens: int = 1024, node: str = "router") -> str:
    """Wrapper kept for backward compat — delegates to llm_client.complete()."""
    temperature = settings.TEMPERATURES.get(node, 0.0)
    return complete(system, messages, max_tokens, temperature)


def parse_json_response(raw: str) -> Dict:
    # Locate the outermost {...} block — robust to leading prose,
    # ```json fences, and extra ```sql blocks around the JSON.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in response")
    return json.loads(match.group(0))


def safe_parse(raw: str) -> tuple:
    try:
        parsed = parse_json_response(raw)
        return parsed, parsed.get("answer", raw), None
    except (json.JSONDecodeError, ValueError, KeyError):
        # Strip fenced code blocks so SQL/JSON doesn't leak to the chat.
        cleaned = re.sub(r"```[\w]*\n?.*?```", "", raw, flags=re.DOTALL).strip()
        # If the remaining text still looks like SQL, replace with a
        # safe generic message rather than dumping it into the bubble.
        if re.search(r"\bSELECT\b|\bFROM\b|\bWHERE\b|\bJOIN\b", cleaned, re.IGNORECASE):
            cleaned = (
                "I had trouble preparing that response. "
                "Could you rephrase your request?"
            )
        elif not cleaned:
            cleaned = "Sorry, I couldn't process that. Please try again."
        return None, cleaned, "no_sql"


def build_messages(state: AgentState) -> List[Dict]:
    messages = list(state["history"])
    content = state["user_message"]
    if state["last_sql"]:
        content += f"\n\nPrevious SQL for context:\n{state['last_sql']}"
        if state["last_rows"]:
            content += f"\nPrevious query returned {len(state['last_rows'])} rows."
    messages.append({"role": "user", "content": content})
    return messages


def is_switch_confirmation(msg: str) -> bool:
    return msg.strip().lower() in CONFIRM_SWITCH_WORDS


def _is_short_reply(msg: str) -> bool:
    """Return True if the message looks like a reply to a previous question
    rather than a new intent — digits only, very short, or a simple yes/no."""
    stripped = msg.strip()
    if len(stripped) <= 10 and stripped.replace(" ", "").isdigit():
        return True
    if len(stripped) <= 20 and re.match(r"^[\d\s\.\,\*]+$", stripped):
        return True
    if stripped.lower() in {"da", "ne", "yes", "no", "ok", "ок"}:
        return True
    return False


def is_menu_request(msg: str) -> bool:
    return msg.strip().lower() in MENU_WORDS


# ── NODE 1: Hybrid Router ─────────────────────────────────────
def router_node(state: AgentState) -> AgentState:
    current_role = state.get("role")
    pending_role = state.get("pending_role")
    mismatch_count = state.get("mismatch_count", 0)
    user_message = state["user_message"]
    language = state.get("language", "en")

    # User requests main menu
    if is_menu_request(user_message):
        logger.info(f"[{state['session_id']}] Menu reset requested")
        return {
            **state,
            "role": None,
            "pending_role": None,
            "mismatch_count": 0,
            "suggest_switch": False,
            "force_reset": True,
            "answer": MISMATCH_RESPONSES[3][language],
            "error": "no_sql",
        }

    # User confirming suggested switch
    if pending_role and is_switch_confirmation(user_message):
        logger.info(
            f"[{state['session_id']}] Switch confirmed: {current_role} → {pending_role}"
        )
        answer = (
            f"Prebačeni ste na kanal {pending_role.title()}. Kako mogu pomoći?"
            if language == "sr"
            else f"Switched to {pending_role.title()} channel. How can I help you?"
        )
        return {
            **state,
            "role": pending_role,
            "pending_role": None,
            "mismatch_count": 0,
            "suggest_switch": False,
            "switch_message": None,
            "force_reset": False,
            "answer": answer,
            "error": "no_sql",
            "history": [],  # clear context on channel switch — prevents cross-channel pollution
        }

    # Fix 2 — short-message bypass: digit-only or very short replies are answers
    # to the previous prompt, not new intents. Skip LLM and stay in current channel.
    if current_role and _is_short_reply(user_message):
        logger.info(
            f"[{state['session_id']}] Short-reply bypass: staying in {current_role}"
        )
        return {
            **state,
            "role": current_role,
            "language": language,
            "mismatch_count": 0,
            "pending_role": None,
            "suggest_switch": False,
            "switch_message": None,
            "force_reset": False,
            "error": None,
        }

    # Fix 3 — pass last assistant message so router knows what the agent just asked
    last_assistant = ""
    if state.get("history"):
        for msg in reversed(state["history"]):
            if msg.get("role") == "assistant":
                last_assistant = msg["content"][:300]
                break

    # Call router LLM
    try:
        router_input = (
            f"current_channel: {current_role or 'none'}\n"
            f"last_assistant_message: {last_assistant or 'none'}\n"
            f"message: {user_message}"
        )
        raw = call_claude(
            system=ROUTER_PROMPT,
            messages=[{"role": "user", "content": router_input}],
            max_tokens=512,
            node="router",
        )
        parsed = parse_json_response(raw)
        detected_role = parsed.get("detected_role", current_role or "CARDHOLDER")
        confidence = float(parsed.get("confidence", 0.0))
        suggest = parsed.get("suggest_switch", False)
        switch_msg = parsed.get("switch_message")
        language = parsed.get("language", language)

        logger.info(
            f"[{state['session_id']}] Router: current={current_role} "
            f"detected={detected_role} conf={confidence:.2f} "
            f"suggest={suggest} mismatches={mismatch_count}"
        )

        # No role yet — set it from detection
        if not current_role:
            return {
                **state,
                "role": detected_role,
                "language": language,
                "mismatch_count": 0,
                "suggest_switch": False,
                "switch_message": None,
                "force_reset": False,
                "error": None,
            }

        # Check for mismatch
        is_mismatch = suggest and confidence >= 0.85 and detected_role != current_role

        # Message matches channel — reset mismatch counter and proceed
        if not is_mismatch:
            return {
                **state,
                "role": current_role,
                "language": language,
                "mismatch_count": 0,
                "pending_role": None,
                "suggest_switch": False,
                "switch_message": None,
                "force_reset": False,
                "error": None,
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
                "role": None,
                "pending_role": None,
                "mismatch_count": 0,
                "suggest_switch": False,
                "force_reset": True,
                "answer": msg,
                "error": "no_sql",
            }

        # Strike 1 or 2 — suggest switch
        fallback = MISMATCH_RESPONSES[new_count].get(
            language, MISMATCH_RESPONSES[new_count]["en"]
        )
        final_msg = switch_msg or fallback
        return {
            **state,
            "role": current_role,
            "pending_role": detected_role,
            "language": language,
            "mismatch_count": new_count,
            "suggest_switch": True,
            "switch_message": final_msg,
            "force_reset": False,
            "answer": final_msg,
            "error": "no_sql",
        }

    except Exception as e:
        logger.error(f"Router error: {e}")
        return {
            **state,
            "role": current_role or "CARDHOLDER",
            "language": language,
            "mismatch_count": mismatch_count,
            "suggest_switch": False,
            "force_reset": False,
            "error": None,
        }


# ── NODE 2a: Cardholder ───────────────────────────────────────
def cardholder_node(state: AgentState) -> AgentState:
    try:
        messages = build_messages(state)
        raw = call_claude(system=CARDHOLDER_PROMPT, messages=messages, node="cardholder")
        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql": parsed.get("sql") if parsed else None,
            "answer": answer,
            "error": err,
        }
    except Exception as e:
        logger.error(f"Cardholder node error: {e}")
        return {
            **state,
            "sql": None,
            "answer": "Sorry, could not process your request.",
            "error": str(e),
        }


# ── NODE 2b: Merchant ─────────────────────────────────────────
def merchant_node(state: AgentState) -> AgentState:
    try:
        messages = build_messages(state)
        raw = call_claude(system=MERCHANT_PROMPT, messages=messages, node="merchant")
        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql": parsed.get("sql") if parsed else None,
            "answer": answer,
            "export_requested": (
                parsed.get("export_requested", False) if parsed else False
            ),
            "error": err,
        }
    except Exception as e:
        logger.error(f"Merchant node error: {e}")
        return {
            **state,
            "sql": None,
            "answer": "Sorry, could not process your request.",
            "error": str(e),
        }


# ── NODE 2c: Dispute ──────────────────────────────────────────
def dispute_node(state: AgentState) -> AgentState:
    try:
        messages = build_messages(state)
        image = state.get("image_data")

        # If image attached — use Claude Vision
        if image and image.get("base64"):
            # Replace last user message with vision content
            vision_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.get("type", "image/png"),
                        "data": image["base64"],
                    },
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
                    ),
                },
            ]
            # Replace last message with vision content
            vision_messages = list(state["history"])
            vision_messages.append({"role": "user", "content": vision_content})
            # Vision path always uses complete_vision() → VISION_MODEL (Claude by default)
            temperature = settings.TEMPERATURES.get("dispute", 0.0)
            raw = complete_vision(
                system      = DISPUTE_PROMPT,
                messages    = vision_messages,
                temperature = temperature,
            )
        else:
            raw = call_claude(system=DISPUTE_PROMPT, messages=messages, node="dispute")

        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql": parsed.get("sql") if parsed else None,
            "answer": answer,
            "dispute_found": parsed.get("dispute_found", False) if parsed else False,
            "confidence": parsed.get("confidence", 0.0) if parsed else 0.0,
            "reversal_recommended": (
                parsed.get("reversal_recommended", False) if parsed else False
            ),
            "original_tx_id": parsed.get("original_transaction_id") if parsed else None,
            "duplicate_tx_id": (
                parsed.get("duplicate_transaction_id") if parsed else None
            ),
            "error": err,
        }
    except Exception as e:
        logger.error(f"Dispute node error: {e}")
        return {
            **state,
            "sql": None,
            "answer": "Sorry, could not process your dispute.",
            "error": str(e),
        }


# ── NODE 2d: Loyalty ──────────────────────────────────────────
def loyalty_node(state: AgentState) -> AgentState:
    try:
        messages = build_messages(state)
        raw = call_claude(system=LOYALTY_PROMPT, messages=messages, node="loyalty")
        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql": parsed.get("sql") if parsed else None,
            "answer": answer,
            "pan_enrolled": parsed.get("pan_enrolled", False) if parsed else False,
            "missing_points": parsed.get("missing_points", 0) if parsed else 0,
            "credit_recommended": (
                parsed.get("credit_recommended", False) if parsed else False
            ),
            "pan_masked": parsed.get("pan_masked") if parsed else None,
            "error": err,
        }
    except Exception as e:
        logger.error(f"Loyalty node error: {e}")
        return {
            **state,
            "sql": None,
            "answer": "Sorry, could not process your loyalty query.",
            "error": str(e),
        }


# ── NODE 3: Validator ─────────────────────────────────────────
def validate_node(state: AgentState) -> AgentState:
    sql = state.get("sql")
    if not sql:
        return {**state, "error": "no_sql"}
    if not is_safe_sql(sql):
        return {
            **state,
            "sql": None,
            "answer": "I can only run read-only queries.",
            "error": "unsafe_sql",
        }
    return {**state, "error": None}


# ── NODE 4: Executor ──────────────────────────────────────────
def execute_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return state
    result = execute_query(state["sql"])
    return {
        **state,
        "db_result": result,
        "latency_ms": int((time.time() - state["start_time"]) * 1000),
    }


# ── NODE 5: Formatter ─────────────────────────────────────────
def format_node(state: AgentState) -> AgentState:
    db_result = state.get("db_result") or {}
    rows = db_result.get("rows", [])
    row_count = db_result.get("row_count", 0)
    answer = state["answer"]
    latency_ms = int((time.time() - state["start_time"]) * 1000)

    if db_result.get("success") and row_count == 0:
        is_sr = state.get("language") == "sr"
        is_disp = state.get("role") == "DISPUTE"
        is_loy = state.get("role") == "LOYALTY"
        if is_disp:
            answer = (
                "Nisam pronašao duplikat zaduženja za navedene podatke. "
                "Ako možete, pošaljite naziv prodavca ili približan datum "
                "i pokušaću ponovo."
                if is_sr
                else "I could not find a duplicate charge for those details. "
                "If you can, share the merchant name or the approximate date "
                "and I'll search again."
            )
        elif is_loy:
            answer = (
                "Nema nekreditiranih poena za ovu karticu. Da li je tačan "
                "broj kartice (poslednje 4 cifre)?"
                if is_sr
                else "No uncredited points were found for that card. "
                "Could you confirm the card last 4 digits?"
            )
        else:
            answer = (
                "Nema pronađenih transakcija za ovaj upit."
                if is_sr
                else "No transactions found matching your query."
            )
    elif db_result.get("success") and str(row_count) not in answer:
        answer = f"{answer} ({row_count} result{'s' if row_count != 1 else ''})"
    elif not db_result.get("success") and db_result.get("error"):
        answer = f"Query could not be executed: {db_result['error']}"
        rows = []

    # ── Fix dispute IDs from actual DB results ────────────────
    # Claude sometimes generates truncated/invalid UUIDs in its JSON.
    # When we have real DB rows from the duplicate detection query,
    # extract the actual transaction IDs directly from the result.
    original_tx_id = state.get("original_tx_id")
    duplicate_tx_id = state.get("duplicate_tx_id")
    dispute_found = state.get("dispute_found", False)
    reversal_recommended = state.get("reversal_recommended", False)
    pan_enrolled = state.get("pan_enrolled", False)
    credit_recommended = state.get("credit_recommended", False)
    missing_points = state.get("missing_points", 0)

    if state.get("role") == "DISPUTE":
        if rows and len(rows) >= 1:
            first_row = rows[0]
            # Pattern A: SQL used the t1/t2 self-join → row has dup_id
            if "transaction_id" in first_row and "dup_id" in first_row:
                original_tx_id = first_row.get("transaction_id")
                duplicate_tx_id = first_row.get("dup_id")
            # Pattern B: SQL returned the duplicate pair as two separate rows
            elif (
                len(rows) >= 2
                and "transaction_id" in first_row
                and "transaction_id" in rows[1]
            ):
                original_tx_id = first_row.get("transaction_id")
                duplicate_tx_id = rows[1].get("transaction_id")
            # When we have a real pair, force the flags ON so the UI
            # always offers a Submit button. The investigator agent is
            # sometimes too conservative even when the DB confirms.
            if original_tx_id and duplicate_tx_id and original_tx_id != duplicate_tx_id:
                dispute_found = True
                reversal_recommended = True
                logger.info(
                    f"Extracted real dispute IDs from DB: "
                    f"original={str(original_tx_id)[:8]} "
                    f"duplicate={str(duplicate_tx_id)[:8]}"
                )
            else:
                # SQL ran but didn't produce a usable pair.
                dispute_found = False
                reversal_recommended = False
                original_tx_id = None
                duplicate_tx_id = None
        else:
            # No rows → SQL found no duplicate. Override Claude's flags so
            # the UI does not render a hallucinated DisputeCard.
            dispute_found = False
            reversal_recommended = False
            original_tx_id = None
            duplicate_tx_id = None

    pan_masked = state.get("pan_masked")

    if state.get("role") == "LOYALTY":
        if not rows:
            credit_recommended = False
            missing_points = 0
        else:
            # Sum uncredited points from DB rows. If the SELECT pulled
            # loyalty_points_earned + loyalty_points_credited, we know the
            # gap exactly — trust the DB over Claude's flags.
            first = rows[0]
            if "loyalty_points_earned" in first:
                gap_rows = [
                    r
                    for r in rows
                    if r.get("loyalty_points_credited") is False
                    and (r.get("loyalty_points_earned") or 0) > 0
                ]
                if gap_rows:
                    db_missing = sum(
                        int(r.get("loyalty_points_earned") or 0) for r in gap_rows
                    )
                    missing_points = db_missing
                    credit_recommended = True

            # Extract pan_masked from rows if Claude didn't put it in JSON.
            if not pan_masked and "pan_masked" in first:
                pan_masked = first.get("pan_masked")

        # Last-ditch: try to recover pan_masked from the SQL text.
        if not pan_masked and state.get("sql"):
            m = re.search(
                r"pan_masked\s*(?:ILIKE|=)\s*'([^']+)'", state["sql"], re.IGNORECASE
            )
            if m:
                tail = m.group(1).replace("%", "")
                # If we only got the last 4 digits, look up the full masked
                # PAN in loyalty_accounts so /loyalty/submit can match exactly.
                if len(tail) <= 6:
                    safe = re.sub(r"[^0-9]", "", tail)
                    if safe:
                        from executor import execute_query

                        r = execute_query(
                            f"SELECT pan_masked FROM loyalty_accounts "
                            f"WHERE pan_masked ILIKE '%{safe}'"
                        )
                        if r.get("rows"):
                            pan_masked = r["rows"][0].get("pan_masked")
                else:
                    pan_masked = tail

    excel_file = None
    if state.get("export_requested") and rows:
        try:
            excel_file = export_to_excel(rows)
        except Exception as e:
            logger.error(f"Excel export error: {e}")

    log_query(
        session_id=state["session_id"],
        user_message=state["user_message"],
        role=state.get("role", "UNKNOWN"),
        sql=state.get("sql"),
        row_count=row_count,
        latency_ms=latency_ms,
        error=state.get("error"),
    )

    return {
        **state,
        "answer": answer,
        "db_result": {"success": True, "rows": rows, "row_count": row_count},
        "latency_ms": latency_ms,
        "_excel_file": excel_file,
        "original_tx_id": original_tx_id,
        "duplicate_tx_id": duplicate_tx_id,
        "dispute_found": dispute_found,
        "reversal_recommended": reversal_recommended,
        "pan_enrolled": pan_enrolled,
        "credit_recommended": credit_recommended,
        "missing_points": missing_points,
        "pan_masked": pan_masked,
    }


# ── Routing decisions ─────────────────────────────────────────
def route_after_router(state: AgentState) -> str:
    if (
        state.get("suggest_switch")
        or state.get("force_reset")
        or state.get("error") == "no_sql"
    ):
        return "format"
    role = state.get("role", "CARDHOLDER")
    return {
        "CARDHOLDER": "cardholder",
        "MERCHANT": "merchant",
        "DISPUTE": "dispute",
        "LOYALTY": "loyalty",
    }.get(role, "cardholder")


def should_execute(state: AgentState) -> str:
    if state.get("error") in ("no_sql", "unsafe_sql"):
        return "skip"
    return "execute"


# ── Build graph ───────────────────────────────────────────────
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("cardholder", cardholder_node)
    graph.add_node("merchant", merchant_node)
    graph.add_node("dispute", dispute_node)
    graph.add_node("loyalty", loyalty_node)
    graph.add_node("validate", validate_node)
    graph.add_node("execute", execute_node)
    graph.add_node("format", format_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "format": "format",
            "cardholder": "cardholder",
            "merchant": "merchant",
            "dispute": "dispute",
            "loyalty": "loyalty",
        },
    )

    for path in ["cardholder", "merchant", "dispute", "loyalty"]:
        graph.add_edge(path, "validate")

    graph.add_conditional_edges(
        "validate", should_execute, {"execute": "execute", "skip": "format"}
    )

    graph.add_edge("execute", "format")
    graph.add_edge("format", END)

    return graph.compile()


GRAPH = build_graph()


# ── Public interface ──────────────────────────────────────────
async def run_agent(
    session_id: str,
    user_message: str,
    session_store,
    image_data: dict = None,
) -> Dict[str, Any]:

    session = session_store.get_or_create(session_id)

    initial_state: AgentState = {
        "session_id": session_id,
        "user_message": user_message,
        "history": list(session["history"]),
        "last_sql": session.get("last_sql"),
        "last_rows": session.get("last_rows", []),
        "start_time": time.time(),
        "role": session.get("role"),
        "pending_role": session.get("pending_role"),
        "mismatch_count": session.get("mismatch_count", 0),
        "language": session.get("language", "en"),
        "suggest_switch": False,
        "switch_message": None,
        "force_reset": False,
        "image_data": image_data,
        "sql": None,
        "db_result": None,
        "answer": "",
        "error": None,
        "latency_ms": None,
        "export_requested": False,
        "dispute_found": False,
        "reversal_recommended": False,
        "original_tx_id": None,
        "duplicate_tx_id": None,
        "confidence": 0.0,
        "missing_points": 0,
        "credit_recommended": False,
        "pan_enrolled": False,
    }

    final_state = GRAPH.invoke(initial_state)

    db_result = final_state.get("db_result") or {}
    rows = db_result.get("rows", [])
    row_count = db_result.get("row_count", 0)
    role = final_state.get("role")

    # Update session
    session_store.update(
        session_id=session_id,
        user_message=user_message,
        assistant_message=final_state["answer"],
        sql=final_state.get("sql"),
        rows=rows,
        role=role,
        language=final_state.get("language", "en"),
    )

    # Persist extra fields
    session_data = session_store.get_or_create(session_id)
    session_data["pending_role"] = final_state.get("pending_role")
    session_data["mismatch_count"] = final_state.get("mismatch_count", 0)

    if final_state.get("force_reset"):
        session_store.reset_to_menu(session_id)

    return {
        "answer": final_state["answer"],
        "sql": final_state.get("sql"),
        "rows": rows,
        "row_count": row_count,
        "role": role,
        "language": final_state.get("language", "en"),
        "latency_ms": final_state.get("latency_ms"),
        "suggest_switch": final_state.get("suggest_switch", False),
        "switch_message": final_state.get("switch_message"),
        "pending_role": final_state.get("pending_role"),
        "force_reset": final_state.get("force_reset", False),
        "mismatch_count": final_state.get("mismatch_count", 0),
        "dispute_found": final_state.get("dispute_found", False),
        "reversal_recommended": final_state.get("reversal_recommended", False),
        "original_tx_id": final_state.get("original_tx_id"),
        "duplicate_tx_id": final_state.get("duplicate_tx_id"),
        "confidence": final_state.get("confidence", 0.0),
        "missing_points": final_state.get("missing_points", 0),
        "credit_recommended": final_state.get("credit_recommended", False),
        "pan_enrolled": final_state.get("pan_enrolled", False),
        "pan_masked": final_state.get("pan_masked"),
        "export_file": final_state.get("_excel_file"),
    }
