#!/usr/bin/env python3
"""Node harness test for the invoice-template-preview workflow (offline).

Extracts the Code-node jsCode from the generated workflow JSON and runs each
against fixtures in plain node (mocking only $input/$env/$ helpers), then
asserts the page content: three swipeable cards, three isolated iframes,
three tap-to-choose forms, the company's real branding, and the HMAC
verifiers accepting good signatures and rejecting bad/expired ones.

Run: python3 backend/n8n/test_invoice_template_preview.py
"""
import hashlib
import hmac
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WF = json.loads((ROOT / "backend" / "n8n" / "workflows" / "invoice-template-preview.json").read_text())
NODES = {n["name"]: n for n in WF["nodes"]}
SECRET = "test-secret"
COMPANY = "1"

FIXTURE = {
    "company_id": 1, "company_name": "Ireh Construction",
    "street_address": "1951 Kaptey Ave", "city": "Coquitlam",
    "province": "BC", "postal_code": "V3K 5Z7", "phone": "778-994-6602",
    "gst_reg_number": None, "pst_reg_number": None,
    "brand_primary_color": "#1d4ed8",
    "logo_data": "SGVsbG8=", "logo_content_type": "image/svg+xml",
    "payment_instructions": "E-transfer to the office.",
    "gst_rate": 0.05, "retention_rate": 0.1,
    "selected_key": "classic",
    "templates": [
        {"key": "classic", "display_name": "Classic",
         "description": "Traditional layout",
         "html": (ROOT / "backend" / "templates" / "invoice.html").read_text()},
        {"key": "modern", "display_name": "Modern",
         "description": "Bold color band",
         "html": (ROOT / "backend" / "templates" / "invoice-modern.html").read_text()},
        {"key": "compact", "display_name": "Compact",
         "description": "Condensed one-pager",
         "html": (ROOT / "backend" / "templates" / "invoice-compact.html").read_text()},
    ],
}


