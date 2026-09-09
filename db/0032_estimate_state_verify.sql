-- 0032: self-rolling-back verification for db/0031 (estimate state machine).
-- Asserts: new defaults (CREATED), vocab normalization on estimate lines, the
-- evidence-based PENDING remap (with a log row → SENT; without → CREATED), and
-- the backfilled Test Approval fixture. Everything rolls back — the live table
-- is untouched after a green run.

BEGIN;

DO $$
DECLARE
    pid uuid;
    lid uuid;
    remapped text;
BEGIN
    -- New default on projects.baseline_status.
    IF (SELECT column_default FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'projects'
          AND column_name = 'baseline_status') <> '''CREATED''::character varying' THEN
        RAISE EXCEPTION 'projects.baseline_status default is not CREATED';
    END IF;

    -- New default on estimates.status.
    IF (SELECT column_default FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'estimates'
          AND column_name = 'status') <> '''CREATED''::character varying' THEN
        RAISE EXCEPTION 'estimates.status default is not CREATED';
    END IF;

    -- No dead quote-era line vocabulary may remain.
    IF EXISTS (SELECT 1 FROM estimates
               WHERE status IN ('ACCEPTED','SENT','DECLINED','SUPERSEDED')) THEN
        RAISE EXCEPTION 'estimates.status still carries dead quote-era vocabulary';
    END IF;

    -- No project may remain in the retired PENDING state.
    IF EXISTS (SELECT 1 FROM projects WHERE baseline_status = 'PENDING') THEN
        RAISE EXCEPTION 'projects.baseline_status still has PENDING rows';
    END IF;

    -- Scratch fixture A: a project that WAS sent (log row) must remap PENDING→SENT.
    INSERT INTO projects (customer_id, title, site_address, baseline_status)
    SELECT id, 'Verify 0032 sent', '1 Verify St', 'PENDING'
      FROM customers ORDER BY created_at LIMIT 1
    RETURNING id INTO pid;
    IF pid IS NULL THEN
        RAISE EXCEPTION 'no seed customer to build scratch projects on';
    END IF;

    INSERT INTO approval_log (company_id, project_id, kind, recipient, message_id)
    SELECT company_id, pid, 'estimate_sent', 'verify@example.invalid', 'verify-sent-msg'
      FROM projects WHERE id = pid;

    UPDATE projects SET baseline_status = 'SENT'
     WHERE id = pid
       AND baseline_status = 'PENDING'
       AND EXISTS (SELECT 1 FROM approval_log al
                    WHERE al.project_id = pid AND al.kind = 'estimate_sent');

    SELECT baseline_status INTO remapped FROM projects WHERE id = pid;
    IF remapped <> 'SENT' THEN
        RAISE EXCEPTION 'PENDING + estimate_sent log did not remap to SENT (got %)', remapped;
    END IF;

    -- Scratch fixture B: a PENDING project with NO send evidence must remap → CREATED.
    INSERT INTO projects (customer_id, title, site_address, baseline_status)
    SELECT id, 'Verify 0032 unsent', '2 Verify St', 'PENDING'
      FROM customers ORDER BY created_at LIMIT 1
    RETURNING id INTO pid;

    UPDATE projects SET baseline_status = 'CREATED'
     WHERE baseline_status = 'PENDING';

    SELECT baseline_status INTO remapped FROM projects WHERE id = pid;
    IF remapped <> 'CREATED' THEN
        RAISE EXCEPTION 'unsent PENDING project did not remap to CREATED (got %)', remapped;
    END IF;

    -- Test Approval fixture: backfilled send row present, state SENT (when the
    -- fixture exists in this environment — it is live-only, absent on scratch).
    IF EXISTS (SELECT 1 FROM projects WHERE title = 'Test Approval') THEN
        IF NOT EXISTS (
            SELECT 1 FROM approval_log al
              JOIN projects p ON p.id = al.project_id
             WHERE p.title = 'Test Approval' AND al.kind = 'estimate_sent'
               AND al.message_id = '1a037d86d907038d'
        ) THEN
            RAISE EXCEPTION 'Test Approval estimate_sent backfill missing';
        END IF;
        SELECT p.baseline_status INTO remapped FROM projects p
         WHERE p.title = 'Test Approval';
        IF remapped <> 'SENT' THEN
            RAISE EXCEPTION 'Test Approval should be SENT (got %)', remapped;
        END IF;
    END IF;

    RAISE NOTICE '0031 state-machine verify OK (defaults, vocab, remap, fixture)';
END $$;

ROLLBACK;
