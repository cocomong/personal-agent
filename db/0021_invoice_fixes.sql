-- 0021_invoice_fixes.sql
-- Invoice lifecycle + numbering + email-audit fixes (2026-09-05 build).
--   * company_profile.invoice_last_number — per-company sequence counter for
--     human invoice numbers (prefix + zero-padded counter, e.g. INV-0001).
--   * invoices.description — optional single description line on the invoice.
--   * invoices.last_client_html — canonical client-facing HTML stored once at
--     preview time; the approve workflow emails THIS copy (never re-renders),
--     so what the PM previews is exactly what the client receives (single
--     template, no drift).
--   * invoice_email_log — audit of every outbound invoice email (preview /
--     client / resend) plus rejects, with recipient + Gmail message_id.
--   * Backfill: invoices already emailed to clients are ISSUED — DRAFT flips
--     to UNPAID (nothing in the old flow ever transitioned status).
--   * fn_refresh_invoice_statuses() — periodic OVERDUE/PAID pass, wired later
--     to the Deadline Reminder schedule (stored OVERDUE only recomputes on
--     payment today).
-- Idempotent (IF NOT EXISTS / IF EXISTS).

-- Per-company numbering counter (idempotent).
ALTER TABLE company_profile
    ADD COLUMN IF NOT EXISTS invoice_last_number INT NOT NULL DEFAULT 0;

-- Invoice content columns.
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS description      TEXT,
    ADD COLUMN IF NOT EXISTS last_client_html TEXT;

-- Outbound invoice email audit log.
CREATE TABLE IF NOT EXISTS invoice_email_log (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id  UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    company_id  SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id),
    kind        VARCHAR(20) NOT NULL,   -- preview | client | resend | reject
    recipient   VARCHAR(255),
    message_id  VARCHAR(255),           -- Gmail message id of the send
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_invoice_email_log_invoice ON invoice_email_log (invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_email_log_company ON invoice_email_log (company_id);

-- Emailed invoices are issued: DRAFT -> UNPAID (idempotent re-run safe).
UPDATE invoices SET status = 'UNPAID'
 WHERE status = 'DRAFT' AND email_sent_at IS NOT NULL;

-- Periodic OVERDUE/PAID refresh. Callable by the future scheduled reminder
-- workflow; payments still recompute immediately via recompute_invoice_status.
CREATE OR REPLACE FUNCTION fn_refresh_invoice_statuses() RETURNS int AS $$
DECLARE
    v_updated int := 0;
    v_id      uuid;
    v_cur     varchar;
    v_paid    numeric;
    v_balance numeric;
    v_due     date;
BEGIN
    FOR v_id, v_cur, v_paid, v_balance, v_due IN
        SELECT i.id, i.status, vp.total_paid, vp.balance_due, vp.due_date
        FROM invoices i
        JOIN view_invoice_payments vp ON vp.invoice_id = i.id
        WHERE i.status <> 'DRAFT' AND i.status <> 'PAID'
    LOOP
        IF v_balance <= 0 AND v_cur <> 'PAID' THEN
            UPDATE invoices SET status = 'PAID' WHERE id = v_id;
            v_updated := v_updated + 1;
        ELSIF v_paid = 0 AND v_due < CURRENT_DATE AND v_cur <> 'OVERDUE' THEN
            UPDATE invoices SET status = 'OVERDUE' WHERE id = v_id;
            v_updated := v_updated + 1;
        END IF;
    END LOOP;
    RETURN v_updated;
END $$ LANGUAGE plpgsql;

COMMENT ON COLUMN invoices.last_client_html IS
    'Canonical client HTML stored at preview time; approve workflow emails this copy';
COMMENT ON TABLE invoice_email_log IS
    'Audit of outbound invoice emails (preview/client/resend) and rejects';
