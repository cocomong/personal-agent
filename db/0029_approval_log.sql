-- 0029: approval_log — audit trail for baseline-estimate (and future CO)
-- approval emails + customer decisions. One row per event; kinds:
--   estimate_sent / estimate_approved / estimate_rejected
-- (change_order_* kinds can share this table later — kind is free text).
-- project_id is NOT NULL so the trail dies with the project (test data
-- cleans up automatically via the existing ON DELETE CASCADE chain).

CREATE TABLE IF NOT EXISTS approval_log (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id  smallint     NOT NULL REFERENCES company_profile(id),
    project_id  uuid         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind        text         NOT NULL,
    recipient   text,
    message_id  text,
    note        text,
    created_at  timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_approval_log_project
    ON approval_log (project_id, created_at DESC);
