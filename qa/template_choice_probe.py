#!/usr/bin/env python3
"""E2E probe for the invoice-template choice feature (run AFTER deploy).

Exercises the REAL chain end to end:
  1. set_invoice_template('modern') via the gateway -> DB row updated
  2. create a QA draft invoice + send_customer_invoice preview ->
     stored last_client_html must carry data-tpl="modern" + logo
  3. preview page GET with a signature computed ON THE HOST (secret never
     leaves the box) -> 200 + three cards + swipe rail
  4. tap-to-choose POST 'compact' -> DB row compact
  5. set_invoice_template('artdeco') -> INVALID_TEMPLATE, row unchanged
  6. revert to classic, delete the QA draft, reset invoice numbering

Run: python3 qa/template_choice_probe.py
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "ubuntu@n8n2.ordrnow.com"
GATEWAY = "https://n8n2.ordrnow.com/webhook/voice/gateway"
SIG_HELPER = (
    "import hmac,hashlib,base64,sys;"
    "print(base64.urlsafe_b64encode("
    "hmac.new(sys.argv[1].encode(),sys.argv[2].encode(),hashlib.sha256).digest()"
    ").decode().rstrip('='))"
)


def ssh(cmd: str) -> str:
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=10", HOST, cmd],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ssh failed: {r.stderr[:500]}")
    return r.stdout.strip()


def gateway_call(action: str, args: dict) -> str:
    body = {"message": {"toolCalls": [{
        "id": f"probe-{int(time.time()*1000)}", "type": "function",
        "function": {"name": action, "arguments": json.dumps(args)}}]}}
    req = urllib.request.Request(GATEWAY, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "curl/8.5.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        d = json.loads(resp.read() or b"{}")
    return (d.get("results") or [{}])[0].get("result", "")


def db(q: str) -> str:
    return ssh(f'sudo docker exec n8n-compose-postgres-1 psql -U postgres -d postgres -At -c "{q}"')


def signed_url(kind: str):
    exp = int(time.time()) + 3600
    payload = f"1.template-{kind}.{exp}"  # workflow signs `${company}.template-${kind}.${exp}`
    sig = ssh(f"cd /home/ubuntu/n8n-compose && SECRET=$(sudo docker exec "
              f"n8n-compose-n8n-1 printenv AUTH_TOKEN_SECRET) && "
              f"python3 -c {json.dumps(SIG_HELPER)} \"$SECRET\" \"{payload}\"")
    return (f"https://n8n2.ordrnow.com/webhook/invoice-template-{kind}"
            f"?company=1&exp={exp}&sig={sig}"), sig, exp


def main() -> int:
    # Self-clean: drop QA drafts left by earlier probe runs, then reset the
    # invoice counter to the highest real INV-NNNN (skips grandfathered
    # legacy numbers like INV-OAK-1001).
    db("DELETE FROM invoices WHERE description='QA template probe - delete me'"
       " AND status='DRAFT'")
    db("UPDATE company_profile SET invoice_last_number = COALESCE("
       "(SELECT max(substring(invoice_number FROM '[0-9]+$')::int) FROM invoices "
       " WHERE invoice_number ~ '^INV-[0-9]{4}$'), 0) WHERE id=1")
    num_before = db("SELECT invoice_last_number FROM company_profile WHERE id=1")

    # 1) set modern via the tool
    reply = gateway_call("set_invoice_template", {"template": "modern"})
    assert "modern" in reply.lower(), f"set reply: {reply}"
    row = db("SELECT COALESCE(invoice_template_key,'classic') FROM company_profile WHERE id=1")
    assert row == "modern", f"row after set: {row}"
    print("1. set_invoice_template('modern'):", reply)

    # 2) QA invoice + preview send -> stored HTML must be MODERN
    reply = gateway_call("create_invoice", {
        "project_id": "Kitsilano Reno", "invoice_type": "PROGRESS_BILLING",
        "billing_percentage": 10, "description": "QA template probe - delete me"})
    num = reply.split("INV-")[1][:4] if "INV-" in reply else None
    assert num, f"create reply: {reply}"
    reply = gateway_call("send_customer_invoice", {"invoice_id": f"INV-{num}"})
    assert "Preview emailed" in reply, f"send reply: {reply}"
    # NOTE: chr(34) instead of literal double quotes — the query travels
    # through ssh + a shell double-quoted -c string, which eats them.
    stored = db(f"SELECT position('data-tpl=' || chr(34) || 'modern' || chr(34) in last_client_html) > 0, "
                f"position('data:image/svg+xml;base64,' in last_client_html) > 0 "
                f"FROM invoices WHERE invoice_number='INV-{num}'")
    assert stored == "t|t", f"stored HTML markers: {stored}"
    print(f"2. INV-{num} preview stored with MODERN layout + logo: OK")

    # 3) preview page (signature computed on the host)
    url, sig, exp = signed_url("preview")
    with urllib.request.urlopen(urllib.request.Request(url, method="GET",
                                   headers={"User-Agent": "curl/8.5.0"}), timeout=45) as r:
        page = r.read().decode()
    assert r.status == 200
    assert page.count('<section class="card') == 3, "preview page cards"
    assert "scroll-snap-type" in page, "swipe rail"
    print("3. preview page: 200, 3 swipeable cards OK")

    # 4) tap-to-choose POST 'compact'
    url, sig, exp = signed_url("choose")
    data = f"template=compact&company=1&exp={exp}&sig={sig}".encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "User-Agent": "curl/8.5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        body = r.read().decode()
    assert r.status == 200 and "Style set: compact" in body, "choose page"
    row = db("SELECT COALESCE(invoice_template_key,'classic') FROM company_profile WHERE id=1")
    assert row == "compact", f"row after choose: {row}"
    print("4. tap-to-choose(compact): page + DB OK")

    # 5) invalid template refused
    reply = gateway_call("set_invoice_template", {"template": "artdeco"})
    assert "classic, modern or compact" in reply or "not one" in reply, f"invalid reply: {reply}"
    row = db("SELECT COALESCE(invoice_template_key,'classic') FROM company_profile WHERE id=1")
    assert row == "compact", "row unchanged after invalid"
    print("5. INVALID_TEMPLATE refused, row unchanged: OK")

    # 6) cleanup + revert
    db(f"DELETE FROM invoices WHERE invoice_number='INV-{num}' AND status='DRAFT'")
    db(f"UPDATE company_profile SET invoice_last_number={num_before} WHERE id=1")
    print(gateway_call("set_invoice_template", {"template": "classic"}))
    row = db("SELECT COALESCE(invoice_template_key,'classic') FROM company_profile WHERE id=1")
    assert row == "classic", f"revert: {row}"
    print("6. reverted to classic, QA draft deleted, numbering reset")

    print("template-choice E2E: ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
