# Validation Set — NLP Agent for POS Transactions

## Files

| File | Purpose |
|---|---|
| `test_cases.json` | 56 test cases across 12 categories |
| `run_tests.py` | Automated test runner with accuracy report |
| `UI_TEST_PLAN.md` | Manual UI test plan (30 scenarios, copy-paste prompts) |

---

## Test case categories

| Category | Count | Description |
|---|---|---|
| `exact_match` | 5 | Find by approval code, terminal, PAN |
| `range_query` | 6 | Amount range, date range, combined |
| `status_filter` | 5 | DECLINED/APPROVED combined with other filters |
| `aggregation` | 6 | COUNT, SUM, GROUP BY queries |
| `multi_filter` | 5 | Complex combined filters |
| `multi_turn` | 3 | Multi-step refinement sessions |
| `edge_case` | 7 | No results, blocked queries, ambiguous input |
| `cardholder` | 4 | PAN isolation, declined filter, date range, Serbian |
| `merchant` | 4 | Name filter, aggregate, Excel export, Serbian daily revenue |
| `dispute` | 4 | Duplicate detection EN + SR, false positive |
| `loyalty` | 4 | Enrolled check, missing points EN + SR, non-enrolled |
| `router` | 3 | Mismatch suggest, correct-channel no-switch |

**Total: 56 test cases**

---

## Prerequisites

```bash
pip install websockets   # already installed if you ran the backend setup
```

Backend must be running (local or deployed). No other dependencies.

---

## Running the tests

### Local — seed DB fresh before testing
```bash
cd validation
python run_tests.py --seed
```
`--seed` runs `db/supabase/topup.py` then `db/supabase/demo_seed.py`.
Requires `DATABASE_URL` in your environment (same as the backend uses).

### Deployed Railway backend
```bash
python run_tests.py --url wss://pos-nlp-agent-production.up.railway.app
```

### One category only
```bash
python run_tests.py --seed --category dispute
python run_tests.py --seed --category loyalty
python run_tests.py --category multi_turn
```

### Save full JSON report
```bash
python run_tests.py --seed --output results.json
```

---

## Evaluation criteria

Each test checks two things:

**1. SQL correctness** — does the generated SQL contain the expected keywords?

**2. Result validity** — `expected_result` field:

| Value | Passes when |
|---|---|
| `has_results` | row_count > 0 |
| `no_results` | row_count == 0 |
| `zero_or_more` | any count |
| `blocked` | destructive query was not executed |
| `clarification` | agent asked for more info (no SQL or 0 rows) |
| `dispute_found` | response.dispute_found == True |
| `no_dispute` | response.dispute_found == False |
| `enrolled` | response.pan_enrolled == True |
| `not_enrolled` | response.pan_enrolled == False |
| `credit_recommended` | response.credit_recommended == True and pan_enrolled == True |
| `suggest_switch` | response.suggest_switch == True |

---

## Notes on path-specific tests

- **dispute / loyalty** require `demo_seed.py` to have run — use `--seed` or run it manually first.
- **router tests** prime the channel automatically before sending the prompt.
- **merchant Excel export** (ME-03) also checks `has_export: true` in the response alongside SQL.
