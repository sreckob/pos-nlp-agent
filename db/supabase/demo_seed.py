"""
Demo Scenario Seed Script
==========================
Inserts specific transactions for reliable demo scenarios.

Scenarios created:
  DISPUTE-01  Double charge at Maxi — Visa card ending 4242
  DISPUTE-02  Double charge at NIS Petrol — Mastercard ending 5555
  DISPUTE-03  Double charge at Gigatron — Dinacard ending 1111
  LOYALTY-01  Recent purchases for Visa card ending 4242 (missing points)
  LOYALTY-02  Recent purchases for Mastercard ending 5555 (missing points)

Usage:
    python demo_seed.py

After running, these transactions are in the DB and can be referenced
in demos, test cases, and receipt generation.
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
# These are the PANs we will use in all demo scenarios
# They should also exist in loyalty_accounts table

DEMO_CARDS = {
    "visa_demo":       {"pan": "411111******4242", "brand": "VISA",       "type": "CONTACTLESS", "class": "DEBIT"},
    "mastercard_demo": {"pan": "510000******5555", "brand": "MASTERCARD", "type": "CHIP",        "class": "CREDIT"},
    "dinacard_demo":   {"pan": "989100******1111", "brand": "DINACARD",   "type": "CHIP",        "class": "DEBIT"},
    "amex_demo":       {"pan": "370000*****9999",  "brand": "AMEX",       "type": "CHIP",        "class": "CORPORATE"},
}

INSERT_SQL = """
    INSERT INTO transactions (
        transaction_id, transaction_date, amount, currency,
        status, response_code, approval_code,
        pan_masked, card_brand, card_type, card_class,
        terminal_id, merchant_id, merchant_name, merchant_category,
        transaction_type
    ) VALUES %s
    ON CONFLICT DO NOTHING
