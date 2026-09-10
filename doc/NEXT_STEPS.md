## DONE 2026-09-10 — tool-routing fix: 4 tools were silently dead
`find_customer`, `list_estimate_status`, `send_invoice_to_phone` and
`send_payment_receipt` (all added 2026-09-06..08) shipped WITHOUT their own
`server.url` in backend/vapi_assistant.json. A tool without one inherits the
ASSISTANT-level serverUrl, which points at the call-start hook endpoint
(`/webhook/vapi/assistant-hook`) — not the gateway. Every call to those four
404'd, Vapi substituted its "No result returned … troubleshooting tips"
boilerplate as the tool output, and NO n8n execution row was created (so the
incident read like a Vapi-side blip from the executions view). The model then
treated the failure text as a not-found: chat fd8539b8 asked "how is 5650
Camino", the model called find_customer (a CUSTOMER tool) for a PROJECT
question, and answered "I could not find any customer or project matching
5650 Camino" while the project sat APPROVED in the DB.
Fixed: `server` blocks (gateway URL, timeoutSeconds 15) added to all four tools
→ create_vapi_assistant.py re-run → read-back 29/29 tools routed correctly (new
`qa/verify_vapi_tools.py`). The deployer now REFUSES to deploy if any tool lacks
server.url. Prompt gained two TOOL HONESTY RULES: the literal "No result
returned" string means the CALL FAILED (never conclude absence — retry), and a
tool result only speaks for what that tool searched (find_customer = customers
only, never projects). `vapi-assistant-hook-001` was also reactivated — it had
gone inactive, so voice calls had lost setup/company variable injection (POST
now returns setup_complete/company_name/pm_preferred_name + greeting again).
Live probes after deploy: find_customer('5650 Camino') → "No customers found
matching 5650 Camino …"; list_estimate_status('5650 Camino') → "baseline
APPROVED approved 2026-09-07 by customer, 1 estimate line totaling $270,000".

## DONE 2026-09-08 — estimate state machine (doc/ESTIMATE_STATE.md, D54–D60)
projects.baseline_status is now a REAL state machine: CREATED (on file, never
sent) → SENT (awaiting customer) → APPROVED/REJECTED — state column is the
truth, approval_log is evidence only. send_estimate_for_approval flips
CREATED/REJECTED→SENT + rotates the approval token BEFORE rendering (email
carries the live link) and flips status + logs estimate_sent in ONE atomic
postgres statement; APPROVED projects never reach the gmail node (spoken
'already approved by <who> on <date>'). get_estimate_approval_link (on-site
presentation) transitions CREATED/REJECTED→SENT too. Portal accepts a
customer decision ONLY from SENT (approving a CREATED project is a guarded
no-op: no state change, no log, no PM push); unknown/rotated tokens render a
friendly page. db/0031 remapped live rows by evidence (Test Approval → SENT
via backfilled 2026-08-26 log row; remaining PENDING → CREATED; estimate-line
ACCEPTED → CREATED, default CREATED) + 0032 self-rolling verify; SCHEMA.md
regenerated to 0031. Vapi 29 tools: system prompt gained a Status Model
section; create_estimate status enum CREATED/DRAFT; tool descriptions
state-aware. E2E reworked to the SENT gate — 12/12 green live; real send
probe verified email→SENT+token-rotate+log. Deployed live (gateway + portal
imports, marker-verified).

