# AIUXTester

AIUXTester is a full-stack web app for AI-driven website testing:
- Playwright (with stealth) drives browser actions
- LangGraph orchestrates agent + postmortem flows
- OpenAI / Gemini / Claude model provider support
- FastAPI backend + Vue frontend dashboard
- MariaDB or SQLite persistence for sessions, screenshots, logs, memory, and postmortems

## Features
- User auth with tiers: `free`, `basic`, `pro`
- Admin controls for user tier changes
- Agent run configuration with tier-based enforcement
- Live run stream with screenshots, actions, intent, and reasoning
- Free-form JS execution mode (LLM writes page JS to execute)
- Postmortem analysis with graceful fallback when model APIs are unavailable

## Tech Stack
- Backend: Python, FastAPI, LangGraph, Playwright, MariaDB/SQLite, Redis, RQ
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

## Run The App (Docker, Recommended)
This matches Fly architecture: `web + worker + redis + mariadb`.
```bash
docker compose up --build
```
Open `http://127.0.0.1:8080`.

Scale workers locally:
```bash
docker compose up --build --scale worker=3
```

## Run The App (Non-Docker)
Use local SQLite + inline queue for development/debugging:
```bash
source .venv/bin/activate
uvicorn main:app --reload
```
Open `http://127.0.0.1:8000`.

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
make run-worker
make test
make e2e
```

## Scenario Bank And Daily Runs

AIUXTester now supports a local scenario-bank workflow for longer-running product pressure tests.

List bundled banks:

```bash
source .venv/bin/activate
python scenario_runner.py list-banks
```

Preview the deterministic daily selection:

```bash
source .venv/bin/activate
python scenario_runner.py preview --bank publicdatawatch --date 2026-03-29 --count 6
```

Run a local daily batch against the bundled PublicDataWatch scenario bank:

```bash
source .venv/bin/activate
python scenario_runner.py run-daily \
  --bank publicdatawatch \
  --count 4 \
  --model gpt-5-mini \
  --max-steps 8 \
  --email scenario-runner@example.com
```

Notes:

- The runner uses AIUXTester's own HTTP API in-process and forces `QUEUE_MODE=inline` for local batch execution.
- Reports are written to `reports/scenario_runs/` as JSON and Markdown.
- The bundled `publicdatawatch` bank is adversarial by design: it rotates personas, surfaces, devices, and skepticism/urgency variants instead of only running a tiny fixed canary set.

## Fly.io
1. Update app name in `fly.toml` if needed.
2. Provision Redis and MariaDB (self-managed VM is fine), then capture:
   - `REDIS_URL=redis://...`
   - `DATABASE_URL=mysql://user:pass@host:3306/aiuxtester`
3. Set secrets:
```bash
fly secrets set JWT_SECRET=... OPENAI_API_KEY=... GEMINI_API_KEY=... ANTHROPIC_API_KEY=...
```
4. Deploy:
```bash
fly deploy
```
5. Scale app + worker VMs:
```bash
fly scale count app=2 worker=2
```
6. Set process-specific VM sizes if needed:
```bash
fly scale vm shared-cpu-1x --group app
fly scale vm shared-cpu-1x --group worker
```

## Notes
- `DB_BACKEND=sqlite` uses `DATABASE_PATH`; `DB_BACKEND=mariadb` uses `DATABASE_URL`.
- On startup, the app initializes schema and applies lightweight compatibility migrations for either backend.
- If configured, admin bootstrap user can be created with `ADMIN_EMAIL` and `ADMIN_PASSWORD`.
- `QUEUE_MODE=redis` uses Redis + RQ for background session jobs and Redis pub/sub for SSE streaming.
- For multi-VM app/worker scaling, use a networked DB (MariaDB in this setup).
