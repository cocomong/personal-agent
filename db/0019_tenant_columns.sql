-- 0019_tenant_columns.sql
-- Multi-tenant Step 2 (TENANT COLUMNS): company_id on every business table.
-- See doc/MULTITENANT.md sections 3.2-3.3.
--
-- Mechanic (deviation from §3.3, same invariants): columns are added as
--   company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id)
-- instead of nullable-then-backfill. Postgres fills existing rows with 1 at
-- ADD COLUMN time, so no backfill pass is needed AND every pre-Step-3 write
-- (the live gateway omits company_id) lands in company 1 — the original Ireh
-- Construction row — which is correct while the service is still single-tenant.
-- The DEFAULT keeps uniqueness airtight through the interim; Step 3 drops it
-- once every write path passes company_id explicitly.
--
-- company_profile.id is SMALLINT (migration 0007), NOT uuid — all company_id
-- columns match that type. Idempotent (IF NOT EXISTS / IF EXISTS).

-- 1. company_profile: allow more than one company (Step 3 creates them).
--    New ids come from a sequence starting at 2 (id 1 = Ireh exists).
CREATE SEQUENCE IF NOT EXISTS company_profile_id_seq START 2;
ALTER TABLE company_profile
    ALTER COLUMN id SET DEFAULT nextval('company_profile_id_seq')::SMALLINT;
ALTER SEQUENCE company_profile_id_seq OWNED BY company_profile.id;
ALTER TABLE company_profile DROP CONSTRAINT IF EXISTS company_profile_id_check;

-- Audit trail: which user created the company (written by Step 3 onboarding).
ALTER TABLE company_profile
    ADD COLUMN IF NOT EXISTS created_by_user UUID REFERENCES users(id);

-- 2. company_id column on every directly-scoped table.
--    Invoices get their own column (set from the project's company at insert)
--    because UNIQUE(company_id, invoice_number) cannot span a join. Children
--    that inherit via project_id (estimates, change_orders, timesheets,
--    invoice_line_items, payments, payroll_entries) need no column.
ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id);
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id);
ALTER TABLE workers
    ADD COLUMN IF NOT EXISTS company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id);
ALTER TABLE payroll_runs
    ADD COLUMN IF NOT EXISTS company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id);
ALTER TABLE schedule_items
    ADD COLUMN IF NOT EXISTS company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id);
ALTER TABLE device_tokens
    ADD COLUMN IF NOT EXISTS company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id);
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id);

-- 3. Re-scope the cross-company uniques to per-company (unique INDEXES so the
--    DDL is idempotent — CREATE UNIQUE INDEX IF NOT EXISTS; PG has no
--    ADD CONSTRAINT IF NOT EXISTS). Create the new guards BEFORE dropping the
--    old global ones so no window exists without protection.
CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_company_email
    ON customers (company_id, email);
CREATE UNIQUE INDEX IF NOT EXISTS uq_workers_company_worker_code
    ON workers (company_id, worker_code);
CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_company_invoice_number
    ON invoices (company_id, invoice_number);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_runs_company_period
    ON payroll_runs (company_id, period_start, period_end);

ALTER TABLE customers    DROP CONSTRAINT IF EXISTS customers_email_key;
ALTER TABLE workers      DROP CONSTRAINT IF EXISTS workers_worker_code_key;
ALTER TABLE invoices     DROP CONSTRAINT IF EXISTS invoices_invoice_number_key;
ALTER TABLE payroll_runs DROP CONSTRAINT IF EXISTS payroll_runs_period_start_period_end_key;
-- device_tokens UNIQUE (token) stays global: FCM tokens are globally unique;
-- company_id on the row records ownership only.

-- 4. Lookup indexes for the Step 3 scoping queries.
CREATE INDEX IF NOT EXISTS idx_customers_company     ON customers (company_id);
CREATE INDEX IF NOT EXISTS idx_projects_company      ON projects (company_id);
CREATE INDEX IF NOT EXISTS idx_workers_company       ON workers (company_id);
CREATE INDEX IF NOT EXISTS idx_payroll_runs_company  ON payroll_runs (company_id);
CREATE INDEX IF NOT EXISTS idx_schedule_items_company ON schedule_items (company_id);
CREATE INDEX IF NOT EXISTS idx_device_tokens_company ON device_tokens (company_id);
CREATE INDEX IF NOT EXISTS idx_invoices_company      ON invoices (company_id);
