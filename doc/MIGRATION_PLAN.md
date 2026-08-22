# Personal-Agent ← Construction Ops Migration Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Bring the proven business capabilities of the Google Sheets "Construction Ops" tracker into the personal-agent stack (Vapi + n8n + Supabase/PostgreSQL + Flutter), with **all company branding and financial settings extracted into a single configurable `company_profile` table** — and migrate the automation, tax, payments, workers/payroll, and document-generation logic.

**Architecture:** PostgreSQL migrations add 4 new tables + column extensions; n8n gateway reads `company_profile` (single-row, typed columns) instead of hardcoded strings; new/updated Vapi tools surface the new capabilities over voice; recurring automations run as n8n Schedule Trigger workflows (self-contained on the existing VPS); branded PDFs generated n8n-native (HTML→PDF) with the reportlab pipeline as a documented fallback.

**Tech Stack:** Supabase/PostgreSQL (existing), n8n (existing at n8n2.ordrnow.com), Vapi (existing), reportlab (existing in `~/.hermes/venv`), Gmail SMTP (existing).

---

## 0. Source inventory (already extracted)

### 0.1 Branding/config hardcoded today (must become configurable)

| Location | Hardcoded value |
|---|---|
| `backend/n8n/workflows/voice-gateway.json` — `Render Estimate Approval Email`, `Render Change Order Approval Email`, `Format Spoken Result` Code nodes | `base = 'https://n8n2.ordrnow.com'` (3×), email brand colors `#2563eb`/`#16a34a`, `fromEmail` |
| `backend/DEPLOY.md` | `GMAIL_USER=yourname@gmail.com` env; `n8n2.ordrnow.com` base URL |
| Sheets workbook `make_invoice.py` (source of truth for branding) | `"Dave's Construction Co. · Burnaby, BC"`, navy `#1a3a5c`, grey `#eef2f6`, signature `"Thanks, Dave"` |
| Sheets workbook `Settings` tab | GST 5%, PST 7%, retention 10%, CPP 5.95%, EI 1.63%, WCB 3.25%, due days 30, prefixes `INV-`/`QUO-`/`CR-`/`PRJ-`, bi-weekly payroll |
| `mobile-flutter/lib/config.dart` | Vapi keys only (no branding) — no change needed for MVP |

### 0.2 Capabilities in Sheets tracker but missing in personal-agent

Workers registry, payroll calc, per-invoice GST/PST, payments ledger, Settings/config table, CR reason taxonomy, quote revision trail, overdue/quote-follow-up automation, branded PDF attachments.

### 0.3 Data state

Sheets workbook holds **test data only** (PRJ-001 "Test Client Co", 2 workers, 20 demo timesheet rows). Nothing to migrate; only rules + settings. Supabase already has seed data (Oakridge / Kitsilano).

### 0.4 Decisions recorded (Dave, 2026-08-22)

| # | Decision |
|---|---|
| 1 | **Branding:** full legal name + full address + phone, all in `company_profile` (configurable). *Received:* Ireh Construction, 1951 Kaptey Ave, Coquitlam BC V3K 5Z7, 778-994-6602. |
| 2 | **Tax:** GST 5% always; PST 7% via per-invoice `pst_applicable` flag (default off for services). |
| 3 | **PDF:** n8n HTML→PDF (Puppeteer) primary; reportlab port only if Puppeteer is unavailable in the n8n image. |
| 4 | **Payroll:** **monthly** cadence; DRAFT run → Dave approves. |
| 5 | **Scope:** ship all 5 new voice tools (`record_payment`, `run_payroll`, `get_payroll_summary`, `add_worker`, `get_dashboard_summary`). |

---

## 1. Schema migrations (`db/0007` → `db/0011`)

Apply order (append to `backend/DEPLOY.md` fresh-install list):

1. `0007_company_profile.sql` — branding + financial settings, single row
2. `0008_workers_payroll.sql` — workers, payroll_runs, payroll_entries
3. `0009_tax_payments.sql` — invoice tax columns + payments table
4. `0010_quote_trail.sql` — estimate revisions/validity, CR reason
5. `0011_dashboard_views.sql` — tax-aware rollup + payroll/dashboard/overdue views

