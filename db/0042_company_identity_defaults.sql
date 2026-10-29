-- 0042: stop new companies from inheriting Ireh's identity.
--
-- company_profile was a single row, so its NOT NULL columns carry Ireh's real
-- data as DEFAULTS ('Ireh Construction', '1951 Kaptey Ave', '778-994-6602',
-- 'support.ordrnow@gmail.com', 'Dave').  With per-company rows, a bare INSERT
-- would clone that identity into a new tenant's invoices and emails, so the
-- tenant-identifying defaults are dropped here: a forgotten column now fails
-- loudly instead of leaking.
--
-- Generic defaults (tax rates, prefixes, brand colours, payroll cadence) stay.
--
-- Also enforces the 2026-10-30 decision that a company cannot be marked set up
-- (and therefore cannot send invoices) without a real business address and a
-- sender address.

-- One company per user: makes onboarding idempotent under retries and races.
CREATE UNIQUE INDEX IF NOT EXISTS uq_company_created_by_user
    ON company_profile (created_by_user)
 WHERE created_by_user IS NOT NULL;

ALTER TABLE company_profile
  ALTER COLUMN company_name    DROP DEFAULT,
  ALTER COLUMN legal_name      DROP DEFAULT,
  ALTER COLUMN street_address  DROP DEFAULT,
  ALTER COLUMN city            DROP DEFAULT,
  ALTER COLUMN province        DROP DEFAULT,
  ALTER COLUMN postal_code     DROP DEFAULT,
  ALTER COLUMN phone           DROP DEFAULT,
  ALTER COLUMN email_from      DROP DEFAULT,
  ALTER COLUMN email_from_name DROP DEFAULT,
  ALTER COLUMN signature_name  DROP DEFAULT;

ALTER TABLE company_profile
  DROP CONSTRAINT IF EXISTS chk_setup_requires_business_address;

ALTER TABLE company_profile
  ADD CONSTRAINT chk_setup_requires_business_address CHECK (
    setup_completed_at IS NULL
    OR (
          btrim(street_address) <> ''
      AND btrim(city) <> ''
      AND btrim(province) <> ''
      AND btrim(postal_code) <> ''
      AND btrim(email_from) <> ''
    )
  );

-- Self-check: the existing company must still satisfy the constraint.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM company_profile
              WHERE setup_completed_at IS NOT NULL
                AND (btrim(street_address) = '' OR btrim(city) = '' OR btrim(province) = ''
                     OR btrim(postal_code) = '' OR btrim(email_from) = '')) THEN
    RAISE EXCEPTION 'an existing set-up company has an incomplete business address';
  END IF;
END $$;
