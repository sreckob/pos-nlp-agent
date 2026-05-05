# POS NLP Agent — Backend

**Deployed:** https://pos-nlp-agent-production.up.railway.app
**Auto-deploys** on push to `main`.

---

## Architecture overview

```
Browser (React UI on Vercel)
    ↕ WebSocket  /ws/{session_id}
    ↕ REST       /dispute/submit  /loyalty/submit  /ops/*
FastAPI backend (Railway)
    → LangGraph INVESTIGATOR agent
        → Router node (role + language, 3-strike channel guard)
        → Four specialist paths (SELECT only, never write):
            CARDHOLDER — own transactions by PAN
            MERCHANT   — terminal/revenue data, Excel export
            DISPUTE    — duplicate detection, Vision OCR for receipts
            LOYALTY    — uncredited points gap detection
        → SQL validator (blocks all DML/DDL)
        → SQL executor (psycopg2)
        → Response formatter (enforces flag consistency from DB)
    → pending_approvals queue  ← customer Submit enqueues here
    → APPROVER agent (approval_agent.py)
        → Runs when ops opens a pending item
        → Hard pre-checks + LLM audit decision (APPROVE|REJECT)
    → write_ops.py  ← only called after ops APPROVE
        → approve_dispute_reversal()
        → credit_loyalty_points()
    → WebSocket push  ← customer notified on ops decision
PostgreSQL on Supabase
    → transactions (100,025 rows)
    → loyalty_accounts (4 demo members)
    → pending_approvals (ops queue)
```

---

## Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, WebSocket, all REST endpoints, WS push registry |
| `agent.py` | LangGraph investigator — router + 4 paths + format node |
| `prompts.py` | System prompts for 4 investigator paths + 2 approver prompts |
| `approval_agent.py` | Ops approver LLM — reviews dispute/loyalty evidence |
| `pending_store.py` | CRUD for pending_approvals queue |
| `executor.py` | SQL executor with read-only guard + Excel export |
| `write_ops.py` | Dispute reversal + loyalty credit write operations |
| `session.py` | In-memory session store (role, history, mismatch count) |
| `logger.py` | Structured JSON logging per turn |
| `config.py` | Environment variable settings |
| `requirements.txt` | Python dependencies |

---

## API endpoints

### WebSocket
| Endpoint | Purpose |
|---|---|
| `WS /ws/{session_id}` | Main chat. Sends `{message, image?}`, receives `typing / response / error / approval_decided` |

### Customer REST
| Endpoint | Purpose |
|---|---|
| `GET /session/new` | Generate session ID |
| `GET /session/{id}/history` | Conversation history (debug) |
| `POST /dispute/submit` | Enqueue dispute reversal for ops review |
| `POST /loyalty/submit` | Enqueue loyalty credit request for ops review |
| `GET /loyalty/balance/{pan_masked}` | Read loyalty account balance |

### Operations REST (ops console)
| Endpoint | Purpose |
|---|---|
| `GET /ops/queue` | List PENDING approvals |
| `GET /ops/pending/{id}` | Detail + approver agent recommendation (cached) |
| `POST /ops/decide` | Approve or reject — triggers write_ops + customer WS push |

### Utility
| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |

---

## Setup

### 1. Environment variables

Create `.env` in `backend/files/`:
```
DATABASE_URL=postgresql://postgres.xxx:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
ANTHROPIC_API_KEY=sk-ant-your-key-here
CLAUDE_MODEL=claude-sonnet-4-5
MAX_ROWS_RETURNED=100
LOG_FILE=agent_logs.jsonl
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Apply database migration (first time only)

Paste `db/supabase/pending_approvals.sql` into Supabase SQL Editor and run.

### 4. Seed demo data
```bash
cd db/supabase
python topup.py      # adds recent transactions (run daily before testing)
python demo_seed.py  # seeds 3 dispute pairs + 2 loyalty scenarios
```

### 5. Run locally
```bash
cd backend/files
uvicorn main:app --reload --port 8000
```

---

## Quick test (without UI)

```bash
# Health check
curl http://localhost:8000/health

# New session
curl http://localhost:8000/session/new

# WebSocket chat (install wscat: npm install -g wscat)
wscat -c ws://localhost:8000/ws/test-session-1
{"message": "Show me declined transactions from yesterday"}

# Ops queue
curl http://localhost:8000/ops/queue

# View logs
cat agent_logs.jsonl
```

---

## Split-of-duties design

The system enforces separation of duties between investigation and approval:

1. **Investigator agents** only run `SELECT` queries. They identify issues and set recommendation flags. They never write to the database.
2. **Customer Submit** calls `/dispute/submit` or `/loyalty/submit` — enqueues a `PENDING` row in `pending_approvals`. No DB write yet.
3. **Approver agent** runs when ops opens the pending detail. Hard pre-checks + LLM audit decision.
4. **Ops decision** (`POST /ops/decide`) is the only path that calls `write_ops`. On APPROVE, the result is pushed to the customer's chat via WebSocket.

---

## Key design decisions

- **LangGraph** — state machine for multi-turn context and conditional routing
- **NL2SQL not RAG** — structured tabular data is more precisely served by SQL than vector search
- **Hybrid router** — user selects role + AI validates each message (3-strike channel guard)
- **Read-only guard** — `executor.py` blocks all DML/DDL; writes only via `write_ops.py`
- **PCI-DSS safe** — only schema goes to Anthropic API, never actual card data
- **In-memory sessions** — acceptable for single-instance prototype; Redis needed for horizontal scale
