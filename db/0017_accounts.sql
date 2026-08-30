-- 0017_accounts.sql
-- Multi-tenant Step 1 (ACCOUNTS): users table for Google sign-in.
-- See doc/MULTITENANT.md section 3.1.
-- Identity: google_sub is the stable key (survives email changes); email is display.
-- company_id is NULL until the user completes onboarding (creates their company).
-- Idempotent (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    google_sub    VARCHAR(255) UNIQUE NOT NULL,   -- Google's stable subject id
    email         VARCHAR(255) UNIQUE NOT NULL,
    name          VARCHAR(255),
    company_id    SMALLINT REFERENCES company_profile(id) ON DELETE SET NULL,  -- NULL until onboarding
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_company ON users (company_id);
