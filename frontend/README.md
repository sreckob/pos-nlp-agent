# POS NLP Agent — Frontend

## Setup

### 1. Install Node.js (if not installed)
Download from https://nodejs.org — choose the LTS version.

Verify:
```bash
node --version   # should be 18+
npm --version
```

### 2. Install dependencies
```bash
cd frontend
npm install
```

### 3. Start the development server
Make sure the FastAPI backend is running on port 8000 first, then:
```bash
npm start
```

Opens automatically at http://localhost:3000

---

## Features

- Chat interface with message history
- Results rendered as sortable, paginated table
- Collapsible SQL panel showing generated query
- Multi-turn refinement — follow-up questions use session context
- Serbian and English language support
- Example query chips on empty state
- Connection status indicator
- New session button to start fresh

---

## Environment variables

Create a `.env` file in the frontend folder for production deployment:

```
REACT_APP_WS_URL=wss://your-backend.railway.app
```

For local development the proxy in `package.json` handles routing to `localhost:8000`.

---

## Deploying to Vercel

```bash
npm run build
# then drag the build/ folder to vercel.com
# or connect your GitHub repo to Vercel
```

Set environment variable in Vercel dashboard:
```
REACT_APP_WS_URL=wss://your-backend.railway.app
```
