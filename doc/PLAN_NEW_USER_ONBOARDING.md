# New-user onboarding — implementation plan

**Status:** IMPLEMENTED AND LIVE 2026-10-30 (see section 8). Verified at the HTTP/DB
level; the on-device pass is still outstanding (no ADB device attached).

**Goal:** a person who signs in with a new Google account must be taken through the
setup process and get their own company — never silently become Ireh Construction.

**Scope:** the onboarding slice of Step 3 in `doc/MULTITENANT.md`. Full per-company
tool scoping (Step 3 proper) is a separate, larger change and is staged as P1 below.

---

## 1. What happens today (verified in code, not assumed)

A stranger signing in with Google right now does **not** see setup. They land inside
Ireh Construction with full access. The chain, with the evidence:

| # | Where | What it does | Verdict |
|---|-------|--------------|---------|
| 1 | `backend/n8n/workflows/auth-google.json` → `Upsert User` | `INSERT INTO users (google_sub, email, name) … ON CONFLICT (google_sub) DO UPDATE` — any valid Google account is accepted; `company_id` stays NULL | correct by design (`users.company_id` is "NULL until onboarding") |
| 2 | same → `Issue Session Token` | 30-day HMAC token `v1.<payload>.<sig>` carrying only `{uid, exp}` | fine |
| 3 | same → response | `setup_complete` = LEFT JOIN on `company_profile` → NULL → `false` | correct |
| 4 | `mobile-flutter/lib/main.dart:127-129` | `return LoginScreen(...)` else `AgentScreen(...)` — `setupComplete` is **never read** | **bug: gate missing** |
| 5 | `mobile-flutter/lib/auth/session_store.dart:32` | parses `setup_complete` into `AuthSession.setupComplete` | dead value |
| 6 | hook `Resolve Company Scope` → `Exec: read_setup_status` | `WHERE cp.id = COALESCE((SELECT company_id FROM users WHERE id = $1::uuid), 1)` | **bug: a logged-in user with no company is resolved to Ireh** |
| 7 | hook `Build Hook Variables` | `setupComplete = !!row.setup_complete` — reads Ireh's flag, which is TRUE | onboarding branch never fires |
| 8 | gateway `Exec: complete_onboarding_profile` | `UPDATE company_profile … WHERE id = 1` and `Exec: get_onboarding_status` `WHERE id = 1` | **bug: a stranger's setup would rewrite Ireh's row** |
| 9 | gateway, ~30 SQL nodes (`lookup_or_create_customer`, `create_project`, `create_invoice`, …) | `WHERE … company_id = 1` hardcoded | **bug: writes land in Ireh** |
| 10 | `company_profile` column defaults (live DB) | `company_name` DEFAULT `'Ireh Construction'`, `street_address` DEFAULT `'1951 Kaptey Ave'`, `phone` DEFAULT `'778-994-6602'`, `email_from` DEFAULT `'support.ordrnow@gmail.com'`, `signature_name` DEFAULT `'Dave'` — all NOT NULL | **trap: a bare INSERT clones Ireh's identity into the new tenant** |
| 11 | live `users` table | both accounts (`dtam2003@gmail.com`, `5650tam@gmail.com`) have `company_id = NULL` | **blocks the fix: "no company ⇒ onboarding" would send the owner back through setup** |
| 12 | `backend/n8n/workflows/chat-gateway.json` → `Exec: chat_context` | same `WHERE cp.id = COALESCE((SELECT company_id FROM users WHERE id = $1::uuid), 1)` | **bug: text chat has the same mis-resolution (must be fixed with the hook)** |

So the actual defect is not "onboarding is missing" — the onboarding conversation,
the `complete_onboarding` tool and the `onboarding_steps` prompt section all exist and
work. The defect is that **a new user is resolved to the wrong company**, so the
prompt's `setup_complete: false` branch (which would start setup) never runs, and the
setup writes that would follow are pinned to `id = 1`.

One more structural fact that shapes everything below: **Vapi calls the gateway, not
the app**, so tool calls carry no `X-User-Token`. The gateway currently has no idea
who is calling. The caller's identity has to travel with the call: the hook already
returns `assistantOverrides.variableValues`, and that map is **proven to round-trip**
on Vapi server events (we verified it with `call_ref` on `end-of-call-report`).

---

