# POS Transaction Database — Setup Guide

## Files in this folder

| File | What it does |
|---|---|
| `schema.sql` | Creates the `transactions` table + 16 indexes |
| `seed.py` | Generates and inserts 100,000 synthetic transactions |
| `docker-compose.yml` | Runs local PostgreSQL via Docker (for development) |
| `.env.example` | Template — copy to `.env` and fill in your values |

---

## Step 1 — Create the database

Pick one option. The seed script works identically with all of them.

### Option A — Supabase (recommended for team sharing, free)

1. Go to https://supabase.com and create a free account
2. Click **New project** — choose a name, set a password, pick a region (Frankfurt is closest)
3. Wait ~2 minutes for provisioning
4. Go to **Settings → Database → Connection string → URI**
5. Copy the connection string — it looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
   ```
6. Paste it into your `.env` file as `DATABASE_URL`
7. Share the connection string with your teammates (via secure channel, not git)

### Option B — DigitalOcean Managed PostgreSQL ($15/month)

1. Go to https://cloud.digitalocean.com and create an account
2. Click **Create → Database**
3. Choose PostgreSQL 16, Basic plan ($15/mo), Frankfurt region
4. Wait ~5 minutes for provisioning
5. Go to your cluster → **Connection Details** → select **Connection string** from the dropdown
6. Copy the URI and paste it into `.env` as `DATABASE_URL`

### Option C — Local Docker (development only, not shareable)

```bash
docker compose up -d
# DATABASE_URL=postgresql://postgres:password@localhost:5432/pos_db
# (already the default in .env.example)
```

---

## Step 2 — Install Python dependencies

```bash
pip install psycopg2-binary python-dotenv
```

If you are on Linux and get a build error with psycopg2-binary, try:
```bash
pip install psycopg2-binary --break-system-packages
```

---

## Step 3 — Configure environment

```bash
cp .env.example .env
# Open .env and set DATABASE_URL to your connection string from Step 1
```

---

## Step 4 — Run the seed script

```bash
python seed.py
```

Expected output (takes 30–90 seconds depending on network):
```
Connecting to database …
Applying schema …
  Schema applied.
Inserting 100,000 transactions (batch size 2,000) …
  100,000 / 100,000  (100%)  ✓

── Sanity check ──────────────────────────────────
  Total rows:           100,000
  By status:
    APPROVED              83,xxx
    DECLINED              14,xxx
    REVERSED               1,xxx
    PENDING                1,xxx
  By card brand:
    VISA                  42,xxx
    MASTERCARD            32,xxx
    DINACARD              14,xxx
    AMEX                   7,xxx
    UNIONPAY               5,xxx
  By card type:
    CONTACTLESS           48,xxx
    CHIP                  42,xxx
    MAGNETIC               7,xxx
    MANUAL                 3,xxx
  Date range:      2025-04-22 → 2026-04-22
  Amount range:    -90000.00 → 90000.00  (avg ~2,400)
──────────────────────────────────────────────────
Database is ready.
```

---

## Step 5 — Verify the data

Connect to your database with any SQL client and run a few test queries:

```sql
-- Total count
SELECT COUNT(*) FROM transactions;

-- Declined transactions above 5,000 RSD
SELECT transaction_date, amount, card_brand, merchant_name, response_code
FROM transactions
WHERE status = 'DECLINED'
  AND amount > 5000
  AND currency = 'RSD'
ORDER BY transaction_date DESC
LIMIT 20;

-- Visa contactless transactions at Maxi
SELECT *
FROM transactions
WHERE card_brand = 'VISA'
  AND card_type = 'CONTACTLESS'
  AND merchant_name ILIKE '%Maxi%'
ORDER BY transaction_date DESC
LIMIT 10;

-- Top 10 most active terminals
SELECT terminal_id, COUNT(*) AS tx_count, SUM(amount) AS total_amount
FROM transactions
WHERE status = 'APPROVED'
GROUP BY terminal_id
ORDER BY tx_count DESC
LIMIT 10;

-- UnionPay transactions (tourists / Chinese nationals)
SELECT *
FROM transactions
WHERE card_brand = 'UNIONPAY'
ORDER BY transaction_date DESC
LIMIT 20;

-- Revenue by merchant category last 30 days
SELECT merchant_category,
       COUNT(*) AS transactions,
       ROUND(SUM(amount), 2) AS total_rsd
FROM transactions
WHERE status = 'APPROVED'
  AND currency = 'RSD'
  AND transaction_date >= NOW() - INTERVAL '30 days'
GROUP BY merchant_category
ORDER BY total_rsd DESC;
```

---

## BIN ranges used (official card scheme sources)

| Brand | BIN range | PAN length | Source |
|---|---|---|---|
| Visa | 400000–499999 | 16 digits | All cards starting with 4 |
| Mastercard | 510000–559999 | 16 digits | Classic 51–55 range |
| Mastercard | 222100–272099 | 16 digits | 2-series, active since Oct 2016 |
| Amex | 340000–349999 | 15 digits | |
| Amex | 370000–379999 | 15 digits | |
| DinaCard | 989100–989199 | 16 digits | Serbian national payment card |
| UnionPay | 620000–629999 | 16 digits | China UnionPay full range |

---

## Re-seeding

If you want to start fresh (e.g. to change the schema):

```bash
python seed.py   # schema.sql drops and recreates the table automatically
```

The `DROP TABLE IF EXISTS` at the top of `schema.sql` handles cleanup.

---

## Migrating from Supabase to DigitalOcean

When you are ready to move to production hosting:

1. Update `DATABASE_URL` in `.env` to point to DigitalOcean
2. Run `python seed.py` again
3. Done — all other code (FastAPI, LangGraph agent) just reads `DATABASE_URL`
   from the environment and requires no changes
