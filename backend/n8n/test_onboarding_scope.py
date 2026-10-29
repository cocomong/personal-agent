#!/usr/bin/env python3
"""Offline harness for per-user company scope (new-user onboarding).

Runs the REAL jsCode from the workflows against fixtures (no n8n, no network)
and asserts the SQL/wiring properties a syntax check cannot see.

  python3 backend/n8n/test_onboarding_scope.py

Covers:
  H1 - hook: a logged-in user with NO company gets the setup greeting, blank
       company name, onboarding_steps, and their user_id in variableValues.
  H2 - hook: a set-up company still gets the normal greeting (regression).
  H3 - hook SQL: three-way scope, no COALESCE(..., 1) for logged-in users.
  H4 - hook SQL: the pending call row is skipped when there is no company.
  H5 - hook wiring: scope resolves before the pending row is written.
  H6 - onboarding text: the business address is required.
  G1 - gateway: scope node reads user_id, guard allowlists only the two
       onboarding tools, and no SQL node still pins company_id = 1.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
HOOK = os.path.join(HERE, "workflows", "vapi-assistant-hook.json")
GATEWAY = os.path.join(HERE, "workflows", "voice-gateway.json")

NODE_RUNNER = r"""
const fs = require('fs');
const code = fs.readFileSync(process.env.CODE_PATH, 'utf8');
const payload = JSON.parse(process.env.FIXTURE || '{}');
const nodeOutputs = JSON.parse(process.env.NODE_OUTPUTS || '{}');
const $input = { first: () => ({ json: payload }), all: () => [{ json: payload }] };
const $env = { AUTH_TOKEN_SECRET: 'test-secret' };
// Fall back to the fixture payload: Build Hook Variables reads the setup row by
// node name, and most fixtures supply it as the input item.
const $ = (name) => ({ first: () => ({ json: nodeOutputs[name] || payload }) });
const fn = new Function('$input', '$env', '$', 'return (async () => {' + code + '})();');
fn($input, $env, $)
  .then((r) => { process.stdout.write(JSON.stringify(r)); })
  .catch((e) => { process.stderr.write('ERR ' + e.message); process.exit(1); });
