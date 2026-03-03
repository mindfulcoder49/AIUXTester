# AIUXTester

AIUXTester is a full-stack web app for AI-driven website testing:
- Playwright (with stealth) drives browser actions
- LangGraph orchestrates agent + postmortem flows
- OpenAI / Gemini / Claude model provider support
- FastAPI backend + Vue frontend dashboard
- SQLite persistence for sessions, screenshots, logs, memory, and postmortems

## Features
- User auth with tiers: `free`, `basic`, `pro`
- Admin controls for user tier changes
- Agent run configuration with tier-based enforcement
- Live run stream with screenshots, actions, intent, and reasoning
- Coordinate-action preview frames (click/swipe/drag markers)
- Postmortem analysis with graceful fallback when model APIs are unavailable

## Tech Stack
- Backend: Python, FastAPI, LangGraph, Playwright, SQLite
- Frontend: Vue 3 + Vue Router
- Tests: Pytest (backend), Vitest (frontend)

## Requirements
- Python 3.12+
- Node.js 18+
- Chromium installed for Playwright runs

## Setup
1. Create and activate a virtual environment.
```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install Python dependencies.
```bash
pip install -r requirements.txt
```

3. Install frontend dependencies.
```bash
npm install
```

4. Create `.env` from the example and fill secrets/keys.
```bash
cp .env.example .env
```

## Run The App
Start backend (serves API + Vue static app):
```bash
source .venv/bin/activate
uvicorn main:app --reload
```

Open:
- `http://127.0.0.1:8000`

## Run Tests
Backend:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest -q
```

Frontend:
```bash
npm run test:ui
```

## Makefile Shortcuts
```bash
make setup
make run
make test
make e2e
```

## Docker
Build:
```bash
docker build -t aiuxtester:local .
```

Run:
```bash
docker run --rm -p 8080:8080 --env-file .env -v "$(pwd)/data:/data" aiuxtester:local
```

## Fly.io
1. Update app name in `fly.toml` if needed.
2. Create persistent volume once:
```bash
fly volumes create aiuxtester_data --size 5 --region iad
```
3. Set secrets:
```bash
fly secrets set JWT_SECRET=... OPENAI_API_KEY=... GEMINI_API_KEY=... ANTHROPIC_API_KEY=...
```
4. Deploy:
```bash
fly deploy
```

## Notes
- The database file defaults to `aiuxtester.db`.
- On startup, the app initializes DB schema and applies lightweight compatibility migrations.
- If configured, admin bootstrap user can be created with `ADMIN_EMAIL` and `ADMIN_PASSWORD`.
