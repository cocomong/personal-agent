#!/usr/bin/env python3
"""Add the first-run onboarding branch to backend/n8n/workflows/voice-gateway.json.

Idempotent (node-name + action-key lookups): safe to re-run. Adds:

  1. Two switch rules (appended AFTER the existing tool rules, so the implicit
     default output keeps routing unmatched actions to Format Spoken Result):
       - get_onboarding_status  (no args; returns setup state + worker count)
       - complete_onboarding    (company_name, pm_name, preferred_name, workers[])
  2. Three PostgreSQL nodes:
       - Exec: get_onboarding_status
       - Exec: complete_onboarding_workers   (upsert by case-insensitive name)
       - Exec: complete_onboarding_profile   (UPDATE company_profile ... RETURNING)
  3. Connections:
       switch -> get_onboarding_status -> Format Spoken Result
       switch -> complete_onboarding_workers -> complete_onboarding_profile -> Format Spoken Result
     (new switch outputs are inserted at indices 21/22, BEFORE the existing
      default output at index 21, so the fallback stays wired.)
  4. Two new cases in Format Spoken Result.
"""
import json
from pathlib import Path

WF = Path(__file__).parent / "workflows" / "voice-gateway.json"
d = json.loads(WF.read_text())
nodes = d["nodes"]
by_name = {n["name"]: n for n in nodes}
conns = d["connections"]

ACTIONS = ("get_onboarding_status", "complete_onboarding")

# ---- 1. switch rules (append after existing tool rules) --------------------
sw = by_name["Actions Sub-Router"]["parameters"]["rules"]["values"]
existing = {r["conditions"]["conditions"][0]["rightValue"] for r in sw}

