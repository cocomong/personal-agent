-- 0003_seed.sql
-- Realistic sample data for manual, end-to-end testing of the Vapi gateway.
-- Idempotent: safe to run against a fresh DB (or careful on an existing one).
-- Values are deterministic so you can rely on the printed IDs.

-- Customers
INSERT INTO customers (name, company_name, email, phone)
SELECT 'Dave Miller', 'Miller Homes', 'dave@miller.com', '+1-604-555-0101'
WHERE NOT EXISTS (SELECT 1 FROM customers WHERE email = 'dave@miller.com');

INSERT INTO customers (name, company_name, email, phone)
SELECT 'Sarah Chen', NULL, 'sarah@chen.com', '+1-604-555-0102'
WHERE NOT EXISTS (SELECT 1 FROM customers WHERE email = 'sarah@chen.com');

-- Projects (reference the customers by email so the script is reusable)
INSERT INTO projects (customer_id, title, site_address, original_contract_value, revised_contract_value, status, baseline_status)
SELECT c.id, 'Oakridge Build', '1234 Oak St, Vancouver', 50000.00, 52500.00, 'ACTIVE', 'APPROVED'
FROM customers c WHERE c.email = 'dave@miller.com'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title = 'Oakridge Build');

INSERT INTO projects (customer_id, title, site_address, original_contract_value, revised_contract_value, status, baseline_status)
SELECT c.id, 'Kitsilano Reno', '88 West 4th Ave, Vancouver', 48000.00, 48000.00, 'ACTIVE', 'APPROVED'
FROM customers c WHERE c.email = 'sarah@chen.com'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title = 'Kitsilano Reno');

-- Estimate (base scope) for Oakridge
INSERT INTO estimates (project_id, division_code, scope_description, allocated_amount)
SELECT p.id, 'Framing', 'Main framing scope', 30000.00
FROM projects p WHERE p.title = 'Oakridge Build'
AND NOT EXISTS (
    SELECT 1 FROM estimates e JOIN projects p2 ON p2.id = e.project_id
    WHERE p2.title = 'Oakridge Build' AND e.division_code = 'Framing'
);

-- Approved change order for Oakridge (raises revised contract: 50000 + 2500 = 52500)
INSERT INTO change_orders (project_id, change_order_number, description, cost_impact, approval_status)
SELECT p.id, 1, 'Upgrade bathroom tile', 2500.00, 'APPROVED'
FROM projects p WHERE p.title = 'Oakridge Build'
AND NOT EXISTS (
    SELECT 1 FROM change_orders co JOIN projects p2 ON p2.id = co.project_id
    WHERE p2.title = 'Oakridge Build' AND co.change_order_number = 1
);

-- Workers (registry — timesheets reference workers by worker_id)
INSERT INTO workers (worker_code, name, trade, hourly_rate, overtime_rate)
SELECT 'W-001', 'Mike Johnson', 'Framer', 38.00, 57.00
WHERE NOT EXISTS (SELECT 1 FROM workers WHERE worker_code = 'W-001');

INSERT INTO workers (worker_code, name, trade, hourly_rate)
SELECT 'W-002', 'Ravi Patel', 'Electrician', 45.00
WHERE NOT EXISTS (SELECT 1 FROM workers WHERE worker_code = 'W-002');

-- Timesheet for Oakridge (references worker W-001)
INSERT INTO timesheets (project_id, worker_id, hours_worked, work_description, date_worked)
SELECT p.id, (SELECT id FROM workers WHERE worker_code = 'W-001'), 8.0, 'Framing day work', CURRENT_DATE
FROM projects p
WHERE p.title = 'Oakridge Build'
AND NOT EXISTS (
    SELECT 1 FROM timesheets t JOIN projects p2 ON p2.id = t.project_id
    WHERE p2.title = 'Oakridge Build'
      AND t.worker_id = (SELECT id FROM workers WHERE worker_code = 'W-001')
      AND t.date_worked = CURRENT_DATE
);

-- Draft invoice for Oakridge (progress billing 50% of revised contract, no tax)
INSERT INTO invoices (project_id, invoice_number, invoice_type, net_amount, gst_amount, pst_amount, amount_due, holdback_amount, status, issued_date, due_date)
SELECT p.id, 'INV-OAK-1001', 'PROGRESS_BILLING',
       ROUND(p.revised_contract_value * 0.50, 2), 0.00, 0.00,
       ROUND(p.revised_contract_value * 0.50, 2), 0.00, 'DRAFT', CURRENT_DATE, CURRENT_DATE + INTERVAL '30 day'
FROM projects p WHERE p.title = 'Oakridge Build'
AND NOT EXISTS (SELECT 1 FROM invoices WHERE invoice_number = 'INV-OAK-1001');

-- Reference summary to copy into manual test calls
SELECT 'seed complete' AS status;
SELECT id, title FROM projects ORDER BY title;
SELECT invoice_number, amount_due, status FROM invoices ORDER BY invoice_number;
