# CLAUDE.md — Project Briefing
## Natural Language Prompt Agent for POS Payment Transaction Systems
**Course:** Introduction to AI Agents | **Team:** sreckob + teammates
**GitHub:** github.com/sreckob/pos-nlp-agent
**Deployed:** https://pos-nlp-agent.vercel.app (frontend) | https://pos-nlp-agent-production.up.railway.app (backend)

---

## What this project does

A conversational AI agent that allows non-technical users to query a POS payment transactions database using natural language — in Serbian or English. The system routes users through four specialist paths based on their role, maintains multi-turn conversation context, and performs write operations for dispute resolution and loyalty point crediting.

---

## Architecture overview

```
Browser (React UI on Vercel)
    ↕ WebSocket
FastAPI backend (Railway)
    → LangGraph agent
        → Router node (classifies role + validates channel)
        → Four specialist paths:
            CARDHOLDER — queries own transactions by PAN
            MERCHANT   — queries terminal/revenue data, Excel export
            DISPUTE    — receipt OCR, duplicate detection, reversal
            LOYALTY    — points check, credit top-up
        → SQL validator (read-only guard)
        → SQL executor (psycopg2)
        → Response formatter
    → Write operations (dispute reversal, loyalty credit)
PostgreSQL on Supabase
    → transactions table (100,025 rows)
    → loyalty_accounts table (4 demo members)
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, WebSocket client |
| Backend | FastAPI, uvicorn |
| AI agent | LangGraph 0.2, Anthropic SDK |
| LLM | Claude Sonnet (claude-sonnet-4-5) |
| Database | PostgreSQL on Supabase |
| Excel export | openpyxl |
| Receipt images | Pillow |
| Deployment | Railway (backend), Vercel (frontend) |
| CI/CD | Auto-deploy on git push to main |

---

## Folder structure

```
code/
├── CLAUDE.md                    ← you are here
├── backend/
│   └── files/
│       ├── main.py              ← FastAPI app, WebSocket, REST endpoints
│       ├── agent.py             ← LangGraph graph, all nodes, hybrid router
│       ├── prompts.py           ← System prompts for all four paths + router
│       ├── session.py           ← In-memory session store with mismatch tracking
│       ├── executor.py          ← SQL executor, read-only guard, Excel export
│       ├── write_ops.py         ← Dispute reversal + loyalty credit write ops
│       ├── logger.py            ← Structured JSON logging per turn
│       ├── config.py            ← Environment variable settings
│       └── requirements.txt     ← Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx              ← Main chat UI, role selector, WebSocket client
│   │   ├── api.js               ← WebSocket helper, sendMessage with image support
│   │   ├── index.js             ← React entry point
│   │   └── components/
│   │       ├── RoleSelector.jsx ← Opening screen with four role cards
│   │       ├── Message.jsx      ← Single chat bubble with path-specific panels
│   │       ├── ResultsTable.jsx ← Sortable paginated results table
│   │       ├── SqlPanel.jsx     ← Collapsible generated SQL display
│   │       ├── DisputeCard.jsx  ← Dispute recommendation + Approve/Reject buttons
│   │       ├── LoyaltyPanel.jsx ← Points balance + Credit button
│   │       └── ReceiptUpload.jsx← File upload for dispute receipts
│   ├── public/
│   │   └── index.html
│   └── package.json
├── db/
│   └── supabase/
│       ├── schema.sql           ← PostgreSQL schema (transactions + loyalty_accounts)
│       ├── seed_v2.py           ← Seeds 100k transactions + 4 loyalty accounts
│       ├── demo_seed.py         ← Seeds dispute pairs + loyalty demo transactions
│       ├── topup.py             ← Adds fresh recent transactions daily
│       └── generate_receipts.py ← Generates receipt PNG images for demo
├── validation/
│   ├── test_cases.json          ← 37 test cases across 7 categories
│   ├── run_tests.py             ← Automated test runner with accuracy report
│   └── README.md
└── receipts/                    ← Generated receipt PNG images for demo
    ├── receipt_dispute_01_maxi.png
    ├── receipt_dispute_02_nis_petrol.png
    └── receipt_dispute_03_gigatron.png
