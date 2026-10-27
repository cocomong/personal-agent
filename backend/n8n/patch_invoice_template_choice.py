#!/usr/bin/env python3
"""Idempotent gateway patch: the invoice-template CHOICE feature (T5).

- new tool `list_invoice_templates`: catalog + current style, and pushes the
  side-by-side preview page to the PM's registered phones (FCM open_url,
  same proven helper pattern as Push Invoice Review, wrapped in an async run()
  so node --check stays green).
- new tool `set_invoice_template`: validated switch (classic|modern|compact).
- complete_onboarding gains an optional invoice_template arg — and its
  queryReplacement is FIXED (it passed only 3 of 10 args to the $1..$10 SQL,
  so the billing-details capture added 2026-09-05 has been broken since).
- get_onboarding_status reports the current invoice style.
- formatter cases for both new tools + onboarding replies mention the style.
- vapi_assistant.json: two new tool defs, complete_onboarding param, prompt
  section INVOICE STYLES.

Usage (repo root): python3 backend/n8n/patch_invoice_template_choice.py
Run AFTER patch_invoice_template.py (same day's catalog feature).
"""
import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GATEWAY = ROOT / "backend" / "n8n" / "workflows" / "voice-gateway.json"
VAPI = ROOT / "backend" / "vapi_assistant.json"
FORMAT_NODE = "Format Spoken Result"

LIST_SQL = """SELECT COALESCE(cp.invoice_template_key, 'classic') AS current_key,
       (SELECT json_agg(json_build_object('key', t.key, 'name', t.display_name,
                        'description', t.description) ORDER BY t.key)
          FROM document_templates t WHERE t.is_active) AS templates,
       (SELECT count(*) FROM device_tokens) AS device_count
  FROM company_profile cp
 WHERE cp.id = 1;"""

SET_SQL = """WITH upd AS (
  UPDATE company_profile cp
     SET invoice_template_key = CASE WHEN btrim($1) = 'classic' THEN NULL ELSE btrim($1) END,
         updated_at = now()
   WHERE cp.id = 1
     AND (btrim($1) = 'classic' OR EXISTS (SELECT 1 FROM document_templates t
                                             WHERE t.key = btrim($1) AND t.is_active))
  RETURNING COALESCE(cp.invoice_template_key, 'classic') AS template
)
SELECT 'UPDATED' AS outcome, upd.template FROM upd
UNION ALL
SELECT 'INVALID_TEMPLATE', NULL WHERE NOT EXISTS (SELECT 1 FROM upd);"""

ONBOARDING_SQL = """UPDATE company_profile
   SET company_name       = COALESCE(NULLIF($1, ''), company_name),
       pm_name            = COALESCE(NULLIF($2, ''), pm_name),
       pm_preferred_name  = COALESCE(NULLIF($3, ''), pm_preferred_name),
       street_address     = COALESCE(NULLIF($4, ''), street_address),
       city               = COALESCE(NULLIF($5, ''), city),
       province           = COALESCE(NULLIF($6, ''), province),
       postal_code        = COALESCE(NULLIF($7, ''), postal_code),
       gst_reg_number     = COALESCE(NULLIF($8, ''), gst_reg_number),
       pst_reg_number     = COALESCE(NULLIF($9, ''), pst_reg_number),
       payment_instructions = COALESCE(NULLIF($10, ''), payment_instructions),
       invoice_template_key = CASE
         WHEN NULLIF(btrim($11), '') IS NULL THEN invoice_template_key
         WHEN btrim($11) = 'classic' THEN NULL
         WHEN EXISTS (SELECT 1 FROM document_templates t
                      WHERE t.key = btrim($11) AND t.is_active) THEN btrim($11)
         ELSE invoice_template_key END,
       setup_completed_at = COALESCE(setup_completed_at, now()),
       updated_at         = now()
 WHERE id = 1
RETURNING company_name, pm_name, pm_preferred_name,
          COALESCE(invoice_template_key, 'classic') AS invoice_template,
          (SELECT count(*) FROM workers WHERE active) AS worker_count;"""

# FIX: the old replacement passed only 3 args to the $1..$10 SQL.
ONBOARDING_REPL = (
    "={{ ["
    "$('Normalize Tool Call').first().json.toolArgs.company_name ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.pm_name ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.preferred_name ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.street_address ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.city ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.province ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.postal_code ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.gst_reg_number ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.pst_reg_number ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.payment_instructions ?? null, "
    "$('Normalize Tool Call').first().json.toolArgs.invoice_template ?? null] }}"
)

