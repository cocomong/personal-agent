#!/usr/bin/env python3
"""Offline harness for the voice-context hook changes (no n8n, no network).

Runs the REAL jsCode from backend/n8n/workflows/vapi-assistant-hook.json against
fixtures, and asserts the SQL/wiring properties that a syntax check cannot see.

  python3 backend/n8n/test_voice_context_hook.py

Covers:
  T3 - event routing (report / call start / ignored event), the report upsert
       payload, and that the pending-row insert is on the call-start path only.
  T4 - recent_context injection: absent when there is no prior call, present and
       bounded when there is, onboarding unchanged, firstMessage unchanged.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "workflows", "vapi-assistant-hook.json")

NODE_RUNNER = r"""
const fs = require('fs');
const code = fs.readFileSync(process.env.CODE_PATH, 'utf8');
const payload = JSON.parse(process.env.FIXTURE || '{}');
const nodeOutputs = JSON.parse(process.env.NODE_OUTPUTS || '{}');
const $input = { first: () => ({ json: payload }), all: () => [{ json: payload }] };
const $env = { AUTH_TOKEN_SECRET: 'test-secret' };
const $ = (name) => ({ first: () => ({ json: nodeOutputs[name] || {} }) });
const fn = new Function('$input', '$env', '$', 'return (async () => {' + code + '})();');
fn($input, $env, $)
  .then((r) => { process.stdout.write(JSON.stringify(r)); })
  .catch((e) => { process.stderr.write('ERR ' + e.message); process.exit(1); });
