#!/usr/bin/env python3
"""Idempotent gateway patch: soft-deleted projects disappear from every tool.

Adds `deleted_at IS NULL` to every project-resolution query, then adds the
`remove_project` tool (router rule -> Exec node -> Format Spoken Result).

Removal is two-phase by design: without confirm=true the tool reports the
dependencies (invoices / estimates / change orders) so the assistant can warn
the PM before anything is hidden; only confirm=true marks the row.

Usage (repo root): python3 backend/n8n/patch_remove_project.py
Exit non-zero on any failed assertion; the file is only written after all
validations pass.
"""
import copy
import json
import re
import sys
from pathlib import Path

WF_PATH = Path(__file__).resolve().parent / "workflows" / "voice-gateway.json"
TOOL = "remove_project"
NODE = f"Exec: {TOOL}"
FORMAT_NODE = "Format Spoken Result"

# (node name, regex, replacement) — each must match exactly once per node.
REPLACEMENTS = [
    ("Exec: list_projects",
     r"WHERE \(\$1::text IS NULL OR LOWER\(project_status\) = LOWER\(\$1\)\)",
     "WHERE ($1::text IS NULL OR LOWER(project_status) = LOWER($1))\n"
     "     AND project_id NOT IN (SELECT id FROM projects WHERE deleted_at IS NOT NULL)"),
    ("Exec: get_project_statement",
     r"WHERE project_id::text = \$1 OR LOWER\(project_name\) LIKE LOWER\(\$2\)",
     "WHERE (project_id::text = $1 OR LOWER(project_name) LIKE LOWER($2))\n"
     "   AND project_id NOT IN (SELECT id FROM projects WHERE deleted_at IS NOT NULL)"),
    ("Exec: create_estimate",
     r"WHERE pr\.company_id = 1 AND a\.project_ref IS NOT NULL",
     "WHERE pr.company_id = 1 AND pr.deleted_at IS NULL AND a.project_ref IS NOT NULL"),
    ("Exec: create_change_order",
     r"WHERE \(id::text = \$1 OR LOWER\(title\) LIKE LOWER\('%' \|\| \$1 \|\| '%'\)\)"
     r" AND baseline_status = 'APPROVED'",
     "WHERE (id::text = $1 OR LOWER(title) LIKE LOWER('%' || $1 || '%'))"
     " AND deleted_at IS NULL AND baseline_status = 'APPROVED'"),
    ("Exec: create_invoice",
     r"WHERE p\.id::text = \$1 OR LOWER\(p\.title\) LIKE LOWER\('%' \|\| \$1 \|\| '%'\)\s+LIMIT 1",
     "WHERE (p.id::text = $1 OR LOWER(p.title) LIKE LOWER('%' || $1 || '%'))\n"
     "    AND p.deleted_at IS NULL\n"
     "  LIMIT 1"),
    ("Exec: create_invoice_change_orders",
     r"WHERE p\.id::text = \$1 OR LOWER\(p\.title\) LIKE LOWER\('%' \|\| \$1 \|\| '%'\)\s+LIMIT 1",
     "WHERE (p.id::text = $1 OR LOWER(p.title) LIKE LOWER('%' || $1 || '%'))\n"
     "    AND p.deleted_at IS NULL\n"
     "  LIMIT 1"),
    ("Exec: send_estimate_for_approval_lookup",
     r"ON p\.id::text = b\.ref OR LOWER\(p\.title\) LIKE LOWER\('%' \|\| b\.ref \|\| '%'\)\s+LEFT JOIN customers",
     "ON (p.id::text = b.ref OR LOWER(p.title) LIKE LOWER('%' || b.ref || '%'))\n"
     "    AND p.deleted_at IS NULL\n"
     "  LEFT JOIN customers"),
    ("Exec: get_estimate_approval_link",
     r"ON p\.id::text = b\.ref OR LOWER\(p\.title\) LIKE LOWER\('%' \|\| b\.ref \|\| '%'\)\s+ORDER BY",
     "ON (p.id::text = b.ref OR LOWER(p.title) LIKE LOWER('%' || b.ref || '%'))\n"
     "      AND p.deleted_at IS NULL\n"
     "   ORDER BY"),
    ("Exec: get_change_order_approval_link",
     r"LEFT JOIN projects p ON p\.id::text = b\.ref OR LOWER\(p\.title\) LIKE LOWER\('%' \|\| b\.ref \|\| '%'\)",
     "LEFT JOIN projects p ON (p.id::text = b.ref OR LOWER(p.title) LIKE LOWER('%' || b.ref || '%'))"
     " AND p.deleted_at IS NULL"),
    ("Exec: send_change_order_for_approval_lookup",
     r"AND \(p\.id::text = \$1 OR LOWER\(p\.title\) LIKE LOWER\('%' \|\| \$1 \|\| '%'\)\) AND co\.change_order_number",
     "AND p.deleted_at IS NULL AND (p.id::text = $1 OR LOWER(p.title) LIKE LOWER('%' || $1 || '%'))"
     " AND co.change_order_number"),
    ("Exec: list_estimate_status",
     r"WHERE p\.company_id = 1\s+AND \(\$1::text IS NULL",
     "WHERE p.company_id = 1\n"
     "     AND p.deleted_at IS NULL\n"
     "     AND ($1::text IS NULL"),
    ("Exec: rotate_estimate_token",
     r"WHERE p\.id::text = \$1\s+AND c\.id = p\.customer_id",
     "WHERE p.id::text = $1\n"
     "     AND p.deleted_at IS NULL\n"
     "     AND c.id = p.customer_id"),
    ("Exec: log_approval_email_estimate",
     r"WHERE p\.id::text = \$4\s+RETURNING id",
     "WHERE p.id::text = $4 AND p.deleted_at IS NULL\n   RETURNING id"),
    ("Exec: log_approval_email_change_order",
     r"WHERE p\.id::text = \$4 RETURNING id;",
     "WHERE p.id::text = $4 AND p.deleted_at IS NULL RETURNING id;"),
]

