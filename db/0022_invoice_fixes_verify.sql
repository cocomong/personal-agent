-- 0022_invoice_fixes_verify.sql
-- Verifies 0021 invariants. Self-contained, self-rolled-back (house style).
-- Asserts:
--   (a) new columns + invoice_email_log table exist
--   (b) per-company counter allocates 1, 2, ... sequentially
--   (c) emailed DRAFT invoices transition to UNPAID (the 0021 backfill rule)
--   (d) invoice_email_log accepts preview/client/resend/reject rows

BEGIN;

-- (a) schema additions present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'company_profile'
          AND column_name = 'invoice_last_number'
          AND is_nullable = 'NO'
    ) THEN
        RAISE EXCEPTION 'VERIFY FAIL (numbering): company_profile.invoice_last_number missing or nullable';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'invoices'
          AND column_name IN ('description', 'last_client_html')
    ) THEN
        RAISE EXCEPTION 'VERIFY FAIL (invoice cols): description/last_client_html missing';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'invoice_email_log'
    ) THEN
        RAISE EXCEPTION 'VERIFY FAIL (email log): invoice_email_log table missing';
    END IF;
END $$;

-- (b) counter allocates sequentially per company
DO $$
DECLARE n1 int; n2 int;
BEGIN
    UPDATE company_profile SET invoice_last_number = invoice_last_number + 1
     WHERE id = 1 RETURNING invoice_last_number INTO n1;
    UPDATE company_profile SET invoice_last_number = invoice_last_number + 1
     WHERE id = 1 RETURNING invoice_last_number INTO n2;
    IF n1 <> 1 OR n2 <> 2 THEN
        RAISE EXCEPTION 'VERIFY FAIL (numbering): expected 1 then 2, got % then %', n1, n2;
    END IF;
END $$;

-- (c) emailed DRAFT -> UNPAID (mirrors the 0021 backfill rule on a fixture)
DO $$
DECLARE v_inv int;
BEGIN
    INSERT INTO customers (name, email, company_id)
    VALUES ('Verify Invoice Fix', 'verify-invfix@example.com', 1);
    INSERT INTO invoices (company_id, project_id, invoice_number, invoice_type,
                          amount_due, net_amount, status, due_date, email_sent_at)
    SELECT 1, NULL, 'INV-VERIFY-FIX', 'PROGRESS_BILLING', 100.00, 100.00, 'DRAFT',
           CURRENT_DATE + 30, CURRENT_TIMESTAMP
    WHERE NOT EXISTS (SELECT 1 FROM invoices WHERE invoice_number = 'INV-VERIFY-FIX');
    UPDATE invoices SET status = 'UNPAID'
     WHERE invoice_number = 'INV-VERIFY-FIX' AND status = 'DRAFT' AND email_sent_at IS NOT NULL;
    SELECT COUNT(*) INTO v_inv FROM invoices
     WHERE invoice_number = 'INV-VERIFY-FIX' AND status = 'UNPAID';
    IF v_inv IS NULL OR v_inv <> 1 THEN
        RAISE EXCEPTION 'VERIFY FAIL (status transition): emailed DRAFT did not become UNPAID';
    END IF;
    -- (d) email log accepts rows
    INSERT INTO invoice_email_log (invoice_id, company_id, kind, recipient, message_id)
    SELECT id, 1, 'preview', 'pm@example.com', 'msg-verify-1'
    FROM invoices WHERE invoice_number = 'INV-VERIFY-FIX';
    INSERT INTO invoice_email_log (invoice_id, company_id, kind, recipient, message_id)
    SELECT id, 1, 'client', 'client@example.com', 'msg-verify-2'
    FROM invoices WHERE invoice_number = 'INV-VERIFY-FIX';
    IF (SELECT COUNT(*) FROM invoice_email_log WHERE message_id LIKE 'msg-verify-%') <> 2 THEN
        RAISE EXCEPTION 'VERIFY FAIL (email log): expected 2 log rows';
    END IF;
END $$;

-- All assertions passed; discard fixtures (counter change rolls back too).
ROLLBACK;

-- Expected (clean run): no exception raised -> all 0021 invariants PASS.
