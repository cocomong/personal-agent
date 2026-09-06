-- 0025_billing_change_orders.sql
-- Simple billing model (user decision 2026-09-06):
--   * Progress/deposit/final invoices bill a percentage of the ORIGINAL contract
--     value (the number the customer signed) - no moving base, no drift.
--   * Approved change orders are billed at 100% of their approved amount when the
--     PM bills them: a CHANGE_ORDER invoice itemizes every approved, not-yet-billed
--     CO as an invoice_line_items row (source_type 'change_order', source_id = CO).
--   * Billed status is DERIVED from issued invoice lines (never a stored counter):
--     a CO counts as billed when any issued invoice (status <> 'DRAFT') has a line
--     referencing it. DRAFT invoices do not claim a CO, so an abandoned preview
--     never blocks re-invoicing; a send-time duplicate check on the approve side
--     stops two issued invoices from ever claiming the same CO.
-- Idempotent (IF NOT EXISTS).

-- One CO may appear only once per invoice (integrity + idempotent creation).
CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_line_items_source
    ON invoice_line_items (invoice_id, source_type, source_id)
    WHERE source_id IS NOT NULL;
