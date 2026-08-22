-- 0011_dashboard_views.sql
-- Tax-aware, ledger-driven financial rollup + payroll/dashboard/overdue views.
-- Replaces the 0004 rollup view (same name). total_paid now comes from the
-- payments ledger (view_invoice_payments), not a manual status flag.
-- DROP then CREATE (not CREATE OR REPLACE) because the view gains columns.

DROP VIEW IF EXISTS view_project_financial_summary;

CREATE VIEW view_project_financial_summary AS
SELECT
    p.id AS project_id,
    p.title AS project_name,
    p.status AS project_status,
    c.id AS customer_id,
    c.name AS customer_name,
    c.email AS customer_email,
    COALESCE(p.original_contract_value, 0.00) AS original_contract_value,
    COALESCE(co.approved_co_total, 0.00) AS approved_change_orders_total,
    COALESCE(p.revised_contract_value, 0.00) AS total_revised_contract_value,
    COALESCE(inv.total_invoiced, 0.00) AS total_invoiced,          -- gross (incl. tax)
    COALESCE(inv.total_paid, 0.00) AS total_paid,                  -- from payments ledger
    (COALESCE(p.revised_contract_value, 0.00) - COALESCE(inv.total_paid, 0.00)) AS balance_remaining,
    (COALESCE(p.revised_contract_value, 0.00) - COALESCE(inv.total_invoiced, 0.00)) AS remaining_unbilled_contract,
    COALESCE(inv.retention_held, 0.00) AS retention_held,
    COALESCE(inv.overdue_amount, 0.00) AS overdue_amount,
    COALESCE(ts.total_labor_hours, 0.00) AS total_labor_hours,
    COALESCE(lc.total_labor_cost, 0.00) AS total_labor_cost,
    (COALESCE(p.revised_contract_value, 0.00) - COALESCE(lc.total_labor_cost, 0.00)) AS gross_margin
FROM projects p
JOIN customers c ON p.customer_id = c.id
LEFT JOIN (
    SELECT project_id, SUM(cost_impact) AS approved_co_total
    FROM change_orders
    WHERE approval_status = 'APPROVED'
    GROUP BY project_id
) co ON p.id = co.project_id
LEFT JOIN (
    SELECT i.project_id,
           SUM(i.amount_due) AS total_invoiced,
           SUM(vp.total_paid) AS total_paid,
           SUM(CASE WHEN i.status <> 'PAID' THEN i.holdback_amount ELSE 0.00 END) AS retention_held,
           SUM(CASE WHEN i.status = 'OVERDUE' THEN vp.balance_due ELSE 0.00 END) AS overdue_amount
    FROM invoices i
    JOIN view_invoice_payments vp ON vp.invoice_id = i.id
    GROUP BY i.project_id
) inv ON p.id = inv.project_id
LEFT JOIN (
    SELECT project_id, SUM(hours_worked) AS total_labor_hours
    FROM timesheets
    GROUP BY project_id
) ts ON p.id = ts.project_id
LEFT JOIN (
    SELECT t.project_id, SUM(t.hours_worked * COALESCE(w.hourly_rate, 0.00)) AS total_labor_cost
    FROM timesheets t
    LEFT JOIN workers w ON w.id = t.worker_id
    GROUP BY t.project_id
) lc ON p.id = lc.project_id;

-- Payroll summary per run
CREATE OR REPLACE VIEW view_payroll_summary AS
SELECT r.id AS run_id, r.period_start, r.period_end, r.status,
       COUNT(e.id) AS workers, SUM(e.regular_hours) AS regular_hours,
       SUM(e.overtime_hours) AS overtime_hours, SUM(e.gross_pay) AS gross_pay,
       SUM(e.cpp + e.ei + e.wcb) AS deductions, SUM(e.net_pay) AS net_pay
FROM payroll_runs r
LEFT JOIN payroll_entries e ON e.payroll_run_id = r.id
GROUP BY r.id, r.period_start, r.period_end, r.status;

-- Overdue / due-soon invoices (daily check source)
CREATE OR REPLACE VIEW view_overdue_invoices AS
SELECT i.invoice_number, i.project_id, p.title AS project_name, c.name AS customer_name,
       c.email AS customer_email, i.amount_due, vp.total_paid, vp.balance_due,
       i.due_date, i.status,
       CASE WHEN i.due_date < CURRENT_DATE THEN 'OVERDUE'
            WHEN i.due_date <= CURRENT_DATE + 7 THEN 'DUE_SOON' ELSE 'OK' END AS bucket
FROM invoices i
JOIN projects p ON p.id = i.project_id
JOIN customers c ON c.id = p.customer_id
JOIN view_invoice_payments vp ON vp.invoice_id = i.id
WHERE i.status <> 'PAID';

-- Sent quotes past validity with no acceptance (follow-up source)
CREATE OR REPLACE VIEW view_quote_followups AS
SELECT e.id, e.project_id, p.title AS project_name, c.name AS customer_name,
       c.email AS customer_email, e.scope_description, e.revision, e.valid_until,
       COALESCE(e.allocated_amount, 0.00) AS amount
FROM estimates e
JOIN projects p ON p.id = e.project_id
JOIN customers c ON c.id = p.customer_id
WHERE e.status = 'SENT'
  AND e.valid_until IS NOT NULL
  AND e.valid_until < CURRENT_DATE;