```

---

## Database schema

### transactions (100,025 rows)
```sql
transaction_id          UUID PRIMARY KEY
transaction_date        TIMESTAMP
amount                  NUMERIC(12,2)
currency                VARCHAR(3)      -- RSD, EUR, USD
status                  VARCHAR(20)     -- APPROVED, DECLINED, REVERSED, PENDING
response_code           VARCHAR(4)      -- ISO 8583
approval_code           VARCHAR(6)      -- NULL when declined
pan_masked              VARCHAR(19)     -- e.g. 411111******1111
card_brand              VARCHAR(20)     -- VISA, MASTERCARD, AMEX, DINACARD, UNIONPAY
card_type               VARCHAR(20)     -- CHIP, CONTACTLESS, MAGNETIC, MANUAL
card_class              VARCHAR(20)     -- DEBIT, CREDIT, PREPAID, CORPORATE
terminal_id             VARCHAR(20)
merchant_id             VARCHAR(20)
merchant_name           VARCHAR(100)
merchant_category       VARCHAR(50)
transaction_type        VARCHAR(20)     -- PURCHASE, REFUND, REVERSAL, CASH_ADVANCE
loyalty_points_earned   INTEGER         -- 0 for non-members
loyalty_points_credited BOOLEAN         -- FALSE until credited
dispute_status          VARCHAR(20)     -- NULL, DISPUTED, APPROVED, REJECTED
dispute_id              UUID            -- links duplicate pairs
disputed_at             TIMESTAMP
resolved_at             TIMESTAMP
```

### loyalty_accounts (4 demo members)
```sql
account_id    UUID PRIMARY KEY
pan_masked    VARCHAR(19) UNIQUE
points        INTEGER
tier          VARCHAR(20)     -- STANDARD, SILVER, GOLD
total_spent   NUMERIC(12,2)
enrolled_at   TIMESTAMP
last_updated  TIMESTAMP
```

### Demo PANs
| PAN | Brand | Tier | Points |
|---|---|---|---|
| 411111******4242 | VISA | SILVER | 1250 |
| 510000******5555 | MASTERCARD | STANDARD | 870 |
| 989100******1111 | DINACARD | GOLD | 3400 |
| 370000*****9999 | AMEX | STANDARD | 520 |

---

## Agent architecture detail

### Router node (hybrid with three-strike)
- Runs on EVERY turn
- Classifies detected role vs current channel
- If confidence >= 0.85 mismatch → suggests switch (strike 1 or 2)
- After 3 consecutive mismatches → force_reset = True → UI shows role selector
- User can type "yes"/"da" to confirm switch, "menu"/"meni" to go back

### Session state fields
```python
role           # current channel: CARDHOLDER|MERCHANT|DISPUTE|LOYALTY
pending_role   # suggested switch target
mismatch_count # consecutive mismatches (resets on correct message)
language       # sr|en (detected by router)
history        # last 20 messages for LLM context
last_sql       # previous SQL for multi-turn refinement
last_rows      # previous result set
```

### Write operations (write_ops.py)
- `approve_dispute_reversal(original_tx_id, duplicate_tx_id)` — marks duplicate as REVERSED
- `reject_dispute(duplicate_tx_id)` — marks as REJECTED
- `credit_loyalty_points(pan_masked, points)` — updates loyalty_accounts + marks transactions
- Called via REST endpoints: POST /dispute/approve, POST /dispute/reject, POST /loyalty/credit

---

## Environment variables (.env)

```
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-5
MAX_ROWS_RETURNED=100
LOG_FILE=agent_logs.jsonl
```

---

## Running locally

```bash
# Backend
cd backend/files
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm start
# Opens at http://localhost:3000

# Database top-up (run before testing)
cd db/supabase
python topup.py

# Validation tests
cd validation
pip install websockets
python run_tests.py
# or against deployed: python run_tests.py --url wss://pos-nlp-agent-production.up.railway.app
```

---

## Demo scenarios for presentation (May 23)

### Scenario 1 — Merchant (2 min)
- Select Merchant → type: "Show all declined transactions on my terminals last week"
- Follow up: "Sortiraj po iznosu" (sort by amount)
- Follow up: "Export to Excel"

### Scenario 2 — Dispute (3 min)
- Select Dispute → type: "I was charged twice at Maxi for my Visa card ending in 4242, amount 3240.50 RSD"
- Attach: receipts/receipt_dispute_01_maxi.png
- Agent finds duplicate → click Approve reversal
- Database updated: duplicate marked REVERSED

### Scenario 3 — Loyalty (2 min)
- Select Loyalty → type: "My points were not added for card ending in 4242"
- Agent finds uncredited transactions → click Credit points
- Database updated: loyalty_accounts.points increased

### Scenario 4 — Router in action (1 min)
- Select Cardholder → type: "I was charged twice at Maxi yesterday"
- Router detects DISPUTE intent → suggests switch
- Reply "yes" → switches to Dispute path automatically

---

## Current status (as of May 3 2026)

### Done ✓
- Database with all columns (dispute + loyalty)
- Four-path LangGraph agent
- Hybrid router with three-strike enforcement
- Frontend with role selector, chat, all path-specific UI
- Write operations (dispute reversal, loyalty credit)
- Receipt generator and demo images
- Deployed Railway + Vercel
- Auto-deploy on git push

### Remaining
- Run validation test suite and fix failing tests
- Update test_cases.json with dispute/loyalty test cases
- Write checkpoint report (due May 14)
- Update README.md
- Final demo rehearsal

---

## Known issues / things to watch

1. **Dispute OCR dates** — Claude Vision sometimes misreads dates from receipts.
   Fix: prompts.py DISPUTE_PROMPT uses INTERVAL '60 days' instead of exact date.
   The format_node extracts real UUIDs from DB rows, not from Claude's JSON.

2. **Session role persistence** — role is stored in memory only.
   If backend restarts, all sessions are lost. Acceptable for demo.

3. **Railway sleep** — Railway free tier may need a moment to wake up.
   Always test the deployed URL the day before presentation.

4. **Supabase pause** — Supabase free tier pauses after 7 days inactivity.
   Go to supabase.com and click Restore if this happens.

---

## Key design decisions (for presentation)

- **LangGraph over plain Python** — state machine handles multi-turn context and conditional routing cleanly
- **NL2SQL not RAG** — structured data → SQL is more precise than vector search
- **No vector DB** — schema fits in system prompt (400 tokens), pgvector not needed
- **Hybrid router** — user selects role (reduces cognitive load) + AI validates each message (catches mistakes)
- **PCI-DSS safe** — only schema goes to Anthropic API, never actual card data
- **Read-only guard** — SQL validator blocks all destructive statements before execution
