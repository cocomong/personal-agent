# Voice + text context carryover — design (for review, nothing built)

**Status:** proposal only. No migrations applied, no workflows imported, no app changes.
**Date:** 2026-10-27 (rev 2 — decisions from review applied)
**Author:** Hermes

**Decisions taken 2026-10-27:** retention **10 days**; text chat **included**; `serverMessages`
**left as-is**; legacy Twilio/Sheets workflow **left alone**. Greeting behaviour (open question 2)
is the only unresolved item.

---

## 1. What already works, so we build only the missing part

| Layer | State | Where |
|---|---|---|
| App shows the last conversation on launch | **Works** | `session_persistence.dart` restores chat id + transcript; `AgentScreen._restoreTranscript()` |
| Assistant remembers the **text** thread | **Works** | every `/webhook/chat` call carries the persisted `chatId`; Vapi keeps the thread |
| Assistant remembers the **voice** conversation | **Missing** | a new call starts with company variables only; nothing stores what was said |
| Voice ↔ text context crossing | **Missing** | a voice call knows nothing said in text; a text chat knows nothing said by voice |

Nothing in the Flutter app needs to change. This is server-side capture + injection.

---

## 2. Findings from investigating the live stack (verified 2026-10-27)

1. **The assistant's `serverUrl` is `https://n8n2.ordrnow.com/webhook/vapi/assistant-hook`** and `serverMessages` is **unset**. Vapi's documented default set includes `end-of-call-report`, `status-update`, `speech-update`, `conversation-update`, `tool-calls` and more.
   → **Vapi is already POSTing every call's `end-of-call-report` to our hook — and the hook discards it.**
2. **Volume:** the hook workflow ran **1,398 times in 7 days** (`execution_entity`, live n8n SQLite) while the app invokes it once per call start. Most runs are event POSTs whose bodies are ignored.
   **Decision: leave `serverMessages` as-is** — zero Vapi config change, capture rides the default set. The wasted runs continue; they are cheap and harmless, and the report branch simply ignores anything that is not a report.
3. **No conversation storage exists:** `db/` ends at `0038`; there is no calls / messages / chat-turn table.
4. **`analysisPlan` is unset** → reports carry `artifact.transcript` and `artifact.messages`, but no `analysis.summary`.
5. **Report shape** (Vapi docs): `{ message: { type, endedReason, call, artifact: { transcript, messages[] } } }`.
6. **Legacy workflow** "end of call report" (`K5h8akMdXeLXkI2K`, `/webhook/callreport`, Twilio SMS + Google Sheets, live since 2026-07-13) is unrelated to this path. **Decision: leave it.**

---

## 3. Architecture

```
      voice                                      text
 call start (app)                            POST /webhook/chat
        |                                          |
        v                                          v
 /webhook/vapi/assistant-hook              resolve company + chatId
   branch on message.type                    call Vapi /chat
        |                                          |
        +--> pending voice_calls row               +--> INSERT user + assistant turns
        +--> SELECT last call summary               +--> respond {chatId, reply}
        +--> SELECT last text turns
        +--> respond assistantOverrides
             { variableValues: {…, recent_context} }

 call end (Vapi) --> end-of-call-report --> upsert voice_calls
                                            (transcript, summary, status='reported')
```

Two capture points, two injection points:

| | captured | injected into |
|---|---|---|
| Voice calls | end-of-call-report | **voice** (call start): last call summary **+** recent text turns |
| Text chat | every turn at the chat proxy | **voice** (call start): recent text turns; **text** (each turn): last call summary |

The asymmetry is deliberate. A text chat already carries its own history through `chatId`, so re-injecting text turns there would duplicate what the model can already see; it cannot see voice, so the last call summary is injected into text. A voice call can see neither, so it gets both.

Calling `POST /webhook/vapi/assistant-hook` from the app is unaffected by `serverMessages` (that setting only governs Vapi→server sends).

---

## 4. Data model — `db/0039_context_capture.sql` + `db/0040_context_capture_verify.sql`

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

