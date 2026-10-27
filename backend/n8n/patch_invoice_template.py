#!/usr/bin/env python3
"""Idempotent patch: invoice rendering becomes template-driven, with the
company logo embedded as a data: URI so archived invoices are self-contained.

What it does (repo files only — deploy is a separate step):

1. Rewrites the three invoice-render Code nodes to render
   backend/templates/invoice.html through backend/templates/mustache_mini.js
   (both embedded verbatim into the jsCode — n8n Code nodes import nothing):
     - voice-gateway.json :: Render Invoice HTML          (email path, -> invoiceHtml)
     - voice-gateway.json :: Render Push Invoice HTML     (push path,  -> invoiceHtml)
     - approve-invoice.json :: Render Client Invoice      (approve-side fallback,
                                     keeps the last_client_html short-circuit,
                                     -> html)
   The data-prep (buildInvoiceData) preserves every mapping of the old inline
   builder: type label translation, descriptive billing line, bill-to lines,
   per-line rows with the single descriptive row when no line items exist,
   holdback %, GST/PST lines, payment-instruction lines.

2. Adds cp.logo_data, cp.logo_content_type to the three lookups that feed the
   renderers so the logo can be baked in:
     - voice-gateway.json :: Exec: send_customer_invoice_lookup
     - voice-gateway.json :: Exec: invoice_push_lookup
     - approve-invoice.json :: Lookup Invoice

Usage (repo root): python3 backend/n8n/patch_invoice_template.py
Validates every generated jsCode with `node --check` and re-parses both JSON
files before writing. Keeps the repo's 1-space JSON indent.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
TEMPLATES = ROOT / "backend" / "templates"
MUSTACHE_SRC = (TEMPLATES / "mustache_mini.js").read_text()
TEMPLATE_LITERAL = json.dumps((TEMPLATES / "invoice.html").read_text())

# --- data preparation (JS): maps the lookup row to the template's context.
# Kept behavior-identical to the old inline builder, minus the HTML assembly. ---
DATAPREP = r'''
function buildInvoiceData(inv) {
  const money = (v) => Number(v ?? 0).toLocaleString('en-CA', { style: 'currency', currency: 'CAD' });
  const typeMap = { 'DEPOSIT': 'Deposit', 'PROGRESS_BILLING': 'Progress billing',
                    'CHANGE_ORDER': 'Change order', 'FINAL': 'Final',
                    'Deposit': 'Deposit', 'Progress': 'Progress billing',
                    'Change Order': 'Change order', 'Final': 'Final' };
  const typeLabel = typeMap[inv?.invoice_type] || inv?.invoice_type || '';
  const addressLine = [inv?.street_address, inv?.city,
                       `${inv?.province ?? ''} ${inv?.postal_code ?? ''}`]
    .filter(Boolean).join(', ');
  const taxBits = [];  // (header reg lines are always rendered in the template)
  const lines = Array.isArray(inv?.lines) ? inv.lines : [];
  const pct = inv?.billing_percentage;
  const basis = inv?.billed_basis;
  const isOriginalBasis = pct != null && basis != null && inv?.contract_original != null &&
    Math.abs(Number(basis) - Number(inv.contract_original)) < 0.005;
  const basisLabel = isOriginalBasis ? 'contract value' : 'revised contract value';
  const lineLabel = inv?.description
    ? String(inv.description)
    : (pct != null && basis != null)
      ? `${typeLabel} \u2014 ${String(Number(pct))}% of ${basisLabel} (${money(basis)})`
      : typeLabel || 'Services';
  const billTo = [inv?.bill_street, inv?.bill_city,
                  inv?.bill_province ? `${inv?.bill_province} ${inv?.bill_postal ?? ''}` : inv?.bill_postal]
    .map(s => (s || '').toString().trim()).filter(Boolean).join('<br>');
  const holdbackPct = inv?.retention_rate != null
    ? Math.round(Number(inv.retention_rate) * 100) : 10;
  const items = lines.length
    ? lines.map((l, i) => ({ position: i + 1, description: l.description || '',
                             amount: money(l.amount) }))
    : [{ position: 1, description: lineLabel, amount: money(inv?.net_amount) }];
  const payLines = (inv?.payment_instructions || '').split('\n')
    .filter(s => s.trim().length > 0);
  return {
    brand_primary_color: inv?.brand_primary_color ?? '#1a3a5c',
    company_name: inv?.company_name ?? 'Ireh Construction',
    company_address: addressLine,
    company_phone: inv?.phone ?? '',
    // Header reg lines are ALWAYS on the layout (blank until the company
    // fills its registration numbers) — the user asked for reserved space.
    gst_reg_number: inv?.gst_reg_number ?? '',
    pst_reg_number: inv?.pst_reg_number ?? '',
    // The logo is baked in as a data: URI — an archived invoice never
    // depends on an externally linked image.
    logo_data_uri: inv?.logo_data && inv?.logo_content_type
      ? `data:${inv.logo_content_type};base64,${inv.logo_data}` : '',
    invoice_number: inv?.invoice_number ?? '',
    issued_date: inv?.issued_date ?? '',
    due_date: inv?.due_date ?? '',
    invoice_type_label: typeLabel,
    project_name: inv?.project_name ?? '',
    bill_to_name: (inv?.customer_name ?? '') +
                  (inv?.customer_company ? ' (' + inv.customer_company + ')' : ''),
    bill_to_address: billTo,
    line_items: items,
    net_amount: money(inv?.net_amount),
    gst_label: 'GST',
    // GST row is always on the layout ($0.00 when zero) — reserved space.
    gst_amount: money(inv?.gst_amount),
    // PST row is always on the layout: the amount, or "Not applicable".
    pst_amount: Number(inv?.pst_amount) ? money(inv.pst_amount) : 0,
    amount_due: money(inv?.amount_due),
    holdback_amount: Number(inv?.holdback_amount) ? money(inv.holdback_amount) : '',
    holdback_label: `Holdback (${holdbackPct}% retained)`,
    payment_instructions: payLines.join('<br>'),
  };
}
'''

CORE = (
    "const inv = $input.first()?.json;\n"
    + MUSTACHE_SRC
    + "\nconst INVOICE_TEMPLATE = " + TEMPLATE_LITERAL + ";\n"
    + DATAPREP
)

GATEWAY_RENDER_JS = (
    CORE
    + "const html = miniMustache(inv.invoice_template_html || INVOICE_TEMPLATE,"
      " buildInvoiceData(inv));\n"
    + "return [{ json: { ...inv, invoiceHtml: html } }];\n"
)

APPROVE_RENDER_JS = (
    "const inv = $input.first()?.json;\n"
    + "if (inv?.last_client_html) return [{ json: { ...inv, html: inv.last_client_html } }];\n"
    + MUSTACHE_SRC
    + "\nconst INVOICE_TEMPLATE = " + TEMPLATE_LITERAL + ";\n"
    + DATAPREP
    + "const html = miniMustache(inv.invoice_template_html || INVOICE_TEMPLATE,"
      " buildInvoiceData(inv));\n"
    + "return [{ json: { ...inv, html } }];\n"
)

LOGO_SELECT_PATCH = (
    r"cp\.payment_instructions,\s*cp\.retention_rate(\s+)FROM invoices i",
    "cp.payment_instructions, cp.retention_rate,"
    " cp.logo_data, cp.logo_content_type\\1FROM invoices i",
)

GATEWAY_PATH = ROOT / "backend" / "n8n" / "workflows" / "voice-gateway.json"
APPROVE_PATH = ROOT / "backend" / "n8n" / "workflows" / "approve-invoice.json"


def node_js_check(js: str, label: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        path = f.name
    proc = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{label}: generated jsCode failed node --check:\n{proc.stderr[:1200]}")


def patch_render_node(wf: dict, name: str, new_js: str) -> str:
    nodes = {n["name"]: n for n in wf["nodes"]}
    node = nodes.get(name)
    if node is None:
        raise SystemExit(f"missing node: {name}")
    js = node["parameters"]["jsCode"]
    # Idempotent: skip only when the jsCode carries THIS template revision
    # AND the v2 selection logic (row template, embedded fallback).
    if TEMPLATE_LITERAL in js and "invoice_template_html" in js:
        return "already"
    node["parameters"]["jsCode"] = new_js
    node_js_check(new_js, name)
    return "patched"


# v2: carry the company's chosen template into the render row. LEFT JOIN so a
# company with no selection (NULL) or a deactivated row yields NULL and the
# renderer falls back to the embedded Classic — rendering never hard-depends
# on the catalog table.
TEMPLATE_SELECT_PATCH = (
    r"cp\.logo_data, cp\.logo_content_type",
    "cp.logo_data, cp.logo_content_type,\n       dt.html AS invoice_template_html",
)
TEMPLATE_JOIN_PATCH = (
    r"JOIN company_profile cp ON cp\.id = p\.company_id",
    "JOIN company_profile cp ON cp.id = p.company_id\n"
    "LEFT JOIN document_templates dt ON dt.key = cp.invoice_template_key"
    " AND dt.is_active",
)


def patch_lookup_template(wf: dict, name: str) -> str:
    nodes = {n["name"]: n for n in wf["nodes"]}
    node = nodes.get(name)
    if node is None:
        raise SystemExit(f"missing node: {name}")
    query = node["parameters"]["query"]
    if "invoice_template_html" in query:
        return "already"
    for pattern, replacement in (TEMPLATE_SELECT_PATCH, TEMPLATE_JOIN_PATCH):
        hits = len(re.findall(pattern, query))
        if hits != 1:
            raise SystemExit(f"{name}: template patch matched {hits}x, expected 1: {pattern}")
        query = re.sub(pattern, replacement, query)
    node["parameters"]["query"] = query
    return "patched"


def patch_lookup(wf: dict, name: str) -> str:
    nodes = {n["name"]: n for n in wf["nodes"]}
    node = nodes.get(name)
    if node is None:
        raise SystemExit(f"missing node: {name}")
    query = node["parameters"]["query"]
    if "cp.logo_data" in query:
        return "already"
    pattern, replacement = LOGO_SELECT_PATCH
    hits = re.findall(pattern, query)
    if len(hits) != 1:
        raise SystemExit(f"{name}: logo select pattern matched {len(hits)} times, expected 1")
    node["parameters"]["query"] = re.sub(pattern, replacement, query)
    return "patched"


def main() -> int:
    gateway = json.loads(GATEWAY_PATH.read_text())
    approve = json.loads(APPROVE_PATH.read_text())

    print("render nodes:")
    print("  Render Invoice HTML      :",
          patch_render_node(gateway, "Render Invoice HTML", GATEWAY_RENDER_JS))
    print("  Render Push Invoice HTML:",
          patch_render_node(gateway, "Render Push Invoice HTML", GATEWAY_RENDER_JS))
    print("  Render Client Invoice    :",
          patch_render_node(approve, "Render Client Invoice", APPROVE_RENDER_JS))

    print("logo lookups:")
    print("  send_customer_invoice_lookup:",
          patch_lookup(gateway, "Exec: send_customer_invoice_lookup"))
    print("  invoice_push_lookup        :",
          patch_lookup(gateway, "Exec: invoice_push_lookup"))
    print("  Lookup Invoice (approve)   :",
          patch_lookup(approve, "Lookup Invoice"))

    print("template-catalog lookups (LEFT JOIN company's choice):")
    for wf, name in ((gateway, "Exec: send_customer_invoice_lookup"),
                     (gateway, "Exec: invoice_push_lookup"),
                     (approve, "Lookup Invoice")):
        print(f"  {name}:", patch_lookup_template(wf, name))

    # validations: connections intact, node names unique, JSON re-parses
    for label, wf, path in (("voice-gateway", gateway, GATEWAY_PATH),
                            ("approve-invoice", approve, APPROVE_PATH)):
        names = [n["name"] for n in wf["nodes"]]
        assert len(names) == len(set(names)), f"{label}: duplicate node names"
        known = set(names)
        for src, conn in wf["connections"].items():
            assert src in known, f"{label}: dangling connection source {src}"
            for out in conn.get("main", []):
                for branch in out:
                    assert branch["node"] in known, f"{label}: dangling target {branch['node']}"
        json.loads(json.dumps(wf))  # round-trip sanity
        path.write_text(json.dumps(wf, indent=1) + "\n")
        print(f"  {label}: validated + written")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
