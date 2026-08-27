-- 0015_device_tokens.sql
-- FCM push registration (v1.4): one row per device.
-- Consumers:
--   (a) set_briefing_time  -> pushes {type:"briefing_time_changed", ...} so the
--                             app re-schedules its local notification.
--   (b) Deadline Reminder  -> passive push nudges (statutory/lead-time/same-day).
-- Registered by the n8n `register_device` tool on app launch; the same tool
-- returns the current briefing_time so the app can schedule immediately.
-- Idempotent (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS device_tokens (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    token        VARCHAR(512) NOT NULL,
    platform     VARCHAR(20)  NOT NULL DEFAULT 'android',   -- android | ios
    device_name  VARCHAR(255),
    last_seen_at TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (token)
);

CREATE INDEX IF NOT EXISTS idx_device_tokens_platform ON device_tokens (platform);
