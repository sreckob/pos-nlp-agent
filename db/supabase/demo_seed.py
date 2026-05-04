"""
POS Transaction Database — Demo Seed Script v2.0
==================================================
Inserts specific transactions for reliable demo scenarios.
Always cleans up previous demo data before inserting fresh ones.
Uses dynamic dates relative to TODAY so demos always work.

Scenarios created:
  DISPUTE-01  Double charge at Maxi — Visa card ending 4242
  DISPUTE-02  Double charge at NIS Petrol — Mastercard ending 5555
  DISPUTE-03  Double charge at Gigatron — Dinacard ending 1111
  LOYALTY-01  Recent purchases for Visa card ending 4242 (missing points)
  LOYALTY-02  Recent purchases for Mastercard ending 5555 (missing points)

Usage:
    python demo_seed.py

Safe to run multiple times — cleans up previous demo data first.
"""

import os
import uuid
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/pos_db"
)

# ── Fixed demo PANs ───────────────────────────────────────────
DEMO_PANS = [
    "411111******4242",
    "510000******5555",
    "989100******1111",
    "370000*****9999",
]

DEMO_CARDS = {
    "visa":       {"pan": "411111******4242", "brand": "VISA",       "type": "CONTACTLESS", "class": "DEBIT"},
    "mastercard": {"pan": "510000******5555", "brand": "MASTERCARD", "type": "CHIP",        "class": "CREDIT"},
    "dinacard":   {"pan": "989100******1111", "brand": "DINACARD",   "type": "CHIP",        "class": "DEBIT"},
    "amex":       {"pan": "370000*****9999",  "brand": "AMEX",       "type": "CHIP",        "class": "CORPORATE"},
}

# ── Loyalty accounts ──────────────────────────────────────────
LOYALTY_ACCOUNTS = [
    ("411111******4242", 1250, "SILVER",   67_400.00),
    ("510000******5555",  870, "STANDARD", 38_200.00),
    ("989100******1111", 3400, "GOLD",    215_800.00),
    ("370000*****9999",   520, "STANDARD", 24_100.00),
]

INSERT_SQL = """
    INSERT INTO transactions (
        transaction_id, transaction_date, amount, currency,
        status, response_code, approval_code,
        pan_masked, card_brand, card_type, card_class,
        terminal_id, merchant_id, merchant_name, merchant_category,
        transaction_type,
        loyalty_points_earned, loyalty_points_credited,
        dispute_status, dispute_id, disputed_at, resolved_at
    ) VALUES %s
"""

def make_tx(card_key, merchant_id, merchant_name, category,
            amount, currency, dt, status="APPROVED",
            response_code="00", tx_type="PURCHASE",
            approval_code=None, terminal_suffix="01",
            loyalty_points=0):
    card = DEMO_CARDS[card_key]
    if approval_code is None:
        approval_code = f"D{str(abs(hash(str(dt) + merchant_id)))[:5]}"
    return (
        str(uuid.uuid4()),
        dt,
        amount,
        currency,
        status,
        response_code,
        approval_code,
        card["pan"],
        card["brand"],
        card["type"],
        card["class"],
        f"T{merchant_id[1:]}{terminal_suffix}",
        merchant_id,
        merchant_name,
        category,
        tx_type,
        loyalty_points,
        False,   # loyalty_points_credited — always False for fresh demo data
        None,    # dispute_status
        None,    # dispute_id
        None,    # disputed_at
        None,    # resolved_at
    )

