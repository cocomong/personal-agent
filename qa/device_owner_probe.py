#!/usr/bin/env python3
"""Live probe: a push registration belongs to the signed-in user.

  python3 qa/device_owner_probe.py

Uses throwaway users and fake FCM tokens, and cleans up after itself.

  P1  register with the owner's session      -> registered, company 1, user_id set
  P2  a second user (company 2) registers    -> its own row, company 2
  P3  company 1's push query sees only its own tokens
  P4  a signed-in user with no company       -> not stored (nothing to push)
  P5  no session token                       -> 401, nothing stored
  P6  unregister removes the row; repeat is a no-op
  P7  one user cannot unregister another user's phone
  P8  cleanup leaves no rows
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import onboarding_probe as base  # psql, mint_token, HOST

BASE = "https://n8n2.ordrnow.com/webhook"
UID_A = "aaaaaaaa-1111-2222-3333-444444444444"   # company 2
UID_N = "bbbbbbbb-1111-2222-3333-444444444444"   # no company yet
TOK_A = "probe-fcm-token-A"
TOK_N = "probe-fcm-token-N"
TOK_OWNER = "probe-fcm-token-owner"

failures = []


def check(cond, msg, extra=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}" + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        failures.append(msg)


def post(path, body, token=None):
    req = urllib.request.Request(f"{BASE}/{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    if token:
        req.add_header("X-User-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def rows(token):
    return base.psql(f"SELECT coalesce(user_id::text,'NULL')||'|'||company_id FROM device_tokens WHERE token='{token}'")


def main():
    owner_id = base.psql("SELECT id FROM users WHERE email='dtam2003@gmail.com'")
    owner_tok = base.mint_token(owner_id)

    # fixture: a company-2 user and a company-less user.
    # Order matters: device_tokens -> company_profile -> users (FKs).
    def purge_fixture():
        base.psql("DELETE FROM device_tokens WHERE company_id IN "
                  f"(SELECT id FROM company_profile WHERE created_by_user = '{UID_A}')")
        base.psql("DELETE FROM device_tokens WHERE user_id IN "
                  f"('{UID_A}','{UID_N}')")
        base.psql(f"DELETE FROM company_profile WHERE created_by_user = '{UID_A}'")
        base.psql(f"DELETE FROM users WHERE id IN ('{UID_A}','{UID_N}')")

    purge_fixture()
    base.psql(f"INSERT INTO users (id, google_sub, email, name) VALUES "
              f"('{UID_N}','probe-sub-n','probe-n@test.local','NoCompany')")
    base.psql(f"INSERT INTO users (id, google_sub, email, name) VALUES "
              f"('{UID_A}','probe-sub-a','probe-a@test.local','Company A')")
    cid = base.psql(
        "WITH ins AS (INSERT INTO company_profile (company_name, legal_name, street_address, city, "
        "province, postal_code, phone, email_from, email_from_name, signature_name, "
        "created_by_user, setup_completed_at) VALUES "
        f"('Probe Co','Probe Co','1 A St','Coquitlam','BC','V3K 1A1','',"
        f"'probe-a@test.local','Probe Co','Probe', '{UID_A}', now()) RETURNING id) "
        "SELECT id FROM ins")
    base.psql(f"UPDATE users SET company_id = {cid} WHERE id = '{UID_A}'")
    tok_a = base.mint_token(UID_A)
    tok_n = base.mint_token(UID_N)

    print("P1 - owner registers this phone")
    st, body = post("device/register", {"token": TOK_OWNER, "platform": "android", "device_name": "probe"}, owner_tok)
    check(st == 200 and body.get("registered") is True, "owner token registered", f"{st} {body}")
    r = rows(TOK_OWNER)
    check(r == f"{owner_id}|1", "row carries the owner's user id and company 1", r)

    print("P2 - a second company registers its own phone")
    st, body = post("device/register", {"token": TOK_A, "platform": "android"}, tok_a)
    check(st == 200 and body.get("registered") is True, "second company registered", f"{st} {body}")
    r = rows(TOK_A)
    check(r == f"{UID_A}|{cid}", "row carries its own user id and company", r)

    print("P3 - a company's push list excludes the other company's phone")
    listed = base.psql(
        "SELECT string_agg(token, ',') FROM device_tokens WHERE company_id = 1")
    check(TOK_OWNER in (listed or ""), "company 1 sees its own token", listed)
    check(TOK_A not in (listed or ""), "company 1 does not see company 2's token", listed)

    print("P4 - a signed-in user with no company is not a push target")
    st, body = post("device/register", {"token": TOK_N, "platform": "android"}, tok_n)
    check(st == 200 and body.get("registered") is False, "no-company user is not registered", f"{st} {body}")
    check(rows(TOK_N) == "", "no row written for the no-company user")

    print("P5 - no session token")
    st, body = post("device/register", {"token": "probe-fcm-unauth", "platform": "android"})
    check(st == 401, "unauthenticated registration refused", str(st))
    check(rows("probe-fcm-unauth") == "", "nothing stored without a session")

    print("P6 - unregister removes exactly this phone")
    st, body = post("device/unregister", {"token": TOK_OWNER}, owner_tok)
    check(st == 200 and int(body.get("removed", -1)) == 1, "row removed", f"{st} {body}")
    check(rows(TOK_OWNER) == "", "row gone")
    st, body = post("device/unregister", {"token": TOK_OWNER}, owner_tok)
    check(st == 200 and int(body.get("removed", -1)) == 0, "repeat is a no-op", f"{st} {body}")

    print("P7 - one user cannot remove another user's phone")
    st, body = post("device/unregister", {"token": TOK_A}, owner_tok)
    check(int(body.get("removed", -1)) == 0, "owner cannot delete company 2's phone", str(body))
    check(rows(TOK_A) == f"{UID_A}|{cid}", "company 2's row still intact")

    print("P8 - cross-user re-registration re-homes the phone")
    st, body = post("device/register", {"token": TOK_A, "platform": "android"}, owner_tok)
    check(st == 200 and body.get("registered") is True, "same phone registered to the owner", f"{st} {body}")
    r = rows(TOK_A)
    check(r == f"{owner_id}|1", "token moved to the owner's account (one row)", r)
    check(base.psql(f"SELECT count(*) FROM device_tokens WHERE token='{TOK_A}'") == "1",
          "still exactly one row for that token")

    print("P9 - cleanup")
    base.psql(f"DELETE FROM device_tokens WHERE token IN ('{TOK_OWNER}','{TOK_A}','{TOK_N}')")
    purge_fixture()
    check(base.psql("SELECT count(*) FROM device_tokens") == "0", "no device rows left")
    check(base.psql(f"SELECT count(*) FROM users WHERE id IN ('{UID_A}','{UID_N}')") == "0",
          "probe users removed")

    print()
    if failures:
        print(f"{len(failures)} FAILED")
        return 1
    print("all device-owner checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
