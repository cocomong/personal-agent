-- 0043: per-company read models (Step 3 / P1).
--
-- The gateway tools filter by company_id now, so every view the tools read must
-- expose it. CREATE OR REPLACE VIEW may only ADD columns at the END, so each
-- view gets company_id as its last column and nothing else moves.
--
-- Also adds fn_run_payroll_for_company(): the original fn_run_payroll() has
-- `WHERE cp.id = 1` and no company filter on timesheets/workers, so it must not
-- be used for a second company. The old function is left in place (nothing else
-- calls it) rather than redefined with a changed signature.

-- 1. project financials -------------------------------------------------------
-- (Restated from the LIVE definition, not from db/0004: later migrations added
--  remaining_unbilled_contract / retention_held / overdue_amount /
--  total_labor_cost / gross_margin, and CREATE OR REPLACE cannot drop columns.)
CREATE OR REPLACE VIEW view_project_financial_summary AS
SELECT p.id AS project_id,
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
    COALESCE(p.revised_contract_value, 0.00) - COALESCE(inv.total_paid, 0.00) AS balance_remaining,
    COALESCE(p.revised_contract_value, 0.00) - COALESCE(inv.total_invoiced, 0.00) AS remaining_unbilled_contract,
    COALESCE(inv.retention_held, 0.00) AS retention_held,
    COALESCE(inv.overdue_amount, 0.00) AS overdue_amount,
    COALESCE(ts.total_labor_hours, 0.00) AS total_labor_hours,
    COALESCE(lc.total_labor_cost, 0.00) AS total_labor_cost,
    COALESCE(p.revised_contract_value, 0.00) - COALESCE(lc.total_labor_cost, 0.00) AS gross_margin,
    p.company_id
   FROM projects p
     JOIN customers c ON p.customer_id = c.id
     LEFT JOIN ( SELECT change_orders.project_id,
            sum(change_orders.cost_impact) AS approved_co_total
           FROM change_orders
          WHERE change_orders.approval_status::text = 'APPROVED'::text
          GROUP BY change_orders.project_id) co ON p.id = co.project_id
     LEFT JOIN ( SELECT i.project_id,
            sum(i.amount_due) AS total_invoiced,
            sum(vp.total_paid) AS total_paid,
            sum(
                CASE
                    WHEN i.status::text <> 'PAID'::text THEN i.holdback_amount
                    ELSE 0.00
                END) AS retention_held,
            sum(
                CASE
                    WHEN i.status::text = 'OVERDUE'::text THEN vp.balance_due
                    ELSE 0.00
                END) AS overdue_amount
           FROM invoices i
             JOIN view_invoice_payments vp ON vp.invoice_id = i.id
          GROUP BY i.project_id) inv ON p.id = inv.project_id
     LEFT JOIN ( SELECT timesheets.project_id,
            sum(timesheets.hours_worked) AS total_labor_hours
           FROM timesheets
          GROUP BY timesheets.project_id) ts ON p.id = ts.project_id
     LEFT JOIN ( SELECT t.project_id,
            sum(t.hours_worked * COALESCE(w.hourly_rate, 0.00)) AS total_labor_cost
           FROM timesheets t
             LEFT JOIN workers w ON w.id = t.worker_id
          GROUP BY t.project_id) lc ON p.id = lc.project_id;

-- 2. schedule -----------------------------------------------------------------
CREATE OR REPLACE VIEW view_schedule AS
SELECT si.project_id,
       p.title      AS project_name,
       si.type,
       si.title,
       si.due_date,
       si.due_time,
       si.status,
       si.priority,
       COALESCE(si.company_id, p.company_id) AS company_id
FROM schedule_items si
LEFT JOIN projects p ON p.id = si.project_id

UNION ALL

SELECT i.project_id,
       p.title              AS project_name,
       'invoice_due'::text  AS type,
       i.invoice_number::text AS title,
       i.due_date,
       NULL::time           AS due_time,
       CASE WHEN i.status = 'PAID' THEN 'DONE' ELSE 'PENDING' END AS status,
       CASE WHEN i.status = 'OVERDUE' THEN 'HIGH' ELSE 'NORMAL' END AS priority,
       i.company_id
