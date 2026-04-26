"""
Agent
=====
LangGraph-based conversational agent.

Graph nodes:
  1. generate_sql   — calls Claude Sonnet to translate NL → SQL
  2. validate_sql   — safety check (read-only guard)
  3. execute_sql    — runs query against PostgreSQL
  4. format_response — builds final answer for the client

State persists across turns via SessionStore:
  - conversation history (last 10 turns)
  - last SQL query
  - last result set
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, TypedDict

import anthropic
from langgraph.graph import StateGraph, END

from config import settings
from executor import execute_query, is_safe_sql
from prompts import SYSTEM_PROMPT
from logger import log_query

logger = logging.getLogger(__name__)

# ── Anthropic client ──────────────────────────────────────────
client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# ── Agent state ───────────────────────────────────────────────
class AgentState(TypedDict):
    session_id:     str
    user_message:   str
    history:        list
    last_sql:       Optional[str]
    last_rows:      list
    sql:            Optional[str]
    db_result:      Optional[Dict[str, Any]]
    answer:         str
    error:          Optional[str]
    latency_ms:     Optional[int]
    start_time:     float

# ── Node 1: Generate SQL ──────────────────────────────────────
def generate_sql(state: AgentState) -> AgentState:
    """
    Calls Claude Sonnet with the conversation history.
    Returns generated SQL and a preliminary answer.
    """
    # Build messages for Claude
    messages = list(state["history"])

    # Add context about previous query if this looks like a refinement
    context_note = ""
    if state["last_sql"]:
        context_note = f"\n\nPrevious SQL query for context:\n{state['last_sql']}"
        if state["last_rows"]:
            context_note += f"\nPrevious query returned {len(state['last_rows'])} rows."

    user_content = state["user_message"]
    if context_note:
        user_content = f"{user_content}{context_note}"

    messages.append({"role": "user", "content": user_content})

    try:
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        sql    = parsed.get("sql")
        answer = parsed.get("answer", "")

        return {
            **state,
            "sql":    sql,
            "answer": answer,
            "error":  None
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        return {
            **state,
            "sql":    None,
            "answer": "Sorry, I could not understand your request. Could you rephrase it?",
            "error":  "json_parse_error"
        }
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return {
            **state,
            "sql":    None,
            "answer": "Sorry, there was an error contacting the AI service. Please try again.",
            "error":  str(e)
        }

# ── Node 2: Validate SQL ──────────────────────────────────────
def validate_sql(state: AgentState) -> AgentState:
    """
    Checks that the generated SQL is safe to execute.
    Blocks any destructive statements.
    """
    sql = state.get("sql")

    if not sql:
        # No SQL generated — clarification needed, skip execution
        return {**state, "error": "no_sql"}

    if not is_safe_sql(sql):
        return {
            **state,
            "sql":    None,
            "answer": "I can only run read-only queries. Please ask about transaction data.",
            "error":  "unsafe_sql"
        }

    return {**state, "error": None}

# ── Node 3: Execute SQL ───────────────────────────────────────
def execute_sql(state: AgentState) -> AgentState:
    """
    Runs the validated SQL against PostgreSQL.
    """
    if state.get("error"):
        return state

    sql = state["sql"]
    result = execute_query(sql)

    return {
        **state,
        "db_result": result,
        "latency_ms": int((time.time() - state["start_time"]) * 1000)
    }

# ── Node 4: Format response ───────────────────────────────────
def format_response(state: AgentState) -> AgentState:
    """
    Builds the final answer enriched with actual row count from DB.
    Logs the full query cycle.
    """
    db_result = state.get("db_result")

    if db_result and db_result["success"]:
        rows      = db_result["rows"]
        row_count = db_result["row_count"]

        # Enrich the answer with actual count if it returned results
        answer = state["answer"]
        if row_count == 0:
            # No results found
            if "Serbian" in SYSTEM_PROMPT or any(
                c in state["user_message"] for c in "čćšđžČĆŠĐŽ"
            ):
                answer = f"Nema pronađenih transakcija za ovaj upit."
            else:
                answer = f"No transactions found matching your query."
        else:
            # Append row count context if not already in answer
            if str(row_count) not in answer:
                answer = f"{answer} ({row_count} result{'s' if row_count != 1 else ''})"

    elif db_result and not db_result["success"]:
        answer = (
            f"The query could not be executed: {db_result['error']}. "
            f"Please try rephrasing your question."
        )
        rows      = []
        row_count = 0
    else:
        rows      = []
        row_count = 0
        answer    = state["answer"]

    latency_ms = int((time.time() - state["start_time"]) * 1000)

    # Log the full cycle
    log_query(
        session_id   = state["session_id"],
        user_message = state["user_message"],
        sql          = state.get("sql"),
        row_count    = row_count,
        latency_ms   = latency_ms,
        error        = state.get("error")
    )

    return {
        **state,
        "answer":     answer,
        "db_result":  {
            "success":   True,
            "rows":      rows if db_result else [],
            "row_count": row_count
        },
        "latency_ms": latency_ms
    }

# ── Routing ───────────────────────────────────────────────────
def should_execute(state: AgentState) -> str:
    """Route to execute_sql or skip directly to format_response."""
    if state.get("error") in ("no_sql", "unsafe_sql", "json_parse_error"):
        return "skip"
    return "execute"

# ── Build the graph ───────────────────────────────────────────
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("generate_sql",    generate_sql)
    graph.add_node("validate_sql",    validate_sql)
    graph.add_node("execute_sql",     execute_sql)
    graph.add_node("format_response", format_response)

    graph.set_entry_point("generate_sql")

    graph.add_edge("generate_sql", "validate_sql")

    graph.add_conditional_edges(
        "validate_sql",
        should_execute,
        {
            "execute": "execute_sql",
            "skip":    "format_response"
        }
    )

    graph.add_edge("execute_sql",     "format_response")
    graph.add_edge("format_response", END)

    return graph.compile()

GRAPH = build_graph()

# ── Public interface ──────────────────────────────────────────
async def run_agent(
    session_id:    str,
    user_message:  str,
    session_store
) -> Dict[str, Any]:
    """
    Run one turn of the agent.
    Returns dict with answer, sql, rows, row_count, latency_ms.
    """
    session = session_store.get_or_create(session_id)

    initial_state: AgentState = {
        "session_id":   session_id,
        "user_message": user_message,
        "history":      list(session["history"]),
        "last_sql":     session.get("last_sql"),
        "last_rows":    session.get("last_rows", []),
        "sql":          None,
        "db_result":    None,
        "answer":       "",
        "error":        None,
        "latency_ms":   None,
        "start_time":   time.time()
    }

    final_state = await asyncio.to_thread(GRAPH.invoke, initial_state)

    db_result = final_state.get("db_result") or {}
    rows      = db_result.get("rows", [])
    row_count = db_result.get("row_count", 0)
    answer    = final_state["answer"]
    sql       = final_state.get("sql")

    # Update session state
    session_store.update(
        session_id       = session_id,
        user_message     = user_message,
        assistant_message= answer,
        sql              = sql,
        rows             = rows
    )

    return {
        "answer":     answer,
        "sql":        sql,
        "rows":       rows,
        "row_count":  row_count,
        "latency_ms": final_state.get("latency_ms")
    }
