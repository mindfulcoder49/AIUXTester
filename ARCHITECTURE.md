# AIUXTester — Architecture Plan (Expanded)

## 1) Overview

AIUXTester is a Python application that runs an agentic AI to interact with websites like a human user. The agent receives a URL and a goal (e.g., "Make a user account"), then iteratively chooses actions based on visual observations (screenshots). Each action and resulting screenshot is streamed to a live UI so a human can watch the agent's progress and stop it if needed. The system stores all session artifacts (screenshots, actions, HTML, memory, post-mortem reports) per user in SQLite for later review.

This revision adds:

- User accounts (register/login), with `admin` and `user` roles.
- Tiered access: `free`, `basic`, `pro`.
- Provider/model selection per session: OpenAI, Google Gemini, Anthropic Claude.
- Tier-based configuration gating (free/basic/pro configuration access).
- Admin tools for user tier management.

---

## 2) System Goals and Non-Goals

### Goals

- Let users run autonomous web interaction tests and observe them live.
- Provide deterministic session artifacts for debugging and review.
- Support multiple LLM providers and user-selected models.
- Provide robust configuration controls with tier-based access.
- Provide a post-mortem analysis pipeline that uses run state + page HTML.

### Non-Goals

- Provide full human-like browsing (the agent only uses allowed actions).
- Support multi-agent concurrency inside a single session (one agent per session).
- Replace manual QA; this is a supplement for UX and flow testing.

---

## 3) High-Level Architecture

```
Browser (Playwright + stealth)
      ↑           ↓
Agent Graph (LangGraph)  ↔  LLM Provider (OpenAI/Gemini/Claude)
      ↑           ↓
Database (SQLite) ←→ FastAPI API ←→ UI (SSE for live steps)
```

Data flow summary:

1. User creates session via UI (URL, goal, provider, model, config).
2. API validates permissions, saves session + config snapshot.
3. Background task starts LangGraph agent.
4. Each step:
   - Agent sees screenshot and state.
   - LLM selects next action via structured output.
   - Action runs in Playwright.
   - Screenshot + HTML captured and persisted.
   - SSE pushes action + screenshot to UI.
5. When session ends, post-mortem agent runs in two phases.
6. Reports saved to DB and visible to user (or admin).

---

## 4) Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| AI Orchestration | `langgraph` | Graph-based control flow, stateful runs |
| LLM Providers | `openai`, `google-generativeai`, `anthropic` | Provider-specific clients with uniform interface |
| Browser | `playwright`, `playwright-stealth` | Stealth evasion, control of viewport |
| Backend | `FastAPI`, `uvicorn` | REST + SSE |
| Auth | JWT, bcrypt (passlib) | Access + refresh tokens |
| Database | SQLite + `aiosqlite` | Local storage, async queries |
| Validation | `pydantic v2` | Input validation, structured outputs |
| Config | `.env` + `config.py` | Provider keys, tier limits |

---

## 5) Repository Structure

```
AIUXTester/
├── main.py
├── requirements.txt
├── .env
├── config.py
│
├── database/
│   ├── schema.sql
│   ├── db.py
│   └── queries.py
│
├── auth/
│   ├── models.py
│   ├── security.py
│   └── dependencies.py
│
├── llm/
│   ├── registry.py
│   ├── openai_client.py
│   ├── gemini_client.py
│   └── claude_client.py
│
├── browser/
│   ├── manager.py
│   └── actions.py
│
├── agent/
│   ├── state.py
│   ├── prompts.py
│   ├── test_graph.py
│   ├── postmortem_graph.py
│   └── nodes/
│       ├── initialize.py
│       ├── think.py
│       ├── execute.py
│       ├── capture.py
│       ├── check_status.py
│       ├── pm_analyze_run.py
│       └── pm_analyze_html.py
│
├── ui/
│   ├── app.py
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── app.js
│       └── style.css
│
└── utils/
    ├── loop_detector.py
    └── image.py
```

---

## 6) Database Schema (Detailed)

### Users and Auth

```sql
CREATE TABLE users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',   -- 'user' | 'admin'
    tier          TEXT NOT NULL DEFAULT 'free',   -- 'free' | 'basic' | 'pro'
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE refresh_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL REFERENCES users(id),
    token      TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
```

### Sessions

