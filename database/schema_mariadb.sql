CREATE TABLE IF NOT EXISTS users (
    id            VARCHAR(64) PRIMARY KEY,
    email         VARCHAR(320) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(32) NOT NULL DEFAULT 'user',
    tier          VARCHAR(32) NOT NULL DEFAULT 'free',
    created_at    VARCHAR(64) NOT NULL,
    updated_at    VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    VARCHAR(64) NOT NULL,
    token      VARCHAR(512) NOT NULL UNIQUE,
    expires_at VARCHAR(64) NOT NULL,
    revoked    TINYINT(1) NOT NULL DEFAULT 0,
    created_at VARCHAR(64) NOT NULL,
    CONSTRAINT fk_refresh_tokens_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sessions (
    id          VARCHAR(64) PRIMARY KEY,
    user_id     VARCHAR(64) NOT NULL,
    goal        LONGTEXT NOT NULL,
    start_url   LONGTEXT NOT NULL,
    mode        VARCHAR(32) NOT NULL,
    status      VARCHAR(32) NOT NULL DEFAULT 'running',
    end_reason  LONGTEXT NULL,
    provider    VARCHAR(64) NOT NULL,
    model       VARCHAR(128) NOT NULL,
    config_json LONGTEXT NOT NULL,
    created_at  VARCHAR(64) NOT NULL,
    updated_at  VARCHAR(64) NOT NULL,
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS screenshots (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id   VARCHAR(64) NOT NULL,
    url          LONGTEXT NOT NULL,
    image_data   LONGBLOB NOT NULL,
    action_taken LONGTEXT NULL,
    step_number  INT NOT NULL,
    timestamp    VARCHAR(64) NOT NULL,
    CONSTRAINT fk_screenshots_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS html_captures (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id  VARCHAR(64) NOT NULL,
    url         LONGTEXT NOT NULL,
    html        LONGTEXT NOT NULL,
    step_number INT NOT NULL,
    timestamp   VARCHAR(64) NOT NULL,
    CONSTRAINT fk_html_captures_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS actions (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(64) NOT NULL,
    step_number   INT NOT NULL,
    action_type   VARCHAR(64) NOT NULL,
    action_params LONGTEXT NULL,
    intent        TEXT NULL,
    reasoning     LONGTEXT NULL,
    action_result LONGTEXT NULL,
    screenshot_id BIGINT NULL,
    success       TINYINT(1) NOT NULL DEFAULT 1,
    error_message LONGTEXT NULL,
    timestamp     VARCHAR(64) NOT NULL,
    CONSTRAINT fk_actions_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_actions_screenshot FOREIGN KEY (screenshot_id) REFERENCES screenshots(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_memory (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    `key`      VARCHAR(191) NOT NULL,
    `value`    LONGTEXT NOT NULL,
    updated_at VARCHAR(64) NOT NULL,
    UNIQUE KEY uq_agent_memory_session_key (session_id, `key`),
    CONSTRAINT fk_agent_memory_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS postmortem_reports (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(64) NOT NULL,
    run_analysis    LONGTEXT NULL,
    html_analysis   LONGTEXT NULL,
    recommendations LONGTEXT NULL,
    created_at      VARCHAR(64) NOT NULL,
    CONSTRAINT fk_postmortem_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS run_logs (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id  VARCHAR(64) NOT NULL,
    step_number INT NULL,
    level       VARCHAR(16) NOT NULL,
    message     LONGTEXT NOT NULL,
    details     LONGTEXT NULL,
    timestamp   VARCHAR(64) NOT NULL,
    CONSTRAINT fk_run_logs_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX IF NOT EXISTS idx_sessions_user_created_at ON sessions (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_actions_session_step ON actions (session_id, step_number);
CREATE INDEX IF NOT EXISTS idx_screenshots_session_step ON screenshots (session_id, step_number);
CREATE INDEX IF NOT EXISTS idx_html_captures_session_step ON html_captures (session_id, step_number);
CREATE INDEX IF NOT EXISTS idx_run_logs_session_id ON run_logs (session_id, id);
