-- 0001_init.sql
-- Construction PM Assistant — initial schema.
-- Matches doc/SYSTEM_DESIGN.md Section 3. Idempotency columns (tool_call_id)
-- implement ADR-3: Vapi tool-calls carry a toolCallId that must not double-insert.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. CUSTOMERS
CREATE TABLE customers (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name          VARCHAR(255) NOT NULL,
    company_name  VARCHAR(255),
    email         VARCHAR(255) UNIQUE NOT NULL,
    phone         VARCHAR(50),
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. PROJECTS
CREATE TABLE projects (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id             UUID REFERENCES customers(id) ON DELETE CASCADE,
    title                   VARCHAR(255) NOT NULL,
    site_address            TEXT NOT NULL,
    original_contract_value NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    revised_contract_value  NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    status                  VARCHAR(50) DEFAULT 'ACTIVE', -- ACTIVE, COMPLETED, ON_HOLD
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. ESTIMATES (base scope — locked once approved; change orders stay separate)
CREATE TABLE estimates (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id        UUID REFERENCES projects(id) ON DELETE CASCADE,
    division_code     VARCHAR(50) NOT NULL, -- e.g. Framing, Electrical, Plumbing
    scope_description TEXT NOT NULL,
    allocated_amount  NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. CHANGE ORDERS (amendments — kept separate from baseline estimate)
CREATE TABLE change_orders (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id          UUID REFERENCES projects(id) ON DELETE CASCADE,
    change_order_number INT NOT NULL,
    description         TEXT NOT NULL,
    cost_impact         NUMERIC(12,2) NOT NULL, -- + additions, - credits
    schedule_impact_days INT DEFAULT 0,
    approval_status     VARCHAR(50) DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED
    approved_at         TIMESTAMP WITH TIME ZONE,
    tool_call_id        VARCHAR(100) UNIQUE, -- ADR-3 idempotency
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. TIMESHEETS (payroll & job costing)
CREATE TABLE timesheets (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id       UUID REFERENCES projects(id) ON DELETE CASCADE,
    worker_name      VARCHAR(255) NOT NULL,
    hours_worked     NUMERIC(5,2) NOT NULL,
    work_description TEXT,
    date_worked      DATE NOT NULL DEFAULT CURRENT_DATE,
    tool_call_id     VARCHAR(100) UNIQUE, -- ADR-3 idempotency
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. INVOICES (billings referencing estimate progress or change orders)
CREATE TABLE invoices (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    invoice_number  VARCHAR(100) UNIQUE NOT NULL,
    invoice_type    VARCHAR(50) NOT NULL, -- DEPOSIT, PROGRESS_BILLING, CHANGE_ORDER, FINAL
    amount_due      NUMERIC(12,2) NOT NULL,
    holdback_amount NUMERIC(12,2) DEFAULT 0.00, -- e.g. statutory 10% retainage
    status          VARCHAR(50) DEFAULT 'UNPAID', -- UNPAID, PAID, OVERDUE
    issued_date     DATE DEFAULT CURRENT_DATE,
    due_date        DATE NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. INVOICE LINE ITEMS (link invoices to estimate_progress or change_order sources)
CREATE TABLE invoice_line_items (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id  UUID REFERENCES invoices(id) ON DELETE CASCADE,
    source_type VARCHAR(50) NOT NULL, -- 'estimate_progress' or 'change_order'
    source_id   UUID,
    description TEXT NOT NULL,
    amount      NUMERIC(12,2) NOT NULL
);

-- Foreign-key indexes (query paths used by the rollup view + n8n lookups)
CREATE INDEX idx_projects_customer ON projects(customer_id);
CREATE INDEX idx_estimates_project ON estimates(project_id);
CREATE INDEX idx_change_orders_project ON change_orders(project_id);
CREATE INDEX idx_timesheets_project ON timesheets(project_id);
CREATE INDEX idx_invoices_project ON invoices(project_id);
CREATE INDEX idx_invoice_line_items_invoice ON invoice_line_items(invoice_id);

-- Rollup view — all financial rollups in SQL, never in the LLM (ADR-2).
-- Source of truth for contract values is the `projects` table
-- (`original_contract_value` / `revised_contract_value`), maintained by the
-- n8n gateway when estimates are created and change orders are approved.
-- `estimates` is the division-level breakdown (informational), NOT the contract
-- baseline; `approved_change_orders_total` is a derived informational sum.
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
