-- 0030: self-rolling-back verification for db/0029 (approval_log).
-- Inserts a scratch row against a seeded project, checks shape/FK, then
-- ROLLBACK so the live table is untouched after a green run.

BEGIN;

DO $$
DECLARE
    pid uuid;
    lid uuid;
BEGIN
    -- The table exists with the expected columns.
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'approval_log'
          AND column_name IN ('id','company_id','project_id','kind','recipient',
                              'message_id','note','created_at')) <> 8 THEN
        RAISE EXCEPTION 'approval_log missing expected columns';
    END IF;

    SELECT id INTO pid FROM projects ORDER BY created_at LIMIT 1;
    IF pid IS NULL THEN
        RAISE EXCEPTION 'no seed project to verify against';
    END IF;

    INSERT INTO approval_log (company_id, project_id, kind, recipient, message_id, note)
    SELECT p.company_id, p.id, 'estimate_sent', 'verify@example.invalid',
           'verify-msg-id', 'verification row'
      FROM projects p WHERE p.id = pid
    RETURNING id INTO lid;

    IF lid IS NULL THEN
        RAISE EXCEPTION 'approval_log insert returned no id';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM approval_log WHERE id = lid AND kind = 'estimate_sent'
    ) THEN
        RAISE EXCEPTION 'approval_log row not readable';
    END IF;

    RAISE NOTICE 'approval_log verify OK (scratch row %)', lid;
END $$;

ROLLBACK;
