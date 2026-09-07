# Test Plan — Personal Agent (Ireh / MSI construction PM assistant)

Four layers. L0 and L1 are scripted and repeatable; run them after any change
to the gateway, portal, or app logic. L2/L3 are smoke/manual layers that need
a live Vapi session or a device.

| Layer | What | Command | Needs | When |
|---|---|---|---|---|
| L0 | App UI logic (widget tests) | `cd mobile-flutter && flutter test` | none (offline) | after any app change |
| L1 | Live API end-to-end (gateway tools + portal approve) | `python3 qa/e2e_estimate_approval.py` | network to VPS + passwordless ssh | after gateway/portal deploys; regression for approval webhooks |
| L2 | Chat-channel smoke (real LLM) | curl /webhook/chat (see below) | live Vapi key/credits + app token | when chat UX/tooling changes |
| L3 | Manual device QA | checklists below | phone + installed APK | release candidates |

## L0 — Flutter widget tests (`mobile-flutter/test/`)

Run: `flutter test` (also `flutter analyze`). No device, no network, no Vapi.

- `widget_test.dart` — smoke: AgentScreen renders Voice/Text switch + Start
  Voice (voice-first shell).
- `agent_chat_flow_test.dart` — the text-chat flow the PM runs:
  - voice-first shell hides the text input until Text mode is picked;
  - switching to Text shows the input + Send;
  - typing a request and sending renders the user bubble and the assistant
    reply (fake ChatController injected via the AgentScreen `chat` seam);
  - a chat failure renders the error message instead of crashing.
  The app ROOT (auth gate) needs platform plugins and is NOT covered here —
  it is exercised on-device (L3).

To add a case for a new screen flow: inject a fake of the screen's service
through a constructor seam, drive widgets with `tester`, assert on bubbles/
state. Do not attempt real network or Vapi sessions in widget tests.

## L1 — Live end-to-end script (`qa/e2e_estimate_approval.py`)

Reproduces, against the LIVE server, the flow the PM runs from the app:
lookup_or_create_customer → create_project → create_estimate →
GET /webhook/approve-estimate (renders the lines + Approve form) →
POST /webhook/estimate/approval (customer signs) → DB asserts:
baseline_status APPROVED, contract value = sum of estimates ($105,000),
signer/method recorded; re-approve is a guarded no-op.

- Tool calls go through the real gateway exactly as Vapi would send them
  (deterministic — no LLM, no Vapi credits).
- Portal page + Approve POST go through the real Customer Approval Portal —
  this is the regression net for the 2026-09-07 doubled-webhook-path bug
  (`/webhook/webhook/estimate/approval`).
- Side effects: creates one throwaway customer/project/estimate, approves it
  for real, then deletes the customer (cascade removes the rest). Nothing is
  emailed. `--keep` leaves the rows for inspection.
- Exit 0 = all checks passed; a named step on failure.

Run it after every gateway or portal deploy. Add sibling scripts for other
pipelines (invoice send → approve, change-order approval) as those flows
stabilize.

## L2 — Chat channel smoke (manual, real LLM)

The L1 script bypasses the LLM on purpose. To smoke the full chat path
(assistant → tool → reply) once per release:

    curl -s -m 180 -X POST https://n8n2.ordrnow.com/webhook/chat \
      -H "Content-Type: application/json" \
      -d '{"input":"list projects"}'          # needs X-User-Token in real use

Expect a JSON reply listing the active projects (tools executed server-side).
Costs a few cents of Vapi credit per call.

## L3 — Manual device QA (release candidates)

Install the latest APK, then:
1. Push-links 5-step tap test: doc/PUSH_LINKS.md (notification View/Approve
   buttons on invoice pushes — the action-button rendering is device-only).
2. Invoice build QA checklist: doc/INVOICE_REVIEW_NOTES.md (create → push or
   email → view/approve → client email lands in the QA inbox).
3. Customer flow: say "find customer Tam" (fuzzy match), create a project +
   estimate, approve it from the phone (establishes L1's flow on-device).
4. Google sign-in on a fresh install (Step 1 leftover).
5. Voice: Start Voice → ask for project status (real call + transcript).

## Regression notes (why L1 exists)

2026-09-07: an estimate Approve tap 404'd ("internal server error") because
the portal action webhooks were registered at /webhook/webhook/... while the
forms posted to /webhook/... — a pure plumbing bug invisible to every tool
probe and to the GET page. L1 covers the POST path so this class fails
loudly in CI-style runs instead of on a customer's phone.