## 2. Design

### 2.1 Scope contract (three-way, replaces COALESCE)

Resolved once per request from the session token (`uid`), then from `users.company_id`:

| Case | Meaning | Company scope |
|------|---------|---------------|
| valid token, `users.company_id` set | normal tenant | that company |
| valid token, `users.company_id` NULL | **onboarding in progress** | `NULL` — no company row exists yet |
| no token / invalid token | legacy client (web chat, old builds) | company 1, unchanged for now (removed in P2) |

The hook and the gateway both implement this identically, from one shared snippet.
A logged-in user is never silently upgraded to company 1.

### 2.2 Where the company row is created

At the end of onboarding, inside `complete_onboarding` — not at sign-in. This matches
`doc/MULTITENANT.md` §2.3 ("complete_onboarding CREATES company_profile + links user")
and avoids creating empty companies for people who sign in and leave.

Mechanics, in three Postgres nodes (a single CTE cannot do it: data-modifying CTEs
cannot see each other's writes in the same statement):

1. `ensure_company` — if `users.company_id IS NULL`, INSERT a `company_profile` row
   with **every tenant-identifying column set explicitly**, `created_by_user = uid`;
   return `COALESCE(users.company_id, inserted id)`.
2. `link_user` — `UPDATE users SET company_id = $company WHERE id = $uid AND company_id IS NULL`.
3. `complete_onboarding_profile` (existing node, unchanged shape) — now
   `WHERE id = $company` instead of `WHERE id = 1`.

Idempotency and races come from
`CREATE UNIQUE INDEX uq_company_created_by_user ON company_profile (created_by_user) WHERE created_by_user IS NOT NULL`
plus `ON CONFLICT (created_by_user) DO NOTHING`; a second call returns the same id.

`complete_onboarding_workers` gets the same `$company` treatment, so workers added
during setup belong to the new company.

### 2.3 What a not-yet-set-up user may do

While the resolved scope is `NULL`, the gateway allows exactly two actions —
`get_onboarding_status` and `complete_onboarding` — and answers everything else with a
spoken line ("I need to finish setting you up first"). This is the guard that makes
bug #9 harmless for the onboarding user: no tool can write into company 1.

> **Honest limitation, needs your decision.** After a new company exists (id=2), the
> tools are *still* hardcoded to company 1, so P0 must also refuse data tools for any
> company other than 1 ("your workspace is being prepared"). That makes the new tenant
> **onboardable but not yet usable**. Making them usable is P1 (parameterise ~30 SQL
> nodes by `$company`), which is Step 3 proper. Options for the morning:
> **(a)** ship P0 alone (safe, second tenant can't work yet), or **(b)** do P0+P1
> together before any second person is let in.

### 2.4 The app gate (two UI options — server work is identical)

`main.dart` chooses the screen from three states instead of two:

```
no session        -> LoginScreen
session, !setup   -> SetupScreen   (NEW)
session, setup    -> AgentScreen
```

**Option A (recommended, reuses what exists):** `SetupScreen` explains that the
workspace needs setting up, with one button — *Start setup* — that opens the existing
voice session. The hook already returns `firstMessage: "Hey, let's get you set up -
what's the company name?"` and injects `onboarding_steps`; nothing about the
conversation has to be rebuilt. Escape hatch: *Sign out*.

**Option B:** the same screen as a Flutter form (company name, PM name, address,
GST/PST, payment instructions, workers) posting to a new
`POST /webhook/onboarding/complete`. Deterministic, no microphone, but it duplicates
the onboarding logic and needs its own validation; the assistant's onboarding branch
then becomes a fallback.

Both need the same server pieces (2.1–2.3), so this choice can be made after P0 lands
without rework.

### 2.5 Keeping the app's flag honest

The app caches `setup_complete` from sign-in. A completed setup must flip it. Add
`POST /webhook/auth/me` (token → fresh user row + `setup_complete`), called on app
resume and when a call ends while `setup_complete` is false. Cheap, and it also fixes
stale flags generally.

---

## 3. Task list

Ordered so each step is independently testable. TDD: the check is written first and
must fail before the code exists.

### Task 0 — Owner backfill (must land before anything else works)
Files: create `db/0041_tenant_owner_backfill.sql`
```sql
-- Bind the existing (single-tenant) accounts to company 1 so the new
-- "no company => onboarding" rule does not send the owner through setup.
DO $$
DECLARE n int;
BEGIN
  UPDATE users SET company_id = 1
   WHERE company_id IS NULL
     AND lower(email) IN ('dtam2003@gmail.com', '5650tam@gmail.com');
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 2 THEN
    RAISE EXCEPTION 'expected 2 owner rows, backfilled %', n;  -- fail loudly, no partial state
  END IF;
END $$;
```
Verify: `SELECT email, company_id FROM users ORDER BY created_at;` → both `1`.
The guard makes it re-runnable (0 rows the second time) — relax the check to
`n IN (0,2)` if the migration is run twice, or run it once and record it.

### Task 1 — Unique index + drop the tenant defaults
Files: create `db/0042_company_identity_defaults.sql`
```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_company_created_by_user
  ON company_profile (created_by_user) WHERE created_by_user IS NOT NULL;

-- These defaults are one tenant's real data. A new company must never inherit them.
ALTER TABLE company_profile
  ALTER COLUMN company_name     DROP DEFAULT,
  ALTER COLUMN legal_name       DROP DEFAULT,
  ALTER COLUMN street_address   DROP DEFAULT,
  ALTER COLUMN city             DROP DEFAULT,
  ALTER COLUMN province         DROP DEFAULT,
  ALTER COLUMN postal_code      DROP DEFAULT,
  ALTER COLUMN phone            DROP DEFAULT,
  ALTER COLUMN email_from       DROP DEFAULT,
  ALTER COLUMN email_from_name  DROP DEFAULT,
  ALTER COLUMN signature_name   DROP DEFAULT;
```
Rows already stored keep their values; only future inserts lose the defaults, so an
INSERT that forgets a column fails loudly instead of cloning Ireh. Rates/prefixes/
brand colours keep their generic defaults (5% GST, 7% PST, INV- …) — noted as
per-tenant settings for later.

### Task 2 — Hook: three-way scope, no fallback for logged-in users
Files: modify `backend/n8n/workflows/vapi-assistant-hook.json` via a new idempotent
`backend/n8n/patch_onboarding_scope.py` (same pattern as `patch_voice_context.py`).

- `Resolve Company Scope` → return `{uid, companyId}` where `companyId` is looked up
  from `users` (empty token ⇒ `companyId = 1`, legacy).
- `Exec: read_setup_status` becomes two branches or one query that survives a NULL
  company:
```sql
SELECT (cp.setup_completed_at IS NOT NULL) AS setup_complete,
       COALESCE(cp.company_name, '')       AS company_name,
       COALESCE(cp.pm_preferred_name, '')  AS pm_preferred_name,
       lc.ctx AS last_call_ctx, lc.ended_at AS last_call_ended_at,
       lc.ended_reason AS last_call_ended_reason
  FROM users u
  LEFT JOIN company_profile cp ON cp.id = u.company_id
  LEFT JOIN LATERAL ( /* unchanged: last reported call, 7d, >30s old */ ) lc ON true
 WHERE u.id = $1::uuid
 UNION ALL
 SELECT true, cp.company_name, COALESCE(cp.pm_preferred_name,''), lc.ctx, lc.ended_at, lc.ended_reason
   FROM company_profile cp LEFT JOIN LATERAL ( /* same */ ) lc ON true
  WHERE cp.id = 1 AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = $1::uuid)
 LIMIT 1;
```
- `Build Hook Variables` — unchanged logic now behaves correctly:
  `!setupComplete` ⇒ firstMessage "Hey, let's get you set up - what's the company name?".
- Add `user_id` to the returned `variableValues` (and `metadata: {userId}`) so the
  gateway can identify the caller from `message.call.assistantOverrides.variableValues`
  (proven to round-trip) — `metadata` as the secondary path.
- `Exec: start_call_row` — **skip the insert when the scope is NULL** (`voice_calls.company_id`
  and `call_ref` are both NOT NULL, verified live), so the report lands as `unmatched:`
  instead of failing the hook.
- `chat-gateway.json` → `Exec: chat_context`: same three-way rule (NULL company ⇒
  `setup_complete: false`, blank `company_name`), and the same `user_id` passed into the
  prompt variables, so text chat for a not-set-up user does not resolve to Ireh either.
  The text path has no tool scope today, so it must at minimum refuse data work while
  the scope is NULL.

### Task 3 — Gateway: scope resolution + guard
Files: modify `backend/n8n/workflows/voice-gateway.json` (same patch script).

- New `Resolve Call Scope` node after `Normalize Tool Call`:
  `userId` from `body.message.call.assistantOverrides.variableValues.user_id`
  (fall back to `body.message.call.metadata.userId`), then `company_id` from `users`
  (NULL allowed; no match ⇒ 1 for legacy clients).
- New `Onboarding Guard` node: if `companyId IS NULL` and `action ∉
  {get_onboarding_status, complete_onboarding}` → respond with the spoken refusal and
  write nothing.
- If `companyId <> 1` (P0): same refusal with "your workspace is being prepared"
  (removed by P1).

### Task 4 — Gateway: onboarding tools write to the caller's company
- `Exec: get_onboarding_status` → `WHERE id = $1` (company id).
- New `Exec: ensure_company` + `Exec: link_user` (SQL in §2.2).
- `Exec: complete_onboarding_profile` → `WHERE id = $12` (company id), and only after
  `ensure_company`; response unchanged otherwise.
- `Exec: complete_onboarding_workers` → workers get `company_id = $company`; the
  `W-###` code generator and the `(company_id, worker_code)` conflict target already
  exist from Step 2.

### Task 5 — `/webhook/auth/me`
Files: create `backend/n8n/workflows/auth-me.json`, deploy as `auth-me-001`.
Token verify (same code as the hook) → `SELECT id, name, email, company_id,
setup_completed_at IS NOT NULL AS setup_complete FROM users u LEFT JOIN company_profile
cp ON cp.id = u.company_id WHERE u.id = $1`. 401 on bad token.

### Task 6 — App gate (Option A)
Files: create `mobile-flutter/lib/screens/setup_screen.dart`; modify
`mobile-flutter/lib/main.dart` (three-state routing at the `_session == null` branch),
`mobile-flutter/lib/auth/auth_service.dart` (add `me()`), `session_store.dart`
(refresh from `me()` on resume).

### Task 7 — Docs
`doc/MULTITENANT.md`: tick the onboarding half of Step 3, record the three-way scope
contract and the company-defaults trap. `doc/NEXT_STEPS.md`: entry with what was
verified and what P1 still owes.

---

## 4. Test plan

### L1 — offline (no network, no DB)
New `backend/n8n/test_onboarding_scope.py`, same style as `test_voice_context_hook.py`
(pulls the real jsCode/SQL out of the workflow JSON and runs it):
1. Scope resolution: token+company → that id; token+NULL company → NULL; no token → 1;
   tampered signature → 1 (legacy) and `uid: null`.
2. Hook variables: NULL company ⇒ `setup_complete: 'false'`, `company_name: ''`,
   firstMessage = setup greeting; company 1 ⇒ unchanged greeting (regression).
3. Guard allowlist: exactly `get_onboarding_status` + `complete_onboarding` pass while
   scope is NULL; all 30 other actions are refused.
4. Static SQL assertions: `read_setup_status`/`get_onboarding_status`/
   `complete_onboarding_profile` no longer contain `id = 1` or `COALESCE(…, 1)`;
   `ensure_company` names every tenant-identifying column explicitly (so it cannot
   lean on the dropped defaults).
5. `start_call_row` is not emitted when the scope is NULL.

### L2 — DB, rolled back (against live Postgres, `BEGIN … ROLLBACK`)
New `qa/onboarding_scope_db_test.py`:
1. Seed user A (`company NULL`, email `a@test.local`), keep owner B (company 1).
2. Snapshot `company_profile` row 1 (all columns) → run the onboarding SQL for A → the
   snapshot must match exactly (Ireh untouched).
3. Assert A's company: new id (2), `created_by_user = A`, `users.company_id = 2`,
   `setup_completed_at NOT NULL`, `company_name = 'Test Co'`, `email_from = 'a@test.local'`,
   `phone = ''`, and **no** column equals Ireh's value (`'1951 Kaptey Ave'`,
   `'778-994-6602'`, `'support.ordrnow@gmail.com'`, `'Dave'`).
4. Run it twice → still one company, same id (idempotent + unique index).
5. Hook SQL for A: `setup_complete` false before, true after; `company_name` matches.
6. Hook SQL for B: company 1, greeting unchanged.
7. Hook SQL with an unknown uid: company 1 (legacy preserved).
8. Workers: `complete_onboarding_workers` for A lands in A's company only.
9. `ROLLBACK` — zero residue (`SELECT count(*) FROM users WHERE email='a@test.local'` = 0).

### L3 — live HTTP (deployed workflows)
New `qa/onboarding_probe.py`:
1. `POST /webhook/auth/google` with a garbage token → 401 JSON (regression).
2. Insert a throwaway user (company NULL) → hook with a token minted for it (probe mints
   with the same HMAC scheme; secret stays on the VPS) → assert
   `variableValues.setup_complete == 'false'`, `company_name == ''`, setup greeting,
   `user_id` present.
3. Gateway tool call with that `user_id`, `action=create_invoice` → refusal, and
   `SELECT count(*) FROM invoices` unchanged.
4. Gateway `complete_onboarding` → company created; response reports setup complete.
5. Hook again for the same user → `setup_complete == 'true'`, `company_name == 'Test Co'`.
6. `POST /webhook/auth/me` → `setup_complete: true`, `company_id` set.
7. P0 guard: gateway `create_project` for the new company → refusal (no Ireh write).
8. Cleanup: delete the company row + the user; assert 0 residue and that
   `company_profile` row 1 still matches its pre-probe snapshot.

### L4 — device (needs you, ~10 minutes)
1. Sign in on the phone with a **second** Google account → the Setup screen appears
   (not the assistant).
2. *Start setup* → the assistant's first line is the setup greeting; give "Test Co",
   your name, address; confirm it does not mention Ireh or Dave.
3. Call ends / app resumes → the app leaves the setup screen and greets you as Test Co.
4. Sign out, sign in as the owner → straight into the assistant as Ireh, no setup
   prompt, greeting unchanged.
5. Regression: owner's invoice preview email still goes to the same inbox, and the
   invoice HTML still carries the logo (the defaults I want to drop are what the
   invoice renderer reads at runtime, not compile-time).

### Rollback
- `db/0041` — reversible in one statement (`UPDATE users SET company_id = NULL WHERE …`).
- `db/0042` — restore defaults from the captured snapshot in this plan's §1 row 10.
- Workflows — `patch_onboarding_scope.py` keeps the pre-patch JSON in
  `backend/n8n/.bak/` and n8n keeps version history; redeploy by id.
- App — the gate is additive; an older APK still works against the new backend
  (legacy no-token path preserved).

### Regression checklist (must stay green)
- `backend/n8n/test_voice_context_hook.py` (39 checks)
- `qa/voice_context_probe.py` (18 live checks; it writes `voice_calls` rows — confirm it
  tolerates the "skip pending row when scope is NULL" change)
- `qa/chat_text_battery.py` (known: 61–62/63, two text-chat failures unrelated to this work)
- Owner's onboarding must **not** re-run (that is L4.4).

---

## 5. Risks

| Risk | Mitigation |
|------|-----------|
| Owner backfill picks up the wrong rows | explicit email list + `RAISE EXCEPTION` unless exactly 2 rows |
| `users.company_id` NULL users exist besides the two owners | the SQL targets emails only; the migration reports what it touched |
| A stranger derives a company because the guard misses an action | guard is an allowlist (2 actions), so a new tool is refused until added |
| Vapi does not echo `user_id` on tool-call events | `variableValues` round-trip is already proven on reports; `metadata.userId` is the backup; L3.3 proves it before the app gate ships |
| Dropping defaults breaks another INSERT | only `complete_onboarding` inserts into `company_profile` (verified: single-row table until now) |
| Two devices complete setup simultaneously | unique index on `created_by_user` + `ON CONFLICT DO NOTHING` |
| A new tenant's invoices go out from someone else's inbox | `email_from` = the tenant's verified Google email at creation; a tenant with no email cannot send until it is set (flag, not silent) |

## 6. Decisions I need from you

1. **Setup surface** — Option A (voice conversation, reuses everything) or Option B
   (app form)? Server work is identical either way.
2. **Scope of this change** — P0 only (new tenant onboardable but data tools refused),
   or P0+P1 (parameterise the ~30 gateway SQL nodes so a second company is actually
   usable)? P1 roughly doubles the work and is Step 3 proper.
3. **Signup policy** — any Google account may create a company (self-serve, Play Store
   style), or should new sign-ins be held for approval? Today any account is accepted.
4. **Tenant sender identity** — use the tenant's Google email as `email_from`, or force
   them to enter a business address before invoices can be sent?
5. **Owner accounts** — confirm `dtam2003@gmail.com` and `5650tam@gmail.com` are both
   yours and should be bound to company 1.

## 7. What I did not do
No code, workflow, migration or app change was made. No deploy. This file is the only
artifact.


---

## 8. As built (2026-10-30) — decisions, deviations, evidence

Decisions taken (user, 2026-10-30): Option A (voice setup, form kept as a later option);
P0 **and** P1; self-serve signup; business address required before setup can complete;
dtam2003@gmail.com is the only owner and 5650tam@gmail.com was removed.

Shipped:
- `db/0041_owner_backfill.sql` — owner bound to company 1, second account deleted, with
  row-count assertions (re-runnable).
- `db/0042_company_identity_defaults.sql` — unique index on `created_by_user`, the
  tenant-identifying column defaults DROPPED, and a CHECK that setup cannot complete
  without street/city/province/postal/sender.
- `db/0043_tenant_views_payroll.sql` — company_id appended to the four views (restated
  from their LIVE definitions; 0004 was stale) + `fn_run_payroll_for_company`.
- Hook (`patch_onboarding_scope.py`) — three-way scope, `user_id` transported in
  variableValues, pending call row skipped when there is no company, address made
  mandatory in the onboarding script.
- Gateway (`patch_tenant_scope_gateway.py`) — Extract Tool Call -> Resolve Call Scope ->
  Normalize Tool Call -> Onboarding Guard; ensure_company/link_user before workers/profile;
  onboarding tools scoped by company; refusal responder.
- Gateway (`patch_tenant_scope_tools.py`) — 43 tenant queries scoped by company.
- `auth-me-001` workflow + `AuthService.refreshSession()` + `SetupScreen` + three-state gate.

Deviations from the plan, and why:
1. **Identity transport is `assistantOverrides.variableValues.user_id`, not `metadata`.**
   variableValues is already proven to round-trip (call_ref uses it); metadata stays as a
   read-side fallback in `Extract Tool Call`.
2. **Two extra nodes (`ensure_company`, `link_user`) instead of one CTE.** Data-modifying
   CTEs cannot see each other's writes in the same statement, so creation and linking are
   separate steps; a unique index keeps it idempotent.
3. **`n8n` binds parameters from `$('Normalize Tool Call')`, not `$json`.** After the
   Switch, `$json` did not carry the parsed tool args; explicit node references are stable.
4. **Views had to be restated from the live definition**, not from db/0004 — later
   migrations had added five columns, and `CREATE OR REPLACE VIEW` cannot drop columns.
5. **The old `fn_run_payroll` is left in place**; the tool now calls the scoped
   `fn_run_payroll_for_company`. Nothing else called it.

Evidence (all run against the live stack):
- `backend/n8n/test_onboarding_scope.py` — offline: hook variables, scope SQL, wiring,
  guard, and "no node pins company_id = 1 / every tenant query is scoped".
- `qa/onboarding_scope_db_test.py` — rolled back: scope NULL, create, link, idempotency,
  address gate, worker scoping, minimal answers, company 1 byte-identical.
- `qa/onboarding_probe.py` — live: legacy hook unchanged; new user gets setup; data tools
  refused before setup; complete_onboarding creates + links; hook then greets their company;
  cross-tenant isolation both ways; cleanup leaves zero residue.
- Owner regression: list_projects/list_invoices/get_dashboard_summary/get_schedule/
  get_payroll_summary/find_customer/list_invoice_templates/get_onboarding_status/
  list_estimate_status all return their previous data.

Known gaps:
- No device pass yet: the setup screen, auto-start and the resume refresh are unverified on
  the phone (no ADB device attached at build time).
- `qa/chat_text_battery.py` still reports the pre-existing multi-turn failure (the model
  says "two hundred seventy thousand dollars", the harness expects digits).
- A tenant's invoices are sent from their own Google email (`email_from`); a real sending
  identity per tenant (verified sender) is still a Step 4 concern.
