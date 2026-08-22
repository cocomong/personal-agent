-- 0008_workers_payroll.sql
-- Payroll subsystem (ported from the Sheets "Construction Ops" tracker).
-- The `workers` registry itself lives in 0001 (timesheets reference it by
-- worker_id). This migration adds the payroll tables + calc and the
-- timesheets.overtime_hours column. Financial calc (CPP/EI/WCB, gross/net) is
-- done in SQL (ADR-2) using rates from company_profile — never in the LLM.

CREATE TABLE IF NOT EXISTS payroll_runs (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    period_start DATE NOT NULL,
    period_end   DATE NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT / APPROVED / PAID
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (period_start, period_end)                   -- run_payroll idempotency key
);

CREATE TABLE IF NOT EXISTS payroll_entries (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    payroll_run_id   UUID NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
    worker_id        UUID NOT NULL REFERENCES workers(id),
    regular_hours    NUMERIC(8,2) NOT NULL DEFAULT 0.00,
    overtime_hours   NUMERIC(8,2) NOT NULL DEFAULT 0.00,
    hourly_rate      NUMERIC(10,2) NOT NULL,
    gross_pay        NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    cpp              NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    ei               NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    wcb              NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    net_pay          NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    hours_by_project JSONB,                          -- {"<project_id>": 40.0, ...}
    created_at       TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (payroll_run_id, worker_id)               -- one entry per worker per run
);
CREATE INDEX IF NOT EXISTS idx_payroll_entries_run   ON payroll_entries (payroll_run_id);
CREATE INDEX IF NOT EXISTS idx_payroll_entries_worker ON payroll_entries (worker_id);
CREATE INDEX IF NOT EXISTS idx_workers_active        ON workers (active);

-- Timesheets gain an overtime column (Sheets tracker parity) so payroll can
-- split regular vs overtime hours. Default 0 keeps existing rows valid.
ALTER TABLE timesheets
    ADD COLUMN IF NOT EXISTS overtime_hours NUMERIC(5,2) NOT NULL DEFAULT 0.00;

-- Compute a payroll run from timesheets (ADR-2: all math in SQL).
-- Aggregates timesheets in [start, end] by worker, joins workers for rates and
-- company_profile for CPP/EI/WCB/OT-multiplier, upserts payroll_runs/entries,
-- and returns the run summary. Idempotent: re-running the same period updates
-- the existing entries instead of duplicating (UNIQUE keys on the tables).
CREATE OR REPLACE FUNCTION fn_run_payroll(p_end date, p_days int DEFAULT NULL)
RETURNS TABLE (run_id uuid, period_start date, period_end date, status varchar,
               workers bigint, regular_hours numeric, overtime_hours numeric,
               gross_pay numeric, deductions numeric, net_pay numeric) AS $$
DECLARE
    v_start date;
    v_end   date := p_end;
    v_run   uuid;
BEGIN
    IF p_days IS NOT NULL THEN
        v_end := COALESCE(p_end, CURRENT_DATE);
        v_start := v_end - (p_days - 1) * INTERVAL '1 day';
    ELSIF p_end IS NOT NULL THEN
        v_start := date_trunc('month', v_end)::date;   -- month-to-date ending at p_end
    ELSE
        -- Default: previous complete calendar month (monthly payroll close).
        v_end := (date_trunc('month', CURRENT_DATE)::date - INTERVAL '1 day')::date;
        v_start := date_trunc('month', v_end)::date;
    END IF;

    INSERT INTO payroll_runs (period_start, period_end, status)
    VALUES (v_start, v_end, 'DRAFT')
    ON CONFLICT DO NOTHING;

    SELECT id INTO v_run FROM payroll_runs pr
     WHERE pr.period_start = v_start AND pr.period_end = v_end;

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
                      WHERE t2.worker_id = t.worker_id
                        AND t2.date_worked BETWEEN v_start AND v_end
                      GROUP BY t2.project_id) x) AS hours_by_project
        FROM timesheets t
        WHERE t.date_worked BETWEEN v_start AND v_end
        GROUP BY t.worker_id
    ) a
    JOIN workers w ON w.id = a.worker_id
    CROSS JOIN company_profile cp
    CROSS JOIN LATERAL (
        SELECT (a.regular_hours * w.hourly_rate
              + a.overtime_hours * COALESCE(w.overtime_rate, w.hourly_rate * cp.ot_multiplier)) AS gross
    ) g
    WHERE cp.id = 1
    ON CONFLICT (payroll_run_id, worker_id) DO UPDATE SET
        regular_hours = EXCLUDED.regular_hours,
        overtime_hours = EXCLUDED.overtime_hours,
        hourly_rate = EXCLUDED.hourly_rate,
        gross_pay = EXCLUDED.gross_pay,
        cpp = EXCLUDED.cpp, ei = EXCLUDED.ei, wcb = EXCLUDED.wcb,
        net_pay = EXCLUDED.net_pay,
        hours_by_project = EXCLUDED.hours_by_project;

    RETURN QUERY
    SELECT r.id, r.period_start, r.period_end, r.status,
           COUNT(e.id), COALESCE(SUM(e.regular_hours), 0),
           COALESCE(SUM(e.overtime_hours), 0), COALESCE(SUM(e.gross_pay), 0),
           COALESCE(SUM(e.cpp + e.ei + e.wcb), 0), COALESCE(SUM(e.net_pay), 0)
    FROM payroll_runs r
    LEFT JOIN payroll_entries e ON e.payroll_run_id = r.id
    WHERE r.id = v_run
    GROUP BY r.id, r.period_start, r.period_end, r.status;
END $$ LANGUAGE plpgsql;

