# Voice context carryover — design (for review, nothing built)

**Status:** proposal only. No migrations applied, no workflows imported, no app changes.
**Date:** 2026-10-27 (rev 3 — scope settled)
**Author:** Hermes

**Decisions taken:** retention **10 days**; greeting **unchanged** (today's deterministic
open); text chat **excluded** (it already carries its own history via `chatId`); `serverMessages`
**left as-is**; legacy Twilio/Sheets workflow **left alone**. No open questions remain.

---

## 0. As built (2026-10-28) — what shipped and where it deviates

Implemented as specified, plus the answers T1 was waiting for:

- **T1 answered on a real call object**: `message.call.assistantOverrides.variableValues`
  **does round-trip**, so report matching uses the injected `call_ref` (deterministic), with
  company+time as a fallback only (`ended_reason` gets an `unmatched:` prefix when no pending
  row exists). Transcripts on this account: median 343 chars, p90 1,632, max 4,143 — small
  enough that a transcript tail beats adding `analysisPlan` (which is still unset, so `summary`
  is empty; the injector prefers `summary` if Vapi ever starts producing one).
- **Context shape**: `right(coalesce(summary, transcript), 900)`, 7-day window, `status='reported'`,
  rows newer than 30 s excluded so an in-flight call is never injected as history.
- **Retention**: workflow `voice-context-retention-001`, daily 03:30 — 10-day delete +
  pending→abandoned after 6 h. Its SQL was executed against live Postgres inside a
  ROLLBACK-wrapped transaction with three seeded rows (1 old deleted, 1 stale abandoned,
  1 fresh kept).
- **Side benefit**: non-report Vapi events now answer `{ok:true, ignored:true}` and skip the
  company query and variables builder entirely, instead of running them ~37 times per call.
- **Text chat** keeps its own thread (`previousChatId`) and now sends `recent_context: ''`
  so the prompt never renders a literal placeholder.
- **Tests**: `backend/n8n/test_voice_context_hook.py` (39 offline checks) and
  `qa/voice_context_probe.py` (18 live checks, self-cleaning — leaves zero rows).
- **Still unproven**: a real phone call start-to-finish; the live probe used synthetic
  end-of-call reports. See the follow-up note below.

---

## 1. What already works, so we build only the missing part

| Layer | State | Where |
|---|---|---|
| App shows the last conversation on launch | **Works** | `session_persistence.dart` restores chat id + transcript; `AgentScreen._restoreTranscript()` |
| Assistant remembers the **text** thread | **Works** | every `/webhook/chat` call carries the persisted `chatId`; Vapi keeps the thread |
| Assistant remembers the **voice** conversation | **Missing** | a new call starts with company variables only; nothing stores what was said |

Nothing in the Flutter app needs to change. This is server-side capture + injection, voice only.

Text is deliberately out of scope: the text thread is continuous through `chatId`, so a typed
conversation already remembers itself. The gap is voice, which starts from zero on every call.

---

## 2. Findings from investigating the live stack (verified 2026-10-27)

1. **The assistant's `serverUrl` is `https://n8n2.ordrnow.com/webhook/vapi/assistant-hook`** and `serverMessages` is **unset**. Vapi's documented default set includes `end-of-call-report`, `status-update`, `speech-update`, `conversation-update`, `tool-calls` and more.
   → **Vapi is already POSTing every call's `end-of-call-report` to our hook — and the hook discards it.**
2. **Volume:** the hook workflow ran **1,398 times in the last 7 days** (`execution_entity`, live n8n SQLite) against **37 real calls** (Vapi `/call`, same window). A sample of the last 60 hook runs, decoded from `execution_data`:

   | event type in payload | runs (of 60) |
   |---|---|
   | `speech-update` | 27 |
   | `conversation-update` | 26 |
   | `status-update` | 3 |
   | `end-of-call-report` | 2 |
   | `assistant.started` | 1 |

   That is ≈37 events per call arriving at a hook that only ever answers the app's single call-start request.

   **Decision: leave `serverMessages` as-is** — zero Vapi config change, capture rides the default set. The wasted runs continue; they are cheap and harmless, and the report branch simply ignores anything that is not a report.
