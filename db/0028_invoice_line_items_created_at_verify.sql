-- 0028_invoice_line_items_created_at_verify.sql
-- Self-rolling-back verification for 0027: column exists, and the exact
-- json_agg(ORDER BY li.created_at) subquery used by the gateway's
-- send_customer_invoice_lookup now executes without error.
BEGIN;

-- (a) column present
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'invoice_line_items' AND column_name = 'created_at'
  ) THEN
    RAISE EXCEPTION '0027 failed: invoice_line_items.created_at missing';
  END IF;
END $$;

-- (b) regression: the gateway lines subquery parses and runs (works on the
-- real ledger, whatever it holds — must not throw "column does not exist")
SELECT COALESCE(json_agg(json_build_object('description', li.description, 'amount', li.amount)
                         ORDER BY li.created_at), '[]'::json) AS lines
FROM invoice_line_items li;

-- (c) default applied (no NULLs)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM invoice_line_items WHERE created_at IS NULL) THEN
    RAISE EXCEPTION '0027 failed: NULL created_at rows remain';
  END IF;
END $$;

ROLLBACK;