FROM invoices i
JOIN projects p ON p.id = i.project_id
WHERE i.status <> 'DRAFT'

UNION ALL

SELECT e.project_id,
       p.title            AS project_name,
       'quote_expiry'::text AS type,
       e.division_code::text AS title,
       e.valid_until      AS due_date,
       NULL::time         AS due_time,
       'PENDING'::text    AS status,
       'NORMAL'::text     AS priority,
       p.company_id
FROM estimates e
JOIN projects p ON p.id = e.project_id
WHERE e.status = 'SENT' AND e.valid_until IS NOT NULL

UNION ALL

SELECT p.id             AS project_id,
       p.title          AS project_name,
       'lien_deadline'::text AS type,
       'Lien filing deadline (45d)'::text AS title,
       (p.completed_at + INTERVAL '45 days')::date AS due_date,
       NULL::time       AS due_time,
       'PENDING'::text  AS status,
       'HIGH'::text     AS priority,
       p.company_id
FROM projects p
WHERE p.completed_at IS NOT NULL

UNION ALL

SELECT p.id             AS project_id,
       p.title          AS project_name,
       'holdback_release'::text AS type,
       'Holdback release (55d)'::text AS title,
       (p.completed_at + INTERVAL '55 days')::date AS due_date,
       NULL::time       AS due_time,
       'PENDING'::text  AS status,
       'HIGH'::text     AS priority,
       p.company_id
FROM projects p
WHERE p.completed_at IS NOT NULL;

-- 3. payroll summary ----------------------------------------------------------
CREATE OR REPLACE VIEW view_payroll_summary AS
SELECT r.id AS run_id, r.period_start, r.period_end, r.status,
       COUNT(e.id) AS workers, SUM(e.regular_hours) AS regular_hours,
       SUM(e.overtime_hours) AS overtime_hours, SUM(e.gross_pay) AS gross_pay,
       SUM(e.cpp + e.ei + e.wcb) AS deductions, SUM(e.net_pay) AS net_pay,
       r.company_id
FROM payroll_runs r
LEFT JOIN payroll_entries e ON e.payroll_run_id = r.id
GROUP BY r.id, r.period_start, r.period_end, r.status, r.company_id;

-- 4. invoice payments ---------------------------------------------------------
CREATE OR REPLACE VIEW view_invoice_payments AS
SELECT i.id AS invoice_id,
       i.project_id,
       COALESCE(SUM(p.amount), 0.00) AS total_paid,
       i.amount_due - COALESCE(SUM(p.amount), 0.00) AS balance_due,
       i.due_date,
       i.company_id
FROM invoices i
LEFT JOIN payments p ON p.invoice_id = i.id
GROUP BY i.id, i.project_id, i.amount_due, i.due_date, i.company_id;

-- 5. company-scoped payroll ---------------------------------------------------
CREATE OR REPLACE FUNCTION fn_run_payroll_for_company(
    p_company_id smallint, p_end date, p_days int DEFAULT NULL)
RETURNS TABLE (run_id uuid, period_start date, period_end date, status varchar,
               workers bigint, regular_hours numeric, overtime_hours numeric,
               gross_pay numeric, deductions numeric, net_pay numeric) AS $$
DECLARE
    v_start date;
    v_end   date := p_end;
    v_run   uuid;
