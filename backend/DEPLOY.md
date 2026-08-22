# Deployment Guide — Construction PM Assistant (backend)

How to deploy the n8n workflows against the live Supabase database and Gmail.

## Current deployment
- **n8n:** `https://n8n2.ordrnow.com` (Oracle Cloud, docker-compose)
- **Database:** Supabase project `zjqizajswdpmtdovjxjo` (PostgreSQL, user `postgres`)

---

## 1. Database (already applied ✅)

Schema, rollup view, approval columns, seed, and the Construction Ops migration (company profile, workers/payroll, payments, tax) are already applied. For a **fresh** install, run the `db/*.sql` files in this order (Supabase SQL editor, or psql):

1. `0001_init.sql` — 8 tables (incl. workers) + indexes + rollup view
2. `0004_reconcile_contract_value.sql` — view reads `projects.*_contract_value` (source of truth)
3. `0005_customer_approval.sql` — approval columns (`baseline_*`, `approval_token`, …)
4. `0006_signer_name.sql` — signer-name columns
5. `0007_company_profile.sql` — Ireh Construction branding + financial defaults (single row)
6. `0008_workers_payroll.sql` — workers + payroll_runs/entries + `fn_run_payroll` + `timesheets.overtime_hours`
7. `0009_tax_payments.sql` — invoice GST/PST columns + payments ledger + `recompute_invoice_status()`
8. `0010_quote_trail.sql` — estimate revisions + change-order reason
9. `0011_dashboard_views.sql` — tax-aware rollup + payroll/overdue/follow-up views
10. `0003_seed.sql` — demo data (Oakridge / Kitsilano)
11. `0012_seed_v2.sql` — demo workers, payroll run, payment
12. `0002_idempotency_test.sql` — idempotency check (self-rolled-back)
13. `0013_verification.sql` — migration invariants (self-rolled-back)

> `0002` and `0013` are verification scripts (assert invariants then roll back), not migrations.

---

## 2. n8n credentials

Create two credentials (n8n → Credentials → Add credential). **Name them exactly** so imported workflows auto-link:

**`Supabase PostgreSQL`** (type: PostgreSQL)
| Field | Value |
|---|---|
| Host | `db.zjqizajswdpmtdovjxjo.supabase.co` |
| Port | `5432` |
| Database | `postgres` |
| User | `postgres` |
| Password | your Supabase database password |
| SSL | **On** (required) |

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

## 3. Environment (docker-compose)

Add to the n8n service environment, then restart:
```yaml
environment:
  - GMAIL_USER=yourname@gmail.com
  - PUBLIC_BASE_URL=https://n8n2.ordrnow.com
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

Activate both. If n8n flags any node as "credential missing", select `Supabase PostgreSQL` / `Gmail SMTP`.

---

## 5. Webhook URLs (base already baked in)

| Purpose | URL |
|---|---|
| Vapi tool-calls | `https://n8n2.ordrnow.com/webhook/voice/gateway` |
| Estimate approval page | `https://n8n2.ordrnow.com/webhook/approve-estimate?token=<uuid>` |
| Change order approval page | `https://n8n2.ordrnow.com/webhook/approve-change-order?token=<uuid>` |

The base URL `https://n8n2.ordrnow.com` is already set in the 3 Code nodes that build links/emails (gate-0012, gate-0016a, gate-0017a).

---

## 6. Vapi assistant

Per `VAPI_ASSISTANT.md`: create the assistant (voice provider `11labs`), add the **17 function tools** (the 5 new ones' JSON is in `backend/vapi_tools_additions.json`), and point every tool's `server.url` at:

```
https://n8n2.ordrnow.com/webhook/voice/gateway
```

⚠️ After the **first live tool-call**, confirm the `Normalize Tool Call` node matches Vapi's actual payload (`body.message.toolCalls[0].function.{name,arguments}`) and adjust the mapping if Vapi nests it differently.

---

## Verification checklist

- [ ] Both workflows imported + active, no missing-credential warnings
- [ ] `company_profile` has exactly one row with Ireh Construction branding
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
- **Secrets:** the DB password and Gmail App Password live only in n8n credentials — never commit them.
- **Idempotency:** `change_orders`/`timesheets` carry a `tool_call_id` unique key; replayed Vapi calls are no-ops (ADR-3).
