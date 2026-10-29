#!/usr/bin/env python3
"""L2: exercise the onboarding SQL against LIVE Postgres inside one transaction.

Nothing is committed: everything runs between BEGIN and ROLLBACK, with the
assertions inside SQL, so a failure exits non-zero and the database is untouched.

  python3 qa/onboarding_scope_db_test.py

Checks
  D1  scope: a signed-in user with no company resolves to NULL (never 1)
  D2  ensure_company creates a row with every tenant field explicit
      (no Ireh name/address/phone/email; sender = the user's own email)
  D3  link_user binds the user to the new company; scope now resolves to it
  D4  re-running ensure_company creates nothing (idempotent)
  D5  complete_onboarding without a business address does NOT complete setup
  D6  complete_onboarding with an address completes setup
  D7  workers created during onboarding land in the new company only
  D8  company 1 (Ireh) is identical before and after
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GW = os.path.join(ROOT, "backend", "n8n", "workflows", "voice-gateway.json")
HOST = "ubuntu@n8n2.ordrnow.com"
CONTAINER = "n8n-compose-postgres-1"

UID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
EMAIL = "newuser@test.local"


def node_sql(name):
    w = json.load(open(GW))
    for n in w["nodes"]:
        if n["name"] == name:
            return n["parameters"]["query"]
    raise SystemExit(f"node not found: {name}")


def bind(sql, *params):
    """Substitute $1..$n with SQL literals (None -> NULL).

    Longest placeholder first: replacing $1 before $10 corrupts the latter.
    """
    for i in range(len(params), 0, -1):
        val = params[i - 1]
        lit = "NULL" if val is None else "'" + str(val).replace("'", "''") + "'"
        sql = sql.replace(f"${i}", lit)
    return sql


def subst(sql, mapping):
    """Replace explicit placeholders, longest first ($12 before $1)."""
    for key in sorted(mapping, key=len, reverse=True):
        sql = sql.replace(key, mapping[key])
    return sql


def main():
    scope = node_sql("Resolve Call Scope")
    ensure = node_sql("Exec: ensure_company")
    link = node_sql("Exec: link_user")
    profile = node_sql("Exec: complete_onboarding_profile")
    workers = node_sql("Exec: complete_onboarding_workers")

    NEW_ID = f"(SELECT id FROM company_profile WHERE created_by_user = '{UID}')"

    def ensure_call(**kw):
        return bind(ensure, UID,
                    kw.get("name"), kw.get("pm"), kw.get("pref"),
                    kw.get("street"), kw.get("city"), kw.get("province"),
                    kw.get("postal"), kw.get("phone"), kw.get("email"),
                    kw.get("gst"), kw.get("pst"), kw.get("pay"))

    def profile_call(street="", city="", province="", postal="", invoice=None):
        def lit(v):
            return "NULL" if v in (None, "") else "'" + str(v).replace("'", "''") + "'"
        return subst(profile, {
            "$1": NEW_ID + "::smallint",
            "$2": "'Test Co'", "$3": "'Test Owner'", "$4": "'Tester'",
            "$5": lit(street), "$6": lit(city), "$7": lit(province),
            "$8": lit(postal), "$9": "NULL", "$10": "NULL", "$11": "NULL",
            "$12": lit(invoice),
        })

    def ensure_call_min(**kw):
        return bind(ensure, "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
                    kw.get("name"), None, None, None, None, None, None,
                    None, None, None, None, None)

    workers_payload = """'[{"name":"Sam Smith","trade":"carpenter","hourly_rate":"45"}]'::jsonb"""

    parts = [
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        f"INSERT INTO users (id, google_sub, email, name) VALUES ('{UID}', 'sub-test-newuser', '{EMAIL}', 'New User');",
        "CREATE TEMP TABLE ireh_before AS SELECT * FROM company_profile WHERE id = 1;",

        # D1 - scope before any company exists
        f"CREATE TEMP TABLE scope_before AS {bind(scope, UID)};",
        """DO $$
DECLARE v smallint;
BEGIN
  SELECT company_id INTO v FROM scope_before;
  IF v IS NOT NULL THEN RAISE EXCEPTION 'D1 FAIL: onboarding user scoped to % (must be NULL)', v; END IF;
  RAISE NOTICE 'D1 OK (onboarding user has no company)';
END $$;""",

        # D2 - create the company
        ensure_call(name="Test Co", pm="Test Owner", pref="Tester"),
        f"UPDATE users SET company_id = {NEW_ID} WHERE id = '{UID}' AND company_id IS NULL;",
        """DO $$
DECLARE v_id smallint; v_name text; v_email text; v_phone text; v_setup timestamptz;
BEGIN
  SELECT id, company_name, email_from, phone, setup_completed_at
    INTO v_id, v_name, v_email, v_phone, v_setup
    FROM company_profile WHERE created_by_user = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
  IF v_id IS NULL THEN RAISE EXCEPTION 'D2 FAIL: no company created'; END IF;
  IF v_name <> 'Test Co' THEN RAISE EXCEPTION 'D2 FAIL: name=%', v_name; END IF;
  IF v_email <> 'newuser@test.local' THEN RAISE EXCEPTION 'D2 FAIL: sender=%', v_email; END IF;
  IF v_phone <> '' THEN RAISE EXCEPTION 'D2 FAIL: phone=%', v_phone; END IF;
  IF v_setup IS NOT NULL THEN RAISE EXCEPTION 'D2 FAIL: setup completed with no address'; END IF;
  IF EXISTS (SELECT 1 FROM company_profile WHERE id = v_id
              AND (street_address = '1951 Kaptey Ave' OR signature_name = 'Dave'
                   OR email_from = 'support.ordrnow@gmail.com' OR postal_code = 'V3K 5Z7')) THEN
    RAISE EXCEPTION 'D2 FAIL: inherited another tenant identity';
  END IF;
  RAISE NOTICE 'D2 OK (company % created, no inherited identity)', v_id;
