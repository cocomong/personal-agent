#!/usr/bin/env bash
# Unprivileged PostgreSQL backup for a dockerised postgres.
#
# Runs as the invoking user: no sudo, no docker, no root. It connects over loopback
# (127.0.0.1:55432, published by compose bound to localhost only) as the least-privilege
# role pm_backup, which has pg_read_all_data and nothing else — a write attempt fails with
# "permission denied for schema public". The password lives in ~/.pgpass (0600).
#
# Env: PGHOST PGPORT PGUSER PGDB BACKUP_DIR RETENTION_DAYS PGBIN
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/pm}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-55432}"
PGUSER="${PGUSER:-pm_backup}"
PGDB="${PGDB:-postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
PGBIN="${PGBIN:-/usr/lib/postgresql/17/bin}"

export PATH="$PGBIN:$PATH"
mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/pm_${TS}.dump"
TMP="$OUT.part"
# A failed pg_dump leaves a partial file behind; make sure it never survives the run.
trap 'rm -f "$TMP"' EXIT

# -Fc (custom format): integrity-checkable with pg_restore --list, restorable table-by-table,
# and comparable in size to gzip for this database.
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDB" -Fc -f "$TMP"
mv "$TMP" "$OUT"   # only a complete dump ever becomes visible under the real name

# Do not report success for an archive that cannot even be listed.
ENTRIES="$(pg_restore -l "$OUT" 2>/dev/null | grep -c '^' || true)"
TABLES="$(pg_restore -l "$OUT" 2>/dev/null | grep -c 'TABLE DATA' || true)"
if [ "${ENTRIES:-0}" -lt 10 ] || [ "${TABLES:-0}" -lt 1 ]; then
  echo "FAIL $(date -Is) archive invalid: entries=${ENTRIES:-0} table_data=${TABLES:-0} file=$OUT"
  exit 1
fi

find "$BACKUP_DIR" -name 'pm_*.dump' -mtime +"$RETENTION_DAYS" -delete
echo "OK $(date -Is) $OUT $(stat -c %s "$OUT") bytes entries=$ENTRIES table_data=$TABLES"
