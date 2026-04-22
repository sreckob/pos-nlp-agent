"""
POS Transaction Database — Seed Script
=======================================
Generates and inserts 100,000 realistic synthetic POS transactions.

Card brands and official BIN ranges used:
  VISA        400000–499999               16 digits
  MASTERCARD  510000–559999 (classic)     16 digits
              222100–272099 (2-series)    16 digits
  AMEX        340000–349999               15 digits
              370000–379999               15 digits
  DINACARD    989100–989199               16 digits  (Serbian national card)
  UNIONPAY    620000–629999               16 digits  (China UnionPay)

Setup:
    pip install psycopg2-binary python-dotenv
    cp .env.example .env          # edit DATABASE_URL
    python seed.py

Supabase connection string format:
    postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres

DigitalOcean connection string format:
    postgresql://doadmin:[PASSWORD]@[HOST].db.ondigitalocean.com:25060/defaultdb?sslmode=require

Local Docker format:
    postgresql://postgres:password@localhost:5432/pos_db
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

# ── Configuration ─────────────────────────────────────────────────────────────

TOTAL_TRANSACTIONS = 100_000
BATCH_SIZE         = 2_000
DATABASE_URL       = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/pos_db"
)

DATE_END   = datetime.now()
DATE_START = DATE_END - timedelta(days=365)

# ── Card brands with official BIN ranges ──────────────────────────────────────
#
#   weight = approximate % share of transactions at a Serbian POS terminal
#   Visa and Mastercard dominate; DinaCard significant locally;
#   UnionPay small but present (tourists, Chinese nationals)

CARD_BRANDS = {
    "VISA": {
        "bin_ranges": [
            (400000, 499999),           # entire Visa space starts with 4
        ],
        "pan_length": 16,
        "weight": 42,
    },
    "MASTERCARD": {
        "bin_ranges": [
            (510000, 559999),           # classic 51–55 range
            (222100, 272099),           # 2-series range, active since Oct 2016
        ],
        "pan_length": 16,
        "weight": 32,
    },
    "DINACARD": {
        "bin_ranges": [
            (989100, 989199),           # Serbian national payment card
        ],
        "pan_length": 16,
        "weight": 14,
    },
    "AMEX": {
        "bin_ranges": [
            (340000, 349999),           # 34xxxxxxxxxxxxX  (15 digits)
            (370000, 379999),           # 37xxxxxxxxxxxxX  (15 digits)
        ],
        "pan_length": 15,
        "weight": 7,
    },
    "UNIONPAY": {
        "bin_ranges": [
            (620000, 629999),           # China UnionPay full range
        ],
        "pan_length": 16,
        "weight": 5,
    },
}

# ── Status / response code distribution ──────────────────────────────────────
#
#   (status, ISO-8583-response-code, weight)
#   Realistic for a Serbian POS environment

STATUS_DIST = [
    ("APPROVED", "00", 83),   # approved
    ("DECLINED", "51",  5),   # insufficient funds
    ("DECLINED", "05",  3),   # do not honour
    ("DECLINED", "14",  2),   # invalid card number
    ("DECLINED", "61",  1),   # exceeds withdrawal limit
    ("DECLINED", "57",  1),   # transaction not permitted to cardholder
    ("DECLINED", "91",  1),   # issuer or switch inoperative
    ("DECLINED", "41",  1),   # lost card
    ("DECLINED", "43",  1),   # stolen card
    ("REVERSED", "00",  1),   # approved then reversed
    ("PENDING",  "00",  1),   # awaiting settlement
]

# ── Card type distribution ────────────────────────────────────────────────────
CARD_TYPES = [
    ("CONTACTLESS", 48),   # dominant modern method
    ("CHIP",        42),   # EMV chip
    ("MAGNETIC",     7),   # older cards / fallback
    ("MANUAL",       3),   # key-entered (e-commerce / MOTO)
]

# ── Card class distribution ───────────────────────────────────────────────────
CARD_CLASSES = [
    ("DEBIT",     52),
    ("CREDIT",    33),
    ("PREPAID",    8),
    ("CORPORATE",  7),
]

# ── Transaction type distribution ─────────────────────────────────────────────
TRANSACTION_TYPES = [
    ("PURCHASE",      90),
    ("REFUND",         5),
    ("REVERSAL",       3),
    ("CASH_ADVANCE",   2),
]

# ── Merchant data — realistic Serbian businesses ──────────────────────────────
#
#   (merchant_id, merchant_name, category, (min_amount, max_amount), currency)

MERCHANTS = [
    # Grocery / supermarkets
    ("M001", "Maxi Supermarket",        "GROCERY",       (250,   8500), "RSD"),
    ("M002", "Lidl Srbija",             "GROCERY",       (180,   6000), "RSD"),
    ("M003", "Mercator",                "GROCERY",       (300,   7500), "RSD"),
    ("M004", "Univerexport",            "GROCERY",       (200,   6500), "RSD"),
    ("M005", "Idea Supermarket",        "GROCERY",       (150,   5000), "RSD"),
    ("M006", "Billa Srbija",            "GROCERY",       (200,   6000), "RSD"),
    ("M007", "Roda Cash & Carry",       "GROCERY",       (500,  15000), "RSD"),

    # Fuel stations
    ("M008", "NIS Petrol",              "FUEL",          (1500,  8500), "RSD"),
    ("M009", "OMV Srbija",              "FUEL",          (1500,  8000), "RSD"),
    ("M010", "Mol Srbija",              "FUEL",          (1500,  7500), "RSD"),
    ("M011", "Lukoil Srbija",           "FUEL",          (1500,  8000), "RSD"),

    # Pharmacy / drugstore
    ("M012", "Apoteka Beograd",         "PHARMACY",      (300,   4000), "RSD"),
    ("M013", "DM Drogerije",            "PHARMACY",      (400,   5000), "RSD"),
    ("M014", "Apoteka Zemun",           "PHARMACY",      (250,   3500), "RSD"),

    # Restaurants / fast food
    ("M015", "McDonald's Beograd",      "RESTAURANT",    (400,   2500), "RSD"),
    ("M016", "Pizza Hut Srbija",        "RESTAURANT",    (700,   3500), "RSD"),
    ("M017", "KFC Srbija",              "RESTAURANT",    (350,   2200), "RSD"),
    ("M018", "KafanaQuestion Mark",    "RESTAURANT",    (800,   6000), "RSD"),
    ("M019", "Restoran Lorenzo",        "RESTAURANT",    (1500,  9000), "RSD"),

    # Electronics
    ("M020", "Gigatron",                "ELECTRONICS",   (2000, 90000), "RSD"),
    ("M021", "Tehnomanija",             "ELECTRONICS",   (1500, 70000), "RSD"),
    ("M022", "Computerland",            "ELECTRONICS",   (3000, 80000), "RSD"),

    # Clothing / fashion
    ("M023", "H&M Beograd",             "CLOTHING",      (1200, 14000), "RSD"),
    ("M024", "Zara Srbija",             "CLOTHING",      (1500, 18000), "RSD"),
    ("M025", "Sport Vision",            "CLOTHING",      (2000, 25000), "RSD"),
    ("M026", "Nike Store Beograd",      "CLOTHING",      (3000, 30000), "RSD"),
    ("M027", "C&A Srbija",              "CLOTHING",      (800,  12000), "RSD"),

    # Utilities / telecom
    ("M028", "Telekom Srbija",          "UTILITIES",     (800,   6000), "RSD"),
    ("M029", "A1 Srbija",               "UTILITIES",     (700,   5500), "RSD"),
    ("M030", "EPS Elektroprivreda",     "UTILITIES",     (1500, 18000), "RSD"),

    # Entertainment
    ("M031", "Cinema City Beograd",     "ENTERTAINMENT", (700,   2500), "RSD"),
    ("M032", "Stark Arena",             "ENTERTAINMENT", (2000, 15000), "RSD"),

    # Furniture / home
    ("M033", "Ikea Srbija",             "FURNITURE",     (1500, 90000), "RSD"),
    ("M034", "Bauhaus Srbija",          "HARDWARE",      (400,  45000), "RSD"),
    ("M035", "Moj Nameštaj",            "FURNITURE",     (5000, 80000), "RSD"),

    # Hotels (EUR)
    ("M036", "Hotel Metropol Palace",   "HOTEL",         (80,     400), "EUR"),
    ("M037", "Hilton Belgrade",         "HOTEL",         (100,    600), "EUR"),
    ("M038", "Crowne Plaza Belgrade",   "HOTEL",         (90,     450), "EUR"),

    # Airport / international retail (EUR)
    ("M039", "Airport Duty Free BEG",  "RETAIL",        (15,     250), "EUR"),
    ("M040", "Relay BEG Airport",      "RETAIL",        (5,       80), "EUR"),
]

# ── Build terminal pool ───────────────────────────────────────────────────────

def build_terminals():
    """Each merchant gets 2–10 terminals."""
    terminals = []
    for m in MERCHANTS:
        merchant_id = m[0]
        num = random.randint(2, 10)
        for i in range(1, num + 1):
            tid = f"T{merchant_id[1:]}{i:02d}"
            terminals.append((tid, merchant_id))
    return terminals

TERMINALS = build_terminals()
TERMINAL_BY_MERCHANT = {}
for tid, mid in TERMINALS:
    TERMINAL_BY_MERCHANT.setdefault(mid, []).append(tid)

# ── Helpers ───────────────────────────────────────────────────────────────────

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
    opts = [(b, d["weight"]) for b, d in CARD_BRANDS.items()]
    return weighted_choice(opts)

def generate_pan(brand: str) -> str:
    """
    Generate a masked PAN with correct BIN for the given brand.
    Format:
      16-digit: BBBBBB ******* LLLL   e.g. 411111******1111
      15-digit: BBBBBB ***** LLLL     e.g. 370000*****6789
    """
    data = CARD_BRANDS[brand]
    bin_range = random.choice(data["bin_ranges"])
    bin_number = str(random.randint(bin_range[0], bin_range[1]))
    pan_len = data["pan_length"]
    last4 = str(random.randint(1000, 9999))
    stars = "*" * (pan_len - len(bin_number) - len(last4))
    return f"{bin_number}{stars}{last4}"

def generate_approval_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def random_timestamp() -> datetime:
    delta = int((DATE_END - DATE_START).total_seconds())
    return DATE_START + timedelta(seconds=random.randint(0, delta))

def pick_status_and_code():
    total = sum(w for _, _, w in STATUS_DIST)
    r = random.uniform(0, total)
    cum = 0
    for status, code, w in STATUS_DIST:
        cum += w
        if r <= cum:
            return status, code
    return "APPROVED", "00"

# ── Transaction generator ─────────────────────────────────────────────────────

def generate_transaction():
    merchant     = random.choice(MERCHANTS)
    m_id         = merchant[0]
    m_name       = merchant[1]
    m_category   = merchant[2]
    amount_range = merchant[3]
    currency     = merchant[4]

    terminal_id  = random.choice(TERMINAL_BY_MERCHANT.get(m_id, [f"T{m_id[1:]}01"]))
    brand        = pick_brand()
    pan_masked   = generate_pan(brand)
    card_type    = weighted_choice(CARD_TYPES)
    card_class   = weighted_choice(CARD_CLASSES)
    tx_type      = weighted_choice(TRANSACTION_TYPES)
    status, response_code = pick_status_and_code()

    approval_code = generate_approval_code() if status in ("APPROVED", "PENDING") else None

    amount = round(random.uniform(*amount_range), 2)
    if tx_type in ("REFUND", "REVERSAL"):
        amount = -abs(amount)

    return (
        str(uuid.uuid4()),    # transaction_id
        random_timestamp(),   # transaction_date
        amount,               # amount
        currency,             # currency
        status,               # status
        response_code,        # response_code
        approval_code,        # approval_code
        pan_masked,           # pan_masked
        brand,                # card_brand
        card_type,            # card_type
        card_class,           # card_class
        terminal_id,          # terminal_id
        m_id,                 # merchant_id
        m_name,               # merchant_name
        m_category,           # merchant_category
        tx_type,              # transaction_type
    )

# ── Main ──────────────────────────────────────────────────────────────────────

INSERT_SQL = """
    INSERT INTO transactions (
        transaction_id, transaction_date, amount, currency,
        status, response_code, approval_code,
        pan_masked, card_brand, card_type, card_class,
        terminal_id, merchant_id, merchant_name, merchant_category,
        transaction_type
    ) VALUES %s
