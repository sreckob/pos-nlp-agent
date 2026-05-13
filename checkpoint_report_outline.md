# Checkpoint Report — Outline
## NLP Prompting for Payment Systems
**Team:** sreckob + teammates | **Due:** May 14, 23:59

---

## 1. Project Description & Current Status

**What it is (2-3 sentences):**
- Conversational AI agent that lets non-technical users query a POS payment transactions
  database using natural language (Serbian or English)
- Routes users through four specialist paths based on role: Cardholder, Merchant,
  Dispute, Loyalty
- Implements split-of-duties: investigator agents (read-only) + operations approver
  (gated writes) — mirroring real banking separation of duties

**Current status:**
- Fully deployed: backend on Railway, frontend on Vercel
- URL: https://pos-nlp-agent.vercel.app
- Validated with automated test suite; security hardening completed
- Multi-LLM abstraction layer implemented (configurable: Claude / Gemini / Mistral)

---

## 2. Data

**Source & volume:**
- PostgreSQL database on Supabase
- 100,025 transaction rows (seeded + daily top-up)
- 4 loyalty accounts (demo members with realistic point balances)
- 1 pending_approvals queue table (ops workflow)
- 3 seeded dispute pairs + 2 loyalty gap scenarios for demo

**Schema highlights (key columns):**
- transactions: transaction_id, pan_masked, amount, currency, status, merchant_name,
  merchant_category, card_brand, card_type, dispute_status, loyalty_points_earned, …
- loyalty_accounts: pan_masked, points, tier, total_spent
- pending_approvals: type, payload (JSONB), status, customer_session_id, agent_recommendation

**Storage format:** PostgreSQL (structured, indexed) — no chunking or vectorisation needed
for the transactional query paths

**Preprocessing decision:**
- Deliberate choice of NL2SQL over RAG for structured tabular data
- Schema (~400 tokens) fits in context window — pgvector not needed for core queries
- The LLM receives the full schema as a system prompt and generates PostgreSQL SELECT
  queries directly; psycopg2 executes them

---

## 3. Pipeline Architecture

**Overview diagram (describe or include the ASCII diagram from CLAUDE.md):**

```
Browser (React UI — Vercel)
    ↕ WebSocket + REST
FastAPI backend (Railway)
    → LangGraph Investigator Agent
        → Router node (hybrid: role classification + 3-strike channel guard)
        → Four specialist paths (SELECT only, never write):
            CARDHOLDER — own transactions by PAN
            MERCHANT   — terminal/revenue data + Excel export
            DISPUTE    — duplicate detection, Vision OCR for receipts
            LOYALTY    — uncredited points gap detection
        → SQL validator (read-only guard)
        → SQL executor (psycopg2 + connection pool)
        → Response formatter
    → pending_approvals queue (customer Submit → enqueue)
    → Approver Agent (runs when ops opens detail)
        → Hard pre-checks + LLM audit decision (APPROVE | REJECT)
    → write_ops.py (only called after ops APPROVE via /ops/decide)
    → WebSocket push (customer notified on decision)
PostgreSQL on Supabase
```

**Key design decisions (each worth a sentence):**
- LangGraph over plain Python: state machine handles multi-turn context cleanly
- Hybrid router: user selects role (reduces cognitive load) + AI validates each message
- NL2SQL not RAG: structured tabular data → SQL is more precise than vector search
- Separation of duties: investigator agents have read-only DB access; writes only
  after human approval via the ops console
- Multi-LLM abstraction: LiteLLM wrapper allows swapping Claude/Gemini/Mistral
  via a single env var (LLM_MODEL) without code changes

**Tech stack:** FastAPI · LangGraph · Anthropic Claude (claude-sonnet-4-6) · LiteLLM ·
psycopg2 · React 18 · WebSocket · PostgreSQL (Supabase) · Railway · Vercel

---

## 4. Evaluation Approach

**Validation set:**
- 56 hand-crafted test cases across 12 categories
- Categories: exact_match, range_query, status_filter, aggregation, multi_filter,
  multi_turn, edge_case, cardholder, merchant, dispute, loyalty, router
- Each test specifies: prompt, channel context (router_current_channel),
  expected SQL keywords, expected result criteria

**Metrics:**
- **SQL accuracy:** does generated SQL contain expected keywords (table names, operators,
  values)?
- **Result accuracy:** does the response meet path-specific criteria (has_results,
  dispute_found, credit_recommended, suggest_switch, etc.)?
- **SQL consistency:** % of tests that produce identical SQL across N repeated runs
  at the same temperature — measures model variance

**Test runner:**
- `validation/run_tests.py` — WebSocket-based, seeds DB before run, supports
  category filtering and temperature labelling
- `validation/tune_temperature.py` — automated sweep across temperature settings,
  starts/stops uvicorn subprocesses, reports mean accuracy + consistency per setting

**Important distinction:**
- Tests measure first-shot accuracy (single turn)
- The system is designed for multi-turn conversations: agents ask for missing info
  (card number, merchant ID, approximate date) and succeed on subsequent turns
- First-shot accuracy underestimates real-world task completion rate

---

## 5. Preliminary Results

**Temperature sweep (Claude claude-sonnet-4-6):**

| Setting | Specialist temp | Mean accuracy | SQL consistency |
|---|---|---|---|
| baseline | 0.0 | 39.3% | 64.3% |
| low | 0.1 | 42.3% | 67.9% |
| **medium** | **0.3** | **44.6%** | **75.0%** |
| high | 0.5 | 25.6% | 57.1% |

→ Recommended: temperature 0.3 for specialist nodes, 0.0 for router and approver

**Path-specific highlights:**
- Cardholder path: 100% (4/4) — full context provided in prompts
- Router mismatch detection: 100% (3/3)
- Dispute detection: 50% (2/4) — requires exact seeded duplicate pairs
- Loyalty gap detection: 25% (1/4) — improvement underway

**Analysis:**
- 0.3 wins on both accuracy AND consistency simultaneously — unusual; suggests
  Claude at 0.0 is too rigid for NL2SQL (slight variance helps SQL phrasing)
- High (0.5) catastrophically unstable — range 5.4–39.3% across runs
- Many first-shot failures are correct clarification requests, not errors

**Qualitative validation (live demo tests):**
- Full dispute flow (submit → ops review → approve → customer push): working end-to-end
- Loyalty gap detection + credit: working end-to-end
- Router 3-strike mismatch enforcement: working
- Serbian / English bilingual responses: working

---

## 6. Open Questions & Next Steps

**Open:**
- RAG implementation: historical dispute case similarity for the approver agent is
  designed (metadata-filtered retrieval from past decided cases) but not yet
  implemented — planned before demo
- Gemini/Mistral comparison: free tier quota exhausted during initial sweep;
  comparison deferred
- Test accuracy gap: path-specific tests that require exact seeded dispute pairs
  are environment-sensitive; reproducibility depends on demo_seed.py state

**Planned before demo (May 23):**
1. RAG — approver agent retrieves similar past cases for better audit summaries
2. Final demo rehearsal with all 4 scenarios from CLAUDE.md
3. Demo seed verification (topup.py + demo_seed.py day before)

**No current blockers** — system is fully deployed and functional.
