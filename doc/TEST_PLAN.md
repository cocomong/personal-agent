# Test Plan — Personal Agent (Ireh / MSI construction PM assistant)

Four layers. L0, L1, and L2 are scripted and repeatable; run them after any change
to the gateway, portal, or app logic. L3 is the manual device layer.

| Layer | What | Command | Needs | When |
|---|---|---|---|---|
| L0 | App UI logic (widget tests) | `cd mobile-flutter && flutter test` | none (offline) | after any app change |
| L1 | Live API end-to-end (gateway tools + portal approve) | `python3 qa/e2e_estimate_approval.py` | network to VPS + passwordless ssh | after gateway/portal deploys; regression for approval webhooks |
| L2 | Chat-channel battery (scripted, real LLM) | `python3 qa/chat_text_battery.py` | network to VPS + `VAPI_PRIVATE_KEY` in `~/.hermes/.env` (+ passwordless ssh for live fixtures and `--side-effects`) | after any prompt/tool/gateway change; nightly |
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

## L2 — Chat-channel battery (`qa/chat_text_battery.py`)

Scripted PM questions through the app's own text path, with tool-level truth behind them.
Two layers, because they answer different questions:

- **Layer A — the app path.** `POST {root}/webhook/chat {input, chatId?}`, byte-for-byte what
  `mobile-flutter/lib/session/chat_controller.dart` sends. Asserts the turn returned 200, the
  reply is a real answer, it never carries the failure boilerplate ("No result returned"), the
  expected content is in it, and multi-turn context survives the `chatId` chain.
- **Layer B — which tools fired.** `POST api.vapi.ai/chat` with the same assistant, reading the
  tool-call frames. The n8n proxy returns only the final text, so a tool that 404s still
  produces a plausible reply; this layer asserts the tool was actually called and that its
  result came back with content.
- **Layer C (`--side-effects`)** — an 11-field fingerprint of the app DB (counts, money sums,
  emailed-invoice count) before and after. A read-only turn must change nothing.

Fixtures are read from the live DB (project/customer names, the estimate total), so the battery
does not rot when the data changes; it falls back to last-known values without ssh.

    python3 qa/chat_text_battery.py                 # layers A + B
    python3 qa/chat_text_battery.py --side-effects  # + DB fingerprint before/after
    python3 qa/chat_text_battery.py --layer app     # the app's own path only

Exit 0 = every check passed. Costs a few cents of Vapi credit per case.

**READ-ONLY BY DESIGN.** Every case uses a read-only tool. The write tools
(`send_customer_invoice`, `send_invoice_to_phone`, `send_payment_receipt`, `record_payment`,
`run_payroll`, `create_*`, `add_worker`, `update_*`, `complete_onboarding`, `set_briefing_time`,
`lookup_or_create_customer`) are deliberately NOT exercised — they send real email/SMS to real
customers and write live rows. Add them only against a dedicated test company.

**Step 3 note:** with no `X-User-Token` the workflow resolves uid=null and falls back to
company 1, which is why this battery needs no secret — and why the endpoint currently answers as
company 1 for anyone holding the URL. When Step 3 lands, add a token-path case plus an
"absent/foreign token cannot reach another company" case.

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

## Regression notes (why L2 exists)

2026-09-10: four of the 29 Vapi tools (`find_customer`, `list_estimate_status`,
`send_invoice_to_phone`, `send_payment_receipt`) shipped without their own `server.url`, so they
inherited the assistant-level URL (the call-start hook), 404'd, and Vapi substituted
"No result returned..." — which the model read as "the record does not exist". The chat reply
still looked plausible, so nothing failed until a human noticed. L2 asserts both halves: the
boilerplate never reaches a reply (layer A) and the expected tool really ran (layer B).

Two traps found while building it, both now guarded:
- `psql` prints an ERROR and still exits 0 without `-v ON_ERROR_STOP=1`, so a broken statement
  is indistinguishable from an empty result — the first version of layer C passed while
  comparing two empty strings. `sql()` sets it, checks stderr, and the snapshot is asserted to
  carry all 11 fields before it is compared.
- `invoices.id` is a uuid, so `max(id)` cannot be used as a fingerprint; counts alone would also
  miss a turn that *modified* a row, hence the money sums.

## Regression notes (why L1 exists)

2026-09-07: an estimate Approve tap 404'd ("internal server error") because
the portal action webhooks were registered at /webhook/webhook/... while the
forms posted to /webhook/... — a pure plumbing bug invisible to every tool
probe and to the GET page. L1 covers the POST path so this class fails
loudly in CI-style runs instead of on a customer's phone.
