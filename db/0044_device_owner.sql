-- 0044: a device token belongs to a user, not just to "the company".
--
-- Why: `device_tokens` had only company_id (NOT NULL DEFAULT 1) and the
-- registration workflow ignored the caller's session token, so EVERY phone that
-- ever registered became a company-1 push target. A second phone signed in as a
-- different account, and later signed out, kept receiving Ireh Construction's
-- invoice pushes (6 rows, all company 1, none owned by a user).
--
-- Existing rows cannot be attributed (no owner was ever recorded, and several
-- are months stale), so they are dropped: every phone re-registers on the next
-- app open (FcmService.registerAfterLogin) and comes back with an owner.

ALTER TABLE device_tokens ADD COLUMN IF NOT EXISTS user_id UUID
    REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_device_tokens_user    ON device_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_device_tokens_company ON device_tokens (company_id);

-- Legacy registrations: unowned and possibly long dead. Phones re-register.
DELETE FROM device_tokens;

-- Self-check: the column exists and no unowned rows remain.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'device_tokens' AND column_name = 'user_id'
    ) THEN
        RAISE EXCEPTION 'device_tokens.user_id missing';
    END IF;
    IF EXISTS (SELECT 1 FROM device_tokens) THEN
        RAISE EXCEPTION 'device_tokens still has rows after the reset';
    END IF;
END $$;
