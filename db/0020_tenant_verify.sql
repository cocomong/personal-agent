-- 0020_tenant_verify.sql
-- Verifies Step 2 (tenant columns) invariants. Plain SQL, self-contained,
-- self-rolled-back (like 0002 / 0013). Run after 0019.
--
-- Asserts:
--   (a) company_id exists and is NOT NULL on all 7 directly-scoped tables
--   (b) company_profile.id is sequence-driven (multi-row ready), the old
--       id=1 CHECK is gone, and the 4 per-company unique indexes exist
--   (c) duplicates WITHIN a company are rejected (email / worker_code /
--       invoice_number / payroll period)  -> unique_violation expected
--   (d) the same values ACROSS companies are allowed (proves the uniques are
--       truly per-company, not just renamed)  -> company 2 created via the
--       sequence, duplicate customer email + worker code inserted against it
--
-- Note: (d) advances company_profile_id_seq (sequences are non-transactional,
-- so the ROLLBACK does not rewind it). Company ids may show harmless gaps.

BEGIN;

-- (a) tenant columns present + NOT NULL
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['customers','projects','workers','payroll_runs',
                             'schedule_items','device_tokens','invoices']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = t
              AND column_name = 'company_id'
              AND is_nullable = 'NO'
        ) THEN
            RAISE EXCEPTION 'VERIFY FAIL (tenant columns): %.company_id missing or nullable', t;
        END IF;
    END LOOP;
END $$;

-- (b) company_profile multi-row plumbing + re-scoped uniques present
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'company_profile_id_check') THEN
        RAISE EXCEPTION 'VERIFY FAIL (company_profile): id=1 CHECK still present';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'company_profile'
          AND column_name = 'id'
          AND column_default LIKE '%company_profile_id_seq%'
    ) THEN
        RAISE EXCEPTION 'VERIFY FAIL (company_profile): id default is not the sequence';
    END IF;
    IF (SELECT COUNT(*) FROM pg_indexes
        WHERE indexname IN ('uq_customers_company_email',
                            'uq_workers_company_worker_code',
                            'uq_invoices_company_invoice_number',
                            'uq_payroll_runs_company_period')) <> 4 THEN
        RAISE EXCEPTION 'VERIFY FAIL (tenant uniques): expected 4 per-company unique indexes';
    END IF;
END $$;

-- (c) duplicates within company 1 are rejected
DO $$
BEGIN
    INSERT INTO customers (name, email, company_id)
    VALUES ('Verify Dup', 'tenant-dup-cust@example.com', 1);
    BEGIN
        INSERT INTO customers (name, email, company_id)
        VALUES ('Verify Dup 2', 'tenant-dup-cust@example.com', 1);
        RAISE EXCEPTION 'VERIFY FAIL (tenant customers): duplicate email within a company accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;  -- expected 23505
    END;
END $$;

DO $$
BEGIN
    INSERT INTO workers (company_id, worker_code, name, hourly_rate)
    VALUES (1, 'W-VERIFY', 'Verify Worker', 30.00);
    BEGIN
        INSERT INTO workers (company_id, worker_code, name, hourly_rate)
        VALUES (1, 'W-VERIFY', 'Verify Worker Dup', 30.00);
        RAISE EXCEPTION 'VERIFY FAIL (tenant workers): duplicate worker_code within a company accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;  -- expected 23505
    END;
END $$;

DO $$
BEGIN
    INSERT INTO invoices (company_id, invoice_number, invoice_type, amount_due,
                          net_amount, due_date)
    VALUES (1, 'INV-TENANT-VERIFY', 'PROGRESS_BILLING', 100.00, 100.00,
            CURRENT_DATE + INTERVAL '30 day');
    BEGIN
        INSERT INTO invoices (company_id, invoice_number, invoice_type, amount_due,
                              net_amount, due_date)
        VALUES (1, 'INV-TENANT-VERIFY', 'PROGRESS_BILLING', 100.00, 100.00,
                CURRENT_DATE + INTERVAL '30 day');
        RAISE EXCEPTION 'VERIFY FAIL (tenant invoices): duplicate invoice_number within a company accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;  -- expected 23505
    END;
END $$;

DO $$
BEGIN
    INSERT INTO payroll_runs (company_id, period_start, period_end, status)
    VALUES (1, '2026-02-01', '2026-02-28', 'DRAFT');
    BEGIN
        INSERT INTO payroll_runs (company_id, period_start, period_end, status)
        VALUES (1, '2026-02-01', '2026-02-28', 'DRAFT');
        RAISE EXCEPTION 'VERIFY FAIL (tenant payroll): duplicate period within a company accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;  -- expected 23505
    END;
END $$;

-- (d) the same values ACROSS companies are allowed
DO $$
DECLARE c2 smallint;
BEGIN
    INSERT INTO company_profile (company_name) VALUES ('Tenant Verify Co')
    RETURNING id INTO c2;
    IF c2 <= 1 THEN
        RAISE EXCEPTION 'VERIFY FAIL (company id): sequence did not advance past 1 (got %)', c2;
    END IF;
    INSERT INTO customers (name, email, company_id)
    VALUES ('Verify Co2 Cust', 'tenant-dup-cust@example.com', c2);
    INSERT INTO workers (company_id, worker_code, name, hourly_rate)
    VALUES (c2, 'W-VERIFY', 'Verify Worker Co2', 30.00);
    INSERT INTO invoices (company_id, invoice_number, invoice_type, amount_due,
                          net_amount, due_date)
    VALUES (c2, 'INV-TENANT-VERIFY', 'PROGRESS_BILLING', 100.00, 100.00,
            CURRENT_DATE + INTERVAL '30 day');
    INSERT INTO payroll_runs (company_id, period_start, period_end, status)
    VALUES (c2, '2026-02-01', '2026-02-28', 'DRAFT');
END $$;

-- All assertions passed; discard fixtures (sequence gaps remain by design).
ROLLBACK;

-- Expected (clean run): no exception raised -> all tenant invariants PASS.
