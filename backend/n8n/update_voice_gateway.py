#!/usr/bin/env python3
"""One-time helper: apply the Migration Plan (doc/MIGRATION_PLAN.md) edits to
backend/n8n/workflows/voice-gateway.json. Re-runnable (idempotent by node-name
lookups + action-key checks). Produces the updated workflow in place.

Changes:
  1. De-hardcode the deployment URL (-> $env.PUBLIC_BASE_URL) and brand
     colors/company name (-> company_profile fields cross-joined into lookups).
  2. Tax-aware create_invoice; reason on create_change_order; revision/validity
     on create_estimate; overtime on log_timesheet.
  3. Five new tool branches: record_payment (2 nodes), run_payroll,
     get_payroll_summary, add_worker, get_dashboard_summary.
"""
import json
from pathlib import Path

WF = Path(__file__).parent / "workflows" / "voice-gateway.json"
d = json.loads(WF.read_text())

nodes = d["nodes"]
by_name = {n["name"]: n for n in nodes}
conns = d["connections"]


def set_query(name, query, replacement):
    n = by_name[name]
    n["parameters"]["query"] = query
    n["parameters"]["options"]["queryReplacement"] = replacement


def set_code(name, js):
    by_name[name]["parameters"]["jsCode"] = js


def pg_node(id_, name, query, replacement, x, y):
    return {
        "parameters": {"operation": "executeQuery", "query": query,
                       "options": {"queryReplacement": replacement}},
        "id": id_, "name": name, "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5, "position": [x, y],
        "credentials": {"postgres": {"id": "YOUR_POSTGRES_CREDENTIALS_ID",
                                     "name": "Supabase PostgreSQL"}},
    }


def add_node_once(node):
    if not any(n["name"] == node["name"] for n in nodes):
        nodes.append(node)


def switch_case(action):
    return {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "",
                        "typeValidation": "strict"},
            "conditions": [{"leftValue": "={{ $json.action }}", "rightValue": action,
                            "operator": {"type": "string", "operation": "equals"}}],
            "combinator": "and",
        },
        "renameOutput": True,
        "outputKey": action,
    }


# ---------------------------------------------------------------------------
# 1. Branding / URL de-hardcoding
# ---------------------------------------------------------------------------
BASE = "const base = $env.PUBLIC_BASE_URL || 'https://n8n2.ordrnow.com';"

set_code("Render Estimate Approval Email", """\
const r = $input.first()?.json;
const base = $env.PUBLIC_BASE_URL || 'https://n8n2.ordrnow.com';
const company = r?.company_name ?? 'Ireh Construction';
const accent = r?.brand_accent_color ?? '#2563eb';
const success = r?.brand_success_color ?? '#16a34a';
const link = `${base}/webhook/approve-estimate?token=${r?.token ?? ''}`;
const html = `<!doctype html><html><body style='font-family:Helvetica,Arial,sans-serif;color:#1e293b'><h2 style='color:${accent}'>Approve your estimate</h2><p>Hi ${r?.customer_name ?? ''}, please review and approve the baseline estimate for <strong>${r?.title ?? ''}</strong>.</p><p><a href='${link}' style='display:inline-block;padding:10px 16px;background:${success};color:#fff;text-decoration:none;border-radius:6px'>Review & approve</a></p><p style='color:#64748b;margin-top:24px'>${company}</p></body></html>`;
return [{ json: { ...r, html } }];""")

