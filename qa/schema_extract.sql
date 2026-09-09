-- Schema catalog extraction (SCHEMA.md regeneration). Emits JSON arrays on
-- ==SECTION== markers; pipe to psql -tA -q over ssh (see doc/SCHEMA.md appendix):
--   ssh ubuntu@n8n2.ordrnow.com "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -tA -q -v ON_ERROR_STOP=1" < qa/schema_extract.sql > /tmp/schema_dump.txt
-- Then: python3 qa/schema_regen.py /tmp/schema_dump.txt > doc/SCHEMA.md
SELECT '==TABLES==';
SELECT json_agg(x) FROM (
  SELECT c.relname AS name,
         obj_description(c.oid) AS comment
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind = 'r'
     AND c.relname NOT LIKE 'pg_%'
   ORDER BY c.relname
) x;
SELECT '==COLUMNS==';
SELECT json_agg(x) FROM (
  SELECT t.relname AS table_name,
         a.attname AS column_name,
         pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
         a.attnotnull AS not_null,
         pg_get_expr(ad.adbin, ad.adrelid) AS default_expr,
         col_description(t.oid, a.attnum) AS comment
    FROM pg_attribute a
    JOIN pg_class t ON t.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
   WHERE n.nspname = 'public' AND t.relkind = 'r'
     AND a.attnum > 0 AND NOT a.attisdropped
   ORDER BY t.relname, a.attnum
) x;
SELECT '==CONSTRAINTS==';
SELECT json_agg(x) FROM (
  SELECT t.relname AS table_name, c.conname AS name,
         c.contype AS type,
         pg_get_constraintdef(c.oid) AS definition,
         a.attname AS column_name,
         (SELECT array_agg(att2.attname ORDER BY ord.ord)
            FROM unnest(c.conkey) WITH ORDINALITY ord(attnum, ord)
            JOIN pg_attribute att2 ON att2.attrelid = c.conrelid AND att2.attnum = ord.attnum
         ) AS columns
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    LEFT JOIN pg_attribute a ON a.attrelid = c.conrelid
         AND a.attnum = (c.conkey::smallint[])[1]
   WHERE n.nspname = 'public' AND t.relkind = 'r' AND c.contype IN ('p','f','u','c')
   ORDER BY t.relname, c.conname
) x;
SELECT '==INDEXES==';
SELECT json_agg(x) FROM (
  SELECT t.relname AS table_name, ic.relname AS name,
         pg_get_indexdef(i.indexrelid) AS definition
    FROM pg_index i
    JOIN pg_class t ON t.oid = i.indrelid
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
   WHERE n.nspname = 'public' AND t.relkind = 'r'
     AND NOT i.indisprimary
     AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)
   ORDER BY t.relname, ic.relname
) x;
SELECT '==VIEWS==';
SELECT json_agg(x) FROM (
  SELECT c.relname AS name,
         pg_get_viewdef(c.oid) AS definition,
         (SELECT array_agg(a.attname ORDER BY a.attnum)
            FROM pg_attribute a
           WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
         ) AS columns
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind = 'v'
   ORDER BY c.relname
) x;
SELECT '==FUNCTIONS==';
SELECT json_agg(x) FROM (
  SELECT p.proname AS name,
         pg_get_function_identity_arguments(p.oid) AS args,
         pg_get_function_result(p.oid) AS result,
         obj_description(p.oid) AS comment
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public'
     AND p.proname NOT LIKE 'uuid_%'
     AND p.proname NOT LIKE 'pg_%'
   ORDER BY p.proname
) x;
SELECT '==SEQUENCES==';
SELECT json_agg(x) FROM (
  SELECT c.relname AS name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind = 'S'
   ORDER BY c.relname
) x;
