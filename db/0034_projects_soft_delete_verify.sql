-- 0034_projects_soft_delete_verify.sql
-- Self-rolling-back verification for 0033. Any failed assertion aborts the
-- transaction, so migrate.sh (ON_ERROR_STOP) exits non-zero.

BEGIN;

DO $$
DECLARE
    col_type text;
    col_default text;
    pid uuid;
BEGIN
    SELECT data_type, column_default
      INTO col_type, col_default
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'projects'
       AND column_name = 'deleted_at';

    IF col_type IS NULL THEN
        RAISE EXCEPTION '0033 verify: projects.deleted_at column is missing';
    END IF;
    IF col_type <> 'timestamp with time zone' THEN
        RAISE EXCEPTION '0033 verify: projects.deleted_at must be timestamptz, got %', col_type;
    END IF;
    IF col_default IS NOT NULL THEN
        RAISE EXCEPTION '0033 verify: projects.deleted_at must default to NULL (existing rows stay active), got %', col_default;
    END IF;

    -- Round trip: a marked project is excluded by the soft-delete filter and
    -- can be un-marked again. Rolled back below either way.
    SELECT id INTO pid FROM projects LIMIT 1;
    IF pid IS NOT NULL THEN
        UPDATE projects SET deleted_at = now() WHERE id = pid;
        IF (SELECT deleted_at FROM projects WHERE id = pid) IS NULL THEN
            RAISE EXCEPTION '0033 verify: deleted_at marker did not persist';
        END IF;
        IF EXISTS (SELECT 1 FROM projects WHERE id = pid AND deleted_at IS NULL) THEN
            RAISE EXCEPTION '0033 verify: marked project still reads as active';
        END IF;
        UPDATE projects SET deleted_at = NULL WHERE id = pid;
    END IF;
END $$;

ROLLBACK;
