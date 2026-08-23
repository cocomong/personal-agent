# Deployment Guide — Construction PM Assistant (backend)

How to deploy the n8n workflows + co-located PostgreSQL, and wire up Gmail.

## Current deployment
- **n8n:** `https://n8n2.ordrnow.com` (Oracle Cloud **8GB Arm** instance, docker-compose)
- **Database:** PostgreSQL, **co-located** on the same instance (the `postgres` service in the compose file below). No public DB endpoint.

> The earlier Supabase cloud project (`zjqizajswdpmtdovjxjo`) is not used — the stack runs plain PostgreSQL beside n8n. The `1GB AMD` instance is spare; it is not needed.

---

## 1. Start the stack + apply migrations

On the n8n host (the 8GB Arm instance):

```bash
cd ~/personal-agent/deploy
cp .env.example .env          # set POSTGRES_PASSWORD (and GMAIL_USER/PUBLIC_BASE_URL)
docker compose up -d          # brings up n8n + postgres (co-located, same network)
./migrate.sh                  # applies db/*.sql in order + runs verification
```

`deploy/migrate.sh` runs the migrations in DEPLOY order via the postgres container's `psql` (no host dependencies), then runs the two self-rolling-back verification scripts. A clean run ends by printing the `company_profile` row (Ireh Construction).

> **Moving Postgres to a separate VPS later?** No code changes — set `PGHOST`/`PGPORT`/`PGPASSWORD` (with a `psql` client installed) and `migrate.sh`/`backup.sh` switch to remote mode automatically. See the script headers for the full env surface.

The migration set:

1. `0001_init.sql` — 8 tables (incl. workers) + indexes + rollup view
2. `0004_reconcile_contract_value.sql` — view reads `projects.*_contract_value` (source of truth)
3. `0005_customer_approval.sql` — approval columns (`baseline_*`, `approval_token`, …)
4. `0006_signer_name.sql` — signer-name columns
5. `0007_company_profile.sql` — Ireh Construction branding + financial defaults (single row)
6. `0008_workers_payroll.sql` — payroll tables + `fn_run_payroll` + `timesheets.overtime_hours`
7. `0009_tax_payments.sql` — invoice GST/PST columns + payments ledger + `recompute_invoice_status()`
8. `0010_quote_trail.sql` — estimate revisions + change-order reason
9. `0011_dashboard_views.sql` — tax-aware rollup + payroll/overdue/follow-up views
10. `0003_seed.sql` — demo data (Oakridge / Kitsilano)
11. `0012_seed_v2.sql` — demo payroll run + payment
12. `0002_idempotency_test.sql` — idempotency check (self-rolled-back)
13. `0013_verification.sql` — migration invariants (self-rolled-back)

> `0002` and `0013` are verification scripts (assert invariants then roll back), not migrations.

---

## 2. n8n credentials

Create two credentials (n8n → Credentials → Add credential). **Name them exactly** so imported workflows auto-link:

**`Supabase PostgreSQL`** (type: PostgreSQL) — *the name stays for workflow compatibility, but it points at the local container:*
| Field | Value |
|---|---|
| Host | `postgres` (the compose service name) |
| Port | `5432` |
| Database | `postgres` |
| User | `postgres` |
| Password | your `POSTGRES_PASSWORD` from `deploy/.env` |
| SSL | **Off** (traffic stays on the Docker network) |

**`Gmail SMTP`** (type: SMTP)
| Field | Value |
|---|---|
| Host | `smtp.gmail.com` |
| Port | `465` |
| SSL/TLS | **On** |
| User | your Gmail address |
| Password | 16-char **App Password** (Google → Security → 2-Step Verification → App passwords) |

> Workflows reference credentials by `name`, so the placeholder `id` values in the JSON are harmless — n8n matches by name on import.

---

## 3. Environment

Set in `deploy/.env` (used by `docker-compose.yml`):

```yaml
POSTGRES_PASSWORD=<strong unique value>
GMAIL_USER=yourname@gmail.com
PUBLIC_BASE_URL=https://n8n2.ordrnow.com
```

`PUBLIC_BASE_URL` is read by the gateway's Code nodes to build approval links (it must match the n8n instance URL). The branding values (company name/address/phone/colors/signature) are NOT env vars — they live in the `company_profile` table (single row, `db/0007`), so they're editable without redeploying.

---

## 4. Import the workflows

n8n → **Workflows → Import from File** (or drag the JSON onto the canvas):

1. `backend/n8n/workflows/voice-gateway.json` — Vapi tool-call router (17 tools)
2. `backend/n8n/workflows/approval-portal.json` — customer approval pages
3. `backend/n8n/workflows/daily-overdue-check.json` — daily 08:00 overdue summary (silent when clear)
4. `backend/n8n/workflows/daily-quote-followup.json` — daily 09:00 expired-quote chase
5. `backend/n8n/workflows/monthly-payroll-digest.json` — monthly (1st) payroll draft digest

Activate all five. If n8n flags any node as "credential missing", select `Supabase PostgreSQL` / `Gmail SMTP`.