### Task 1: `db/0007_company_profile.sql`

**Objective:** Create the single source of truth for branding + financial defaults; seed with values extracted from the Sheets tracker.

**Files:**
- Create: `db/0007_company_profile.sql`
- Test: `db/0007_company_profile.sql` (idempotent re-run + row guard check)

```sql
-- 0007_company_profile.sql
-- Single source of truth for company branding + financial defaults.
-- Replaces hardcoded strings in n8n Code nodes and PDF/email templates.

CREATE TABLE IF NOT EXISTS company_profile (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),   -- enforce single row
    -- Identity / branding
    company_name        VARCHAR(255) NOT NULL DEFAULT 'Ireh Construction',
    legal_name          VARCHAR(255) NOT NULL DEFAULT 'Ireh Construction',
    street_address      TEXT NOT NULL DEFAULT '1951 Kaptey Ave',
    city                VARCHAR(100) NOT NULL DEFAULT 'Coquitlam',
    province            VARCHAR(50)  NOT NULL DEFAULT 'BC',
    postal_code         VARCHAR(20) NOT NULL DEFAULT 'V3K 5Z7',
    phone               VARCHAR(50) NOT NULL DEFAULT '778-994-6602',
    email_from          VARCHAR(255) NOT NULL DEFAULT 'support.ordrnow@gmail.com',
    email_from_name     VARCHAR(255) NOT NULL DEFAULT 'Ireh Construction',
    website             VARCHAR(255),
    portal_base_url     VARCHAR(255) NOT NULL DEFAULT 'https://n8n2.ordrnow.com',
    signature_name      VARCHAR(255) NOT NULL DEFAULT 'Dave',
    -- Document numbering
    invoice_prefix      VARCHAR(20) NOT NULL DEFAULT 'INV-',
    quote_prefix        VARCHAR(20) NOT NULL DEFAULT 'QUO-',
    change_order_prefix VARCHAR(20) NOT NULL DEFAULT 'CR-',
    project_prefix      VARCHAR(20) NOT NULL DEFAULT 'PRJ-',
    -- Branding colors (emails / PDFs / portal)
    brand_primary_color VARCHAR(9)  NOT NULL DEFAULT '#1a3a5c',
    brand_accent_color  VARCHAR(9)  NOT NULL DEFAULT '#2563eb',
    brand_success_color VARCHAR(9)  NOT NULL DEFAULT '#16a34a',
    -- Financial defaults (BC)
    gst_rate            NUMERIC(5,4) NOT NULL DEFAULT 0.05,
    pst_rate            NUMERIC(5,4) NOT NULL DEFAULT 0.07,
    retention_rate      NUMERIC(5,4) NOT NULL DEFAULT 0.10,
    invoice_due_days    INT NOT NULL DEFAULT 30,
    -- Payroll defaults
    cpp_rate            NUMERIC(5,4) NOT NULL DEFAULT 0.0595,
    ei_rate             NUMERIC(5,4) NOT NULL DEFAULT 0.0163,
    wcb_rate            NUMERIC(5,4) NOT NULL DEFAULT 0.0325,
    payroll_period      VARCHAR(20)  NOT NULL DEFAULT 'MONTHLY',  -- WEEKLY / BIWEEKLY / MONTHLY
    payroll_day_of_month INT NOT NULL DEFAULT 1,                  -- fire day for MONTHLY
    ot_multiplier       NUMERIC(3,2) NOT NULL DEFAULT 1.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed (values extracted from Sheets Settings tab + make_invoice.py branding)
INSERT INTO company_profile (id)
SELECT 1
WHERE NOT EXISTS (SELECT 1 FROM company_profile WHERE id = 1);
```

**Verify:** re-run file twice (idempotent); `SELECT * FROM company_profile;` returns exactly 1 row with the seed values.

### Task 2: `db/0008_workers_payroll.sql`

**Objective:** Port the Workers + Payroll subsystem (the biggest gap).

**Files:**
- Create: `db/0008_workers_payroll.sql`

