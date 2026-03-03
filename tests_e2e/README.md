# E2E Test Layer

This suite runs true end-to-end tests with:

- Real OpenAI model calls (`gpt-5-mini` by default)
- Real Playwright browser execution
- Real agent/postmortem graph flow

## Prerequisites

1. Fill `.env` from `.env.example`.
2. Ensure these values are set:
   - `OPENAI_API_KEY`
   - `ADMIN_EMAIL`
   - `ADMIN_PASSWORD`
3. Install Playwright browser binaries:

```bash
.venv/bin/python -m playwright install chromium
```

## Run

```bash
E2E_RUN=1 PYTHONPATH=. .venv/bin/pytest -q tests_e2e
```

## Notes

- This suite is opt-in and skipped unless `E2E_RUN=1`.
- It consumes API tokens and can take a few minutes.
- It uses an isolated temporary SQLite DB per test run.
