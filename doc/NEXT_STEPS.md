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
