# Invoice Review & Email-Guarantee — Build Notes (2026-08-31)

Feature request (user, 2026-08-30 night): "the assistant has the ability to email
invoice to client, but can you make sure that the email address is set for the
client and if it is not set, ask for it. also, is it possible to verify if the
invoice either by html page or pdf file, is correct by the user before sending it."

Built autonomously overnight under the user's standing overnight grant
("do all that you can, make note of all the decisions you made on your own").

## What changed (summary)

1. **Email guarantee** — sending any client email now refuses with a clear ask:
   - `send_customer_invoice` / `send_estimate_for_approval` /
     `send_change_order_for_approval` respond "customer has no email address on
     file — ask the user for it, call `update_customer_email`, then retry" when
     the client row has no email (the old response was a misleading
     "Invoice or customer not found").
   - New gateway tool **`update_customer_email`** (customer_id = name or id,
     email) persists the address: `UPDATE customers SET email = $2 WHERE
     id::text = $1 OR LOWER(name) = LOWER($1) RETURNING ...`.
2. **Preview-before-send** — `send_customer_invoice` no longer emails the client
   directly. It renders the exact client-facing HTML invoice, wraps it in a
   PREVIEW banner with **Approve & send** / **Reject** links, and emails THAT to
   the PM's own inbox (`company_profile.email_from`). The client email goes out
   only when the PM taps Approve in the preview email.
