#!/usr/bin/env python3
"""Generate backend/n8n/workflows/invoice-template-preview.json (T4).

One workflow, two webhooks:
  GET  /webhook/invoice-template-preview  — HMAC 'template-preview' scoped:
       renders every active catalog template side by side as swipeable cards
       (CSS scroll-snap), each with the company's REAL branding (logo, colors,
       GST/PST lines) on a clearly-marked SAMPLE invoice, and a
       "Use this style" form button.
  POST /webhook/invoice-template-choose  — HMAC 'template-choose' scoped:
       validates the template key against the catalog and writes
       company_profile.invoice_template_key, then confirms.

GET never mutates. Node shapes (webhook/if/respond) are cloned from the
proven invoice-review.json so they match the live n8n version. miniMustache
is embedded into the page builder (n8n Code nodes import nothing).

Usage: python3 backend/n8n/build_invoice_template_preview.py
Idempotent by regeneration: the file is always rebuilt from scratch.
"""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WF_PATH = ROOT / "backend" / "n8n" / "workflows" / "invoice-template-preview.json"
REVIEW = ROOT / "backend" / "n8n" / "workflows" / "invoice-review.json"
MUSTACHE_SRC = (ROOT / "backend" / "templates" / "mustache_mini.js").read_text()

PG_CREDS = {"postgres": {"id": "YOUR_POSTGRES_CREDENTIALS_ID", "name": "Supabase PostgreSQL"}}

VERIFY_PREVIEW_JS = """// Verify the template-preview signature: `${company}.template-preview.${exp}`.
const crypto = require('crypto');
const q = $input.first().json.query || {};
const secret = $env.AUTH_TOKEN_SECRET || '';
const company = String(q.company || '');
const exp = String(q.exp || '');
const sig = String(q.sig || '');
let ok = false;
if (secret && company && exp && sig) {
  const expected = crypto.createHmac('sha256', secret).update(`${company}.template-preview.${exp}`).digest('base64url');
  const a = Buffer.from(sig); const b = Buffer.from(expected);
  if (a.length === b.length && crypto.timingSafeEqual(a, b) && Number(exp) * 1000 > Date.now()) ok = true;
}
return [{ json: { ok, company } }];
"""

VERIFY_CHOOSE_JS = """// Verify the template-choose signature: `${company}.template-choose.${exp}`.
// template comes from the form body; company/exp/sig from the query string.
const crypto = require('crypto');
const j = $input.first().json;
const q = j.query || {};
const b = j.body || {};
const secret = $env.AUTH_TOKEN_SECRET || '';
const company = String(b.company ?? q.company ?? '');
const exp = String(b.exp ?? q.exp ?? '');
const sig = String(b.sig ?? q.sig ?? '');
const template = String(b.template || '');
let ok = false;
if (secret && company && exp && sig && template) {
  const expected = crypto.createHmac('sha256', secret).update(`${company}.template-choose.${exp}`).digest('base64url');
  const a = Buffer.from(sig); const e = Buffer.from(expected);
  if (a.length === e.length && crypto.timingSafeEqual(a, e) && Number(exp) * 1000 > Date.now()) ok = true;
}
return [{ json: { ok, company, template } }];
"""

LOAD_SQL = """SELECT cp.id AS company_id, cp.company_name, cp.street_address, cp.city,
       cp.province, cp.postal_code, cp.phone, cp.gst_reg_number, cp.pst_reg_number,
       cp.brand_primary_color, cp.logo_data, cp.logo_content_type,
       cp.payment_instructions, cp.gst_rate, cp.retention_rate,
       COALESCE(cp.invoice_template_key, 'classic') AS selected_key,
       (SELECT json_agg(json_build_object('key', t.key, 'display_name', t.display_name,
                        'description', t.description, 'html', t.html) ORDER BY t.key)
          FROM document_templates t WHERE t.is_active) AS templates
  FROM company_profile cp
 WHERE cp.id = $1::smallint;"""

SET_SQL = """WITH upd AS (
  UPDATE company_profile cp
     SET invoice_template_key = btrim($1), updated_at = now()
   WHERE cp.id = $2::smallint
     AND EXISTS (SELECT 1 FROM document_templates t WHERE t.key = btrim($1) AND t.is_active)
  RETURNING cp.company_name, COALESCE(cp.invoice_template_key, 'classic') AS invoice_template
)
SELECT 'UPDATED' AS outcome, upd.company_name, upd.invoice_template AS template FROM upd
UNION ALL
SELECT 'INVALID_TEMPLATE', NULL, NULL WHERE NOT EXISTS (SELECT 1 FROM upd);"""

