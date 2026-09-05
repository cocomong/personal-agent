-- 0024_invoice_presentation_verify.sql
-- Verifies 0023 invariants. Self-contained, self-rolled-back (house style).
-- Asserts the new capture columns exist and are nullable (render-when-present).

BEGIN;

DO $$
DECLARE t text; c text;
BEGIN
    FOREACH t IN ARRAY ARRAY['company_profile', 'customers', 'invoices']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = t AND column_name = 'id'
        ) THEN
            RAISE EXCEPTION 'VERIFY FAIL: table % missing', t;
        END IF;
    END LOOP;

    FOREACH c IN ARRAY ARRAY['gst_reg_number', 'pst_reg_number', 'payment_instructions']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'company_profile' AND column_name = c
        ) THEN
            RAISE EXCEPTION 'VERIFY FAIL (company_profile): column % missing', c;
        END IF;
    END LOOP;

    FOREACH c IN ARRAY ARRAY['street_address', 'city', 'province', 'postal_code']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'customers' AND column_name = c
        ) THEN
            RAISE EXCEPTION 'VERIFY FAIL (customers): column % missing', c;
        END IF;
    END LOOP;

    FOREACH c IN ARRAY ARRAY['billing_percentage', 'billed_basis']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'invoices' AND column_name = c
        ) THEN
            RAISE EXCEPTION 'VERIFY FAIL (invoices): column % missing', c;
        END IF;
    END LOOP;

    -- all must be nullable (optional capture)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND ((table_name = 'company_profile' AND column_name IN
                ('gst_reg_number', 'pst_reg_number', 'payment_instructions'))
            OR (table_name = 'customers' AND column_name IN
                ('street_address', 'city', 'province', 'postal_code'))
            OR (table_name = 'invoices' AND column_name IN
                ('billing_percentage', 'billed_basis')))
          AND is_nullable = 'NO'
    ) THEN
        RAISE EXCEPTION 'VERIFY FAIL: a presentation/capture column is NOT NULL (must be nullable)';
    END IF;
END $$;

ROLLBACK;

-- Expected (clean run): no exception raised -> all 0023 invariants PASS.
