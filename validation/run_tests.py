"""
Validation Test Runner
======================
Runs all test cases from test_cases.json against the deployed or local agent.
Measures SQL correctness, result accuracy, and multi-turn context retention.

Usage:
    # Test local backend
    python run_tests.py

    # Test deployed Railway backend
    python run_tests.py --url wss://pos-nlp-agent-production.up.railway.app

    # Test specific category only
    python run_tests.py --category multi_turn

    # Save results to file
    python run_tests.py --output results.json
"""

import asyncio
import json
import argparse
import time
import uuid
from datetime import datetime
from typing import Optional

import websockets

# ── Config ────────────────────────────────────────────────────
DEFAULT_WS_URL = "ws://localhost:8000"
TEST_CASES_FILE = "test_cases.json"

# ── Helpers ───────────────────────────────────────────────────

async def send_and_receive(ws, message: str, timeout: int = 30) -> dict:
    """Send a message and wait for response."""
    await ws.send(json.dumps({"message": message}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(raw)
        if data.get("type") == "response":
            return data
        if data.get("type") == "error":
            return data
        # skip typing indicator


def check_sql_contains(sql: Optional[str], expected: list) -> tuple:
    """Check if generated SQL contains all expected keywords."""
    if not expected:
        return True, []
    if not sql:
        return False, expected
    sql_upper = sql.upper()
    missing = [kw for kw in expected if kw.upper() not in sql_upper]
    return len(missing) == 0, missing


def evaluate_result(response: dict, expected_result: str, sql: Optional[str]) -> tuple:
    """
    Evaluate whether the response meets the expected result criteria.
    Returns (passed: bool, reason: str)
    """
    row_count = response.get("row_count", 0)
    message = response.get("message", "").lower()

    if expected_result == "has_results":
        if row_count > 0:
            return True, f"✓ {row_count} rows returned"
        return False, f"✗ Expected results but got 0 rows"

    elif expected_result == "no_results":
        if row_count == 0:
            return True, "✓ Correctly returned no results"
        return False, f"✗ Expected no results but got {row_count} rows"

    elif expected_result == "zero_or_more":
        return True, f"✓ {row_count} rows returned (zero or more acceptable)"

    elif expected_result == "blocked":
        if sql is None and ("only" in message or "select" in message or "blocked" in message or "cannot" in message):
            return True, "✓ Query correctly blocked"
        if sql and any(kw in sql.upper() for kw in ["DELETE", "DROP", "UPDATE", "INSERT"]):
            return False, "✗ Destructive SQL was generated and possibly executed"
        return True, f"✓ No destructive SQL generated (sql={sql})"

    elif expected_result == "clarification":
        if sql is None or row_count == 0:
            return True, "✓ Agent asked for clarification or returned no SQL"
        return False, f"✗ Expected clarification but got SQL: {sql}"

    return True, "✓ Passed (unknown criteria)"


async def run_single_turn_test(ws_url: str, test: dict) -> dict:
    """Run a single-turn test case."""
    session_id = f"test-{test['id']}-{uuid.uuid4().hex[:6]}"
    uri = f"{ws_url}/ws/{session_id}"

    result = {
        "id": test["id"],
        "category": test["category"],
        "language": test["language"],
        "prompt": test["prompt"],
        "passed": False,
        "sql": None,
        "row_count": 0,
        "answer": "",
        "missing_keywords": [],
        "reason": "",
        "latency_ms": 0
    }

    try:
        async with websockets.connect(uri) as ws:
            start = time.time()
            response = await send_and_receive(ws, test["prompt"])
            result["latency_ms"] = int((time.time() - start) * 1000)

            sql = response.get("sql")
            result["sql"] = sql
            result["row_count"] = response.get("row_count", 0)
            result["answer"] = response.get("message", "")

            # Check SQL keywords
            sql_ok, missing = check_sql_contains(sql, test.get("expected_sql_contains", []))
            result["missing_keywords"] = missing

            # Check result criteria
            result_ok, reason = evaluate_result(response, test["expected_result"], sql)

            result["passed"] = sql_ok and result_ok
            result["reason"] = reason
            if missing:
                result["reason"] += f" | Missing SQL keywords: {missing}"

    except Exception as e:
        result["reason"] = f"ERROR: {e}"
        result["passed"] = False

    return result


async def run_multi_turn_test(ws_url: str, test: dict) -> dict:
    """Run a multi-turn test case."""
    session_id = f"test-{test['id']}-{uuid.uuid4().hex[:6]}"
    uri = f"{ws_url}/ws/{session_id}"

    result = {
        "id": test["id"],
        "category": test["category"],
        "language": test["language"],
        "turns": [],
        "passed": False,
        "reason": "",
        "latency_ms": 0
    }

    try:
        async with websockets.connect(uri) as ws:
            start = time.time()
            all_passed = True

            for i, turn in enumerate(test["turns"]):
                response = await send_and_receive(ws, turn["prompt"])
                sql = response.get("sql")

                sql_ok, missing = check_sql_contains(sql, turn.get("expected_sql_contains", []))
                result_ok, reason = evaluate_result(response, turn.get("expected_result", "zero_or_more"), sql)

                turn_passed = sql_ok and result_ok
                all_passed = all_passed and turn_passed

                result["turns"].append({
                    "turn": i + 1,
                    "prompt": turn["prompt"],
                    "sql": sql,
                    "row_count": response.get("row_count", 0),
                    "passed": turn_passed,
                    "missing_keywords": missing,
                    "reason": reason
                })

            result["latency_ms"] = int((time.time() - start) * 1000)
            result["passed"] = all_passed
            result["reason"] = "All turns passed" if all_passed else "One or more turns failed"

    except Exception as e:
        result["reason"] = f"ERROR: {e}"
        result["passed"] = False

    return result


async def run_all_tests(ws_url: str, category_filter: Optional[str] = None) -> dict:
    """Run all test cases and return a full report."""
    with open(TEST_CASES_FILE) as f:
        test_cases = json.load(f)

    if category_filter:
        test_cases = [t for t in test_cases if t["category"] == category_filter]
        print(f"Running {len(test_cases)} tests in category: {category_filter}")
    else:
        print(f"Running {len(test_cases)} test cases...")

    results = []
    passed = 0
    failed = 0

    for test in test_cases:
        print(f"  [{test['id']}] {test['prompt'][:60] if 'prompt' in test else 'multi-turn'}...", end=" ")

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

        # Small delay between tests
        await asyncio.sleep(0.5)

    total = passed + failed
    accuracy = (passed / total * 100) if total > 0 else 0

    # Category breakdown
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"passed": 0, "total": 0}
        categories[cat]["total"] += 1
        if r["passed"]:
            categories[cat]["passed"] += 1

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "ws_url": ws_url,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "accuracy_pct": round(accuracy, 1)
        },
        "by_category": {
            cat: {
                "passed": v["passed"],
                "total": v["total"],
                "accuracy_pct": round(v["passed"] / v["total"] * 100, 1)
            }
            for cat, v in categories.items()
        },
        "results": results
    }

    return report


