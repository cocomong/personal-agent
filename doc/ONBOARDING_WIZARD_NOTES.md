# Onboarding Wizard — Build Notes & Decisions (2026-08-29)

Status: BUILD + LIVE (n8n gateway + Postgres), Vapi assistant config staged.
Build #2 of the PM-assistant backlog (initial-setup onboarding wizard).

## What was built

1. **Migration `db/0016_onboarding.sql`** — applied to live Postgres:
   - `company_profile.pm_name`            (PM full name)
   - `company_profile.pm_preferred_name`  (daily address, e.g. "Dave" / "boss")
   - `company_profile.setup_completed_at` (NULL until first-run completes)
2. **voice-gateway.json** — two new tool branches (23 tools total now):
   - `get_onboarding_status` — returns setup state + company + worker count
   - `complete_onboarding` — upserts company profile + worker list in one call
3. **vapi_assistant.json** — 2 new tools + "First-Run Setup (Onboarding)" section
   in the system prompt (STAGED — sync to Vapi still needs your API key, see below).
4. Verified live end-to-end (see "Test evidence" below), then test data cleaned up
   so the first real call runs onboarding for real.

## DECISIONS made on my own (review these!)

D1. **Conversation design: system-prompt-driven, not a state machine.**
    The LLM (Vapi session) holds the multi-turn conversation (company → PM name →
    preferred address → workers one by one) and calls ONE completion tool at the
    end. Rejected alternative: a DB-backed step machine (`onboarding_state` table)
    — more moving parts, fragile across dropped calls, and the LLM already
    handles multi-turn context natively. Trade-off accepted: if the call drops
    mid-onboarding, nothing is written (harmless — just start again).

D2. **One completion tool, not one tool per step.**
    `complete_onboarding(company_name, pm_name, preferred_name, workers[])`
    writes everything in a single n8n call. Fewer round-trips, atomic-ish, and
    `get_onboarding_status` gives the assistant a cheap way to know when to
    offer onboarding.

D3. **Schema: 3 new nullable columns on `company_profile`, no new table.**
    `company_profile` is a single-row table (id=1) — onboarding just fills it.
    `setup_completed_at` (NULL = not done) avoids a boolean that needs defaults.
    Did NOT reuse `signature_name` (kept for email signatures) and did NOT touch
    the `workers` table (name/trade/hourly_rate already exist from db/0001).

D4. **Workers upserted by case-insensitive name; never duplicated.**
    Gateway SQL: match `lower(name)`, update trade/rate + set active on match,
    else INSERT with auto `worker_code` `W-###` continuing from the max existing
    code. No UNIQUE constraint added on workers.name — existing seed data could
    already contain near-duplicates and a failed migration is worse than a
    code-level dedupe.

D5. **Empty `workers` array is valid** (crew not known yet) — gateway handles
    `[]` and replies "registered with N workers on file".

D6. **Onboarding re-runs are allowed and idempotent.**
    `complete_onboarding` again = updates company fields, upserts workers (no
    dupes), keeps the ORIGINAL `setup_completed_at` (COALESCE). Changing company
    details later is therefore just "run onboarding again" — no reset needed.

D7. **New tool names**: `get_onboarding_status` + `complete_onboarding`
    (snake_case, matches the existing 21-tool convention).

D8. **Deployment mechanics** (following the established repo pattern):
    - Migration: ssh → `docker exec` psql, ON_ERROR_STOP.
    - Workflow: scp → sudo cp into `/files` mount → `n8n import:workflow` →
      `n8n update:workflow --active=true` → **restart the n8n container**
      (import deactivates the workflow and the running instance doesn't pick up
      CLI activation without a restart — verified empirically).
    - n8n expression gotcha (cost 2 deploy cycles): a node DOWNSTREAM of another
      node does NOT see the original tool args — `$json.toolArgs` is the
      previous node's OUTPUT. Read upstream args with
      `$('Normalize Tool Call').first().json.toolArgs` (the pattern Format
      Spoken Result already uses).

## Test evidence (all live on n8n2.ordrnow.com)

- `get_onboarding_status` → "Setup is not complete yet. Let us start - what is
  the company name?"
- `complete_onboarding` (2 workers) → "All set, boss. Ireh Construction is
  registered with 4 workers on file. Anything else?" (4 = 2 seed workers + 2
  test workers; auto codes W-003/W-004 continued from W-002 correctly)
- `complete_onboarding` with empty `workers: []` → "All set, Dave. ... 4 workers
  on file." (also proved re-run UPDATES preferred_name: boss → Dave)
- Re-run idempotency: second call updated, no duplicate worker rows.
- Cleanup done: test workers deleted, profile reset to NULL —
  final status check confirms "Setup is not complete yet" (pristine first-run).

## BLOCKED on you (one command each)

1. **Sync the Vapi assistant** (the voice side isn't live until this runs):
   ```bash
   cd ~/projects/personal-agent
   VAPI_PRIVATE_KEY=your_key_here python3 backend/create_vapi_assistant.py
   ```
   `backend/vapi_assistant.json` already has the 2 tools + onboarding prompt
   section; the script is idempotent (safe to re-run).
   I could not find VAPI_PRIVATE_KEY on this machine (~/.hermes/.env, SOUL.md,
   shell rc, repo — all checked), so I did not run it.

2. **Optional**: real phone call test of the whole loop (also on the backlog).

## Files changed

- `db/0016_onboarding.sql` (new migration, applied live)
- `backend/n8n/workflows/voice-gateway.json` (2 new branches)
- `backend/n8n/add_onboarding_to_gateway.py` (idempotent patcher, re-runnable)
- `backend/vapi_assistant.json` (2 tools + onboarding prompt)
- `backend/update_vapi_onboarding.py` (idempotent updater, re-runnable)
- `deploy/migrate.sh` (0016 added to the migration list)
- `doc/SYSTEM_DESIGN.md` (onboarding section), `doc/NEXT_STEPS.md`,
  `backend/VAPI_ASSISTANT.md`
