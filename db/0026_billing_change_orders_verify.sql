-- 0026_billing_change_orders_verify.sql
-- Verifies 0025 + the billing-model invariants. Self-contained, self-rolled-back.
--   (a) partial unique index exists
--   (b) the "unbilled approved COs" query picks exactly the COs with no line on an
--       issued invoice (DRAFT invoices must NOT claim a CO)
--   (c) same CO twice on one invoice is rejected by the unique index

BEGIN;

-- (a)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'uq_invoice_line_items_source'
    ) THEN
        RAISE EXCEPTION 'VERIFY FAIL: uq_invoice_line_items_source missing';
    END IF;
END $$;

-- fixtures: two projects w/ customers, two approved COs each on proj A
DO $$
DECLARE
    v_cust_a uuid; v_cust_b uuid;
    v_proj_a uuid; v_proj_b uuid;
    v_inv_issued uuid; v_inv_draft uuid;
    v_n int;
BEGIN
    INSERT INTO customers (name, email, company_id)
    VALUES ('Verify Bill A', 'verify-bill-a@example.com', 1)
    RETURNING id INTO v_cust_a;
    INSERT INTO customers (name, email, company_id)
    VALUES ('Verify Bill B', 'verify-bill-b@example.com', 1)
    RETURNING id INTO v_cust_b;

    INSERT INTO projects (customer_id, title, site_address, original_contract_value,
                          revised_contract_value, baseline_status)
    VALUES (v_cust_a, 'Verify Bill Proj A', '1 A St', 20000.00, 23500.00, 'APPROVED')
    RETURNING id INTO v_proj_a;
    INSERT INTO projects (customer_id, title, site_address, original_contract_value,
                          revised_contract_value, baseline_status)
    VALUES (v_cust_b, 'Verify Bill Proj B', '2 B St', 10000.00, 10000.00, 'APPROVED')
    RETURNING id INTO v_proj_b;

    -- CO1 (drywall) approved; CO2 (plumbing) approved on proj A
    INSERT INTO change_orders (project_id, change_order_number, description, cost_impact, approval_status)
    VALUES (v_proj_a, 1, 'Drywall extra', 2500.00, 'APPROVED');
    INSERT INTO change_orders (project_id, change_order_number, description, cost_impact, approval_status)
    VALUES (v_proj_a, 2, 'Plumbing extra', 1000.00, 'APPROVED');
    INSERT INTO change_orders (project_id, change_order_number, description, cost_impact, approval_status)
    VALUES (v_proj_b, 1, 'Proj B CO', 500.00, 'APPROVED');

    -- CO1 on an ISSUED invoice (claims it); CO2 on a DRAFT invoice (must NOT claim)
    INSERT INTO invoices (company_id, project_id, invoice_number, invoice_type, amount_due,
                          net_amount, status, due_date, email_sent_at)
    VALUES (1, v_proj_a, 'INV-VERIFY-CO-ISSUED', 'CHANGE_ORDER', 2500.00, 2500.00, 'UNPAID',
            CURRENT_DATE + 30, CURRENT_TIMESTAMP)
    RETURNING id INTO v_inv_issued;
    INSERT INTO invoice_line_items (invoice_id, source_type, source_id, description, amount)
    SELECT v_inv_issued, 'change_order', id, 'CO #1 - Drywall extra', 2500.00
    FROM change_orders WHERE change_order_number = 1 AND project_id = v_proj_a;

    INSERT INTO invoices (company_id, project_id, invoice_number, invoice_type, amount_due,
                          net_amount, status, due_date)
    VALUES (1, v_proj_a, 'INV-VERIFY-CO-DRAFT', 'CHANGE_ORDER', 1000.00, 1000.00, 'DRAFT',
            CURRENT_DATE + 30)
    RETURNING id INTO v_inv_draft;
    INSERT INTO invoice_line_items (invoice_id, source_type, source_id, description, amount)
    SELECT v_inv_draft, 'change_order', id, 'CO #2 - Plumbing extra', 1000.00
    FROM change_orders WHERE change_order_number = 2 AND project_id = v_proj_a;

    -- (b) unbilled query: only CO #2 of proj A (the DRAFT claim must not exclude it),
    -- and proj B CO is on a different project.
    SELECT COUNT(*) INTO v_n
    FROM change_orders co
    WHERE co.project_id = v_proj_a
      AND co.approval_status = 'APPROVED'
      AND NOT EXISTS (
          SELECT 1 FROM invoice_line_items li
          JOIN invoices i ON i.id = li.invoice_id
          WHERE li.source_type = 'change_order' AND li.source_id = co.id
            AND i.status <> 'DRAFT'
      );
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'VERIFY FAIL (unbilled): expected 1 unbilled CO on proj A, got %', v_n;
    END IF;

    -- (c) same CO twice on one invoice violates the partial unique index
    BEGIN
        INSERT INTO invoice_line_items (invoice_id, source_type, source_id, description, amount)
        SELECT v_inv_issued, 'change_order', id, 'dup', 1.00
        FROM change_orders WHERE change_order_number = 1 AND project_id = v_proj_a;
        RAISE EXCEPTION 'VERIFY FAIL (unique line): duplicate CO line accepted on one invoice';
    EXCEPTION WHEN unique_violation THEN
        NULL;  -- expected 23505
    END;

    -- cleanup happens via ROLLBACK
END $$;

ROLLBACK;

-- Expected (clean run): no exception raised -> all 0025 invariants PASS.