```sql
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    goal        TEXT NOT NULL,
    start_url   TEXT NOT NULL,
    mode        TEXT NOT NULL,             -- 'desktop' | 'mobile'
    status      TEXT NOT NULL DEFAULT 'running',
    end_reason  TEXT,

    provider    TEXT NOT NULL,             -- 'openai' | 'gemini' | 'claude'
    model       TEXT NOT NULL,

    config_json TEXT NOT NULL,             -- frozen config snapshot (JSON)

    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

### Screenshots

```sql
CREATE TABLE screenshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    url          TEXT NOT NULL,
    image_data   BLOB NOT NULL,
    action_taken TEXT,
    step_number  INTEGER NOT NULL,
    timestamp    TEXT NOT NULL
);
```

### HTML Captures (Not visible to test agent)

```sql
CREATE TABLE html_captures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    url         TEXT NOT NULL,
    html        TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    timestamp   TEXT NOT NULL
);
```

### Actions

```sql
CREATE TABLE actions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES sessions(id),
    step_number   INTEGER NOT NULL,
    action_type   TEXT NOT NULL,
    action_params TEXT,
    reasoning     TEXT,
    screenshot_id INTEGER REFERENCES screenshots(id),
    success       INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    timestamp     TEXT NOT NULL
);
```

### Agent Memory

```sql
CREATE TABLE agent_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id, key)
);
```

### Post-mortem Reports

```sql
CREATE TABLE postmortem_reports (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         TEXT NOT NULL REFERENCES sessions(id),
    run_analysis       TEXT,
    html_analysis      TEXT,
    recommendations    TEXT,  -- JSON
    created_at         TEXT NOT NULL
);
```

---

## 7) Auth and User Management

### Registration Flow

1. User submits email + password.
2. Password hashed via bcrypt.
3. User created with `role='user'` and `tier='free'`.
4. JWT access + refresh token returned.

### Login Flow

1. User submits credentials.
2. Password verified.
3. Access + refresh token issued.

### Roles and Tier Management

- `admin` role can:
  - List all users.
  - Change a user's `tier`.
  - View all sessions and post-mortems.
- `user` role can only access their own sessions.

---

## 8) LLM Provider Abstraction

### Uniform Interface

All provider clients implement:

```python
async def generate_action(
    *,
    system_prompt: str,
    user_prompt: str,
    images: list[bytes],
    schema: type[BaseModel],
    temperature: float,
) -> BaseModel
```

### Provider Registry

`llm/registry.py` provides:

- Provider availability
- Allowed model lists per provider
- Tier-based model gating
- Max tokens and context size constraints

### Example Model Access Policy

```
free:  OpenAI gpt-4o-mini | Gemini 1.5 Flash | Claude Haiku
basic: OpenAI gpt-4o-mini, gpt-4o | Gemini 1.5 Flash, 1.5 Pro | Claude Haiku, Sonnet
pro:   All available models
```

---

## 9) Configuration System

### Config Snapshot
Each session stores a JSON snapshot of settings to ensure reproducibility. This snapshot is used by the agent and post-mortem pipeline.

### Config Categories and Access

#### Free Tier
- `mode`
- `max_steps`
- `stop_on_first_error`

#### Basic Tier
- All Free settings
- `max_history_actions`
- `loop_detection_enabled`
- `loop_detection_window`

#### Pro Tier
- All Free + Basic settings
- `loop_detection_rules`
- `memory_injection_format`
- `screenshot_quality`
- `action_retry_policy`
- `postmortem_depth`
- `custom_system_prompt_preamble`

### Enforcement

- UI only exposes settings allowed for the tier.
- Server validates tier permissions at session creation.
- `registry.py` enforces model access.

---

## 10) Agent State

### State Fields (Expanded)

```python
class AgentState(TypedDict):
    session_id: str
    user_id: str
    goal: str
    start_url: str
    mode: Literal["desktop", "mobile"]

    provider: str
    model: str
    tier: Literal["free", "basic", "pro"]
    config: dict

    current_url: str
    current_screenshot: str
    current_screenshot_id: int
    current_step: int

    memory: dict[str, str]
    action_history: list[ActionRecord]
    recent_action_fingerprints: list[str]
    pages_visited: list[str]

    status: Literal["running", "completed", "failed", "stopped", "loop_detected"]
    end_reason: Optional[str]
    next_action: Optional[dict]

    postmortem_run_analysis: Optional[str]
    postmortem_html_analysis: Optional[str]
    postmortem_recommendations: Optional[str]
```

---

## 11) Agent Action Schema

Agent uses structured output to select one of these actions:

- `scroll_down`
- `scroll_up`
- `swipe_left`
- `swipe_right`
- `click`
- `click_and_drag`
- `type`
- `navigate`
- `save_to_memory`
- `finish`
- `fail`

Each action has a strict param schema to ensure deterministic execution.

---

## 12) LangGraph Control Flow

### Test Agent Graph

```
START
  ↓
[initialize]
  ↓
[think] → [execute] → [capture] → [check_status]
  ↑__________________________________________
  ↓
[teardown]
  ↓
[postmortem_graph]
  ↓
END
```

### Post-mortem Graph

```
START
  ↓
[pm_analyze_run]
  ↓
[pm_analyze_html]
  ↓
[save_postmortem]
  ↓
END
```

---

## 13) UI and UX Details

### Main Views

- Login/Register
- Session Dashboard
- New Session Wizard
- Live Session View
- Post-mortem View
- Admin User Management

### Live View

- Shows step-by-step:
  - Action just taken
  - Screenshot after action
  - URL
- "Stop" button halts the session immediately.

---

## 14) Security and Compliance

- Password hashing with bcrypt.
- JWT access tokens short-lived, refresh tokens stored in DB.
- Per-user access control in all queries.
- Provider API keys stored only in environment.

---

## 15) Implementation Order

1. Schema + query layer
2. Auth + tier enforcement
3. LLM registry and provider clients
4. Browser layer
5. Agent graph
6. UI + SSE
7. Post-mortem
8. Admin panel

---

This expanded architecture plan provides full detail for all major subsystems and how they interconnect.
