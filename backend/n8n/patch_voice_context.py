#!/usr/bin/env python3
"""Add voice-call context capture + injection to the Vapi assistant hook.

Idempotent: re-running replaces the generated nodes rather than appending.

Shape after this patch:

  Webhook
    -> Route By Event Type (switch)
         report  )  Extract Call Report -> Exec: upsert_call_report -> Respond Report
         other   )  Event Or Call Start?
                      true  -> Resolve Company Scope -> Exec: start_call_row
                               -> Exec: read_setup_status -> Build Hook Variables
                               -> Respond Hook (variables)
                      false -> Respond Event (ignored)

Why the middle branch exists: Vapi POSTs ~37 events per call to this same URL
(conversation-update, speech-update, status-update, ...). Only a call START
(no message.type, sent by the app with X-User-Token) should write a pending
row; everything else answers 200 and does nothing.

Design: doc/VOICE_CONTEXT_DESIGN.md
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "workflows", "vapi-assistant-hook.json")

ASSISTANT_ID = "67e2850c-1028-484d-bf52-d948826b2a7e"
PG_CRED = {"postgres": {"id": "YOUR_POSTGRES_CREDENTIALS_ID", "name": "Supabase PostgreSQL"}}

# ---------------------------------------------------------------- node SQL

START_CALL_ROW_SQL = (
    "INSERT INTO voice_calls (company_id, call_ref)\n"
    "SELECT COALESCE((SELECT company_id FROM users WHERE id = $1::uuid), 1),\n"
    "       gen_random_uuid()\n"
    "RETURNING call_ref;"
)

READ_SETUP_SQL = (
    "SELECT (cp.setup_completed_at IS NOT NULL) AS setup_complete,\n"
    "       cp.company_name,\n"
    "       COALESCE(cp.pm_preferred_name, '') AS pm_preferred_name,\n"
    "       lc.ctx            AS last_call_ctx,\n"
    "       lc.ended_at       AS last_call_ended_at,\n"
    "       lc.ended_reason   AS last_call_ended_reason\n"
    "  FROM company_profile cp\n"
    "  LEFT JOIN LATERAL (\n"
    "        SELECT right(COALESCE(vc.summary, vc.transcript), 900) AS ctx,\n"
    "               vc.ended_at, vc.ended_reason\n"
    "          FROM voice_calls vc\n"
    "         WHERE vc.company_id = cp.id\n"
    "           AND vc.status = 'reported'\n"
    "           AND vc.ended_at > now() - interval '7 days'\n"
    "           AND vc.ended_at < now() - interval '30 seconds'\n"
    "         ORDER BY vc.ended_at DESC\n"
    "         LIMIT 1\n"
    "  ) lc ON true\n"
    " WHERE cp.id = COALESCE((SELECT company_id FROM users WHERE id = $1::uuid), 1)\n"
    " LIMIT 1;"
)

UPSERT_REPORT_SQL = (
    "WITH upd AS (\n"
    "  UPDATE voice_calls\n"
    "     SET status           = 'reported',\n"
    "         vapi_call_id     = COALESCE($2, vapi_call_id),\n"
    "         started_at       = COALESCE($3::timestamptz, started_at),\n"
    "         ended_at         = COALESCE($4::timestamptz, ended_at),\n"
    "         ended_reason     = COALESCE($5, ended_reason),\n"
    "         duration_seconds = COALESCE($6, duration_seconds),\n"
    "         summary          = COALESCE($7, summary),\n"
    "         transcript       = COALESCE($8, transcript),\n"
    "         messages         = COALESCE($9::jsonb, messages),\n"
    "         updated_at       = now()\n"
    "   WHERE $1::uuid IS NOT NULL\n"
    "     AND call_ref = $1::uuid\n"
    "   RETURNING id, call_ref, status\n"
    "), ins AS (\n"
    "  INSERT INTO voice_calls (company_id, call_ref, vapi_call_id, status,\n"
    "                           started_at, ended_at, ended_reason,\n"
    "                           duration_seconds, summary, transcript, messages)\n"
    "  SELECT 1,\n"
    "         COALESCE($1::uuid, gen_random_uuid()),\n"
    "         $2,\n"
    "         'reported',\n"
    "         COALESCE($3::timestamptz, now()),\n"
    "         $4::timestamptz,\n"
    "         CASE WHEN $1::uuid IS NULL THEN 'unmatched:' || COALESCE($5, 'unknown')\n"
    "              ELSE $5 END,\n"
    "         $6, $7, $8, $9::jsonb\n"
    "   WHERE NOT EXISTS (SELECT 1 FROM upd)\n"
    "     AND COALESCE($2, '') <> ''\n"
    "  ON CONFLICT (vapi_call_id) DO UPDATE\n"
    "     SET status       = 'reported',\n"
    "         ended_at     = COALESCE(EXCLUDED.ended_at, voice_calls.ended_at),\n"
    "         ended_reason = COALESCE(voice_calls.ended_reason, EXCLUDED.ended_reason),\n"
    "         transcript   = COALESCE(voice_calls.transcript, EXCLUDED.transcript),\n"
    "         summary      = COALESCE(voice_calls.summary, EXCLUDED.summary),\n"
    "         messages     = COALESCE(voice_calls.messages, EXCLUDED.messages),\n"
    "         updated_at   = now()\n"
    "  RETURNING id, call_ref, status\n"
    ")\n"
    "SELECT id, call_ref, status FROM upd\n"
    "UNION ALL\n"
    "SELECT id, call_ref, status FROM ins\n"
    "UNION ALL\n"
    "SELECT NULL::bigint, NULL::uuid, 'none'::text\n"
    " WHERE NOT EXISTS (SELECT 1 FROM upd)\n"
    "   AND NOT EXISTS (SELECT 1 FROM ins);"
)

# ---------------------------------------------------------------- node code

EXTRACT_CODE = r"""
// Pull the end-of-call-report payload into flat columns for the upsert.
// The webhook item is { headers, params, query, body }; `body.message` is the
// Vapi ServerMessage. call_ref rides back inside
// call.assistantOverrides.variableValues because the call-start hook put it
// there — that is how a report is matched to the call that started it.
const item = $input.first().json || {};
const body = item.body || {};
const m = body.message || {};
const call = m.call || {};
const art = m.artifact || {};
const vv = (call.assistantOverrides && call.assistantOverrides.variableValues) || {};