REMOVE_SQL = """WITH args AS (
  SELECT NULLIF(btrim($1::text), '') AS ref,
         COALESCE($2::boolean, false) AS do_it
), r AS (
  SELECT p.id, p.title
    FROM projects p, args a
   WHERE a.ref IS NOT NULL
     AND p.deleted_at IS NULL
     AND p.company_id = 1
     AND (p.id::text = a.ref OR LOWER(p.title) LIKE LOWER('%' || a.ref || '%'))
   ORDER BY (p.id::text = a.ref) DESC NULLS LAST
   LIMIT 1
), d AS (
  SELECT r.id, r.title,
         (SELECT count(*) FROM invoices i WHERE i.project_id = r.id) AS invoice_count,
         (SELECT count(*) FROM estimates e WHERE e.project_id = r.id) AS estimate_count,
         (SELECT count(*) FROM change_orders co WHERE co.project_id = r.id) AS change_order_count
    FROM r
), upd AS (
  UPDATE projects p
     SET deleted_at = now()
    FROM d, args a
   WHERE p.id = d.id AND a.do_it AND p.deleted_at IS NULL
  RETURNING p.id, p.title
)
SELECT CASE
         WHEN d.id IS NULL THEN 'NOT_FOUND'
         WHEN upd.id IS NOT NULL THEN 'REMOVED'
         ELSE 'NEEDS_CONFIRMATION'
       END AS outcome,
       d.title,
       COALESCE(d.invoice_count, 0) AS invoices,
       COALESCE(d.estimate_count, 0) AS estimates,
       COALESCE(d.change_order_count, 0) AS change_orders
  FROM (SELECT 1) one
  LEFT JOIN d ON true
  LEFT JOIN upd ON upd.id = d.id;"""


def patch_formatter(wf: dict) -> bool:
    """Add the remove_project case to Format Spoken Result (its default branch
    otherwise answers 'I'm not sure how to handle…' for a routed tool)."""
    fmt = next(n for n in wf["nodes"] if n["name"] == FORMAT_NODE)
    code = fmt["parameters"]["jsCode"]
    if "case 'remove_project'" in code:
        return False
    case = """  case 'remove_project': {
    const r = dbRow || {};
    if (r.outcome === 'REMOVED') {
      spoken = `Removed ${r.title}. It is hidden from every list and tool; the invoices, estimates and change orders stay on file.`;
    } else if (r.outcome === 'NEEDS_CONFIRMATION') {
      const inv = Number(r.invoices || 0), est = Number(r.estimates || 0), co = Number(r.change_orders || 0);
      const parts = [];
      if (inv) parts.push(`${inv} invoice${inv === 1 ? '' : 's'}`);
      if (est) parts.push(`${est} estimate${est === 1 ? '' : 's'}`);
      if (co) parts.push(`${co} change order${co === 1 ? '' : 's'}`);
      const attached = parts.length ? `It has ${parts.join(', ')} attached` : 'Nothing is attached to it';
      spoken = `${attached}. Removing ${r.title} hides the project from every tool - the records stay on file. Should I remove it?`;
    } else {
      spoken = `I could not find an active project called ${(toolCall.toolArgs && toolCall.toolArgs.project) || 'that'} - it may already be removed.`;
    }
    break;
  }
  default:"""
    if "\n  default:" not in code:
        raise SystemExit("formatter default branch not found — aborting")
    fmt["parameters"]["jsCode"] = code.replace("\n  default:", "\n" + case, 1)
    return True


