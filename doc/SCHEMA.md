# Database Schema — live (generated)

> **Generated 2026-09-05 from the live production DB** (n8n2.ordrnow.com, container `n8n-compose-postgres-1`, db `postgres`, PostgreSQL 17). Reflects migrations 0001–0021 applied. This file is machine-generated, not hand-maintained — after any schema change, re-run the extraction in the Appendix and regenerate.

## Conventions
- Every business table PK is `id UUID DEFAULT uuid_generate_v4()` (uuid-ossp).
- Write tools carry a `tool_call_id` UNIQUE column (ADR-3): replayed Vapi tool calls `ON CONFLICT (tool_call_id) DO NOTHING` instead of double-inserting.
- `company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id)` on every directly-scoped table (Step 2, migration 0019). `DEFAULT 1` = the original Ireh row; Step 3 (scoped gateway) drops the default and writes company_id explicitly. `company_profile.id` is a sequence (`company_profile_id_seq`, starts at 2) — one profile per company.
- Invoice numbers are per-company sequential: `invoice_prefix + LPAD(invoice_last_number, 4)` (migration 0021), e.g. INV-0001. Legacy timestamp numbers are grandfathered.
- Outbound invoice emails (preview / client / resend / reject) are audited in `invoice_email_log` (0021). `invoices.email_sent_at` = first client send; `last_client_html` = the canonical client HTML stored at preview time (approve emails that copy, so previewed == sent).
- Children that inherit tenancy via a parent's `project_id` (estimates, change_orders, timesheets, invoice_line_items, payments, payroll_entries) carry no company_id column.
- Worker identity: `workers.id` (uuid) is the FK target; `worker_code` (W-###) is a per-company unique display/code handle — two companies may each have a W-001.

## Company & tenancy

### company_profile

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `smallint` | PK, NOT NULL, default (nextval('company_profile_id_seq'::regclass)) |
| `company_name` | `character varying(255)` | NOT NULL, default 'Ireh Construction' |
| `legal_name` | `character varying(255)` | NOT NULL, default 'Ireh Construction' |
| `street_address` | `text` | NOT NULL, default '1951 Kaptey Ave' |
| `city` | `character varying(100)` | NOT NULL, default 'Coquitlam' |
| `province` | `character varying(50)` | NOT NULL, default 'BC' |
| `postal_code` | `character varying(20)` | NOT NULL, default 'V3K 5Z7' |
| `phone` | `character varying(50)` | NOT NULL, default '778-994-6602' |
| `email_from` | `character varying(255)` | NOT NULL, default 'support.ordrnow@gmail.com' |
| `email_from_name` | `character varying(255)` | NOT NULL, default 'Ireh Construction' |
| `website` | `character varying(255)` |  |
| `portal_base_url` | `character varying(255)` | NOT NULL, default 'https://n8n2.ordrnow.com' |
| `signature_name` | `character varying(255)` | NOT NULL, default 'Dave' |
| `invoice_prefix` | `character varying(20)` | NOT NULL, default 'INV-' |
| `quote_prefix` | `character varying(20)` | NOT NULL, default 'QUO-' |
| `change_order_prefix` | `character varying(20)` | NOT NULL, default 'CR-' |
| `project_prefix` | `character varying(20)` | NOT NULL, default 'PRJ-' |
| `brand_primary_color` | `character varying(9)` | NOT NULL, default '#1a3a5c' |
| `brand_accent_color` | `character varying(9)` | NOT NULL, default '#2563eb' |
| `brand_success_color` | `character varying(9)` | NOT NULL, default '#16a34a' |
| `gst_rate` | `numeric(5,4)` | NOT NULL, default 0.05 |
| `pst_rate` | `numeric(5,4)` | NOT NULL, default 0.07 |
| `retention_rate` | `numeric(5,4)` | NOT NULL, default 0.10 |
| `invoice_due_days` | `integer` | NOT NULL, default 30 |
| `cpp_rate` | `numeric(5,4)` | NOT NULL, default 0.0595 |
| `ei_rate` | `numeric(5,4)` | NOT NULL, default 0.0163 |
| `wcb_rate` | `numeric(5,4)` | NOT NULL, default 0.0325 |
| `payroll_period` | `character varying(20)` | NOT NULL, default 'MONTHLY' |
| `payroll_day_of_month` | `integer` | NOT NULL, default 1 |
| `ot_multiplier` | `numeric(3,2)` | NOT NULL, default 1.5 |
| `created_at` | `timestamp with time zone` | NOT NULL, default CURRENT_TIMESTAMP |
| `updated_at` | `timestamp with time zone` | NOT NULL, default CURRENT_TIMESTAMP |
| `briefing_time` | `time without time zone` | NOT NULL, default '07:00:00' |
| `pm_name` | `character varying(255)` | PM full name, captured by the first-run onboarding wizard |
| `pm_preferred_name` | `character varying(255)` | How the PM wants to be addressed daily (e.g. Dave, boss) |
| `setup_completed_at` | `timestamp with time zone` | NULL until onboarding completes; set once, preserved on re-runs |
| `created_by_user` | `uuid` |  |
| `invoice_last_number` | `integer` | NOT NULL, default 0 |
- FK: `created_by_user` → `users(id)` (ON DELETE NO ACTION)

*created in 0007_company_profile; extended in 0014_schedule, 0016_onboarding, 0019_tenant_columns, 0021_invoice_fixes*

### users

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `google_sub` | `character varying(255)` | NOT NULL |
| `email` | `character varying(255)` | NOT NULL |
| `name` | `character varying(255)` |  |
| `company_id` | `smallint` | tenant |
| `created_at` | `timestamp with time zone` | NOT NULL, default CURRENT_TIMESTAMP |
| `last_login_at` | `timestamp with time zone` |  |
- FK: `company_id` → `company_profile(id)` (ON DELETE SET NULL)
- UNIQUE constraint `users_email_key` (`email`)
- UNIQUE constraint `users_google_sub_key` (`google_sub`)
- index `idx_users_company`

*created in 0017_accounts*

## Customers & projects

### customers

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `name` | `character varying(255)` | NOT NULL |
| `company_name` | `character varying(255)` |  |
| `email` | `character varying(255)` | NOT NULL |
| `phone` | `character varying(50)` |  |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
| `company_id` | `smallint` | NOT NULL, default 1, tenant |
- FK: `company_id` → `company_profile(id)` (ON DELETE NO ACTION)
- index `idx_customers_company`
- UNIQUE index `uq_customers_company_email` (per-company unique; Step 2)

*created in 0001_init; extended in 0019_tenant_columns*

### projects

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `customer_id` | `uuid` |  |
| `title` | `character varying(255)` | NOT NULL |
| `site_address` | `text` | NOT NULL |
| `original_contract_value` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `revised_contract_value` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `status` | `character varying(50)` | default 'ACTIVE' |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
| `baseline_status` | `character varying(50)` | NOT NULL, default 'PENDING' |
| `baseline_approved_at` | `timestamp with time zone` |  |
| `baseline_approved_by` | `character varying(50)` |  |
| `baseline_approval_method` | `character varying(50)` |  |
| `baseline_approval_token` | `uuid` | default uuid_generate_v4() |
| `baseline_signer_name` | `character varying(255)` |  |
| `completed_at` | `date` |  |
| `scheduled_start` | `date` |  |
| `target_completion` | `date` |  |
| `company_id` | `smallint` | NOT NULL, default 1, tenant |
- FK: `company_id` → `company_profile(id)` (ON DELETE NO ACTION)
- FK: `customer_id` → `customers(id)` (ON DELETE CASCADE)
- index `idx_projects_company`
- index `idx_projects_customer`

*created in 0001_init; extended in 0005_customer_approval, 0006_signer_name, 0014_schedule, 0019_tenant_columns*

## Invoicing & payments

### invoices

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `project_id` | `uuid` |  |
| `invoice_number` | `character varying(100)` | NOT NULL |
| `invoice_type` | `character varying(50)` | NOT NULL |
| `amount_due` | `numeric(12,2)` | NOT NULL |
| `holdback_amount` | `numeric(12,2)` | default 0.00 |
| `status` | `character varying(50)` | default 'UNPAID' |
| `issued_date` | `date` | default CURRENT_DATE |
| `due_date` | `date` | NOT NULL |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
| `net_amount` | `numeric(12,2)` | NOT NULL |
| `gst_amount` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `pst_amount` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `pst_applicable` | `boolean` | NOT NULL, default false |
| `email_sent_at` | `timestamp with time zone` |  |
| `company_id` | `smallint` | NOT NULL, default 1, tenant |
| `description` | `text` |  |
| `last_client_html` | `text` | Canonical client HTML stored at preview time; approve workflow emails this copy |
- FK: `company_id` → `company_profile(id)` (ON DELETE NO ACTION)
- FK: `project_id` → `projects(id)` (ON DELETE CASCADE)
- index `idx_invoices_company`
- index `idx_invoices_project`
- UNIQUE index `uq_invoices_company_invoice_number` (per-company unique; Step 2)

*created in 0001_init; extended in 0009_tax_payments, 0018_invoice_send, 0019_tenant_columns, 0021_invoice_fixes*

### invoice_line_items

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `invoice_id` | `uuid` |  |
| `source_type` | `character varying(50)` | NOT NULL |
| `source_id` | `uuid` |  |
| `description` | `text` | NOT NULL |
| `amount` | `numeric(12,2)` | NOT NULL |
- FK: `invoice_id` → `invoices(id)` (ON DELETE CASCADE)
- index `idx_invoice_line_items_invoice`

*created in 0001_init*

### payments

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `invoice_id` | `uuid` | NOT NULL |
| `payment_date` | `date` | NOT NULL, default CURRENT_DATE |
| `amount` | `numeric(12,2)` | NOT NULL |
| `method` | `character varying(50)` |  |
| `notes` | `text` |  |
| `tool_call_id` | `character varying(100)` |  |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
- FK: `invoice_id` → `invoices(id)` (ON DELETE CASCADE)
- CHECK `payments_amount_check`: `CHECK ((amount > (0)::numeric))`
- UNIQUE constraint `payments_tool_call_id_key` (`tool_call_id`)
- index `idx_payments_invoice`

*created in 0009_tax_payments*

### invoice_email_log

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `invoice_id` | `uuid` | NOT NULL |
| `company_id` | `smallint` | NOT NULL, default 1, tenant |
| `kind` | `character varying(20)` | NOT NULL |
| `recipient` | `character varying(255)` |  |
| `message_id` | `character varying(255)` |  |
| `created_at` | `timestamp with time zone` | NOT NULL, default CURRENT_TIMESTAMP |
- FK: `company_id` → `company_profile(id)` (ON DELETE NO ACTION)
- FK: `invoice_id` → `invoices(id)` (ON DELETE CASCADE)
- index `idx_invoice_email_log_company`
- index `idx_invoice_email_log_invoice`

*created in 0021_invoice_fixes*

## Quotes & change orders

### estimates

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `project_id` | `uuid` |  |
| `division_code` | `character varying(50)` | NOT NULL |
| `scope_description` | `text` | NOT NULL |
| `allocated_amount` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
| `revision` | `integer` | NOT NULL, default 1 |
| `status` | `character varying(20)` | NOT NULL, default 'ACCEPTED' |
| `valid_until` | `date` |  |
| `sent_at` | `timestamp with time zone` |  |
- FK: `project_id` → `projects(id)` (ON DELETE CASCADE)
- index `idx_estimates_project`

*created in 0001_init; extended in 0010_quote_trail*

### change_orders

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `project_id` | `uuid` |  |
| `change_order_number` | `integer` | NOT NULL |
| `description` | `text` | NOT NULL |
| `cost_impact` | `numeric(12,2)` | NOT NULL |
| `schedule_impact_days` | `integer` | default 0 |
| `approval_status` | `character varying(50)` | default 'PENDING' |
| `approved_at` | `timestamp with time zone` |  |
| `tool_call_id` | `character varying(100)` |  |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
| `approval_token` | `uuid` | default uuid_generate_v4() |
| `sent_for_approval_at` | `timestamp with time zone` |  |
| `approval_method` | `character varying(50)` |  |
| `approved_by` | `character varying(50)` |  |
| `signer_name` | `character varying(255)` |  |
| `reason` | `character varying(50)` |  |
- FK: `project_id` → `projects(id)` (ON DELETE CASCADE)
- UNIQUE constraint `change_orders_tool_call_id_key` (`tool_call_id`)
- index `idx_change_orders_project`

*created in 0001_init; extended in 0005_customer_approval, 0006_signer_name, 0010_quote_trail*

## Schedule & devices

### schedule_items

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `project_id` | `uuid` |  |
| `type` | `character varying(50)` | NOT NULL |
| `title` | `character varying(255)` | NOT NULL |
| `description` | `text` |  |
| `due_date` | `date` |  |
| `due_time` | `time without time zone` |  |
| `status` | `character varying(50)` | NOT NULL, default 'PENDING' |
| `priority` | `character varying(20)` | NOT NULL, default 'NORMAL' |
| `assigned_to` | `character varying(255)` |  |
| `reminder_days` | `integer` | NOT NULL, default 0 |
| `reminder_sent_at` | `timestamp with time zone` |  |
| `completed_at` | `timestamp with time zone` |  |
| `created_at` | `timestamp with time zone` | NOT NULL, default CURRENT_TIMESTAMP |
| `company_id` | `smallint` | NOT NULL, default 1, tenant |
- FK: `company_id` → `company_profile(id)` (ON DELETE NO ACTION)
- FK: `project_id` → `projects(id)` (ON DELETE CASCADE)
- index `idx_schedule_items_company`
- index `idx_schedule_items_due`
- index `idx_schedule_items_project`

*created in 0014_schedule; extended in 0019_tenant_columns*

### device_tokens

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `token` | `character varying(512)` | NOT NULL |
| `platform` | `character varying(20)` | NOT NULL, default 'android' |
| `device_name` | `character varying(255)` |  |
| `last_seen_at` | `timestamp with time zone` | NOT NULL, default CURRENT_TIMESTAMP |
| `created_at` | `timestamp with time zone` | NOT NULL, default CURRENT_TIMESTAMP |
| `company_id` | `smallint` | NOT NULL, default 1, tenant |
- FK: `company_id` → `company_profile(id)` (ON DELETE NO ACTION)
- UNIQUE constraint `device_tokens_token_key` (`token`)
- index `idx_device_tokens_company`
- index `idx_device_tokens_platform`

*created in 0015_device_tokens; extended in 0019_tenant_columns*

## Workers & payroll

### workers

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `worker_code` | `character varying(20)` |  |
| `name` | `character varying(255)` | NOT NULL |
| `trade` | `character varying(100)` |  |
| `hourly_rate` | `numeric(10,2)` | NOT NULL, default 0.00 |
| `overtime_rate` | `numeric(10,2)` |  |
| `active` | `boolean` | NOT NULL, default true |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
| `company_id` | `smallint` | NOT NULL, default 1, tenant |
- FK: `company_id` → `company_profile(id)` (ON DELETE NO ACTION)
- index `idx_workers_active`
- index `idx_workers_company`
- UNIQUE index `uq_workers_company_worker_code` (per-company unique; Step 2)

*created in 0001_init; extended in 0019_tenant_columns*

### timesheets

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `project_id` | `uuid` |  |
| `worker_id` | `uuid` | NOT NULL |
| `hours_worked` | `numeric(5,2)` | NOT NULL |
| `work_description` | `text` |  |
| `date_worked` | `date` | NOT NULL, default CURRENT_DATE |
| `tool_call_id` | `character varying(100)` |  |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
| `overtime_hours` | `numeric(5,2)` | NOT NULL, default 0.00 |
- FK: `project_id` → `projects(id)` (ON DELETE CASCADE)
- FK: `worker_id` → `workers(id)` (ON DELETE RESTRICT)
- UNIQUE constraint `timesheets_tool_call_id_key` (`tool_call_id`)
- index `idx_timesheets_project`
- index `idx_timesheets_worker`

*created in 0001_init; extended in 0008_workers_payroll*

### payroll_runs

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `period_start` | `date` | NOT NULL |
| `period_end` | `date` | NOT NULL |
| `status` | `character varying(20)` | NOT NULL, default 'DRAFT' |
| `notes` | `text` |  |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
| `company_id` | `smallint` | NOT NULL, default 1, tenant |
- FK: `company_id` → `company_profile(id)` (ON DELETE NO ACTION)
- index `idx_payroll_runs_company`
- UNIQUE index `uq_payroll_runs_company_period` (per-company unique; Step 2)

*created in 0008_workers_payroll; extended in 0019_tenant_columns*

### payroll_entries

| Column | Type | Flags / default |
|--------|------|-----------------|
| `id` | `uuid` | PK, NOT NULL, default uuid_generate_v4() |
| `payroll_run_id` | `uuid` | NOT NULL |
| `worker_id` | `uuid` | NOT NULL |
| `regular_hours` | `numeric(8,2)` | NOT NULL, default 0.00 |
| `overtime_hours` | `numeric(8,2)` | NOT NULL, default 0.00 |
| `hourly_rate` | `numeric(10,2)` | NOT NULL |
| `gross_pay` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `cpp` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `ei` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `wcb` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `net_pay` | `numeric(12,2)` | NOT NULL, default 0.00 |
| `hours_by_project` | `jsonb` |  |
| `created_at` | `timestamp with time zone` | default CURRENT_TIMESTAMP |
- FK: `payroll_run_id` → `payroll_runs(id)` (ON DELETE CASCADE)
- FK: `worker_id` → `workers(id)` (ON DELETE NO ACTION)
- UNIQUE constraint `payroll_entries_payroll_run_id_worker_id_key` (`payroll_run_id`, `worker_id`)
- index `idx_payroll_entries_run`
- index `idx_payroll_entries_worker`

*created in 0008_workers_payroll*

## Views

### view_invoice_payments

Columns: `invoice_id`, `project_id`, `total_paid`, `balance_due`, `due_date`

*created in 0009_tax_payments*

```sql
SELECT i.id AS invoice_id,
    i.project_id,
    COALESCE(sum(p.amount), 0.00) AS total_paid,
    (i.amount_due - COALESCE(sum(p.amount), 0.00)) AS balance_due,
    i.due_date
   FROM (invoices i
     LEFT JOIN payments p ON ((p.invoice_id = i.id)))
  GROUP BY i.id, i.project_id, i.amount_due, i.due_date;
```

### view_overdue_invoices

Columns: `invoice_number`, `project_id`, `project_name`, `customer_name`, `customer_email`, `amount_due`, `total_paid`, `balance_due`, `due_date`, `status`, `bucket`

*created in 0011_dashboard_views*

```sql
SELECT i.invoice_number,
    i.project_id,
    p.title AS project_name,
    c.name AS customer_name,
    c.email AS customer_email,
    i.amount_due,
    vp.total_paid,
    vp.balance_due,
    i.due_date,
    i.status,
        CASE
            WHEN (i.due_date < CURRENT_DATE) THEN 'OVERDUE'::text
            WHEN (i.due_date <= (CURRENT_DATE + 7)) THEN 'DUE_SOON'::text
            ELSE 'OK'::text
        END AS bucket
   FROM (((invoices i
     JOIN projects p ON ((p.id = i.project_id)))
     JOIN customers c ON ((c.id = p.customer_id)))
     JOIN view_invoice_payments vp ON ((vp.invoice_id = i.id)))
  WHERE ((i.status)::text <> 'PAID'::text);
```

### view_payroll_summary

Columns: `run_id`, `period_start`, `period_end`, `status`, `workers`, `regular_hours`, `overtime_hours`, `gross_pay`, `deductions`, `net_pay`

*created in 0011_dashboard_views*

```sql
SELECT r.id AS run_id,
    r.period_start,
    r.period_end,
    r.status,
    count(e.id) AS workers,
    sum(e.regular_hours) AS regular_hours,
    sum(e.overtime_hours) AS overtime_hours,
    sum(e.gross_pay) AS gross_pay,
    sum(((e.cpp + e.ei) + e.wcb)) AS deductions,
    sum(e.net_pay) AS net_pay
   FROM (payroll_runs r
     LEFT JOIN payroll_entries e ON ((e.payroll_run_id = r.id)))
  GROUP BY r.id, r.period_start, r.period_end, r.status;
```

### view_project_financial_summary

Columns: `project_id`, `project_name`, `project_status`, `customer_id`, `customer_name`, `customer_email`, `original_contract_value`, `approved_change_orders_total`, `total_revised_contract_value`, `total_invoiced`, `total_paid`, `balance_remaining`, `remaining_unbilled_contract`, `retention_held`, `overdue_amount`, `total_labor_hours`, `total_labor_cost`, `gross_margin`

*created in 0001_init*

```sql
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
    (COALESCE(p.revised_contract_value, 0.00) - COALESCE(inv.total_paid, 0.00)) AS balance_remaining,
    (COALESCE(p.revised_contract_value, 0.00) - COALESCE(inv.total_invoiced, 0.00)) AS remaining_unbilled_contract,
    COALESCE(inv.retention_held, 0.00) AS retention_held,
    COALESCE(inv.overdue_amount, 0.00) AS overdue_amount,
    COALESCE(ts.total_labor_hours, 0.00) AS total_labor_hours,
    COALESCE(lc.total_labor_cost, 0.00) AS total_labor_cost,
    (COALESCE(p.revised_contract_value, 0.00) - COALESCE(lc.total_labor_cost, 0.00)) AS gross_margin
   FROM (((((projects p
     JOIN customers c ON ((p.customer_id = c.id)))
     LEFT JOIN ( SELECT change_orders.project_id,
            sum(change_orders.cost_impact) AS approved_co_total
           FROM change_orders
          WHERE ((change_orders.approval_status)::text = 'APPROVED'::text)
          GROUP BY change_orders.project_id) co ON ((p.id = co.project_id)))
     LEFT JOIN ( SELECT i.project_id,
            sum(i.amount_due) AS total_invoiced,
            sum(vp.total_paid) AS total_paid,
            sum(
                CASE
                    WHEN ((i.status)::text <> 'PAID'::text) THEN i.holdback_amount
                    ELSE 0.00
                END) AS retention_held,
            sum(
                CASE
                    WHEN ((i.status)::text = 'OVERDUE'::text) THEN vp.balance_due
                    ELSE 0.00
                END) AS overdue_amount
           FROM (invoices i
             JOIN view_invoice_payments vp ON ((vp.invoice_id = i.id)))
          GROUP BY i.project_id) inv ON ((p.id = inv.project_id)))
     LEFT JOIN ( SELECT timesheets.project_id,
            sum(timesheets.hours_worked) AS total_labor_hours
           FROM timesheets
          GROUP BY timesheets.project_id) ts ON ((p.id = ts.project_id)))
     LEFT JOIN ( SELECT t.project_id,
            sum((t.hours_worked * COALESCE(w.hourly_rate, 0.00))) AS total_labor_cost
           FROM (timesheets t
             LEFT JOIN workers w ON ((w.id = t.worker_id)))
          GROUP BY t.project_id) lc ON ((p.id = lc.project_id)));
```

### view_quote_followups

Columns: `id`, `project_id`, `project_name`, `customer_name`, `customer_email`, `scope_description`, `revision`, `valid_until`, `amount`

*created in 0011_dashboard_views*

```sql
SELECT e.id,
    e.project_id,
    p.title AS project_name,
    c.name AS customer_name,
    c.email AS customer_email,
    e.scope_description,
    e.revision,
    e.valid_until,
    COALESCE(e.allocated_amount, 0.00) AS amount
   FROM ((estimates e
     JOIN projects p ON ((p.id = e.project_id)))
     JOIN customers c ON ((c.id = p.customer_id)))
  WHERE (((e.status)::text = 'SENT'::text) AND (e.valid_until IS NOT NULL) AND (e.valid_until < CURRENT_DATE));
```

### view_schedule

Columns: `project_id`, `project_name`, `type`, `title`, `due_date`, `due_time`, `status`, `priority`

*created in 0014_schedule*

```sql
SELECT si.project_id,
    p.title AS project_name,
    si.type,
    si.title,
    si.due_date,
    si.due_time,
    si.status,
    si.priority
   FROM (schedule_items si
     LEFT JOIN projects p ON ((p.id = si.project_id)))
UNION ALL
 SELECT i.project_id,
    p.title AS project_name,
    'invoice_due'::text AS type,
    (i.invoice_number)::text AS title,
    i.due_date,
    NULL::time without time zone AS due_time,
        CASE
            WHEN ((i.status)::text = 'PAID'::text) THEN 'DONE'::text
            ELSE 'PENDING'::text
        END AS status,
        CASE
            WHEN ((i.status)::text = 'OVERDUE'::text) THEN 'HIGH'::text
            ELSE 'NORMAL'::text
        END AS priority
   FROM (invoices i
     JOIN projects p ON ((p.id = i.project_id)))
  WHERE ((i.status)::text <> 'DRAFT'::text)
UNION ALL
 SELECT e.project_id,
    p.title AS project_name,
    'quote_expiry'::text AS type,
    (e.division_code)::text AS title,
    e.valid_until AS due_date,
    NULL::time without time zone AS due_time,
    'PENDING'::text AS status,
    'NORMAL'::text AS priority
   FROM (estimates e
     JOIN projects p ON ((p.id = e.project_id)))
  WHERE (((e.status)::text = 'SENT'::text) AND (e.valid_until IS NOT NULL))
UNION ALL
 SELECT p.id AS project_id,
    p.title AS project_name,
    'lien_deadline'::text AS type,
    'Lien filing deadline (45d)'::text AS title,
    ((p.completed_at + '45 days'::interval))::date AS due_date,
    NULL::time without time zone AS due_time,
    'PENDING'::text AS status,
    'HIGH'::text AS priority
   FROM projects p
  WHERE (p.completed_at IS NOT NULL)
UNION ALL
 SELECT p.id AS project_id,
    p.title AS project_name,
    'holdback_release'::text AS type,
    'Holdback release (55d)'::text AS title,
    ((p.completed_at + '55 days'::interval))::date AS due_date,
    NULL::time without time zone AS due_time,
    'PENDING'::text AS status,
    'HIGH'::text AS priority
   FROM projects p
  WHERE (p.completed_at IS NOT NULL);
```

## Functions

- `fn_refresh_invoice_statuses()` → `integer`  (created in 0021_invoice_fixes)
- `fn_run_payroll(p_end date, p_days integer)` → `TABLE(run_id uuid, period_start date, period_end date, status character varying, workers bigint, regular_hours numeric, overtime_hours numeric, gross_pay numeric, deductions numeric, net_pay numeric)`  (created in 0008_workers_payroll)
- `recompute_invoice_status(invoice_uuid uuid)` → `void`  (created in 0009_tax_payments)
- `uuid_generate_v1()` → `uuid`  (created in ?)
- `uuid_generate_v1mc()` → `uuid`  (created in ?)
- `uuid_generate_v3(namespace uuid, name text)` → `uuid`  (created in ?)
- `uuid_generate_v4()` → `uuid`  (created in ?)
- `uuid_generate_v5(namespace uuid, name text)` → `uuid`  (created in ?)
- `uuid_nil()` → `uuid`  (created in ?)
- `uuid_ns_dns()` → `uuid`  (created in ?)
- `uuid_ns_oid()` → `uuid`  (created in ?)
- `uuid_ns_url()` → `uuid`  (created in ?)
- `uuid_ns_x500()` → `uuid`  (created in ?)

## Sequences

- `company_profile_id_seq`

## Un-grouped tables: invoice_email_log

## Appendix — how to regenerate

1. Extract the catalog: run the extraction SQL in this repo's history (`/tmp` copy lives with the generator) against the live DB via
   `ssh ubuntu@n8n2.ordrnow.com` → `sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -tA -q -v ON_ERROR_STOP=1` (stdin). Sections: TABLES / COLUMNS / CONSTRAINTS / INDEXES / VIEWS / FUNCTIONS / SEQUENCES, each a JSON array on `==NAME==` markers.
2. Regenerate this file (markdown assembly + migration provenance from `db/*.sql`).
3. Commit: the header date and contents must match the applied migrations.