BEGIN
    IF p_company_id IS NULL THEN
        RAISE EXCEPTION 'fn_run_payroll_for_company requires a company id';
    END IF;

    IF p_days IS NOT NULL THEN
        v_end := COALESCE(p_end, CURRENT_DATE);
        v_start := v_end - (p_days - 1) * INTERVAL '1 day';
    ELSIF p_end IS NOT NULL THEN
        v_start := date_trunc('month', v_end)::date;
    ELSE
        v_end := (date_trunc('month', CURRENT_DATE)::date - INTERVAL '1 day')::date;
        v_start := date_trunc('month', v_end)::date;
    END IF;

    INSERT INTO payroll_runs (period_start, period_end, status, company_id)
    VALUES (v_start, v_end, 'DRAFT', p_company_id)
    ON CONFLICT DO NOTHING;

    SELECT pr.id INTO v_run FROM payroll_runs pr
     WHERE pr.period_start = v_start AND pr.period_end = v_end
       AND pr.company_id = p_company_id;

    INSERT INTO payroll_entries (
        payroll_run_id, worker_id, regular_hours, overtime_hours, hourly_rate,
        gross_pay, cpp, ei, wcb, net_pay, hours_by_project)
    SELECT v_run, w.id, a.regular_hours, a.overtime_hours, w.hourly_rate,
           ROUND(g.gross, 2),
           ROUND(g.gross * cp.cpp_rate, 2),
           ROUND(g.gross * cp.ei_rate, 2),
           ROUND(g.gross * cp.wcb_rate, 2),
           ROUND(g.gross * (1 - cp.cpp_rate - cp.ei_rate), 2),
           a.hours_by_project
    FROM (
        SELECT t.worker_id,
               SUM(t.hours_worked) AS regular_hours,
               SUM(t.overtime_hours) AS overtime_hours,
               (SELECT jsonb_object_agg(x.project_id::text, x.hrs)
                FROM (SELECT t2.project_id, SUM(t2.hours_worked + t2.overtime_hours) AS hrs
                      FROM timesheets t2
                      JOIN projects p2 ON p2.id = t2.project_id
                      WHERE t2.worker_id = t.worker_id
                        AND p2.company_id = p_company_id
                        AND t2.date_worked BETWEEN v_start AND v_end
                      GROUP BY t2.project_id) x) AS hours_by_project
        FROM timesheets t
        JOIN projects p ON p.id = t.project_id
        WHERE p.company_id = p_company_id
          AND t.date_worked BETWEEN v_start AND v_end
        GROUP BY t.worker_id
    ) a
    JOIN workers w ON w.id = a.worker_id AND w.company_id = p_company_id
    CROSS JOIN company_profile cp
    CROSS JOIN LATERAL (
        SELECT (a.regular_hours * w.hourly_rate
              + a.overtime_hours * COALESCE(w.overtime_rate, w.hourly_rate * cp.ot_multiplier)) AS gross
    ) g
    WHERE cp.id = p_company_id
    ON CONFLICT (payroll_run_id, worker_id) DO UPDATE SET
        regular_hours = EXCLUDED.regular_hours,
        overtime_hours = EXCLUDED.overtime_hours,
        hourly_rate = EXCLUDED.hourly_rate,
        gross_pay = EXCLUDED.gross_pay,
        cpp = EXCLUDED.cpp,
        ei = EXCLUDED.ei,
        wcb = EXCLUDED.wcb,
        net_pay = EXCLUDED.net_pay,
        hours_by_project = EXCLUDED.hours_by_project;

    RETURN QUERY
    SELECT pr.id, pr.period_start, pr.period_end, pr.status,
           COUNT(pe.id)::bigint, COALESCE(SUM(pe.regular_hours), 0),
           COALESCE(SUM(pe.overtime_hours), 0), COALESCE(SUM(pe.gross_pay), 0),
           COALESCE(SUM(pe.cpp + pe.ei + pe.wcb), 0), COALESCE(SUM(pe.net_pay), 0)
      FROM payroll_runs pr
      LEFT JOIN payroll_entries pe ON pe.payroll_run_id = pr.id
     WHERE pr.id = v_run
     GROUP BY pr.id, pr.period_start, pr.period_end, pr.status;
END;
$$ LANGUAGE plpgsql;

-- self-check ------------------------------------------------------------------
DO $$
DECLARE v text;
BEGIN
    FOREACH v IN ARRAY ARRAY['view_project_financial_summary', 'view_schedule',
                             'view_payroll_summary', 'view_invoice_payments'] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = v AND column_name = 'company_id'
        ) THEN
            RAISE EXCEPTION 'view % does not expose company_id', v;
        END IF;
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'fn_run_payroll_for_company') THEN
        RAISE EXCEPTION 'fn_run_payroll_for_company missing';
    END IF;
END $$;
