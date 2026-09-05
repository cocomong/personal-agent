-- 0023_invoice_presentation.sql
-- Invoice presentation + capture build (2026-09-05, user decisions):
--   * company_profile.gst_reg_number / pst_reg_number  - tax numbers shown on invoices
--   * company_profile.payment_instructions             - free-text "how to pay" block
--   * customers.street_address/city/province/postal_code - structured bill-to address
--   * invoices.billing_percentage / billed_basis       - snapshot of what an invoice
--     billed (x% of revised contract value at creation), so the descriptive line on
--     the invoice stays accurate if the contract changes later. NULL on legacy rows
--     (they render a plain type label instead).
-- All nullable: rendered only when present. Idempotent (IF NOT EXISTS).

ALTER TABLE company_profile
    ADD COLUMN IF NOT EXISTS gst_reg_number      VARCHAR(50),
    ADD COLUMN IF NOT EXISTS pst_reg_number      VARCHAR(50),
    ADD COLUMN IF NOT EXISTS payment_instructions TEXT;

ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS street_address TEXT,
    ADD COLUMN IF NOT EXISTS city           VARCHAR(100),
    ADD COLUMN IF NOT EXISTS province       VARCHAR(50),
    ADD COLUMN IF NOT EXISTS postal_code    VARCHAR(20);

ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS billing_percentage NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS billed_basis       NUMERIC(12,2);

COMMENT ON COLUMN invoices.billing_percentage IS
    'Snapshot: percent of revised contract value billed at creation';
COMMENT ON COLUMN invoices.billed_basis IS
    'Snapshot: revised contract value the invoice percentage was applied to';
COMMENT ON COLUMN company_profile.payment_instructions IS
    'Free-text how-to-pay block shown on client invoices';
