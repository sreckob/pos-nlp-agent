"""
iron_user.py — Simulated multi-turn conversation evaluation
============================================================
Implements the "Iron User" pattern from the lecture: a scripted user
that drives a full multi-turn conversation with fixed goals. Tests
context retention, multi-turn refinement, and channel-specific flows.

Each scenario has:
  - A sequence of fixed user messages
  - Per-turn assertions on what the response must contain
  - A final assertion on overall conversation success

Usage:
    cd validation
    python iron_user.py                        # local backend
    python iron_user.py --url wss://...        # deployed
    python iron_user.py --scenario cardholder  # single scenario
    python iron_user.py --output iron_user.json

Requires: backend running, websockets installed
"""

import argparse
import asyncio
import json
import time
import uuid
from datetime import datetime

import websockets

DEFAULT_WS_URL = "ws://localhost:8000"


# ── Iron User scenarios ───────────────────────────────────────

SCENARIOS = [
    {
        "name": "cardholder_multi_turn_refinement",
        "description": "Cardholder drills down from broad query to specific declined transaction",
        "channel": "CARDHOLDER",
        "turns": [
            {
                "message": "Show me my recent transactions",
                "assert_contains": [],  # agent asks for card or returns results
                "assert_flags": {},
                "note": "Agent should ask for card number or return results",
            },
            {
                "message": "My card ends in 4242",
                "assert_contains": ["4242"],
                "assert_flags": {},
                "note": "Agent should now filter by PAN 4242",
            },
            {
                "message": "Show only the declined ones",
                "assert_sql_contains": ["DECLINED", "4242"],
                "assert_flags": {},
                "note": "Agent should retain PAN context and add DECLINED filter",
            },
            {
                "message": "Sort by amount, largest first",
                "assert_sql_contains": ["ORDER BY", "amount"],
                "assert_flags": {},
                "note": "Agent should retain all filters and add ORDER BY",
            },
        ],
    },
    {
        "name": "loyalty_full_flow",
        "description": "Loyalty member checks balance then requests missing points credit",
        "channel": "LOYALTY",
        "turns": [
            {
                "message": "I want to check my loyalty points",
                "assert_contains": [],
                "assert_flags": {},
                "note": "Agent asks for card or shows loyalty info",
            },
            {
                "message": "My card ends in 4242",
                "assert_contains": [],
                "assert_flags": {},
                "note": "Agent should look up loyalty account for card 4242",
            },
            {
                "message": "I think some points were not credited from last week",
                "assert_contains": [],
                "assert_flags": {"credit_recommended": True},
                "note": "Agent should detect uncredited transactions and recommend credit",
            },
        ],
    },
    {
        "name": "dispute_full_flow",
        "description": "Cardholder reports double charge, agent detects duplicate",
        "channel": "DISPUTE",
        "turns": [
            {
                "message": "I was charged twice at Maxi for the same purchase",
                "assert_contains": [],
                "assert_flags": {},
                "note": "Agent should ask for card details or start investigating",
            },
            {
                "message": "My Visa card ending in 4242, amount was 3240.50 RSD",
                "assert_contains": [],
                "assert_flags": {},
                "note": "Agent should search for duplicates with this PAN/amount",
            },
            {
                "message": "Yes that's correct, please check if I was charged twice",
                "assert_contains": [],
                "assert_flags": {"dispute_found": True},
                "note": "Agent should confirm duplicate found and recommend reversal",
            },
        ],
    },
    {
        "name": "merchant_excel_flow",
        "description": "Merchant queries declined transactions then exports to Excel",
        "channel": "MERCHANT",
        "turns": [
            {
                "message": "I am merchant T00101. Show me all declined transactions from last week",
                "assert_sql_contains": ["DECLINED"],
                "assert_flags": {},
                "note": "Agent should generate SQL with DECLINED filter and date range",
            },
            {
                "message": "How many of those were Visa?",
                "assert_sql_contains": ["DECLINED", "VISA"],
                "assert_flags": {},
                "note": "Agent retains DECLINED filter and adds VISA filter",
            },
            {
                "message": "Export all declined transactions from terminal T00101 last week to Excel",
                "assert_contains": [],
                "assert_flags": {"has_export": True},
                "note": "Agent should trigger Excel export",
            },
        ],
    },
    {
        "name": "router_channel_switch",
        "description": "User starts in CARDHOLDER, describes a dispute, switches to DISPUTE channel",
        "channel": "CARDHOLDER",
        "turns": [
            {
                "message": "Show me my transactions for card ending in 4242",
                "assert_sql_contains": ["4242"],
                "assert_flags": {},
                "note": "Normal cardholder query — stays in channel",
            },
            {
                "message": "I was charged twice at Maxi, I want to dispute this double charge",
                "assert_contains": [],
                "assert_flags": {"suggest_switch": True},
                "note": "Router should detect DISPUTE intent and suggest switch",
            },
            {
                "message": "yes",
                "assert_contains": [],
                "assert_flags": {},
                "note": "User confirms switch — should be in DISPUTE channel now",
            },
        ],
    },
]


# ── WebSocket helpers ─────────────────────────────────────────

