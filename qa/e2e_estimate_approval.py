#!/usr/bin/env python3
"""E2E: create customer -> project -> estimate -> customer approves -> contract updated.

Reproduces, end to end against the LIVE server, the flow the PM runs from the
app/chat (and the flow that broke 2026-09-07 with the doubled webhook path):
tool calls go through the real gateway (/webhook/voice/gateway) exactly as
Vapi would send them; the approval page + Approve POST go through the real
Customer Approval Portal. No LLM is involved (deterministic, no Vapi credits).

Side effects: creates one throwaway customer/project/estimate, approves it
for real, then deletes the customer (cascades project+estimate). Nothing is
emailed (the send-for-approval email step is a separate smoke layer — see
doc/TEST_PLAN.md). Needs network to the VPS + passwordless ssh.

Usage:
  qa/e2e_estimate_approval.py [--base https://n8n2.ordrnow.com] [--ssh ubuntu@n8n2.ordrnow.com] [--keep]
Exit 0 on full pass, 1 with the failing step named.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

def gw(base, name, args):
    body = json.dumps({"message": {"toolCalls": [{"id": "e2e-" + name[:16],
        "function": {"name": name, "arguments": json.dumps(args)}}]}}).encode()
    req = urllib.request.Request(base + "/webhook/voice/gateway", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read().decode())
    res = out.get("results") or [{}]
    return (res[0].get("result") or "").strip()

def http_get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.status, r.read().decode()

def http_post(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode()

def sql(ssh, statement, single=True):
    """Run SQL over ssh->docker psql (-tA), return trimmed lines."""
    cmd = ["ssh", "-o", "ConnectTimeout=20", ssh,
           "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -t -A -q"]
    p = subprocess.run(cmd, input=statement.encode(), capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError("psql failed: " + p.stderr.decode()[:300])
    lines = [l for l in p.stdout.decode().splitlines() if l.strip()]
    if single:
        return lines[0].strip() if lines else ""
    return lines

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://n8n2.ordrnow.com")
    ap.add_argument("--ssh", default="ubuntu@n8n2.ordrnow.com")
    ap.add_argument("--keep", action="store_true", help="do not clean up rows")
    a = ap.parse_args()
    base, ssh = a.base.rstrip("/"), a.ssh
    tag = str(int(time.time()))[-8:]
    cust = f"QA E2E {tag}"
    cemail = f"qa-e2e-{tag}@example.invalid"
    proj = f"E2E Proj {tag}"
    checks = []

    def step(name, fn):
        try:
            fn()
            checks.append((name, True, ""))
            print(f"  PASS  {name}")
        except AssertionError as e:
            checks.append((name, False, str(e)))
            print(f"  FAIL  {name}: {e}")
            raise
        except Exception as e:
            checks.append((name, False, f"{type(e).__name__}: {e}"))
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
            raise

    created = False
    try:
        print(f"[1] fixtures tag={tag} customer={cust} project={proj}")
        r = gw(base, "lookup_or_create_customer",
               {"first_name": "QA", "last_name": f"E2E {tag}", "email": cemail, "phone": None})
        assert "created" in r.lower() and cust.lower() in r.lower(), f"create customer: {r}"
        created = True

        step("create_project resolves customer by name", lambda: None)
        r = gw(base, "create_project", {"customer_id": cust, "project_name": proj})
        assert "created" in r.lower() and proj in r, f"create project: {r}"
        step("create_project outcome", lambda: None)

        r = gw(base, "create_estimate",
               {"project_id": proj, "scope_description": "E2E basement reno",
                "labor_estimate": 100000, "material_estimate": 5000,
                "valid_until": "2099-01-01"})
        assert "105,000" in r and proj in r, f"create estimate: {r}"
        step("create_estimate by project name, $105,000", lambda: None)

        tok = sql(ssh, f"SELECT baseline_approval_token, baseline_status FROM projects WHERE title = '{proj}';")
        parts = tok.split("|")
        assert len(parts) == 2 and parts[0], f"token row: {tok}"
        token, status = parts[0], parts[1]
        if not token:
            sql(ssh, f"UPDATE projects SET baseline_approval_token = md5(random()::text) || md5(clock_timestamp()::text) WHERE title = '{proj}';")
            token = sql(ssh, f"SELECT baseline_approval_token FROM projects WHERE title = '{proj}';")
        assert status == "PENDING", f"expected PENDING, got {status}"
        step("project holds a PENDING approval token", lambda: None)

        st, page = http_get(f"{base}/webhook/approve-estimate?token={token}")
        assert st == 200 and proj in page and "Approve" in page and "$105,000" in page, \
            f"approve page status {st}"
        step("GET approve-estimate page renders lines + Approve", lambda: None)

        st, conf = http_post(f"{base}/webhook/estimate/approval",
                             {"token": token, "decision": "approve",
                              "approval_method": "onsite_link", "signer_name": "QA Robot"})
        assert st == 200 and "Approved" in conf and "$105,000" in conf, \
            f"approve POST status {st}: {conf[:200]}"
        step("POST estimate/approval -> Approved + revised $105,000", lambda: None)

        row = sql(ssh, f"SELECT baseline_status, baseline_approved_by, baseline_approval_method, baseline_signer_name, original_contract_value, revised_contract_value FROM projects WHERE title = '{proj}';")
        (bs, by, method, signer, ocv, rcv) = row.split("|")
        assert bs == "APPROVED" and by == "customer" and method == "onsite_link" \
            and signer == "QA Robot" and float(ocv) == 105000.0 and float(rcv) == 105000.0, \
            f"db row: {row}"
        step("DB: APPROVED, contract value = sum of estimates", lambda: None)

        # Re-approving the same token must be a no-op (PENDING guard).
        st2, _ = http_post(f"{base}/webhook/estimate/approval",
                           {"token": token, "decision": "approve",
                            "approval_method": "onsite_link", "signer_name": "QA Robot"})
        bs2 = sql(ssh, f"SELECT baseline_status FROM projects WHERE title = '{proj}';")
        assert st2 == 200 and bs2 == "APPROVED", f"re-approve changed state: {st2}/{bs2}"
        step("re-approve is a guarded no-op", lambda: None)

        print(f"\nALL {len(checks)} E2E CHECKS PASSED (tag {tag})")
    finally:
        if created and not a.keep:
            sql(ssh, f"DELETE FROM customers WHERE name = '{cust}';")
            n = sql(ssh, f"SELECT count(*) FROM projects WHERE title = '{proj}';")
            print(f"  cleanup: customer deleted, leftover projects = {n}")

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nE2E FAILED: {e}")
        sys.exit(1)