def run_node(js: str, input_json: dict, env: dict) -> dict:
    harness = (
        "const input = " + json.dumps(input_json) + ";\n"
        "const env = " + json.dumps(env) + ";\n"
        "const $input = { first: () => ({ json: input }) };\n"
        "const $env = new Proxy({}, { get: (_, k) => env[k] });\n"
        "function main() {\n" + js + "\n}\n"
        "console.log(JSON.stringify(main()));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
    out = subprocess.run(["node", f.name], capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError("node harness failed:\n" + out.stderr[:1500])
    parsed = json.loads(out.stdout)
    if isinstance(parsed, list):  # n8n Code nodes return [{ json: {...} }]
        parsed = parsed[0]["json"]
    return parsed


def b64url_sig(payload: str) -> str:
    import base64
    raw = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def main() -> int:
    # 1) preview page build
    page = run_node(NODES["Build Preview Page"]["parameters"]["jsCode"], FIXTURE,
                    {"PUBLIC_BASE_URL": "https://n8n2.ordrnow.com", "AUTH_TOKEN_SECRET": SECRET})
    html = page["html"]
    assert html.count('<section class="card') == 3, "three cards"
    assert html.count("iframe srcdoc=") == 3, "three isolated iframes"
    assert html.count('<form class="choose"') == 3, "three choose forms"
    for key in ("classic", "modern", "compact"):
        assert f'value="{key}"' in html, f"choose button for {key}"
    assert "scroll-snap-type: x mandatory" in html, "swipeable rail CSS"
    # srcdoc round-trip: every iframe must carry a COMPLETE document (a broken
    # escape silently blanks the preview — the bug this test exists for).
    import re as _re
    srcdocs = _re.findall(r'<iframe srcdoc="([^"]*)"', html)
    assert len(srcdocs) == 3, f"three srcdoc payloads, got {len(srcdocs)}"
    for i, raw in enumerate(srcdocs):
        decoded = (raw.replace("&quot;", '"').replace("&lt;", "<")
                      .replace("&gt;", ">").replace("&amp;", "&"))
        assert decoded.startswith("<!doctype html>"), f"card {i}: srcdoc not a full document"
        assert "data-tpl=" in decoded, f"card {i}: template body missing in srcdoc"
        assert "SAMPLE" in decoded, f"card {i}: sample invoice missing in srcdoc"
        assert len(decoded) > 4000, f"card {i}: srcdoc suspiciously short ({len(decoded)} bytes)"
    assert "Current style" in html, "current badge"
    assert "SAMPLE" in html, "sample invoice marker"
    assert "data:image/svg+xml;base64,SGVsbG8=" in html, "logo in card renders"
    assert "Ireh Construction" in html, "company branding"
    assert "invoice-template-choose?company=1&" in html, "choose URL with sig"
    print("preview page: 3 cards, 3 iframes, 3 forms, swipe CSS, branding — OK ("
          + str(len(html)) + " bytes)")

    # 2) preview sig verifier
    exp = int(time.time()) + 3600
    good = b64url_sig(f"{COMPANY}.template-preview.{exp}")
    r = run_node(NODES["Verify Preview Sig"]["parameters"]["jsCode"],
                 {"query": {"company": COMPANY, "exp": str(exp), "sig": good}},
                 {"AUTH_TOKEN_SECRET": SECRET})
    assert r["ok"] is True, "good sig accepted"
    r = run_node(NODES["Verify Preview Sig"]["parameters"]["jsCode"],
                 {"query": {"company": COMPANY, "exp": str(exp), "sig": "deadbeef"}},
                 {"AUTH_TOKEN_SECRET": SECRET})
    assert r["ok"] is False, "bad sig rejected"
    expired = int(time.time()) - 10
    sig_old = b64url_sig(f"{COMPANY}.template-preview.{expired}")
    r = run_node(NODES["Verify Preview Sig"]["parameters"]["jsCode"],
                 {"query": {"company": COMPANY, "exp": str(expired), "sig": sig_old}},
                 {"AUTH_TOKEN_SECRET": SECRET})
    assert r["ok"] is False, "expired sig rejected"
    print("preview sig: good accepted, bad + expired rejected — OK")

    # 3) choose sig verifier (template from body, sig from query)
    exp2 = int(time.time()) + 3600
    csig = b64url_sig(f"{COMPANY}.template-choose.{exp2}")
    r = run_node(NODES["Verify Choose Sig"]["parameters"]["jsCode"],
                 {"query": {"company": COMPANY, "exp": str(exp2), "sig": csig},
                  "body": {"template": "modern"}},
                 {"AUTH_TOKEN_SECRET": SECRET})
    assert r["ok"] is True and r["template"] == "modern", "choose sig + template"
    r = run_node(NODES["Verify Choose Sig"]["parameters"]["jsCode"],
                 {"query": {"company": COMPANY, "exp": str(exp2), "sig": csig},
                  "body": {}},
                 {"AUTH_TOKEN_SECRET": SECRET})
    assert r["ok"] is False, "choose without template rejected"
    print("choose sig: accepted with template, rejected without — OK")

    # 4) choice confirmation pages
    ok_page = run_node(NODES["Build Choice Page"]["parameters"]["jsCode"],
                       {"outcome": "UPDATED", "template": "modern"}, {})
    assert "Style set: modern" in ok_page["html"], "UPDATED page"
    bad_page = run_node(NODES["Build Choice Page"]["parameters"]["jsCode"],
                        {"outcome": "INVALID_TEMPLATE", "template": None}, {})
    assert "Unknown style" in bad_page["html"], "INVALID page"
    # hands control back to the app: Android intent:// to the real package
    # (the app has no custom scheme — MAIN/LAUNCHER only)
    for label, page in (("UPDATED", ok_page), ("INVALID", bad_page)):
        h = page["html"]
        assert "intent://app#Intent;package=com.ordrnow.personal_agent_mobile" in h, \
            f"{label} page: no intent return link"
        assert "component=com.ordrnow.personal_agent_mobile/.MainActivity" in h, \
            f"{label} page: return link names the wrong component"
        assert "openclaw://" not in h, f"{label} page: dead custom scheme still present"
    print("choice pages: UPDATED + INVALID — OK")

    print("invoice-template-preview harness: ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
