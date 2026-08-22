-- 0009_tax_payments.sql
-- (a) Invoice tax breakdown: amount_due becomes GROSS (tax-inclusive).
--     GST always applied; PST only when pst_applicable is true (Decision #2).
-- (b) Payments ledger: individual payments against invoices, with derived
--     paid/balance totals and a recompute function for invoice status.

-- (a) Tax columns on invoices
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS net_amount     NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS gst_amount     NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS pst_amount     NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS pst_applicable BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: existing invoices carry no tax, so net = amount_due.
UPDATE invoices SET net_amount = amount_due WHERE net_amount IS NULL;
ALTER TABLE invoices ALTER COLUMN net_amount SET NOT NULL;

-- (b) Payments ledger
CREATE TABLE IF NOT EXISTS payments (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id   UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    payment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    amount       NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    method       VARCHAR(50),              -- E-transfer / Cheque / Credit card / Cash
    notes        TEXT,
    tool_call_id VARCHAR(100) UNIQUE,      -- ADR-3 idempotency (record_payment)
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments (invoice_id);

-- Paid totals derived from the ledger (used by the rollup view).
CREATE OR REPLACE VIEW view_invoice_payments AS
SELECT i.id AS invoice_id,
       i.project_id,
       COALESCE(SUM(p.amount), 0.00) AS total_paid,
       i.amount_due - COALESCE(SUM(p.amount), 0.00) AS balance_due,
       i.due_date
FROM invoices i
LEFT JOIN payments p ON p.invoice_id = i.id
GROUP BY i.id, i.project_id, i.amount_due, i.due_date;

-- Recompute invoice status from the ledger (called by the record_payment tool).
-- DRAFT invoices are left untouched (not yet issued).
CREATE OR REPLACE FUNCTION recompute_invoice_status(invoice_uuid UUID) RETURNS VOID AS $$
DECLARE
    v RECORD;
BEGIN
    SELECT vp.total_paid, vp.balance_due, vp.due_date, i.status AS cur_status
      INTO v
      FROM view_invoice_payments vp
      JOIN invoices i ON i.id = vp.invoice_id
     WHERE vp.invoice_id = invoice_uuid;

    IF v.cur_status = 'DRAFT' THEN
        RETURN;
    END IF;

    IF v.total_paid = 0 THEN
        UPDATE invoices
           SET status = CASE WHEN v.due_date < CURRENT_DATE THEN 'OVERDUE' ELSE 'UNPAID' END
         WHERE id = invoice_uuid;
    ELSIF v.balance_due <= 0 THEN
        UPDATE invoices SET status = 'PAID' WHERE id = invoice_uuid;
    ELSE
        UPDATE invoices SET status = 'PARTIAL' WHERE id = invoice_uuid;
    END IF;
END $$ LANGUAGE plpgsql;