ONBOARDING_STATUS_SQL = """SELECT cp.company_name,
       cp.pm_name,
       cp.pm_preferred_name,
       (cp.setup_completed_at IS NOT NULL) AS setup_completed,
       COALESCE(cp.invoice_template_key, 'classic') AS invoice_template,
       (SELECT count(*) FROM workers WHERE active) AS worker_count
  FROM company_profile cp WHERE id = 1;"""

PUSH_DEVICES_SQL = ("SELECT token FROM device_tokens UNION ALL "
                    "SELECT NULL::text WHERE NOT EXISTS (SELECT 1 FROM device_tokens);")

FCM_HELPERS = """
function b64url(s) { return s.replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, ''); }
function splitUrl(u) { const m = u.match(/^https?:\\/\\/([^/]+)(\\/[^?#]*)?(\\?[^#]*)?/); return { hostname: m[1], path: (m[2] || '/') + (m[3] || '') }; }
function httpsRequest(options, body) {
  return new Promise((resolve, reject) => {
    const req = require('https').request(options, (res) => {
      let data = '';
      res.on('data', (c) => (data += c));
      res.on('end', () => resolve({ status: res.statusCode, body: data }));
    });
    req.on('error', reject); req.write(body); req.end();
  });
}
async function getAccessToken(sa, crypto) {
  const now = Math.floor(Date.now() / 1000);
  const head = b64url(Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64'));
  const claim = b64url(Buffer.from(JSON.stringify({ iss: sa.client_email, scope: 'https://www.googleapis.com/auth/firebase.messaging', aud: sa.token_uri, iat: now, exp: now + 3600 })).toString('base64'));
  const jwt = head + '.' + claim + '.' + b64url(crypto.createSign('RSA-SHA256').update(head + '.' + claim).sign(sa.private_key).toString('base64'));
  const u = splitUrl(sa.token_uri);
  const resp = await httpsRequest({ method: 'POST', hostname: u.hostname, path: u.path, headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
    'grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=' + encodeURIComponent(jwt));
  const parsed = JSON.parse(resp.body);
  if (!parsed.access_token) throw new Error('token exchange failed (' + resp.status + '): ' + resp.body.slice(0, 200));
  return parsed.access_token;
}
async function sendFcm(accessToken, projectId, token, data) {
  const u = splitUrl('https://fcm.googleapis.com/v1/projects/' + projectId + '/messages:send');
  const resp = await httpsRequest({ method: 'POST', hostname: u.hostname, path: u.path,
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + accessToken } },
    JSON.stringify({ message: { token, data } }));
  if (resp.status >= 400) throw new Error('FCM HTTP ' + resp.status + ': ' + resp.body.slice(0, 200));
}
"""

PUSH_JS = """// Push the invoice-style preview page (side-by-side, tap-to-choose) to every
// registered phone: data {type:'open_url', url, title, body}. Same FCM
// helpers as Push Invoice Review, wrapped in an async run() so node --check
// passes (no top-level await in the source).
async function run() {
  const crypto = require('crypto');
  const row = $('Exec: list_invoice_templates').first().json;
  const base = $env.PUBLIC_BASE_URL || 'https://n8n2.ordrnow.com';
  const secret = $env.AUTH_TOKEN_SECRET || '';
  const company = '1';
  const exp = Math.floor(Date.now() / 1000) + 7 * 86400;
  const sig = crypto.createHmac('sha256', secret).update(`${company}.template-preview.${exp}`).digest('base64url');
  const previewUrl = `${base}/webhook/invoice-template-preview?company=${company}&exp=${exp}&sig=${encodeURIComponent(sig)}`;
  const title = 'Invoice styles';
  const body = 'Compare Classic, Modern and Compact side by side, then tap to choose.';
  const tokens = $input.all().map(i => i.json).filter(r => r && r.token).map(r => r.token);
  let saRaw = String($env.FCM_SERVICE_ACCOUNT_JSON || '').trim();
  let note = '';
  if (!saRaw) {
    try {
      const file = String($env.FCM_SERVICE_ACCOUNT_FILE || '').trim();
      if (file) saRaw = require('fs').readFileSync(file, 'utf8').trim();
    } catch (e) { note = 'FCM key file read failed: ' + e.message; }
  }
  let pushed = 0;
  if (!saRaw) note = note || 'FCM not configured; push skipped';
  else if (tokens.length === 0) note = 'no registered devices';
  else {
    try {
      const sa = JSON.parse(saRaw);
      const accessToken = await getAccessToken(sa, crypto);
      let stale = 0;
      for (const token of tokens) {
        try { await sendFcm(accessToken, sa.project_id, token, { type: 'open_url', url: previewUrl, title, body }); pushed++; }
        catch (e) { stale++; }
      }
      note = 'pushed to ' + pushed + ' device(s)' + (stale ? ', ' + stale + ' stale' : '');
    } catch (e) { note = 'FCM send failed: ' + e.message; }
  }
  return { ...row, preview_url: previewUrl, pushed, note };
}
return run().then((r) => [{ json: r }]);
""" + FCM_HELPERS