## DONE 2026-09-07/08 — read-status tools + invoice totals (D51-D53)
list_invoices replies now lead with a COMPUTED total + count ('3 invoices
totaling $41,475: ...') — arithmetic is done in the code node, never trusted
to the LLM. NEW read-only list_estimate_status (Vapi 29 tools): company-wide
estimate/approval status per project (baseline PENDING/APPROVED/REJECTED,
approver + date, estimate line count + total, last approval-log event),
filter by project or baseline status; guaranteed NONE row so 'no match' is
spoken. Prompt rule reinforced: never call create_estimate to check status.
Also deleted the junk $0 DRAFT estimate the assistant created 2026-09-08
when asked 'any draft estimate' (no such read tool existed then — it does
now). E2E unaffected; probes live green.

## DONE 2026-09-07 — approval audit trail + PM notice push (doc/APPROVAL_AUDIT.md, D47-D50)
db/0029 approval_log (+0030 verify, live): kinds estimate_sent/approved/
rejected + change_order_sent; recipient + Gmail message_id = send-success
proof; project FK cascade cleans test trails. Gateway logs each approval-request
email after send; portal writes the customer decision + pushes the PM a
notice-type FCM message (per-token stale skip; automation signers 'QA …'/
'… Robot' suppress the push but still log). App gained plain 'notice' handling.
E2E now asserts the audit row — 9/9 green. Verify visually: install the new
APK, approve an estimate as customer → PM phone gets "Estimate approved".
DEFERRED: auto-send estimate to customer on PM finalize (guardrails agreed,
awaiting go — see doc end).

## DONE 2026-09-07 — automated tests (doc/TEST_PLAN.md): L0 widget + L1 live E2E
- L0: mobile-flutter/test/ — AgentScreen smoke + text-chat flow widget tests
  (mode toggle, send -> user bubble + reply, error path) via an injected
  FakeChatController (AgentScreen gained an optional `chat` seam).
  `flutter test` = 5 passing, offline. Pre-existing root-app smoke test was
  broken headless (auth gate needs plugins) — rewired to AgentScreen.
- L1: qa/e2e_estimate_approval.py — full create customer/project/estimate ->
  approve page -> Approve POST -> DB asserts (APPROVED, contract = estimates)
  -> cleanup. Deterministic (no LLM/credits); regression net for the doubled-
  webhook-path bug. 8/8 green live.
- L2 (manual smoke) + L3 (device QA checklists) in TEST_PLAN.md.

## FIXED 2026-09-07 (commit pending) — estimate/CO Approve button: 'internal server error'
Customer Approval Portal action webhooks were registered at a DOUBLE path
(webhook node path 'webhook/estimate/approval' -> external
/webhook/webhook/estimate/approval) while the rendered forms POST to
/webhook/estimate/approval — every Approve tap 404'd ('not registered').
Fixed node paths to 'estimate/approval' / 'change-order/approval'; portal file
now versioned in repo as backend/n8n/workflows/customer-approval-portal.json.
Pitfall: when a webhook node's path field contains a full-URL fragment
('webhook/...'), n8n prepends /webhook/ AGAIN. GET pages (approve-estimate,
approve-change-order) were unaffected.

# NEXT STEPS — status 2026-09-07 (customer-identity batch DONE; find_customer live)

## DONE 2026-09-07 — customer identity & tool honesty (doc/CUSTOMER_IDENTITY.md, D42–D46)
lookup_or_create_customer always returns a row (FOUND-by-email/name w/ dup
email disclosure vs CREATED); create_project + create_estimate resolve by
name-or-id (no more uuid crashes) and never fabricate; NEW find_customer
fuzzy best-match tool (code-node scoring, top-3 w/ labels); TOOL HONESTY
RULES added to the system prompt. The exact failing scenario now works:
"create a project for Tom Smith, d_tam@yahoo.com" -> assistant reports the
email belongs to David Tam and proceeds with him. Deploy learnings for n8n
2.35.7 (new-node operation/credentials, queryReplacement arity, versioned
activation) recorded in the doc + skill. Re-test from the app: say "find
customer Tam" / redo the 5056 Camino flow.

## DEFERRED — silent-death error-output wiring (#3)
Per-node onError error branches break every execution on n8n 2.35.7; reverted.
Guaranteed-row SQL + honesty rules are the current protection. Revisit with
the correct 2.35 error-handling shape (UI or docs) before re-attempting.

# NEXT STEPS — status 2026-09-07 (invoice push channel + text chat channel done)

## DONE 2026-09-07 — invoice delivery: create -> offer push-or-email; push has View/Approve
Review page /webhook/invoice-review (stored invoice HTML + approve/reject);
send_invoice_to_phone tool; app notification action buttons. Details D37-D40
in INVOICE_REVIEW_NOTES.md. Manual QA: user phone — create invoice, choose
push, tap View (page) and Approve (lands in support.ordrnow inbox — fixture
email points there).

## DONE 2026-09-07 — text chat via n8n proxy to Vapi /chat (silent, separate session)
Details D41 in INVOICE_REVIEW_NOTES.md. ChatController in app; voice mode
unchanged. Manual QA: type in Text mode — silent replies with tools working.

# NEXT STEPS — status 2026-09-06 (trigger gated: brand, domain, public hosting)

## DEFERRED — trigger: app fully built & functional (post-Step-3 + QA). NOT started.
User decision 2026-09-06: no domain/brand yet; no website scaffold until the app
is finished and working. When that trigger fires, plan + build in order:
1. Brand/product name decision (multi-company product, not Ireh-specific).
2. Register dedicated domain (.com + .ca if Canadian construction market).
3. Product website for the app (static; landing, features, screenshots,
   FAQ, support) — Play Store listing needs a privacy policy URL anyway.
4. SECURITY-HYGIENE: hide n8n2.ordrnow.com from customers. Branded subdomain
   (e.g. portal.<domain>) via DNS CNAME/A + Traefik host rule + LE cert on the
   VPS; expose ONLY /webhook paths publicly; keep the n8n workflow editor
   admin UI on the internal hostname only. Flip company_profile.portal_base_url
   + PUBLIC_BASE_URL to the branded host so every customer-facing link/email
   (approve links, portal pages) shows the brand. Signatures are host-agnostic
   so old links keep working.
Guidance recorded: registrar Porkbun/Cloudflare; site = www.<domain>,
proxy = portal.<domain>; n8n2.ordrnow.com stays internal/admin.

# NEXT STEPS — status 2026-09-06 (push-to-phone links done)

## DONE 2026-09-06 — approval links delivered via push notification (see doc/PUSH_LINKS.md)
get_estimate_approval_link + get_change_order_approval_link now PUSH the link to
registered phones as an FCM 'open_url' data message; voice replies "…sent to your
phone — tap the notification to open it" (speaks the URL only when no device is
registered). App: notification tap opens the link in the system browser
(url_launcher) from foreground/background/terminated states. New APK built.
Follow-ups: (a) user device QA of the tap flow (manual list in PUSH_LINKS.md);
(b) stale NotRegistered device-token cleanup on re-registration; (c) chat-text
rendering gap (typed assistant replies) still open; (d) real "open in app"
portal pages later — same push type + tap handler is the pattern.

