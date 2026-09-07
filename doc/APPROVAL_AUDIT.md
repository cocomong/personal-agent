# Approval audit trail + PM notification (2026-09-07, D47–D50)

Context: after the estimate-approval fix (portal webhook paths), the PM asked
for three things: (1) a trail of estimate status changes, (2) proof that
approval emails were sent successfully, and (3) a push to the PM when the
customer approves (or rejects) an estimate. The auto-send-to-customer-on-PM-
approve flow was DISCUSSED and deferred (see "Next decision" at the bottom).

## What was built

### db/0029 approval_log (+ db/0030 self-rolling verify) — applied live
One row per event. Kinds today: `estimate_sent`, `estimate_approved`,
`estimate_rejected`, `change_order_sent`. Columns: company_id, project_id
(NOT NULL, FK ON DELETE CASCADE — test projects clean their trail up
automatically), kind, recipient, message_id (Gmail's id at send time = the
"sent successfully" proof), note, created_at. Registered in deploy/migrate.sh.

### Email-send logging (gateway)
After each approval-request gmail send (estimate + change-order chains), a new
Postgres node writes kind `estimate_sent` / `change_order_sent` with the
recipient and the Gmail message id. The change-order lookup now also exposes
`p.id AS project_id` (approval_log.project_id is the PROJECT). Verified live:
an approval-request email to support.ordrnow@gmail.com produced a log row with
a real Gmail message id.

### Customer decision -> PM push + decision log (Customer Approval Portal)
New chain after `Estimate Approval Update`:
Portal Devices (device_tokens, guaranteed row) → `Exec: pm_estimate_notice`
(code: FCM data {type:'notice', title, body}) → `Exec: log_estimate_decision`
(writes estimate_approved / estimate_rejected with signer/method/push note) →
Confirm.

- Push text: "Estimate approved — <project>: $<contract> signed by <signer>."
  (or rejected). Per-token resilience: a NotRegistered (stale) token is
  skipped, not fatal — verified live: 2 stale skipped, 1 live device pushed.
- Automation signers (`QA ...` / `... Robot` — the E2E script's signer) have
  the PUSH suppressed but the log row still written, so test runs never spam
  the PM's phone.
- The E2E script (qa/e2e_estimate_approval.py) now asserts the approval_log
  row (kind + signer + push-suppressed note). 9/9 checks green live.

### App: `notice` push type
fcm_service (foreground + background) and notification_service gained a plain
`showNotice(title, body)` for informational pushes with no tap action — the
PM notice renders as a normal notification on the new APK.

## Deploy notes / gotchas hit

- Postgres nodes REPLACE the item payload with their query result: inserting
  the log node between the Update and the Confirm page starved the Confirm of
  the update row (baseline_status) → page said "Decision recorded" instead of
  "Approved". Fix: the Confirm code now reads the Update node by reference
  (`$('Estimate Approval Update').first().json`) with the input as fallback.
  Rule: respond/confirm pages must reference the source SQL node by name, not
  assume the input item survives intervening nodes.
- New portal/gateway Postgres nodes need `operation: executeQuery` + the
  credentials block (house pattern) or the whole workflow fails up front.
- FCM code needs `NODE_FUNCTION_ALLOW_BUILTIN=crypto,fs,https` (already set on
  the container) — same helper block as the gateway push nodes.

## Verified live (2026-09-07)

- estimate_sent log row w/ Gmail message id after a real approval-request
  email (recipient = fixture customer's support inbox).
- estimate_approved log row after a real Approve; note records signer, method,
  and push outcome ("pushed to 1 device(s)").
- E2E suite: 9/9 (create → approve → DB asserts → audit row → no-op replay →
  cleanup).

## Next decision (deferred, awaiting PM "go")

Auto-send the estimate to the customer the moment the PM approves/finalizes
it (removing the separate "send for approval" step). Guardrails agreed:
hold when the customer has no email; send only on an explicit PM finalize
(never on draft tweaks); refresh the approval token/link on re-send after a
rejection or revision.
