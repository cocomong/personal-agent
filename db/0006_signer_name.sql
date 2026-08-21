-- 0006_signer_name.sql
-- Record the typed signer name captured on the customer approval page
-- (typed-name e-signature), for the audit trail alongside approved_by / method.

ALTER TABLE projects      ADD COLUMN IF NOT EXISTS baseline_signer_name VARCHAR(255);
ALTER TABLE change_orders ADD COLUMN IF NOT EXISTS signer_name          VARCHAR(255);
