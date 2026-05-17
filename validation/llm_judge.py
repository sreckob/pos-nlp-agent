"""
llm_judge.py — LLM-as-judge for approver agent audit quality
=============================================================
Uses Claude to grade the approver agent's decisions on three criteria
(per the lecture: one criterion per judge call to avoid halo effect):
  1. Regulation applicability — is the cited clause correct?
  2. Factual consistency     — is the audit_summary consistent with DB data?
  3. Decision correctness    — is APPROVE/REJECT the right call?

Also computes a simple agreement rate between deterministic checks
and the LLM judge as a proxy for Cohen's κ.

Usage:
    cd validation
    python llm_judge.py                        # local backend
    python llm_judge.py --url http://localhost:8000
    python llm_judge.py --output judge_results.json

Requires: backend running, ANTHROPIC_API_KEY set
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime

import requests
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "files", ".env")
load_dotenv(ENV_PATH)

import anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
OPS_API_KEY       = os.getenv("OPS_API_KEY", "")
DEFAULT_URL       = "http://localhost:8000"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Judge prompts (one criterion each) ───────────────────────

JUDGE_REGULATION = """You are evaluating an approver agent's use of regulation citations.

Dispute scenario:
{scenario}

Approver audit summary: "{audit_summary}"
Approver decision: {decision}

Criterion: REGULATION APPLICABILITY
Does the audit summary cite a specific regulation clause (e.g. "per Visa VDR-11.1.3",
"per Mastercard MC-4853", "per PSD2 Art.73")? If a clause is cited, is it applicable
to this type of dispute (duplicate transaction / unauthorized charge)?
If no regulation is cited, score 1.

Score definitions:
  5 — Cites a specific, correct and applicable regulation clause
  4 — Cites a regulation but clause number is imprecise or partially applicable
  3 — References a regulation body without a specific clause
  2 — Cites a clause but it is not applicable to this dispute type
  1 — No regulation cited

Respond with JSON only:
{{"score": 1-5, "reasoning": "one sentence"}}"""


JUDGE_FACTUAL = """You are evaluating an approver agent's factual accuracy.

Transaction evidence:
{evidence}

Approver audit summary: "{audit_summary}"
Approver decision: {decision}

Criterion: FACTUAL CONSISTENCY
Are all specific claims in the audit_summary (merchant name, amount, currency, time gap,
PAN suffix) consistent with the transaction evidence provided? Any invented or wrong detail
lowers the score.

Score definitions:
  5 — All factual details in the summary are correct and present in the evidence
  4 — Minor omission but no incorrect facts
  3 — One factual detail is wrong or unverifiable from evidence
  2 — Multiple factual errors
  1 — Summary contradicts the evidence

Respond with JSON only:
{{"score": 1-5, "reasoning": "one sentence"}}"""


JUDGE_DECISION = """You are evaluating an approver agent's APPROVE/REJECT decision.

Transaction evidence:
{evidence}

Approver decision: {decision}
Approver blocking_reason: {blocking_reason}
Approver confidence: {confidence}

Criterion: DECISION CORRECTNESS
Given the evidence, is the APPROVE or REJECT decision correct?
A valid duplicate requires: same PAN, same merchant, same amount, same day,
different approval codes, less than 30 minutes apart, both APPROVED status.

Score definitions:
  5 — Decision is clearly correct given the evidence
  4 — Decision is correct but the stated reason is incomplete
  3 — Decision is debatable — evidence is ambiguous
  2 — Decision appears incorrect given the evidence
  1 — Decision is clearly wrong