"""

def make_tx(pan_key, merchant_id, merchant_name, category,
            amount, currency, date, status="APPROVED",
            response_code="00", tx_type="PURCHASE",
            approval_code=None, terminal_suffix="01"):
    card = DEMO_CARDS[pan_key]
    return (
        str(uuid.uuid4()),
        date,
        amount,
        currency,
        status,
        response_code,
        approval_code or f"D{str(abs(hash(str(date) + merchant_id)))[:5]}",
        card["pan"],
        card["brand"],
        card["type"],
        card["class"],
        f"T{merchant_id[1:]}{terminal_suffix}",
        merchant_id,
        merchant_name,
        category,
        tx_type,
    )

def seed_demo_transactions():
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    now       = datetime.now()
    today     = now.replace(hour=10, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    two_days  = today - timedelta(days=2)
    last_week = today - timedelta(days=7)

    rows = []

    # ── DISPUTE SCENARIO 1 ────────────────────────────────────
    # Visa card double-charged at Maxi Supermarket yesterday
    # Same amount, same terminal, 3 minutes apart — clear duplicate
    print("Creating dispute scenario 1 — double charge at Maxi...")
    rows.append(make_tx(
        "visa_demo", "M001", "Maxi Supermarket", "GROCERY",
        3240.50, "RSD",
        yesterday.replace(hour=14, minute=22, second=10),
        approval_code="DM0001"
    ))
    rows.append(make_tx(
        "visa_demo", "M001", "Maxi Supermarket", "GROCERY",
        3240.50, "RSD",
        yesterday.replace(hour=14, minute=25, second=33),
        approval_code="DM0002"
    ))

    # ── DISPUTE SCENARIO 2 ────────────────────────────────────
    # Mastercard double-charged at NIS Petrol two days ago
    print("Creating dispute scenario 2 — double charge at NIS Petrol...")
    rows.append(make_tx(
        "mastercard_demo", "M008", "NIS Petrol", "FUEL",
        5870.00, "RSD",
        two_days.replace(hour=9, minute=15, second=0),
        approval_code="DN0001"
    ))
    rows.append(make_tx(
        "mastercard_demo", "M008", "NIS Petrol", "FUEL",
        5870.00, "RSD",
        two_days.replace(hour=9, minute=17, second=44),
        approval_code="DN0002"
    ))

    # ── DISPUTE SCENARIO 3 ────────────────────────────────────
    # Dinacard double-charged at Gigatron last week
    print("Creating dispute scenario 3 — double charge at Gigatron...")
    rows.append(make_tx(
        "dinacard_demo", "M020", "Gigatron", "ELECTRONICS",
        42500.00, "RSD",
        last_week.replace(hour=16, minute=45, second=0),
        approval_code="DG0001"
    ))
    rows.append(make_tx(
        "dinacard_demo", "M020", "Gigatron", "ELECTRONICS",
        42500.00, "RSD",
        last_week.replace(hour=16, minute=48, second=22),
        approval_code="DG0002"
    ))

    # ── LOYALTY SCENARIO 1 ────────────────────────────────────
    # Visa card — several purchases last week, points should have been added
    print("Creating loyalty scenario 1 — Visa recent purchases...")
    loyalty_visa = [
        ("M001", "Maxi Supermarket",    "GROCERY",     2180.00, yesterday.replace(hour=11, minute=30)),
        ("M002", "Lidl Srbija",         "GROCERY",     1340.50, yesterday.replace(hour=17, minute=15)),
        ("M008", "NIS Petrol",          "FUEL",        4200.00, two_days.replace(hour=8,  minute=45)),
        ("M012", "Apoteka Beograd",     "PHARMACY",     890.00, two_days.replace(hour=15, minute=20)),
        ("M015", "McDonald's Beograd",  "RESTAURANT",   760.00, last_week.replace(hour=13, minute=0)),
        ("M031", "Cinema City Beograd", "ENTERTAINMENT",1600.00, last_week.replace(hour=19, minute=30)),
    ]
    for m_id, m_name, cat, amt, dt in loyalty_visa:
        rows.append(make_tx("visa_demo", m_id, m_name, cat, amt, "RSD", dt))

    # ── LOYALTY SCENARIO 2 ────────────────────────────────────
    # Mastercard — purchases last week, one declined (no points for declined)
    print("Creating loyalty scenario 2 — Mastercard recent purchases...")
    loyalty_mc = [
        ("M003", "Mercator",        "GROCERY",     3100.00, yesterday.replace(hour=10, minute=0),  "APPROVED", "00"),
        ("M009", "OMV Srbija",      "FUEL",        6300.00, two_days.replace(hour=7,   minute=30), "APPROVED", "00"),
        ("M023", "H&M Beograd",     "CLOTHING",    8900.00, last_week.replace(hour=14, minute=0),  "APPROVED", "00"),
        ("M020", "Gigatron",        "ELECTRONICS", 15000.0, last_week.replace(hour=16, minute=0),  "DECLINED", "51"),
        ("M033", "Ikea Srbija",     "FURNITURE",   24000.0, last_week.replace(hour=11, minute=0),  "APPROVED", "00"),
    ]
    for m_id, m_name, cat, amt, dt, status, code in loyalty_mc:
        rows.append(make_tx(
            "mastercard_demo", m_id, m_name, cat, amt, "RSD", dt,
            status=status, response_code=code
        ))

    # ── REGULAR RECENT TRANSACTIONS ───────────────────────────
    # A few normal approved transactions for today and yesterday
    # So "show me today's transactions" always returns something
    print("Creating recent normal transactions for all demo cards...")
    recent = [
        ("visa_demo",       "M001", "Maxi Supermarket",    "GROCERY",   1890.00, today.replace(hour=9,  minute=10)),
        ("visa_demo",       "M008", "NIS Petrol",          "FUEL",      4500.00, today.replace(hour=7,  minute=30)),
        ("mastercard_demo", "M002", "Lidl Srbija",         "GROCERY",   2200.00, today.replace(hour=10, minute=0)),
        ("mastercard_demo", "M013", "DM Drogerije",        "PHARMACY",   640.00, today.replace(hour=11, minute=15)),
        ("dinacard_demo",   "M004", "Univerexport",        "GROCERY",   1100.00, today.replace(hour=8,  minute=45)),
        ("dinacard_demo",   "M028", "Telekom Srbija",      "UTILITIES", 2400.00, yesterday.replace(hour=15, minute=0)),
        ("amex_demo",       "M036", "Hotel Metropol Palace","HOTEL",     120.00, today.replace(hour=12, minute=0)),
        ("amex_demo",       "M039", "Airport Duty Free BEG","RETAIL",    45.00, yesterday.replace(hour=18, minute=30)),
    ]
    for pan_key, m_id, m_name, cat, amt, dt in recent:
        rows.append(make_tx(pan_key, m_id, m_name, cat, amt, "RSD" if cat != "HOTEL" and cat != "RETAIL" else "EUR", dt))

    # ── Insert all ────────────────────────────────────────────
    print(f"\nInserting {len(rows)} demo transactions...")
    execute_values(cur, INSERT_SQL, rows)
    conn.commit()

    # ── Upsert loyalty accounts for demo PANs ─────────────────
    print("Upserting loyalty accounts for demo PANs...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS loyalty_accounts (
            account_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pan_masked   VARCHAR(19) NOT NULL UNIQUE,
            points       INTEGER DEFAULT 0,
            tier         VARCHAR(20) DEFAULT 'STANDARD',
            last_updated TIMESTAMP DEFAULT NOW()
        )
    """)

    loyalty_rows = [
        (DEMO_CARDS["visa_demo"]["pan"],       1250, "SILVER"),
        (DEMO_CARDS["mastercard_demo"]["pan"],  870, "STANDARD"),
        (DEMO_CARDS["dinacard_demo"]["pan"],   3400, "GOLD"),
        (DEMO_CARDS["amex_demo"]["pan"],        520, "STANDARD"),
    ]
    cur.executemany("""
        INSERT INTO loyalty_accounts (pan_masked, points, tier)
        VALUES (%s, %s, %s)
        ON CONFLICT (pan_masked) DO UPDATE
        SET points = EXCLUDED.points,
            tier   = EXCLUDED.tier,
            last_updated = NOW()
    """, loyalty_rows)
    conn.commit()

    # ── Verify ────────────────────────────────────────────────
    print("\n── Demo data summary ─────────────────────────────")
    cur.execute("""
        SELECT pan_masked, COUNT(*) as tx_count, SUM(amount) as total
        FROM transactions
        WHERE pan_masked IN %s
        GROUP BY pan_masked ORDER BY pan_masked
    """, (tuple(c["pan"] for c in DEMO_CARDS.values()),))

    print("  Transactions per demo PAN:")
    for row in cur.fetchall():
        print(f"    {row[0]}  →  {row[1]} transactions,  total {row[2]:,.2f}")

    cur.execute("""
        SELECT pan_masked, points, tier FROM loyalty_accounts ORDER BY tier
    """)
    print("\n  Loyalty accounts:")
    for row in cur.fetchall():
        print(f"    {row[0]}  →  {row[1]} points  ({row[2]})")

    cur.execute("""
        SELECT pan_masked, amount, merchant_name, transaction_date
        FROM transactions
        WHERE pan_masked IN %s
          AND amount IN (
            SELECT amount FROM transactions
            WHERE pan_masked IN %s
            GROUP BY pan_masked, amount, merchant_id,
                     DATE(transaction_date)
            HAVING COUNT(*) > 1
          )
        ORDER BY pan_masked, amount, transaction_date
    """, (
        tuple(c["pan"] for c in DEMO_CARDS.values()),
        tuple(c["pan"] for c in DEMO_CARDS.values()),
    ))
    print("\n  Duplicate charges (dispute scenarios):")
    for row in cur.fetchall():
        print(f"    {row[0]}  {row[1]:>10,.2f} RSD  {row[2]:<25}  {str(row[3])[:16]}")

    print("\n──────────────────────────────────────────────────")
    cur.close()
    conn.close()
    print("\nDemo data ready.")

if __name__ == "__main__":
    seed_demo_transactions()
