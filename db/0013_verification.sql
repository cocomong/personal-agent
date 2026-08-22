-- 0013_verification.sql
-- Verifies the migration invariants. Plain SQL, self-contained, self-rolled-back
-- (like 0002_idempotency_test.sql). Run after 0001-0012.

BEGIN;

-- (a) company_profile has exactly one row
DO $$
DECLARE n int;
BEGIN
    SELECT COUNT(*) INTO n FROM company_profile;
    IF n <> 1 THEN
        RAISE EXCEPTION 'VERIFY FAIL (company_profile): expected 1 row, got %', n;
    END IF;
END $$;

-- (b) every invoice reconciles: amount_due = net + gst + pst
DO $$
DECLARE bad int;
BEGIN
    SELECT COUNT(*) INTO bad FROM invoices
     WHERE ABS(amount_due - (COALESCE(net_amount,0) + gst_amount + pst_amount)) > 0.02;
    IF bad <> 0 THEN
        RAISE EXCEPTION 'VERIFY FAIL (invoice tax): % invoice(s) do not reconcile net+gst+pst', bad;
    END IF;
END $$;

-- (c) rollup reconciles: balance_remaining = revised_contract - total_paid
DO $$
DECLARE bad int;
BEGIN
    SELECT COUNT(*) INTO bad FROM view_project_financial_summary
     WHERE ABS(balance_remaining - (total_revised_contract_value - total_paid)) > 0.02;
    IF bad <> 0 THEN
        RAISE EXCEPTION 'VERIFY FAIL (rollup): % project(s) balance_remaining mismatch', bad;
    END IF;
END $$;

-- (d) record_payment idempotency: replayed tool_call_id does not double-insert
INSERT INTO customers (name, email) VALUES ('Verify Test', 'verify@example.com');

INSERT INTO projects (customer_id, title, site_address, original_contract_value, revised_contract_value, baseline_status)
SELECT c.id, 'Verify Test Project', '1 Verify St', 1000.00, 1000.00, 'APPROVED'
FROM customers c WHERE c.email = 'verify@example.com';

INSERT INTO invoices (project_id, invoice_number, invoice_type, amount_due, net_amount, status, due_date)
SELECT p.id, 'INV-VERIFY-1', 'PROGRESS_BILLING', 1000.00, 1000.00, 'UNPAID', CURRENT_DATE + INTERVAL '30 day'
FROM projects p WHERE p.title = 'Verify Test Project';

INSERT INTO payments (invoice_id, amount, tool_call_id)
SELECT i.id, 250.00, 'call_pay_dup_1' FROM invoices i WHERE i.invoice_number = 'INV-VERIFY-1'
ON CONFLICT (tool_call_id) DO NOTHING;

INSERT INTO payments (invoice_id, amount, tool_call_id)
SELECT i.id, 250.00, 'call_pay_dup_1' FROM invoices i WHERE i.invoice_number = 'INV-VERIFY-1'
ON CONFLICT (tool_call_id) DO NOTHING;

DO $$
DECLARE n int;
BEGIN
    SELECT COUNT(*) INTO n FROM payments WHERE tool_call_id = 'call_pay_dup_1';
    IF n <> 1 THEN
        RAISE EXCEPTION 'VERIFY FAIL (payment idempotency): expected 1 row, got %', n;
    END IF;
END $$;

-- All assertions passed; discard fixtures.
ROLLBACK;

-- Expected (clean run): no exception raised -> all invariants PASS.
