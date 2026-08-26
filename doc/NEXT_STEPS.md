# NEXT STEPS — updated 2026-08-25 (end of day)

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