set_code("Render Change Order Approval Email", """\
const r = $input.first()?.json;
const base = $env.PUBLIC_BASE_URL || 'https://n8n2.ordrnow.com';
const company = r?.company_name ?? 'Ireh Construction';
const accent = r?.brand_accent_color ?? '#2563eb';
const success = r?.brand_success_color ?? '#16a34a';
const link = `${base}/webhook/approve-change-order?token=${r?.token ?? ''}`;
const amount = Number(r?.cost_impact ?? 0);
const sign = amount >= 0 ? '+' : '';
const html = `<!doctype html><html><body style='font-family:Helvetica,Arial,sans-serif;color:#1e293b'><h2 style='color:${accent}'>Approve change order #${r?.change_order_number ?? ''}</h2><p>Hi ${r?.customer_name ?? ''}, please review and approve change order #${r?.change_order_number ?? ''} for <strong>${r?.project_name ?? ''}</strong>.</p><p>${r?.description ?? ''}: ${sign}$${Math.abs(amount).toLocaleString('en-US')}</p><p><a href='${link}' style='display:inline-block;padding:10px 16px;background:${success};color:#fff;text-decoration:none;border-radius:6px'>Review & approve</a></p><p style='color:#64748b;margin-top:24px'>${company}</p></body></html>`;
return [{ json: { ...r, html } }];""")

set_code("Render Invoice HTML", """\
const inv = $input.first()?.json;
const money = (v) => Number(v ?? 0).toLocaleString('en-CA', { style: 'currency', currency: 'CAD' });
const company = inv?.company_name ?? 'Ireh Construction';
const accent = inv?.brand_accent_color ?? '#2563eb';
const primary = inv?.brand_primary_color ?? '#1a3a5c';
const addressLine = [inv?.street_address, inv?.city, `${inv?.province ?? ''} ${inv?.postal_code ?? ''}`].filter(Boolean).join(', ');
const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  body { font-family: Helvetica, Arial, sans-serif; color: #1e293b; margin: 2rem; }
  .header { display: flex; justify-content: space-between; border-bottom: 2px solid ${primary}; padding-bottom: 1rem; }
  .title { font-size: 1.5rem; font-weight: 700; color: ${primary}; }
  .co { color: #64748b; font-size: .85rem; }
  .row { display: flex; justify-content: space-between; padding: .4rem 0; }
  .total { font-size: 1.3rem; font-weight: 700; border-top: 2px solid ${primary}; margin-top: 1rem; padding-top: 1rem; }
  @media print { body { margin: 0; } }
</style></head><body>
  <div class="header">
    <div><div class="title">${company}</div><div class="co">${addressLine}</div><div class="co">${inv?.phone ?? ''}</div></div>
    <div style="text-align:right"><div class="title">Invoice</div><div>${inv?.invoice_number ?? ''}</div><div>Issued: ${inv?.issued_date ?? ''}</div><div>Due: ${inv?.due_date ?? ''}</div></div>
  </div>
  <p><strong>Project:</strong> ${inv?.project_name ?? ''}</p>
  <p><strong>Customer:</strong> ${inv?.customer_name ?? ''}</p>
  <p><strong>Type:</strong> ${inv?.invoice_type ?? ''}</p>
  <div class="row"><span>Subtotal (net)</span><span>${money(inv?.net_amount)}</span></div>
  ${Number(inv?.gst_amount) ? `<div class="row"><span>GST</span><span>${money(inv?.gst_amount)}</span></div>` : ''}
  ${Number(inv?.pst_amount) ? `<div class="row"><span>PST</span><span>${money(inv?.pst_amount)}</span></div>` : ''}
  <div class="row"><span>Holdback</span><span>${money(inv?.holdback_amount)}</span></div>
  <div class="total">Total due ${money(inv?.amount_due)}</div>
</body></html>`;
return [{ json: { ...inv, invoiceHtml: html } }];""")

