#!/usr/bin/env bash
# Nightly Postgres backup for the Construction PM Assistant.
# pg_dump from the co-located postgres container, gzip, retain last N days.
#
# Wire it into cron on the VPS (e.g. daily at 03:00):
#   0 3 * * * /path/to/personal-agent/deploy/backup.sh >> /var/log/pm-backup.log 2>&1
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/pm}"
CONTAINER="${POSTGRES_CONTAINER:-postgres}"
PGUSER="${POSTGRES_USER:-postgres}"
PGDB="${POSTGRES_DB:-postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/pm_${TS}.sql.gz"

docker exec "$CONTAINER" pg_dump -U "$PGUSER" "$PGDB" | gzip > "$OUT"
find "$BACKUP_DIR" -name 'pm_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "Backup written: $OUT ($(du -h "$OUT" | cut -f1))"

# Off-site copy (optional) — uncomment once rclone is configured on the VPS:
#   rclone copy "$BACKUP_DIR" "gdrive:ConstructionOpsBackups"
