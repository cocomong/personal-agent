#!/usr/bin/env bash
# Apply the Construction PM Assistant migrations to Postgres.
# Runs db/*.sql in DEPLOY order, then the two self-rolling-back verification
# scripts. Works in two modes with zero edits:
#
#   Co-located (default) — run on the same host as the postgres container:
#     ./migrate.sh
#
#   Remote — run against Postgres on another VPS (psql must be installed here):
#     PGHOST=10.0.0.5 PGPASSWORD=... ./migrate.sh
#
# Env: POSTGRES_CONTAINER (default 'postgres'), POSTGRES_USER, POSTGRES_DB,
#      PGHOST (set to go remote), PGPORT (default 5432), PGPASSWORD (remote).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_DIR="$SCRIPT_DIR/../db"
CONTAINER="${POSTGRES_CONTAINER:-postgres}"
PGUSER="${POSTGRES_USER:-postgres}"
PGDB="${POSTGRES_DB:-postgres}"

if [[ -n "${PGHOST:-}" ]]; then
  PSQL=(psql -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDB")
else
  PSQL=(docker exec -i "$CONTAINER" psql -U "$PGUSER" -d "$PGDB")
fi

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
  0014_schedule.sql
  0015_device_tokens.sql
)

VERIFY=(
  0002_idempotency_test.sql
  0013_verification.sql
)

echo "== Migrations =="
for f in "${MIGRATIONS[@]}"; do
  echo "  applying $f"
  "${PSQL[@]}" -v ON_ERROR_STOP=1 -q < "$DB_DIR/$f"
done

echo "== Verification (asserts then self-rolls-back) =="
for f in "${VERIFY[@]}"; do
  echo "  running $f"
  "${PSQL[@]}" -v ON_ERROR_STOP=1 < "$DB_DIR/$f"
done

echo "== Done =="
"${PSQL[@]}" -c \
  "SELECT company_name, city, province, phone FROM company_profile WHERE id = 1;"
