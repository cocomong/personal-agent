-- 0031: baseline estimate state machine — CREATED → SENT → APPROVED / REJECTED
-- (doc/ESTIMATE_STATE.md, D54-D58).
--
-- Principle (PM decision, 2026-09-08): the entity state column is the truth;
-- approval_log is the evidence trail. Transitions write state AND log together.
--
-- Changes:
--   1. projects.baseline_status default PENDING → CREATED. New projects are no
--      longer born "PENDING" (which falsely implied awaiting a signature that
--      was never requested). Vocabulary: CREATED (on file, never sent) / SENT
--      (emailed or link-pushed, awaiting customer) / APPROVED / REJECTED.
--   2. estimates.status (per scope line) default ACCEPTED → CREATED — an
--      on-file marker only, NEVER customer acceptance (that lives solely on
--      projects.baseline_status). Dead quote-era vocab (SENT/DECLINED/
--      SUPERSEDED) normalized to CREATED; DRAFT preserved.
--   3. Live remap by evidence: PENDING + an estimate_sent approval_log row
--      → SENT (a real request went out); remaining PENDING → CREATED. The
--      Test Approval fixture's documented 2026-08-26 send (NEXT_STEPS message
--      id 1a037d86d907038d) predates approval_log, so its log row is backfilled
--      first — it is genuinely SENT, awaiting the customer.

BEGIN;

-- 1. New projects default to CREATED (estimate on file, not yet asked).
ALTER TABLE projects
    ALTER COLUMN baseline_status SET DEFAULT 'CREATED';

COMMENT ON COLUMN projects.baseline_status IS
    'Baseline-estimate workflow state: CREATED (on file, never sent) -> SENT (awaiting customer) -> APPROVED | REJECTED. Truth of the entity; approval_log is the evidence trail.';

-- 2. Estimate line status = on-file marker, default CREATED.
ALTER TABLE estimates
    ALTER COLUMN status SET DEFAULT 'CREATED';

COMMENT ON COLUMN estimates.status IS
    'On-file marker for the scope line: CREATED (counts toward contract math when the project baseline is approved) / DRAFT. NEVER implies customer acceptance - that is projects.baseline_status.';

-- 2b. Normalize dead quote-era vocabulary; preserve DRAFT.
UPDATE estimates SET status = 'CREATED'
 WHERE status IN ('ACCEPTED', 'SENT', 'DECLINED', 'SUPERSEDED');

-- 3. Data repair: backfill the Test Approval fixture's estimate_sent row.
--    Its approval email went out 2026-08-26 (Gmail message id 1a037d86d907038d,
--    recipient support.ordrnow@gmail.com — see doc/NEXT_STEPS.md) BEFORE
--    approval_log existed (db/0029, 2026-09-07). created_at is the documented
--    send date; the recipient is what was on file then (the dup-email fix later
--    moved support.ordrnow@gmail.com to Dave Miller).
INSERT INTO approval_log (company_id, project_id, kind, recipient, message_id, note, created_at)
SELECT p.company_id, p.id, 'estimate_sent', 'support.ordrnow@gmail.com',
       '1a037d86d907038d', 'backfilled 0031: 2026-08-26 send documented in NEXT_STEPS predates approval_log', '2026-08-26 12:00:00+00'
  FROM projects p
 WHERE p.title = 'Test Approval'
   AND NOT EXISTS (SELECT 1 FROM approval_log al
                    WHERE al.project_id = p.id AND al.kind = 'estimate_sent');

-- 3b. Evidence-based remap: PENDING + a real estimate_sent log → SENT.
UPDATE projects p
   SET baseline_status = 'SENT'
 WHERE p.baseline_status = 'PENDING'
   AND EXISTS (SELECT 1 FROM approval_log al
                WHERE al.project_id = p.id AND al.kind = 'estimate_sent');

-- 3c. Any remaining PENDING was never actually sent → CREATED.
UPDATE projects SET baseline_status = 'CREATED'
 WHERE baseline_status = 'PENDING';

COMMIT;
