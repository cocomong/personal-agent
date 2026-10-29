#!/usr/bin/env python3
"""Patch the n8n workflows for per-user company scope (new-user onboarding).

Idempotent: every operation rewrites a node to a fixed target state, so running
it twice is a no-op. Run with --check to only report.

What it changes (2026-10-30):
  vapi-assistant-hook.json
    - Exec: read_setup_status  -> three-way scope, no COALESCE(..., 1) for a
      logged-in user with no company; also returns company_id + user_id.
    - Exec: start_call_row     -> skips the pending row when there is no company.
    - wiring                   -> read_setup_status BEFORE start_call_row.
    - Build Hook Variables      -> adds user_id / company_scope to variableValues
      so the gateway can identify the caller on Vapi tool-call events.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = ROOT / "backend" / "n8n" / "workflows" / "vapi-assistant-hook.json"

READ_SETUP_SQL = """WITH me AS (
  SELECT u.id AS uid, u.company_id
    FROM users u
   WHERE u.id = NULLIF(btrim($1::text), '')::uuid
), scope AS (
  -- Three-way scope: logged-in user with a company -> that company;
  -- logged-in user with no company (onboarding) -> NULL, NOT company 1;
  -- no/invalid token (legacy client) -> company 1.
  SELECT me.uid,
         COALESCE(me.company_id, CASE WHEN me.uid IS NULL THEN 1 END) AS company_id
    FROM (SELECT 1) one
    LEFT JOIN me ON true
)
SELECT COALESCE(cp.setup_completed_at IS NOT NULL, false) AS setup_complete,
       COALESCE(cp.company_name, '')      AS company_name,
       COALESCE(cp.pm_preferred_name, '') AS pm_preferred_name,
       scope.company_id,
       COALESCE(scope.uid::text, '')      AS user_id,
       lc.ctx            AS last_call_ctx,
       lc.ended_at       AS last_call_ended_at,
       lc.ended_reason   AS last_call_ended_reason
  FROM scope
  LEFT JOIN company_profile cp ON cp.id = scope.company_id
  LEFT JOIN LATERAL (
        SELECT right(COALESCE(vc.summary, vc.transcript), 900) AS ctx,
               vc.ended_at, vc.ended_reason
          FROM voice_calls vc
         WHERE vc.company_id = scope.company_id
           AND vc.status = 'reported'
           AND vc.ended_at > now() - interval '7 days'
           AND vc.ended_at < now() - interval '30 seconds'
         ORDER BY vc.ended_at DESC
         LIMIT 1
  ) lc ON true
 LIMIT 1;"""

START_CALL_SQL = """-- voice_calls.company_id and call_ref are both NOT NULL, so a caller with no
-- company yet (onboarding) has no pending row: the report then lands as
-- 'unmatched:' instead of failing the hook.
WITH scope AS (
  SELECT NULLIF(btrim($1::text), '')::smallint AS company_id
), ins AS (
  INSERT INTO voice_calls (company_id, call_ref)
  SELECT scope.company_id, gen_random_uuid() FROM scope
   WHERE scope.company_id IS NOT NULL
  RETURNING call_ref
)
SELECT COALESCE((SELECT call_ref::text FROM ins), '') AS call_ref;"""


def node(w, name):
    for n in w["nodes"]:
        if n["name"] == name:
            return n
    raise SystemExit(f"FAIL: node not found: {name}")


def patch_hook(w):
    changes = []

    hook_vars = node(w, "Build Hook Variables")
    code = hook_vars["parameters"]["jsCode"]

    # 1. scope variables in Build Hook Variables
    if "const userId = String(row.user_id" not in code:
        anchor = "const name = String(row.pm_preferred_name || '').trim();"
        if anchor not in code:
            raise SystemExit("FAIL: Build Hook Variables anchor missing")
        code = code.replace(
            anchor,
            anchor
            + "\n\n// Who is calling (echoed back to the gateway on tool-call events so the\n"
            "// gateway can scope every query; empty for legacy unauthenticated clients).\n"
            "const userId = String(row.user_id || '').trim();\n"
            "const companyScope =\n"
            "  row.company_id === null || row.company_id === undefined ? '' : String(row.company_id);",
            1,
        )
        changes.append("Build Hook Variables: scope vars")

    if "user_id: userId" not in code:
        code = code.replace(
            "  recent_context: recentContext,\n};",
            "  recent_context: recentContext,\n"
            "  // Transport for the caller identity: assistantOverrides.variableValues is\n"
            "  // proven to round-trip on Vapi server events (call_ref uses the same path).\n"
            "  user_id: userId,\n"
            "  company_scope: companyScope,\n};",
            1,
        )
        changes.append("Build Hook Variables: user_id/company_scope")

    # 1b. the setup row is no longer the last node: read it by name
    if "const row = $('Exec: read_setup_status').first().json;" not in code:
        if "const row = $input.first().json;" not in code:
            raise SystemExit("FAIL: Build Hook Variables row source not found")
        code = code.replace(
            "const row = $input.first().json;",
            "// The scope/setup row is resolved BEFORE the pending call row now, so\n"
            "// read it by node name instead of relying on item order.\n"
            "const row = $('Exec: read_setup_status').first().json;",
            1,
        )
        changes.append("Build Hook Variables: read setup row by node")

    # 2. the billing address is mandatory at setup (user decision 2026-10-30)
    old_addr = (
        "  '  4. Ask for the company billing address (street, city, province, postal code) -',\n"
        "  '     it appears on every client invoice.',"
    )
    new_addr = (
        "  '  4. Ask for the company billing address (street, city, province, postal code).',\n"
        "  '     It is REQUIRED - setup cannot complete without it, and it appears on',\n"
        "  '     every client invoice. If they resist, say that once and keep going.',"
    )
    if old_addr in code:
        code = code.replace(old_addr, new_addr, 1)
        changes.append("Build Hook Variables: address is required")
    elif new_addr not in code:
        raise SystemExit("FAIL: onboarding step 4 text not found in expected form")

    hook_vars["parameters"]["jsCode"] = code

    # 3. read_setup_status: three-way scope
    rss = node(w, "Exec: read_setup_status")
    if rss["parameters"]["query"].strip() != READ_SETUP_SQL.strip():
        rss["parameters"]["query"] = READ_SETUP_SQL
        changes.append("read_setup_status: three-way scope")

    # 4. start_call_row: no pending row without a company
    scr = node(w, "Exec: start_call_row")
    if scr["parameters"]["query"].strip() != START_CALL_SQL.strip():
        scr["parameters"]["query"] = START_CALL_SQL
        scr["parameters"].setdefault("options", {})["queryReplacement"] = (
            "={{ [$('Exec: read_setup_status').first().json.company_id] }}"
        )
        changes.append("start_call_row: skip without company")

    # 5. wiring: scope must resolve before the pending row is created
    conns = w["connections"]
    if conns.get("Resolve Company Scope", {}).get("main", [[{}]])[0][0]["node"] != "Exec: read_setup_status":
        conns["Resolve Company Scope"] = {"main": [[{"node": "Exec: read_setup_status", "type": "main", "index": 0}]]}
        conns["Exec: read_setup_status"] = {"main": [[{"node": "Exec: start_call_row", "type": "main", "index": 0}]]}
        conns["Exec: start_call_row"] = {"main": [[{"node": "Build Hook Variables", "type": "main", "index": 0}]]}
        changes.append("wiring: read_setup_status before start_call_row")

    return changes


def main():
    check = "--check" in sys.argv
    w = json.loads(HOOK.read_text())
    changes = patch_hook(w)
    print(f"{HOOK.name}: {len(changes)} change(s)")
    for c in changes:
        print(f"  - {c}")
    if check:
        return 0
    HOOK.write_text(json.dumps(w, indent=2, ensure_ascii=False) + "\n")
    print("written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