3. **No conversation storage exists:** `db/` ends at `0038`; there is no calls / messages table.
4. **`analysisPlan` is unset** → reports carry `artifact.transcript` and `artifact.messages`, but no `analysis.summary`.
5. **Report shape** (Vapi docs): `{ message: { type, endedReason, call, artifact: { transcript, messages[] } } }`.
6. **Legacy workflow** "end of call report" (`K5h8akMdXeLXkI2K`, `/webhook/callreport`, Twilio SMS + Google Sheets, live since 2026-07-13) is unrelated to this path. **Decision: leave it.**

---

## 3. Architecture

```
 call start (app)                          call end (Vapi)
        |                                        |
        v                                        v
 POST /webhook/vapi/assistant-hook        POST /webhook/vapi/assistant-hook
   direct from the app,                    Vapi server message:
   X-User-Token                            type = end-of-call-report
        |                                        |
        +--> resolve company                     +--> branch on message.type
        +--> INSERT voice_calls                  +--> Extract Call Report (Code)
             (pending, call_ref)                 +--> upsert voice_calls
        +--> SELECT last reported summary             transcript, summary,
        +--> respond assistantOverrides               status='reported'
             { variableValues: {…,
               recent_context} }
```

One webhook path, two branches. The app's direct call is unaffected by `serverMessages`
(that setting only governs Vapi→server sends).

---

## 4. Data model — `db/0039_voice_context.sql` + `db/0040_voice_context_verify.sql`

```sql
CREATE TABLE IF NOT EXISTS voice_calls (
  id               bigserial PRIMARY KEY,
  company_id       integer NOT NULL REFERENCES company_profile(id) ON DELETE CASCADE,
  call_ref         uuid NOT NULL,
  vapi_call_id     text UNIQUE,
  status           text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','reported','abandoned')),
  started_at       timestamptz NOT NULL DEFAULT now(),
  ended_at         timestamptz,
  ended_reason     text,
  duration_seconds numeric(10,2),
  summary          text,
  transcript       text,
  messages         jsonb,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS voice_calls_ref_key    ON voice_calls (call_ref);
CREATE INDEX        IF NOT EXISTS voice_calls_recent_idx ON voice_calls (company_id, ended_at DESC NULLS LAST);
```

- `call_ref` is generated by the hook at call start and is the join key between "a call is about to happen" and "here is its report".
- Register both files in `deploy/migrate.sh` in DEPLOY order after the 0037/0038 pair; regenerate `doc/SCHEMA.md` afterwards.
- **Verify file (`0040`) asserts, then rolls back:** pending + reported insert; duplicate `call_ref` rejected; bogus `status` rejected; FK rejects `company_id = 9999`; the recent-index query returns in the expected order.

---

## 5. Capture path