# NEXT STEPS — status 2026-09-06 (simple billing model done)

## DONE 2026-09-06 — billing model: progress % of ORIGINAL contract + COs billed at 100%
create_invoice now draws against projects.original_contract_value with a 100% cumulative
cap; CHANGE_ORDER invoices auto-bill every approved, not-yet-billed change order at full
value, itemized (invoice_line_items now used); approve-side duplicate guard; schedule-of-
values method deliberately deferred (documented in INVOICE_REVIEW_NOTES.md). db/0025+0026
live; gateway + approve redeployed; Vapi 25 tools. Decisions D31-D34 + QA: INVOICE_REVIEW_NOTES.md.

# NEXT STEPS — status 2026-09-05 (invoice presentation & capture done)

## DONE 2026-09-05 build 2 — invoice presentation + capture
GST/PST numbers, free-text payment instructions, structured customer bill-to,
dynamic holdback label, type translation, descriptive auto billing line
(snapshots billing_percentage/billed_basis), onboarding captures company billing
details, update_customer (consolidated editor) + update_company_billing voice
tools. db/0023 + 0024 live; gateway + approve + hook redeployed; Vapi 25 tools.
Details + decisions D25-D30 + QA: doc/INVOICE_REVIEW_NOTES.md (bottom).

# NEXT STEPS — status 2026-09-05 (invoice lifecycle build done)