# Format Spoken Result: env-based base URL + 5 new action cases.
set_code("Format Spoken Result", """\
const toolCall = $('Normalize Tool Call').first().json;
const dbRow = $input.first()?.json;
const base = $env.PUBLIC_BASE_URL || 'https://n8n2.ordrnow.com';

let spoken = 'Done.';
switch (toolCall.action) {
  case 'lookup_or_create_customer':
    spoken = 'Customer ready.';
    break;
  case 'create_project':
    spoken = 'Project created.';
    break;
  case 'create_estimate':
    spoken = 'Baseline estimate recorded.';
    break;
  case 'create_change_order':
    spoken = dbRow && dbRow.id ? `Change order ${dbRow.change_order_number} recorded.` : 'Could not create change order - baseline estimate must be approved first.';
    break;
  case 'log_timesheet':
    spoken = dbRow && dbRow.id ? 'Hours logged.' : 'Worker not found - add the worker first.';
    break;
  case 'create_invoice':
    spoken = dbRow && dbRow.invoice_number ? `Draft invoice ${dbRow.invoice_number} created for $${Number(dbRow.amount_due).toLocaleString()} (incl. tax).` : 'Draft invoice created.';
    break;
  case 'send_customer_invoice':
    spoken = 'Invoice sent to the client.';
    break;
  case 'get_project_statement':
    spoken = dbRow
      ? `${dbRow.project_name} (${dbRow.customer_name}): Revised contract is $${Number(dbRow.total_revised_contract_value).toLocaleString()}, $${Number(dbRow.total_paid).toLocaleString()} collected. Outstanding balance is $${Number(dbRow.balance_remaining).toLocaleString()}.`
      : 'Project not found.';
    break;
  case 'get_estimate_approval_link':
    spoken = dbRow && dbRow.approval_token ? `Approval link ready: ${base}/webhook/approve-estimate?token=${dbRow.approval_token}` : 'Project not found.';
    break;
  case 'get_change_order_approval_link':
    spoken = dbRow && dbRow.approval_token ? `Approval link ready: ${base}/webhook/approve-change-order?token=${dbRow.approval_token}` : 'Change order not found.';
    break;
  case 'send_estimate_for_approval':
    spoken = dbRow && dbRow.email ? 'Approval link emailed to the client.' : 'Project or customer not found.';
    break;
  case 'send_change_order_for_approval':
    spoken = dbRow && dbRow.email ? 'Change order approval link emailed to the client.' : 'Change order not found.';
    break;
  case 'record_payment':
    spoken = dbRow && dbRow.invoice_number
      ? `Payment recorded. ${dbRow.invoice_number} is now ${(dbRow.status || '').toLowerCase()}; balance due $${Number(dbRow.balance_due).toLocaleString()}.`
      : 'Invoice not found.';
    break;
  case 'run_payroll':
    spoken = dbRow && dbRow.run_id
      ? `Payroll computed for ${dbRow.period_start} to ${dbRow.period_end}: ${dbRow.workers} worker(s), $${Number(dbRow.gross_pay).toLocaleString()} gross, $${Number(dbRow.net_pay).toLocaleString()} net.`
      : 'No timesheets found for that period.';
    break;
  case 'get_payroll_summary':
    spoken = dbRow && dbRow.run_id
      ? `Payroll for ${dbRow.period_start} to ${dbRow.period_end}: $${Number(dbRow.gross_pay).toLocaleString()} gross, $${Number(dbRow.net_pay).toLocaleString()} net (${dbRow.workers} workers).`
      : 'No payroll run found.';
    break;
  case 'add_worker':
    spoken = dbRow && dbRow.worker_code
      ? `Worker ${dbRow.name} added as ${dbRow.worker_code}${dbRow.trade ? ' (' + dbRow.trade + ')' : ''}.`
      : 'Could not add worker.';
    break;
  case 'get_dashboard_summary': {
    const rows = $input.all().map(i => i.json);
    if (!rows.length) { spoken = 'No projects found.'; }
    else {
      spoken = rows.map(r => `${r.project_name}: contract $${Number(r.total_revised_contract_value).toLocaleString()}, paid $${Number(r.total_paid).toLocaleString()}, balance $${Number(r.balance_remaining).toLocaleString()}.`).join(' ');
    }
    break;
  }
}

return [{
  json: {
    toolCallId: toolCall.toolCallId,
    result: spoken,
  },
}];""")

