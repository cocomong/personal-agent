-- 0012_seed_v2.sql
-- Demo data for the new subsystems (payroll, payments). Idempotent.
-- Workers are seeded in db/0003_seed.sql (W-001 Mike Johnson, W-002 Ravi Patel).

-- A demo monthly payroll run for Oakridge (hand-computed, deterministic).
INSERT INTO payroll_runs (period_start, period_end, status)
SELECT '2026-08-01', '2026-08-31', 'DRAFT'
WHERE NOT EXISTS (SELECT 1 FROM payroll_runs WHERE period_start = '2026-08-01');

-- Payroll entry for Mike Johnson: 160 regular hours @ $38.
INSERT INTO payroll_entries (payroll_run_id, worker_id, regular_hours, overtime_hours,
                             hourly_rate, gross_pay, cpp, ei, wcb, net_pay)
SELECT r.id, w.id, 160.00, 0.00, w.hourly_rate,
       ROUND(160.00 * w.hourly_rate, 2),
       ROUND(160.00 * w.hourly_rate * 0.0595, 2),
       ROUND(160.00 * w.hourly_rate * 0.0163, 2),
       ROUND(160.00 * w.hourly_rate * 0.0325, 2),
       ROUND(160.00 * w.hourly_rate * (1 - 0.0595 - 0.0163), 2)
FROM payroll_runs r, workers w
WHERE r.period_start = '2026-08-01' AND w.worker_code = 'W-001'
  AND NOT EXISTS (SELECT 1 FROM payroll_entries e WHERE e.payroll_run_id = r.id AND e.worker_id = w.id);

-- A partial payment against the seeded Oakridge invoice (INV-OAK-1001).
-- First ensure the invoice is issued (not DRAFT), then record a payment and
-- recompute its status.
UPDATE invoices SET status = 'UNPAID'
WHERE invoice_number = 'INV-OAK-1001' AND status = 'DRAFT';

INSERT INTO payments (invoice_id, payment_date, amount, method, notes)
SELECT i.id, CURRENT_DATE, ROUND(i.amount_due * 0.50, 2), 'E-transfer', 'Demo partial payment'
FROM invoices i
WHERE i.invoice_number = 'INV-OAK-1001'
  AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.invoice_id = i.id AND p.notes = 'Demo partial payment');

SELECT recompute_invoice_status(i.id)
FROM invoices i WHERE i.invoice_number = 'INV-OAK-1001';

SELECT 'seed v2 complete' AS status;
SELECT worker_code, name, trade, hourly_rate FROM workers ORDER BY worker_code;
SELECT period_start, period_end, status FROM payroll_runs ORDER BY period_start;
