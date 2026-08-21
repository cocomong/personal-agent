-- 0005_customer_approval.sql
-- Customer approval flow (ADR-6, ADR-2): tokenized approval pages let the
-- customer sign the baseline estimate (contract) and individual change orders
-- (amendments) on the spot. Approvals record who + how for the audit trail, and
-- contract values are recomputed in SQL — never in the LLM.

-- Baseline estimate approval lives on `projects` (one baseline per project).
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS baseline_status           VARCHAR(50) NOT NULL DEFAULT 'PENDING', -- PENDING/APPROVED/REJECTED
    ADD COLUMN IF NOT EXISTS baseline_approved_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS baseline_approved_by      VARCHAR(50),   -- 'customer' | 'pm'
    ADD COLUMN IF NOT EXISTS baseline_approval_method  VARCHAR(50),   -- 'onsite_link' | 'email_link' | 'portal' | 'verbal'
    ADD COLUMN IF NOT EXISTS baseline_approval_token   UUID DEFAULT uuid_generate_v4();

-- Change order approval is per-CO (many per project), so it lives here.
ALTER TABLE change_orders
    ADD COLUMN IF NOT EXISTS approval_token        UUID DEFAULT uuid_generate_v4(),
    ADD COLUMN IF NOT EXISTS sent_for_approval_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approval_method       VARCHAR(50),   -- 'onsite_link' | 'email_link' | 'portal' | 'verbal'
    ADD COLUMN IF NOT EXISTS approved_by           VARCHAR(50);   -- 'customer' | 'pm'

-- Existing seeded projects already carry contract values; treat their baseline
-- as approved so the create_change_order gate does not block demo data.
UPDATE projects SET baseline_status = 'APPROVED' WHERE original_contract_value <> 0;