```sql
-- 0008_workers_payroll.sql
CREATE TABLE IF NOT EXISTS workers (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    worker_code   VARCHAR(20) UNIQUE,               -- W-001 style (Sheets parity)
    name          VARCHAR(255) NOT NULL,
    trade         VARCHAR(100),                     -- Framer / Electrician / Labourer...
    hourly_rate   NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    overtime_rate NUMERIC(10,2),                    -- NULL -> hourly_rate * ot_multiplier
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    period_start DATE NOT NULL,
    period_end   DATE NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT / APPROVED / PAID
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (period_start, period_end)
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
    UNIQUE (payroll_run_id, worker_id)
);
CREATE INDEX IF NOT EXISTS idx_payroll_entries_run   ON payroll_entries (payroll_run_id);
CREATE INDEX IF NOT EXISTS idx_payroll_entries_worker ON payroll_entries (worker_id);
CREATE INDEX IF NOT EXISTS idx_workers_active        ON workers (active);
```

**Payroll calc rule (ported from `weekly_payroll.py`, executed in n8n SQL — ADR-2):**
gross = `regular_hours * hourly_rate + overtime_hours * COALESCE(overtime_rate, hourly_rate * cp.ot_multiplier)`; cpp/ei/wcb = gross × rates from `company_profile`; net = gross − cpp − ei. Hours-by-project from `timesheets` joined to `workers` by name→worker lookup.

### Task 3: `db/0009_tax_payments.sql`

**Objective:** Add per-invoice tax (GST/PST) and a payments ledger with derived status.

**Files:**
- Create: `db/0009_tax_payments.sql`

```sql
-- 0009_tax_payments.sql
-- amount_due becomes the GROSS (tax-inclusive) total; net/tax broken out.
-- GST always applied; PST applied only when pst_applicable is true (Decision #2).
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS net_amount NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS gst_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS pst_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS pst_applicable BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: existing rows have no tax -> net = amount_due
UPDATE invoices SET net_amount = amount_due WHERE net_amount IS NULL;

ALTER TABLE invoices ALTER COLUMN net_amount SET NOT NULL;

CREATE TABLE IF NOT EXISTS payments (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id   UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    payment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    amount       NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    method       VARCHAR(50),     -- E-transfer / Cheque / Credit card / Cash
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments (invoice_id);

-- Paid totals derived from the ledger (used by the rollup view)
CREATE OR REPLACE VIEW view_invoice_payments AS
SELECT i.id AS invoice_id,
       i.project_id,
       COALESCE(SUM(p.amount), 0.00) AS total_paid,
       i.amount_due - COALESCE(SUM(p.amount), 0.00) AS balance_due,
       i.due_date
FROM invoices i
LEFT JOIN payments p ON p.invoice_id = i.id
GROUP BY i.id, i.project_id, i.amount_due, i.due_date;

-- Recompute invoice status from the ledger (called by record_payment tool)
CREATE OR REPLACE FUNCTION recompute_invoice_status(invoice_uuid UUID) RETURNS VOID AS $$
DECLARE
    paid NUMERIC(12,2);
    due  NUMERIC(12,2);
    d    DATE;
BEGIN
    SELECT v.total_paid, v.balance_due, v.due_date INTO paid, due, d
    FROM view_invoice_payments v WHERE v.invoice_id = invoice_uuid;
    IF paid = 0 THEN
        UPDATE invoices SET status = CASE WHEN d < CURRENT_DATE THEN 'OVERDUE' ELSE 'UNPAID' END
        WHERE id = invoice_uuid;
    ELSIF due <= 0 THEN
        UPDATE invoices SET status = 'PAID' WHERE id = invoice_uuid;
    ELSE
        UPDATE invoices SET status = 'PARTIAL' WHERE id = invoice_uuid;
    END IF;
END $$ LANGUAGE plpgsql;
```

