"""
POS Transaction Database — Top-up Script
=========================================
Adds fresh transactions for the last 7 days without deleting existing data.
Run this daily or before testing to ensure "today", "yesterday", "last week"
queries always return results.

Usage:
    python topup.py                    # adds ~500 transactions for last 7 days
    python topup.py --days 3           # last 3 days only
    python topup.py --count 1000       # add 1000 transactions
    python topup.py --today-only       # today only, ~200 transactions

Schedule daily with cron:
    0 8 * * * cd /path/to/db && python topup.py
"""

import os
import random
import string
import uuid
import argparse
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/pos_db"
)

# ── Reuse same data from seed.py ──────────────────────────────

CARD_BRANDS = {
    "VISA":       {"bin_ranges": [(400000, 499999)],                          "pan_length": 16, "weight": 42},
    "MASTERCARD": {"bin_ranges": [(510000, 559999), (222100, 272099)],        "pan_length": 16, "weight": 32},
    "DINACARD":   {"bin_ranges": [(989100, 989199)],                          "pan_length": 16, "weight": 14},
    "AMEX":       {"bin_ranges": [(340000, 349999), (370000, 379999)],        "pan_length": 15, "weight": 7},
    "UNIONPAY":   {"bin_ranges": [(620000, 629999)],                          "pan_length": 16, "weight": 5},
}

STATUS_DIST = [
    ("APPROVED", "00", 83),
    ("DECLINED", "51",  5),
    ("DECLINED", "05",  3),
    ("DECLINED", "14",  2),
    ("DECLINED", "61",  1),
    ("DECLINED", "57",  1),
    ("DECLINED", "91",  1),
    ("DECLINED", "41",  1),
    ("DECLINED", "43",  1),
    ("REVERSED", "00",  1),
    ("PENDING",  "00",  1),
]

CARD_TYPES       = [("CONTACTLESS", 48), ("CHIP", 42), ("MAGNETIC", 7), ("MANUAL", 3)]
CARD_CLASSES     = [("DEBIT", 52), ("CREDIT", 33), ("PREPAID", 8), ("CORPORATE", 7)]
TRANSACTION_TYPES = [("PURCHASE", 90), ("REFUND", 5), ("REVERSAL", 3), ("CASH_ADVANCE", 2)]

MERCHANTS = [
    ("M001", "Maxi Supermarket",       "GROCERY",       (250,   8500), "RSD"),
    ("M002", "Lidl Srbija",            "GROCERY",       (180,   6000), "RSD"),
    ("M003", "Mercator",               "GROCERY",       (300,   7500), "RSD"),
    ("M004", "Univerexport",           "GROCERY",       (200,   6500), "RSD"),
    ("M005", "Idea Supermarket",       "GROCERY",       (150,   5000), "RSD"),
    ("M006", "Billa Srbija",           "GROCERY",       (200,   6000), "RSD"),
    ("M007", "Roda Cash & Carry",      "GROCERY",       (500,  15000), "RSD"),
    ("M008", "NIS Petrol",             "FUEL",          (1500,  8500), "RSD"),
    ("M009", "OMV Srbija",             "FUEL",          (1500,  8000), "RSD"),
    ("M010", "Mol Srbija",             "FUEL",          (1500,  7500), "RSD"),
    ("M011", "Lukoil Srbija",          "FUEL",          (1500,  8000), "RSD"),
    ("M012", "Apoteka Beograd",        "PHARMACY",      (300,   4000), "RSD"),
    ("M013", "DM Drogerije",           "PHARMACY",      (400,   5000), "RSD"),
    ("M015", "McDonald's Beograd",     "RESTAURANT",    (400,   2500), "RSD"),
    ("M016", "Pizza Hut Srbija",       "RESTAURANT",    (700,   3500), "RSD"),
    ("M020", "Gigatron",               "ELECTRONICS",   (2000, 90000), "RSD"),
    ("M021", "Tehnomanija",            "ELECTRONICS",   (1500, 70000), "RSD"),
    ("M023", "H&M Beograd",            "CLOTHING",      (1200, 14000), "RSD"),
    ("M024", "Zara Srbija",            "CLOTHING",      (1500, 18000), "RSD"),
    ("M025", "Sport Vision",           "CLOTHING",      (2000, 25000), "RSD"),
    ("M028", "Telekom Srbija",         "UTILITIES",     (800,   6000), "RSD"),
    ("M030", "EPS Elektroprivreda",    "UTILITIES",     (1500, 18000), "RSD"),
    ("M031", "Cinema City Beograd",    "ENTERTAINMENT", (700,   2500), "RSD"),
    ("M033", "Ikea Srbija",            "FURNITURE",     (1500, 90000), "RSD"),
    ("M034", "Bauhaus Srbija",         "HARDWARE",      (400,  45000), "RSD"),
    ("M036", "Hotel Metropol Palace",  "HOTEL",         (80,     400), "EUR"),
    ("M037", "Hilton Belgrade",        "HOTEL",         (100,    600), "EUR"),
    ("M039", "Airport Duty Free BEG", "RETAIL",         (15,     250), "EUR"),
]

