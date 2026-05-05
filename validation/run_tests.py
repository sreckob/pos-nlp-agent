"""
Validation Test Runner
======================
Runs all test cases from test_cases.json against the deployed or local agent.
Measures SQL correctness, result accuracy, path-specific flags, and router behaviour.

Usage:
    # Test local backend (seed DB first with --seed)
    python run_tests.py --seed

    # Test without re-seeding
    python run_tests.py

    # Test deployed Railway backend
    python run_tests.py --url wss://pos-nlp-agent-production.up.railway.app

    # Test specific category only
    python run_tests.py --category dispute

    # Save results to file
    python run_tests.py --seed --output results.json

Seed scripts run before tests when --seed is given:
    db/supabase/topup.py      — adds recent transactions
    db/supabase/demo_seed.py  — seeds 3 dispute pairs + 2 loyalty scenarios

Categories covered:
    exact_match, range_query, aggregation, multi_filter, status_filter,
    edge_case, multi_turn,
    cardholder, merchant, dispute, loyalty, router
"""

import asyncio
import json
import argparse
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import Optional

import websockets

# ── Config ────────────────────────────────────────────────────
DEFAULT_WS_URL   = "ws://localhost:8000"
TEST_CASES_FILE  = "test_cases.json"
SEED_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "db", "supabase")


# ── Seed helpers ──────────────────────────────────────────────

def run_seed_scripts():
    """Run topup.py then demo_seed.py to prepare fresh demo data."""
    scripts = ["topup.py", "demo_seed.py"]
    for script in scripts:
        path = os.path.join(SEED_SCRIPTS_DIR, script)
        print(f"  Running {script}...")
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  WARNING: {script} exited {result.returncode}")
            if result.stderr:
                print(f"  {result.stderr[:200]}")
        else:
            last = [l for l in result.stdout.strip().splitlines() if l]
            if last:
                print(f"  ✓ {last[-1]}")


# ── WS helpers ────────────────────────────────────────────────