**Rule (ADR-2, Decision #2):** `create_invoice` computes `net_amount`, `gst_amount = net * gst_rate` (always), and `pst_amount = net * pst_rate` only when `pst_applicable` is true; `amount_due = net + gst + pst` — all in SQL against `company_profile`. `create_invoice` gains a `pst_applicable` param (default false).

### Task 4: `db/0010_quote_trail.sql`

**Objective:** CR reason taxonomy + quote revision/validity trail.

**Files:**
- Create: `db/0010_quote_trail.sql`

```sql
-- 0010_quote_trail.sql
ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS revision   INT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS status     VARCHAR(20) NOT NULL DEFAULT 'ACCEPTED',
        -- DRAFT / SENT / ACCEPTED / DECLINED / SUPERSEDED (Sheets parity)
    ADD COLUMN IF NOT EXISTS valid_until DATE,
    ADD COLUMN IF NOT EXISTS sent_at    TIMESTAMPTZ;

-- Existing rows are the accepted baseline -> ACCEPTED is the correct default.

ALTER TABLE change_orders
    ADD COLUMN IF NOT EXISTS reason VARCHAR(50);
        -- client_change / site_condition / owner_directed / other
```

**Rule (Sheets parity):** when a quote revision reaches `ACCEPTED`, n8n updates `projects.original_contract_value` from the accepted estimate amount (per 0004, project columns are the source of truth). `create_estimate` gains `revision` + `valid_until` params; prior revisions stay as history.

### Task 5: `db/0011_dashboard_views.sql`

**Objective:** Extend the financial rollup with tax, payments-ledger paid totals, labor cost, margin, retention held, overdue flags; add payroll/overdue/quote-follow-up views.

**Files:**
- Create: `db/0011_dashboard_views.sql`

```sql
-- 0011_dashboard_views.sql
-- Replaces the 0004 view (same name) with a tax-aware, ledger-driven version.
CREATE OR REPLACE VIEW view_project_financial_summary AS
SELECT
    p.id AS project_id, p.title AS project_name, p.status AS project_status,
    c.id AS customer_id, c.name AS customer_name, c.email AS customer_email,
    COALESCE(p.original_contract_value, 0.00) AS original_contract_value,
    COALESCE(co.approved_co_total, 0.00) AS approved_change_orders_total,
    COALESCE(p.revised_contract_value, 0.00) AS total_revised_contract_value,
    COALESCE(inv.total_invoiced, 0.00) AS total_invoiced,          -- gross (incl. tax)
    COALESCE(inv.total_paid, 0.00) AS total_paid,                  -- from payments ledger
    COALESCE(inv.total_invoiced, 0.00) - COALESCE(inv.total_paid, 0.00) AS balance_remaining,
    COALESCE(inv.retention_held, 0.00) AS retention_held,
    COALESCE(inv.overdue_amount, 0.00) AS overdue_amount,
    COALESCE(ts.total_labor_hours, 0.00) AS total_labor_hours,
    COALESCE(lc.total_labor_cost, 0.00) AS total_labor_cost,
    (COALESCE(p.revised_contract_value, 0.00) - COALESCE(lc.total_labor_cost, 0.00)) AS gross_margin
FROM projects p
JOIN customers c ON p.customer_id = c.id
LEFT JOIN (SELECT project_id, SUM(cost_impact) AS approved_co_total
           FROM change_orders WHERE approval_status = 'APPROVED' GROUP BY project_id) co ON p.id = co.project_id
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
LEFT JOIN (SELECT project_id, SUM(hours_worked) AS total_labor_hours
           FROM timesheets GROUP BY project_id) ts ON p.id = ts.project_id
LEFT JOIN (
    SELECT t.project_id, SUM(t.hours_worked * COALESCE(w.hourly_rate, 0)) AS total_labor_cost
    FROM timesheets t LEFT JOIN workers w ON w.id = t.worker_id
    GROUP BY t.project_id
) lc ON p.id = lc.project_id;

-- Payroll summary per run
CREATE OR REPLACE VIEW view_payroll_summary AS
SELECT r.id AS run_id, r.period_start, r.period_end, r.status,
       COUNT(e.id) AS workers, SUM(e.regular_hours) AS regular_hours,
       SUM(e.overtime_hours) AS overtime_hours, SUM(e.gross_pay) AS gross_pay,
       SUM(e.cpp + e.ei + e.wcb) AS deductions, SUM(e.net_pay) AS net_pay
FROM payroll_runs r LEFT JOIN payroll_entries e ON e.payroll_run_id = r.id
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
```

**Verify:** `SELECT * FROM view_project_financial_summary;` reconciles: `total_invoiced − total_paid = balance_remaining`; retention + unbilled + invoiced = contract (spot-check with seed data).

---

## 2. n8n gateway updates (`backend/n8n/workflows/voice-gateway.json`)

### Task 6: Company profile loader + de-hardcode branding

**Objective:** Every Code node reads branding from `company_profile`; no hardcoded URLs/colors/names remain.

**Files:**
- Modify: `backend/n8n/workflows/voice-gateway.json`

1. **New node `Load Company Profile`** (PostgreSQL query, placed after the Webhook): `SELECT * FROM company_profile WHERE id = 1;` merge its fields into the payload (`{{ $json }}`).
2. **`Render Estimate Approval Email`** — replace:
   - `const base = 'https://n8n2.ordrnow.com';` → `const base = $json.portal_base_url;`
   - inline `#2563eb`/`#16a34a` → `brand_accent_color` / `brand_success_color` from profile
   - add company name header + `email_from_name`
3. **`Render Change Order Approval Email`** — same replacements.
4. **`Format Spoken Result`** — `base` from `portal_base_url`; spoken lines unchanged.
5. **Gmail nodes** — set From name from `email_from_name` (header-level; SMTP account stays `GMAIL_USER`).

**Verify:** re-import workflow; trigger `get_estimate_approval_link`; confirm email HTML shows profile values, link uses `portal_base_url`.

### Task 7: New tool branches (gateway routing)

**Objective:** Route 5 new Vapi actions + tax-aware/reason-aware updates.

**Files:**
- Modify: `backend/n8n/workflows/voice-gateway.json`
- Modify: `backend/README.md` (routing table 12 → 17 rows)

New `Actions Sub-Router` cases:

| Action | Node chain |
|---|---|
| `record_payment` | Exec: `INSERT INTO payments ...` → Exec: `SELECT recompute_invoice_status($1)` → spoken confirm with new balance |
| `run_payroll` | Exec CTE: aggregate `timesheets` in period → join `workers` rates + `company_profile` rates → INSERT `payroll_runs` + `payroll_entries` (ON CONFLICT (period_start, period_end) DO UPDATE) → return `view_payroll_summary` row |
| `get_payroll_summary` | Exec: query `view_payroll_summary` (latest run or by period) |
| `add_worker` | Exec: INSERT `workers` (worker_code auto `W-###`), return worker |
| `get_dashboard_summary` | Exec: query `view_project_financial_summary` (+ optional `view_overdue_invoices` tail) |

Updated existing branches:

| Action | Change |
|---|---|
| `create_invoice` | SQL computes `net_amount`/`gst_amount`/`pst_amount` from `company_profile`; `amount_due` = gross; inserts `invoice_line_items`; optional `pst_applicable` param |
| `create_change_order` | accept `reason` param → `change_orders.reason` |
| `create_estimate` | accept `revision`, `valid_until`, `status` params; on ACCEPTED → update `projects.original_contract_value` |
| `send_customer_invoice` | add branded PDF attachment (Task 10) |

**Verify:** curl each new action against the webhook with a fake tool-call payload; check DB rows + spoken `results[]` (see §5 smoke tests).

### Task 8: Vapi assistant — new/updated tool schemas

**Files:**
- Modify: `backend/VAPI_ASSISTANT.md` (tool table + Section 4 JSON)
- Modify: `doc/SYSTEM_DESIGN.md` (§4, §11 — new tools, v1.3 note)

New tool JSON (add to assistant; all `server.url` → `https://n8n2.ordrnow.com/webhook/voice/gateway`):

```json
{
  "type": "function",
  "function": {
    "name": "record_payment",
    "description": "Records a payment received against an invoice and updates the invoice status.",
    "parameters": {
      "type": "object",
      "properties": {
        "invoice_number": { "type": "string", "description": "Invoice number, e.g. INV-1002" },
        "amount": { "type": "number", "description": "Payment amount received" },
        "payment_date": { "type": "string", "description": "Date received (YYYY-MM-DD); defaults to today" },
        "method": { "type": "string", "enum": ["E-transfer", "Cheque", "Credit card", "Cash", "Other"] }
      },
      "required": ["invoice_number", "amount"]
    }
  }
}
```

```json
{
  "type": "function",
  "function": {
    "name": "run_payroll",
    "description": "Computes payroll for the current (or given) period from logged timesheets and worker rates.",
    "parameters": {
      "type": "object",
      "properties": {
        "period_end": { "type": "string", "description": "Payroll period end date (YYYY-MM-DD); defaults to end of the current month" },
        "days": { "type": "number", "description": "Period length in days; defaults to the company payroll_period (monthly by default)" }
      }
    }
  }
}
```

Plus `get_payroll_summary`, `add_worker`, `get_dashboard_summary` (same pattern; schemas in `VAPI_ASSISTANT.md`). Updated: `create_invoice` (+ `pst_applicable` optional), `create_change_order` (+ `reason` enum), `create_estimate` (+ `revision`, `valid_until`).

Update the assistant system prompt (Section 6) with one added rule: *"Payments: after recording a payment, confirm the new balance. Payroll: run on request or the scheduled cadence."*

---

## 3. Branded PDF generation

### Task 9: n8n-native HTML→PDF (primary)

**Objective:** `send_customer_invoice` / approval emails carry a branded PDF attachment with no new services.

**Files:**
- Modify: `backend/n8n/workflows/voice-gateway.json` (`send_customer_invoice` chain: `..._lookup` → `Render Invoice HTML` → **new `Invoice to PDF`** (n8n HTML node, Conversion → PDF, Puppeteer) → `send_customer_invoice_email` (Gmail, PDF attachment))

All styling pulled from `company_profile` (colors, company name/address block, signature_name).

**Verify:** send a test invoice to Dave's email; open the attachment; confirm branding + math.

### Task 10: reportlab fallback (Drive archival, optional)

**Objective:** Keep the proven `make_invoice.py` pipeline alive against Postgres for Drive document archive.

**Files:**
- Create: `backend/scripts/make_invoice_pg.py` (port of `~/.hermes/scripts/construction/make_invoice.py`; reads rows via psycopg + `company_profile` for branding; uploads to Drive; `--send` emails via Gmail)
- Note: `~/.hermes/venv` already has reportlab.

**Verify:** `python make_invoice_pg.py --type invoice --invoice-number INV-1002` → PDF in Drive with profile branding.

---

## 4. Recurring automation (n8n Schedule Trigger)

### Task 11: Three scheduled workflows

**Objective:** Daily overdue check, daily quote follow-up, monthly payroll digest — self-contained on the VPS (no Hermes dependency).

**Files:**
- Create: `backend/n8n/workflows/daily-overdue-check.json`
- Create: `backend/n8n/workflows/daily-quote-followup.json`
- Create: `backend/n8n/workflows/monthly-payroll-digest.json`

| Workflow | Trigger | SQL source | Delivery |
|---|---|---|---|
| `daily-overdue-check` | Schedule daily 08:00 | `view_overdue_invoices` | Gmail to Dave (`company_profile.email_from`), summary of OVERDUE/DUE_SOON |
| `daily-quote-followup` | Schedule daily 09:00 | `view_quote_followups` | Gmail to Dave, list of expired quotes to chase |
| `monthly-payroll-digest` | Schedule day-of-month 07:00 (`payroll_day_of_month` from profile) | `run_payroll` SQL then `view_payroll_summary` | Gmail to Dave (DRAFT run; Dave approves) |

**Alternative:** Hermes cron equivalents (note: from a TUI session cron delivery is local-only — must target a gateway platform to reach Dave).

**Verify:** import + activate; run each manually once in n8n; confirm email arrives with correct rows.

---

## 5. Documentation + cleanup

### Task 12: Docs

- `backend/DEPLOY.md`: add `0007`–`0011` to the fresh-install order; note `email_from` lives in `company_profile` (GMAIL_USER stays the SMTP auth account); document `portal_base_url` consistency with the n8n instance URL.
- `backend/README.md`: routing table 12 → 17 tools; new env note; payroll/tax/payments sections.
- `backend/VAPI_ASSISTANT.md`: new tool JSON; fix §7 `mobile/src/config.ts` → `mobile-flutter/lib/config.dart` (existing inconsistency).
- `doc/SYSTEM_DESIGN.md`: bump to v1.3 — add `company_profile`, workers/payroll, payments, tax, quote trail; update §4 tool list (8 → 13) and §11 milestones.

### Task 13: Seed + verification scripts

- `db/0012_seed_v2.sql` (optional): demo workers (Mike Johnson framer $38 — matches Sheets), a payroll run, a payment, a SENT quote past validity — so every new view returns rows.
- `db/0013_verification.sql` (idempotency-test style, self-rolled-back like `0002`): assert (a) `company_profile` has exactly 1 row, (b) `amount_due = net + gst + pst` for all invoices, (c) rollup reconciles `invoiced − paid = balance`, (d) replayed `record_payment`/`run_payroll` don't double-insert (unique keys).

---

## 6. Verification checklist (end-to-end)

- [ ] `0007`–`0011` apply cleanly + re-apply idempotently; `0013_verification.sql` passes
- [ ] `SELECT * FROM company_profile` → 1 row, branding values correct
- [ ] No `n8n2.ordrnow.com` / brand-color / company-name literals left in `voice-gateway.json` Code nodes
- [ ] curl smoke tests per action (webhook `POST /voice/gateway` with fake `message.toolCalls[0]`):
  - `record_payment` → payment row + invoice status flips (UNPAID→PARTIAL→PAID)
  - `run_payroll` → payroll_runs/entries rows; `view_payroll_summary` matches hand calc
  - `get_dashboard_summary` → margin + retention + overdue populated
  - `create_invoice` → tax computed from profile; `amount_due = net + gst + pst`
  - `create_estimate` with revision → `original_contract_value` updates on ACCEPTED
- [ ] Approval email renders profile branding; invoice email has branded PDF attachment
- [ ] All 3 scheduled workflows active; each fired once manually with correct output
- [ ] Voice test: "record a $5,000 e-transfer on INV-1002" and "run payroll for the last two weeks" on a device

---

## 7. Risks, tradeoffs, open questions

### Risks
| Risk | Mitigation |
|---|---|
| n8n HTML→PDF (Puppeteer) unavailable in the docker image | Fall back to Task 10 reportlab pipeline; HTML email still works today |
| `amount_due` semantic change (net → gross) breaks existing statement text / tool output | Update `Format Spoken Result` + `get_project_statement` copy in same change; run 0013 assertions |
| Live Supabase is already in use (seed data) | Migrations are additive + idempotent; apply in DEPLOY.md order; 0009 backfills before NOT NULL |
| `email_from` ≠ authenticated SMTP account → Gmail rejects | Keep `email_from` = `support.ordrnow@gmail.com` (same as `GMAIL_USER`); validate at seed |
| View replacement (0011) shadows 0004 version | Same view name on purpose; 0011 ships with the reconciliation assertions |
| ~~Workers ↔ timesheets join is by name (no FK today)~~ | **Resolved during implementation** — `timesheets.worker_id` FK (ON DELETE RESTRICT) replaces the name join; `log_timesheet` resolves name/code/id → `worker_id` |

### Resolved decisions
| # | Decision |
|---|---|
| 1 | **Branding:** full legal name + address + phone in `company_profile` |
| 2 | **Tax:** GST 5% always; PST 7% per-invoice `pst_applicable` flag |
| 3 | **PDF:** n8n HTML→PDF primary; reportlab fallback only if Puppeteer unavailable |
| 4 | **Payroll:** monthly cadence, DRAFT run → Dave approves |
| 5 | **Scope:** all 5 new voice tools |

### Defaults applied (editable anytime in `company_profile`)
- **Email identity:** From name "Ireh Construction", sending account `support.ordrnow@gmail.com` (unchanged).
- **Brand colors:** navy `#1a3a5c` primary, blue `#2563eb` accent, green `#16a34a` success.

### Received from Dave
- Legal name: **Ireh Construction** · 1951 Kaptey Ave, Coquitlam BC V3K 5Z7 · 778-994-6602 (seeded into `company_profile` defaults).
