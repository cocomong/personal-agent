-- 0010_quote_trail.sql
-- Ports the Sheets tracker's negotiation paper trail:
--   * estimates gain revision + lifecycle status + validity (quote revisions)
--   * change_orders gain a reason taxonomy (client_change / site_condition /
--     owner_directed / other)
-- Accepted quotes become the project baseline via the approval-portal workflow
-- (projects.original_contract_value is the source of truth — 0004).

ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS revision   INT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS status     VARCHAR(20) NOT NULL DEFAULT 'ACCEPTED',
        -- DRAFT / SENT / ACCEPTED / DECLINED / SUPERSEDED (Sheets parity)
    ADD COLUMN IF NOT EXISTS valid_until DATE,
    ADD COLUMN IF NOT EXISTS sent_at    TIMESTAMPTZ;

-- Existing estimates are the accepted baseline, so ACCEPTED is the right default.

ALTER TABLE change_orders
    ADD COLUMN IF NOT EXISTS reason VARCHAR(50);
        -- client_change / site_condition / owner_directed / other