async def send_and_receive(ws, message: str, timeout: int = 45) -> dict:
    """Send a message and wait for the next response frame."""
    await ws.send(json.dumps({"message": message}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(raw)
        if data.get("type") in ("response", "error"):
            return data


async def prime_channel(ws, channel: str, timeout: int = 30):
    """Send a silent priming message to set the router's current_channel."""
    greetings = {
        "CARDHOLDER": "I am a cardholder and want to check my transactions",
        "MERCHANT":   "I am a merchant and want to view my terminal transactions",
        "DISPUTE":    "I am a cardholder and I have a dispute about a double charge",
        "LOYALTY":    "I am a loyalty member and want to check my points",
    }
    greeting = greetings.get(channel)
    if greeting:
        await send_and_receive(ws, greeting, timeout=timeout)


# ── Result evaluation ─────────────────────────────────────────

def check_sql_contains(sql: Optional[str], expected: list) -> tuple:
    if not expected:
        return True, []
    if not sql:
        return False, expected
    sql_upper = sql.upper()
    missing = [kw for kw in expected if kw.upper() not in sql_upper]
    return len(missing) == 0, missing


def evaluate_result(response: dict, expected_result: str, sql: Optional[str]) -> tuple:
    """
    Returns (passed: bool, reason: str).

    Supported expected_result values:
        has_results       — row_count > 0
        no_results        — row_count == 0
        zero_or_more      — always passes
        blocked           — SQL was blocked by read-only guard
        clarification     — agent asked for more info (no SQL or 0 rows)
        dispute_found     — response.dispute_found == True
        no_dispute        — response.dispute_found == False (and no spurious card shown)
        enrolled          — response.pan_enrolled == True
        not_enrolled      — response.pan_enrolled == False
        credit_recommended— response.credit_recommended == True
        suggest_switch    — response.suggest_switch == True
    """
    row_count = response.get("row_count", 0)
    message   = (response.get("message") or "").lower()

    if expected_result == "has_results":
        if row_count > 0:
            return True, f"✓ {row_count} rows returned"
        return False, "✗ Expected results but got 0 rows"

    if expected_result == "no_results":
        if row_count == 0:
            return True, "✓ Correctly returned no results"
        return False, f"✗ Expected no results but got {row_count} rows"

    if expected_result == "zero_or_more":
        return True, f"✓ {row_count} rows (zero or more acceptable)"

    if expected_result == "blocked":
        if sql is None and any(w in message for w in ["only", "select", "blocked", "cannot", "read-only"]):
            return True, "✓ Query correctly blocked"
        if sql and any(kw in sql.upper() for kw in ["DELETE", "DROP", "UPDATE", "INSERT"]):
            return False, "✗ Destructive SQL was generated"
        return True, f"✓ No destructive SQL (sql={'present' if sql else 'None'})"

    if expected_result == "clarification":
        if sql is None or row_count == 0:
            return True, "✓ Agent asked for clarification"
        return False, f"✗ Expected clarification but got SQL with {row_count} rows"

    if expected_result == "dispute_found":
        if response.get("dispute_found"):
            return True, f"✓ dispute_found=True, reversal_recommended={response.get('reversal_recommended')}"
        return False, "✗ Expected dispute_found=True but agent did not detect duplicate"

    if expected_result == "no_dispute":
        if not response.get("dispute_found"):
            return True, "✓ Correctly found no duplicate"
        return False, "✗ Agent hallucinated a dispute where none should exist"

    if expected_result == "enrolled":
        if response.get("pan_enrolled"):
            return True, f"✓ pan_enrolled=True, missing_points={response.get('missing_points', 0)}"
        return False, "✗ Expected pan_enrolled=True but card not found in loyalty_accounts"

    if expected_result == "not_enrolled":
        if not response.get("pan_enrolled"):
            return True, "✓ Correctly identified card as not enrolled"
        return False, "✗ Agent wrongly reported card as enrolled"

    if expected_result == "credit_recommended":
        if response.get("credit_recommended") and response.get("pan_enrolled"):
            pts = response.get("missing_points", 0)
            return True, f"✓ credit_recommended=True, missing_points={pts}"
        if not response.get("pan_enrolled"):
            return False, "✗ Card not enrolled — cannot check credit_recommended"
        return False, "✗ credit_recommended=False despite being enrolled"

    if expected_result == "suggest_switch":
        if response.get("suggest_switch"):
            pending = response.get("pending_role", "?")
            return True, f"✓ suggest_switch=True, pending_role={pending}"
        return False, "✗ Expected suggest_switch=True but router did not suggest switch"

    return True, f"✓ Passed (unknown criteria: {expected_result})"


# ── Single-turn test ──────────────────────────────────────────

async def run_single_turn_test(ws_url: str, test: dict) -> dict:
    session_id = f"test-{test['id']}-{uuid.uuid4().hex[:6]}"
    uri = f"{ws_url}/ws/{session_id}"

    result = {
        "id":               test["id"],
        "category":         test["category"],
        "language":         test["language"],
        "prompt":           test["prompt"],
        "passed":           False,
        "sql":              None,
        "row_count":        0,
        "answer":           "",
        "missing_keywords": [],
        "reason":           "",
        "latency_ms":       0,
    }

    try:
        async with websockets.connect(uri) as ws:
            start = time.time()

            # Prime the router with the expected channel if specified.
            if test.get("router_current_channel"):
                await prime_channel(ws, test["router_current_channel"])

            response = await send_and_receive(ws, test["prompt"])
            result["latency_ms"] = int((time.time() - start) * 1000)

            sql = response.get("sql")
            result["sql"]       = sql
            result["row_count"] = response.get("row_count", 0)
            result["answer"]    = response.get("message", "")

            sql_ok, missing = check_sql_contains(sql, test.get("expected_sql_contains", []))
            result["missing_keywords"] = missing

            result_ok, reason = evaluate_result(response, test["expected_result"], sql)

            # Check any extra expected flags (e.g. has_export).
            flag_ok = True
            for flag, expected_val in test.get("expected_flags", {}).items():
                actual = response.get(flag)
                if actual != expected_val:
                    flag_ok = False
                    reason += f" | flag {flag}={actual} (expected {expected_val})"

            result["passed"] = sql_ok and result_ok and flag_ok
            result["reason"] = reason
            if missing:
                result["reason"] += f" | Missing SQL: {missing}"

    except Exception as e:
        result["reason"] = f"ERROR: {e}"

    return result


# ── Multi-turn test ───────────────────────────────────────────

async def run_multi_turn_test(ws_url: str, test: dict) -> dict:
    session_id = f"test-{test['id']}-{uuid.uuid4().hex[:6]}"
    uri = f"{ws_url}/ws/{session_id}"

    result = {
        "id":         test["id"],
        "category":   test["category"],
        "language":   test["language"],
        "turns":      [],
        "passed":     False,
        "reason":     "",
        "latency_ms": 0,
    }

    try:
        async with websockets.connect(uri) as ws:
            start = time.time()
            all_passed = True

            for i, turn in enumerate(test["turns"]):
                response = await send_and_receive(ws, turn["prompt"])
                sql = response.get("sql")

                sql_ok, missing = check_sql_contains(sql, turn.get("expected_sql_contains", []))
                result_ok, reason = evaluate_result(
                    response,
                    turn.get("expected_result", "zero_or_more"),
                    sql
                )

                turn_passed = sql_ok and result_ok
                all_passed  = all_passed and turn_passed

                result["turns"].append({
                    "turn":             i + 1,
                    "prompt":           turn["prompt"],
                    "sql":              sql,
                    "row_count":        response.get("row_count", 0),
                    "passed":           turn_passed,
                    "missing_keywords": missing,
                    "reason":           reason,
                })

            result["latency_ms"] = int((time.time() - start) * 1000)
            result["passed"]     = all_passed
            result["reason"]     = "All turns passed" if all_passed else "One or more turns failed"

    except Exception as e:
        result["reason"] = f"ERROR: {e}"

    return result


# ── Main runner ───────────────────────────────────────────────

async def run_all_tests(ws_url: str, category_filter: Optional[str] = None) -> dict:
    with open(TEST_CASES_FILE) as f:
        test_cases = json.load(f)

    if category_filter:
        test_cases = [t for t in test_cases if t["category"] == category_filter]
        print(f"Running {len(test_cases)} tests in category: {category_filter}")
    else:
        print(f"Running {len(test_cases)} test cases...")

    results = []
    passed  = 0
    failed  = 0

    for test in test_cases:
        label = test.get("prompt", "multi-turn")[:60]
        print(f"  [{test['id']}] {label}...", end=" ", flush=True)

        if test["category"] == "multi_turn":
            result = await run_multi_turn_test(ws_url, test)
        else:
            result = await run_single_turn_test(ws_url, test)

        results.append(result)

        if result["passed"]:
            passed += 1
            print("✓")
        else:
            failed += 1
            print(f"✗  → {result['reason']}")

        await asyncio.sleep(0.5)

    total    = passed + failed
    accuracy = (passed / total * 100) if total else 0

    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"passed": 0, "total": 0}
        categories[cat]["total"] += 1
        if r["passed"]:
            categories[cat]["passed"] += 1

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "ws_url":    ws_url,
        "summary": {
            "total":        total,
            "passed":       passed,
            "failed":       failed,
            "accuracy_pct": round(accuracy, 1),
        },
        "by_category": {
            cat: {
                "passed":       v["passed"],
                "total":        v["total"],
                "accuracy_pct": round(v["passed"] / v["total"] * 100, 1),
            }
            for cat, v in categories.items()
        },
        "results": results,
    }


