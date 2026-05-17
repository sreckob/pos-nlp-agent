"""
rag_eval.py — RAG retrieval quality evaluation
===============================================
Measures Precision@K for the dispute_policies pgvector store.
For each labeled dispute scenario, checks whether the retrieved clauses
are actually relevant (hand-labeled ground truth + LLM judge).

Usage:
    cd backend/files          # must run from here to import rag_store
    python ../../validation/rag_eval.py
    python ../../validation/rag_eval.py --judge   # adds LLM judge scoring
    python ../../validation/rag_eval.py --k 5

Requires:
    - ingest_policies.py already run (dispute_policies table populated)
    - DATABASE_URL in .env
    - ANTHROPIC_API_KEY in .env (only for --judge mode)
"""

import argparse
import json
import os
import sys
from datetime import datetime

# Must be run from backend/files so rag_store imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from config import settings
from db import init_pool
from rag_store import retrieve_clauses

# ── Labeled test scenarios ────────────────────────────────────
# Each entry: (scenario_description, relevant_clause_ids)
# relevant_clause_ids = the clauses that SHOULD be in top-K results

LABELED_SCENARIOS = [
    (
        "Duplicate charge at Maxi supermarket, same amount 3240 RSD, Visa card ending 4242, two charges within 12 minutes",
        {"VDR-11.1.3", "MC-4853", "DC-6.2.1"},
    ),
    (
        "Cardholder charged twice at NIS Petrol petrol station, Mastercard, 1850 RSD, same day",
        {"VDR-11.1.3", "MC-4853", "MC-4853-R"},
    ),
    (
        "Customer wants to dispute a transaction they did not authorize, card was lost",
        {"VDR-10.4.1", "MC-4837", "PSD2-Art73"},
    ),
    (
        "How long does a cardholder have to file a chargeback dispute after noticing the charge?",
        {"VDR-11.4", "MC-4853-TL", "DC-8.4"},
    ),
    (
        "Payment service provider liability for refunding unauthorized transactions within one business day",
        {"PSD2-Art73", "PSD2-Art74"},
    ),
    (
        "Remedy and reversal procedure for confirmed duplicate transaction at POS terminal",
        {"VDR-11.2", "MC-4853-R", "DC-7.1"},
    ),
    (
        "Dinacard duplicate transaction same terminal same PAN within 60 minutes",
        {"DC-6.2.1", "VDR-11.1.3"},
    ),
    (
        "Complaint response timeline and out-of-court redress for payment disputes",
        {"PSD2-Art80"},
    ),
]


# ── Metrics ───────────────────────────────────────────────────

def precision_at_k(retrieved_ids: list, relevant_ids: set, k: int) -> float:
    top_k = retrieved_ids[:k]
    hits = sum(1 for c in top_k if c in relevant_ids)
    return hits / k if k > 0 else 0.0


def recall_at_k(retrieved_ids: list, relevant_ids: set, k: int) -> float:
    top_k = retrieved_ids[:k]
    hits = sum(1 for c in top_k if c in relevant_ids)
    return hits / len(relevant_ids) if relevant_ids else 0.0


# ── LLM judge ─────────────────────────────────────────────────

JUDGE_PROMPT = """You are evaluating whether a regulation clause is relevant to a payment dispute scenario.

Dispute scenario: {scenario}

Retrieved clause [{clause_id}] from {source}:
{content}

Is this regulation clause relevant to the dispute scenario above?
A clause is relevant if it directly applies to the type of dispute, the parties involved,
the time limits, or the remedy described in the scenario.

Respond with JSON only:
{{
  "relevant": true | false,
  "confidence": 0.0-1.0,
  "reason": "one sentence"
}}"""