BUILD_PAGE_JS = """// Build the side-by-side, swipeable template preview page. Every card
// renders its catalog template through miniMustache with the company's REAL
// branding on a clearly-marked SAMPLE invoice, plus a tap-to-choose form.
""" + MUSTACHE_SRC + """
const row = $input.first().json;
const crypto = require('crypto');
const money = (v) => Number(v ?? 0).toLocaleString('en-CA', { style: 'currency', currency: 'CAD' });
// \x26 = '&' itself, so the entities below can never be mangled in transit
const esc = (s) => String(s).replace(/&/g, '\x26amp;').replace(/</g, '\x26lt;').replace(/>/g, '\x26gt;').replace(/"/g, '\x26quot;');
const gstRate = Number(row.gst_rate ?? 0.05);
const holdRate = Number(row.retention_rate ?? 0.1);
const net = 25000;
const dueDate = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10);
const data = {
  brand_primary_color: row.brand_primary_color || '#1a3a5c',
  company_name: row.company_name || 'Ireh Construction',
  company_address: [row.street_address, row.city, `${row.province ?? ''} ${row.postal_code ?? ''}`].filter(Boolean).join(', '),
  company_phone: row.phone || '',
  gst_reg_number: row.gst_reg_number || '',
  pst_reg_number: row.pst_reg_number || '',
  logo_data_uri: row.logo_data && row.logo_content_type ? `data:${row.logo_content_type};base64,${row.logo_data}` : '',
  invoice_number: 'SAMPLE',
  issued_date: new Date().toISOString().slice(0, 10),
  due_date: dueDate,
  invoice_type_label: 'Progress billing — 25% of contract value (' + money(100000) + ')',
  project_name: 'Sample Project',
  bill_to_name: 'Sample Customer',
  bill_to_address: '123 Sample Street<br>Vancouver, BC',
  line_items: [{ position: 1, description: 'Progress billing — 25% of contract value (' + money(100000) + ')', amount: money(net) }],
  net_amount: money(net),
  gst_label: 'GST',
  gst_amount: money(net * gstRate),
  pst_amount: 0,
  amount_due: money(net * (1 + gstRate)),
  holdback_amount: money(net * holdRate),
  holdback_label: `Holdback (${Math.round(holdRate * 100)}% retained)`,
  payment_instructions: (row.payment_instructions || '').split('\\n').filter((s) => s.trim().length > 0).join('<br>'),
};
const base = $env.PUBLIC_BASE_URL || 'https://n8n2.ordrnow.com';
const secret = $env.AUTH_TOKEN_SECRET || '';
const company = String(row.company_id ?? 1);
const exp = Math.floor(Date.now() / 1000) + 7 * 86400;
const sig = crypto.createHmac('sha256', secret).update(`${company}.template-choose.${exp}`).digest('base64url');
const chooseBase = `${base}/webhook/invoice-template-choose?company=${encodeURIComponent(company)}&exp=${exp}&sig=${encodeURIComponent(sig)}`;
const templates = Array.isArray(row.templates) ? row.templates : [];
const cards = templates.map((t) => {
  const html = miniMustache(t.html || '', data);
  const cur = (row.selected_key || 'classic') === t.key;
  return `<section class="card${cur ? ' current' : ''}">
    <div class="card-head">
      <div><h2>${esc(t.display_name)}</h2><p>${esc(t.description || '')}</p></div>
      ${cur ? '<span class="badge">Current style</span>' : ''}
    </div>
    <div class="frame"><iframe srcdoc="${esc(html)}" title="${esc(t.display_name)}"></iframe></div>
    <form class="choose" method="post" action="${chooseBase}">
      <input type="hidden" name="template" value="${esc(t.key)}">
      <button type="submit"${cur ? ' disabled' : ''}>${cur ? 'In use' : 'Use this style'}</button>
    </form>
  </section>`;
}).join('');
const page = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invoice styles — ${esc(data.company_name)}</title>
<style>
  :root { --brand: ${row.brand_primary_color || '#1a3a5c'}; }
  body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; margin: 0; background: #0f172a; color: #f8fafc; }
  .head { padding: 18px 16px 10px; }
  .head h1 { font-size: 20px; margin: 0 0 6px; }
  .head p { color: #94a3b8; font-size: 13px; margin: 0; line-height: 1.5; }
  .rail { display: flex; overflow-x: auto; scroll-snap-type: x mandatory;
          gap: 14px; padding: 4px 16px 24px; -webkit-overflow-scrolling: touch; }
  .card { flex: 0 0 86%; max-width: 400px; scroll-snap-align: center; background: #1e293b;
           border-radius: 12px; padding: 12px; border: 1px solid #334155; }
  .card.current { border-color: var(--brand); }
  .card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; min-height: 52px; }
  .card-head h2 { font-size: 16px; margin: 0; }
  .card-head p { color: #94a3b8; font-size: 11px; margin: 4px 0 0; line-height: 1.4; }
  .badge { background: var(--brand); color: #fff; font-size: 10px; border-radius: 999px;
           padding: 4px 8px; white-space: nowrap; }
  .frame { width: 100%; height: 560px; overflow: hidden; border-radius: 8px;
           background: #fff; margin-top: 8px; }
  .frame iframe { width: 800px; height: 1160px; border: 0; transform: scale(0.485);
                  transform-origin: top left; }
  .choose button { width: 100%; margin-top: 10px; padding: 12px; font-size: 15px; font-weight: 600;
                    border: 0; border-radius: 8px; background: var(--brand); color: #fff; }
  .choose button:disabled { background: #475569; }
</style></head><body>
<div class="head">
  <h1>Invoice styles</h1>
  <p>Swipe to compare. Tap "Use this style" to switch — only NEW invoices change;
     issued ones keep their original look. (Sample data with your real branding.)</p>
</div>
<div class="rail">${cards}</div>
</body></html>`;
return [{ json: { html: page } }];
"""

