#!/usr/bin/env bash
# Nightly Postgres backup for the Construction PM Assistant.
# pg_dump + gzip + 30-day retention. Works co-located or remote:
#
#   Co-located (default) — run on the same host as the postgres container:
#     ./backup.sh
#
#   Remote — run against Postgres on another VPS (pg_dump must be installed):
#     PGHOST=10.0.0.5 PGPASSWORD=... ./backup.sh
#
# Wire it into cron (e.g. daily at 03:00):
#   0 3 * * * /path/to/personal-agent/deploy/backup.sh >> /var/log/pm-backup.log 2>&1
#
# Env: POSTGRES_CONTAINER (default 'postgres'), POSTGRES_USER, POSTGRES_DB,
#      PGHOST (set to go remote), PGPORT (default 5432), PGPASSWORD (remote),
#      BACKUP_DIR, RETENTION_DAYS.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/pm}"
CONTAINER="${POSTGRES_CONTAINER:-postgres}"
PGUSER="${POSTGRES_USER:-postgres}"
PGDB="${POSTGRES_DB:-postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

if [[ -n "${PGHOST:-}" ]]; then
  DUMP=(pg_dump -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" "$PGDB")
else
  DUMP=(docker exec "$CONTAINER" pg_dump -U "$PGUSER" "$PGDB")
fi

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/pm_${TS}.sql.gz"

"${DUMP[@]}" | gzip > "$OUT"
find "$BACKUP_DIR" -name 'pm_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "Backup written: $OUT ($(du -h "$OUT" | cut -f1))"

# Off-site copy (optional) — uncomment once rclone is configured:
#   rclone copy "$BACKUP_DIR" "gdrive:ConstructionOpsBackups"
