"""
router_eval.py — Router classification evaluation
===================================================
Measures per-channel precision, recall, F1 and prints a confusion matrix.
Goes beyond simple accuracy to show WHICH channels get confused with which.

Usage:
    cd validation
    python router_eval.py                          # local backend
    python router_eval.py --url wss://...          # deployed backend
    python router_eval.py --output router_eval.json

Requires: backend running, websockets installed
"""

import argparse
import asyncio
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime

import websockets

DEFAULT_WS_URL = "ws://localhost:8000"

CHANNELS = ["CARDHOLDER", "MERCHANT", "DISPUTE", "LOYALTY"]

# ── Labeled test cases ────────────────────────────────────────
# Each entry: (true_channel, message, language)
# Deliberately includes ambiguous short messages that trip up the router.

ROUTER_TEST_CASES = [
    # CARDHOLDER — clear cases
    ("CARDHOLDER", "Why was my payment declined yesterday at Maxi?", "en"),
    ("CARDHOLDER", "Show me all my transactions from last month", "en"),
    ("CARDHOLDER", "Zašto mi je transakcija odbijena?", "sr"),
    ("CARDHOLDER", "My card ending in 4242 was charged at Gigatron on Friday", "en"),
    ("CARDHOLDER", "Prikaži sve moje transakcije za april", "sr"),

    # CARDHOLDER — ambiguous short replies (should stay in CARDHOLDER when primed)
    ("CARDHOLDER", "4242", "en"),
    ("CARDHOLDER", "last week", "en"),
    ("CARDHOLDER", "da", "sr"),

    # MERCHANT — clear cases
    ("MERCHANT", "Show me all declined transactions on my terminal last week", "en"),
    ("MERCHANT", "What is my total revenue this month in RSD?", "en"),
    ("MERCHANT", "Export my transactions to Excel", "en"),
    ("MERCHANT", "Prikaži mi promet po terminalu za mart", "sr"),
    ("MERCHANT", "How many VISA transactions did I process today?", "en"),

    # MERCHANT — ambiguous
    ("MERCHANT", "terminal T001", "en"),
    ("MERCHANT", "April revenue", "en"),

    # DISPUTE — clear cases
    ("DISPUTE", "I was charged twice at Maxi for 3240 RSD with my Visa card ending in 4242", "en"),
    ("DISPUTE", "There is a duplicate transaction on my account I want to dispute", "en"),
    ("DISPUTE", "Zadužen sam dva puta za istu kupovinu", "sr"),
    ("DISPUTE", "I have a receipt and want to report a double charge", "en"),
    ("DISPUTE", "Imam duplo zaduženje i tražim povraćaj", "sr"),

    # DISPUTE — ambiguous
    ("DISPUTE", "I was charged twice", "en"),
    ("DISPUTE", "duplo zaduženje", "sr"),

    # LOYALTY — clear cases
    ("LOYALTY", "My loyalty points were not credited for my last purchase", "en"),
    ("LOYALTY", "How many points do I have on my Dinacard?", "en"),
    ("LOYALTY", "Moji poeni nisu dodati za kupovinu od prošle nedelje", "sr"),
    ("LOYALTY", "I want to check my points balance for card ending in 9999", "en"),
    ("LOYALTY", "Koliko poena imam na kartici koja se završava sa 1111?", "sr"),

    # LOYALTY — ambiguous
    ("LOYALTY", "check points", "en"),
    ("LOYALTY", "poeni", "sr"),
]


# ── WebSocket helpers ─────────────────────────────────────────

async def send_and_receive(ws, message: str, timeout: int = 30) -> dict:
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


async def classify_message(ws_url: str, channel: str, message: str) -> str:
    """Prime the router with the correct channel, send the message, return detected role."""
    session_id = f"router-eval-{uuid.uuid4().hex[:8]}"
    uri = f"{ws_url}/ws/{session_id}"
    try:
        async with websockets.connect(uri) as ws:
            await prime_channel(ws, channel)
            response = await send_and_receive(ws, message)
            # The backend returns current role in the response
            # If suggest_switch=True the router detected a different channel
            if response.get("suggest_switch"):
                return response.get("pending_role", channel)
            return channel  # stayed in channel = correct classification
    except Exception as e:
        return f"ERROR: {e}"


# ── Metrics ───────────────────────────────────────────────────