CHOOSE_PAGE_JS = """// Confirmation page after a tap-to-choose POST. Hands control back to the
// app: an explicit "Back to the app" button (a click is always allowed) plus
// a best-effort auto-redirect to the app scheme.
const r = $input.first().json || {};
// Return-to-app: an Android intent URL goes to the installed app by package
// + component (the app declares NO custom scheme). Chrome allows this from a
// user tap; if the app is missing the browser falls back to S.browser_fallback_url.
const APP_RETURN = 'personalagent://app';  // declared in the app manifest
// Fallback for phones still running the older apk (before the scheme existed):
// a component intent launches the app by package+activity on any Chrome.
const APP_INTENT = 'intent://app#Intent;package=com.ordrnow.personal_agent_mobile;'
  + 'component=com.ordrnow.personal_agent_mobile/.MainActivity;'
  + 'S.browser_fallback_url=https%3A%2F%2Fn8n2.ordrnow.com%2F;end';
// \x26 = '&', so the entities can never be mangled in transit
const esc = (s) => String(s).replace(/&/g, '\x26amp;').replace(/</g, '\x26lt;').replace(/>/g, '\x26gt;');
const ok = r.outcome === 'UPDATED';
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invoice style</title>
<style>
  body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; background: #0f172a;
         color: #f8fafc; display: flex; min-height: 100vh; align-items: center; justify-content: center; margin: 0; }
  .box { background: #1e293b; padding: 26px 28px; border-radius: 12px; text-align: center; max-width: 420px; }
  h1 { font-size: 20px; margin: 0 0 8px; }
  p { color: #94a3b8; font-size: 14px; margin: 0 0 18px; line-height: 1.6; }
  .note { color: #64748b; font-size: 11px; margin: 10px 0 0; }
  .btn { display: inline-block; background: #2563eb; color: #fff; text-decoration: none;
         padding: 12px 22px; border-radius: 8px; font-weight: 600; font-size: 15px; }
</style></head><body><div class="box">
<h1>${ok ? 'Style set: ' + esc(r.template) : 'Unknown style'}</h1>
<p>${ok
  ? 'New invoices will use the ' + esc(r.template) + ' layout. Already-issued invoices keep their original look.'
  : 'That style is not in the catalog. Go back and pick Classic, Modern or Compact.'}</p>
<a class="btn" id="backApp" href="${APP_RETURN}">Back to the app</a>
<p class="note">If the button does nothing, the app is not installed on this device.</p>
</div>
<script>
  (function () {
    var go = function (u) { try { window.location.href = u; } catch (e) {} };
    var btn = document.getElementById('backApp');
    if (btn) btn.addEventListener('click', function () {
      // if the scheme opened nothing (old apk), fall back to the component intent
      setTimeout(function () { if (!document.hidden) go(${JSON.stringify(APP_INTENT)}); }, 1200);
    });
    ${ok ? `// best-effort auto-return: scheme first, component intent second
    setTimeout(function () { if (!document.hidden) go(${JSON.stringify(APP_RETURN)}); }, 1400);
    setTimeout(function () { if (!document.hidden) go(${JSON.stringify(APP_INTENT)}); }, 3000);` : ''}
  })();
</script>
</body></html>`;
return [{ json: { html } }];
"""