def judge_relevance(scenario: str, clause: dict) -> dict:
    """Use Claude to judge if a retrieved clause is relevant to the scenario."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = JUDGE_PROMPT.format(
            scenario=scenario,
            clause_id=clause["clause_id"],
            source=clause["source"],
            content=clause["content"],
        )
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=200,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        import re
        raw = response.content[0].text.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"relevant": None, "confidence": 0.0, "reason": f"judge error: {e}"}
    return {"relevant": None, "confidence": 0.0, "reason": "no JSON returned"}


# ── Main evaluation ───────────────────────────────────────────

def run_rag_eval(k: int = 3, use_judge: bool = False) -> dict:
    init_pool(settings.DATABASE_URL)

    print(f"RAG Retrieval Evaluation — Precision@{k} / Recall@{k}")
    print(f"{'='*60}")
    print(f"Scenarios: {len(LABELED_SCENARIOS)}  |  Judge: {'on' if use_judge else 'off'}")
    print()

    all_p_at_k = []
    all_r_at_k = []
    details    = []

    for scenario, relevant_ids in LABELED_SCENARIOS:
        clauses = retrieve_clauses(scenario, top_k=k)
        retrieved_ids = [c["clause_id"] for c in clauses]

        p = precision_at_k(retrieved_ids, relevant_ids, k)
        r = recall_at_k(retrieved_ids, relevant_ids, k)
        all_p_at_k.append(p)
        all_r_at_k.append(r)

        hit_markers = []
        judge_scores = []
        for c in clauses:
            in_relevant = c["clause_id"] in relevant_ids
            marker = "✓" if in_relevant else "·"

            judge_result = None
            if use_judge:
                judge_result = judge_relevance(scenario, c)
                j_mark = "J✓" if judge_result.get("relevant") else "J✗"
                marker = f"{marker}{j_mark}"
                if judge_result.get("relevant") is not None:
                    judge_scores.append(1 if judge_result["relevant"] else 0)

            hit_markers.append(f"{marker}[{c['clause_id']}]({c['similarity']:.2f})")

        print(f"  Scenario: {scenario[:65]}...")
        print(f"  Retrieved: {' '.join(hit_markers)}")
        print(f"  Relevant:  {', '.join(sorted(relevant_ids))}")
        print(f"  P@{k}={p:.2f}  R@{k}={r:.2f}")
        if use_judge and judge_scores:
            print(f"  Judge relevance: {sum(judge_scores)}/{len(judge_scores)} retrieved marked relevant")
        print()

        details.append({
            "scenario":      scenario,
            "relevant_ids":  list(relevant_ids),
            "retrieved":     [{"clause_id": c["clause_id"], "similarity": c["similarity"]} for c in clauses],
            "precision_at_k": p,
            "recall_at_k":    r,
        })

    mean_p = sum(all_p_at_k) / len(all_p_at_k)
    mean_r = sum(all_r_at_k) / len(all_r_at_k)
    f1     = 2 * mean_p * mean_r / (mean_p + mean_r) if (mean_p + mean_r) > 0 else 0.0

    print("=" * 60)
    print(f"Mean Precision@{k}: {mean_p:.3f}")
    print(f"Mean Recall@{k}:    {mean_r:.3f}")
    print(f"Mean F1@{k}:        {f1:.3f}")
    print()
    if mean_p >= 0.7:
        print("✓ Retrieval quality: GOOD (P@K >= 0.7)")
    elif mean_p >= 0.5:
        print("~ Retrieval quality: ACCEPTABLE (P@K >= 0.5)")
    else:
        print("✗ Retrieval quality: NEEDS IMPROVEMENT (P@K < 0.5)")

    return {
        "timestamp":    datetime.utcnow().isoformat(),
        "k":            k,
        "judge_enabled": use_judge,
        "mean_precision_at_k": round(mean_p, 3),
        "mean_recall_at_k":    round(mean_r, 3),
        "mean_f1_at_k":        round(f1, 3),
        "details":      details,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k",      type=int, default=3)
    parser.add_argument("--judge",  action="store_true", help="Use Claude to judge relevance")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = run_rag_eval(k=args.k, use_judge=args.judge)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {args.output}")
