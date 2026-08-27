-- 0014_schedule.sql
-- Scheduling layer (v1.4): explicit schedule items + auto-derived events.
-- Two layers merged into view_schedule:
--   explicit  -> schedule_items (milestones, inspections, permits, deliveries,
--                meetings, tasks, lien, holdback, warranty)
--   derived   -> invoice due dates, quote expiries, and BC Builders Lien Act
--                statutory clocks (45-day lien filing, 55-day holdback release)
--                auto-computed from projects.completed_at.
-- Idempotent (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS / CREATE OR REPLACE).

-- 1. Project scheduling dates (drives the statutory auto-dates)
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS completed_at      DATE,   -- triggers lien/holdback clocks
    ADD COLUMN IF NOT EXISTS scheduled_start   DATE,   -- planned start
    ADD COLUMN IF NOT EXISTS target_completion DATE;   -- planned finish

-- 2. Explicit schedule items
CREATE TABLE IF NOT EXISTS schedule_items (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id        UUID REFERENCES projects(id) ON DELETE CASCADE,  -- NULL = company-wide
    type              VARCHAR(50) NOT NULL,  -- milestone|inspection|permit|delivery|meeting|task|lien|holdback|warranty
    title             VARCHAR(255) NOT NULL,
    description       TEXT,
    due_date          DATE,
    due_time          TIME,
    status            VARCHAR(50) NOT NULL DEFAULT 'PENDING',  -- PENDING|DONE|CANCELLED
    priority          VARCHAR(20) NOT NULL DEFAULT 'NORMAL',   -- HIGH|NORMAL|LOW
    assigned_to       VARCHAR(255),            -- free text or worker name
    reminder_days     INT NOT NULL DEFAULT 0,  -- remind N days before due
    reminder_sent_at  TIMESTAMPTZ,             -- idempotency for reminders
    completed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_schedule_items_due     ON schedule_items (due_date);
CREATE INDEX IF NOT EXISTS idx_schedule_items_project ON schedule_items (project_id);

-- 3. Configurable daily-briefing time (single-row settings live on company_profile)
ALTER TABLE company_profile
    ADD COLUMN IF NOT EXISTS briefing_time TIME NOT NULL DEFAULT '07:00';

-- 4. Unified schedule view: explicit items + derived events
CREATE OR REPLACE VIEW view_schedule AS
-- explicit schedule items
SELECT si.project_id,
       p.title      AS project_name,
       si.type,
       si.title,
       si.due_date,
       si.due_time,
       si.status,
       si.priority
FROM schedule_items si
LEFT JOIN projects p ON p.id = si.project_id

UNION ALL

-- invoice due dates (skip drafts; DONE when paid, HIGH when overdue)
SELECT i.project_id,
       p.title              AS project_name,
       'invoice_due'::text  AS type,
       i.invoice_number::text AS title,
       i.due_date,
       NULL::time           AS due_time,
       CASE WHEN i.status = 'PAID' THEN 'DONE' ELSE 'PENDING' END AS status,
       CASE WHEN i.status = 'OVERDUE' THEN 'HIGH' ELSE 'NORMAL' END AS priority
FROM invoices i
JOIN projects p ON p.id = i.project_id
WHERE i.status <> 'DRAFT'

UNION ALL

-- quote/estimate expiry (only SENT quotes that can still expire)
SELECT e.project_id,
       p.title            AS project_name,
       'quote_expiry'::text AS type,
       e.division_code::text AS title,
       e.valid_until      AS due_date,
       NULL::time         AS due_time,
       'PENDING'::text    AS status,
       'NORMAL'::text     AS priority
FROM estimates e
JOIN projects p ON p.id = e.project_id
WHERE e.status = 'SENT' AND e.valid_until IS NOT NULL

UNION ALL

-- BC Builders Lien Act: lien filing deadline (45 days after completion)
SELECT p.id             AS project_id,
       p.title          AS project_name,
       'lien_deadline'::text AS type,
       'Lien filing deadline (45d)'::text AS title,
       (p.completed_at + INTERVAL '45 days')::date AS due_date,
       NULL::time       AS due_time,
       'PENDING'::text  AS status,
       'HIGH'::text     AS priority
FROM projects p
WHERE p.completed_at IS NOT NULL

UNION ALL

-- BC Builders Lien Act: holdback release (55 days after completion)
SELECT p.id             AS project_id,
       p.title          AS project_name,
       'holdback_release'::text AS type,
       'Holdback release (55d)'::text AS title,
       (p.completed_at + INTERVAL '55 days')::date AS due_date,
       NULL::time       AS due_time,
       'PENDING'::text  AS status,
       'HIGH'::text     AS priority
FROM projects p
WHERE p.completed_at IS NOT NULL;
