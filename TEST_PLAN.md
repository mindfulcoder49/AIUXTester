# AIUXTester Test Plan (API‑Key‑Free)

This test plan verifies all major features described in `ARCHITECTURE.md` without requiring API keys or consuming LLM tokens. It relies on mocks and fakes for LLM providers and Playwright.

## Principles

- No real network calls to LLM providers.
- No real Playwright browser automation.
- Deterministic test data and outputs.
- SQLite temp DB per test session.

## Coverage Areas

### 1) Database Schema & Queries
- Verify schema creation and constraints
- CRUD for:
  - users
  - refresh_tokens
  - sessions
  - screenshots
  - html_captures
  - actions
  - agent_memory
  - postmortem_reports

### 2) Authentication & RBAC
- Register → Login → /me
- Refresh token issuance + revocation
- Admin permissions enforced
- Tier updates reflected in /me

### 3) Tier‑Based Config Gating
- Free tier rejects basic/pro settings
- Basic tier rejects pro settings
- Pro tier allows all config keys
- Stored config snapshot is filtered by tier

### 4) Provider/Model Gating
- /models returns allowed models for tier
- Create session with invalid model rejected
- Create session with allowed model accepted

### 5) Session Lifecycle (API)
- POST /sessions creates session
- SSE stream emits steps/status/postmortem
- POST /sessions/{id}/stop updates status

### 6) Agent Graph (Unit)
- Think node respects memory/history limits
- Execute node handles finish/fail/save_to_memory
- Capture node persists screenshot/html/action
- Loop detection triggers correctly
- stop_on_first_error halts run
- max_steps enforcement

### 7) Postmortem Graph (Unit)
- Run analysis output saved
- HTML analysis output saved
- Postmortem SSE event emitted

### 8) Access Control
- Users cannot access other users’ sessions
- Screenshot endpoint protected
- SSE stream requires authorization

## Test Infrastructure

- `pytest` + `pytest-asyncio`
- `httpx` ASGI client for FastAPI
- Monkeypatch LLM providers to return deterministic `AgentAction` and postmortem outputs
- Monkeypatch Playwright/BrowserManager to return static screenshots/HTML
- Use a temp SQLite DB per test session

## Files

- `tests/conftest.py`: fixtures (temp DB, app client, auth helpers)
- `tests/test_db.py`: database CRUD
- `tests/test_auth.py`: registration/login/refresh/RBAC
- `tests/test_tiers.py`: tier config validation
- `tests/test_models.py`: model registry access
- `tests/test_sessions_api.py`: session endpoints + stop
- `tests/test_streaming.py`: SSE stream auth
- `tests/test_agent_graph.py`: agent unit tests with fakes
- `tests/test_postmortem.py`: postmortem unit tests

## Notes

- No API keys are required to run these tests.
- LLM and Playwright are mocked.
- End‑to‑end integration can be added later once tokens are available.
