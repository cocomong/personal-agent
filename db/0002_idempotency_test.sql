-- 0002_idempotency_test.sql
-- Verifies ADR-3: a replayed Vapi tool-call (same tool_call_id) must NOT
-- double-insert into change_orders or timesheets.
--
-- Plain SQL (no psql meta-commands) so it runs via pg, the Supabase SQL editor,
-- or any Postgres client. Self-contained: creates a throwaway project, inserts a
-- duplicate tool_call_id twice, asserts only one row, then rolls back.

BEGIN;

-- Fixture: a throwaway customer + project (rolled back at the end)
INSERT INTO customers (name, email) VALUES ('Idempotency Test', 'idem-test@example.com');

INSERT INTO projects (customer_id, title, site_address)
SELECT c.id, 'Idem Test Project', '123 Test St'
FROM customers c
WHERE c.email = 'idem-test@example.com';

-- Fixture: a throwaway worker (rolled back at the end)
INSERT INTO workers (worker_code, name, hourly_rate) VALUES ('W-IDEM', 'Idem Worker', 30.00);

-- 1. TIMESHEETS idempotency: insert, then replay the SAME tool_call_id.
INSERT INTO timesheets (project_id, worker_id, hours_worked, date_worked, tool_call_id)
SELECT p.id, (SELECT id FROM workers WHERE worker_code = 'W-IDEM'), 8.0, CURRENT_DATE, 'call_timesheet_dup_1'
FROM projects p JOIN customers c ON c.id = p.customer_id
WHERE c.email = 'idem-test@example.com'
ON CONFLICT (tool_call_id) DO NOTHING;

INSERT INTO timesheets (project_id, worker_id, hours_worked, date_worked, tool_call_id)
SELECT p.id, (SELECT id FROM workers WHERE worker_code = 'W-IDEM'), 8.0, CURRENT_DATE, 'call_timesheet_dup_1'
FROM projects p JOIN customers c ON c.id = p.customer_id
WHERE c.email = 'idem-test@example.com'
ON CONFLICT (tool_call_id) DO NOTHING;

-- 2. CHANGE ORDERS idempotency: insert, then replay the SAME tool_call_id.
INSERT INTO change_orders (project_id, change_order_number, description, cost_impact, tool_call_id)
SELECT p.id, 1, 'Test CO', 500.00, 'call_co_dup_1'
FROM projects p JOIN customers c ON c.id = p.customer_id
WHERE c.email = 'idem-test@example.com'
ON CONFLICT (tool_call_id) DO NOTHING;

INSERT INTO change_orders (project_id, change_order_number, description, cost_impact, tool_call_id)
SELECT p.id, 2, 'Test CO (replayed)', 500.00, 'call_co_dup_1'
FROM projects p JOIN customers c ON c.id = p.customer_id
WHERE c.email = 'idem-test@example.com'
ON CONFLICT (tool_call_id) DO NOTHING;

-- Assert exactly one row per tool_call_id (raise if a replay double-inserted).
DO $$
DECLARE
    timesheet_rows   int;
    change_order_rows int;
BEGIN
    SELECT COUNT(*) INTO timesheet_rows
    FROM timesheets WHERE tool_call_id = 'call_timesheet_dup_1';
    IF timesheet_rows <> 1 THEN
        RAISE EXCEPTION 'IDEMPOTENCY FAIL (timesheets): expected 1 row, got %', timesheet_rows;
    END IF;

    SELECT COUNT(*) INTO change_order_rows
    FROM change_orders WHERE tool_call_id = 'call_co_dup_1';
    IF change_order_rows <> 1 THEN
        RAISE EXCEPTION 'IDEMPOTENCY FAIL (change_orders): expected 1 row, got %', change_order_rows;
    END IF;
END $$;

-- All assertions passed; discard the throwaway fixtures.
ROLLBACK;

-- Expected (clean run):
--   no exception raised -> IDEMPOTENCY PASSED for both timesheets and change_orders.
-- A failure raises the named EXCEPTION and reports the row count.