# ---------------------------------------------------------------------------
# 2. Lookup queries: cross-join company_profile for branding + invoice tax fields
# ---------------------------------------------------------------------------
set_query(
    "Exec: send_customer_invoice_lookup",
    "SELECT i.invoice_number, i.invoice_type, i.net_amount, i.gst_amount, i.pst_amount, "
    "i.amount_due, i.holdback_amount, i.issued_date, i.due_date, "
    "p.title AS project_name, c.name AS customer_name, c.email, "
    "cp.company_name, cp.email_from_name, cp.street_address, cp.city, cp.province, "
    "cp.postal_code, cp.phone, cp.signature_name, cp.brand_primary_color, "
    "cp.brand_accent_color, cp.brand_success_color, cp.portal_base_url "
    "FROM invoices i JOIN projects p ON p.id = i.project_id "
    "JOIN customers c ON c.id = p.customer_id CROSS JOIN company_profile cp "
    "WHERE cp.id = 1 AND (i.id::text = $1 OR i.invoice_number = $1) LIMIT 1;",
    "={{ [$json.arguments.invoice_id] }}")

set_query(
    "Exec: send_estimate_for_approval_lookup",
    "SELECT p.id, p.title, p.baseline_approval_token AS token, c.name AS customer_name, c.email, "
    "cp.company_name, cp.email_from_name, cp.brand_primary_color, cp.brand_accent_color, "
    "cp.brand_success_color, cp.portal_base_url "
    "FROM projects p JOIN customers c ON c.id = p.customer_id CROSS JOIN company_profile cp "
    "WHERE cp.id = 1 AND (p.id::text = $1 OR LOWER(p.title) LIKE LOWER('%' || $1 || '%')) LIMIT 1;",
    "={{ [$json.arguments.project_id] }}")

set_query(
    "Exec: send_change_order_for_approval_lookup",
    "SELECT co.id, co.change_order_number, co.description, co.cost_impact, co.approval_token AS token, "
    "p.title AS project_name, c.name AS customer_name, c.email, "
    "cp.company_name, cp.email_from_name, cp.brand_primary_color, cp.brand_accent_color, "
    "cp.brand_success_color, cp.portal_base_url "
    "FROM change_orders co JOIN projects p ON p.id = co.project_id "
    "JOIN customers c ON c.id = p.customer_id CROSS JOIN company_profile cp "
    "WHERE cp.id = 1 AND (p.id::text = $1 OR LOWER(p.title) LIKE LOWER('%' || $1 || '%')) "
    "AND co.change_order_number = $2 LIMIT 1;",
    "={{ [$json.arguments.project_id, $json.arguments.change_order_number] }}")

# ---------------------------------------------------------------------------
# 3. Updated tool branches
# ---------------------------------------------------------------------------
set_query(
    "Exec: create_estimate",
    "INSERT INTO estimates (project_id, division_code, scope_description, allocated_amount, revision, status, valid_until) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id;",
    "={{ [$json.arguments.project_id, ($json.arguments.division_code ?? 'Base Scope'), $json.arguments.scope_description, ($json.arguments.labor_estimate ?? 0) + ($json.arguments.material_estimate ?? 0), ($json.arguments.revision ?? 1), ($json.arguments.status ?? 'ACCEPTED'), ($json.arguments.valid_until ?? null)] }}")

set_query(
    "Exec: create_change_order",
    "WITH proj AS (SELECT id FROM projects WHERE (id::text = $1 OR LOWER(title) LIKE LOWER('%' || $1 || '%')) AND baseline_status = 'APPROVED' LIMIT 1) "
    "INSERT INTO change_orders (project_id, change_order_number, description, cost_impact, schedule_impact_days, reason, approval_status, tool_call_id) "
    "SELECT p.id, COALESCE((SELECT MAX(co.change_order_number) FROM change_orders co WHERE co.project_id = p.id), 0) + 1, $2, $3, $4, $6, 'PENDING', $5 "
    "FROM proj p ON CONFLICT (tool_call_id) DO NOTHING RETURNING id, change_order_number;",
    "={{ [$json.arguments.project_id, $json.arguments.description, $json.arguments.cost_impact, ($json.arguments.schedule_impact_days ?? 0), $json.toolCallId, ($json.arguments.reason ?? null)] }}")