"""

failures = []


def check(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        failures.append(msg)


def run_node(js, fixture, node_outputs=None):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        code_path = fh.name
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(NODE_RUNNER)
        runner = fh.name
    env = dict(os.environ, CODE_PATH=code_path,
               FIXTURE=json.dumps(fixture),
               NODE_OUTPUTS=json.dumps(node_outputs or {}))
    proc = subprocess.run(["node", runner], capture_output=True, text=True, env=env, timeout=30)
    if proc.returncode != 0:
        raise SystemExit(f"node failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def wf(path):
    return json.load(open(path))


def node(w, name):
    for n in w["nodes"]:
        if n["name"] == name:
            return n
    raise SystemExit(f"node not found: {name}")


# --------------------------------------------------------------------------- #
print("H1/H2 - hook variables")
hook = wf(HOOK)
build = node(hook, "Build Hook Variables")["parameters"]["jsCode"]

onboarding_row = {
    "setup_complete": False, "company_name": "", "pm_preferred_name": "",
    "company_id": None, "user_id": "11111111-2222-3333-4444-555555555555",
    "last_call_ctx": None, "last_call_ended_at": None, "last_call_ended_reason": None,
}
out = run_node(build, onboarding_row,
              {"Exec: read_setup_status": onboarding_row,
               "Exec: start_call_row": {"call_ref": ""}})[0]["json"]
vv = out["assistantOverrides"]["variableValues"]
check(str(vv["setup_complete"]).lower() == "false", "new user: setup_complete is false")
check(vv["company_name"] == "", "new user: company_name is blank (not Ireh)")
check(vv["user_id"] == onboarding_row["user_id"], "new user: user_id transported")
check(vv["company_scope"] == "", "new user: company_scope is empty (no company yet)")
check("company name" in out["assistantOverrides"]["firstMessage"].lower(),
      "new user: greeting asks for the company name")
check(len(vv["onboarding_steps"]) > 100, "new user: onboarding_steps injected")

ready_row = dict(onboarding_row, setup_complete=True, company_name="Ireh Construction",
                 pm_preferred_name="Dave", company_id=1)
out2 = run_node(build, ready_row,
              {"Exec: read_setup_status": ready_row,
               "Exec: start_call_row": {"call_ref": "abc"}})[0]["json"]
vv2 = out2["assistantOverrides"]["variableValues"]
check("set you up" not in out2["assistantOverrides"]["firstMessage"].lower(),
      "set-up company: no setup greeting")
check("Dave" in out2["assistantOverrides"]["firstMessage"], "set-up company: greeting names the PM")
check(vv2["company_name"] == "Ireh Construction", "set-up company: company name intact")
check(vv2["onboarding_steps"] == "", "set-up company: onboarding_steps empty")
check(vv2["company_scope"] == "1", "set-up company: company_scope 1")

# --------------------------------------------------------------------------- #
print("H3 - read_setup_status SQL")
sql = node(hook, "Exec: read_setup_status")["parameters"]["query"]
check("COALESCE((SELECT company_id FROM users" not in sql, "no COALESCE(..., 1) fallback")
check("CASE WHEN me.uid IS NULL THEN 1 END" in sql, "legacy fallback is explicit and token-only")
check("scope.company_id" in sql and "AS user_id" in sql, "returns company_id + user_id")
check("LEFT JOIN company_profile cp ON cp.id = scope.company_id" in sql,
      "a company-less user yields no company row (not company 1)")
check("interval '7 days'" in sql and "interval '30 seconds'" in sql,
      "recent-context window preserved")

# --------------------------------------------------------------------------- #
print("H4/H5 - pending row + wiring")
start_sql = node(hook, "Exec: start_call_row")["parameters"]["query"]
check("WHERE scope.company_id IS NOT NULL" in start_sql, "pending row only when a company exists")
check("COALESCE((SELECT call_ref::text FROM ins), '')" in start_sql, "returns an empty call_ref safely")
conns = hook["connections"]
check(conns["Resolve Company Scope"]["main"][0][0]["node"] == "Exec: read_setup_status",
      "scope resolves before the pending row")
check(conns["Exec: read_setup_status"]["main"][0][0]["node"] == "Exec: start_call_row",
      "pending row runs after scope")
check(conns["Exec: start_call_row"]["main"][0][0]["node"] == "Build Hook Variables",
      "variables built last")

# --------------------------------------------------------------------------- #
print("H6 - onboarding text")
check("REQUIRED - setup cannot complete without it" in build, "billing address is mandatory")

# --------------------------------------------------------------------------- #
print("G1 - gateway scope + guard")
gw = wf(GATEWAY)
names = [n["name"] for n in gw["nodes"]]
check("Extract Tool Call" in names, "Extract Tool Call node exists")
if "Extract Tool Call" in names:
    ex = node(gw, "Extract Tool Call")["parameters"]["jsCode"]
    check("assistantOverrides" in ex and "variableValues" in ex,
          "caller identity read from assistantOverrides.variableValues")
    check("metadata" in ex, "metadata provides the fallback identity")

check("Resolve Call Scope" in names, "Resolve Call Scope node exists")
if "Resolve Call Scope" in names:
    scope_sql = node(gw, "Resolve Call Scope")["parameters"]["query"]
    check("CASE WHEN NULLIF(btrim($1::text), '') IS NULL THEN 1 END" in scope_sql.replace("\n", " "),
          "only a missing user id falls back to company 1")
    check("FROM users u" in scope_sql, "a company comes from the users row")

norm = node(gw, "Normalize Tool Call")["parameters"]["jsCode"]
check("ONBOARDING_ACTIONS" in norm and "get_onboarding_status" in norm
      and "complete_onboarding" in norm, "only the two onboarding tools pass with no company")
check("refusal" in norm, "refusal is computed per call")
check("companyId === null" in norm, "a company-less caller is refused data work")

guard = [n for n in gw["nodes"] if n["name"] == "Onboarding Guard"]
check(len(guard) == 1, "Onboarding Guard node exists")
if guard:
    conns = gw["connections"]["Onboarding Guard"]["main"]
    check(conns[0][0]["node"] == "Actions Sub-Router", "allowed -> router")
    check(conns[1][0]["node"] == "Respond Setup First", "refused -> spoken refusal")

ob = gw["connections"]["Actions Sub-Router"]["main"]
rules = node(gw, "Actions Sub-Router")["parameters"]["rules"]["values"]
idx = [i for i, v in enumerate(rules) if v["outputKey"] == "complete_onboarding"][0]
check(ob[idx][0]["node"] == "Exec: ensure_company", "complete_onboarding creates the company first")
check(gw["connections"]["Exec: ensure_company"]["main"][0][0]["node"] == "Exec: link_user",
      "the user is linked before any company row is written")
check(gw["connections"]["Exec: link_user"]["main"][0][0]["node"] == "Exec: complete_onboarding_workers",
      "workers run against the new company")

ensure = node(gw, "Exec: ensure_company")["parameters"]["query"]
check("AND u.company_id IS NULL" in ensure, "company created only for a user without one")
check("ON CONFLICT (created_by_user)" in ensure, "create is idempotent")
for col in ("company_name", "street_address", "phone", "email_from", "signature_name"):
    check(col in ensure.split("SELECT", 1)[0], f"ensure_company sets {col} explicitly")
check("WHERE id = 1" not in node(gw, "Exec: complete_onboarding_profile")["parameters"]["query"],
      "complete_onboarding_profile no longer targets company 1")
check("WHERE id = 1" not in node(gw, "Exec: get_onboarding_status")["parameters"]["query"],
      "get_onboarding_status no longer targets company 1")

# P1 (2026-10-30) scoped every tenant query: nothing may pin company_id = 1.
KNOWN_UNSCOPED: set = set()
offenders = set()
for n in gw["nodes"]:
    q = n.get("parameters", {}).get("query")
    if q and re.search(r"company_id\s*=\s*1\b", q):
        offenders.add(n["name"])
check(offenders <= KNOWN_UNSCOPED,
      f"no node pins company_id = 1 (unscoped: {sorted(offenders)})")

# every SQL node that touches tenant tables must carry a company predicate
TENANT_SQL = re.compile(
    r"\b(customers|projects|invoices|workers|payroll_runs|schedule_items|device_tokens|timesheets)\b")
unscoped = []
for n in gw["nodes"]:
    q = n.get("parameters", {}).get("query")
    if not q or not TENANT_SQL.search(q):
        continue
    # Scoped either by a company_id predicate or by joining company_profile on
    # the caller's company (cp.id = $n), or through the scoped payroll function.
    if ("company_id" in q or "fn_run_payroll_for_company" in q
            or re.search(r"cp\.id\s*=\s*\$\d+", q)):
        continue
    unscoped.append(n["name"])
check(not unscoped, f"every tenant query is company-scoped (unscoped: {sorted(unscoped)})")

# --------------------------------------------------------------------------- #
print()
if failures:
    print(f"{len(failures)} FAILED")
    sys.exit(1)
print("all onboarding-scope checks passed")
