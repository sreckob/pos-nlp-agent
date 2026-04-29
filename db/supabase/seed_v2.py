"""
POS Transaction Database — Seed Script v2.0
============================================
Generates and inserts 100,000 realistic synthetic POS transactions.
Includes loyalty and dispute columns from the start.

Loyalty logic:
  - A small set of demo PANs are pre-enrolled in loyalty_accounts
  - Only enrolled PANs earn points on approved RSD purchases
  - Rule: FLOOR(amount / 100) points per approved purchase
  - All other transactions get loyalty_points_earned = 0

Dispute logic:
  - All regular transactions start with dispute columns = NULL
  - Dispute scenarios are seeded separately via demo_seed.py

Card brands and BIN ranges:
  VISA        400000–499999               16 digits
  MASTERCARD  510000–559999 (classic)     16 digits
              222100–272099 (2-series)    16 digits
  AMEX        340000–349999               15 digits
              370000–379999               15 digits
  DINACARD    989100–989199               16 digits
  UNIONPAY    620000–629999               16 digits

Usage:
    pip install psycopg2-binary python-dotenv
    cp .env.example .env
    python seed.py
"""

import os
import random
import string
import uuid
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────
TOTAL_TRANSACTIONS = 100_000
BATCH_SIZE         = 2_000
DATABASE_URL       = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/pos_db"
)

DATE_END   = datetime.now()
DATE_START = DATE_END - timedelta(days=365)

# ── Demo loyalty PANs (pre-enrolled members) ──────────────────
# These PANs will have loyalty_accounts records seeded below.
# Regular random transactions use random PANs — most will not match.
DEMO_LOYALTY_PANS = {
    "411111******4242",   # Visa demo — Silver
    "510000******5555",   # Mastercard demo — Standard
    "989100******1111",   # Dinacard demo — Gold
    "370000*****9999",    # Amex demo — Standard
}

# ── Card brands ───────────────────────────────────────────────
CARD_BRANDS = {
    "VISA":       {"bin_ranges": [(400000, 499999)],                   "pan_length": 16, "weight": 42},
    "MASTERCARD": {"bin_ranges": [(510000, 559999), (222100, 272099)], "pan_length": 16, "weight": 32},
    "DINACARD":   {"bin_ranges": [(989100, 989199)],                   "pan_length": 16, "weight": 14},
    "AMEX":       {"bin_ranges": [(340000, 349999), (370000, 379999)], "pan_length": 15, "weight": 7},
    "UNIONPAY":   {"bin_ranges": [(620000, 629999)],                   "pan_length": 16, "weight": 5},
}

# ── Status distribution ───────────────────────────────────────
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

CARD_TYPES        = [("CONTACTLESS", 48), ("CHIP", 42), ("MAGNETIC", 7),  ("MANUAL", 3)]
CARD_CLASSES      = [("DEBIT", 52),       ("CREDIT", 33), ("PREPAID", 8), ("CORPORATE", 7)]
TRANSACTION_TYPES = [("PURCHASE", 90),    ("REFUND", 5),  ("REVERSAL", 3),("CASH_ADVANCE", 2)]

# ── Merchants ─────────────────────────────────────────────────
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
    ("M017", "KFC Srbija",             "RESTAURANT",    (350,   2200), "RSD"),
    ("M018", "Restoran Lorenzo",       "RESTAURANT",    (1500,  9000), "RSD"),
    ("M020", "Gigatron",               "ELECTRONICS",   (2000, 90000), "RSD"),
    ("M021", "Tehnomanija",            "ELECTRONICS",   (1500, 70000), "RSD"),
    ("M022", "Computerland",           "ELECTRONICS",   (3000, 80000), "RSD"),
    ("M023", "H&M Beograd",            "CLOTHING",      (1200, 14000), "RSD"),
    ("M024", "Zara Srbija",            "CLOTHING",      (1500, 18000), "RSD"),
    ("M025", "Sport Vision",           "CLOTHING",      (2000, 25000), "RSD"),
    ("M026", "Nike Store Beograd",     "CLOTHING",      (3000, 30000), "RSD"),
    ("M028", "Telekom Srbija",         "UTILITIES",     (800,   6000), "RSD"),
    ("M029", "A1 Srbija",              "UTILITIES",     (700,   5500), "RSD"),
    ("M030", "EPS Elektroprivreda",    "UTILITIES",     (1500, 18000), "RSD"),
    ("M031", "Cinema City Beograd",    "ENTERTAINMENT", (700,   2500), "RSD"),
    ("M032", "Stark Arena",            "ENTERTAINMENT", (2000, 15000), "RSD"),
    ("M033", "Ikea Srbija",            "FURNITURE",     (1500, 90000), "RSD"),
    ("M034", "Bauhaus Srbija",         "HARDWARE",      (400,  45000), "RSD"),
    ("M035", "Moj Nameštaj",           "FURNITURE",     (5000, 80000), "RSD"),
    ("M036", "Hotel Metropol Palace",  "HOTEL",         (80,     400), "EUR"),
    ("M037", "Hilton Belgrade",        "HOTEL",         (100,    600), "EUR"),
    ("M038", "Crowne Plaza Belgrade",  "HOTEL",         (90,     450), "EUR"),
    ("M039", "Airport Duty Free BEG", "RETAIL",         (15,     250), "EUR"),
    ("M040", "Relay BEG Airport",      "RETAIL",        (5,       80), "EUR"),
]

