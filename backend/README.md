# Backend: n8n Vapi Gateway

The backend layer of the Vapi-primary Construction PM Assistant.

**n8n unified gateway** (`n8n/workflows/voice-gateway.json`) — the synchronous webhook that routes Vapi tool-calls to PostgreSQL business logic. **This is the required backend piece.**

> **Stack direction (v1.2):** Vapi orchestrates voice + same-session text; ElevenLabs is the voice engine inside Vapi (`voice.provider='11labs'`). The mobile app talks to Vapi (voice/text on one session) and Vapi sends tool-calls here. There is **no separate text relay** needed — Vapi native same-session text.

```
React Native app ──voice + text (SAME Vapi session)──► Vapi.com
                                                          │ tool-call
                                                          ▼
                                                   n8n /voice/gateway
                                                          │
                                                          ▼
                                                   Supabase/PostgreSQL
```

---

## 1. n8n Unified Gateway

**Import:** n8n canvas → **Import from JSON** → `n8n/workflows/voice-gateway.json`.

**Webhook:** `POST https://<n8n>/webhook/voice/gateway`

Routes on Vapi tool-calls (Vapi sends `message.toolCalls[0].{id, function:{name, arguments}}`):

| Vapi tool function name | Routed to |
|---|---|
| `lookup_or_create_customer` | `Exec: lookup_or_create_customer` — upsert by email |
| `create_project` | `Exec: create_project` — insert project |
| `create_estimate` | `Exec: create_estimate` — insert base estimate |
| `create_change_order` | `Exec: create_change_order` — insert CO + auto-number (ADR-3 `tool_call_id`) |
| `log_timesheet` | `Exec: log_timesheet` — insert hours (ADR-3 `tool_call_id`) |
| `create_invoice` | `Exec: create_invoice` — SQL computes net + GST (+PST if `pst_applicable`) from `company_profile` (ADR-2) |
| `send_customer_invoice` | `send_customer_invoice_lookup` (DB) → `Render Invoice HTML` (branded) → `send_customer_invoice_email` (Gmail) |
| `get_project_statement` | `Exec: get_project_statement` — rollup view query |
| `get_estimate_approval_link` | `Exec: get_estimate_approval_link` — return baseline approval token |
| `get_change_order_approval_link` | `Exec: get_change_order_approval_link` — return CO approval token |
| `send_estimate_for_approval` | `send_estimate_for_approval_lookup` (DB) → `Render Estimate Approval Email` → `send_estimate_for_approval_email` (Gmail) |
| `send_change_order_for_approval` | `send_change_order_for_approval_lookup` (DB) → `Render Change Order Approval Email` → `send_change_order_for_approval_email` (Gmail) |
| `record_payment` | `Exec: record_payment` (insert payment, ADR-3 `tool_call_id`) → `Exec: record_payment_status` (recompute status + balance) |
| `run_payroll` | `Exec: run_payroll` — calls `fn_run_payroll($1,$2)` (aggregates timesheets, CPP/EI/WCB from `company_profile`) |
| `get_payroll_summary` | `Exec: get_payroll_summary` — `view_payroll_summary` query |
| `add_worker` | `Exec: add_worker` — upsert `workers` (auto `W-###` code) |
| `get_dashboard_summary` | `Exec: get_dashboard_summary` — `view_project_financial_summary` (one or all projects) |

> **Branding is configurable, not hardcoded.** Company name/address/phone/colors/signature live in the `company_profile` table (single row, `db/0007`). The gateway's email-render Code nodes read those fields via a `CROSS JOIN company_profile`. The deployment URL is read from `$env.PUBLIC_BASE_URL` (n8n env var) — see `DEPLOY.md`.

> The gateway's `Normalize Tool Call` node maps Vapi's `message.toolCalls[0].function` payload to a canonical `{ toolCallId, action, arguments }` shape before the actions sub-router. Apply Vapi's actual field nesting (`function.name` / `function.arguments`) in that mapping.

### Environment / credentials
- **PostgreSQL credential** named `Supabase PostgreSQL` — connect to the Supabase project with the schema in `db/0001_init.sql`.
- **Gmail SMTP credential** (type `smtp`) named `Gmail SMTP` — host `smtp.gmail.com:465` (SSL), user = your Gmail address, password = a 16-char Gmail **App Password** (Google → Security → 2-Step Verification → App passwords). `GMAIL_USER` env holds the sending address (used as `fromEmail`).
- **n8n webhook URL** — point the Vapi assistant tools at `POST https://<n8n>/webhook/voice/gateway`.

