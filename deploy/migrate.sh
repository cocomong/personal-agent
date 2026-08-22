#!/usr/bin/env bash
# Apply the Construction PM Assistant migrations to the co-located Postgres.
# Runs db/*.sql in DEPLOY order via the postgres container's psql (no host deps).
#
# Usage:
#   ./migrate.sh                        # default 'postgres' container/user/db
#   POSTGRES_CONTAINER=my-pg ./migrate.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_DIR="$SCRIPT_DIR/../db"
CONTAINER="${POSTGRES_CONTAINER:-postgres}"
PGUSER="${POSTGRES_USER:-postgres}"
PGDB="${POSTGRES_DB:-postgres}"

MIGRATIONS=(
  0001_init.sql
  0004_reconcile_contract_value.sql
  0005_customer_approval.sql
  0006_signer_name.sql
  0007_company_profile.sql
  0008_workers_payroll.sql
  0009_tax_payments.sql
  0010_quote_trail.sql
  0011_dashboard_views.sql
  0003_seed.sql
  0012_seed_v2.sql
)

VERIFY=(
  0002_idempotency_test.sql
  0013_verification.sql
)

echo "== Migrations =="
for f in "${MIGRATIONS[@]}"; do
  echo "  applying $f"
  docker exec -i "$CONTAINER" psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 -q < "$DB_DIR/$f"
done

echo "== Verification (asserts then self-rolls-back) =="
for f in "${VERIFY[@]}"; do
  echo "  running $f"
  docker exec -i "$CONTAINER" psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 < "$DB_DIR/$f"
done

echo "== Done =="
docker exec -i "$CONTAINER" psql -U "$PGUSER" -d "$PGDB" -c \
  "SELECT company_name, city, province, phone FROM company_profile WHERE id = 1;"