# ── Terminals ─────────────────────────────────────────────────
def build_terminals():
    terminals = []
    for m in MERCHANTS:
        count = random.randint(2, 10)
        for i in range(1, count + 1):
            terminals.append((f"T{m[0][1:]}{i:02d}", m[0]))
    return terminals

TERMINALS = build_terminals()
TERMINAL_BY_MERCHANT = {}
for tid, mid in TERMINALS:
    TERMINAL_BY_MERCHANT.setdefault(mid, []).append(tid)

# ── Helpers ───────────────────────────────────────────────────
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

def generate_pan(brand: str) -> str:
    data = CARD_BRANDS[brand]
    bin_range = random.choice(data["bin_ranges"])
    bin_number = str(random.randint(bin_range[0], bin_range[1]))
    pan_len = data["pan_length"]
    last4 = str(random.randint(1000, 9999))
    stars = "*" * (pan_len - len(bin_number) - len(last4))
    return f"{bin_number}{stars}{last4}"

def generate_approval_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def random_date() -> datetime:
    delta = DATE_END - DATE_START
    return DATE_START + timedelta(seconds=random.randint(0, int(delta.total_seconds())))

def pick_status_and_code():
    total = sum(w for _, _, w in STATUS_DIST)
    r = random.uniform(0, total)
    cum = 0
    for status, code, w in STATUS_DIST:
        cum += w
        if r <= cum:
            return status, code
    return "APPROVED", "00"