3. **New webhook workflow** `approve-invoice.json` (deployed id
   `invoice-approval-001`):
   - `GET /webhook/approve-invoice?invoice=<num>&sig=<hmac>` — verifies sig,
     looks up the invoice, sends the real email to the client via Gmail, stamps
     `invoices.email_sent_at`, answers an HTML page ("Invoice sent" / "Already
     sent on <date>").
   - `GET /webhook/reject-invoice?invoice=<num>&sig=<hmac>` — answers "Invoice
     NOT sent", no DB write, invoice stays UNPAID and can be previewed/sent
     again later.
4. **Schema**: `db/0018_invoice_send.sql` adds `invoices.email_sent_at TIMESTAMPTZ`
   (NULL = never sent). Registered in `deploy/migrate.sh`, applied live.
5. **Vapi**: 24 tools now (`update_customer_email` created, `send_customer_invoice`
   description rewritten, system prompt rule 3b added). Sync via
   `backend/create_vapi_assistant.py` (assert bumped >= 24).

## Flow

```
PM: "send invoice INV-1005 to the client"
  -> send_customer_invoice (gateway)
  -> lookup invoice + customer email + branding
  -> Has Email? NO  -> "no email on file, ask user, update_customer_email, retry"
  -> Has Email? YES -> Render Invoice HTML (same template the client gets)
  -> Render Invoice Preview (banner + HMAC approve/reject links)
  -> email preview to company_profile.email_from (PM's inbox)
  -> "Preview emailed to you — tap Approve to send to <client>, or Reject"

PM taps Approve in preview email
  -> GET /webhook/approve-invoice?invoice=..&sig=..
  -> verify HMAC(AUTH_TOKEN_SECRET, invoice)
  -> lookup invoice (email_sent_at included)
  -> already sent? YES -> "Already sent on <date>" page (no resend)
  -> NO -> send real invoice email to client
  -> UPDATE invoices SET email_sent_at = now() WHERE ... AND email_sent_at IS NULL
  -> "Invoice sent" page

PM taps Reject -> GET /webhook/reject-invoice?... -> "Invoice not sent" page
```

Signature scheme (stateless, no new columns/env):
`sig = base64url( HMAC-SHA256( AUTH_TOKEN_SECRET, invoice_number ) )` — reuses the
`AUTH_TOKEN_SECRET` already in the n8n env from the Google sign-in work.

## Decisions made autonomously (D1–D13)

- **D1 — Preview is mandatory.** Every send goes through the visual preview;
  there is NO voice-only "just send it" bypass in v1. Accuracy over speed. If the
  PM wants a verbal-confirm shortcut later, add an optional `confirm: true`
  param to the tool.
- **D2 — Preview target = `company_profile.email_from`** (the Gmail account that
  sends invoices = the PM's own inbox). No new column; can be made configurable
  later (e.g. a `pm_review_email`).
- **D3 — HTML preview, not server-side PDF.** The preview email contains the
  exact HTML the client receives, so what you verify is what gets sent. A PDF
  copy is available via print-to-PDF from the email/browser — same approach as
  the existing customer portal (screen print-to-PDF). Real PDF attachments
  (client-side) would need an HTML→PDF renderer on the VPS; noted as a future
  option, deliberately NOT added tonight (new dependency, no ask for it).
- **D4 — Stateless HMAC links** reusing `AUTH_TOKEN_SECRET`: no token columns,
  no token expiry beyond signature validity, no new env vars.
- **D5 — Double-send guard** = `email_sent_at` check before send (reads the
  timestamp) AND conditional UPDATE after send. Second approve shows
  "Already sent on <date>". Verified in test: two sequential approves sent once.
- **D6 — `update_customer_email` is a general-purpose tool** (also fixes typos /
  changed addresses), not invoice-specific. Matches by id or exact name
  (case-insensitive). Unknown customer -> "Customer not found — ask for the full
  name or ID."
- **D7 — Same no-email treatment applied to estimate/change-order approval
  emails** for consistency; their old responses ("Project not found" when the
  real problem was a missing email) were misleading.
- **D8 — No email-format validation in the gateway.** The tool description tells
  the LLM to collect a valid address; regex validation is a possible hardening
  step (skipped to keep the diff small; a bad address bounces harmlessly).
- **D9 — Invoice HTML template is duplicated** in `approve-invoice.json`
  (n8n Code nodes cannot import shared code). Kept byte-identical to the
  gateway's `Render Invoice HTML`; both files are edited together from now on.
  A single-template refactor (e.g. generated by one Python builder) is the
  clean future fix.
- **D10 — Reject is a no-op on data.** No status column is touched; the invoice
  remains UNPAID and can be previewed/sent again. (A "rejected" audit trail can
  come later if wanted.)
- **D11 — n8n Gmail-output pitfall (found in testing):** the Gmail node's output
  is the sent-message object and does NOT carry the input row's fields. The
  `Mark Invoice Sent` node must read `$('Lookup Invoice').first().json.invoice_number`,
  not `$json.invoice_number` — same class of bug as the documented
  "downstream nodes lose $json.toolArgs" pitfall. Caught because the first
  approve test showed "Already sent" without any timestamp.
- **D12 — In-place workflow deployment** by top-level `id` in the JSON
  (`5Dswa943KQF0rnZ1`, `invoice-approval-001`); `n8n import:workflow` upserts by
  id (no duplicates), CLI `update:workflow --active=true` is ignored until the
  container restarts (existing known pitfall, applied again).
- **D13 — QA hygiene:** test customer/project/invoices (INV-QA-1001/1002) were
  created, exercised end-to-end, then fully deleted. Side effects that remain:
  one preview email in the PM's inbox (support.ordrnow@gmail.com) and two
  sends to noreply@example.com (a deliberately fake address — bounces, no real
  recipient ever touched).

## Files changed

- `backend/n8n/workflows/voice-gateway.json` — +`update_customer_email` branch
  (router + Exec node + Format Spoken Result case), invoice lookup now returns
  `customer_id` + `email_from`, client-direct-send replaced by preview render +
  preview email nodes, no-email / preview-first messages in all three send cases.
- `backend/n8n/workflows/approve-invoice.json` — NEW workflow (18 nodes).
- `backend/vapi_assistant.json` — new tool, updated description, prompt rule 3b.
- `backend/create_vapi_assistant.py` — tool-count assert >= 24.
- `db/0018_invoice_send.sql` — NEW; `deploy/migrate.sh` — registered.
- `backend/README.md` — endpoints table + notes.

## How to verify (manual)

1. Vapi web chat: "send invoice INV-<n> to the client" with a client that has no
   email -> assistant asks for the email. Give it -> it saves it and retries.
2. With an email on file -> assistant says a preview was emailed to you.
3. In your inbox: PREVIEW email with Approve/Reject -> tap Approve -> client gets
   the real invoice; tapping again shows "Already sent".