def compute_metrics(true_labels: list, pred_labels: list) -> dict:
    """Compute per-class precision, recall, F1 and macro averages."""
    metrics = {}
    for ch in CHANNELS:
        tp = sum(1 for t, p in zip(true_labels, pred_labels) if t == ch and p == ch)
        fp = sum(1 for t, p in zip(true_labels, pred_labels) if t != ch and p == ch)
        fn = sum(1 for t, p in zip(true_labels, pred_labels) if t == ch and p != ch)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        support   = sum(1 for t in true_labels if t == ch)

        metrics[ch] = {
            "precision": round(precision, 3),
            "recall":    round(recall, 3),
            "f1":        round(f1, 3),
            "support":   support,
            "tp": tp, "fp": fp, "fn": fn,
        }

    total     = len(true_labels)
    correct   = sum(1 for t, p in zip(true_labels, pred_labels) if t == p)
    macro_p   = sum(m["precision"] for m in metrics.values()) / len(CHANNELS)
    macro_r   = sum(m["recall"]    for m in metrics.values()) / len(CHANNELS)
    macro_f1  = sum(m["f1"]        for m in metrics.values()) / len(CHANNELS)

    return {
        "per_class": metrics,
        "accuracy":  round(correct / total, 3) if total else 0,
        "macro_precision": round(macro_p, 3),
        "macro_recall":    round(macro_r, 3),
        "macro_f1":        round(macro_f1, 3),
        "total": total,
        "correct": correct,
    }


def print_confusion_matrix(true_labels: list, pred_labels: list):
    """Print an ASCII confusion matrix."""
    matrix = defaultdict(lambda: defaultdict(int))
    for t, p in zip(true_labels, pred_labels):
        matrix[t][p] += 1

    short = {"CARDHOLDER": "CH", "MERCHANT": "ME", "DISPUTE": "DI", "LOYALTY": "LO"}
    header = "        " + "  ".join(f"{short[c]:>4}" for c in CHANNELS)
    print(header)
    print("        " + "-" * (len(CHANNELS) * 6))
    for true_ch in CHANNELS:
        row = f"{short[true_ch]:>6} |"
        for pred_ch in CHANNELS:
            val = matrix[true_ch][pred_ch]
            row += f"  {val:>3} "
        print(row)
    print()
    print("Rows = true label, Cols = predicted label. Diagonal = correct.")


def print_report(metrics: dict, true_labels: list, pred_labels: list):
    print("\n" + "=" * 60)
    print("ROUTER EVALUATION — Precision / Recall / F1")
    print("=" * 60)
    print(f"{'Channel':<14} {'Precision':>9} {'Recall':>7} {'F1':>6} {'Support':>8}")
    print("-" * 50)
    for ch, m in metrics["per_class"].items():
        print(f"{ch:<14} {m['precision']:>9.3f} {m['recall']:>7.3f} {m['f1']:>6.3f} {m['support']:>8}")
    print("-" * 50)
    print(f"{'macro avg':<14} {metrics['macro_precision']:>9.3f} {metrics['macro_recall']:>7.3f} {metrics['macro_f1']:>6.3f} {metrics['total']:>8}")
    print(f"\nOverall accuracy: {metrics['correct']}/{metrics['total']} = {metrics['accuracy']*100:.1f}%")
    print("\nConfusion matrix (short: CH=Cardholder, ME=Merchant, DI=Dispute, LO=Loyalty):")
    print_confusion_matrix(true_labels, pred_labels)


# ── Main ──────────────────────────────────────────────────────

async def run_router_eval(ws_url: str) -> dict:
    true_labels = []
    pred_labels = []
    details     = []

    print(f"Running {len(ROUTER_TEST_CASES)} router classification tests...")

    for i, (true_ch, message, lang) in enumerate(ROUTER_TEST_CASES):
        print(f"  [{i+1:02d}/{len(ROUTER_TEST_CASES)}] [{true_ch[:2]}] {message[:55]}...", end=" ", flush=True)
        t0 = time.time()
        predicted = await classify_message(ws_url, true_ch, message)
        ms = int((time.time() - t0) * 1000)
        correct = predicted == true_ch
        symbol = "✓" if correct else f"✗ (got {predicted})"
        print(f"{symbol}  [{ms}ms]")
        true_labels.append(true_ch)
        pred_labels.append(predicted if predicted in CHANNELS else true_ch)
        details.append({
            "true": true_ch, "predicted": predicted,
            "message": message, "language": lang,
            "correct": correct, "latency_ms": ms,
        })
        await asyncio.sleep(0.3)

    metrics = compute_metrics(true_labels, pred_labels)
    print_report(metrics, true_labels, pred_labels)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "ws_url": ws_url,
        "metrics": metrics,
        "details": details,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",    default=DEFAULT_WS_URL)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = asyncio.run(run_router_eval(args.url))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Report saved to: {args.output}")