FORMATTER_CASES = """  case 'list_invoice_templates': {
    const r = dbRow || {};
    const list = Array.isArray(r.templates) ? r.templates : [];
    const names = list.map((t) => `${t.name} (${t.key})`).join('; ');
    const cur = r.current_key || 'classic';
    if (r.note === 'no registered devices' || (r.note || '').indexOf('not configured') !== -1) {
      spoken = `Your invoices use the ${cur} style. The others: ${names}. I could not push the preview to a phone - preview link: ${r.preview_url || ''}`;
    } else {
      spoken = `Your invoices use the ${cur} style. Available: ${names}. I sent the styles to your phone - swipe to compare them side by side and tap to choose.`;
    }
    break;
  }
  case 'set_invoice_template': {
    const r = dbRow || {};
    spoken = r.outcome === 'UPDATED'
      ? `Done - invoices now use the ${r.template} style.`
      : 'That is not one of the invoice styles. Say classic, modern or compact - or ask me to list the styles.';
    break;
  }
  default:"""

PROMPT_SECTION = """

## INVOICE STYLES (TEMPLATE PICKER)
- Catalog: classic (traditional bordered layout), modern (bold color-band header), compact (condensed one-pager). Every style carries the logo, the GST/PST lines and the totals.
- During first-run setup, right after payment details, offer the style: "Which invoice look do you want - Classic, Modern or Compact? I can show you all three on your phone." Record the answer with complete_onboarding(invoice_template). Skipped = classic.
- "show me the invoice styles" -> list_invoice_templates (it pushes a side-by-side preview to the PM's phone; they can tap to choose). "switch my invoices to modern/compact/classic" -> set_invoice_template.
- Never invent styles beyond classic, modern and compact. If the tool says INVALID_TEMPLATE, spell the three options. Changing the style only affects NEW invoices - issued ones keep their stored look."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_invoice_templates",
            "description": (
                "Lists the available invoice layout styles (classic, modern, compact), says "
                "which one the company currently uses, and pushes a side-by-side preview page "
                "to the PM's phone so they can compare and tap-to-choose."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "server": {"url": "https://n8n2.ordrnow.com/webhook/voice/gateway", "timeoutSeconds": 15},
    },
    {
        "type": "function",
        "function": {
            "name": "set_invoice_template",
            "description": (
                "Sets the company's invoice layout style. template must be one of: classic, "
                "modern, compact. Only affects NEW invoices; issued ones keep their stored look. "
                "Outcomes: UPDATED / INVALID_TEMPLATE."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template": {"type": "string",
                                 "description": "classic, modern or compact"},
                },
                "required": ["template"],
            },
        },
        "server": {"url": "https://n8n2.ordrnow.com/webhook/voice/gateway", "timeoutSeconds": 15},
    },
]


def node_js_check(js: str, label: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        path = f.name
    proc = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{label}: jsCode failed node --check:\n{proc.stderr[:1200]}")


def max_gate_id(wf: dict) -> int:
    ids = [int(m.group(1)) for n in wf["nodes"]
           if (m := re.match(r"gate-(\d+)$", n.get("id", "")))]
    return max(ids) if ids else 0


def postgres_node(name: str, node_id: str, query: str, repl, y: int,
                  always_output: bool = False) -> dict:
    params: dict = {"operation": "executeQuery", "query": query}
    if repl is not None:
        params["options"] = {"queryReplacement": repl}
    node = {
        "parameters": params,
        "id": node_id, "name": name, "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5, "position": [960, y],
        "credentials": {"postgres": {"id": "YOUR_POSTGRES_CREDENTIALS_ID",
                                     "name": "Supabase PostgreSQL"}},
    }
    if always_output:
        node["alwaysOutputData"] = True
    return node


def add_rule(wf: dict, action: str) -> int:
    router = next(n for n in wf["nodes"] if n["name"] == "Actions Sub-Router")
    rules = router["parameters"]["rules"]["values"]
    rule = copy.deepcopy(rules[-1])
    rule["conditions"]["conditions"][0]["rightValue"] = action
    rule["outputKey"] = action
    rules.append(rule)
    main = wf["connections"]["Actions Sub-Router"]["main"]
    if main[-1][0]["node"] != FORMAT_NODE:
        raise SystemExit("router fallback not last — aborting")
    return len(rules) - 1  # output index for this rule


def main() -> int:
    wf = json.loads(GATEWAY.read_text())
    vapi = json.loads(VAPI.read_text())
    nodes = {n["name"]: n for n in wf["nodes"]}

    # 1) two new tools
    added = []
    if "Exec: list_invoice_templates" not in nodes:
        nid = f"gate-{max_gate_id(wf) + 1:04d}"
        wf["nodes"].append(postgres_node(
            "Exec: list_invoice_templates", nid, LIST_SQL, "={{ [] }}", 3600,
            always_output=True))
        wf["nodes"].append(postgres_node(
            "Exec: template_push_devices", f"gate-{max_gate_id(wf) + 1:04d}",
            PUSH_DEVICES_SQL, None, 3600))
        push = {
            "parameters": {"jsCode": PUSH_JS},
            "id": f"gate-{max_gate_id(wf) + 1:04d}",
            "name": "Push Template Preview",
            "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1200, 3600],
        }
        wf["nodes"].append(push)
        node_js_check(PUSH_JS, "Push Template Preview")

        i1 = add_rule(wf, "list_invoice_templates")
        wf["connections"]["Actions Sub-Router"]["main"].insert(
            i1, [{"node": "Exec: list_invoice_templates", "type": "main", "index": 0}])
        wf["connections"]["Exec: list_invoice_templates"] = {"main": [[
            {"node": "Exec: template_push_devices", "type": "main", "index": 0}]]}
        wf["connections"]["Exec: template_push_devices"] = {"main": [[
            {"node": "Push Template Preview", "type": "main", "index": 0}]]}
        wf["connections"]["Push Template Preview"] = {"main": [[
            {"node": FORMAT_NODE, "type": "main", "index": 0}]]}
        added.append("list_invoice_templates (+push chain)")
    else:
        print("list_invoice_templates: already present")

    if "Exec: set_invoice_template" not in nodes:
        wf["nodes"].append(postgres_node(
            "Exec: set_invoice_template", f"gate-{max_gate_id(wf) + 1:04d}",
            SET_SQL, "={{ [($json.toolArgs.template ?? 'classic')] }}", 3820,
            always_output=True))
        i2 = add_rule(wf, "set_invoice_template")
        wf["connections"]["Actions Sub-Router"]["main"].insert(
            i2, [{"node": "Exec: set_invoice_template", "type": "main", "index": 0}])
        wf["connections"]["Exec: set_invoice_template"] = {"main": [[
            {"node": FORMAT_NODE, "type": "main", "index": 0}]]}
        added.append("set_invoice_template")
    else:
        print("set_invoice_template: already present")

    # 2) formatter cases for the new tools
    fmt = next(n for n in wf["nodes"] if n["name"] == FORMAT_NODE)
    code = fmt["parameters"]["jsCode"]
    if "case 'list_invoice_templates'" not in code:
        if "\n  default:" not in code:
            raise SystemExit("formatter default branch not found")
        fmt["parameters"]["jsCode"] = code.replace("\n  default:", "\n" + FORMATTER_CASES, 1)
        node_js_check(fmt["parameters"]["jsCode"], "formatter (new cases)")
        added.append("formatter cases")
    else:
        print("formatter cases: already present")

    # 3) onboarding: fix repl + add invoice_template; status reports style
    ob = nodes["Exec: complete_onboarding_profile"]
    if "$11" not in ob["parameters"]["query"]:
        ob["parameters"]["query"] = ONBOARDING_SQL
        ob["parameters"]["options"]["queryReplacement"] = ONBOARDING_REPL
        added.append("complete_onboarding (repl FIX + invoice_template)")
    else:
        print("complete_onboarding: already patched")

    st = nodes["Exec: get_onboarding_status"]
    if "invoice_template" not in st["parameters"]["query"]:
        st["parameters"]["query"] = ONBOARDING_STATUS_SQL
        added.append("get_onboarding_status (style)")
    else:
        print("get_onboarding_status: already patched")

    # formatter: onboarding replies mention the style
    code = fmt["parameters"]["jsCode"]
    old = "worker${dbRow.worker_count === 1 ? '' : 's'} on file. Anything else?`"
    new = ("worker${dbRow.worker_count === 1 ? '' : 's'} on file, "
           "invoices set to the ${dbRow.invoice_template || 'classic'} style. Anything else?`")
    if old in code:
        fmt["parameters"]["jsCode"] = code.replace(old, new, 1)
        added.append("complete_onboarding reply")
    code = fmt["parameters"]["jsCode"]
    old2 = "active worker${dbRow.worker_count === 1 ? '' : 's'} on file.`"
    new2 = "active worker${dbRow.worker_count === 1 ? '' : 's'} on file. Invoices use the ${dbRow.invoice_template || 'classic'} style.`"
    if old2 in code:
        fmt["parameters"]["jsCode"] = code.replace(old2, new2, 1)
        added.append("get_onboarding_status reply")
    node_js_check(fmt["parameters"]["jsCode"], "formatter (after onboarding edits)")

    # 4) vapi: tools + param + prompt
    names = [t["function"]["name"] for t in vapi["tools"]]
    for tool in TOOLS:
        if tool["function"]["name"] not in names:
            vapi["tools"].append(tool)
            added.append(f"vapi tool {tool['function']['name']}")
    co = next(t for t in vapi["tools"] if t["function"]["name"] == "complete_onboarding")
    props = co["function"]["parameters"]["properties"]
    if "invoice_template" not in props:
        props["invoice_template"] = {
            "type": "string",
            "description": "Invoice layout style: classic, modern or compact (optional; default classic)",
        }
        co["function"]["description"] += (
            " Optionally also the invoice style via invoice_template (classic|modern|compact);"
            " when offered, the PM gets a preview pushed to their phone to compare and tap-to-choose.")
        added.append("vapi complete_onboarding param")
    if "INVOICE STYLES (TEMPLATE PICKER)" not in vapi["systemPrompt"]:
        vapi["systemPrompt"] = vapi["systemPrompt"].rstrip() + PROMPT_SECTION
        added.append("vapi prompt section")

    # ---- validations ----
    names = [n["name"] for n in wf["nodes"]]
    assert len(names) == len(set(names)), "duplicate node names"
    known = set(names)
    for src, conn in wf["connections"].items():
        assert src in known, f"dangling source {src}"
        for out in conn.get("main", []):
            for b in out:
                assert b["node"] in known, f"dangling target {b['node']}"
    router = next(n for n in wf["nodes"] if n["name"] == "Actions Sub-Router")
    rules = router["parameters"]["rules"]["values"]
    main = wf["connections"]["Actions Sub-Router"]["main"]
    assert len(main) == len(rules) + 1, f"rule/output parity: {len(main)} vs {len(rules)}"
    assert main[-1][0]["node"] == FORMAT_NODE, "fallback lost"
    for action in ("list_invoice_templates", "set_invoice_template"):
        idx = next(i for i, r in enumerate(rules) if r["outputKey"] == action)
        assert main[idx][0]["node"] == f"Exec: {action}", f"{action} routing wrong"
    missing = [t["function"]["name"] for t in vapi["tools"]
               if not (t.get("server") or {}).get("url")]
    assert not missing, f"tools without server.url: {missing}"

    GATEWAY.write_text(json.dumps(wf, indent=1) + "\n")
    VAPI.write_text(json.dumps(vapi, indent=1) + "\n")
    print("added/patched:")
    for a in added:
        print("  -", a)
    print(f"gateway nodes: {len(wf['nodes'])} | router rules: {len(rules)} | vapi tools: {len(vapi['tools'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
