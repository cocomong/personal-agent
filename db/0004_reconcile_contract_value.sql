-- 0004_reconcile_contract_value.sql
-- Makes `projects.original_contract_value` / `revised_contract_value` the
-- single source of truth for contract values (Option 2 reconciliation).
--
-- Before: the rollup view derived contract value from SUM(estimates), which
-- disagreed with the `projects` columns (e.g. Oakridge showed 30000/32500 while
-- the project record + invoice math used 50000/52500).
--
-- After: the view reads the `projects` columns directly. `estimates` remains the
-- division-level breakdown (informational); `approved_change_orders_total` is a
-- derived informational sum. This matches the n8n `create_invoice` tool, which
-- already computes `amount_due = p.revised_contract_value * pct / 100`.

CREATE OR REPLACE VIEW view_project_financial_summary AS
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
    COALESCE(inv.total_invoiced, 0.00) AS total_invoiced,
    COALESCE(inv.total_paid, 0.00) AS total_paid,
    (COALESCE(p.revised_contract_value, 0.00) - COALESCE(inv.total_paid, 0.00)) AS balance_remaining,
    COALESCE(ts.total_labor_hours, 0.00) AS total_labor_hours
FROM projects p
JOIN customers c ON p.customer_id = c.id
LEFT JOIN (
    SELECT project_id, SUM(cost_impact) AS approved_co_total
    FROM change_orders
    WHERE approval_status = 'APPROVED'
    GROUP BY project_id
) co ON p.id = co.project_id
LEFT JOIN (
    SELECT project_id,
           SUM(amount_due) AS total_invoiced,
           SUM(CASE WHEN status = 'PAID' THEN amount_due ELSE 0.00 END) AS total_paid
    FROM invoices
    GROUP BY project_id
) inv ON p.id = inv.project_id
LEFT JOIN (
    SELECT project_id, SUM(hours_worked) AS total_labor_hours
    FROM timesheets
    GROUP BY project_id
) ts ON p.id = ts.project_id;