CREATE TABLE IF NOT EXISTS chat_turns (
  id          bigserial PRIMARY KEY,
  company_id  integer NOT NULL REFERENCES company_profile(id) ON DELETE CASCADE,
  chat_id     text NOT NULL,
  role        text NOT NULL CHECK (role IN ('user','assistant')),
  content     text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_turns_recent_idx ON chat_turns (company_id, created_at DESC);
```

- `call_ref` is generated by the hook at call start and is the join key between "a call is about to happen" and "here is its report".
- Register both files in `deploy/migrate.sh` in DEPLOY order after the 0037/0038 pair; regenerate `doc/SCHEMA.md` afterwards.
- **Verify file (`0040`) asserts, then rolls back:** pending + reported insert; duplicate `call_ref` rejected; bogus `status` and bogus `chat_turns.role` rejected; FK rejects `company_id = 9999`; the recent-index queries return in the expected order.

---

## 5. Capture paths

**5.1 Voice — branch the hook.** In `vapi-assistant-hook.json`, immediately after the webhook node, switch on `{{ $json.body.message.type }}`:
- `end-of-call-report` → report branch
- everything else (including the app's direct call, which has no `message.type`) → today's variables path, byte-identical

**5.2 Voice — pending row.** In the variables branch, after company resolution, `INSERT INTO voice_calls (company_id, call_ref) VALUES ($1, gen_random_uuid()) RETURNING call_ref`. Written on every call start, including calls that never connect (those become `abandoned`).

**5.3 Voice — report branch nodes** (new; ids from a plain counter, per the n8n id pitfall):

1. `Extract Call Report` (Code): pull `vapi_call_id = message.call.id`, `ended_reason = message.endedReason`, timestamps from `message.call`, `transcript = message.artifact.transcript`, `messages = message.artifact.messages`, `summary = message.analysis?.summary ?? null`; derive `duration_seconds`.
2. `Exec: match_or_insert_call` (Postgres, `operation: executeQuery`): match by `call_ref` from `message.call.assistantOverrides.variableValues.call_ref` **if that field exists** (T1 decides), else the most recent `pending` row for the company within 6 h; `UPDATE … SET status='reported', vapi_call_id, ended_at, ended_reason, transcript, summary, messages …`. If nothing matches, `INSERT` a `reported` row with a generated `call_ref` and `ended_reason` prefixed `unmatched:` — visible rather than silent.
3. `Respond Report (ok)` (Respond to Webhook, 200 `{"ok":true}`) — Vapi expects no body for this type.

**5.4 Voice — dedupe & orphans.** `vapi_call_id UNIQUE` + `ON CONFLICT (vapi_call_id) DO UPDATE` makes Vapi's retries idempotent. A nightly step flips `pending` rows older than 6 h to `abandoned`, so a call that never connected is never injected as "last conversation".

**5.5 Text — capture at the chat proxy.** In `chat-gateway.json`, after `Chat OK?`, one Postgres node inserts two rows per turn (`role='user'` with the request input, `role='assistant'` with the reply) using the company from `Resolve Chat Token` and the `chatId` from the request. It runs **after** the response payload is built and its errors are caught, so a storage fault never costs the user their answer.

---

## 6. Injection paths

**6.1 Shared context query** (guaranteed row — a 0-row result would end the n8n chain silently):

```sql
-- voice call start: last call summary + recent text turns
SELECT
  (SELECT left(coalesce(summary, transcript), 900)
     FROM voice_calls
    WHERE company_id = $1 AND status = 'reported'
      AND ended_at > now() - interval '7 days'
      AND ended_at < now() - interval '30 seconds'
    ORDER BY ended_at DESC LIMIT 1) AS last_call,
  (SELECT string_agg(role || ': ' || left(content, 200), E'\n' ORDER BY created_at)
     FROM (SELECT role, content, created_at
             FROM chat_turns
            WHERE company_id = $1
              AND created_at > now() - interval '7 days'
            ORDER BY created_at DESC LIMIT 6) t) AS recent_text;
```

**6.2 `Build Hook Variables`** formats this into one `variableValues.recent_context` (≤1,600 chars total) and omits the key entirely when both parts are null.

**6.3 Text injection.** The chat proxy adds the same key to its `assistantOverrides.variableValues`, carrying **only** the last voice-call summary — not text turns, which are already in the thread.

**6.4 System prompt section** (added to `backend/vapi_assistant.json`):

```
## Recent context
variableValues.recent_context may hold a summary of the last voice call and the last few
text messages. Use it to avoid re-asking what the PM already told you, and to offer
continuity when they return to the same topic. Never read it aloud or quote it back.
Never state a fact from it as current without checking a tool first — amounts, balances
and statuses change. If the last call ended mid-task and they resume it, pick up from
there instead of starting over. If it is empty, behave exactly as today.
```

**6.5 Greeting.** **Unresolved.** Either keep today's deterministic greeting (recommended for v1 — the model uses `recent_context` when the topic comes up) or template one continuity line into `firstMessage` when the last call was within 24 h. Awaiting the pick.

**6.6 Failure isolation.** Every context lookup is failure-tolerant: any error, timeout or missing row falls through to today's exact payload. The hook is on the call's critical path (the app waits on it), so its budget stays small: one SQL round trip, no LLM.

---

## 7. Failure modes and guarantees

| Failure | Guarantee |
|---|---|
| Report never arrives (Vapi outage, call never connected) | row stays `pending` → `abandoned` after 6 h; never injected |
| Report delivered twice | `ON CONFLICT (vapi_call_id)` upsert |
| Report arrives before the pending row commits | upsert inserts; company+time fallback |
| Chat capture fails | the reply still returns; the turn is simply absent from context |
| Context lookup fails | variables response identical to today |
| Transcript enormous | stored; only 900 chars of the last call + 6 turns × 200 chars injected |
| Stale facts mislead the model | prompt rule: context is a hint, tools are truth |
| Two calls for one company | `call_ref` disambiguates |

---

## 8. Retention — 10 days

- **10 days** for `voice_calls` (transcript, messages, summary) and `chat_turns` (content). One window, both tables — no transcript/summary split.
- Nightly job: `DELETE FROM voice_calls WHERE created_at < now() - interval '10 days'`; `DELETE FROM chat_turns WHERE created_at < now() - interval '10 days'`; then flip `status='pending' AND started_at < now() - interval '6 hours'` to `abandoned`.
- The injection window is **7 days**, inside the retention window, so context never points at a row that is about to disappear.
- No recordings are stored; audio is not needed for context.

---

## 9. Tasks, each with its test plan

Order is dependency order. Nothing proceeds without an explicit go.

**T1 — Capture the current reality (read-only).**
Read one real `end-of-call-report` payload out of an n8n execution of the hook and answer: does `message.type` arrive as expected, **is `assistantOverrides.variableValues` echoed back in `message.call`**, and how big is a real transcript.
*Test:* print the payload's top-level keys + the variableValues presence boolean for one real call; recorded in this doc. This decides `call_ref` matching vs the company+time fallback.

**T2 — Schema.**
`db/0039_context_capture.sql`, `db/0040_context_capture_verify.sql`, registered in `deploy/migrate.sh`.
*Test:* hermetic run in migrate.sh order on a scratch Postgres; live apply after a `pg_dump` snapshot; the verify file asserts and rolls back; `doc/SCHEMA.md` regenerated and diffed.

**T3 — Hook: branch + pending row + report upsert.**
*Test:* offline node harness, four fixtures (app variables POST, end-of-call-report POST, status-update POST, malformed POST) asserting the response body per branch, SQL param arity/order, and that the variables branch output is **byte-identical to today** for non-report bodies. `node --check` on every generated jsCode; unique node ids and connection integrity validated before import.

**T4 — Text capture at the chat proxy.**
*Test:* harness that posts a chat-shaped body through the modified chain with a mocked Vapi reply; assert two `chat_turns` rows with the right `company_id`, `chat_id`, roles and content; a forced SQL error still yields the reply.

**T5 — Injection (both paths).**
*Test:* fixtures — no rows, a fresh call summary, only text turns, stale (>7 d) rows, a 20 KB transcript (assert the cap), query-error path (assert today's payload). Live: `POST /webhook/vapi/assistant-hook` with a real `X-User-Token` → `recent_context` present; and one `/webhook/chat` turn → assert the injected overrides include the last call summary.

**T6 — Live end-to-end.**
1. Text the assistant one identifying sentence → assert `chat_turns` rows.
2. Place a short voice call, hang up → assert one `voice_calls` row `status='reported'` with non-null `transcript` and `ended_reason`.
3. Call the hook with the token → `recent_context` contains both the call summary and the text turn.
4. Start a second call and ask "what were we just talking about?" → assert from the **second call's stored report** that it used the context (not by ear).
*Test:* the four assertions plus a `SELECT` showing both rows.

**T7 — Retention job.**
Nightly SQL (abandon + 10-day delete) wired into an existing daily job or a cron SQL step.
*Test:* insert an 11-day-old voice row, an 11-day-old chat turn and a 2-day-old pending row; run the job; assert exactly the expected deletes and one `abandoned` flip.

**T8 — Documentation.**
`doc/SCHEMA.md` regen, `doc/NEXT_STEPS.md` entry, project-skill note that reports arrive on the default `serverMessages` set and were being discarded.

---

## 10. Rollout and rollback

- One deploy script: pre-dump → 0039/0040 → import both changed workflows → activate → container restart → `create_vapi_assistant.py` (prompt section only — **no `serverMessages` change**) → live probes → SCHEMA regen.
- **Rollback:** re-import the previous workflow JSONs from git, re-run `create_vapi_assistant.py` from the parent commit, and leave the tables in place (dropping them destroys the only transcripts — decide at the time).

---

## 11. Decisions and open items

| # | Item | Decision |
|---|---|---|
| 1 | Retention | **10 days**, voice + text, single window |
| 2 | Greeting | **OPEN** — deterministic (recommended) vs one continuity line when the last call is <24 h old |
| 3 | Text chat in context | **Included** — captured at the chat proxy, injected into voice; voice summary injected into text |
| 4 | `serverMessages` narrowing | **Left as-is.** Capture rides Vapi's default set, which already includes `end-of-call-report`. The ~200 ignored event POSTs/day continue and are harmless. |
| 5 | Legacy Twilio/Sheets workflow | **Left alone** — unrelated to this path |

---

## 12. Non-goals (explicitly out of scope)

- Re-attaching to a live call, or the "Start Voice enabled during a live call" state bug (separate, previously reverted feature).
- Search over old conversations ("what did we say in August about Oakridge") — recent continuity only, capped at 7 days.
- Any change to the Flutter app, therefore no APK rebuild.
- Cross-company or cross-user memory: one user per company, company-scoped rows.
