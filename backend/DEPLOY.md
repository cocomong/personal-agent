# Deployment Guide — Construction PM Assistant (backend)

How to deploy the n8n workflows against the live Supabase database and Gmail.

## Current deployment
- **n8n:** `https://n8n2.ordrnow.com` (Oracle Cloud, docker-compose)
- **Database:** Supabase project `zjqizajswdpmtdovjxjo` (PostgreSQL, user `postgres`)

---

## 1. Database (already applied ✅)

Schema, rollup view, approval columns, and seed are already applied. For a **fresh** install, run the `db/*.sql` files in this order (Supabase SQL editor, or psql):

1. `0001_init.sql` — 7 tables + indexes + rollup view
2. `0004_reconcile_contract_value.sql` — view reads `projects.*_contract_value` (source of truth)
3. `0005_customer_approval.sql` — approval columns (`baseline_*`, `approval_token`, …)
4. `0006_signer_name.sql` — signer-name columns
5. `0003_seed.sql` — demo data (Oakridge / Kitsilano)
6. `0002_idempotency_test.sql` — idempotency check (self-rolled-back)

> `0002` is a verification script (asserts replayed tool-calls don't double-insert), not a migration.

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
```

---

## 4. Import the workflows

n8n → **Workflows → Import from File** (or drag the JSON onto the canvas):

1. `backend/n8n/workflows/voice-gateway.json` — Vapi tool-call router (12 tools)
2. `backend/n8n/workflows/approval-portal.json` — customer approval pages

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

Per `VAPI_ASSISTANT.md`: create the assistant (voice provider `11labs`), add the **12 function tools**, and point every tool's `server.url` at:

```
https://n8n2.ordrnow.com/webhook/voice/gateway
```

⚠️ After the **first live tool-call**, confirm the `Normalize Tool Call` node matches Vapi's actual payload (`body.message.toolCalls[0].function.{name,arguments}`) and adjust the mapping if Vapi nests it differently.

---

## Verification checklist

- [ ] Both workflows imported + active, no missing-credential warnings
- [ ] `create_change_order` refuses until `baseline_status = 'APPROVED'`
- [ ] Estimate approval sets `original_contract_value` = Σ(estimates)
- [ ] CO approval recomputes `revised_contract_value` (self-healing)
- [ ] Gmail sends invoice + approval emails (check "Sent" folder)
- [ ] Approval link opens the page; Approve/Reject records correctly
- [ ] Voice + text same-session on a device (mobile app)

## Notes

- **HTTPS:** TLS terminates at `n8n2.ordrnow.com`, so the typed-name approval page is already a reasonable signature record.
- **Secrets:** the DB password and Gmail App Password live only in n8n credentials — never commit them.
- **Idempotency:** `change_orders`/`timesheets` carry a `tool_call_id` unique key; replayed Vapi calls are no-ops (ADR-3).