## DONE 2026-09-05 — invoice generation/regen overhaul (overnight build, plan approved)
Full fix of the ten reviewed invoice issues (status lifecycle, resend, per-company
numbering INV-0001+, honest billing contract, auto-holdback, email audit log, single
stored template, expiring action-bound signatures, company-scoped approve links).
db/0021 + 0022 live; voice-gateway + approve-invoice redeployed; Vapi synced (24 tools).
Details + decisions D14-D24: doc/INVOICE_REVIEW_NOTES.md (bottom section).
Manual QA checklist for the PM is at the end of that section.
Remaining from that build (out of scope, tracked): bounce/read tracking (Gmail watch),
real line items, scheduled fn_refresh_invoice_statuses (wire with Deadline Reminder).

# NEXT STEPS — status 2026-09-04 (Step 2 tenant columns done)

## DONE since the header below was written
- Multi-tenant Step 1 (accounts): users table (db/0017), /webhook/auth/google, HMAC session tokens,
  Flutter Google login — live 2026-08-30 (details in doc/MULTITENANT.md).
- Invoice preview-approval + email-on-file (db/0018, approve-invoice workflow) — live 2026-08-31
  (details in doc/INVOICE_REVIEW_NOTES.md).
- **Step 2 TENANT COLUMNS — DONE + verified live 2026-09-04**: db/0019 (`company_id` NOT NULL DEFAULT 1
  on customers/projects/workers/payroll_runs/schedule_items/device_tokens/invoices; company_profile.id
  sequence-driven; per-company unique indexes) + db/0020 self-rolling-back verification. add_worker tool
  fixed + workflow redeployed (see MULTITENANT.md §6 Step 2 note). Pre-apply backup:
  /home/ubuntu/backups/pm/pre-step2-tenant-20260904-163456.sql (VPS).

## UP NEXT
- Step 3 — SCOPED SERVICE (MULTITENANT.md §6): hook returns caller's company; gateway tools filter +
  write with explicit company_id; complete_onboarding CREATES company_profile + links users.company_id;
  drop the DEFAULT 1 once every write path is explicit; relax 0013(a) single-company assert; views/
  functions per §3.4 (view_schedule/view_project_financial_summary company passthrough, fn_run_payroll
  takes company). Biggest chunk of the remaining work.
- Step 4 — STORE POLISH: real release keystore, runtime-config base URLs, app icon, privacy policy,
  Play Console listing.
- Backlog: Capabilities KB on Vapi; Deadline Reminder workflow (lien/holdback nudges, email-first);
  real phone-call test.

## NICE-TO-HAVE — admin capability-request loop (discussed 2026-09-08, FILED AWAY)
Goal: when a PM (any tenant) asks the assistant to do something with NO matching tool, the
assistant never fakes it — it files a capability request and the ADMIN (developer, not the PM)
decides what happens. Full design discussed; deliberately not built yet (needs Telegram bot token
+ Hermes gateway decision).
- Actors: tenant PMs → Vapi assistant (per company); assistant hits missing capability →
  request_capability tool → row in a `capability_requests` table (company_id source, summary,
  context, status OPEN → WAIT | PLANNING → PLANNED | DONE | DROPPED, dedupe on identical OPEN/WAIT
  requests) → Telegram push to the ADMIN (deployment-level setting: admin chat id + bot token,
  server-side only; never visible to tenant PMs; note in MULTITENANT.md).
- Buttons/replies: "Plan it" = I do feasibility + planning only (approach, effort, affected
  pieces, risks) and reply in-thread — an explicit "go" is still required before any build
  (plan-first rule holds; Plan it NEVER auto-builds). "Wait" = parked, no nag; re-surface via
  "show pending capability requests" anytime.
- Transport order: Telegram first (cheapest buttons), WhatsApp/Twilio later; plain email was the
  original fallback idea. Deferred whole, incl. the request_capability tool + prompt rule
  ("no matching tool → say so → request_capability, never approximate with another tool") — the
  prompt-honesty half still worth doing standalone if chat behaviour regresses.

