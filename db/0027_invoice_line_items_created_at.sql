-- 0027_invoice_line_items_created_at.sql
-- invoice_line_items was created (0009-era) without created_at, while every
-- sibling table has it. The invoice lookup orders line items by li.created_at
-- (send_customer_invoice), so send errored: "column li.created_at does not
-- exist". Add the column; backfill defaults to now().
ALTER TABLE invoice_line_items
  ADD COLUMN IF NOT EXISTS created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP;