END $$;""",

        # D3 - link + scope resolves to the new company
        subst(link, {"$1": f"'{UID}'", "$2": f"{NEW_ID}::smallint"}),
        f"CREATE TEMP TABLE scope_after AS {bind(scope, UID)};",
        f"""DO $$
DECLARE v smallint; newid smallint;
BEGIN
  SELECT id INTO newid FROM company_profile WHERE created_by_user = '{UID}';
  SELECT company_id INTO v FROM scope_after;
  IF v IS DISTINCT FROM newid THEN RAISE EXCEPTION 'D3 FAIL: scope=% new=%', v, newid; END IF;
  RAISE NOTICE 'D3 OK (scope resolves to %)', v;
END $$;""",

        # D4 - idempotent create
        """DO $$
DECLARE before int; after int;
BEGIN
  SELECT count(*) INTO before FROM company_profile;
END $$;""",
        ensure_call(name="Test Co"),
        """DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM company_profile WHERE created_by_user = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
  IF n <> 1 THEN RAISE EXCEPTION 'D4 FAIL: % companies for one user', n; END IF;
  RAISE NOTICE 'D4 OK (idempotent)';
END $$;""",

        # D5 - no address: setup stays open
        profile_call(),
        """DO $$
DECLARE v boolean;
BEGIN
  SELECT setup_completed_at IS NOT NULL INTO v FROM company_profile
   WHERE created_by_user = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
  IF v THEN RAISE EXCEPTION 'D5 FAIL: completed without a business address'; END IF;
  RAISE NOTICE 'D5 OK (setup blocked until the address is given)';
END $$;""",

        # D6/D7 - full address completes setup; workers stay in the new company
        profile_call(street="123 Test St", city="Coquitlam", province="BC", postal="V3K 1A1"),
        subst(workers, {"$1": f"{NEW_ID}::smallint", "$2": workers_payload}),
        """DO $$
DECLARE v boolean; n int; wid smallint;
BEGIN
  SELECT setup_completed_at IS NOT NULL INTO v FROM company_profile
   WHERE created_by_user = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
  IF NOT v THEN RAISE EXCEPTION 'D6 FAIL: setup did not complete with a full address'; END IF;
  SELECT id INTO wid FROM company_profile WHERE created_by_user = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
  SELECT count(*) INTO n FROM workers WHERE company_id = wid AND name = 'Sam Smith';
  IF n <> 1 THEN RAISE EXCEPTION 'D7 FAIL: worker missing from the new company'; END IF;
  SELECT count(*) INTO n FROM workers WHERE company_id = 1 AND name = 'Sam Smith';
  IF n <> 0 THEN RAISE EXCEPTION 'D7 FAIL: worker leaked into company 1'; END IF;
  RAISE NOTICE 'D6-D7 OK';
END $$;""",

        # D2b - minimal answers must still create a valid row (NOT NULL gaps)
        "INSERT INTO users (id, google_sub, email, name) VALUES ('bbbbbbbb-cccc-dddd-eeee-ffffffffffff', 'sub-test-minimal', 'minimal@test.local', 'Min');",
        ensure_call_min(name="Min Co"),
        """DO $$
DECLARE v_sign text; v_name text;
BEGIN
  SELECT signature_name, company_name INTO v_sign, v_name
    FROM company_profile WHERE created_by_user = 'bbbbbbbb-cccc-dddd-eeee-ffffffffffff';
  IF v_name IS NULL THEN RAISE EXCEPTION 'D2b FAIL: minimal row not created'; END IF;
  IF v_sign IS NULL THEN RAISE EXCEPTION 'D2b FAIL: signature_name left NULL'; END IF;
  RAISE NOTICE 'D2b OK (minimal answers still valid)';
END $$;""",

        # D8 - Ireh untouched
        """DO $$
BEGIN
  IF EXISTS (SELECT * FROM ireh_before EXCEPT SELECT * FROM company_profile WHERE id = 1)
  OR EXISTS (SELECT * FROM company_profile WHERE id = 1 EXCEPT SELECT * FROM ireh_before) THEN
    RAISE EXCEPTION 'D8 FAIL: company 1 changed';
  END IF;
  RAISE NOTICE 'D8 OK (company 1 identical)';
END $$;""",

        "ROLLBACK;",
    ]

    script = "\n\n".join(parts) + "\n"
    with open("/tmp/onboarding_db_test.sql", "w") as fh:
        fh.write(script)

    cmd = ["ssh", "-o", "ConnectTimeout=10", HOST,
           f"sudo docker exec -i {CONTAINER} psql -U postgres -d postgres -q"]
    proc = subprocess.run(cmd, stdin=open("/tmp/onboarding_db_test.sql"),
                          capture_output=True, text=True, timeout=180)
    out = (proc.stdout + proc.stderr).strip()
    print(out)
    if proc.returncode != 0 or "FAIL" in out:
        print("\nFAILED")
        return 1
    print("\nall DB checks passed (rolled back)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
