#!/usr/bin/env python3
"""P1: scope every tenant-facing tool query by the caller's company.

Every SQL node that reads or writes tenant data gets an explicit company
predicate bound to `$C`, which is replaced by a real parameter index and bound
to `$('Normalize Tool Call').first().json.companyId` (the scope resolved once
per call). Rows that belong to another company simply do not match, so a second
tenant can neither read nor write the first tenant's data.

Idempotent: a node that already carries `company_id = $` is left alone, so
re-running reports 0 changes.

    python3 backend/n8n/patch_tenant_scope_tools.py [--check]
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GW = ROOT / "backend" / "n8n" / "workflows" / "voice-gateway.json"

COMPANY_EXPR = "Number($('Normalize Tool Call').first().json.companyId)"

# node -> list of (old, new) exact SQL edits. `$C` is rewritten to a bound param.
EDITS = {
    "Exec: lookup_or_create_customer": [
        ("WHERE c.company_id = 1", "WHERE c.company_id = $C"),
        ("INSERT INTO customers (name, email, phone)",
         "INSERT INTO customers (name, email, phone, company_id)"),
        ("SELECT a.full_name, a.email, a.phone FROM args a",
         "SELECT a.full_name, a.email, a.phone, $C FROM args a"),
    ],
    "Exec: find_customer_candidates": [
        ("WHERE company_id = 1", "WHERE company_id = $C"),
    ],
    "Exec: create_project": [
        ("WHERE c.company_id = 1", "WHERE c.company_id = $C"),
        ("INSERT INTO projects (customer_id, title, site_address)",
         "INSERT INTO projects (customer_id, title, site_address, company_id)"),
        ("SELECT c.id, a.title, COALESCE(a.site, a.title) FROM c, args a",
         "SELECT c.id, a.title, COALESCE(a.site, a.title), $C FROM c, args a"),
    ],
    "Exec: create_estimate": [
        ("WHERE pr.company_id = 1", "WHERE pr.company_id = $C"),
    ],
    "Exec: create_change_order": [
        ("AND deleted_at IS NULL AND baseline_status = 'APPROVED' LIMIT 1",
         "AND deleted_at IS NULL AND baseline_status = 'APPROVED'\n   AND company_id = $C LIMIT 1"),
    ],
    "Exec: log_timesheet": [
        ("WITH w AS (SELECT id FROM workers WHERE lower(name) = lower($2) "
         "OR worker_code = $2 OR id::text = $2 LIMIT 1)",
         "WITH p AS (SELECT id FROM projects WHERE id::text = $1 AND company_id = $C),\n"
         "     w AS (SELECT id FROM workers WHERE company_id = $C\n"
         "            AND (lower(name) = lower($2) OR worker_code = $2 OR id::text = $2) LIMIT 1)"),
        ("SELECT $1, w.id, $3, $4, $5, CURRENT_DATE, $6 FROM w",
         "SELECT p.id, w.id, $3, $4, $5, CURRENT_DATE, $6 FROM w, p"),
    ],
    "Exec: add_worker": [
        ("INSERT INTO workers (worker_code, name, trade, hourly_rate, overtime_rate)",
         "INSERT INTO workers (worker_code, name, trade, hourly_rate, overtime_rate, company_id)"),
        ("FROM workers WHERE worker_code ~ '^W-[0-9]+$')),",
         "FROM workers WHERE worker_code ~ '^W-[0-9]+$' AND company_id = $C)),"),
        ("$2, $3, $4, $5 ON CONFLICT (company_id, worker_code)",
         "$2, $3, $4, $5, $C ON CONFLICT (company_id, worker_code)"),
    ],
    "Exec: create_invoice": [
        ("WHERE (p.id::text = $1 OR LOWER(p.title) LIKE LOWER('%' || $1 || '%'))\n"
         "    AND p.deleted_at IS NULL",
         "WHERE (p.id::text = $1 OR LOWER(p.title) LIKE LOWER('%' || $1 || '%'))\n"
         "    AND p.deleted_at IS NULL\n    AND p.company_id = $C"),
    ],
    "Exec: create_invoice_change_orders": [
        ("WHERE (p.id::text = $1 OR LOWER(p.title) LIKE LOWER('%' || $1 || '%'))\n"
         "    AND p.deleted_at IS NULL",
         "WHERE (p.id::text = $1 OR LOWER(p.title) LIKE LOWER('%' || $1 || '%'))\n"
         "    AND p.deleted_at IS NULL\n    AND p.company_id = $C"),
    ],
    "Exec: get_project_statement": [
        ("FROM view_project_financial_summary WHERE (project_id::text = $1 "
         "OR LOWER(project_name) LIKE LOWER($2))",
         "FROM view_project_financial_summary WHERE (project_id::text = $1 "
         "OR LOWER(project_name) LIKE LOWER($2)) AND company_id = $C"),
    ],
    "Exec: get_dashboard_summary": [
        ("FROM view_project_financial_summary WHERE ($1::text IS NULL",
         "FROM view_project_financial_summary WHERE company_id = $C AND ($1::text IS NULL"),
    ],
    "Exec: list_projects": [
        ("FROM view_project_financial_summary WHERE ($1::text IS NULL",
         "FROM view_project_financial_summary WHERE company_id = $C AND ($1::text IS NULL"),
    ],
    "Exec: get_schedule": [
        ("FROM view_schedule WHERE status <> 'DONE'",
         "FROM view_schedule WHERE company_id = $C AND status <> 'DONE'"),
    ],
    "Exec: get_payroll_summary": [
        ("FROM view_payroll_summary WHERE",
         "FROM view_payroll_summary WHERE company_id = $C AND"),
    ],
    "Exec: run_payroll": [
        ("SELECT * FROM fn_run_payroll($1::date, $2::int);",
         "SELECT * FROM fn_run_payroll_for_company($C, $1::date, $2::int);"),
    ],
    "Exec: list_invoices": [
        ("WHERE ($1::text IS NULL OR LOWER(i.status) = LOWER($1))",
         "WHERE i.company_id = $C AND ($1::text IS NULL OR LOWER(i.status) = LOWER($1))"),
    ],
    "Exec: send_customer_invoice_lookup": [
        ("WHERE i.id::text = $1 OR i.invoice_number = $1",
         "WHERE (i.id::text = $1 OR i.invoice_number = $1) AND i.company_id = $C"),
    ],
    "Exec: invoice_push_lookup": [
        ("WHERE i.id::text = $1 OR i.invoice_number = $1",
         "WHERE (i.id::text = $1 OR i.invoice_number = $1) AND i.company_id = $C"),
    ],
    "Exec: record_payment": [
        ("WITH inv AS (SELECT id FROM invoices WHERE invoice_number = $1 OR id::text = $1 LIMIT 1)",
         "WITH inv AS (SELECT id FROM invoices WHERE (invoice_number = $1 OR id::text = $1)\n"
         "              AND company_id = $C LIMIT 1)"),
    ],
    "Exec: record_payment_status": [
        ("FROM view_invoice_payments WHERE invoice_id = $1",
         "FROM view_invoice_payments WHERE invoice_id = $1 AND company_id = $C"),
    ],
    "Exec: store_invoice_html": [
        ("UPDATE invoices SET last_client_html = $2 WHERE id::text = $1",
         "UPDATE invoices SET last_client_html = $2 WHERE id::text = $1 AND company_id = $C"),
    ],
    "Exec: store_push_html": [
        ("UPDATE invoices SET last_client_html = $2 WHERE id::text = $1",
         "UPDATE invoices SET last_client_html = $2 WHERE id::text = $1 AND company_id = $C"),
    ],
    "Exec: log_invoice_preview": [
        ("WHERE i.id::text = $2 RETURNING id;",
         "WHERE i.id::text = $2 AND i.company_id = $C RETURNING id;"),
    ],
    "Exec: log_receipt": [
        ("WHERE EXISTS (SELECT 1 FROM invoices WHERE id = $2::uuid)",
         "WHERE EXISTS (SELECT 1 FROM invoices WHERE id = $2::uuid AND company_id = $C)"),
    ],
    "Exec: update_customer": [
        ("WHERE c.id::text = $1 OR LOWER(c.name) = LOWER(btrim($1::text))",
         "WHERE c.company_id = $C\n   AND (c.id::text = $1 OR LOWER(c.name) = LOWER(btrim($1::text)))"),
    ],
    "Exec: update_company_billing": [
        ("WHERE id = $4", "WHERE id = $C"),
    ],
    "Exec: set_briefing_time": [
        ("WHERE id = 1", "WHERE id = $C"),
    ],
    "Exec: list_invoice_templates": [
        ("WHERE cp.id = 1", "WHERE cp.id = $C"),
        ("(SELECT count(*) FROM device_tokens) AS device_count",
         "(SELECT count(*) FROM device_tokens WHERE company_id = $C) AS device_count"),
    ],
    "Exec: set_invoice_template": [
        ("WHERE cp.id = 1", "WHERE cp.id = $C"),
    ],
    "Exec: get_device_tokens": [
        ("SELECT token FROM device_tokens UNION ALL SELECT NULL::text "
         "WHERE NOT EXISTS (SELECT 1 FROM device_tokens)",
         "SELECT token FROM device_tokens WHERE company_id = $C\n"
         "UNION ALL SELECT NULL::text\n WHERE NOT EXISTS (SELECT 1 FROM device_tokens WHERE company_id = $C)"),
    ],
    "Exec: approval_devices": [
        ("SELECT token FROM device_tokens UNION ALL SELECT NULL::text "
         "WHERE NOT EXISTS (SELECT 1 FROM device_tokens)",
         "SELECT token FROM device_tokens WHERE company_id = $C\n"
         "UNION ALL SELECT NULL::text\n WHERE NOT EXISTS (SELECT 1 FROM device_tokens WHERE company_id = $C)"),
    ],
    "Exec: push_devices": [
        ("SELECT token FROM device_tokens UNION ALL SELECT NULL::text "
         "WHERE NOT EXISTS (SELECT 1 FROM device_tokens)",
         "SELECT token FROM device_tokens WHERE company_id = $C\n"
         "UNION ALL SELECT NULL::text\n WHERE NOT EXISTS (SELECT 1 FROM device_tokens WHERE company_id = $C)"),
    ],
    "Exec: template_push_devices": [
        ("SELECT token FROM device_tokens UNION ALL SELECT NULL::text "
         "WHERE NOT EXISTS (SELECT 1 FROM device_tokens)",
         "SELECT token FROM device_tokens WHERE company_id = $C\n"
         "UNION ALL SELECT NULL::text\n WHERE NOT EXISTS (SELECT 1 FROM device_tokens WHERE company_id = $C)"),
    ],
    "Exec: list_estimate_status": [
        ("WHERE p.company_id = 1", "WHERE p.company_id = $C"),
    ],
    "Exec: remove_project": [
        ("AND p.company_id = 1", "AND p.company_id = $C"),
    ],
    "Exec: rotate_estimate_token": [
        ("WHERE p.id::text = $1", "WHERE p.id::text = $1 AND p.company_id = $C"),
    ],
    "Exec: log_approval_email_estimate": [
        ("   WHERE p.id::text = $4 AND p.deleted_at IS NULL\n   RETURNING id",
         "   WHERE p.id::text = $4 AND p.deleted_at IS NULL AND p.company_id = $C\n   RETURNING id"),
        ("   WHERE p.id::text = $4 AND p.baseline_status IN",
         "   WHERE p.id::text = $4 AND p.company_id = $C AND p.baseline_status IN"),
    ],
    "Exec: log_approval_email_change_order": [
        ("WHERE p.id::text = $4 AND p.deleted_at IS NULL RETURNING id;",
         "WHERE p.id::text = $4 AND p.deleted_at IS NULL AND p.company_id = $C RETURNING id;"),
    ],
    "Exec: receipt_lookup": [
        ("LEFT JOIN invoices i ON i.invoice_number = b.ref OR i.id::text = b.ref",
         "LEFT JOIN invoices i ON (i.invoice_number = b.ref OR i.id::text = b.ref)\n"
         "                         AND i.company_id = $C"),
    ],
    "Exec: get_estimate_approval_link": [
        ("      AND p.deleted_at IS NULL\n   ORDER BY",
         "      AND p.deleted_at IS NULL\n      AND p.company_id = $C\n   ORDER BY"),
    ],
    "Exec: get_change_order_approval_link": [
        ("AND p.deleted_at IS NULL\nLEFT JOIN change_orders",
         "AND p.deleted_at IS NULL AND p.company_id = $C\nLEFT JOIN change_orders"),
    ],
    "Exec: send_estimate_for_approval_lookup": [
        ("    AND p.deleted_at IS NULL",
         "    AND p.deleted_at IS NULL\n    AND p.company_id = $C"),
    ],
    "Exec: send_change_order_for_approval_lookup": [
        ("WHERE cp.id = 1 AND p.deleted_at IS NULL",
         "WHERE cp.id = $C AND p.deleted_at IS NULL"),
    ],
}


def next_param(sql):
    """Highest existing $n in the ORIGINAL query (before $C becomes $n)."""
    nums = [int(m) for m in re.findall(r"\$(\d+)", sql)]
    return (max(nums) + 1) if nums else 1


def append_param(expr, param):
    """Add the company value to a node's queryReplacement array expression."""
    if not expr:
        return "={{ [" + COMPANY_EXPR + "] }}"
    # Shape: ={{ [arg1, arg2, ...] }} - the inner text may itself contain
    # brackets and quotes, so strip the wrapper rather than regex-matching it.
    body = expr.strip()
    if body.startswith("={{"):
        body = body[3:]
    if body.endswith("}}"):
        body = body[:-2]
    body = body.strip()
    if not (body.startswith("[") and body.endswith("]")):
        raise SystemExit(f"unexpected queryReplacement shape: {expr[:80]}")
    inner = body[1:-1].strip()
    sep = ", " if inner else ""
    return "={{ [" + inner + sep + COMPANY_EXPR + "] }}"