set_query(
    "Exec: log_timesheet",
    "WITH w AS (SELECT id FROM workers WHERE lower(name) = lower($2) OR worker_code = $2 OR id::text = $2 LIMIT 1) "
    "INSERT INTO timesheets (project_id, worker_id, hours_worked, overtime_hours, work_description, date_worked, tool_call_id) "
    "SELECT $1, w.id, $3, $4, $5, CURRENT_DATE, $6 FROM w "
    "ON CONFLICT (tool_call_id) DO NOTHING RETURNING id;",
    "={{ [$json.arguments.project_id, $json.arguments.worker_name, $json.arguments.hours_worked, ($json.arguments.overtime_hours ?? 0), $json.arguments.work_description, $json.toolCallId] }}")

set_query(
    "Exec: create_invoice",
    "WITH cp AS (SELECT * FROM company_profile WHERE id = 1) "
    "INSERT INTO invoices (project_id, invoice_number, invoice_type, net_amount, gst_amount, pst_amount, pst_applicable, amount_due, holdback_amount, status, issued_date, due_date) "
    "SELECT p.id, $2, $3, "
    "ROUND(p.revised_contract_value * ($4 / 100.0), 2), "
    "ROUND(p.revised_contract_value * ($4 / 100.0) * cp.gst_rate, 2), "
    "CASE WHEN $5 THEN ROUND(p.revised_contract_value * ($4 / 100.0) * cp.pst_rate, 2) ELSE 0.00 END, "
    "$5, "
    "ROUND(p.revised_contract_value * ($4 / 100.0) * (1 + cp.gst_rate + CASE WHEN $5 THEN cp.pst_rate ELSE 0 END), 2), "
    "0.00, 'DRAFT', CURRENT_DATE, CURRENT_DATE + cp.invoice_due_days * INTERVAL '1 day' "
    "FROM projects p, cp WHERE p.id = $1 "
    "RETURNING id, invoice_number, net_amount, gst_amount, pst_amount, amount_due;",
    "={{ [$json.arguments.project_id, 'INV-' + Date.now(), $json.arguments.invoice_type, $json.arguments.billing_percentage, ($json.arguments.pst_applicable ?? false)] }}")

# ---------------------------------------------------------------------------
# 4. New tool branches
# ---------------------------------------------------------------------------
NEW_ACTIONS = ["record_payment", "run_payroll", "get_payroll_summary",
               "add_worker", "get_dashboard_summary"]

# Append switch cases (idempotent by existing outputKey)
existing_keys = {r.get("outputKey") for r in by_name["Actions Sub-Router"]["parameters"]["rules"]["values"]}
for action in NEW_ACTIONS:
    if action not in existing_keys:
        by_name["Actions Sub-Router"]["parameters"]["rules"]["values"].append(switch_case(action))

# record_payment: insert payment -> recompute status
add_node_once(pg_node(
    "gate-0020", "Exec: record_payment",
    "WITH inv AS (SELECT id FROM invoices WHERE invoice_number = $1 OR id::text = $1 LIMIT 1) "
    "INSERT INTO payments (invoice_id, payment_date, amount, method, notes, tool_call_id) "
    "SELECT inv.id, COALESCE($3::date, CURRENT_DATE), $2, $4, $5, $6 FROM inv "
    "ON CONFLICT (tool_call_id) DO NOTHING RETURNING invoice_id;",
    "={{ [$json.arguments.invoice_number, $json.arguments.amount, ($json.arguments.payment_date ?? null), ($json.arguments.method ?? null), ($json.arguments.notes ?? null), $json.toolCallId] }}",
    960, 980))

add_node_once(pg_node(
    "gate-0021", "Exec: record_payment_status",
    "WITH vp AS (SELECT total_paid, balance_due, due_date FROM view_invoice_payments WHERE invoice_id = $1), "
    "upd AS (UPDATE invoices i SET status = CASE "
    "WHEN i.status = 'DRAFT' THEN i.status "
    "WHEN vp.total_paid = 0 THEN CASE WHEN vp.due_date < CURRENT_DATE THEN 'OVERDUE' ELSE 'UNPAID' END "
    "WHEN vp.balance_due <= 0 THEN 'PAID' ELSE 'PARTIAL' END "
    "FROM vp WHERE i.id = $1 RETURNING i.invoice_number, i.status) "
    "SELECT upd.invoice_number, upd.status, vp.total_paid, vp.balance_due "
    "FROM upd CROSS JOIN vp;",
    "={{ [$json.invoice_id] }}",
    960, 1040))

