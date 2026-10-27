-- 0038_invoice_templates_verify.sql
-- Self-rolling-back verification for 0037. Any failed assertion aborts the
-- transaction, so migrate.sh (ON_ERROR_STOP) exits non-zero.

BEGIN;

DO $$
DECLARE
    col_type text;
    fk_violation boolean;
    t_count integer;
BEGIN
    SELECT data_type INTO col_type FROM information_schema.columns
     WHERE table_schema='public' AND table_name='document_templates' AND column_name='key';
    IF col_type IS NULL THEN RAISE EXCEPTION '0037 verify: document_templates missing'; END IF;
    IF col_type <> 'text' THEN RAISE EXCEPTION '0037 verify: document_templates.key wrong type: %', col_type; END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_type='UNIQUE' AND table_name='document_templates'
                      AND constraint_name='document_templates_key_key') THEN
        RAISE EXCEPTION '0037 verify: document_templates.key UNIQUE constraint missing';
    END IF;

    SELECT data_type INTO col_type FROM information_schema.columns
     WHERE table_schema='public' AND table_name='company_profile' AND column_name='invoice_template_key';
    IF col_type IS NULL THEN RAISE EXCEPTION '0037 verify: company_profile.invoice_template_key missing'; END IF;

    -- FK behavior: an unknown key must be rejected.
    BEGIN
        UPDATE company_profile SET invoice_template_key = 'no-such-template-key'
         WHERE id = (SELECT min(id) FROM company_profile);
        fk_violation := false;
    EXCEPTION WHEN foreign_key_violation THEN
        fk_violation := true;
    END;
    IF NOT fk_violation THEN
        RAISE EXCEPTION '0037 verify: FK to document_templates(key) not enforced';
    END IF;

    -- Round trip: seed-shaped row + selection (all rolled back).
    INSERT INTO document_templates (key, display_name, description, html)
    VALUES ('verify-tpl', 'Verify', 'temporary', '<p>{{invoice_number}}</p>')
    ON CONFLICT (key) DO UPDATE SET html = EXCLUDED.html;
    SELECT count(*) INTO t_count FROM document_templates WHERE key = 'verify-tpl';
    IF t_count <> 1 THEN RAISE EXCEPTION '0037 verify: upsert by key failed'; END IF;

    UPDATE company_profile SET invoice_template_key = 'verify-tpl'
     WHERE id = (SELECT min(id) FROM company_profile);
    IF NOT EXISTS (SELECT 1 FROM company_profile WHERE invoice_template_key = 'verify-tpl') THEN
        RAISE EXCEPTION '0037 verify: company selection did not persist';
    END IF;

    UPDATE company_profile SET invoice_template_key = NULL
     WHERE id = (SELECT min(id) FROM company_profile);
    DELETE FROM document_templates WHERE key = 'verify-tpl';
END $$;

ROLLBACK;