def calculate_loyalty_points(pan: str, status: str, tx_type: str,
                              currency: str, amount: float) -> int:
    """
    Points only for loyalty members on eligible transactions.
    Non-members: 0 always.
    Members: APPROVED + PURCHASE + RSD → FLOOR(amount / 100)
    """
    if pan not in DEMO_LOYALTY_PANS:
        return 0
    if status == "APPROVED" and tx_type == "PURCHASE" and currency == "RSD":
        return int(amount // 100)
    return 0

# ── Transaction generator ─────────────────────────────────────
def generate_transaction():
    merchant     = random.choice(MERCHANTS)
    m_id         = merchant[0]
    m_name       = merchant[1]
    m_category   = merchant[2]
    amount_range = merchant[3]
    currency     = merchant[4]

    terminal_id  = random.choice(TERMINAL_BY_MERCHANT.get(m_id, [f"T{m_id[1:]}01"]))
    brand        = pick_brand()
    pan          = generate_pan(brand)
    card_type    = weighted_choice(CARD_TYPES)
    card_class   = weighted_choice(CARD_CLASSES)
    tx_type      = weighted_choice(TRANSACTION_TYPES)
    status, code = pick_status_and_code()

    approval_code = generate_approval_code() if status in ("APPROVED", "PENDING") else None

    amount = round(random.uniform(*amount_range), 2)
    if tx_type in ("REFUND", "REVERSAL"):
        amount = -abs(amount)

    loyalty_points = calculate_loyalty_points(pan, status, tx_type, currency, amount)

    return (
        str(uuid.uuid4()),      # transaction_id
        random_date(),          # transaction_date
        amount,                 # amount
        currency,               # currency
        status,                 # status
        code,                   # response_code
        approval_code,          # approval_code
        pan,                    # pan_masked
        brand,                  # card_brand
        card_type,              # card_type
        card_class,             # card_class
        terminal_id,            # terminal_id
        m_id,                   # merchant_id
        m_name,                 # merchant_name
        m_category,             # merchant_category
        tx_type,                # transaction_type
        loyalty_points,         # loyalty_points_earned
        False,                  # loyalty_points_credited
        None,                   # dispute_status
        None,                   # dispute_id
        None,                   # disputed_at
        None,                   # resolved_at
    )

# ── INSERT SQL ────────────────────────────────────────────────
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

# ── Loyalty accounts seed data ────────────────────────────────
LOYALTY_SEED = [
    # (pan_masked, points, tier, total_spent)
    ("411111******4242", 1250,  "SILVER",   67_400.00),
    ("510000******5555",  870,  "STANDARD", 38_200.00),
    ("989100******1111", 3400,  "GOLD",    215_800.00),
    ("370000*****9999",   520,  "STANDARD", 24_100.00),
]

# ── Main ──────────────────────────────────────────────────────
def print_stats(cur):
    print("\n── Sanity check ──────────────────────────────────")

    cur.execute("SELECT COUNT(*) FROM transactions;")
    print(f"  Total rows:          {cur.fetchone()[0]:>10,}")

    cur.execute("""
        SELECT status, COUNT(*) FROM transactions
        GROUP BY status ORDER BY COUNT(*) DESC
    """)
    print("  By status:")
    for r in cur.fetchall():
        print(f"    {r[0]:<12}  {r[1]:>8,}")

    cur.execute("""
        SELECT card_brand, COUNT(*) FROM transactions
        GROUP BY card_brand ORDER BY COUNT(*) DESC
    """)
    print("  By card brand:")
    for r in cur.fetchall():
        print(f"    {r[0]:<14}  {r[1]:>8,}")

    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE loyalty_points_earned > 0) AS with_pts,
               SUM(loyalty_points_earned) AS total_pts
        FROM transactions
    """)
    r = cur.fetchone()
    print(f"  Transactions with loyalty points: {r[0]:,}")
    print(f"  Total loyalty points in DB:       {r[1]:,}")

    cur.execute("SELECT MIN(transaction_date), MAX(transaction_date) FROM transactions;")
    lo, hi = cur.fetchone()
    print(f"  Date range:          {lo.date()} → {hi.date()}")

    cur.execute("SELECT COUNT(*) FROM loyalty_accounts;")
    print(f"  Loyalty accounts:    {cur.fetchone()[0]:>10,}")
    print("──────────────────────────────────────────────────")

def main():
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

# Schema already applied manually in Supabase SQL Editor
# print("Applying schema...")
# schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
# with open(schema_path) as f:
#     cur.execute(f.read())
# conn.commit()
# print("  Schema applied.")

    # Seed loyalty accounts first
    print("Seeding loyalty accounts...")
    cur.executemany("""
        INSERT INTO loyalty_accounts (pan_masked, points, tier, total_spent)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (pan_masked) DO NOTHING
    """, LOYALTY_SEED)
    conn.commit()
    print(f"  {len(LOYALTY_SEED)} loyalty accounts created.")

    # Generate and insert transactions
    print(f"Inserting {TOTAL_TRANSACTIONS:,} transactions (batch {BATCH_SIZE:,})...")

    inserted = 0
    batch    = []

    for i in range(TOTAL_TRANSACTIONS):
        batch.append(generate_transaction())
        if len(batch) == BATCH_SIZE:
            execute_values(cur, INSERT_SQL, batch)
            conn.commit()
            inserted += len(batch)
            batch = []
            pct = inserted / TOTAL_TRANSACTIONS * 100
            print(f"  {inserted:>7,} / {TOTAL_TRANSACTIONS:,}  ({pct:.0f}%)", end="\r")

    if batch:
        execute_values(cur, INSERT_SQL, batch)
        conn.commit()
        inserted += len(batch)

    print(f"  {inserted:>7,} / {TOTAL_TRANSACTIONS:,}  (100%)  ✓")

    print_stats(cur)
    cur.close()
    conn.close()
    print("\nDatabase ready.\n")

if __name__ == "__main__":
    main()