async def send_and_receive(ws, message: str, timeout: int = 45) -> dict:
    await ws.send(json.dumps({"message": message}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(raw)
        if data.get("type") in ("response", "error"):
            return data


async def prime_channel(ws, channel: str):
    greetings = {
        "CARDHOLDER": "I am a cardholder and want to check my transactions",
        "MERCHANT":   "I am a merchant reviewing my terminal data",
        "DISPUTE":    "I have a dispute about a double charge on my card",
        "LOYALTY":    "I am a loyalty member checking my points balance",
    }
    await send_and_receive(ws, greetings[channel])


# ── Turn evaluation ───────────────────────────────────────────

def evaluate_turn(response: dict, turn: dict, turn_num: int) -> tuple:
    """Returns (passed, list_of_reasons)."""
    reasons = []
    passed  = True

    # Check assert_contains (in message text)
    for phrase in turn.get("assert_contains", []):
        msg = (response.get("message") or "").lower()
        if phrase.lower() not in msg:
            reasons.append(f"message missing '{phrase}'")
            passed = False

    # Check assert_sql_contains (in generated SQL)
    for kw in turn.get("assert_sql_contains", []):
        sql = (response.get("sql") or "").upper()
        if kw.upper() not in sql:
            reasons.append(f"SQL missing '{kw}' (sql={sql[:80]})")
            passed = False

    # Check assert_flags (response flags)
    for flag, expected in turn.get("assert_flags", {}).items():
        actual = response.get(flag)
        if actual != expected:
            reasons.append(f"flag {flag}={actual} (expected {expected})")
            passed = False

    return passed, reasons


# ── Single scenario runner ────────────────────────────────────

async def run_scenario(ws_url: str, scenario: dict) -> dict:
    session_id = f"iron-{uuid.uuid4().hex[:8]}"
    uri = f"{ws_url}/ws/{session_id}"

    result = {
        "name":        scenario["name"],
        "description": scenario["description"],
        "channel":     scenario["channel"],
        "turns":       [],
        "passed":      False,
        "reason":      "",
    }

    try:
        async with websockets.connect(uri) as ws:
            await prime_channel(ws, scenario["channel"])
            all_passed = True

            for i, turn in enumerate(scenario["turns"]):
                t0 = time.time()
                response = await send_and_receive(ws, turn["message"])
                ms = int((time.time() - t0) * 1000)

                turn_passed, reasons = evaluate_turn(response, turn, i + 1)
                all_passed = all_passed and turn_passed

                turn_result = {
                    "turn":       i + 1,
                    "message":    turn["message"],
                    "note":       turn.get("note", ""),
                    "passed":     turn_passed,
                    "reasons":    reasons,
                    "sql":        response.get("sql"),
                    "row_count":  response.get("row_count", 0),
                    "latency_ms": ms,
                }
                result["turns"].append(turn_result)

                symbol = "✓" if turn_passed else f"✗ {reasons}"
                print(f"    Turn {i+1}: {symbol}  [{ms}ms]")
                if not turn_passed:
                    print(f"      Message: {turn['message']}")
                    for r in reasons:
                        print(f"      → {r}")

                await asyncio.sleep(0.5)

            result["passed"] = all_passed
            result["reason"] = "All turns passed" if all_passed else f"{sum(1 for t in result['turns'] if not t['passed'])} turn(s) failed"

    except Exception as e:
        result["reason"] = f"ERROR: {e}"

    return result


# ── Main ──────────────────────────────────────────────────────

async def run_iron_user(ws_url: str, scenario_filter: str = None) -> dict:
    scenarios = SCENARIOS
    if scenario_filter:
        scenarios = [s for s in SCENARIOS if scenario_filter in s["name"]]
        if not scenarios:
            print(f"No scenario matching '{scenario_filter}'")
            return {}

    print(f"Iron User — {len(scenarios)} scenario(s) — {ws_url}")
    print("=" * 60)

    results = []
    passed = failed = 0

    for scenario in scenarios:
        print(f"\nScenario: {scenario['name']}")
        print(f"  {scenario['description']}")
        result = await run_scenario(ws_url, scenario)
        results.append(result)
        if result["passed"]:
            passed += 1
            print(f"  → PASSED")
        else:
            failed += 1
            print(f"  → FAILED: {result['reason']}")

    total_turns  = sum(len(r["turns"]) for r in results)
    passed_turns = sum(sum(1 for t in r["turns"] if t["passed"]) for r in results)

    print(f"\n{'='*60}")
    print(f"Scenarios: {passed}/{passed+failed} passed")
    print(f"Turns:     {passed_turns}/{total_turns} passed")

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "ws_url": ws_url,
        "summary": {
            "scenarios_passed":  passed,
            "scenarios_failed":  failed,
            "scenarios_total":   passed + failed,
            "turns_passed":      passed_turns,
            "turns_total":       total_turns,
        },
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",      default=DEFAULT_WS_URL)
    parser.add_argument("--scenario", default=None, help="Filter by scenario name substring")
    parser.add_argument("--output",   default=None)
    args = parser.parse_args()

    report = asyncio.run(run_iron_user(args.url, args.scenario))

    if args.output and report:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {args.output}")
