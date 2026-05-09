# POS NLP Agent

A conversational AI agent that lets non-technical users query a POS payment transactions database using natural language — in Serbian or English.

**Frontend (Vercel):** https://pos-nlp-agent.vercel.app  
**Backend (Railway):** https://pos-nlp-agent-production.up.railway.app

---

## What it does

Users select a role (Cardholder, Merchant, Dispute, Loyalty) and ask questions in plain language. The agent translates their intent into SQL, queries the database, and returns a structured answer with results. Write operations (dispute reversals, loyalty credits) go through a separate ops approval flow.

---

## Architecture

```
Browser (React on Vercel)
    ↕ WebSocket
FastAPI backend (Railway)
    → LangGraph workflow
        → Router node       — classifies role + language, 3-strike channel guard
        → Cardholder node   — own transactions by PAN (SELECT only)
        → Merchant node     — terminal/revenue data, Excel export (SELECT only)
        → Dispute node      — duplicate detection, receipt OCR via Vision (SELECT only)
        → Loyalty node      — uncredited points gap detection (SELECT only)
        → Validator node    — blocks all DML/DDL
        → Executor node     — psycopg2 query
        → Format node       — DB-driven flag correction (hallucination guard)
    → Pending approvals queue  ← customer Submit enqueues here
    → Approver agent           — LLM audit decision (APPROVE | REJECT)
    → write_ops.py             — called only after ops APPROVE
PostgreSQL on Supabase
    → transactions (100,025 rows)
    → loyalty_accounts (4 demo members)
    → pending_approvals (ops queue)
```

**LLM calls per turn:** 2 — router + one specialist node. If the router short-circuits (mismatch, menu), only 1 call is made.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, WebSocket |
| Backend | FastAPI, uvicorn |
| AI workflow | LangGraph 0.2 |
| LLM | Claude Sonnet (`claude-sonnet-4-6`) via Anthropic SDK |
| Database | PostgreSQL on Supabase |
| Excel export | openpyxl |
| Receipt OCR | Claude Vision (Pillow for image handling) |
| Deployment | Railway (backend), Vercel (frontend) |

---

## Folder structure

```
├── backend/files/       — FastAPI app + LangGraph agent
├── frontend/src/        — React chat UI
├── db/supabase/         — Schema, seed scripts, daily top-up
├── validation/          — 56 automated test cases + runner
└── receipts/            — Demo receipt PNGs for dispute testing
```

---

## Running locally

### Backend
```bash
cd backend/files
pip install -r requirements.txt
# Create .env — see backend/files/README.md for required variables
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm start          # opens at http://localhost:3000
```

### Database
```bash
cd db/supabase
python topup.py    # add recent transactions (run before testing)
python demo_seed.py  # seed dispute pairs + loyalty scenarios
```

---

## Validation

56 automated test cases across 12 categories (exact match, range, aggregation, multi-filter, status, multi-turn, edge cases, cardholder, merchant, dispute, loyalty, router).

```bash
cd validation
pip install websockets

# Local — seed DB first
python run_tests.py --seed

# Deployed backend
python run_tests.py --url wss://pos-nlp-agent-production.up.railway.app

# One category
python run_tests.py --category dispute

# Save report
python run_tests.py --seed --output results.json
```

See `validation/README.md` for full evaluation criteria.

---

## Temperature experiments

Node temperatures are configurable per node without code changes. Defaults are all `0.0` (deterministic), appropriate for NL→SQL generation.

**Experiment files** (git-ignored):
```
backend/files/.env.exp_merchant   — TEMP_MERCHANT=0.3
backend/files/.env.exp_dispute    — TEMP_DISPUTE=0.2
```

**Run an experiment:**
```bash
env $(grep -v '^#' backend/files/.env | xargs) TEMP_MERCHANT=0.3 uvicorn main:app --reload --port 8000
# then compare validation output:
python run_tests.py --category merchant --output results_exp_merchant.json
```

See `backend/files/README.md` for all available `TEMP_*` environment variables.

---

## Key design decisions

- **AI workflow not pure agent** — LangGraph graph topology is fixed; Python logic controls routing, not the LLM. Predictable, debuggable.
- **NL2SQL not RAG** — structured tabular data is more precisely served by SQL than vector search; schema fits in the system prompt (~400 tokens).
- **Hybrid router** — user selects role (reduces cognitive load) + AI validates each message (catches wrong-channel queries with 3-strike enforcement).
- **Read-only guard** — SQL validator blocks all DML/DDL before execution; writes only via `write_ops.py` after explicit ops approval.
- **Separation of duties** — investigator agents only read; a separate approver agent and ops human must approve before any write occurs.
- **Hallucination guard** — `format_node` overrides Claude's `dispute_found`/`credit_recommended` flags based on actual DB row counts.
- **PCI-DSS safe** — only schema goes to the Anthropic API, never actual card data.

---

## Demo scenarios

### Merchant
Select Merchant → *"Show all declined transactions on my terminals last week"*  
→ *"Sortiraj po iznosu"* → *"Export to Excel"*

### Dispute
Select Dispute → *"I was charged twice at Maxi for my Visa card ending in 4242, amount 3240.50 RSD"*  
→ attach `receipts/receipt_dispute_01_maxi.png` → click Approve reversal

### Loyalty
Select Loyalty → *"My points were not added for card ending in 4242"*  
→ click Credit points

### Router in action
Select Cardholder → *"I was charged twice at Maxi yesterday"*  
→ router detects DISPUTE intent → reply *"yes"* → switches channel automatically

---

## Demo PANs

| PAN | Brand | Tier | Points |
|---|---|---|---|
| 411111\*\*\*\*\*\*4242 | VISA | SILVER | 1250 |
| 510000\*\*\*\*\*\*5555 | MASTERCARD | STANDARD | 870 |
| 989100\*\*\*\*\*\*1111 | DINACARD | GOLD | 3400 |
| 370000\*\*\*\*\*9999 | AMEX | STANDARD | 520 |