add_node_once(pg_node(
    "gate-0022", "Exec: run_payroll",
    "SELECT * FROM fn_run_payroll($1::date, $2::int);",
    "={{ [($json.arguments.period_end ?? null), ($json.arguments.days ?? null)] }}",
    960, 1100))

add_node_once(pg_node(
    "gate-0023", "Exec: get_payroll_summary",
    "SELECT * FROM view_payroll_summary WHERE ($1::date IS NULL OR period_end = $1::date) ORDER BY period_end DESC LIMIT 1;",
    "={{ [($json.arguments.period_end ?? null)] }}",
    960, 1160))

add_node_once(pg_node(
    "gate-0024", "Exec: add_worker",
    "INSERT INTO workers (worker_code, name, trade, hourly_rate, overtime_rate) "
    "SELECT COALESCE($1, (SELECT 'W-' || LPAD(COALESCE(MAX(SUBSTRING(worker_code FROM '([0-9]+)')::int), 0) + 1, 3, '0') FROM workers WHERE worker_code ~ '^W-[0-9]+$')), "
    "$2, $3, $4, $5 "
    "ON CONFLICT (worker_code) DO UPDATE SET name = EXCLUDED.name, trade = EXCLUDED.trade, hourly_rate = EXCLUDED.hourly_rate, overtime_rate = EXCLUDED.overtime_rate "
    "RETURNING id, worker_code, name, trade, hourly_rate, overtime_rate;",
    "={{ [($json.arguments.worker_code ?? null), $json.arguments.name, ($json.arguments.trade ?? null), $json.arguments.hourly_rate, ($json.arguments.overtime_rate ?? null)] }}",
    960, 1220))

add_node_once(pg_node(
    "gate-0025", "Exec: get_dashboard_summary",
    "SELECT * FROM view_project_financial_summary WHERE ($1::text IS NULL OR project_id::text = $1 OR LOWER(project_name) LIKE LOWER('%' || $1 || '%'));",
    "={{ [($json.arguments.project_id ?? null)] }}",
    960, 1280))

# Rebuild name index + connections
by_name = {n["name"]: n for n in nodes}

router_main = conns["Actions Sub-Router"]["main"]
existing_router = [entry[0]["node"] for entry in router_main]
new_node_names = ["Exec: record_payment", "Exec: run_payroll", "Exec: get_payroll_summary",
                  "Exec: add_worker", "Exec: get_dashboard_summary"]
for name in new_node_names:
    if name not in existing_router:
        router_main.append([{"node": name, "type": "main", "index": 0}])

conns["Exec: record_payment"] = {"main": [[{"node": "Exec: record_payment_status", "type": "main", "index": 0}]]}
conns["Exec: record_payment_status"] = {"main": [[{"node": "Format Spoken Result", "type": "main", "index": 0}]]}
for name in ["Exec: run_payroll", "Exec: get_payroll_summary", "Exec: add_worker", "Exec: get_dashboard_summary"]:
    conns[name] = {"main": [[{"node": "Format Spoken Result", "type": "main", "index": 0}]]}

# ---------------------------------------------------------------------------
# Validate + write
# ---------------------------------------------------------------------------
node_names = {n["name"] for n in nodes}
for src, targets in conns.items():
    if src not in node_names:
        raise SystemExit(f"connection source missing node: {src}")
    for branch in targets["main"]:
        for t in branch:
            if t["node"] not in node_names:
                raise SystemExit(f"connection target missing node: {t['node']} (from {src})")

WF.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print(f"OK: {len(nodes)} nodes, {len(conns)} connection keys.")
print("New branches:", new_node_names)
