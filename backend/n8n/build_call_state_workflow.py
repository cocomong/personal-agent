#!/usr/bin/env python3
"""Generate backend/n8n/workflows/call-state.json.

POST /webhook/call/state  (X-User-Token required)
  -> { active: bool, callId?, startedAt?, type?, reason? }

Why: a Vapi web call keeps running while the app is backgrounded or killed.
The app has no way to see it (the private key must stay server-side), so the
UI happily shows "Start Voice" while a call is still open — and tapping it
opens a SECOND assistant. This endpoint is the app's window into Vapi's state:
it asks Vapi for this assistant's calls and reports whether one is still
in-progress. The app disables Start Voice while that is true.

Single assistant architecture: the id comes from VAPI_ASSISTANT_ID in the n8n
environment (same value the app uses). Multi-tenant scoping (metadata per
company) comes with Step 3.

Usage: python3 backend/n8n/build_call_state_workflow.py
"""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WF_PATH = ROOT / "backend" / "n8n" / "workflows" / "call-state.json"
CHAT = ROOT / "backend" / "n8n" / "workflows" / "chat-gateway.json"

RESOLVE_TOKEN_JS = """// Resolve the caller from X-User-Token (HMAC v1 token), same scheme as the
// chat proxy. No/invalid token -> uid null -> 401 below.
const crypto = require('crypto');
const req = $input.first().json || {};
const headers = req.headers || {};
const token = String(headers['x-user-token'] || headers['X-User-Token'] || '').trim();
const secret = $env.AUTH_TOKEN_SECRET || '';
let uid = null;
if (token && secret) {
  try {
    const parts = token.split('.');
    if (parts.length === 3 && parts[0] === 'v1') {
      const payloadB64 = parts[1];
      const expected = crypto.createHmac('sha256', secret).update(payloadB64).digest('base64url');
      const a = Buffer.from(parts[2]); const b = Buffer.from(expected);
      if (a.length === b.length && crypto.timingSafeEqual(a, b)) {
        const payload = JSON.parse(Buffer.from(payloadB64, 'base64url').toString());
        if (payload.uid && payload.exp * 1000 > Date.now()) uid = payload.uid;
      }
    }
  } catch (e) { uid = null; }
}
return [{ json: { uid } }];
"""

QUERY_VAPI_JS = """// Ask Vapi whether this assistant still has an in-progress call. The private
// key never leaves the server. Web-call statuses: queued | ringing |
// in-progress | forwarding | ended.
const https = require('https');
const assistantId = String($env.VAPI_ASSISTANT_ID || '').trim();
const key = String($env.VAPI_PRIVATE_KEY || '').trim();

function get(url) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, { method: 'GET', headers: {
      'Authorization': 'Bearer ' + key,
      'User-Agent': 'curl/8.5.0',
      'Accept': 'application/json',
    } }, (res) => {
      let data = '';
      res.on('data', (c) => (data += c));
      res.on('end', () => resolve({ status: res.statusCode, body: data }));
    });
    req.on('error', reject);
    req.end();
  });
}

async function run() {
  if (!key || !assistantId) return { active: false, reason: 'vapi not configured' };
  let r;
  try {
    r = await get(`https://api.vapi.ai/call?assistantId=${encodeURIComponent(assistantId)}&limit=10`);
  } catch (e) {
    return { active: false, reason: 'vapi unreachable: ' + e.message };
  }
  if (r.status !== 200) return { active: false, reason: 'vapi ' + r.status };
  let calls;
  try {
    calls = JSON.parse(r.body);
  } catch (e) {
    return { active: false, reason: 'vapi returned non-JSON' };
  }
  if (!Array.isArray(calls)) calls = calls.results || calls.data || [];
  const live = calls.filter((c) => c && c.status === 'in-progress');
  const c = live[0];
  if (!c) return { active: false };
  return {
    active: true,
    callId: c.id || null,
    startedAt: c.startedAt || c.createdAt || null,
    type: c.type || null,
  };
}

return run().then((out) => [{ json: out }]);
"""


def js_check(js: str, label: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
    proc = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{label}: failed node --check:\n{proc.stderr[:1200]}")


def main() -> int:
    src = json.loads(CHAT.read_text())
    tpl = {n["type"]: n for n in src["nodes"]}

    def node(kind, name, nid, pos, **params):
        n = copy.deepcopy(tpl[kind])
        n["name"] = name
        n["id"] = nid
        n["position"] = pos
        if params:
            n["parameters"].update(params)
        return n

    for label, js in (("Resolve Token", RESOLVE_TOKEN_JS), ("Query Vapi Calls", QUERY_VAPI_JS)):
        js_check(js, label)

    nodes = [
        node("n8n-nodes-base.webhook", "Call State Webhook", "cs-0001", [0, 300],
             httpMethod="POST", path="call/state", responseMode="responseNode", options={}),
        node("n8n-nodes-base.code", "Resolve Token", "cs-0002", [220, 300],
             jsCode=RESOLVE_TOKEN_JS),
        node("n8n-nodes-base.if", "Token OK?", "cs-0003", [440, 300]),
        node("n8n-nodes-base.code", "Query Vapi Calls", "cs-0004", [660, 200],
             jsCode=QUERY_VAPI_JS),
        node("n8n-nodes-base.respondToWebhook", "Respond State", "cs-0005", [880, 200],
             respondWith="json",
             responseBody="={{ { active: $json.active === true, callId: $json.callId ?? null, "
                          "startedAt: $json.startedAt ?? null, type: $json.type ?? null, "
                          "reason: $json.reason ?? null } }}",
             options={"responseCode": 200}),
        node("n8n-nodes-base.respondToWebhook", "Respond Unauthorized", "cs-0006", [660, 420],
             respondWith="json", responseBody="={{ { active: false, reason: 'unauthorized' } }}",
             options={"responseCode": 401}),
    ]
    # webhook id (stable per workflow so n8n keeps the same registration)
    nodes[0]["webhookId"] = "c5a1e9d2-0000-4c55-9d10-callstate01"

    # IF: uid must be a non-empty string
    cond = nodes[2]["parameters"]["conditions"]
    cond["conditions"][0]["leftValue"] = "={{ $json.uid }}"
    cond["conditions"][0]["rightValue"] = ""
    cond["conditions"][0]["operator"] = {"type": "string", "operation": "notEmpty"}

    connections = {
        "Call State Webhook": {"main": [[{"node": "Resolve Token", "type": "main", "index": 0}]]},
        "Resolve Token": {"main": [[{"node": "Token OK?", "type": "main", "index": 0}]]},
        "Token OK?": {"main": [
            [{"node": "Query Vapi Calls", "type": "main", "index": 0}],
            [{"node": "Respond Unauthorized", "type": "main", "index": 0}],
        ]},
        "Query Vapi Calls": {"main": [[{"node": "Respond State", "type": "main", "index": 0}]]},
    }

    wf = {"name": "Call State (is a Vapi call still open?)", "id": "call-state-001",
          "nodes": nodes, "connections": connections,
          "settings": {"executionOrder": "v1"}}

    names = [n["name"] for n in nodes]
    assert len(names) == len(set(names))
    ids = [n["id"] for n in nodes]
    assert len(ids) == len(set(ids)), "duplicate node ids"
    for src_name, conn in connections.items():
        for out in conn["main"]:
            for b in out:
                assert b["node"] in names, f"dangling target {b['node']}"

    WF_PATH.write_text(json.dumps(wf, indent=1) + "\n")
    print(f"built {WF_PATH.name}: {len(nodes)} nodes, jsCode node --check clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