def build_terminals():
    terminals = []
    for m in MERCHANTS:
        for i in range(1, random.randint(2, 8) + 1):
            terminals.append((f"T{m[0][1:]}{i:02d}", m[0]))
    return terminals

TERMINALS = build_terminals()
TERMINAL_BY_MERCHANT = {}
for tid, mid in TERMINALS:
    TERMINAL_BY_MERCHANT.setdefault(mid, []).append(tid)

def weighted_choice(options):
    total = sum(w for _, w in options)
    r = random.uniform(0, total)
    cum = 0
    for val, w in options:
        cum += w
        if r <= cum:
            return val
    return options[-1][0]

def pick_brand():
    return weighted_choice([(b, d["weight"]) for b, d in CARD_BRANDS.items()])

def generate_pan(brand):
    data = CARD_BRANDS[brand]
    bin_range = random.choice(data["bin_ranges"])
    bin_number = str(random.randint(bin_range[0], bin_range[1]))
    pan_len = data["pan_length"]
    last4 = str(random.randint(1000, 9999))
    stars = "*" * (pan_len - len(bin_number) - len(last4))
    return f"{bin_number}{stars}{last4}"

def generate_approval_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def pick_status_and_code():
    total = sum(w for _, _, w in STATUS_DIST)
    r = random.uniform(0, total)
    cum = 0
    for status, code, w in STATUS_DIST:
        cum += w
        if r <= cum:
            return status, code
    return "APPROVED", "00"

def random_timestamp_in_range(start: datetime, end: datetime) -> datetime:
    delta = int((end - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, delta))

def generate_transaction(start: datetime, end: datetime):
    merchant     = random.choice(MERCHANTS)
    m_id         = merchant[0]
    terminal_id  = random.choice(TERMINAL_BY_MERCHANT.get(m_id, [f"T{m_id[1:]}01"]))
    brand        = pick_brand()
    status, code = pick_status_and_code()
    tx_type      = weighted_choice(TRANSACTION_TYPES)
    amount       = round(random.uniform(*merchant[3]), 2)

    if tx_type in ("REFUND", "REVERSAL"):
        amount = -abs(amount)

    return (
        str(uuid.uuid4()),
        random_timestamp_in_range(start, end),
        amount,
        merchant[4],
        status,
        code,
        generate_approval_code() if status in ("APPROVED", "PENDING") else None,
        generate_pan(brand),
        brand,
        weighted_choice(CARD_TYPES),
        weighted_choice(CARD_CLASSES),
        terminal_id,
        m_id,
        merchant[1],
        merchant[2],
        tx_type,
    )

INSERT_SQL = """
    INSERT INTO transactions (
        transaction_id, transaction_date, amount, currency,
        status, response_code, approval_code,
        pan_masked, card_brand, card_type, card_class,
        terminal_id, merchant_id, merchant_name, merchant_category,
        transaction_type
    ) VALUES %s
"""

def topup(days: int = 7, count: int = 500, today_only: bool = False):
    now   = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if today_only:
        date_start = today_start
        date_end   = now
        label      = "today"
    else:
        date_start = today_start - timedelta(days=days - 1)
        date_end   = now
        label      = f"last {days} days"

    print(f"Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    # Check existing count
    cur.execute("SELECT COUNT(*) FROM transactions WHERE transaction_date >= %s", (date_start,))
    existing = cur.fetchone()[0]
    print(f"Existing transactions in {label}: {existing:,}")

    print(f"Adding {count:,} fresh transactions for {label} ({date_start.date()} → {date_end.date()})...")

    batch = []
    for i in range(count):
        batch.append(generate_transaction(date_start, date_end))

    execute_values(cur, INSERT_SQL, batch)
    conn.commit()

    # Verify
    cur.execute("SELECT COUNT(*) FROM transactions WHERE transaction_date >= %s", (date_start,))
    new_total = cur.fetchone()[0]

    cur.execute("""
        SELECT DATE(transaction_date) as day, COUNT(*) as cnt
        FROM transactions
        WHERE transaction_date >= %s
        GROUP BY day ORDER BY day DESC
    """, (date_start,))

    print(f"\nTransactions per day after top-up:")
    for row in cur.fetchall():
        print(f"  {row[0]}  →  {row[1]:>5,}")

    print(f"\nTotal in {label}: {new_total:,} (+{count:,} added)")

    cur.close()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Top up transactions database with fresh data")
    parser.add_argument("--days",       type=int,  default=7,    help="Number of days to cover (default: 7)")
    parser.add_argument("--count",      type=int,  default=500,  help="Number of transactions to add (default: 500)")
    parser.add_argument("--today-only", action="store_true",     help="Add transactions for today only")
    args = parser.parse_args()

    topup(days=args.days, count=args.count, today_only=args.today_only)