const startedMs = call.startedAt ? Date.parse(call.startedAt) : null;
const endedMs = call.endedAt ? Date.parse(call.endedAt) : null;
const duration = (startedMs && endedMs && endedMs > startedMs)
  ? Math.round((endedMs - startedMs) / 100) / 10
  : null;

const callRef = String(vv.call_ref || '').trim();
const messages = art.messages || call.messages || null;

return [{
  json: {
    call_ref: callRef || null,
    vapi_call_id: call.id || null,
    started_at: call.startedAt || null,
    ended_at: call.endedAt || null,
    ended_reason: m.endedReason || call.endedReason || null,
    duration_seconds: duration,
    summary: (m.analysis && m.analysis.summary) || call.summary || null,
    transcript: art.transcript || call.transcript || null,
    // jsonb parameter travels as a JSON string (pg cannot bind a JS object).
    messages: messages ? JSON.stringify(messages) : null,
  },
}];
"""

BUILD_VARIABLES_CODE = r"""
// Build setup-status variables + a human-like greeting for Vapi.
// - firstMessage: time-aware + randomized variation, personalized with the PM's
//   preferred name; on the very first call (setup incomplete) it goes straight
//   into onboarding.
// - onboarding_steps: injected into the system prompt ONLY while setup is
//   incomplete, so the prompt does not carry it once onboarding is done.
// - recent_context: tail of the last voice call (<=900 chars, inside 7 days),
//   so a new call does not start from zero. Always present; empty string when
//   there is no history.
// - call_ref: the uuid of the pending row created for THIS call; Vapi echoes it
//   back in the end-of-call report.
const row = $input.first().json;
const setupComplete = !!row.setup_complete;
const name = String(row.pm_preferred_name || '').trim();

