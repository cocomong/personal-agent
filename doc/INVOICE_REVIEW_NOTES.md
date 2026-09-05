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

---

# 2026-09-05 build — lifecycle, numbering, resend, audit (decisions D14–D24)

Follow-up build fixing the ten issues found in the invoice-flow review
(2026-09-04). Built autonomously under the user's overnight grant, plan approved
in advance. Migrations 0021 (schema) + 0022 (self-rolling-back verify) applied
live; voice-gateway + approve-invoice workflows redeployed (both active);
Vapi assistant re-synced (24 tools, contracts updated, read-back verified).
Pre-apply backup: /home/ubuntu/backups/pm/pre-invoice-fixes-20260905-084813.sql.

## What changed (map to the reviewed issues)
- **#1 Status lifecycle**: nothing ever moved invoices out of DRAFT. Now the
  approve-time send flips DRAFT -> UNPAID (Mark Invoice Sent UPDATE); 0021
  backfilled already-emailed DRAFT rows to UNPAID. OVERDUE/PAID still recompute
  on payment; a periodic pass (`fn_refresh_invoice_statuses()`, migration 0021)
  exists and gets wired to the Deadline Reminder schedule later.
- **#2 Resend**: an already-sent invoice now shows an "Already sent on <date> —
  Send this invoice again" page (2-tap confirm, no silent resend). Fixing the
  customer email via update_customer_email then resending now works.
- **#3 Numbering**: per-company sequence. `company_profile.invoice_last_number`
  counter + `invoice_prefix` + LPAD(4) -> INV-0001, INV-0002... allocated
  atomically in the create CTE (UPDATE ... RETURNING inside the INSERT). Legacy
  epoch-ms numbers grandfathered; counter starts at 0 (first real invoice is
  INV-0001 — verified: two allocations in the live test produced 0001, 0002).
- **#4 Content honesty**: create_invoice tool description rewritten (billing = %
  of revised contract value, tax from company rates); removed the fake
  `include_change_order_ids` param; invoice_type enum now the canonical stored
  values (DEPOSIT/PROGRESS_BILLING/CHANGE_ORDER/FINAL); added optional
  `description` shown on the invoice; billing_percentage defaults to 100 (so
  FINAL works without it). Real line-item itemization stays a future build.
- **#5 Holdback**: automatic — net_amount x company retention_rate (10%) on
  Deposit/Progress/Change Order invoices, 0 on FINAL; shown on the invoice and
  counted by the rollup's retention_held. Live-verified (2625.00 on a 50% draw).
- **#6 Delivery visibility**: every outbound email (preview, client, resend)
  and every reject is logged to `invoice_email_log` with recipient + Gmail
  message_id. True bounce/read tracking still needs Gmail watch/PubSub — future.
- **#7 Single template**: the client HTML is rendered ONCE at preview time and
  stored in `invoices.last_client_html`; approve emails that stored copy (legacy
  rows fall back to an inline re-render). Previewed == sent, template edited in
  one place (the gateway Render Invoice HTML node).
- **#8 Audit + expiry**: new sig scheme `HMAC(secret, company.invoice.action.exp)`
  with 90-day expiry and approve/reject action binding. Legacy approve links
  (HMAC over number only) still verify; legacy reject links are now invalid
  (they were indistinguishable from approve and only cancelled sends — benign).
  Rejects are logged (audit) — previously nothing was recorded.
- **#9 Cross-tenant (Step 3-proof)**: the signed payload carries company_id; the
  approve/reject lookups filter `WHERE company_id = <signed>`, so a link minted
  for one company cannot act on another company's same-numbered invoice.
- **#10**: invoice lookups resolve the company via the project
  (`JOIN company_profile cp ON cp.id = p.company_id`) instead of hardcoded id=1;
  create_invoice is likewise project-driven, so per-company numbering works for
  every company the moment Step 3 lands.

## Decisions made this build (D14–D24)
- D14: numbering counter on company_profile (INT, transactional) rather than a
  Postgres sequence — one counter per company row, rolls back with its tx.
- D15: holdback auto-applied at company retention_rate unless invoice_type=FINAL.
- D16: invoice is ISSUED (UNPAID) at first client send, not at creation; DRAFT
  rows are never sent-able twice (email_sent_at still gates the first send).
- D17: stored-HTML (last_client_html) is authoritative for the client email;
  gateway is the single template owner.
- D18: resend is a deliberate second tap on the Already-sent page (resend=1
  param); resends are logged kind=resend and never change status/email_sent_at.
- D19: invoice_email_log rows: preview (recipient = PM inbox), client/resend
  (recipient = client, message_id from the Gmail node output), reject
  (no recipient). FK invoice_id ON DELETE CASCADE.
- D20: signature v2 = base64url HMAC over `company.invoice.action.exp`; legacy
  approve accepted with no expiry; legacy reject rejected. Old previews' Reject
  buttons stop working (harmless); their Approve buttons still work.
- D21: email format validation on update_customer_email (SQL regex) with
  outcome OK / INVALID_EMAIL / NOT_FOUND — a bad address is refused, not saved.
- D22: create_invoice queryReplacement defaults billing_percentage to 100 so a
  Final invoice never breaks on a missing percentage.
- D23: gate node added in approve flow (Invoice Found?) — a valid-sig link for a
  deleted invoice shows the invalid page instead of erroring the webhook.
