# Validation Set — NLP Agent for POS Transactions

## Files

| File | Purpose |
|---|---|
| `test_cases.json` | 37 test cases across 6 categories |
| `run_tests.py` | Automated test runner with accuracy report |

---

## Test case categories

| Category | Count | Description |
|---|---|---|
| `exact_match` | 5 | Find by approval code, terminal, PAN |
| `range_query` | 6 | Amount range, date range, combined |
| `status_filter` | 5 | DECLINED/APPROVED, combined with other filters |
| `aggregation` | 6 | COUNT, SUM, GROUP BY queries |
| `multi_filter` | 5 | Complex combined filters |
| `multi_turn` | 3 | Multi-step refinement sessions (9 turns total) |
| `edge_case` | 7 | No results, blocked queries, ambiguous input |

**Total: 37 test cases, 43 individual prompts**

---

## Running the tests

### Prerequisites
```bash
pip install websockets
```

### Test local backend (make sure uvicorn is running)
```bash
python run_tests.py
```

### Test deployed Railway backend
```bash
python run_tests.py --url wss://pos-nlp-agent-production.up.railway.app
```

### Test one category only
```bash
python run_tests.py --category multi_turn
python run_tests.py --category edge_case
```

### Save full report
```bash
python run_tests.py --output results.json
```

---

## Example output

```
Running 37 test cases...
  [EX-01] Find the transaction with approval code A1B2C3... ✓
  [EX-02] Show me all transactions from terminal T0101... ✓
  [ST-01] Show me all declined transactions... ✓
  [ED-05] Delete all transactions... ✓
  ...

==================================================
VALIDATION RESULTS — 2026-04-23
==================================================
Total:    37
Passed:   33
Failed:   4
Accuracy: 89.2%

By category:
  exact_match          ██████████  5/5   (100%)
  range_query          █████████░  5/6   (83.3%)
  status_filter        ██████████  5/5   (100%)
  aggregation          █████████░  5/6   (83.3%)
  multi_filter         ██████████  5/5   (100%)
  multi_turn           ████████░░  2/3   (66.7%)
  edge_case            █████████░  6/7   (85.7%)
==================================================
```

---

## Evaluation criteria per test case

Each test case checks two things:

1. **SQL correctness** — does the generated SQL contain the expected keywords?
   - e.g. for "declined Visa transactions" → SQL must contain `DECLINED` and `VISA`

2. **Result validity** — does the result match the expected outcome?
   - `has_results` — at least one row returned
   - `no_results` — zero rows (for impossible queries)
   - `zero_or_more` — any count is acceptable
   - `blocked` — destructive query was not executed
   - `clarification` — agent asked for clarification

---

## Using results in the checkpoint report

Run the tests and include in your report:
- Overall accuracy percentage
- Accuracy by category table
- 2-3 example failures with analysis of why they failed
- Comparison between Serbian and English prompt accuracy