"""

def print_stats(cur):
    print("\n── Sanity check ──────────────────────────────────")

    cur.execute("SELECT COUNT(*) FROM transactions;")
    print(f"  Total rows:      {cur.fetchone()[0]:>10,}")

    cur.execute("""
        SELECT status, COUNT(*) AS n
        FROM transactions GROUP BY status ORDER BY n DESC;
    """)
    print("  By status:")
    for row in cur.fetchall():
        print(f"    {row[0]:<12}  {row[1]:>8,}")

    cur.execute("""
        SELECT card_brand, COUNT(*) AS n
        FROM transactions GROUP BY card_brand ORDER BY n DESC;
    """)
    print("  By card brand:")
    for row in cur.fetchall():
        print(f"    {row[0]:<14}  {row[1]:>8,}")

    cur.execute("""
        SELECT card_type, COUNT(*) AS n
        FROM transactions GROUP BY card_type ORDER BY n DESC;
    """)
    print("  By card type:")
    for row in cur.fetchall():
        print(f"    {row[0]:<14}  {row[1]:>8,}")

    cur.execute("SELECT MIN(transaction_date), MAX(transaction_date) FROM transactions;")
    lo, hi = cur.fetchone()
    print(f"  Date range:      {lo.date()} → {hi.date()}")

    cur.execute("SELECT MIN(amount), MAX(amount), ROUND(AVG(amount),2) FROM transactions;")
    mn, mx, av = cur.fetchone()
    print(f"  Amount range:    {mn} → {mx}  (avg {av})")
    print("──────────────────────────────────────────────────")

def main():
    print(f"Connecting to database …")
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    print("Applying schema …")
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        cur.execute(f.read())
    conn.commit()
    print("  Schema applied.")

    print(f"Inserting {TOTAL_TRANSACTIONS:,} transactions "
          f"(batch size {BATCH_SIZE:,}) …")

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
    print("\nDatabase is ready.\n")

if __name__ == "__main__":
    main()