## DECISION 2026-09-04 — worker PII: option A (data minimization)
NO worker_profiles table and NO collection of SIN / DOB / address for now. **When the T4/ROE filing
feature is built, it WILL need per-worker SIN + full address + DOB — collect them at that time** via a
secure channel (never through voice/LLM), not speculatively today. Design for then: 1:1
worker_profiles table (worker_id FK, company_id), SIN pgcrypto column-encrypted (key in n8n compose
env, AUTH_TOKEN_SECRET pattern — never in DB/repo), DOB/address plaintext + access-restricted,
encrypted dumps mandatory before any PII is stored. BC PIPA applies; SIN restricted to
income-reporting use.

---

# NEXT STEPS — updated 2026-08-27 (scheduling loop built)

## Scheduling & reminders — voice-configured briefing time (BUILT + LIVE)
- db/0015 `device_tokens` table applied live (register target + FCM push target).
- New `device-registration` workflow live: `POST /webhook/device/register` upserts the
  token and returns the current `briefing_time`. Verified: `{"status":"ok","briefing_time":"07:00"}`.
- voice-gateway: `set_briefing_time` now chains `set_briefing_time -> get_device_tokens
  -> Push Briefing Time Change -> Format Spoken Result`. Verified live: "Daily briefing
  set to 06:30." (the Push node gracefully skips when FCM is unconfigured).
- Flutter: local-notification scheduler (`notifications/notification_service.dart`) +
  FCM registration/re-schedule (`notifications/fcm_service.dart`); degrades to default
  07:00 when Firebase isn't set up yet.
- **FCM SEND IS LIVE + VERIFIED** — service account mounted at
  secrets/fcm-service-account.json (uid 1000, 600), env `FCM_SERVICE_ACCOUNT_FILE` +
  `NODE_FUNCTION_ALLOW_BUILTIN=crypto,fs,https`. Live test: set_briefing_time reached
  FCM's API (real OAuth + HTTP v1); the fake test token was rejected with
  INVALID_ARGUMENT — exactly the expected success signal. The app registers a real
  token on first launch.

## UPCOMING BUILDS (to do)
1. **Capabilities KB (Vapi)** — instruction manual / self-introduction of the whole
   assistant: the 21 tools, native SMS, email approvals. Upload as a Vapi Knowledge Base
   (see the `vapi-kb-tool` skill).
2. **Initial-setup onboarding wizard — BUILT + LIVE END-TO-END (2026-08-29)** —
   first-run flow capturing: company name, PM name + daily preferred address ("Dave"/"boss"),
   and workers (name + trade + hourly rate). db/0016 (pm_name, pm_preferred_name,
   setup_completed_at) applied; gateway branches `get_onboarding_status` + `complete_onboarding`
   (23 tools) live + verified; Vapi assistant synced (23 toolIds + First-Run Setup prompt,
   verified by read-back); test data cleaned up so the first real call runs onboarding.
   VAPI_PRIVATE_KEY recovered from old session history -> saved in ~/.hermes/.env;
   create_vapi_assistant.py reads it. Notes + decisions:
   `doc/ONBOARDING_WIZARD_NOTES.md`, SYSTEM_DESIGN.md §15.
   **Call-start hook (2026-08-29):** assistant `serverUrl` ->
   `/webhook/vapi/assistant-hook` (workflow vapi-assistant-hook.json) injects
   `setup_complete`/company/PM/worker variables into the system prompt at call
   start — LLM knows setup state with zero tool calls (SYSTEM_DESIGN.md §15.2a).
   The detailed onboarding steps are served by the hook as `onboarding_steps`
   (full when setup incomplete, EMPTY when complete) so the prompt only carries
   them when needed; a short fallback stays static.
   **Greeting + hang-up (2026-08-29):** hook returns a time-aware randomized
   `firstMessage` (morning variants w/ "good morning"; else "what's up?" /
   "what's happening?" / "what's good?"; personalized with pm_preferred_name;
   straight into onboarding when setup incomplete). Assistant: firstMessageMode
   assistant-speaks-first + endCallFunctionEnabled + endCallPhrases +
   endCallMessage "Take care!" so the call hangs up after goodbye. worker_count
   dropped from hook/prompt.