let callRef = '';
try {
  callRef = String(($('Exec: start_call_row').first().json || {}).call_ref || '');
} catch (e) {
  callRef = '';  // the pending row failed to insert; the report will land as 'unmatched:'
}

// Time of day in the PM's timezone (Ireh Construction, Coquitlam BC).
const hour = parseInt(new Date().toLocaleString('en-US', {
  timeZone: 'America/Vancouver', hour: 'numeric', hour12: false,
}), 10);
const isMorning = hour >= 5 && hour < 12;

function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

let firstMessage;
if (!setupComplete) {
  firstMessage = "Hey, let's get you set up - what's the company name?";
} else if (isMorning) {
  firstMessage = pick([
    name ? `Hey ${name}, good morning, what's up?` : "Hey, good morning, what's up?",
    name ? `Good morning ${name}, what's happening?` : "Good morning, what's happening?",
  ]);
} else {
  firstMessage = pick([
    name ? `Hey ${name}, what's up?` : "Hey, what's up?",
    name ? `Hey ${name}, what's happening?` : "Hey, what's happening?",
    name ? `What's good, ${name}?` : "What's good?",
  ]);
}

// Last call context: the transcript tail, with a short deterministic header.
let recentContext = '';
const ctx = String(row.last_call_ctx || '').trim();
if (ctx) {
  let when = '';
  if (row.last_call_ended_at) {
    const d = new Date(row.last_call_ended_at);
    if (!isNaN(d.getTime())) {
      when = d.toLocaleString('en-US', {
        timeZone: 'America/Vancouver', month: 'short', day: 'numeric',
        hour: 'numeric', minute: '2-digit',
      });
    }
  }
  const reason = String(row.last_call_ended_reason || '').trim();
  recentContext = 'Previous voice call'
    + (when ? ' (' + when + ')' : '')
    + (reason ? ' ended: ' + reason.replace(/[-_]/g, ' ') : '')
    + '.\nTranscript tail:\n' + ctx;
}

const steps = setupComplete ? '' : [
  '# First-Run Setup (Onboarding) - follow these steps',
  '- Run onboarding BEFORE any other work when setup_complete is false, even if',
  '  the caller asks for something else first - tell them one minute of setup is needed.',
  '- Do NOT call get_onboarding_status to learn the status; it is injected above.',
  '  Call it only to refresh mid-call (e.g. right after complete_onboarding).',
  '  1. Ask for the company name.',
  '  2. Ask for the project manager\'s full name.',
  '  3. Ask how the PM wants to be addressed every day (e.g. "Dave" or "boss").',
  '  4. Ask for the company billing address (street, city, province, postal code) -',
  '     it appears on every client invoice.',
  '  5. Ask for the company GST number (e.g. 123456789RT0001). If they do not have',
  '     it handy, note it can be added later and move on.',
  '  6. Ask if they charge PST and if so for the PST number (optional; skip if unsure).',
  '  7. Ask how customers should pay (payment instructions) - e.g. e-transfer email,',
  '     cheque details. Repeat the instructions back to confirm them.',
  '  8. Ask for each worker\'s name, trade, and hourly rate, one at a time',
  '     (ask "anyone else?" until they say no).',
  '  9. When you have everything, call complete_onboarding with all fields',
  '     (workers as an array), then confirm: "All set - everything is registered."',
  '- Keep each question short (10-15 words). Never call complete_onboarding before',
  '  you have company name, PM name, preferred address, and the worker list (an',
  '  empty workers array is allowed only if they have no crew yet).',
  '- If setup IS complete, never re-run onboarding unless the user asks to change',
  '  company details; use add_worker for new crew members.',
].join('\n');

const variableValues = {
  setup_complete: row.setup_complete,
  company_name: row.company_name,
  pm_preferred_name: row.pm_preferred_name,
  onboarding_steps: steps,
  // Always present (empty when there is no history) so the prompt never
  // renders a literal {{recent_context}} placeholder to the model.
  recent_context: recentContext,
};
if (callRef) variableValues.call_ref = callRef;

