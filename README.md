# POS NLP Agent

A conversational AI agent that lets non-technical users query a POS payment transactions database using natural language — in Serbian or English.

**Frontend (Vercel):** https://pos-nlp-agent.vercel.app  
**Backend (Railway):** https://pos-nlp-agent-production.up.railway.app

---

## The problem

Payment operations staff, merchants, and cardholders all need to query the same POS transaction database — but none of them are SQL users. Today they either wait for a developer to run a query, or they get access to a reporting tool with a fixed set of screens that never quite matches what they need.

This project replaces that with a chat interface: the user describes what they want in plain language (or Serbian), and the agent translates it into SQL, executes it, and returns a structured answer. For write operations (reversing a duplicate charge, crediting missing loyalty points), the agent identifies the issue and queues it for human approval — no direct DB writes from user input.

---

## Demo video

[Watch the demo](https://wetransfer.com/downloads/115770eecce1f76eab58139d732a0cde20260521111015/b298bb36e0a1cb86d2e012afd6ba3ea620260521111055/26f09d) *(temporary link, valid until May 24 2026 — will be replaced with YouTube)*

---

## What it does

Users select a role and ask questions in plain language:

| Role | What they can do |
|---|---|
| **Cardholder** | Query their own transaction history by card number, filter by status, date, merchant |
| **Merchant** | Query terminal/revenue data, filter declined transactions, export to Excel |
| **Dispute** | Report a double charge (with optional receipt image), agent finds the duplicate and queues a reversal for ops approval |
| **Loyalty** | Check points balance, find uncredited transactions, submit a credit request for ops approval |

The agent also validates that each message belongs to the selected channel and suggests switching if not (hybrid router with 3-strike enforcement).

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
        → RAG store            — retrieves relevant chargeback regulation clauses
    → write_ops.py             — called only after ops APPROVE
PostgreSQL on Supabase
    → transactions (100,025 rows)
    → loyalty_accounts (4 demo members)
    → dispute_policies (pgvector embeddings of chargeback regulations)
```

**LLM calls per turn:** 2 — router + one specialist node. If the router short-circuits (mismatch, menu), only 1 call is made.

---

## Components

**`agent.py`** — LangGraph state machine with 8 nodes. Handles routing, SQL generation, validation, execution, and response formatting. All conditional logic is in Python; only NL→SQL and role classification are delegated to the LLM.

**`prompts.py`** — System prompts for all five roles (router + 4 specialist paths) plus two internal approver prompts (dispute and loyalty). Schema is injected once and cached.

**`approval_agent.py`** — Separate LLM agent that reviews queued dispute/loyalty submissions. Pulls relevant regulation clauses from the RAG store and produces an audit decision with a one-line summary for the ops log.

**`rag_store.py`** — Retrieves the top-K most relevant chargeback regulation clauses from pgvector given a dispute scenario description. Used by the approver agent to cite regulations (e.g. "per Visa VDR-11.1.3"). Populated by running `ingest_policies.py` once.

**`write_ops.py`** — The only file that performs DB writes. Called exclusively by the ops `/decide` endpoint after a human approves. Marks duplicate transactions as REVERSED or credits loyalty points.

**`main.py`** — FastAPI app. Exposes WebSocket for chat, REST endpoints for dispute/loyalty submit, and ops endpoints (queue, detail, decide) protected by `X-Ops-Key` header.

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

### Prerequisites
- Python 3.10+
- Node.js 18+
- A Supabase project with the schema from `db/supabase/schema.sql`
- An Anthropic API key

### Environment variables

Create `backend/files/.env`:
```
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-6
OPS_API_KEY=any-secret-string
MAX_ROWS_RETURNED=100
LOG_FILE=agent_logs.jsonl
```

### Backend
```bash
cd backend/files
pip install -r requirements.txt
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
python seed_v2.py      # seed 100k transactions (first time only)
python demo_seed.py    # seed dispute pairs + loyalty scenarios
python topup.py        # add recent transactions (run before testing)
python ingest_policies.py  # populate pgvector RAG store (first time only)
```

---

## Evaluation results

Latest run against local backend (May 19, 2026):

| Suite | Result | Interpretation |
|---|---|---|
| Router | **100% accuracy, F1=1.000** | All 29 channel classifications correct across English and Serbian, including single-word inputs ("da", "poeni"). No misrouting in any test. |
| Policy | **15/15 checks passed** | All DML injection attempts blocked, PAN isolation enforced on every cardholder query, ops endpoints protected. |
| RAG | **P@3=0.625, R@3=0.771, F1@3=0.690** | On average 2 of 3 retrieved regulation clauses are relevant. Acceptable for audit enrichment; 2 edge-case scenarios (unauthorized charge, PSP liability) score 0.33 due to missing niche clauses. |
| State | **2/2 write ops validated** | Dispute reversal and loyalty credit both correctly update the DB before/after. |
| LLM Judge | **3 scenarios scored** | Approver agent produces audit decisions with regulatory citations. Agreement tracking between deterministic checks and LLM judge in progress. |
| Iron User | **4/5 scenarios, 15/16 turns** | Cardholder refinement, dispute flow, loyalty flow, and router switch all pass fully. Merchant Excel export (turn 3) has one remaining issue with explicit SQL generation on the export command. |

---

## Validation

Full evaluation suite with 6 modules:

| Suite | What it tests |
|---|---|
| `router` | Per-channel precision / recall / F1 + confusion matrix |
| `state` | DB before/after validation for write ops |
| `policy` | Read-only guard, PAN isolation, ops auth |
| `rag` | RAG Precision@K retrieval quality |
| `judge` | LLM-as-judge for approver audit quality |
| `iron` | Multi-turn Iron User conversation scenarios |

```bash
cd validation
pip install websockets

python eval_suite.py                          # all suites, local backend
python eval_suite.py --output results.json    # save full JSON report
python eval_suite.py --only router,policy     # specific suites
python eval_suite.py --url wss://pos-nlp-agent-production.up.railway.app
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
- **NL2SQL for queries, RAG for approvals** — SQL is more precise than vector search for structured transaction data; RAG (pgvector + sentence-transformers) is used in the approver agent to retrieve relevant chargeback regulation clauses.
- **Schema in system prompt, cached** — schema fits in ~400 tokens and is cached via prompt caching to reduce latency and cost on every turn.
- **Hybrid router** — user selects role (reduces cognitive load) + AI validates each message (catches wrong-channel queries with 3-strike enforcement).
- **Read-only guard** — SQL validator blocks all DML/DDL before execution; writes only via `write_ops.py` after explicit ops approval.
- **Separation of duties** — investigator agents only read; a separate approver agent and ops human must approve before any write occurs.
- **Hallucination guard** — `format_node` overrides Claude's `dispute_found`/`credit_recommended` flags based on actual DB row counts.
- **PCI-DSS safe** — only schema goes to the Anthropic API, never actual card data.

---

## Demo scenarios

### Cardholder
Select Cardholder → *"Why was my card ending in 4242 declined yesterday?"*  
→ *"Show me all my transactions from last month"* → *"Prikaži samo odbijene"* (Serbian)

### Router in action
Select Cardholder → *"I was charged twice at Maxi yesterday"*  
→ router detects DISPUTE intent → reply *"yes"* → switches channel automatically

### Dispute
Select Dispute → *"I was charged twice at Maxi for my Visa card ending in 4242, amount 3240.50 RSD"*  
→ attach `receipts/receipt_dispute_01_maxi.png` → click Approve reversal

### Loyalty
Select Loyalty → *"My points were not added for card ending in 4242"*  
→ click Credit points

### Merchant
Select Merchant → *"Show all declined transactions on my terminals last week"*  
→ *"Sortiraj po iznosu"* → *"Export to Excel"*

---

## Known limitations

- **No merchant authentication** — merchants identify themselves by typing their terminal or merchant ID. In production this would come from an auth token. For the demo, users are trusted to provide the correct ID.
- **In-memory sessions** — session state (role, conversation history) is stored in memory only. A backend restart clears all active sessions. Acceptable for demo; production would need a persistent session store (Redis, DB).
- **RAG recall gaps** — P@3=0.625 means ~37% of relevant regulation clauses are missed on edge-case disputes (unauthorized charges, PSP liability). These scenarios have smaller representation in the policy corpus.
- **No real ops console UI** — ops approval is done via REST API (`POST /ops/decide`). A real deployment would have a dedicated ops dashboard.
- **Railway free tier sleep** — the backend may need 20–30 seconds to wake up on first request if idle. Test the deployed URL the day before any presentation.
- **Supabase free tier pause** — Supabase pauses after 7 days inactivity. Restore at supabase.com if needed.
- **Single-language OCR reliability** — Claude Vision correctly extracts most receipt fields but occasionally misreads dates. The dispute prompt uses a 60-day date window instead of exact date matching to compensate.

---

## Demo PANs

| PAN | Brand | Tier | Points |
|---|---|---|---|
| 411111\*\*\*\*\*\*4242 | VISA | SILVER | 1250 |
| 510000\*\*\*\*\*\*5555 | MASTERCARD | STANDARD | 870 |
| 989100\*\*\*\*\*\*1111 | DINACARD | GOLD | 3400 |
| 370000\*\*\*\*\*9999 | AMEX | STANDARD | 520 |
