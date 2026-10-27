-- 0036_company_logo_verify.sql
-- Self-rolling-back verification for 0035. Any failed assertion aborts the
-- transaction, so migrate.sh (ON_ERROR_STOP) exits non-zero.

BEGIN;

DO $$
DECLARE
    logo_type text;
    pid integer;
BEGIN
    SELECT column_name
      INTO logo_type
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'company_profile'
       AND column_name = 'logo_content_type';

    IF logo_type IS NULL THEN
        RAISE EXCEPTION '0035 verify: company_profile.logo_content_type is missing';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'company_profile'
                      AND column_name = 'logo_data') THEN
        RAISE EXCEPTION '0035 verify: company_profile.logo_data is missing';
    END IF;

    -- Round trip (rolled back): bytes in, bytes readable back out.
    SELECT id INTO pid FROM company_profile ORDER BY id LIMIT 1;
    IF pid IS NOT NULL THEN
        UPDATE company_profile
           SET logo_data = 'aGVsbG8=', logo_content_type = 'image/svg+xml'
         WHERE id = pid;
        IF (SELECT length(logo_data) FROM company_profile WHERE id = pid) <> 8 THEN
            RAISE EXCEPTION '0035 verify: logo_data did not round-trip';
        END IF;
        IF (SELECT logo_content_type FROM company_profile WHERE id = pid) IS NULL THEN
            RAISE EXCEPTION '0035 verify: logo_content_type did not round-trip';
        END IF;
        UPDATE company_profile
           SET logo_data = NULL, logo_content_type = NULL
         WHERE id = pid;
    END IF;
END $$;

ROLLBACK;
