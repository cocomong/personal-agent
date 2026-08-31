-- 0018_invoice_send.sql
-- Invoice email delivery tracking (preview-approval flow).
-- email_sent_at is set when the invoice email is actually delivered to the
-- client (approve-invoice webhook). NULL = never sent (only previewed).
-- Powers the double-send guard: the approve endpoint refuses to send again
-- once this timestamp is set.
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMPTZ;