// assistant-request response contract (docs.vapi.ai/server-url/events):
// { assistantId } + assistantOverrides.{ variableValues, firstMessage }.
// The stored assistant provides model/voice/tools/prompt; these per-call
// overrides supply the DB-backed variables and the dynamic greeting.
return [{
  json: {
    assistantId: '67e2850c-1028-484d-bf52-d948826b2a7e',
    assistantOverrides: {
      variableValues,
      firstMessage,
    },
  },
}];
"""


def pg(name, node_id, sql, repl, pos, always=True):
    n = {
        "parameters": {
            "operation": "executeQuery",
            "query": sql,
            "options": {"queryReplacement": repl},
        },
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.4,
        "position": pos,
        "credentials": PG_CRED,
    }
    if always:
        n["alwaysOutputData"] = True
    return n


def code(name, node_id, js, pos):
    return {
        "parameters": {"jsCode": js.strip() + "\n"},
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos,
    }


def respond(name, node_id, body, pos):
    return {
        "parameters": {
            "respondWith": "json",
            "responseBody": body,
            "options": {},
        },
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.1,
        "position": pos,
    }


def build(wf):
    by_name = {n["name"]: n for n in wf["nodes"]}

    # 1) route: report vs everything else
    route = {
        "parameters": {
            "rules": {
                "values": [{
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "conditions": [{
                            "leftValue": "={{ $json.body?.message?.type }}",
                            "rightValue": "end-of-call-report",
                            "operator": {"type": "string", "operation": "equals"},
                        }],
                        "combinator": "and",
                    },
                    "renameOutput": True,
                    "outputKey": "report",
                }],
            },
            "options": {"fallbackOutput": "extra"},
        },
        "id": "hook-0006",
        "name": "Route By Event Type",
        "type": "n8n-nodes-base.switch",
        "typeVersion": 3,
        "position": [220, 0],
    }

    # 2) is this a call start (app POST) rather than a Vapi event?
    is_start = {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                "conditions": [{
                    "id": "no-vapi-message-type",
                    "leftValue": "={{ $json.body?.message?.type }}",
                    "rightValue": "",
                    "operator": {"type": "string", "operation": "empty"},
                }],
                "combinator": "and",
            },
            "options": {},
        },
        "id": "hook-0007",
        "name": "Call Start Or Event?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [440, 140],
    }

    report_nodes = [
        code("Extract Call Report", "hook-0010", EXTRACT_CODE, [440, -160]),
        pg("Exec: upsert_call_report", "hook-0011", UPSERT_REPORT_SQL,
           ["={{ $json.call_ref }}", "={{ $json.vapi_call_id }}", "={{ $json.started_at }}",
            "={{ $json.ended_at }}", "={{ $json.ended_reason }}", "={{ $json.duration_seconds }}",
            "={{ $json.summary }}", "={{ $json.transcript }}", "={{ $json.messages }}"],
           [660, -160]),
        respond("Respond Report (ok)", "hook-0012", '={"ok":true}', [880, -160]),
    ]

    start_nodes = [
        pg("Exec: start_call_row", "hook-0009", START_CALL_ROW_SQL,
           ["={{ $json.uid }}"], [440, 220]),
        respond("Respond Event (ignored)", "hook-0008", '={"ok":true,"ignored":true}', [440, 420]),
    ]

    # 3) rewire existing nodes' positions a little so the canvas reads sensibly
    by_name["Resolve Company Scope"]["position"] = [660, 220]
    by_name["Exec: read_setup_status"]["position"] = [880, 220]
    by_name["Build Hook Variables"]["position"] = [1100, 220]
    by_name["Respond Hook (variables)"]["position"] = [1320, 220]

    # 4) existing nodes get the new SQL / code
    by_name["Exec: read_setup_status"]["parameters"]["query"] = READ_SETUP_SQL
    by_name["Exec: read_setup_status"]["parameters"]["options"] = {
        "queryReplacement": ["={{ $('Resolve Company Scope').first().json.uid }}"]
    }
    by_name["Exec: read_setup_status"]["alwaysOutputData"] = True
    by_name["Build Hook Variables"]["parameters"]["jsCode"] = BUILD_VARIABLES_CODE.strip() + "\n"

    keep = [by_name[n] for n in ("Assistant Hook Webhook", "Resolve Company Scope",
                                 "Exec: read_setup_status", "Build Hook Variables",
                                 "Respond Hook (variables)")]
    wf["nodes"] = keep + [route, is_start] + report_nodes + start_nodes

    wf["connections"] = {
        "Assistant Hook Webhook": {"main": [[{"node": "Route By Event Type", "type": "main", "index": 0}]]},
        "Route By Event Type": {"main": [
            [{"node": "Extract Call Report", "type": "main", "index": 0}],
            [{"node": "Call Start Or Event?", "type": "main", "index": 0}],
        ]},
        "Call Start Or Event?": {"main": [
            [{"node": "Resolve Company Scope", "type": "main", "index": 0}],
            [{"node": "Respond Event (ignored)", "type": "main", "index": 0}],
        ]},
        "Resolve Company Scope": {"main": [[{"node": "Exec: start_call_row", "type": "main", "index": 0}]]},
        "Exec: start_call_row": {"main": [[{"node": "Exec: read_setup_status", "type": "main", "index": 0}]]},
        "Exec: read_setup_status": {"main": [[{"node": "Build Hook Variables", "type": "main", "index": 0}]]},
        "Build Hook Variables": {"main": [[{"node": "Respond Hook (variables)", "type": "main", "index": 0}]]},
        "Extract Call Report": {"main": [[{"node": "Exec: upsert_call_report", "type": "main", "index": 0}]]},
        "Exec: upsert_call_report": {"main": [[{"node": "Respond Report (ok)", "type": "main", "index": 0}]]},
    }
    return wf


def validate(wf):
    errs = []
    names = [n["name"] for n in wf["nodes"]]
    ids = [n["id"] for n in wf["nodes"]]
    if len(set(names)) != len(names):
        errs.append("duplicate node names")
    if len(set(ids)) != len(ids):
        errs.append("duplicate node ids")
    known = set(names)
    for src, spec in wf["connections"].items():
        if src not in known:
            errs.append(f"connection source not a node: {src}")
        for branch in spec.get("main") or []:
            for conn in branch:
                if conn["node"] not in known:
                    errs.append(f"connection target not a node: {conn['node']}")
    # respond-node coverage: every terminal path must answer (webhook mode=responseNode)
    for n in wf["nodes"]:
        if n["type"].endswith("respondToWebhook"):
            continue
        if n["name"] not in wf["connections"]:
            errs.append(f"node has no outgoing connection (would hang the webhook): {n['name']}")
    # SQL parameter arity vs queryReplacement
    for n in wf["nodes"]:
        if not n["type"].endswith("postgres"):
            continue
        q = n["parameters"].get("query", "")
        used = {int(x) for x in __import__("re").findall(r"\$(\d+)", q)}
        repl = n["parameters"].get("options", {}).get("queryReplacement") or []
        if used != set(range(1, len(repl) + 1)):
            errs.append(f"{n['name']}: SQL uses ${sorted(used)} but {len(repl)} replacements")
    # jsCode syntax
    for n in wf["nodes"]:
        if not n["type"].endswith(".code"):
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write("(async () => {\n" + n["parameters"]["jsCode"] + "\n})();")
            path = fh.name
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        os.unlink(path)
        if r.returncode != 0:
            errs.append(f"{n['name']}: jsCode syntax error: {r.stderr.strip().splitlines()[:3]}")
    return errs


def main():
    with open(WF) as fh:
        wf = json.load(fh)
    wf = build(wf)
    errs = validate(wf)
    if errs:
        for e in errs:
            print("FAIL:", e)
        return 1
    with open(WF, "w") as fh:
        json.dump(wf, fh, indent=1)
        fh.write("\n")
    print(f"patched {WF}")
    for n in wf["nodes"]:
        print(f"  {n['id']:10s} {n['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