### Idempotency (ADR-3)
`tool_call_id` columns on `change_orders` and `timesheets` (with UNIQUE constraints in `db/0001_init.sql`) prevent duplicate inserts on Vapi retries. The gateway INSERTs use `ON CONFLICT (tool_call_id) DO NOTHING`, so a replayed call returns 0 rows instead of erroring. See `db/0002_idempotency_test.sql`.

### Invoice delivery (send_customer_invoice)
The chain is: `send_customer_invoice_lookup` (DB: invoice + project + customer) → `Render Invoice HTML` (styled invoice body, design-doc Section 7 approach) → `send_customer_invoice_email` (Gmail SMTP HTML email). For a PDF attachment instead of an HTML email, render via the browser print path (design Section 7) or add an HTML-to-PDF node.

---

## 2. Notes (retired relay)

An earlier revision shipped a text relay (`backend/relay/`) to bridge text chat to an ElevenLabs conversational WebSocket. Under **Vapi-primary**, same-session text is native to Vapi (`vapi.send({type:'add-message',...})`), so the relay is **not used** by the mobile app and is retained only as reference for a hypothetical ElevenLabs-only endpoint. It can be removed if not needed.

---

## 3. How it connects to the mobile app

| App need | Calls | Returns |
|---|---|---|
| Voice + text (same Vapi session) | Vapi RN SDK (`vapi.start` / `vapi.send`) | — |
| Agent tool-calls → DB | n8n `POST /voice/gateway` | `{ results[] }` |
| Voice engine | Vapi assistant `voice.provider='11labs'` (configured in Vapi) | ElevenLabs TTS |

The mobile `AgentScreen` / `VapiSessionController` (in `mobile/`) drives voice + same-session text through Vapi; only Vapi's tool-calls hit this n8n gateway.

---

## 2. Customer Approval Portal

A second workflow (`n8n/workflows/approval-portal.json`) hosts the **customer-facing** approval pages. It is separate from the voice gateway because the customer's browser hits it directly (not Vapi).

| Endpoint | Method | Action |
|---|---|---|
| `/webhook/approve-estimate?token=` | GET | Render baseline estimate + Approve/Reject form |
| `/webhook/estimate/approval` | POST | Record approval; set `original_contract_value` = Σ(estimates) |
| `/webhook/approve-change-order?token=` | GET | Render one change order + Approve/Reject form |
| `/webhook/change-order/approval` | POST | Record approval; recompute `revised_contract_value` |

- Token-gated: `approval_token` on `change_orders`, `baseline_approval_token` on `projects` (`db/0005`, `0006`).
- `create_change_order` (voice gateway) is gated on `baseline_status = 'APPROVED'`.
- The CO-approval recompute must add the just-approved `decided` delta explicitly — data-modifying CTEs share one snapshot, so a `recalc` CTE can't see the `decided` flip (see `SYSTEM_DESIGN.md` §5).
- Signer name is captured as typed-name e-signature (`signer_name` / `baseline_signer_name`).

## Open items (build after scaffold)
- [ ] Apply `db/0001`–`0011` to Supabase; optionally load `db/0003_seed.sql` + `db/0012_seed_v2.sql` and run `db/0002_idempotency_test.sql` + `db/0013_verification.sql`.
- [ ] Point the gateway's tool-call webhook at the real n8n URL and map Vapi's exact `message.toolCalls[0].function` shape in `Normalize Tool Call`.
- [ ] Build the Vapi assistant (voice provider='11labs') per `VAPI_ASSISTANT.md`, add the 17 tools (`backend/vapi_tools_additions.json` has the 5 new ones), and confirm same-session voice+text on a device.
- [ ] Move the hard-coded `Supabase PostgreSQL` / SendGrid credential ids to real n8n credentials.
- [ ] Import the 3 scheduled workflows (overdue / quote-follow-up / payroll digest) and activate.
- [ ] (Optional) Upgrade `send_customer_invoice` from HTML email body to a PDF attachment (n8n HTML→PDF node).