def print_summary(report: dict):
    s = report["summary"]
    print("\n" + "=" * 50)
    print(f"VALIDATION RESULTS — {report['timestamp'][:10]}")
    print("=" * 50)
    print(f"Total:    {s['total']}")
    print(f"Passed:   {s['passed']}")
    print(f"Failed:   {s['failed']}")
    print(f"Accuracy: {s['accuracy_pct']}%")
    print()
    print("By category:")
    for cat, v in report["by_category"].items():
        bar = "█" * int(v["accuracy_pct"] / 10) + "░" * (10 - int(v["accuracy_pct"] / 10))
        print(f"  {cat:<20} {bar}  {v['passed']}/{v['total']}  ({v['accuracy_pct']}%)")
    print("=" * 50)


async def main(ws_url: str, category: Optional[str], output: Optional[str]):
    report = await run_all_tests(ws_url, category)
    print_summary(report)

    if output:
        with open(output, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nFull report saved to: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run validation tests against the NLP agent")
    parser.add_argument("--url", default=DEFAULT_WS_URL, help="WebSocket base URL")
    parser.add_argument("--category", help="Filter by category (e.g. multi_turn, edge_case)")
    parser.add_argument("--output", help="Save full JSON report to file")
    args = parser.parse_args()

    asyncio.run(main(args.url, args.category, args.output))