def print_summary(report: dict):
    s = report["summary"]
    print("\n" + "=" * 55)
    print(f"VALIDATION RESULTS — {report['timestamp'][:10]}")
    print("=" * 55)
    print(f"Total:    {s['total']}")
    print(f"Passed:   {s['passed']}")
    print(f"Failed:   {s['failed']}")
    print(f"Accuracy: {s['accuracy_pct']}%")
    print()
    print("By category:")
    for cat, v in report["by_category"].items():
        bar = "█" * int(v["accuracy_pct"] / 10) + "░" * (10 - int(v["accuracy_pct"] / 10))
        print(f"  {cat:<22} {bar}  {v['passed']}/{v['total']}  ({v['accuracy_pct']}%)")
    print("=" * 55)


async def main(ws_url: str, category: Optional[str], output: Optional[str], seed: bool):
    if seed:
        print("Seeding database...")
        run_seed_scripts()
        print("Seed complete. Waiting 2s for DB to settle...")
        await asyncio.sleep(2)
        print()

    report = await run_all_tests(ws_url, category)
    print_summary(report)

    if output:
        with open(output, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nFull report saved to: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run validation tests against the NLP agent")
    parser.add_argument("--url",      default=DEFAULT_WS_URL,
                        help="WebSocket base URL (default: ws://localhost:8000)")
    parser.add_argument("--category", help="Filter by category (e.g. dispute, loyalty, router)")
    parser.add_argument("--output",   help="Save full JSON report to file")
    parser.add_argument("--seed",     action="store_true",
                        help="Run topup.py + demo_seed.py before tests")
    args = parser.parse_args()

    asyncio.run(main(args.url, args.category, args.output, args.seed))