"""

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        failures.append(msg)


def run_node(js, fixture, node_outputs=None):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        code_path = fh.name
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(NODE_RUNNER)
        runner = fh.name
    env = dict(os.environ,
               CODE_PATH=code_path,
               FIXTURE=json.dumps(fixture),
               NODE_OUTPUTS=json.dumps(node_outputs or {}))
    r = subprocess.run(["node", runner], capture_output=True, text=True, env=env)
    os.unlink(code_path)
    os.unlink(runner)
    if r.returncode != 0:
        raise RuntimeError(f"node failed: {r.stderr.strip()[:400]}")
    return json.loads(r.stdout)


def node(wf, name):
    for n in wf["nodes"]:
        if n["name"] == name:
            return n
    raise KeyError(name)


def webhook_item(body):
    return {"headers": {"x-user-token": "v1.x.y"}, "params": {}, "query": {}, "body": body}


def main():
    wf = json.load(open(WF))
    names = {n["name"] for n in wf["nodes"]}
    conns = wf["connections"]

    print("wiring")
    check(conns["Assistant Hook Webhook"]["main"][0][0]["node"] == "Route By Event Type",
          "webhook feeds the event router")
    check([c["node"] for c in conns["Route By Event Type"]["main"][0]] == ["Extract Call Report"],
          "router output 0 (report) -> Extract Call Report")
    check([c["node"] for c in conns["Route By Event Type"]["main"][1]] == ["Call Start Or Event?"],
          "router fallback -> Call Start Or Event?")
    check([c["node"] for c in conns["Call Start Or Event?"]["main"][0]] == ["Resolve Company Scope"],
          "call-start branch -> Resolve Company Scope")
    check([c["node"] for c in conns["Call Start Or Event?"]["main"][1]] == ["Respond Event (ignored)"],
          "ignored events -> Respond (no DB work)")
    check(conns["Resolve Company Scope"]["main"][0][0]["node"] == "Exec: start_call_row",
          "call start writes the pending row BEFORE reading setup status")
    check("Exec: start_call_row" not in
          [c["node"] for c in conns["Route By Event Type"]["main"][0]],
          "report branch never writes a pending row")
    for terminal in ("Respond Hook (variables)", "Respond Report (ok)", "Respond Event (ignored)"):
        check(terminal in names, f"{terminal} exists (webhook mode=responseNode needs a responder)")
    check(node(wf, "Route By Event Type")["parameters"]["rules"]["values"][0]
          ["conditions"]["conditions"][0]["rightValue"] == "end-of-call-report",
          "router matches end-of-call-report")
    check("message?.type" in node(wf, "Route By Event Type")["parameters"]["rules"]["values"][0]
          ["conditions"]["conditions"][0]["leftValue"],
          "router reads body.message.type (optional chaining: app POSTs have no body.message)")

    print("\nSQL")
    start_sql = node(wf, "Exec: start_call_row")["parameters"]["query"]
    check("INSERT INTO voice_calls" in start_sql and "gen_random_uuid()" in start_sql,
          "pending insert creates call_ref")
    check(start_sql.count("$1") == 1, "pending insert takes exactly the uid param")
    read_sql = node(wf, "Exec: read_setup_status")["parameters"]["query"]
    check("right(COALESCE(vc.summary, vc.transcript), 900)" in read_sql, "context is capped at 900 chars")
    check("interval '7 days'" in read_sql, "context window is 7 days")
    check("vc.status = 'reported'" in read_sql, "only reported calls are injected")
    check("interval '30 seconds'" in read_sql, "in-flight call is not injected as history")
    check("LEFT JOIN LATERAL" in read_sql or "lateral" in read_sql.lower(),
          "company row survives with no prior call (guaranteed row)")
    up = node(wf, "Exec: upsert_call_report")["parameters"]["query"]
    check("ON CONFLICT (vapi_call_id)" in up, "re-delivered report is idempotent")
    check("unmatched:" in up, "a report with no pending row is flagged, not silently dropped")
    used = sorted({int(x) for x in re.findall(r"\$(\d+)", up)})
    check(used == list(range(1, 10)), f"upsert binds $1..$9, got {used}")

    print("\nT3 - Extract Call Report")
    report_body = {
        "message": {
            "type": "end-of-call-report",
            "endedReason": "customer-ended-call",
            "call": {
                "id": "01a180e5-aaaa-bbbb-cccc-dddddddddddd",
                "startedAt": "2026-10-28T05:04:57.756Z",
                "endedAt": "2026-10-28T05:05:06.898Z",
                "assistantOverrides": {"variableValues": {"call_ref": "11111111-2222-3333-4444-555555555555"}},
            },
            "artifact": {
                "transcript": "AI: hey. User: create an invoice for Oakridge.",
                "messages": [{"role": "assistant", "message": "hey"}],
            },
        }
    }
    out = run_node(node(wf, "Extract Call Report")["parameters"]["jsCode"], webhook_item(report_body))[0]["json"]
    check(out["call_ref"] == "11111111-2222-3333-4444-555555555555", "call_ref echoed from the call's overrides")
    check(out["vapi_call_id"] == "01a180e5-aaaa-bbbb-cccc-dddddddddddd", "vapi_call_id extracted")
    check(out["ended_reason"] == "customer-ended-call", "endedReason extracted")
    check(abs((out["duration_seconds"] or 0) - 9.1) < 0.2, f"duration derived from timestamps ({out['duration_seconds']}s)")
    check(isinstance(out["messages"], str), "messages travel as a JSON string for the jsonb param")
    check("Oakridge" in (out["transcript"] or ""), "transcript extracted")

    no_ref = json.loads(json.dumps(report_body))
    del no_ref["message"]["call"]["assistantOverrides"]
    out2 = run_node(node(wf, "Extract Call Report")["parameters"]["jsCode"], webhook_item(no_ref))[0]["json"]
    check(out2["call_ref"] is None, "missing call_ref becomes NULL (upsert falls back to company+time row)")

    print("\nT4 - Build Hook Variables")
    base_row = {"setup_complete": True, "company_name": "Ireh Construction",
                "pm_preferred_name": "Dave", "last_call_ctx": None,
                "last_call_ended_at": None, "last_call_ended_reason": None}
    no_ctx = run_node(node(wf, "Build Hook Variables")["parameters"]["jsCode"], base_row,
                      {"Exec: start_call_row": {"call_ref": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}})[0]["json"]
    vv = no_ctx["assistantOverrides"]["variableValues"]
    check(vv.get("recent_context") == "", "no prior call -> recent_context is empty (never a literal {{recent_context}})")
    check(vv.get("call_ref") == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "call_ref forwarded to Vapi")
    check(vv["company_name"] == "Ireh Construction" and vv["setup_complete"] is True,
          "existing variables unchanged")
    check(no_ctx["assistantOverrides"]["firstMessage"], "greeting still produced (unchanged behaviour)")
    check(no_ctx["assistantId"] == "67e2850c-1028-484d-bf52-d948826b2a7e", "assistant id unchanged")

    with_ctx = dict(base_row)
    with_ctx["last_call_ctx"] = "AI: want the compact style? User: yes, switch it to compact."
    with_ctx["last_call_ended_at"] = "2026-10-27T22:11:00Z"
    with_ctx["last_call_ended_reason"] = "customer-ended-call"
    got = run_node(node(wf, "Build Hook Variables")["parameters"]["jsCode"], with_ctx,
                   {"Exec: start_call_row": {"call_ref": ""}})[0]["json"]["assistantOverrides"]["variableValues"]
    check("recent_context" in got, "prior call -> recent_context present")
    check("compact" in got["recent_context"], "context carries the transcript tail")
    check("customer ended call" in got["recent_context"], "ended reason is humanised")
    check(len(got["recent_context"]) < 1100, f"context stays small ({len(got['recent_context'])} chars)")
    check("call_ref" not in got, "empty call_ref is not forwarded as a bogus value")

    onboarding = run_node(node(wf, "Build Hook Variables")["parameters"]["jsCode"],
                          {"setup_complete": False, "company_name": "Ireh", "pm_preferred_name": "",
                           "last_call_ctx": None}, {})[0]["json"]["assistantOverrides"]["variableValues"]
    check("First-Run Setup" in onboarding["onboarding_steps"], "onboarding steps still injected when setup is incomplete")
    check(onboarding.get("recent_context") == "", "no context during onboarding")
    setup_done = run_node(node(wf, "Build Hook Variables")["parameters"]["jsCode"], base_row, {})[0]["json"]
    check(setup_done["assistantOverrides"]["variableValues"]["onboarding_steps"] == "",
          "onboarding steps stay empty once setup is complete")

    print("\nidempotency")
    before = open(WF).read()
    subprocess.run([sys.executable, os.path.join(HERE, "patch_voice_context.py")],
                   check=True, capture_output=True)
    check(open(WF).read() == before, "re-running the patcher produces an identical workflow")

    print()
    if failures:
        print(f"{len(failures)} FAILURES")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