3. **Deadline Reminder workflow (n8n)** — the passive nudges from build-order item 5
   (Aug 26): lien/holdback reminders at 7/3/1 day, lead-time "order materials" nudges,
   same-day inspections. DB layer exists (`view_schedule` + lien/holdback clocks in 0014);
   NO workflow file exists yet. Email first, FCM push bolts on later.
4. **Real phone call test** — Vapi assistant (id 67e2850c-…, webhook voice/gateway) has
   never had a real inbound call. Make a real call and confirm the full voice loop.

---

## Status: VOICE GATEWAY IS WORKING END-TO-END ✅

Verified live (executions 1137-1139 on n8n2.ordrnow.com):
- lookup_or_create_customer -> created Dave Lee (dave@ireh.ca) in Postgres, replied "Customer ready."
- send_estimate_for_approval -> looked up "Test Approval" project, rendered branded HTML,
  sent via Gmail API (message id 1a037d86d907038d), landed in support.ordrnow@gmail.com inbox
  (subject "Please approve your estimate for Test Approval")

## What was fixed today (all committed to git main)

1. Credential A created by Dave (PostgreSQL "Supabase PostgreSQL") — DB calls work
2. Email: switched 6 emailSend (SMTP) nodes -> Gmail OAuth2 send nodes (commit cfc6156).
   Uses the existing "Gmail account" OAuth2 credential. NO SMTP/app-password needed.
   Credential scope must include gmail.send — it does (send worked).
3. N8N_BLOCK_ENV_ACCESS_IN_NODE=false added to n8n service env (commit 8497354) —
   n8n 2.35 blocks $env in Code nodes; gateway Code nodes read PUBLIC_BASE_URL.
   Also mirrored into deploy/docker-compose.yml and live /home/ubuntu/n8n-compose/compose.yaml.

## Known issues (next session)

1. ~~COSMETIC: send_estimate_for_approval spoken reply says "Project or customer not found."~~ FIXED (commit a06393f)
   Format Spoken Result read `$input`, which for the email branches is the Gmail
   node's response (no `.email`). Now reads the lookup node's output directly.
   Also fixed the identical latent bug in `send_change_order_for_approval`, and
   added a switch fallback + `default` case so unrecognized actions reply to Vapi
   with a clear message. ✅ DEPLOYED + VERIFIED live (executions 1146/1147, 2026-08-26):
   unknown action returns the fallback message; send_estimate_for_approval now
   replies "Approval link emailed to the client." (email sent to test fixture).

2. Test fixture in live DB (created for the email test):
   - customer "Ireh Test" (support.ordrnow@gmail.com)
   - project "Test Approval" (PENDING, site 123 Test St, Coquitlam BC)
   Delete when done testing, or keep for approval-link clicking. IDs in psql:
     SELECT id FROM customers WHERE email='support.ordrnow@gmail.com';
     SELECT id FROM projects WHERE title='Test Approval';

## Pending from earlier

- Hermes session DB swap STILL NOT DONE (recovered DB: 1,832/1,915 msgs, 15 sessions):
  1. /exit  2. kill 579103 (dashboard)  3. ~/.hermes/swap-recovered-db.sh  4. hermes
- Vapi assistant itself: created earlier (Ireh Construction PM Assistant, id 67e2850c-…)
  pointing at https://n8n2.ordrnow.com/webhook/voice/gateway. Real phone call test not
  done yet — next good step: make a real Vapi call and confirm the full voice loop.

## Deploy facts (all live on 8GB Arm VPS)

- Postgres 17 co-located, migrations 0001-0013 applied, company_profile = Ireh Construction
- n8n pinned 2.35.7, upgrade runbook in backend/DEPLOY.md §8
- 5 workflows imported + active; webhooks: voice/gateway, approve-estimate,
  webhook/estimate/approval, approve-change-order, webhook/change-order/approval
- Nightly backup cron 03:00 -> /home/ubuntu/backups/pm
- GMAIL_USER = support.ordrnow@gmail.com (env on VPS); sender is the OAuth account