def patch_statement(wf: dict) -> bool:
    """get_project_statement must answer 'Project not found.' instead of dying
    silently: a 0-row lookup stops the chain (empty HTTP body — the Vapi
    'No result returned' trap). Emit one empty item, and only build the
    sentence when a project_name actually came back."""
    changed = False
    node = next(n for n in wf["nodes"] if n["name"] == "Exec: get_project_statement")
    if not node.get("alwaysOutputData"):
        node["alwaysOutputData"] = True
        changed = True
    fmt = next(n for n in wf["nodes"] if n["name"] == FORMAT_NODE)
    code = fmt["parameters"]["jsCode"]
    if "dbRow && dbRow.project_name\n      ?" not in code:
        old = "spoken = dbRow\n      ? `${dbRow.project_name}"
        new = "spoken = dbRow && dbRow.project_name\n      ? `${dbRow.project_name}"
        if old not in code:
            raise SystemExit("statement formatter shape changed — aborting")
        fmt["parameters"]["jsCode"] = code.replace(old, new, 1)
        changed = True
    return changed


def main() -> int:
    raw = WF_PATH.read_text()
    wf = json.loads(raw)
    nodes = {n["name"]: n for n in wf["nodes"]}

    patched, skipped = [], []
    for node_name, pattern, replacement in REPLACEMENTS:
        node = nodes.get(node_name)
        if node is None:
            raise SystemExit(f"missing node: {node_name}")
        query = node["parameters"]["query"]
        if "deleted_at" in query:
            skipped.append(node_name)
            continue
        hits = len(re.findall(pattern, query, re.DOTALL))
        if hits != 1:
            raise SystemExit(f"{node_name}: pattern matched {hits} times, expected 1")
        node["parameters"]["query"] = re.sub(pattern, replacement, query, flags=re.DOTALL)
        patched.append(node_name)

    if NODE in nodes:
        print("already applied: node exists")
    else:
        max_id = max(int(m.group(1)) for n in wf["nodes"]
                     if (m := re.match(r"gate-(\d+)$", n.get("id", ""))) )
        top_y = max(n["position"][1] for n in wf["nodes"] if "position" in n)

        node = {
            "parameters": {
                "operation": "executeQuery",
                "query": REMOVE_SQL,
                "options": {
                    "queryReplacement":
                        "={{ [$json.toolArgs.project, ($json.toolArgs.confirm ?? false)] }}"
                },
            },
            "id": f"gate-{max_id + 1:04d}",
            "name": NODE,
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [960, top_y + 220],
            "credentials": {
                "postgres": {"id": "YOUR_POSTGRES_CREDENTIALS_ID", "name": "Supabase PostgreSQL"}
            },
        }
        wf["nodes"].append(node)

        router = nodes["Actions Sub-Router"]
        rules = router["parameters"]["rules"]["values"]

        rule = copy.deepcopy(rules[-1])
        cond = rule["conditions"]["conditions"][0]
        cond["rightValue"] = TOOL
        rule["outputKey"] = TOOL
        rules.append(rule)

        main = wf["connections"]["Actions Sub-Router"]["main"]
        if main[-1] != [{"node": FORMAT_NODE, "type": "main", "index": 0}]:
            raise SystemExit("router fallback is not the last output — aborting")
        main.insert(len(rules) - 1, [{"node": NODE, "type": "main", "index": 0}])
        wf["connections"][NODE] = {
            "main": [[{"node": FORMAT_NODE, "type": "main", "index": 0}]]
        }

    fmt_patched = patch_formatter(wf)
    print("formatter case added" if fmt_patched else "formatter case already present")
    st_patched = patch_statement(wf)
    print("statement not-found handling added" if st_patched else "statement already guarded")

    # ---- validations ----
    names = [n["name"] for n in wf["nodes"]]
    assert len(names) == len(set(names)), "duplicate node names"
    ids = [n.get("id") for n in wf["nodes"] if n.get("id")]
    assert len(ids) == len(set(ids)), "duplicate node ids"
    known = set(names)
    for src, conn in wf["connections"].items():
        assert src in known, f"connection source not a node: {src}"
        for out in conn.get("main", []):
            for branch in out:
                assert branch["node"] in known, f"connection target not a node: {branch['node']}"
    router_rules = wf["nodes"][names.index("Actions Sub-Router")]["parameters"]["rules"]["values"]
    main = wf["connections"]["Actions Sub-Router"]["main"]
    assert len(main) == len(router_rules) + 1, (
        f"router output/rule parity broken: {len(main)} outputs vs {len(router_rules)} rules"
    )
    idx = next(i for i, r in enumerate(router_rules) if r["outputKey"] == TOOL)
    assert main[idx][0]["node"] == NODE, f"rule {TOOL} routed to {main[idx][0]['node']}"
    assert main[-1][0]["node"] == FORMAT_NODE, "fallback lost"

    WF_PATH.write_text(json.dumps(wf, indent=2) + "\n")
    print(f"patched queries: {len(patched)}")
    print(f"skipped (already had deleted_at): {len(skipped)}")
    print(f"router rules: {len(router_rules)} | outputs: {len(main)} | {TOOL} -> {NODE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