def js_check(js: str, label: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
    proc = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{label}: failed node --check:\n{proc.stderr[:1200]}")


def main() -> int:
    review = json.loads(REVIEW.read_text())
    tpl = {n["type"]: n for n in review["nodes"]}
    id_counter = iter(range(1, 100))

    def nid() -> str:
        return f"tpl-{next(id_counter):04d}"

    def webhook(path, method, name, wid, x, y):
        n = copy.deepcopy(tpl["n8n-nodes-base.webhook"])
        n["parameters"]["path"] = path
        n["parameters"]["httpMethod"] = method
        n["webhookId"] = wid
        n["id"], n["name"], n["position"] = nid(), name, [x, y]
        return n

    def code(name, js, x, y):
        js_check(js, name)
        return {"parameters": {"jsCode": js}, "id": nid(),
                "name": name, "type": "n8n-nodes-base.code",
                "typeVersion": 2, "position": [x, y]}

    def ifnode(name, x, y):
        n = copy.deepcopy(tpl["n8n-nodes-base.if"])
        n["id"], n["name"], n["position"] = nid(), name, [x, y]
        return n

    def postgres(name, query, repl, x, y, always=False):
        params = {"operation": "executeQuery", "query": query}
        if repl is not None:
            params["options"] = {"queryReplacement": repl}
        n = {"parameters": params, "id": nid(), "name": name,
             "type": "n8n-nodes-base.postgres", "typeVersion": 2.5,
             "position": [x, y], "credentials": copy.deepcopy(PG_CREDS)}
        if always:
            n["alwaysOutputData"] = True
        return n

    def respond(name, ok_200, x, y):
        n = copy.deepcopy(tpl["n8n-nodes-base.respondToWebhook"])
        n["parameters"]["options"]["responseCode"] = 200 if ok_200 else 400
        n["id"], n["name"], n["position"] = nid(), name, [x, y]
        return n

    nodes = [
        webhook("invoice-template-preview", "GET", "Preview Webhook", "a1f3c0de-0000-4a5b-9c1d-tplprev0001", 0, 300),
        code("Verify Preview Sig", VERIFY_PREVIEW_JS, 220, 300),
        ifnode("Preview Sig OK?", 440, 300),
        postgres("Load Company + Catalog", LOAD_SQL, "={{ [Number($json.company) || 1] }}", 660, 200),
        code("Build Preview Page", BUILD_PAGE_JS, 880, 200),
        respond("Respond Preview Page", True, 1100, 200),
        respond("Respond Preview Invalid", False, 660, 420),
        webhook("invoice-template-choose", "POST", "Choose Webhook", "b2e4d1ef-0000-4a5b-9c1d-tplcho0001", 0, 700),
        code("Verify Choose Sig", VERIFY_CHOOSE_JS, 220, 700),
        ifnode("Choose Sig OK?", 440, 700),
        postgres("Set Chosen Template", SET_SQL, "={{ [$json.template, Number($json.company) || 1] }}", 660, 600, always=True),
        code("Build Choice Page", CHOOSE_PAGE_JS, 880, 600),
        respond("Respond Choice Page", True, 1100, 600),
        respond("Respond Choose Invalid", False, 660, 820),
    ]

    connections = {
        "Preview Webhook": {"main": [[{"node": "Verify Preview Sig", "type": "main", "index": 0}]]},
        "Verify Preview Sig": {"main": [[{"node": "Preview Sig OK?", "type": "main", "index": 0}]]},
        "Preview Sig OK?": {"main": [
            [{"node": "Load Company + Catalog", "type": "main", "index": 0}],
            [{"node": "Respond Preview Invalid", "type": "main", "index": 0}],
        ]},
        "Load Company + Catalog": {"main": [[{"node": "Build Preview Page", "type": "main", "index": 0}]]},
        "Build Preview Page": {"main": [[{"node": "Respond Preview Page", "type": "main", "index": 0}]]},
        "Choose Webhook": {"main": [[{"node": "Verify Choose Sig", "type": "main", "index": 0}]]},
        "Verify Choose Sig": {"main": [[{"node": "Choose Sig OK?", "type": "main", "index": 0}]]},
        "Choose Sig OK?": {"main": [
            [{"node": "Set Chosen Template", "type": "main", "index": 0}],
            [{"node": "Respond Choose Invalid", "type": "main", "index": 0}],
        ]},
        "Set Chosen Template": {"main": [[{"node": "Build Choice Page", "type": "main", "index": 0}]]},
        "Build Choice Page": {"main": [[{"node": "Respond Choice Page", "type": "main", "index": 0}]]},
    }

    wf = {"name": "Invoice Template Preview", "id": "tplPreview-001",
          "nodes": nodes, "connections": connections,
          "settings": {"executionOrder": "v1"}}

    names = [n["name"] for n in wf["nodes"]]
    assert len(names) == len(set(names)), "duplicate node names"
    known = set(names)
    for src, conn in connections.items():
        assert src in known, f"dangling source {src}"
        for out in conn["main"]:
            for b in out:
                assert b["node"] in known, f"dangling target {b['node']}"

    WF_PATH.write_text(json.dumps(wf, indent=1) + "\n")
    print(f"built {WF_PATH.name}: {len(nodes)} nodes, all jsCode node --check clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