---

## 5. Webhook URLs (base already baked in)

| Purpose | URL |
|---|---|
| Vapi tool-calls | `https://n8n2.ordrnow.com/webhook/voice/gateway` |
| Estimate approval page | `https://n8n2.ordrnow.com/webhook/approve-estimate?token=<uuid>` |
| Change order approval page | `https://n8n2.ordrnow.com/webhook/approve-change-order?token=<uuid>` |

The base URL is read from `$env.PUBLIC_BASE_URL` at runtime (set in §3).

---

## 6. Vapi assistant

Per `VAPI_ASSISTANT.md`: create the assistant (voice provider `11labs`), add the **17 function tools** (the 5 new ones' JSON is in `backend/vapi_tools_additions.json`), and point every tool's `server.url` at:

```
https://n8n2.ordrnow.com/webhook/voice/gateway
```

⚠️ After the **first live tool-call**, confirm the `Normalize Tool Call` node matches Vapi's actual payload (`body.message.toolCalls[0].function.{name,arguments}`) and adjust the mapping if Vapi nests it differently.

---

## 7. Backups

Nightly `pg_dump` + gzip + 30-day retention via `deploy/backup.sh`. Wire into cron on the host:

```bash
crontab -e
# daily at 03:00
0 3 * * * /home/ubuntu/personal-agent/deploy/backup.sh >> /var/log/pm-backup.log 2>&1
```

For off-site safety, add an `rclone` line to `backup.sh` (commented out at the bottom) pointing at a Google Drive remote — the host's local backups are single-point-of-failure otherwise.

---

## 8. Upgrading n8n (or Postgres minor)

Containers are disposable; data lives in volumes (`n8n_data`, `pgdata`), so an upgrade is: change one line, pull, recreate **that one service**. The other service never blinks.

**n8n** — check the current stable at https://github.com/n8n-io/n8n/releases (e.g. `2.35.7`), then:

```bash
# 1. Edit deploy/docker-compose.yml: image: docker.n8n.io/n8nio/n8n:<new-version>
cd ~/personal-agent/deploy
docker compose pull n8n            # downloads new image; nothing else changes
docker compose up -d n8n           # recreates ONLY n8n; postgres untouched
docker compose ps                  # both services running
docker logs n8n --tail 50          # clean startup?
docker compose exec postgres pg_isready -U postgres   # DB still up
```

Then make one test call to the assistant and confirm a workflow runs.

**Rollback** (if something's wrong): flip the version back in `docker-compose.yml`, then `docker compose up -d n8n` again — the old image is still cached locally, so it's a ~1-minute revert. Same pattern works for a Postgres *minor* bump (`postgres:17-alpine` floats within major 17).

> **Postgres MAJOR upgrade (17 → 18)** is the one exception: it needs `pg_dump`/`pg_restore` (or `pg_upgrade`), which is a deliberate, rare event. Take a fresh backup first via `deploy/backup.sh`, then dump/restore into a new container. This is true regardless of where Postgres runs — it's a database procedure, not a compose concern.

> **Why pinned, not `:latest`:** `docker compose pull` with `:latest` grabs whatever shipped that day — you can't predict it, and n8n breaks between majors. Pinning means *you* decide when to move, after reading the release notes.

---

## Verification checklist

- [ ] `migrate.sh` runs clean; `company_profile` shows Ireh Construction
- [ ] All 5 workflows imported + active, no missing-credential warnings
- [ ] `create_change_order` refuses until `baseline_status = 'APPROVED'`
- [ ] Estimate approval sets `original_contract_value` = Σ(estimates)
- [ ] CO approval recomputes `revised_contract_value` (self-healing)
- [ ] `create_invoice` computes net + GST (+PST if `pst_applicable`); `amount_due` = net + GST + PST
- [ ] `record_payment` inserts a payment and flips invoice status (UNPAID → PARTIAL → PAID)
- [ ] `run_payroll` / `get_payroll_summary` return a run with correct CPP/EI/WCB math
- [ ] `get_dashboard_summary` shows margin, retention, and overdue amounts
- [ ] Gmail sends invoice + approval emails (check "Sent" folder)
- [ ] Approval link opens the page; Approve/Reject records correctly
- [ ] The 3 scheduled workflows fire (overdue / quote-follow-up / payroll digest)
- [ ] Voice + text same-session on a device (mobile app)

## Notes

- **HTTPS:** TLS terminates at `n8n2.ordrnow.com`, so the typed-name approval page is already a reasonable signature record.
- **Postgres is not exposed:** the `postgres` service has no `ports:` mapping — only n8n (and `docker exec` backup) can reach it.
- **Secrets:** `POSTGRES_PASSWORD` and the Gmail App Password live in `deploy/.env` / n8n credentials — never commit them (`.env` is git-ignored; `.env.example` is the template).
- **Idempotency:** `change_orders`/`timesheets`/`payments` carry unique idempotency keys; replayed Vapi calls are no-ops (ADR-3).
