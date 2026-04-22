# POS NLP Agent — Backend

## Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, WebSocket endpoint |
| `config.py` | Environment variable settings |
| `session.py` | In-memory session management |
| `executor.py` | SQL executor with read-only guard |
| `agent.py` | LangGraph agent — 4 nodes |
| `prompts.py` | System prompt with DB schema |
| `logger.py` | Structured JSON logging |
| `requirements.txt` | Python dependencies |

---

## Setup

### 1. Copy .env from the database folder
```bash
cp ../db/.env .env
# Make sure it has both DATABASE_URL and ANTHROPIC_API_KEY set
```

Or create a new `.env`:
```
DATABASE_URL=postgresql://postgres.xxx:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the server
```bash
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

---

## Testing without a UI

### Health check
```bash
curl http://localhost:8000/health
```

### Get a new session ID
```bash
curl http://localhost:8000/session/new
```

### Test the WebSocket agent (install wscat first)
```bash
npm install -g wscat

# Connect with a session ID
wscat -c ws://localhost:8000/ws/test-session-1
```

Once connected, type a message and press Enter:
```
{"message": "Show me declined transactions from yesterday"}
```

Or in Serbian:
```
{"message": "Pokaži mi odbijene transakcije od juče"}
```

You will receive a JSON response with:
- `type`: "response"
- `message`: human-readable answer
- `sql`: the generated SQL query
- `rows`: array of transaction rows
- `row_count`: number of results

### Check session history
```bash
curl http://localhost:8000/session/test-session-1/history
```

### View logs
```bash
cat agent_logs.jsonl
```

---

## Example test queries

**English:**
- `Show me all declined transactions above 5000 RSD`
- `Find the transaction with approval code ABC123`
- `How many Visa contactless transactions happened last week?`
- `Show transactions at Maxi Supermarket from last month`
- `Which terminal processed the most transactions today?`

**Serbian:**
- `Pokaži mi odbijene transakcije od juče`
- `Koliko Visa beskontaktnih transakcija je bilo prošle sedmice?`
- `Prikaži transakcije na terminalu T00101`
- `Koje transakcije su iznad 10.000 dinara i odbijene?`

**Multi-turn refinement (send these one after another in same session):**
1. `Show me declined transactions from yesterday`
2. `Only those above 10000 RSD`
3. `Sort by amount descending`
4. `Which merchant had the most of these?`

---

## Project structure (full)

```
project/
├── db/
│   ├── schema.sql
│   ├── seed.py
│   ├── docker-compose.yml
│   └── .env
├── backend/          ← YOU ARE HERE
│   ├── main.py
│   ├── agent.py
│   ├── config.py
│   ├── session.py
│   ├── executor.py
│   ├── prompts.py
│   ├── logger.py
│   └── requirements.txt
└── frontend/         ← coming next
    └── ...
```
