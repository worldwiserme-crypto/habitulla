-- ═══════════════════════════════════════════════════════════════════
-- Habit Tracker & Budget Planning Bot — Supabase PostgreSQL schema
-- Run this in Supabase SQL Editor once before starting the bot.
-- ═══════════════════════════════════════════════════════════════════

-- USERS ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              BIGINT PRIMARY KEY,
    username        VARCHAR(100),
    full_name       VARCHAR(200),
    currency        VARCHAR(3) DEFAULT 'UZS',
    timezone        VARCHAR(50) DEFAULT 'Asia/Tashkent',
    reminders_on    BOOLEAN DEFAULT TRUE,
    language        VARCHAR(5) DEFAULT 'uz',
    is_banned       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_active_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users (last_active_at DESC);

-- HABIT LOGS ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS habit_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    habit_name  VARCHAR(200) NOT NULL,
    duration    NUMERIC,
    unit        VARCHAR(20),
    logged_date DATE DEFAULT CURRENT_DATE,
    raw_text    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_habit_user_date ON habit_logs (user_id, logged_date DESC);

-- BUDGET LOGS ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS budget_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        VARCHAR(10) NOT NULL CHECK (type IN ('income', 'expense')),
    category    VARCHAR(100),
    amount      NUMERIC NOT NULL,
    currency    VARCHAR(3) DEFAULT 'UZS',
    note        TEXT,
    logged_date DATE DEFAULT CURRENT_DATE,
    raw_text    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_budget_user_date ON budget_logs (user_id, logged_date DESC);
CREATE INDEX IF NOT EXISTS idx_budget_type ON budget_logs (user_id, type);

-- SUBSCRIPTIONS -------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriptions (
    id                BIGSERIAL PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tier              VARCHAR(20) DEFAULT 'free' CHECK (tier IN ('free', 'premium')),
    plan_code         VARCHAR(10),
    started_at        TIMESTAMPTZ,
    expires_at        TIMESTAMPTZ,
    price_uzs         INTEGER,
    payment_request_id BIGINT,
    approved_by       BIGINT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions (user_id, expires_at DESC);

-- PAYMENT REQUESTS (manual approval flow) -----------------------------
CREATE TABLE IF NOT EXISTS payment_requests (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_code           VARCHAR(10) NOT NULL,
    expected_amount     INTEGER NOT NULL,
    status              VARCHAR(20) DEFAULT 'pending'
                        CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    receipt_file_id     VARCHAR(300),
    receipt_file_type   VARCHAR(20),  -- 'photo' | 'document'
    admin_message_id    BIGINT,
    admin_chat_id       BIGINT,
    approved_by         BIGINT,
    rejection_reason    TEXT,
    submitted_at        TIMESTAMPTZ DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_payment_status ON payment_requests (status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_user ON payment_requests (user_id, submitted_at DESC);

-- DAILY USAGE (rate limiting & analytics) -----------------------------
CREATE TABLE IF NOT EXISTS daily_usage (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    usage_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    log_count   INTEGER DEFAULT 0,
    ai_calls    INTEGER DEFAULT 0,
    voice_calls INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, usage_date)
);
CREATE INDEX IF NOT EXISTS idx_usage_date ON daily_usage (usage_date DESC);

-- BOT METRICS (admin panel) -------------------------------------------
CREATE TABLE IF NOT EXISTS bot_metrics (
    id          BIGSERIAL PRIMARY KEY,
    metric_type VARCHAR(50) NOT NULL,     -- 'error', 'ai_call', 'voice_call', 'report_generated'
    user_id     BIGINT,
    metadata    JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_metrics_type_date ON bot_metrics (metric_type, created_at DESC);

-- BROADCAST HISTORY ---------------------------------------------------
CREATE TABLE IF NOT EXISTS broadcasts (
    id            BIGSERIAL PRIMARY KEY,
    admin_id      BIGINT NOT NULL,
    text          TEXT NOT NULL,
    sent_count    INTEGER DEFAULT 0,
    failed_count  INTEGER DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
