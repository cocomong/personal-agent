-- 0041: bind the owner account to the original company, remove the second account.
--
-- Why: the onboarding fix treats "logged-in user with company_id NULL" as
-- "must complete setup". Both existing accounts were NULL, so without this
-- backfill the owner would be sent back through setup. 5650tam@gmail.com is
-- not an owner account (user decision 2026-10-30) and is removed.
--
-- Idempotent: re-running finds nothing to do and changes nothing.
DO $$
DECLARE
  linked int;
  removed int;
BEGIN
  UPDATE users
     SET company_id = 1
   WHERE company_id IS NULL
     AND lower(email) = 'dtam2003@gmail.com';
  GET DIAGNOSTICS linked = ROW_COUNT;

  DELETE FROM users WHERE lower(email) = '5650tam@gmail.com';
  GET DIAGNOSTICS removed = ROW_COUNT;

  IF linked NOT IN (0, 1) THEN
    RAISE EXCEPTION 'expected at most 1 owner row to link, linked %', linked;
  END IF;
  IF removed NOT IN (0, 1) THEN
    RAISE EXCEPTION 'expected at most 1 row to remove, removed %', removed;
  END IF;

  -- Only meaningful when the owner has signed in at least once (a fresh database
  -- has no users yet, and this migration must stay replayable there).
  IF EXISTS (SELECT 1 FROM users WHERE lower(email) = 'dtam2003@gmail.com')
     AND NOT EXISTS (
    SELECT 1 FROM users u JOIN company_profile cp ON cp.id = u.company_id
     WHERE lower(u.email) = 'dtam2003@gmail.com' AND cp.id = 1
  ) THEN
    RAISE EXCEPTION 'owner account is not linked to company 1 after backfill';
  END IF;

  RAISE NOTICE 'linked=% removed=%', linked, removed;
END $$;
