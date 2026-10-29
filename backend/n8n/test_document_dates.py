#!/usr/bin/env python3
"""Offline harness: document dates render as human dates, never ISO timestamps.

Runs the REAL jsCode from the workflows (no n8n, no network):

  python3 backend/n8n/test_document_dates.py

Covers
  D1 invoice HTML      "2026-10-29T07:00:00.000Z" -> "Oct 29, 2026"
  D2 due date          "2026-11-28T07:00:00.000Z" -> "Nov 28, 2026"
  D3 no ISO leaks      no "T07:00", no trailing "Z" in the rendered document
  D4 missing date      null/'' -> blank (no "Invalid Date", no "null")
  D5 already literal   "Oct 29, 2026" passes through unchanged
  D6 receipt           rendered receipt shows the human date too
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GW = os.path.join(HERE, "workflows", "voice-gateway.json")

RUNNER = r"""
const fs = require('fs');
const code = fs.readFileSync(process.env.CODE_PATH, 'utf8');
const payload = JSON.parse(process.env.FIXTURE || '{}');
const $input = { first: () => ({ json: payload }), all: () => [{ json: payload }] };
const $env = { PUBLIC_BASE_URL: 'https://example.test' };
const $ = () => ({ first: () => ({ json: payload }) });
const fn = new Function('$input', '$env', '$', 'return (async () => {' + code + '})();');
fn($input, $env, $)
  .then((r) => { process.stdout.write(JSON.stringify(r)); })
  .catch((e) => { process.stderr.write('ERR ' + e.message); process.exit(1); });
"""

failures = []


def check(cond, msg, extra=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}" + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        failures.append(msg)


def run(js, fixture):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        code_path = fh.name
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(RUNNER)
        runner = fh.name
    env = dict(os.environ, CODE_PATH=code_path, FIXTURE=json.dumps(fixture))
    proc = subprocess.run(["node", runner], capture_output=True, text=True, env=env, timeout=40)
    os.unlink(code_path)
    os.unlink(runner)
    if proc.returncode != 0:
        raise SystemExit(f"node failed: {proc.stderr.strip()[:400]}")
    return json.loads(proc.stdout)[0]["json"]


def node_js(name):
    w = json.load(open(GW))
    for n in w["nodes"]:
        if n["name"] == name:
            return n["parameters"]["jsCode"]
    raise SystemExit(f"node not found: {name}")


INVOICE = {
    "invoice_number": "INV-0099", "invoice_type": "PROGRESS_BILLING",
    "net_amount": 1000, "gst_amount": 50, "pst_amount": 0, "amount_due": 1050,
    "holdback_amount": 100, "retention_rate": 0.10,
    "issued_date": "2026-10-29T07:00:00.000Z",
    "due_date": "2026-11-28T07:00:00.000Z",
    "company_name": "Ireh Construction", "street_address": "1951 Kaptey Ave",
    "city": "Coquitlam", "province": "BC", "postal_code": "V3K 5Z7",
    "phone": "778-994-6602", "customer_name": "David Tam",
    "project_name": "5650 Camino", "lines": [], "billing_percentage": 10,
    "billed_basis": 10000, "contract_original": 10000,
    "payment_instructions": "e-transfer", "brand_primary_color": "#1a3a5c",
}

print("D1-D5 - invoice HTML")
out = run(node_js("Render Invoice HTML"), INVOICE)
html = out["invoiceHtml"]
check("Oct 29, 2026" in html, "issued date renders as Oct 29, 2026")
check("Nov 28, 2026" in html, "due date renders as Nov 28, 2026")
check("T07:00" not in html and "T00:00" not in html, "no ISO time component in the document")
check("2026-10-29T" not in html, "no ISO timestamp for the issued date")

blank = run(node_js("Render Invoice HTML"), dict(INVOICE, issued_date=None, due_date=""))
check("Invalid Date" not in blank["invoiceHtml"], "a missing date does not print Invalid Date")
check("null" not in blank["invoiceHtml"].lower(), "a missing date does not print null")

literal = run(node_js("Render Invoice HTML"), dict(INVOICE, issued_date="Oct 29, 2026"))
check("Oct 29, 2026" in literal["invoiceHtml"], "an already-formatted date is untouched")

print("D6 - receipt HTML")
receipt_fixture = dict(INVOICE, id="11111111-1111-1111-1111-111111111111",
                       customer_email="d@example.test", customer_company="",
                       total_paid=1050, balance_due=0, status="PAID",
                       payments=[{"payment_date": "2026-10-29T07:00:00.000Z",
                                  "amount": 1050, "method": "e-transfer"}],
                       latest_amount=1050, latest_date="2026-10-29T07:00:00.000Z",
                       latest_method="e-transfer", has_email=True, has_payments=True)
out2 = run(node_js("Render Receipt HTML"), receipt_fixture)
html2 = out2.get("receiptHtml", "")
check("Oct 29, 2026" in html2, "receipt shows Oct 29, 2026")
check("T07:00" not in html2, "receipt carries no ISO time component")

print()
if failures:
    print(f"{len(failures)} FAILED")
    sys.exit(1)
print("all document-date checks passed")
