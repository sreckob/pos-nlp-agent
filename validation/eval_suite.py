"""
eval_suite.py — Master evaluation runner
=========================================
Runs all evaluation modules and produces a unified report.

Usage:
    cd validation
    python eval_suite.py                        # all suites, local backend
    python eval_suite.py --url ws://...         # deployed backend
    python eval_suite.py --skip router          # skip specific suite
    python eval_suite.py --only state,policy    # run only these suites
    python eval_suite.py --output full_eval.json

Available suites:
    router   — per-channel precision/recall/F1 + confusion matrix
    state    — DB before/after state validation for write ops
    policy   — read-only guard, PAN isolation, ops auth
    rag      — RAG Precision@K retrieval quality (run from backend/files)
    judge    — LLM-as-judge for audit summary quality
    iron     — Iron User multi-turn conversation scenarios

Note: 'rag' suite must be run from backend/files directory since it
imports rag_store directly. If running from validation/, it is skipped
automatically with a note.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime

DEFAULT_WS_URL   = "ws://localhost:8000"
DEFAULT_HTTP_URL = "http://localhost:8000"

ALL_SUITES = ["router", "state", "policy", "rag", "judge", "iron"]


def print_header(title: str):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


async def run_suite(suite: str, ws_url: str, http_url: str) -> dict:
    t0 = time.time()

    if suite == "router":
        print_header("ROUTER EVALUATION — Precision / Recall / F1")
        from router_eval import run_router_eval
        result = await run_router_eval(ws_url)
        result["suite"] = "router"

    elif suite == "state":
        print_header("STATE VALIDATOR — DB Before/After Write Ops")
        from state_validator import run_all
        result = run_all(http_url)
        result["suite"] = "state"

    elif suite == "policy":
        print_header("POLICY CHECKER — Read-only / PAN Isolation / Ops Auth")
        from policy_checker import run_all as run_policy
        result = await run_policy(ws_url, http_url)
        result["suite"] = "policy"

    elif suite == "rag":
        # rag_eval must be run from backend/files
        backend_path = os.path.join(os.path.dirname(__file__), "..", "backend", "files")
        if not os.path.exists(os.path.join(backend_path, "rag_store.py")):
            print_header("RAG EVALUATION — SKIPPED")
            print("  Run 'python ../../validation/rag_eval.py' from backend/files instead.")
            return {"suite": "rag", "skipped": True, "reason": "must run from backend/files"}
        sys.path.insert(0, os.path.abspath(backend_path))
        os.chdir(backend_path)
        print_header("RAG EVALUATION — Precision@K Retrieval Quality")
        from rag_eval import run_rag_eval
        result = run_rag_eval(k=3, use_judge=False)
        result["suite"] = "rag"

    elif suite == "judge":
        print_header("LLM JUDGE — Approver Audit Quality")
        from llm_judge import run_judge_eval
        result = run_judge_eval(http_url)
        result["suite"] = "judge"

    elif suite == "iron":
        print_header("IRON USER — Multi-turn Conversation Scenarios")
        from iron_user import run_iron_user
        result = await run_iron_user(ws_url)
        result["suite"] = "iron"

    else:
        return {"suite": suite, "error": f"unknown suite: {suite}"}

    result["duration_s"] = round(time.time() - t0, 1)
    return result


def summarize(results: list) -> dict:
    summary = {}
    for r in results:
        suite = r.get("suite", "?")
        if r.get("skipped"):
            summary[suite] = "SKIPPED"
            continue
        if r.get("error"):
            summary[suite] = f"ERROR: {r['error']}"
            continue

        if suite == "router":
            m = r.get("metrics", {})
            summary[suite] = (
                f"accuracy={m.get('accuracy',0)*100:.0f}%  "
                f"macro_F1={m.get('macro_f1',0):.3f}"
            )
        elif suite == "state":
            s = r.get("summary", {})
            summary[suite] = f"{s.get('passed',0)} passed / {s.get('failed',0)} failed / {s.get('skipped',0)} skipped"
        elif suite == "policy":
            s = r.get("summary", {})
            summary[suite] = f"{s.get('total_passed',0)}/{s.get('total_checks',0)} checks passed"
        elif suite == "rag":
            summary[suite] = (
                f"P@3={r.get('mean_precision_at_k',0):.3f}  "
                f"R@3={r.get('mean_recall_at_k',0):.3f}  "
                f"F1@3={r.get('mean_f1_at_k',0):.3f}"
            )
        elif suite == "judge":
            ms = r.get("mean_scores", {})
            ag = r.get("agreement", {})
            summary[suite] = (
                f"regulation={ms.get('regulation_applicability','?')}/5  "
                f"factual={ms.get('factual_consistency','?')}/5  "
                f"decision={ms.get('decision_correctness','?')}/5  "
                f"agreement={ag.get('agreement_rate',0)*100:.0f}%"
            )
        elif suite == "iron":
            s = r.get("summary", {})
            summary[suite] = (
                f"scenarios={s.get('scenarios_passed',0)}/{s.get('scenarios_total',0)}  "
                f"turns={s.get('turns_passed',0)}/{s.get('turns_total',0)}"
            )

    return summary


async def main(ws_url: str, http_url: str, suites: list, output: str):
    print(f"\nPOS NLP Agent — Full Evaluation Suite")
    print(f"Backend:  {ws_url}")
    print(f"Suites:   {', '.join(suites)}")
    print(f"Started:  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    all_results = []
    for suite in suites:
        try:
            result = await run_suite(suite, ws_url, http_url)
        except Exception as e:
            print(f"\nERROR in suite '{suite}': {e}")
            result = {"suite": suite, "error": str(e)}
        all_results.append(result)

    # Final summary
    summary = summarize(all_results)
    print(f"\n{'='*65}")
    print("EVALUATION SUMMARY")
    print(f"{'='*65}")
    for suite, line in summary.items():
        print(f"  {suite:<10} {line}")
    print(f"{'='*65}\n")

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "ws_url":    ws_url,
        "http_url":  http_url,
        "suites_run": suites,
        "summary":   summary,
        "results":   all_results,
    }

    if output:
        with open(output, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"Full report saved to: {output}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run full evaluation suite")
    parser.add_argument("--url",    default=DEFAULT_WS_URL,
                        help="WebSocket URL (default: ws://localhost:8000)")
    parser.add_argument("--http",   default=DEFAULT_HTTP_URL,
                        help="HTTP base URL for REST calls (default: http://localhost:8000)")
    parser.add_argument("--only",   default=None,
                        help="Comma-separated list of suites to run (e.g. router,policy)")
    parser.add_argument("--skip",   default=None,
                        help="Comma-separated list of suites to skip")
    parser.add_argument("--output", default=None,
                        help="Save full JSON report to file")
    args = parser.parse_args()

    suites = ALL_SUITES.copy()
    if args.only:
        suites = [s.strip() for s in args.only.split(",") if s.strip() in ALL_SUITES]
    if args.skip:
        skip = {s.strip() for s in args.skip.split(",")}
        suites = [s for s in suites if s not in skip]

    asyncio.run(main(args.url, args.http, suites, args.output))