def calc_points(amount, status, tx_type, currency):
    """1 point per 100 RSD for approved RSD purchases."""
    if status == "APPROVED" and tx_type == "PURCHASE" and currency == "RSD":
        return int(amount // 100)
    return 0

def seed(conn):
    cur = conn.cursor()
    now   = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Dynamic date references ───────────────────────────────
    yesterday  = today - timedelta(days=1)
    two_days   = today - timedelta(days=2)
    three_days = today - timedelta(days=3)
    last_week  = today - timedelta(days=7)

    rows = []

    # ── DISPUTE SCENARIO 1 ────────────────────────────────────
    # Visa ****4242 — double charge at Maxi yesterday
    print("Creating dispute scenario 1 — double charge at Maxi...")
    rows.append(make_tx(
        "visa", "M001", "Maxi Supermarket", "GROCERY",
        3240.50, "RSD",
        yesterday.replace(hour=14, minute=22, second=10),
        approval_code="DM0001",
        loyalty_points=calc_points(3240.50, "APPROVED", "PURCHASE", "RSD")
    ))
    rows.append(make_tx(
        "visa", "M001", "Maxi Supermarket", "GROCERY",
        3240.50, "RSD",
        yesterday.replace(hour=14, minute=25, second=33),
        approval_code="DM0002",
        loyalty_points=calc_points(3240.50, "APPROVED", "PURCHASE", "RSD")
    ))

    # ── DISPUTE SCENARIO 2 ────────────────────────────────────
    # Mastercard ****5555 — double charge at NIS Petrol two days ago
    print("Creating dispute scenario 2 — double charge at NIS Petrol...")
    rows.append(make_tx(
        "mastercard", "M008", "NIS Petrol", "FUEL",
        5870.00, "RSD",
        two_days.replace(hour=9, minute=15, second=0),
        approval_code="DN0001",
        loyalty_points=calc_points(5870.00, "APPROVED", "PURCHASE", "RSD")
    ))
    rows.append(make_tx(
        "mastercard", "M008", "NIS Petrol", "FUEL",
        5870.00, "RSD",
        two_days.replace(hour=9, minute=17, second=44),
        approval_code="DN0002",
        loyalty_points=calc_points(5870.00, "APPROVED", "PURCHASE", "RSD")
    ))

    # ── DISPUTE SCENARIO 3 ────────────────────────────────────
    # Dinacard ****1111 — double charge at Gigatron last week
    print("Creating dispute scenario 3 — double charge at Gigatron...")
    rows.append(make_tx(
        "dinacard", "M020", "Gigatron", "ELECTRONICS",
        42500.00, "RSD",
        last_week.replace(hour=16, minute=45, second=0),
        approval_code="DG0001",
        loyalty_points=calc_points(42500.00, "APPROVED", "PURCHASE", "RSD")
    ))
    rows.append(make_tx(
        "dinacard", "M020", "Gigatron", "ELECTRONICS",
        42500.00, "RSD",
        last_week.replace(hour=16, minute=48, second=22),
        approval_code="DG0002",
        loyalty_points=calc_points(42500.00, "APPROVED", "PURCHASE", "RSD")
    ))

    # ── LOYALTY SCENARIO 1 ───────────────────────────────────
    # Visa ****4242 — 6 purchases with uncredited points
    print("Creating loyalty scenario 1 — Visa recent purchases...")
    loyalty_visa = [
        ("M001", "Maxi Supermarket",    "GROCERY",     2180.00, yesterday.replace(hour=11, minute=30)),
        ("M002", "Lidl Srbija",         "GROCERY",     1340.50, yesterday.replace(hour=17, minute=15)),
        ("M008", "NIS Petrol",          "FUEL",        4200.00, two_days.replace(hour=8,   minute=45)),
        ("M012", "Apoteka Beograd",     "PHARMACY",     890.00, two_days.replace(hour=15,  minute=20)),
        ("M015", "McDonald's Beograd",  "RESTAURANT",   760.00, last_week.replace(hour=13, minute=0)),
        ("M031", "Cinema City Beograd", "ENTERTAINMENT",1600.00,last_week.replace(hour=19, minute=30)),
    ]
    for m_id, m_name, cat, amt, dt in loyalty_visa:
        rows.append(make_tx(
            "visa", m_id, m_name, cat, amt, "RSD", dt,
            loyalty_points=calc_points(amt, "APPROVED", "PURCHASE", "RSD")
        ))

    # ── LOYALTY SCENARIO 2 ───────────────────────────────────
    # Mastercard ****5555 — purchases with one declined (no points for declined)
    print("Creating loyalty scenario 2 — Mastercard recent purchases...")
    loyalty_mc = [
        ("M003", "Mercator",    "GROCERY",     3100.00, yesterday.replace(hour=10, minute=0),  "APPROVED", "00"),
        ("M009", "OMV Srbija",  "FUEL",        6300.00, two_days.replace(hour=7,   minute=30), "APPROVED", "00"),
        ("M023", "H&M Beograd", "CLOTHING",    8900.00, three_days.replace(hour=14, minute=0), "APPROVED", "00"),
        ("M020", "Gigatron",    "ELECTRONICS",15000.00, three_days.replace(hour=16, minute=0), "DECLINED", "51"),
        ("M033", "Ikea Srbija", "FURNITURE",  24000.00, last_week.replace(hour=11,  minute=0), "APPROVED", "00"),
    ]
    for m_id, m_name, cat, amt, dt, status, code in loyalty_mc:
        pts = calc_points(amt, status, "PURCHASE", "RSD")
        rows.append(make_tx(
            "mastercard", m_id, m_name, cat, amt, "RSD", dt,
            status=status, response_code=code,
            loyalty_points=pts
        ))

    # ── RECENT NORMAL TRANSACTIONS ───────────────────────────
    # Fresh transactions for today/yesterday so date queries work
    print("Creating recent normal transactions for all demo cards...")
    recent = [
        ("visa",       "M001", "Maxi Supermarket",     "GROCERY",   1890.00, "RSD", today.replace(hour=9,  minute=10)),
        ("visa",       "M008", "NIS Petrol",           "FUEL",      4500.00, "RSD", today.replace(hour=7,  minute=30)),
        ("mastercard", "M002", "Lidl Srbija",          "GROCERY",   2200.00, "RSD", today.replace(hour=10, minute=0)),
        ("mastercard", "M013", "DM Drogerije",         "PHARMACY",   640.00, "RSD", today.replace(hour=11, minute=15)),
        ("dinacard",   "M004", "Univerexport",         "GROCERY",   1100.00, "RSD", today.replace(hour=8,  minute=45)),
        ("dinacard",   "M028", "Telekom Srbija",       "UTILITIES", 2400.00, "RSD", yesterday.replace(hour=15, minute=0)),
        ("amex",       "M036", "Hotel Metropol Palace","HOTEL",      120.00, "EUR", today.replace(hour=12, minute=0)),
        ("amex",       "M039", "Airport Duty Free BEG","RETAIL",     45.00, "EUR", yesterday.replace(hour=18, minute=30)),
    ]
    for card_key, m_id, m_name, cat, amt, curr, dt in recent:
        rows.append(make_tx(
            card_key, m_id, m_name, cat, amt, curr, dt,
            loyalty_points=calc_points(amt, "APPROVED", "PURCHASE", curr)
        ))

    # ── Insert all ────────────────────────────────────────────
    print(f"\nInserting {len(rows)} demo transactions...")
    execute_values(cur, INSERT_SQL, rows)
    conn.commit()

    # ── Upsert loyalty accounts ───────────────────────────────
    print("Upserting loyalty accounts for demo PANs...")
    cur.executemany("""
        INSERT INTO loyalty_accounts (pan_masked, points, tier, total_spent)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (pan_masked) DO UPDATE
        SET points       = EXCLUDED.points,
            tier         = EXCLUDED.tier,
            last_updated = NOW()
    """, LOYALTY_ACCOUNTS)
    conn.commit()

    # ── Verify ────────────────────────────────────────────────
    print("\n── Demo data summary ─────────────────────────────")

    cur.execute("""
        SELECT pan_masked, COUNT(*) as tx_count,
               SUM(amount) as total
        FROM transactions
        WHERE pan_masked = ANY(%s)
        GROUP BY pan_masked ORDER BY pan_masked
    """, (DEMO_PANS,))
    print("  Transactions per demo PAN:")
    for row in cur.fetchall():
        print(f"    {row[0]}  →  {row[1]} transactions,  total {row[2]:,.2f}")

    cur.execute("""
        SELECT pan_masked, points, tier
        FROM loyalty_accounts ORDER BY tier
    """)
    print("\n  Loyalty accounts:")
    for row in cur.fetchall():
        print(f"    {row[0]}  →  {row[1]} points  ({row[2]})")

    cur.execute("""
        SELECT pan_masked,
               COUNT(*) as txns,
               SUM(loyalty_points_earned) as uncredited
        FROM transactions
        WHERE pan_masked = ANY(%s)
          AND loyalty_points_earned > 0
          AND loyalty_points_credited = FALSE
        GROUP BY pan_masked ORDER BY pan_masked
    """, (DEMO_PANS,))
    print("\n  Uncredited loyalty points:")
    for row in cur.fetchall():
        print(f"    {row[0]}  →  {row[2]} points across {row[1]} transactions")

    cur.execute("""
        SELECT t1.pan_masked, t1.amount, t1.merchant_name,
               t1.transaction_date, t1.approval_code
        FROM transactions t1
        JOIN transactions t2
          ON  t1.pan_masked    = t2.pan_masked
          AND t1.amount        = t2.amount
          AND t1.merchant_name = t2.merchant_name
          AND t1.approval_code != t2.approval_code
          AND t1.transaction_id != t2.transaction_id
          AND ABS(EXTRACT(EPOCH FROM (t1.transaction_date - t2.transaction_date))) < 3600
        WHERE t1.pan_masked = ANY(%s)
          AND t1.status = 'APPROVED'
        ORDER BY t1.pan_masked, t1.amount, t1.transaction_date
    """, (DEMO_PANS,))
    print("\n  Dispute pairs (duplicate charges):")
    for row in cur.fetchall():
        print(f"    {row[0]}  {row[1]:>10,.2f} RSD  {row[2]:<25}  {str(row[3])[:16]}")

    print("\n──────────────────────────────────────────────────")
    cur.close()

def main():
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    # ── Clean up ALL previous demo transactions first ─────────
    print("Cleaning up previous demo transactions...")
    cur.execute("""
        DELETE FROM transactions
        WHERE pan_masked = ANY(%s)
    """, (DEMO_PANS,))
    deleted = cur.rowcount
    conn.commit()
    print(f"  Removed {deleted} previous demo transactions.")

    cur.close()

    # ── Seed fresh data ───────────────────────────────────────
    seed(conn)

    conn.close()
    print("\nDemo data ready.")

if __name__ == "__main__":
    main()
