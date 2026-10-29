#!/usr/bin/env python3
"""L3: live probe - a brand-new Google user gets setup, and cannot touch Ireh.

  python3 qa/onboarding_probe.py

The probe creates a throwaway user row, mints a real session token with the
server's own secret (inside the n8n container, never printed), and drives the
live hook + gateway exactly as Vapi would. It cleans up after itself and
asserts that company 1 is unchanged.

  P1  hook, no token (legacy client)  -> Ireh variables, unchanged greeting
  P2  hook, new user token           -> setup greeting, blank company, user_id
  P3  gateway data tool, new user    -> refused, no rows written
  P4  gateway onboarding status      -> returns the (empty) status row
  P5  gateway complete_onboarding    -> company created + user linked
  P6  hook again                     -> setup_complete true, own company name
  P7  gateway data tool, new company -> still refused (P1 scoping pending)
  P8  hook, owner-equivalent token    -> Ireh variables intact
  P9  cleanup: zero residue, company 1 identical
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

HOST = "ubuntu@n8n2.ordrnow.com"
CONTAINER = "n8n-compose-n8n-1"
PG = "n8n-compose-postgres-1"
BASE = "https://n8n2.ordrnow.com/webhook"
UID = "11111111-2222-3333-4444-555555555555"
EMAIL = "probe-onboarding@test.local"

failures = []


def check(cond, msg, extra=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}" + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        failures.append(msg)


def sh(cmd):
    p = subprocess.run(["ssh", "-o", "ConnectTimeout=10", HOST, cmd],
                       capture_output=True, text=True, timeout=120)
    return p.stdout.strip(), p.stderr.strip(), p.returncode


def psql(sql):
    out, err, rc = sh(f"sudo docker exec {PG} psql -U postgres -d postgres -At -c {json.dumps(sql)}")
    if rc != 0:
        raise SystemExit(f"psql failed: {err}")
    return out


def mint_token(uid):
    js = (
        "const crypto=require('crypto');"
        f"const p=Buffer.from(JSON.stringify({{uid:'{uid}',exp:Math.floor(Date.now()/1000)+600}})).toString('base64url');"
        "const s=crypto.createHmac('sha256',process.env.AUTH_TOKEN_SECRET).update(p).digest('base64url');"
        "process.stdout.write('v1.'+p+'.'+s);"
    )
    out, err, rc = sh(f"sudo docker exec {CONTAINER} node -e {json.dumps(js)}")
    if rc != 0 or not out.startswith("v1."):
        raise SystemExit(f"token mint failed: {err}")
    return out


def post(path, body, token=None):
    req = urllib.request.Request(f"{BASE}/{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    if token:
        req.add_header("X-User-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode()[:300]}


def tool(name, args, user_id):
    return {
        "message": {
            "type": "tool-calls",
            "toolCalls": [{"id": "tc-1", "type": "function",
                           "function": {"name": name, "arguments": json.dumps(args)}}],
            "call": {"assistantOverrides": {"variableValues": {"user_id": user_id}}},
        }
    }


def main():
    ireh_before = psql("SELECT md5(row_to_json(cp)::text) FROM company_profile cp WHERE id=1")
    employees_before = psql("SELECT count(*) FROM workers WHERE company_id=1")
    invoices_before = psql("SELECT count(*) FROM invoices")
    customers_before = psql("SELECT count(*) FROM customers")

    print("P1 - hook without a token (legacy client)")
    hook = post("vapi/assistant-hook", {})
    vv = (hook.get("assistantOverrides") or {}).get("variableValues") or {}
    check(str(vv.get("setup_complete")).lower() == "true", "legacy client still resolves company 1",
          str(vv)[:200])
    check(vv.get("company_name") == "Ireh Construction", "legacy company name intact", str(vv.get("company_name")))

    print("P2 - hook with a brand-new user")
    psql(f"INSERT INTO users (id, google_sub, email, name) VALUES ('{UID}', 'probe-sub', '{EMAIL}', 'Probe User')")
    token = mint_token(UID)
    hook2 = post("vapi/assistant-hook", {}, token)
    vv2 = (hook2.get("assistantOverrides") or {}).get("variableValues") or {}
    check(str(vv2.get("setup_complete")).lower() == "false", "new user is not set up")
    check(vv2.get("company_name") == "", "new user sees no company name", str(vv2.get("company_name")))
    check(vv2.get("user_id") == UID, "user_id transported to the call")
    check("company name" in (hook2.get("assistantOverrides") or {}).get("firstMessage", "").lower(),
          "greeting starts the setup")
    check(len(vv2.get("onboarding_steps") or "") > 100, "onboarding steps injected")

    print("P3 - a data tool is refused for a user with no company")
    r = post("voice/gateway", tool("list_projects", {}, UID))
    res = json.dumps(r)
    check("results" in r, "gateway responded", res[:200])
    check("finish setting you up" in res.lower() or "setup" in res.lower(),
          "refusal explains setup is needed", res[:200])
    check(psql("SELECT count(*) FROM customers") == customers_before, "no customer written")
    check(psql("SELECT count(*) FROM invoices") == invoices_before, "no invoice written")

    print("P4 - onboarding status is allowed and empty")
    r4 = post("voice/gateway", tool("get_onboarding_status", {}, UID))
    check("results" in r4, "status answered", json.dumps(r4)[:200])

    print("P5 - complete_onboarding creates the company")
    r5 = post("voice/gateway", tool("complete_onboarding", {
        "company_name": "Probe Co",
        "pm_name": "Probe Owner",
        "pm_preferred_name": "Probe",
        "street_address": "1 Probe Way",
        "city": "Coquitlam",
        "province": "BC",
        "postal_code": "V3K 9Z9",
        "payment_instructions": "e-transfer to probe@test.local",
        "workers": [{"name": "Probe Worker", "trade": "labourer", "hourly_rate": "30"}],
    }, UID))
    check("results" in r5, "complete_onboarding responded", json.dumps(r5)[:300])
    row = psql(f"SELECT cp.id, cp.company_name, cp.email_from, (cp.setup_completed_at IS NOT NULL) "
               f"FROM company_profile cp JOIN users u ON u.company_id = cp.id WHERE u.id = '{UID}'")
    check(bool(row), "company linked to the user", row)
    if row:
        cid, cname, cemail, csetup = row.split("|")
        check(cname == "Probe Co", "company name stored", cname)
        check(cemail == EMAIL, "sender is the user's own email", cemail)
        check(csetup == "t", "setup completed (address given)", csetup)
        check(psql(f"SELECT count(*) FROM workers WHERE company_id={cid} AND name='Probe Worker'") == "1",
              "worker created in the new company")
        check(psql("SELECT count(*) FROM workers WHERE company_id=1 AND name='Probe Worker'") == "0",
              "worker did not leak into company 1")

    print("P6 - the hook now sees a set-up company")
    hook3 = post("vapi/assistant-hook", {}, token)
    vv3 = (hook3.get("assistantOverrides") or {}).get("variableValues") or {}
    check(str(vv3.get("setup_complete")).lower() == "true", "setup now complete")
    check(vv3.get("company_name") == "Probe Co", "greeting uses their company", str(vv3.get("company_name")))

    print("P7 - the new tenant gets the tools, scoped to their own company")
    r7 = post("voice/gateway", tool("list_projects", {}, UID))
    body7 = json.dumps(r7)
    check("being prepared" not in body7.lower(), "scope guard no longer blocks the new tenant", body7[:200])
    check("5650 Camino" not in body7 and "Oakridge" not in body7,
          "no other tenant's projects are visible", body7[:200])

    # write as the new tenant
    r_cust = post("voice/gateway", tool("lookup_or_create_customer", {
        "full_name": "Probe Customer", "email": "cust@probe.test"}, UID))
    check("results" in r_cust, "customer tool answered", json.dumps(r_cust)[:200])
    cust_row = psql("SELECT id, company_id FROM customers WHERE email='cust@probe.test'")
    check(bool(cust_row), "customer created for the new tenant", cust_row)
    if cust_row:
        cid, cco = cust_row.split("|")
        new_cid = psql(f"SELECT cp.id FROM company_profile cp JOIN users u ON u.company_id=cp.id WHERE u.id='{UID}'")
        check(cco == new_cid, "customer landed in the new company", f"{cco} vs {new_cid}")
        r_proj = post("voice/gateway", tool("create_project", {
            "customer_id": cid, "project_name": "Probe Project"}, UID))
        check("results" in r_proj, "project tool answered", json.dumps(r_proj)[:200])
        proj_row = psql("SELECT id, company_id FROM projects WHERE title='Probe Project'")
        check(bool(proj_row), "project created", proj_row)
        if proj_row:
            pid, pco = proj_row.split("|")
            check(pco == new_cid, "project landed in the new company", f"{pco} vs {new_cid}")
        lst = json.dumps(post("voice/gateway", tool("list_projects", {}, UID)))
        check("Probe Project" in lst, "the new tenant sees its own project", lst[:200])
        check("Kitsilano" not in lst and "Oakridge" not in lst,
              "and not the other tenant's", lst[:200])

    # the owner's view is unchanged
    owner = psql("SELECT id FROM users WHERE email='dtam2003@gmail.com'")
    owner_projects = json.dumps(post("voice/gateway", tool("list_projects", {}, owner)))
    check("Kitsilano Reno" in owner_projects, "owner still sees their own projects")
    check("Probe Project" not in owner_projects, "owner does not see the new tenant's project")

    print("P8 - company 1 is untouched")
    check(psql("SELECT md5(row_to_json(cp)::text) FROM company_profile cp WHERE id=1") == ireh_before,
          "Ireh row unchanged")
    check(psql("SELECT count(*) FROM workers WHERE company_id=1") == employees_before,
          "Ireh workers unchanged")

    print("P9 - cleanup")
    psql(f"DELETE FROM invoices WHERE company_id IN (SELECT id FROM company_profile WHERE created_by_user='{UID}')")
    psql(f"DELETE FROM projects WHERE company_id IN (SELECT id FROM company_profile WHERE created_by_user='{UID}')")
    psql(f"DELETE FROM customers WHERE company_id IN (SELECT id FROM company_profile WHERE created_by_user='{UID}')")
    psql(f"DELETE FROM workers WHERE company_id IN (SELECT id FROM company_profile WHERE created_by_user='{UID}')")
    psql(f"DELETE FROM company_profile WHERE created_by_user='{UID}'")
    psql(f"DELETE FROM users WHERE id='{UID}'")
    check(psql(f"SELECT count(*) FROM users WHERE id='{UID}'") == "0", "user removed")
    check(psql(f"SELECT count(*) FROM company_profile WHERE company_name='Probe Co'") == "0",
          "company removed")
    check(psql("SELECT md5(row_to_json(cp)::text) FROM company_profile cp WHERE id=1") == ireh_before,
          "Ireh row still identical after cleanup")

    print()
    if failures:
        print(f"{len(failures)} FAILED")
        return 1
    print("all live onboarding checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