Respond with JSON only:
{{"score": 1-5, "reasoning": "one sentence"}}"""


# ── Judge helper ──────────────────────────────────────────────

def call_judge(prompt: str) -> dict:
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"score": None, "reasoning": f"judge error: {e}"}
    return {"score": None, "reasoning": "no JSON returned"}


# ── Ops helpers ───────────────────────────────────────────────

def get_pending_item(base_url: str, approval_id: str) -> dict:
    r = requests.get(
        f"{base_url}/ops/pending/{approval_id}",
        headers={"X-Ops-Key": OPS_API_KEY},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def submit_dispute(base_url: str, original_id: str, duplicate_id: str, pan: str) -> str:
    session_id = f"judge-{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{base_url}/dispute/submit", json={
        "session_id": session_id,
        "original_tx_id": original_id,
        "duplicate_tx_id": duplicate_id,
        "pan_masked": pan,
    }, timeout=15)
    r.raise_for_status()
    return r.json().get("approval_id")


# ── Scenario runner ───────────────────────────────────────────

def run_scenario(base_url: str, label: str, original_id: str, duplicate_id: str,
                 pan: str, expect_approve: bool) -> dict:
    print(f"\n  Scenario: {label}")

    # Submit
    approval_id = submit_dispute(base_url, original_id, duplicate_id, pan)
    if not approval_id:
        return {"label": label, "error": "no approval_id returned"}
    print(f"    Submitted: {approval_id}")

    # Get approver recommendation (triggers approver agent)
    time.sleep(2)
    item = get_pending_item(base_url, approval_id)
    rec = item.get("agent_recommendation", {})
    decision     = rec.get("decision", "?")
    confidence   = rec.get("confidence", 0.0)
    audit_summary = rec.get("audit_summary", "")
    blocking_reason = rec.get("blocking_reason", "null")
    print(f"    Agent: {decision} (conf={confidence}) — {audit_summary}")

    # Build evidence string for judge
    payload = item.get("payload", {})
    evidence = json.dumps(payload, indent=2, default=str)
    scenario_desc = f"Dispute: {label}. PAN: {pan}."

    # Deterministic check: does decision match expectation?
    det_correct = (decision == "APPROVE") == expect_approve

    # LLM judge — three criteria
    j_reg  = call_judge(JUDGE_REGULATION.format(
        scenario=scenario_desc, audit_summary=audit_summary, decision=decision))
    j_fact = call_judge(JUDGE_FACTUAL.format(
        evidence=evidence[:1500], audit_summary=audit_summary, decision=decision))
    j_dec  = call_judge(JUDGE_DECISION.format(
        evidence=evidence[:1500], decision=decision,
        blocking_reason=blocking_reason, confidence=confidence))

    print(f"    Judge — Regulation: {j_reg.get('score')}/5  Factual: {j_fact.get('score')}/5  Decision: {j_dec.get('score')}/5")
    print(f"    Deterministic correct: {'✓' if det_correct else '✗'}")

    return {
        "label": label,
        "approval_id": approval_id,
        "agent_decision": decision,
        "agent_confidence": confidence,
        "audit_summary": audit_summary,
        "expected_approve": expect_approve,
        "deterministic_correct": det_correct,
        "judge": {
            "regulation_applicability": j_reg,
            "factual_consistency": j_fact,
            "decision_correctness": j_dec,
        },
    }


# ── Fetch demo dispute pairs from DB ──────────────────────────

def fetch_dispute_pairs():
    """Fetch seeded dispute pairs directly from the DB."""
    import psycopg2
    DATABASE_URL = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT t1.transaction_id, t2.transaction_id, t1.pan_masked, t1.merchant_name, t1.amount
        FROM transactions t1
        JOIN transactions t2
          ON t1.pan_masked = t2.pan_masked
         AND t1.merchant_id = t2.merchant_id
         AND t1.amount = t2.amount
         AND t1.transaction_id != t2.transaction_id
         AND t1.status = 'APPROVED'
         AND t2.status = 'APPROVED'
         AND t1.approval_code != t2.approval_code
        WHERE ABS(EXTRACT(EPOCH FROM (t1.transaction_date - t2.transaction_date))) < 1800
        LIMIT 3
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [(str(r[0]), str(r[1]), r[2], f"{r[3]} {r[4]} RSD") for r in rows]


# ── Agreement rate (proxy for Cohen's κ) ─────────────────────

def compute_agreement(results: list) -> dict:
    """Compare deterministic decision vs judge decision_correctness score."""
    agreed = 0
    total  = 0
    for r in results:
        if "error" in r:
            continue
        det = r["deterministic_correct"]
        judge_score = r["judge"]["decision_correctness"].get("score")
        if judge_score is None:
            continue
        judge_correct = judge_score >= 4  # score 4-5 = judge agrees it's correct
        if det == judge_correct:
            agreed += 1
        total += 1
    return {
        "agreed": agreed,
        "total": total,
        "agreement_rate": round(agreed / total, 3) if total else 0,
    }


# ── Main ──────────────────────────────────────────────────────

def run_judge_eval(base_url: str) -> dict:
    print(f"LLM Judge Evaluation — {base_url}")
    print("=" * 60)

    print("Fetching seeded dispute pairs from DB...")
    try:
        pairs = fetch_dispute_pairs()
    except Exception as e:
        print(f"ERROR fetching pairs: {e}")
        print("Run demo_seed.py first to create dispute pairs.")
        sys.exit(1)

    if not pairs:
        print("No dispute pairs found. Run demo_seed.py first.")
        sys.exit(1)

    print(f"Found {len(pairs)} dispute pairs to evaluate.\n")

    results = []
    for orig_id, dup_id, pan, label in pairs:
        r = run_scenario(base_url, label, orig_id, dup_id, pan, expect_approve=True)
        results.append(r)
        time.sleep(1)

    agreement = compute_agreement(results)

    # Summary scores
    reg_scores  = [r["judge"]["regulation_applicability"].get("score") for r in results if "judge" in r and r["judge"]["regulation_applicability"].get("score")]
    fact_scores = [r["judge"]["factual_consistency"].get("score")      for r in results if "judge" in r and r["judge"]["factual_consistency"].get("score")]
    dec_scores  = [r["judge"]["decision_correctness"].get("score")     for r in results if "judge" in r and r["judge"]["decision_correctness"].get("score")]

    print(f"\n{'='*60}")
    print("LLM JUDGE SUMMARY")
    print(f"{'='*60}")
    if reg_scores:
        print(f"Regulation applicability: {sum(reg_scores)/len(reg_scores):.2f}/5.0")
    if fact_scores:
        print(f"Factual consistency:      {sum(fact_scores)/len(fact_scores):.2f}/5.0")
    if dec_scores:
        print(f"Decision correctness:     {sum(dec_scores)/len(dec_scores):.2f}/5.0")
    print(f"Agreement rate (det vs judge): {agreement['agreed']}/{agreement['total']} = {agreement['agreement_rate']*100:.0f}%")
    if agreement["agreement_rate"] >= 0.8:
        print("✓ High agreement — judge and deterministic checks align (κ proxy ≥ 0.8)")
    elif agreement["agreement_rate"] >= 0.6:
        print("~ Moderate agreement — review disagreements (κ proxy ≥ 0.6)")
    else:
        print("✗ Low agreement — judge and deterministic checks diverge")

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "base_url": base_url,
        "mean_scores": {
            "regulation_applicability": round(sum(reg_scores)/len(reg_scores), 2) if reg_scores else None,
            "factual_consistency":      round(sum(fact_scores)/len(fact_scores), 2) if fact_scores else None,
            "decision_correctness":     round(sum(dec_scores)/len(dec_scores), 2) if dec_scores else None,
        },
        "agreement": agreement,
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",    default=DEFAULT_URL)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = run_judge_eval(args.url)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport saved to: {args.output}")
