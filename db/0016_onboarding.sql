-- 0016_onboarding.sql
-- Initial-setup onboarding wizard (voice first-run flow).
--
-- Adds to company_profile:
--   * pm_name            - PM's full name, captured during onboarding
--   * pm_preferred_name  - how the PM wants to be addressed daily ("Dave", "boss")
--   * setup_completed_at - NULL until first-run onboarding completes; kept on re-runs
--
-- No workers-table change needed: name / trade / hourly_rate already exist (0001).
-- Workers are upserted by case-insensitive name (see the gateway's
-- complete_onboarding_workers node), so re-running onboarding never duplicates.

ALTER TABLE company_profile
    ADD COLUMN IF NOT EXISTS pm_name            VARCHAR(255),
    ADD COLUMN IF NOT EXISTS pm_preferred_name  VARCHAR(255),
    ADD COLUMN IF NOT EXISTS setup_completed_at TIMESTAMPTZ;

COMMENT ON COLUMN company_profile.pm_name IS 'PM full name, captured by the first-run onboarding wizard';
COMMENT ON COLUMN company_profile.pm_preferred_name IS 'How the PM wants to be addressed daily (e.g. Dave, boss)';
COMMENT ON COLUMN company_profile.setup_completed_at IS 'NULL until onboarding completes; set once, preserved on re-runs';