**5.1 Branch the hook.** In `vapi-assistant-hook.json`, immediately after the webhook node, switch on `{{ $json.body.message.type }}`:
- `end-of-call-report` → report branch
- everything else (including the app's direct call, which has no `message.type`) → today's variables path, byte-identical

**5.2 Pending row.** In the variables branch, after company resolution: `INSERT INTO voice_calls (company_id, call_ref) VALUES ($1, gen_random_uuid()) RETURNING call_ref`. Written on every call start, including calls that never connect (those become `abandoned`).

**5.3 Report branch** (new nodes; ids from a plain counter, per the n8n id pitfall):

1. `Extract Call Report` (Code): `vapi_call_id = message.call.id`, `ended_reason = message.endedReason`, timestamps from `message.call`, `transcript = message.artifact.transcript`, `messages = message.artifact.messages`, `summary = message.analysis?.summary ?? null`, derived `duration_seconds`.
2. `Exec: match_or_insert_call` (Postgres, `operation: executeQuery`): match by `call_ref` from `message.call.assistantOverrides.variableValues.call_ref` **if that field exists** (T1 decides), else the most recent `pending` row for the company within 6 h; then `UPDATE … SET status='reported', vapi_call_id, ended_at, ended_reason, transcript, summary, messages …`. If nothing matches, `INSERT` a `reported` row with a generated `call_ref` and `ended_reason` prefixed `unmatched:` — visible rather than silent.
3. `Respond Report (ok)` (Respond to Webhook, 200 `{"ok":true}`) — Vapi expects no body for this type.

**5.4 Dedupe & orphans.** `vapi_call_id UNIQUE` + `ON CONFLICT (vapi_call_id) DO UPDATE` makes Vapi's retries idempotent. A nightly step flips `pending` rows older than 6 h to `abandoned`, so a call that never connected is never injected as "last conversation".

---

## 6. Injection path

**6.1 Context query** (guaranteed row — a 0-row result would end the n8n chain silently):

```sql
WITH last AS (
  SELECT summary, transcript, ended_at, ended_reason
    FROM voice_calls
   WHERE company_id = $1
     AND status = 'reported'
     AND ended_at > now() - interval '7 days'
     AND ended_at < now() - interval '30 seconds'
   ORDER BY ended_at DESC
   LIMIT 1
)
SELECT left(coalesce(summary, transcript), 900) AS last_call,
       ended_at, ended_reason
FROM last
UNION ALL
SELECT NULL, NULL, NULL
WHERE NOT EXISTS (SELECT 1 FROM last);
```

**6.2 `Build Hook Variables`** adds `recent_context` (≤900 chars: date, ended reason, summary) and omits the key entirely when the row is absent.

**6.3 System prompt section** (added to `backend/vapi_assistant.json`):

```
## Recent context
variableValues.recent_context may hold a summary of the last voice call.
Use it to avoid re-asking what the PM already told you, and to offer continuity when they
return to the same topic. Never read it aloud or quote it back. Never state a fact from it
as current without checking a tool first — amounts, balances and statuses change. If the
last call ended mid-task and they resume it, pick up from there instead of starting over.
If it is empty, behave exactly as today.
```

**6.4 Greeting: unchanged.** Today's deterministic, time-aware greeting stays exactly as it is. Continuity is available to the model through `recent_context` when the topic comes up; a call never opens by asserting what was discussed last time.

**6.5 Failure isolation.** Every context lookup is failure-tolerant: any error, timeout or missing row falls through to today's exact payload. The hook is on the call's critical path (the app waits on it), so its budget stays small: one SQL round trip, no LLM.

---

## 7. Failure modes and guarantees

| Failure | Guarantee |
|---|---|
| Report never arrives (Vapi outage, call never connected) | row stays `pending` → `abandoned` after 6 h; never injected |
| Report delivered twice | `ON CONFLICT (vapi_call_id)` upsert |
| Report arrives before the pending row commits | upsert inserts; company+time fallback |
| Context lookup fails | variables response identical to today |
| Transcript enormous | stored; only 900 chars injected |
| Stale facts mislead the model | prompt rule: context is a hint, tools are truth |
| Two calls for one company | `call_ref` disambiguates |

---

## 8. Retention — 10 days

- **10 days** for `voice_calls` (transcript, messages, summary).
- Nightly job: `DELETE FROM voice_calls WHERE created_at < now() - interval '10 days'`, then flip `status='pending' AND started_at < now() - interval '6 hours'` to `abandoned`.
- The injection window is **7 days**, inside the retention window, so context never points at a row that is about to disappear.
- No recordings are stored; audio is not needed for context.

---

## 9. Tasks, each with its test plan

Order is dependency order. Nothing proceeds without an explicit go.

**T1 — Capture the current reality (read-only).**
Read one real `end-of-call-report` payload out of an n8n execution of the hook and answer: does `message.type` arrive as expected, **is `assistantOverrides.variableValues` echoed back in `message.call`**, and how big is a real transcript.
*Test:* print the payload's top-level keys + the variableValues presence boolean for one real call; recorded in this doc. This decides `call_ref` matching vs the company+time fallback.

**T2 — Schema.**
`db/0039_voice_context.sql`, `db/0040_voice_context_verify.sql`, registered in `deploy/migrate.sh`.
*Test:* hermetic run in migrate.sh order on a scratch Postgres; live apply after a `pg_dump` snapshot; the verify file asserts and rolls back; `doc/SCHEMA.md` regenerated and diffed.

**T3 — Hook: branch + pending row + report upsert.**
*Test:* offline node harness, four fixtures (app variables POST, end-of-call-report POST, status-update POST, malformed POST) asserting the response body per branch, SQL param arity/order, and that the variables branch output is **byte-identical to today** for non-report bodies. `node --check` on every generated jsCode; unique node ids and connection integrity validated before import.

**T4 — Injection.**
Context query + `recent_context` in `Build Hook Variables` + the prompt section.
*Test:* harness fixtures — no rows, a fresh call summary, a stale (>7 d) row, a 20 KB transcript (assert the 900-char cap), query-error path (assert today's payload). Live: `POST /webhook/vapi/assistant-hook` with a real `X-User-Token` → `recent_context` present.

**T5 — Live end-to-end.**
1. Place a short voice call, say one identifying sentence, hang up.
2. Assert exactly one `voice_calls` row `status='reported'` with non-null `transcript` and `ended_reason`.
3. Call the hook with the token → `recent_context` contains that topic.
4. Start a second call and ask "what were we just talking about?" → assert from the **second call's stored report** that it used the context (not by ear).
*Test:* the four assertions plus a `SELECT` showing both rows.

**T6 — Retention job.**
Nightly SQL (abandon + 10-day delete) wired into an existing daily job or a cron SQL step.
*Test:* insert an 11-day-old row and a 2-day-old pending row; run the job; assert exactly one delete and one `abandoned` flip.

**T7 — Documentation.**
`doc/SCHEMA.md` regen, `doc/NEXT_STEPS.md` entry, project-skill note that reports arrive on the default `serverMessages` set and were being discarded.

---

## 10. Rollout and rollback

- One deploy script: pre-dump → 0039/0040 → import the changed workflow → activate → container restart → `create_vapi_assistant.py` (prompt section only — **no `serverMessages` change**) → live probes → SCHEMA regen.
- **Rollback:** re-import the previous workflow JSON from git, re-run `create_vapi_assistant.py` from the parent commit, and leave the table in place (dropping it destroys the only transcripts — decide at the time).

---

## 11. Decisions

| # | Item | Decision |
|---|---|---|
| 1 | Retention | **10 days**, single window |
| 2 | Greeting | **Unchanged** — today's deterministic greeting |
| 3 | Text chat in context | **Excluded** — the text thread already carries its own history via `chatId` |
| 4 | `serverMessages` narrowing | **Left as-is** — capture rides Vapi's default set, which includes `end-of-call-report`; ~37 ignored event POSTs per call continue |
| 5 | Legacy Twilio/Sheets workflow | **Left alone** — unrelated to this path |

---

## 12. Non-goals (explicitly out of scope)

- Re-attaching to a live call, or the "Start Voice enabled during a live call" state bug (separate, previously reverted feature).
- Text↔voice context crossing: text is self-continuing via `chatId`; voice is the gap this build closes.
- Search over old conversations ("what did we say in August about Oakridge") — recent continuity only, capped at 7 days.
- Any change to the Flutter app, therefore no APK rebuild.
- Cross-company or cross-user memory: one user per company, company-scoped rows.
