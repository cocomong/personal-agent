# Backups: unprivileged dump path, and how to restore

The nightly dump used to run as `sudo docker exec pg_dump` from cron. Two consequences, both real:
the job needed root, and the cron redirect wrote to `/var/log/` as a non-root user, so the redirect
failed before the script started and **nothing recorded the failure** — the last usable dump was
2026-09-29, seventeen days before anyone noticed.

`deploy/backup_host.sh` replaces that. It runs as the normal user, with no `sudo`, no `docker`
access and no root privileges, and it verifies its own output before claiming success.

## One-time provisioning (needs admin; the job does not)

Postgres here is 17-alpine inside compose. The host needs a client of the **same major version** —
Ubuntu 24.04 ships 16, and `pg_dump` refuses a newer server:

```bash
sudo install -d /usr/share/postgresql-common/pgdg
sudo curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
  https://www.postgresql.org/media/keys/ACCC4CF8.asc
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
  https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" \
  | sudo tee /etc/apt/sources.list.d/pgdg.list
sudo apt-get update && sudo apt-get install -y postgresql-client-17
```

Publish the port on **loopback only** — the container deliberately had no `ports:` mapping, and
`127.0.0.1` keeps that intent while letting an unprivileged process reach the database:

```yaml
  postgres:
    ports:
      - "127.0.0.1:55432:5432"
```

```bash
cd /home/ubuntu/n8n-compose && docker compose up -d postgres   # recreates postgres only
```

A least-privilege role — read everything, write nothing:

```sql
CREATE ROLE pm_backup LOGIN PASSWORD '<generate one>';
GRANT pg_read_all_data TO pm_backup;          -- SELECT on all tables/sequences + USAGE on schemas
GRANT CONNECT ON DATABASE postgres TO pm_backup;
```

And the password where libpq expects it, so no secret appears in cron or in the script:

```bash
printf '127.0.0.1:55432:postgres:pm_backup:%s\n' '<password>' > ~/.pgpass
chmod 600 ~/.pgpass
```

## The job

```cron
0 3 * * * /home/ubuntu/personal-agent/deploy/backup_host.sh >> /home/ubuntu/logs/pm-backup.log 2>&1
```

- Dumps `-Fc` (custom format) to `~/backups/pm/pm_<ts>.dump`, renaming from `.part` only on success,
  so an incomplete file never carries a real name.
- Refuses to report success unless `pg_restore -l` lists the archive (≥10 entries, ≥1 table-data):
  `OK ... 74592 bytes entries=152 table_data=17`.
- Deletes `pm_*.dump` older than 30 days (`RETENTION_DAYS`).
- Logs one line per run to `~/logs/pm-backup.log`.

## Proving it restores (do this before trusting it)

```bash
DUMP=$(ls -t ~/backups/pm/pm_*.dump | head -1)
sudo docker exec n8n-compose-postgres-1 psql -U postgres -q \
  -c "drop database if exists pm_restore_check" -c "create database pm_restore_check"
sudo docker exec -i n8n-compose-postgres-1 pg_restore -U postgres -d pm_restore_check \
  --no-owner --no-privileges < "$DUMP"
# compare figures, not formatting:
for db in postgres pm_restore_check; do
  sudo docker exec n8n-compose-postgres-1 psql -U postgres -d $db -Atc \
    "select 'invoices='||count(*)||' net='||coalesce(sum(net_amount),0)||' due='||coalesce(sum(amount_due),0) from invoices"
done
sudo docker exec n8n-compose-postgres-1 psql -U postgres -q -c "drop database pm_restore_check"
```

First run, 2026-10-19: 23 tables and 3 invoices / 6 change orders / 4 device tokens in both
databases; `net=53250.00 due=54600.00 gst=1350.00` identical on each side; `pg_restore` exit 0.
The role's write attempt fails with `permission denied for schema public`.

## Still missing

- **Off-site copy.** Everything above lives on `/dev/sda1` next to the database it protects. The
  destination is the next step (GCS or OCI Object Storage), plus a freshness alarm —
  healthchecks.io-style, so that *silence* is what pages you, which is exactly what failed here.
- **Scheduled restore rehearsal.** The command above is manual; a monthly run would catch a
  corruption that `pg_restore -l` cannot.
