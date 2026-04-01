PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    tier          TEXT NOT NULL DEFAULT 'free',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL REFERENCES users(id),
    token      TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    goal        TEXT NOT NULL,
    start_url   TEXT NOT NULL,
    mode        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    end_reason  TEXT,

    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,

    config_json TEXT NOT NULL,

    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screenshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    url          TEXT NOT NULL,
    image_data   BLOB NOT NULL,
    action_taken TEXT,
    step_number  INTEGER NOT NULL,
    timestamp    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS html_captures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    url         TEXT NOT NULL,
    html        TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    timestamp   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES sessions(id),
    step_number   INTEGER NOT NULL,
    action_type   TEXT NOT NULL,
    action_params TEXT,
    intent        TEXT,
    reasoning     TEXT,
    action_result TEXT,
    screenshot_id INTEGER REFERENCES screenshots(id),
    success       INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    timestamp     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id, key)
);

CREATE TABLE IF NOT EXISTS postmortem_reports (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         TEXT NOT NULL REFERENCES sessions(id),
    run_analysis       TEXT,
    html_analysis      TEXT,
    recommendations    TEXT,
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    step_number INTEGER,
    level       TEXT NOT NULL,          -- 'debug' | 'info' | 'warning' | 'error'
    message     TEXT NOT NULL,
    details     TEXT,
    timestamp   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS competitions (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'open',  -- open | closed | running | complete
    created_by  TEXT NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS competition_entries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_id TEXT NOT NULL REFERENCES competitions(id),
    session_id     TEXT NOT NULL REFERENCES sessions(id),
    user_id        TEXT NOT NULL REFERENCES users(id),
    note           TEXT,
    submitted_at   TEXT NOT NULL,
    UNIQUE(competition_id, user_id)
);

CREATE TABLE IF NOT EXISTS competition_matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_id  TEXT NOT NULL REFERENCES competitions(id),
    round_number    INTEGER NOT NULL,
    match_number    INTEGER NOT NULL,
    entry_ids       TEXT NOT NULL,
    winner_entry_id INTEGER REFERENCES competition_entries(id),
    judge_reasoning TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | complete
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