- D24: holdback line on the invoice HTML only renders when > 0 (no "$0.00
  Holdback" noise); description renders when present.

## Still open (explicitly out of scope this build)
- Bounce/read tracking (needs Gmail watch API / Pub/Sub) — log has message_id
  ready for it.
- Real line-item itemization (invoice_line_items) and PDF attachments (D3).
- fn_refresh_invoice_statuses is not yet scheduled — wire it with the Deadline
  Reminder workflow so stored OVERDUE ages without a payment event.

## Manual QA for the PM (next interaction)
1. Voice: "create a progress invoice for Oakridge at 50%" -> expect INV-0001,
   amount incl. GST, holdback line mentioned.
2. "send invoice INV-0001" -> preview email in support.ordrnow@gmail.com with
   Approve + Reject; approve -> client email (noreply@example.com if fixture)
   -> page "Invoice sent"; DB: status UNPAID, email_sent_at set, log row kind
   client.
3. Tap the same Approve link again -> "Already sent — Send this invoice again"
   -> tap -> resent (log kind resend).
4. Change the client email (wrong address) then resend -> works.
5. list_invoices / "who owes me money" now surfaces sent invoices as UNPAID/
   OVERDUE instead of hiding them as DRAFT.

---

# 2026-09-05 build 2 — invoice presentation & capture (decisions D25–D30)

User-directed additions to what appears on the client invoice, agreed in
discussion: free-text payment instructions, structured customer bill-to address,
percentage-only billing with a descriptive auto-line, dynamic holdback label,
raw-type translation, company tax numbers; onboarding captures the new company
fields and everything is voice-editable later. Migrations 0023 + 0024 applied
live (hermetic + live verified); voice-gateway + approve-invoice +
vapi-assistant-hook redeployed (active); Vapi re-synced (25 tools; stale
update_customer_email resource deleted). Pre-apply backup:
/home/ubuntu/backups/pm/pre-invoice-presentation-20260905-*.sql.

## What changed
- company_profile += gst_reg_number, pst_reg_number, payment_instructions (free
  text "How to pay" block). customers += structured street_address / city /
  province / postal_code (bill-to). invoices += billing_percentage +
  billed_basis (snapshots so the descriptive line never misstates the basis
  after a contract change; legacy rows render a plain type label).
- Client invoice (single template — gateway Render Invoice HTML; approve's
  legacy fallback kept in sync via the shared builder): company tax numbers
  under the header when present; Bill-to block when the customer has an
  address; How-to-pay block when instructions exist; Holdback label shows the
  ACTUAL retention rate ("Holdback (10% retained)" derived from
  company_profile.retention_rate, not hardcoded); invoice type displayed via a
  translation map (DEPOSIT -> Deposit, PROGRESS_BILLING -> Progress billing,
  etc.); the net row is a descriptive line = free-text description when set,
  else "Progress billing — 50% of revised contract value ($52,500.00)" from the
  snapshots.
- update_customer_email -> update_customer (consolidated): one customer editor
  for email (validated) + phone + address; SQL returns single outcome
  OK / INVALID_EMAIL / NOT_FOUND. All spoken texts + tool descriptions updated.
- New tool update_company_billing: GST/PST numbers + payment instructions,
  partial COALESCE update on company_profile id 1 (Step 3 resolves the company).
- Onboarding (hook onboarding_steps + complete_onboarding tool + gateway node):
  now also asks for company billing address, GST number, optional PST number,
  and payment instructions (read back for confirmation) before the worker list.
- Vapi prompt: rule 3 rewritten (percentage billing, no line items — the old
  text promised change-order line items that never existed); references to the
  renamed tool fixed; onboarding fallback text extended.

## Decisions D25–D30
- D25: payment_instructions is free text (banks/cheques/etransfer vary too much
  for structured columns); rendered verbatim with line breaks.
- D26: customer bill-to is STRUCTURED (street/city/province/postal) per user.
- D27: billing stays percentage-only with ONE descriptive line (description or
  auto-generated from snapshots); no true line items — the invoice_line_items
  itemization build remains future.
- D28: company tax numbers + payment instructions + billing address are
  collected in onboarding AND editable later by voice (update_company_billing).
- D29: display-only translation for invoice_type (DB stays canonical; legacy
  friendly spellings also mapped so old rows render sanely).
- D30: template renders each block only when its data exists (no empty
  "GST #" / "Bill to" / "$0.00" noise).

## Verified
- Hermetic: fresh-chain migrations incl. 0023/0024 idempotent re-runs.
- Template: the deployed buildClientInvoiceHtml executed against a fixture in a
  node harness — GST #, PST #, bill-to block, how-to-pay block, "Holdback (10%
  retained)" from rate, "Progress billing" translation, auto descriptive line
  "$52,500.00", and total all asserted.
- Live SQL: update_company_billing partial update and update_customer
  (multi-field OK; invalid email -> INVALID_EMAIL, nothing saved) — rolled back.
- Deployed exports carry all markers; gateway + approve webhooks 200.

## Manual QA for the PM (next interaction)
1. Voice onboarding on a fresh company (or update_company_billing now):
   supply GST number + payment instructions -> confirm invoice shows them.
2. "create a progress invoice for Oakridge at 50%" -> INV-00xx; the client
   invoice should show: company GST #, Bill to (Dave Miller / Miller Homes
   address once set via update_customer), the descriptive line with basis, and
   How to pay.
3. "update the customer Dave Miller's address to ..." then re-send a preview
   -> bill-to block appears.
4. Set a different retention_rate on the company (test) -> holdback label
   follows it.