def main():
    check = "--check" in sys.argv
    w = json.loads(GW.read_text())
    nodes = {n["name"]: n for n in w["nodes"]}
    changes = []
    problems = []

    for name, edits in EDITS.items():
        n = nodes.get(name)
        if n is None:
            problems.append(f"missing node: {name}")
            continue
        q = n["parameters"].get("query", "")
        if "$C" not in q and "company_id = $" in q:
            continue  # already scoped
        new_q = q
        for old, new in edits:
            if old == new:
                continue
            if old not in new_q:
                # Already applied? $C became a concrete $n::smallint.
                pat = re.escape(new).replace(re.escape("$C"), r"\$\d+::smallint")
                if re.search(pat, new_q):
                    continue
                problems.append(f"{name}: fragment not found -> {old[:60]!r}")
                continue
            new_q = new_q.replace(old, new, 1)
        if "$C" in new_q:
            idx = next_param(q)          # number from the ORIGINAL query
            new_q = new_q.replace("$C", f"${idx}::smallint")
            opts = n["parameters"].setdefault("options", {})
            opts["queryReplacement"] = append_param(opts.get("queryReplacement"), idx)
        if new_q != q:
            n["parameters"]["query"] = new_q
            changes.append(name)

    print(f"{GW.name}: {len(changes)} node(s) scoped")
    for c in changes:
        print(f"  - {c}")
    for p in problems:
        print(f"  PROBLEM {p}")
    if check or problems:
        return 1 if problems else 0
    GW.write_text(json.dumps(w, indent=2, ensure_ascii=False) + "\n")
    print("written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
