"""
Agent — v2.0
=============
LangGraph agent with router and four specialist paths.

Graph structure:
  [router]
      ├── CARDHOLDER → [cardholder_agent]
      ├── MERCHANT   → [merchant_agent]
      ├── DISPUTE    → [dispute_agent]
      └── LOYALTY    → [loyalty_agent]

Each path shares:
  - Conversation history from session
  - Last SQL query
  - Last result set
  - Detected language

All LLM calls use Anthropic SDK directly.
All tool calls use plain Python functions from executor.py.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, TypedDict

import anthropic
from langgraph.graph import StateGraph, END

from config import settings
from executor import execute_query, is_safe_sql, export_to_excel
from prompts import (
    ROUTER_PROMPT, get_prompt,
    CARDHOLDER_PROMPT, MERCHANT_PROMPT,
    DISPUTE_PROMPT, LOYALTY_PROMPT
)
from logger import log_query

logger = logging.getLogger(__name__)

# ── Anthropic client ──────────────────────────────────────────
client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# ── Agent state ───────────────────────────────────────────────
class AgentState(TypedDict):
    # Input
    session_id:     str
    user_message:   str
    history:        List[Dict]
    last_sql:       Optional[str]
    last_rows:      List[Dict]
    start_time:     float

    # Router output
    role:           Optional[str]   # CARDHOLDER, MERCHANT, DISPUTE, LOYALTY
    language:       str             # sr, en

    # SQL agent output
    sql:            Optional[str]
    db_result:      Optional[Dict]
    answer:         str
    error:          Optional[str]
    latency_ms:     Optional[int]

    # Path-specific flags
    export_requested:        bool
    dispute_found:           bool
    reversal_recommended:    bool
    original_tx_id:          Optional[str]
    duplicate_tx_id:         Optional[str]
    confidence:              float
    missing_points:          int
    credit_recommended:      bool
    pan_enrolled:            bool

# ── Helper: call Claude ───────────────────────────────────────
def call_claude(system: str, messages: List[Dict],
                max_tokens: int = 1024) -> str:
    """Call Claude Sonnet and return raw text response."""
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages
    )
    return response.content[0].text.strip()

def parse_json_response(raw: str) -> Dict:
    """Parse JSON from Claude response, stripping markdown fences if present."""
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())

def build_messages(state: AgentState) -> List[Dict]:
    """Build message list for Claude including context about previous query."""
    messages = list(state["history"])
    content  = state["user_message"]

    # Add context about previous query if this is a refinement
    if state["last_sql"]:
        content += f"\n\nPrevious SQL for context:\n{state['last_sql']}"
        if state["last_rows"]:
            content += f"\nPrevious query returned {len(state['last_rows'])} rows."

    messages.append({"role": "user", "content": content})
    return messages

# ── NODE 1: Router ────────────────────────────────────────────
def router_node(state: AgentState) -> AgentState:
    """
    Classify the user's role and intent.
    Only runs on the first turn (role is None) or when re-classification needed.
    """
    try:
        raw = call_claude(
            system=ROUTER_PROMPT,
            messages=[{"role": "user", "content": state["user_message"]}],
            max_tokens=256
        )
        parsed   = parse_json_response(raw)
        role     = parsed.get("role", "CARDHOLDER")
        language = parsed.get("language", "en")
        logger.info(
            f"[{state['session_id']}] Router: role={role} "
            f"lang={language} confidence={parsed.get('confidence', 0):.2f}"
        )
        return {**state, "role": role, "language": language, "error": None}

    except Exception as e:
        logger.error(f"Router error: {e}")
        return {**state, "role": "CARDHOLDER", "language": "en", "error": str(e)}

# ── Shared: safe JSON parse with plain-text fallback ──────────
def safe_parse(raw: str, extra_defaults: dict = None) -> tuple:
    """
    Try to parse JSON from Claude response.
    If it fails (Claude returned a clarification in plain text),
    return (None, raw_text, "no_sql") so the agent handles it gracefully.
    Returns: (parsed_dict | None, answer_str, error_str | None)
    """
    try:
        parsed = parse_json_response(raw)
        return parsed, parsed.get("answer", raw), None
    except (json.JSONDecodeError, ValueError, KeyError):
        # Claude returned plain text — treat as clarification, no SQL
        return None, raw, "no_sql"

# ── NODE 2a: Cardholder agent ─────────────────────────────────
def cardholder_node(state: AgentState) -> AgentState:
    try:
        messages        = build_messages(state)
        raw             = call_claude(system=CARDHOLDER_PROMPT, messages=messages)
        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql":    parsed.get("sql") if parsed else None,
            "answer": answer,
            "error":  err
        }
    except Exception as e:
        logger.error(f"Cardholder node error: {e}")
        return {**state, "sql": None, "answer": "Sorry, could not process your request.", "error": str(e)}

# ── NODE 2b: Merchant agent ───────────────────────────────────
def merchant_node(state: AgentState) -> AgentState:
    try:
        messages        = build_messages(state)
        raw             = call_claude(system=MERCHANT_PROMPT, messages=messages)
        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql":              parsed.get("sql") if parsed else None,
            "answer":           answer,
            "export_requested": parsed.get("export_requested", False) if parsed else False,
            "error":            err
        }
    except Exception as e:
        logger.error(f"Merchant node error: {e}")
        return {**state, "sql": None, "answer": "Sorry, could not process your request.", "error": str(e)}

# ── NODE 2c: Dispute agent ────────────────────────────────────
def dispute_node(state: AgentState) -> AgentState:
    try:
        messages        = build_messages(state)
        raw             = call_claude(system=DISPUTE_PROMPT, messages=messages)
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
            "error":                 err
        }
    except Exception as e:
        logger.error(f"Dispute node error: {e}")
        return {**state, "sql": None, "answer": "Sorry, could not process your dispute.", "error": str(e)}

# ── NODE 2d: Loyalty agent ────────────────────────────────────
def loyalty_node(state: AgentState) -> AgentState:
    try:
        messages        = build_messages(state)
        raw             = call_claude(system=LOYALTY_PROMPT, messages=messages)
        parsed, answer, err = safe_parse(raw)
        return {
            **state,
            "sql":                parsed.get("sql") if parsed else None,
            "answer":             answer,
            "pan_enrolled":       parsed.get("pan_enrolled", False) if parsed else False,
            "missing_points":     parsed.get("missing_points", 0) if parsed else 0,
            "credit_recommended": parsed.get("credit_recommended", False) if parsed else False,
            "error":              err
        }
    except Exception as e:
        logger.error(f"Loyalty node error: {e}")
        return {**state, "sql": None, "answer": "Sorry, could not process your loyalty query.", "error": str(e)}

# ── NODE 3: SQL validator ─────────────────────────────────────
def validate_node(state: AgentState) -> AgentState:
    """Safety check — block any destructive SQL."""
    sql = state.get("sql")
    if not sql:
        return {**state, "error": "no_sql"}
    if not is_safe_sql(sql):
        return {
            **state,
            "sql":    None,
            "answer": "I can only run read-only queries.",
            "error":  "unsafe_sql"
        }
    return {**state, "error": None}

# ── NODE 4: SQL executor ──────────────────────────────────────
def execute_node(state: AgentState) -> AgentState:
    """Execute the validated SQL against PostgreSQL."""
    if state.get("error"):
        return state

    result = execute_query(state["sql"])
    return {
        **state,
        "db_result":  result,
        "latency_ms": int((time.time() - state["start_time"]) * 1000)
    }

# ── NODE 5: Response formatter ────────────────────────────────
def format_node(state: AgentState) -> AgentState:
    """Build final response, handle Excel export, log the cycle."""
    db_result  = state.get("db_result") or {}
    rows       = db_result.get("rows", [])
    row_count  = db_result.get("row_count", 0)
    answer     = state["answer"]
    latency_ms = int((time.time() - state["start_time"]) * 1000)

    if db_result.get("success") and row_count == 0:
        if state.get("language") == "sr":
            answer = "Nema pronađenih transakcija za ovaj upit."
        else:
            answer = "No transactions found matching your query."
    elif db_result.get("success") and str(row_count) not in answer:
        answer = f"{answer} ({row_count} result{'s' if row_count != 1 else ''})"
    elif not db_result.get("success") and db_result.get("error"):
        answer = f"Query could not be executed: {db_result['error']}"
        rows   = []

    # Handle Excel export for merchant path
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
        error        = state.get("error")
    )

    return {
        **state,
        "answer":     answer,
        "db_result":  {"success": True, "rows": rows, "row_count": row_count},
        "latency_ms": latency_ms,
        "_excel_file": excel_file
    }

# ── Routing functions ─────────────────────────────────────────
def route_by_role(state: AgentState) -> str:
    """Route to the correct path based on classified role."""
    role = state.get("role", "CARDHOLDER")
    return {
        "CARDHOLDER": "cardholder",
        "MERCHANT":   "merchant",
        "DISPUTE":    "dispute",
        "LOYALTY":    "loyalty",
    }.get(role, "cardholder")

def should_execute(state: AgentState) -> str:
    """Skip execution if SQL is missing or unsafe."""
    if state.get("error") in ("no_sql", "unsafe_sql"):
        return "skip"
    return "execute"

# ── Build the graph ───────────────────────────────────────────
def build_graph():
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("router",     router_node)
    graph.add_node("cardholder", cardholder_node)
    graph.add_node("merchant",   merchant_node)
    graph.add_node("dispute",    dispute_node)
    graph.add_node("loyalty",    loyalty_node)
    graph.add_node("validate",   validate_node)
    graph.add_node("execute",    execute_node)
    graph.add_node("format",     format_node)

    # Entry point
    graph.set_entry_point("router")

    # Router → one of four paths
    graph.add_conditional_edges(
        "router",
        route_by_role,
        {
            "cardholder": "cardholder",
            "merchant":   "merchant",
            "dispute":    "dispute",
            "loyalty":    "loyalty",
        }
    )

    # All four paths → validate
    for path in ["cardholder", "merchant", "dispute", "loyalty"]:
        graph.add_edge(path, "validate")

    # Validate → execute or skip to format
    graph.add_conditional_edges(
        "validate",
        should_execute,
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
    session_store
) -> Dict[str, Any]:
    """
    Run one turn of the multi-path agent.
    Returns dict with answer, sql, rows, row_count, role, latency_ms.
    """
    session = session_store.get_or_create(session_id)

    # Use existing role if already classified (skip router on follow-up turns)
    existing_role = session.get("role")

    initial_state: AgentState = {
        "session_id":            session_id,
        "user_message":          user_message,
        "history":               list(session["history"]),
        "last_sql":              session.get("last_sql"),
        "last_rows":             session.get("last_rows", []),
        "start_time":            time.time(),
        "role":                  existing_role,  # None on first turn → router classifies
        "language":              session.get("language", "en"),
        "sql":                   None,
        "db_result":             None,
        "answer":                "",
        "error":                 None,
        "latency_ms":            None,
        "export_requested":      False,
        "dispute_found":         False,
        "reversal_recommended":  False,
        "original_tx_id":        None,
        "duplicate_tx_id":       None,
        "confidence":            0.0,
        "missing_points":        0,
        "credit_recommended":    False,
        "pan_enrolled":          False,
    }

    final_state = await asyncio.to_thread(GRAPH.invoke, initial_state)

    db_result = final_state.get("db_result") or {}
    rows      = db_result.get("rows", [])
    row_count = db_result.get("row_count", 0)
    role      = final_state.get("role", "CARDHOLDER")

    # Update session
    session_store.update(
        session_id        = session_id,
        user_message      = user_message,
        assistant_message = final_state["answer"],
        sql               = final_state.get("sql"),
        rows              = rows,
        role              = role,
        language          = final_state.get("language", "en")
    )

    return {
        "answer":               final_state["answer"],
        "sql":                  final_state.get("sql"),
        "rows":                 rows,
        "row_count":            row_count,
        "role":                 role,
        "language":             final_state.get("language", "en"),
        "latency_ms":           final_state.get("latency_ms"),
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
