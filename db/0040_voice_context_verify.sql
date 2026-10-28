-- 0040_voice_context_verify.sql
-- Self-rolling-back verification for 0039. Any failed assertion aborts the
-- transaction, so migrate.sh (ON_ERROR_STOP) exits non-zero.

BEGIN;

DO $$
DECLARE
    col_type text;
    cid smallint;
    ref_a uuid := gen_random_uuid();
    n integer;
    rejected boolean;
BEGIN
    cid := (SELECT min(id) FROM company_profile);
    IF cid IS NULL THEN RAISE EXCEPTION '0039 verify: company_profile is empty'; END IF;

    SELECT data_type INTO col_type FROM information_schema.columns
     WHERE table_schema='public' AND table_name='voice_calls' AND column_name='company_id';
    IF col_type IS NULL THEN RAISE EXCEPTION '0039 verify: voice_calls missing'; END IF;
    IF col_type <> 'smallint' THEN
        RAISE EXCEPTION '0039 verify: voice_calls.company_id should be smallint, got %', col_type;
    END IF;

    -- both status-like guards exist
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'voice_calls'::regclass AND contype = 'c') THEN
        RAISE EXCEPTION '0039 verify: voice_calls status CHECK missing';
    END IF;

    -- 1. pending row insert (what the hook does at call start)
    INSERT INTO voice_calls (company_id, call_ref) VALUES (cid, ref_a);
    SELECT count(*) INTO n FROM voice_calls WHERE call_ref = ref_a AND status = 'pending';
    IF n <> 1 THEN RAISE EXCEPTION '0039 verify: pending insert failed'; END IF;

    -- 2. duplicate call_ref must be rejected
    rejected := false;
    BEGIN
        INSERT INTO voice_calls (company_id, call_ref) VALUES (cid, ref_a);
    EXCEPTION WHEN unique_violation THEN
        rejected := true;
    END;
    IF NOT rejected THEN RAISE EXCEPTION '0039 verify: duplicate call_ref accepted'; END IF;

    -- 3. unknown status must be rejected
    rejected := false;
    BEGIN
        INSERT INTO voice_calls (company_id, call_ref, status)
        VALUES (cid, gen_random_uuid(), 'bogus');
    EXCEPTION WHEN check_violation THEN
        rejected := true;
    END;
    IF NOT rejected THEN RAISE EXCEPTION '0039 verify: bogus status accepted'; END IF;

    -- 4. FK to company_profile must be enforced
    rejected := false;
    BEGIN
        INSERT INTO voice_calls (company_id, call_ref) VALUES (9999, gen_random_uuid());
    EXCEPTION WHEN foreign_key_violation THEN
        rejected := true;
    END;
    IF NOT rejected THEN RAISE EXCEPTION '0039 verify: FK to company_profile not enforced'; END IF;

    -- 5. the report upsert (what the end-of-call branch does) flips the row
    UPDATE voice_calls
       SET status = 'reported',
           vapi_call_id = 'verify-call-id',
           ended_at = CURRENT_TIMESTAMP,
           ended_reason = 'customer-ended-call',
           duration_seconds = 12.5,
           transcript = 'AI: hi. User: hello.',
           messages = '[{"role":"assistant","message":"hi"}]'::jsonb,
           updated_at = CURRENT_TIMESTAMP
     WHERE call_ref = ref_a;
    SELECT count(*) INTO n FROM voice_calls
     WHERE call_ref = ref_a AND status = 'reported' AND vapi_call_id = 'verify-call-id';
    IF n <> 1 THEN RAISE EXCEPTION '0039 verify: report upsert did not flip the row'; END IF;

    -- 6. re-delivery of the same report is idempotent (unique vapi_call_id)
    rejected := false;
    BEGIN
        INSERT INTO voice_calls (company_id, call_ref, vapi_call_id, status)
        VALUES (cid, gen_random_uuid(), 'verify-call-id', 'reported');
    EXCEPTION WHEN unique_violation THEN
        rejected := true;
    END;
    IF NOT rejected THEN RAISE EXCEPTION '0039 verify: duplicate vapi_call_id accepted'; END IF;

    -- 7. the recent-context lookup returns the reported row and skips pending ones
    INSERT INTO voice_calls (company_id, call_ref) VALUES (cid, gen_random_uuid());
    SELECT count(*) INTO n
      FROM voice_calls
     WHERE company_id = cid AND status = 'reported'
       AND ended_at > CURRENT_TIMESTAMP - interval '7 days';
    IF n <> 1 THEN
        RAISE EXCEPTION '0039 verify: recent-context query returned % rows (expected 1 reported, pending excluded)', n;
    END IF;

    RAISE NOTICE '0039 verify: all assertions passed';
END $$;

ROLLBACK;