def make_rule(action):
    return {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
            "conditions": [{
                "leftValue": "={{ $json.action }}",
                "rightValue": action,
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        },
        "renameOutput": True,
        "outputKey": action,
    }

for a in ACTIONS:
    if a not in existing:
        sw.append(make_rule(a))

# ---- 2. PostgreSQL nodes ---------------------------------------------------
def pg_node(node_id, name, query, replacement, x, y):
    return {
        "parameters": {
            "operation": "executeQuery",
            "query": query,
            "options": {"queryReplacement": replacement},
        },
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "alwaysOutputData": True,
        "position": [x, y],
        "credentials": {"postgres": {"id": "YOUR_POSTGRES_CREDENTIALS_ID", "name": "Supabase PostgreSQL"}},
    }

def add_node_once(node):
    if not any(n["name"] == node["name"] for n in nodes):
        nodes.append(node)

add_node_once(pg_node(
    "gate-0036", "Exec: get_onboarding_status",
    "SELECT cp.company_name,\n"
    "       cp.pm_name,\n"
    "       cp.pm_preferred_name,\n"
    "       (cp.setup_completed_at IS NOT NULL) AS setup_completed,\n"
    "       (SELECT count(*) FROM workers WHERE active) AS worker_count\n"
    "  FROM company_profile cp WHERE id = 1;",
    "={{ [] }}", 960, 1960,
))

add_node_once(pg_node(
    "gate-0037", "Exec: complete_onboarding_workers",
    "WITH incoming AS (\n"
    "  SELECT lower(btrim(w.name)) AS name_key, btrim(w.name) AS name,\n"
    "         nullif(btrim(w.trade), '') AS trade,\n"
    "         nullif(w.hourly_rate, '')::numeric AS hourly_rate\n"
    "  FROM jsonb_to_recordset($1::jsonb) AS w(name text, trade text, hourly_rate text)\n"
    "),\n"
    "upserted AS (\n"
    "  UPDATE workers w\n"
    "     SET trade = i.trade,\n"
    "         hourly_rate = COALESCE(i.hourly_rate, w.hourly_rate),\n"
    "         active = TRUE\n"
    "    FROM incoming i\n"
    "   WHERE lower(w.name) = i.name_key\n"
    "  RETURNING w.id\n"
    "),\n"
    "added AS (\n"
    "  INSERT INTO workers (name, trade, hourly_rate, worker_code)\n"
    "  SELECT i.name, i.trade, i.hourly_rate,\n"
    "         'W-' || lpad((b.max_code + row_number() OVER ())::text, 3, '0')\n"
    "    FROM incoming i\n"
    "    CROSS JOIN (SELECT COALESCE(max(NULLIF(regexp_replace(worker_code, '\\D', '', 'g'), '')::int), 0) AS max_code\n"
    "                  FROM workers) b\n"
    "   WHERE NOT EXISTS (SELECT 1 FROM workers w WHERE lower(w.name) = i.name_key)\n"
    "  RETURNING id\n"
    ")\n"
    "SELECT (SELECT count(*) FROM incoming) AS requested,\n"
    "       (SELECT count(*) FROM upserted) AS updated,\n"
    "       (SELECT count(*) FROM added)    AS added,\n"
    "       (SELECT count(*) FROM workers WHERE active) AS total_workers;",
    "={{ [JSON.stringify($json.toolArgs.workers ?? [])] }}", 960, 2040,
))

add_node_once(pg_node(
    "gate-0038", "Exec: complete_onboarding_profile",
    "UPDATE company_profile\n"
    "   SET company_name       = COALESCE(NULLIF($1, ''), company_name),\n"
    "       pm_name            = COALESCE(NULLIF($2, ''), pm_name),\n"
    "       pm_preferred_name  = COALESCE(NULLIF($3, ''), pm_preferred_name),\n"
    "       setup_completed_at = COALESCE(setup_completed_at, now()),\n"
    "       updated_at         = now()\n"
    " WHERE id = 1\n"
    "RETURNING company_name, pm_name, pm_preferred_name,\n"
    "          (SELECT count(*) FROM workers WHERE active) AS worker_count;",
    "={{ [($('Normalize Tool Call').first().json.toolArgs.company_name ?? null), ($('Normalize Tool Call').first().json.toolArgs.pm_name ?? null), ($('Normalize Tool Call').first().json.toolArgs.preferred_name ?? null)] }}",
    960, 2120,
))

# ---- 3. connections --------------------------------------------------------
sw_conns = conns["Actions Sub-Router"]["main"]

def link(src, dst, index=0):
    conns.setdefault(src, {}).setdefault("main", [[]])[0] = [{"node": dst, "type": "main", "index": index}]

# Insert the two new switch outputs BEFORE the implicit default output
# (currently at index 21 -> Format Spoken Result). After insertion the default
# sits at index 23 and stays wired to Format Spoken Result.
if not any(c and c[0]["node"] == "Exec: get_onboarding_status" for c in sw_conns):
    sw_conns.insert(21, [{"node": "Exec: get_onboarding_status", "type": "main", "index": 0}])
if not any(c and c[0]["node"] == "Exec: complete_onboarding_workers" for c in sw_conns):
    sw_conns.insert(22, [{"node": "Exec: complete_onboarding_workers", "type": "main", "index": 0}])

link("Exec: get_onboarding_status", "Format Spoken Result")
link("Exec: complete_onboarding_workers", "Exec: complete_onboarding_profile")
link("Exec: complete_onboarding_profile", "Format Spoken Result")

# ---- 4. Format Spoken Result cases ----------------------------------------
fc = by_name["Format Spoken Result"]["parameters"]["jsCode"]
if "case 'get_onboarding_status':" not in fc:
    fc = fc.replace(
        "  default:\n",
        "  case 'get_onboarding_status':\n"
        "    spoken = dbRow && dbRow.setup_completed\n"
        "      ? `Setup is complete. ${dbRow.company_name}, ${dbRow.worker_count} active worker${dbRow.worker_count === 1 ? '' : 's'} on file.`\n"
        "      : 'Setup is not complete yet. Let us start - what is the company name?';\n"
        "    break;\n"
        "  case 'complete_onboarding':\n"
        "    spoken = dbRow && dbRow.company_name\n"
        "      ? `All set, ${dbRow.pm_preferred_name || 'boss'}. ${dbRow.company_name} is registered with ${dbRow.worker_count} worker${dbRow.worker_count === 1 ? '' : 's'} on file. Anything else?`\n"
        "      : 'Setup did not complete. Please try again.';\n"
        "    break;\n"
        "  default:\n",
        1,
    )
    by_name["Format Spoken Result"]["parameters"]["jsCode"] = fc

WF.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
print("voice-gateway.json updated:")
print("  rules:", len(sw), "| switch outputs:", len(sw_conns))
print("  nodes:", [n["name"] for n in nodes if n["name"].startswith("Exec: complete_onboarding") or n["name"] == "Exec: get_onboarding_status"])
print("  spoken cases:", "ok" if "case 'complete_onboarding':" in by_name["Format Spoken Result"]["parameters"]["jsCode"] else "MISSING")
