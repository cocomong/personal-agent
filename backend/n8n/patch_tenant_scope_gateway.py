#!/usr/bin/env python3
"""Gateway half of per-user company scope (new-user onboarding).

  Webhook -> Extract Tool Call (code: action/args/user_id)
          -> Resolve Call Scope (sql: user_id -> company_id, NULL = onboarding)
          -> Normalize Tool Call (code: merge + refusal decision)
          -> Onboarding Guard (if refusal empty)
               -> Actions Sub-Router
               -> Respond Setup First

complete_onboarding now runs: ensure_company -> link_user -> workers -> profile,
so the first company is CREATED and the user LINKED before any row is written
against a company id. Every onboarding query is scoped by the caller's company
instead of `company_id = 1`.

Idempotent: rewrites nodes to a fixed target state; re-running reports 0 changes.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GW = ROOT / "backend" / "n8n" / "workflows" / "voice-gateway.json"

EXTRACT_JS = r"""// Pull the tool call + caller identity out of the Vapi payload.
// The app's X-User-Token never reaches Vapi, so the caller arrives as
// assistantOverrides.variableValues.user_id, injected by the call-start hook.
const body = ($input.first().json || {}).body || {};
const msg = body.message || {};
const toolCall = (msg.toolCalls || [])[0] || {};
const fn = toolCall.function || {};
const call = msg.call || {};
const vv = (call.assistantOverrides && call.assistantOverrides.variableValues) || {};
const meta = call.metadata || {};

let toolArgs = {};
try {
  toolArgs = typeof fn.arguments === 'string' ? JSON.parse(fn.arguments) : (fn.arguments ?? {});
} catch (e) {
  // leave empty; the action's SQL will surface the missing argument
}

return [{
  json: {
    toolCallId: toolCall.id || '',
    action: fn.name || '',
    toolArgs,
    userId: String(vv.user_id || meta.userId || meta.user_id || '').trim(),
  },
}];"""

SCOPE_SQL = """-- user_id -> company_id. No user id at all = legacy client -> company 1.
-- A signed-in user with no company -> NULL ("onboarding"), never company 1.
SELECT NULLIF(btrim($1::text), '')                       AS user_id,
       COALESCE(
         (SELECT u.company_id FROM users u
           WHERE u.id = NULLIF(btrim($1::text), '')::uuid),
         CASE WHEN NULLIF(btrim($1::text), '') IS NULL THEN 1 END
       )::smallint                                        AS company_id;"""

NORMALIZE_JS = r"""// Merge the tool call with the resolved company scope and decide whether this
// action is allowed for the caller.
const call = $('Extract Tool Call').first().json || {};
const scope = $('Resolve Call Scope').first().json || {};

const companyId = (scope.company_id === null || scope.company_id === undefined || scope.company_id === '')
  ? null
  : Number(scope.company_id);
const userId = String(scope.user_id || '').trim();

// Every tool query is company-scoped now (P1, 2026-10-30), so a company other
// than the original one can be served normally.
const SCOPED_TOOLS_READY = true;

const ONBOARDING_ACTIONS = ['get_onboarding_status', 'complete_onboarding'];
const action = String(call.action || '');

let refusal = '';
if (companyId === null) {
  if (!ONBOARDING_ACTIONS.includes(action)) {
    refusal = 'I need to finish setting you up first - it takes about a minute. '
            + 'Say "let us set up" and I will walk you through it.';
  }
} else if (companyId !== 1 && !SCOPED_TOOLS_READY) {
  // Kept for a future staged rollout; P1 made every query company-scoped.
  refusal = 'Your setup is saved, but your workspace is still being prepared, '
          + 'so I cannot do that yet. Try again a little later.';
}

return [{
  json: {
    toolCallId: call.toolCallId,
    action,
    toolArgs: call.toolArgs || {},
    userId,
    companyId,
    refusal,
  },
}];"""

STATUS_SQL = """SELECT cp.company_name,
       cp.pm_name,
       cp.pm_preferred_name,
       (cp.setup_completed_at IS NOT NULL) AS setup_completed,
       COALESCE(cp.invoice_template_key, 'classic') AS invoice_template,
       (SELECT count(*) FROM workers w WHERE w.active AND w.company_id = $1::smallint) AS worker_count
  FROM company_profile cp WHERE cp.id = $1::smallint;"""

ENSURE_SQL = """-- Create the caller's company on first use. Every tenant-identifying column is
-- explicit because db/0042 dropped the defaults that would otherwise clone
-- another tenant's name/address/phone/email. Sender address defaults to the
-- caller's own Google email, never the platform inbox.
INSERT INTO company_profile (
    company_name, legal_name, pm_name, pm_preferred_name,
    street_address, city, province, postal_code, phone,
    email_from, email_from_name, signature_name,
    gst_reg_number, pst_reg_number, payment_instructions,
    created_by_user
)
SELECT COALESCE(NULLIF(btrim($2::text), ''), 'My Company'),
       COALESCE(NULLIF(btrim($2::text), ''), 'My Company'),
       NULLIF(btrim($3::text), ''),
       NULLIF(btrim($4::text), ''),
       COALESCE(NULLIF(btrim($5::text), ''), ''),
       COALESCE(NULLIF(btrim($6::text), ''), ''),
       COALESCE(NULLIF(btrim($7::text), ''), 'BC'),
       COALESCE(NULLIF(btrim($8::text), ''), ''),
       COALESCE(NULLIF(btrim($9::text), ''), ''),
       COALESCE(NULLIF(btrim($10::text), ''), u.email),
       COALESCE(NULLIF(btrim($2::text), ''), 'My Company'),
       -- signature_name is NOT NULL (db/0001): never leave it NULL.
       COALESCE(NULLIF(btrim($4::text), ''), NULLIF(btrim($3::text), ''), ''),
       NULLIF(btrim($11::text), ''),
       NULLIF(btrim($12::text), ''),
       NULLIF(btrim($13::text), ''),
       u.id
  FROM users u
 WHERE u.id = $1::uuid
   AND u.company_id IS NULL
ON CONFLICT (created_by_user) WHERE created_by_user IS NOT NULL DO NOTHING
RETURNING id;"""

LINK_SQL = """UPDATE users SET company_id = $2::smallint
 WHERE id = $1::uuid AND company_id IS NULL
RETURNING company_id;"""

PROFILE_SQL = """WITH upd AS (
  UPDATE company_profile
     SET company_name       = COALESCE(NULLIF($2, ''), company_name),
         pm_name            = COALESCE(NULLIF($3, ''), pm_name),
         pm_preferred_name  = COALESCE(NULLIF($4, ''), pm_preferred_name),
         street_address     = COALESCE(NULLIF($5, ''), street_address),
         city               = COALESCE(NULLIF($6, ''), city),
         province           = COALESCE(NULLIF($7, ''), province),
         postal_code        = COALESCE(NULLIF($8, ''), postal_code),
         gst_reg_number     = COALESCE(NULLIF($9, ''), gst_reg_number),
         pst_reg_number     = COALESCE(NULLIF($10, ''), pst_reg_number),
         payment_instructions = COALESCE(NULLIF($11, ''), payment_instructions),
         invoice_template_key = CASE
           WHEN NULLIF(btrim($12), '') IS NULL THEN invoice_template_key
           WHEN btrim($12) = 'classic' THEN NULL
           WHEN EXISTS (SELECT 1 FROM document_templates t
                        WHERE t.key = btrim($12) AND t.is_active) THEN btrim($12)
           ELSE invoice_template_key END,
         -- Setup completes only with a real business address and a sender
         -- address; db/0042 enforces the same rule with a CHECK constraint.
         setup_completed_at = CASE
           WHEN COALESCE(NULLIF(btrim($5), ''), street_address) <> ''
            AND COALESCE(NULLIF(btrim($6), ''), city) <> ''
            AND COALESCE(NULLIF(btrim($7), ''), province) <> ''
            AND COALESCE(NULLIF(btrim($8), ''), postal_code) <> ''
            AND btrim(email_from) <> ''
           THEN COALESCE(setup_completed_at, now())
           ELSE setup_completed_at END,
         updated_at = now()
   WHERE id = $1::smallint
  RETURNING company_name, pm_name, pm_preferred_name,
            street_address, city, province, postal_code,
            COALESCE(invoice_template_key, 'classic') AS invoice_template,
            (setup_completed_at IS NOT NULL) AS setup_completed,
            (SELECT count(*) FROM workers w WHERE w.active AND w.company_id = $1::smallint) AS worker_count
)
SELECT * FROM upd
UNION ALL
SELECT company_name, pm_name, pm_preferred_name,
       street_address, city, province, postal_code,
       COALESCE(invoice_template_key, 'classic'), (setup_completed_at IS NOT NULL),
       (SELECT count(*) FROM workers w WHERE w.active AND w.company_id = $1::smallint)
  FROM company_profile
 WHERE id = $1::smallint AND NOT EXISTS (SELECT 1 FROM upd)
LIMIT 1;"""

WORKERS_SQL = """WITH incoming AS (
  SELECT lower(btrim(w.name)) AS name_key, btrim(w.name) AS name,
         nullif(btrim(w.trade), '') AS trade,
         nullif(w.hourly_rate, '')::numeric AS hourly_rate
  FROM jsonb_to_recordset($2::jsonb) AS w(name text, trade text, hourly_rate text)
), upserted AS (
  UPDATE workers w
     SET trade = i.trade,
         hourly_rate = COALESCE(i.hourly_rate, w.hourly_rate),
         active = TRUE
    FROM incoming i
   WHERE w.company_id = $1::smallint
     AND lower(w.name) = i.name_key
  RETURNING w.id
), added AS (
  INSERT INTO workers (name, trade, hourly_rate, worker_code, company_id)
  SELECT i.name, i.trade, i.hourly_rate,
         'W-' || lpad((b.max_code + row_number() OVER ())::text, 3, '0'),
         $1::smallint
    FROM incoming i
    CROSS JOIN (SELECT COALESCE(max(NULLIF(regexp_replace(worker_code, '\\D', '', 'g'), '')::int), 0) AS max_code
                  FROM workers WHERE company_id = $1::smallint) b
   WHERE NOT EXISTS (SELECT 1 FROM workers w
                      WHERE w.company_id = $1::smallint AND lower(w.name) = i.name_key)
  RETURNING id
)
SELECT (SELECT count(*) FROM incoming) AS requested,
       (SELECT count(*) FROM upserted) AS updated,
       (SELECT count(*) FROM added)    AS added,
       (SELECT count(*) FROM workers w WHERE w.active AND w.company_id = $1::smallint) AS total_workers;"""

# Every tool argument is coerced to a string/number so the parameter array never
# contains undefined (the Postgres node rejects that) and the SQL's COALESCEs
# handle empties.
ENSURE_PARAMS = (
    "={{ ["
    " String($('Normalize Tool Call').first().json.userId || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.company_name || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.pm_name || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.pm_preferred_name || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.street_address || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.city || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.province || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.postal_code || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.phone || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.email_from || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.gst_reg_number || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.pst_reg_number || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.payment_instructions || '')"
    "] }}"
)
LINK_PARAMS = ("={{ [String($('Normalize Tool Call').first().json.userId || ''),"
               " Number($('Exec: ensure_company').first().json.id || $('Normalize Tool Call').first().json.companyId)] }}")
PROFILE_PARAMS = (
    "={{ ["
    " Number($('Exec: ensure_company').first().json.id || $('Normalize Tool Call').first().json.companyId),"
    " String($('Normalize Tool Call').first().json.toolArgs.company_name || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.pm_name || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.pm_preferred_name || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.street_address || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.city || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.province || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.postal_code || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.gst_reg_number || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.pst_reg_number || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.payment_instructions || ''),"
    " String($('Normalize Tool Call').first().json.toolArgs.invoice_template || '')"
    "] }}"
)
WORKERS_PARAMS = (
    "={{ ["
    " Number($('Exec: ensure_company').first().json.id || $('Normalize Tool Call').first().json.companyId),"
    " JSON.stringify($('Normalize Tool Call').first().json.toolArgs.workers || [])"
    "] }}"
)
STATUS_PARAMS = "={{ [Number($('Normalize Tool Call').first().json.companyId)] }}"


REFUSAL_RESPOND = {
    "respondWith": "json",
    "responseBody": "={{ { results: [{ toolCallId: $json.toolCallId, result: $json.refusal }] } }}",
    "options": {"responseCode": 200},
}


def main():
    check = "--check" in sys.argv
    w = json.loads(GW.read_text())
    changes = []
    nodes = w["nodes"]
    by = {n["name"]: n for n in nodes}
    creds = by["Exec: create_project"]["credentials"]

    def add_node(name, ntype, params, nid, pos, type_version=1.0):
        nodes.append({"parameters": params, "id": nid, "name": name,
                      "type": ntype, "typeVersion": type_version,
                      "position": pos, **({"credentials": creds} if ntype.endswith("postgres") else {})})
        by[name] = nodes[-1]
        changes.append(f"added {name}")

    # 1. Extract Tool Call ----------------------------------------------------
    if "Extract Tool Call" not in by:
        add_node("Extract Tool Call", "n8n-nodes-base.code",
                 {"jsCode": EXTRACT_JS}, "gate-extract-001", [-320, 100], 2)
    elif by["Extract Tool Call"]["parameters"]["jsCode"].strip() != EXTRACT_JS.strip():
        by["Extract Tool Call"]["parameters"]["jsCode"] = EXTRACT_JS
        changes.append("Extract Tool Call: rewrote")

    # 2. Resolve Call Scope ---------------------------------------------------
    if "Resolve Call Scope" not in by:
        add_node("Resolve Call Scope", "n8n-nodes-base.postgres",
                 {"operation": "executeQuery", "query": SCOPE_SQL,
                  "options": {"queryReplacement": "={{ [$json.userId] }}"}},
                 "gate-scope-001", [-140, 100], 2.5)
    elif by["Resolve Call Scope"]["parameters"]["query"].strip() != SCOPE_SQL.strip():
        by["Resolve Call Scope"]["parameters"] = {
            "operation": "executeQuery", "query": SCOPE_SQL,
            "options": {"queryReplacement": "={{ [$json.userId] }}"}}
        changes.append("Resolve Call Scope: rewrote")

    # 3. Normalize Tool Call --------------------------------------------------
    if by["Normalize Tool Call"]["parameters"]["jsCode"].strip() != NORMALIZE_JS.strip():
        by["Normalize Tool Call"]["parameters"]["jsCode"] = NORMALIZE_JS
        changes.append("Normalize Tool Call: scope merge + refusal")

    # 4. Guard + refusal responder -------------------------------------------
    if "Onboarding Guard" not in by:
        add_node("Onboarding Guard", "n8n-nodes-base.if", {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "",
                            "typeValidation": "loose", "version": 2},
                "conditions": [{"id": "scope-allowed",
                                "leftValue": "={{ $json.refusal }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "equals"}}],
                "combinator": "and"},
            "options": {},
        }, "gate-guard-001", [80, 100], 2)
    if "Respond Setup First" not in by:
        add_node("Respond Setup First", "n8n-nodes-base.respondToWebhook",
                 dict(REFUSAL_RESPOND), "gate-refuse-001", [300, 260], 1.1)
    elif by["Respond Setup First"]["parameters"] != REFUSAL_RESPOND:
        by["Respond Setup First"]["parameters"] = dict(REFUSAL_RESPOND)
        changes.append("Respond Setup First: rewrote")

    # 5. company creation on the complete_onboarding branch -------------------
    def upsert_node(name, nid, sql, params, pos):
        """Create the node, or rewrite it when either SQL or params drifted."""
        if name not in by:
            add_node(name, "n8n-nodes-base.postgres",
                     {"operation": "executeQuery", "query": sql,
                      "options": {"queryReplacement": params}},
                     nid, pos, 2.5)
            return
        n = by[name]
        if (n["parameters"].get("query", "").strip() != sql.strip()
                or n["parameters"].get("options", {}).get("queryReplacement") != params):
            n["parameters"] = {"operation": "executeQuery", "query": sql,
                               "options": {"queryReplacement": params}}
            changes.append(f"{name}: rewrote")

    upsert_node("Exec: ensure_company", "gate-ensure-001", ENSURE_SQL, ENSURE_PARAMS, [300, 620])
    upsert_node("Exec: link_user", "gate-link-001", LINK_SQL, LINK_PARAMS, [520, 620])

    # 6. scoped onboarding queries -------------------------------------------
    upsert_node("Exec: get_onboarding_status", "gate-status-001", STATUS_SQL, STATUS_PARAMS, [760, 700])
    upsert_node("Exec: complete_onboarding_profile", "gate-prof-001", PROFILE_SQL, PROFILE_PARAMS, [980, 620])
    upsert_node("Exec: complete_onboarding_workers", "gate-work-001", WORKERS_SQL, WORKERS_PARAMS, [760, 620])

    # 7. wiring --------------------------------------------------------------
    c = w["connections"]
    for src, dst in (("Voice Gateway Webhook", "Extract Tool Call"),
                     ("Extract Tool Call", "Resolve Call Scope"),
                     ("Resolve Call Scope", "Normalize Tool Call")):
        cur = c.get(src, {}).get("main", [[{}]])[0][0].get("node")
        if cur != dst:
            c[src] = {"main": [[{"node": dst, "type": "main", "index": 0}]]}
            changes.append(f"wiring: {src} -> {dst}")

    want_norm = {"main": [[{"node": "Onboarding Guard", "type": "main", "index": 0}]]}
    want_guard = {"main": [
        [{"node": "Actions Sub-Router", "type": "main", "index": 0}],
        [{"node": "Respond Setup First", "type": "main", "index": 0}],
    ]}
    if c.get("Normalize Tool Call") != want_norm or c.get("Onboarding Guard") != want_guard:
        c["Normalize Tool Call"] = want_norm
        c["Onboarding Guard"] = want_guard
        changes.append("wiring: Normalize -> Guard -> Router / refusal")

    # complete_onboarding: ensure -> link -> workers -> profile
    router = by["Actions Sub-Router"]["parameters"]["rules"]["values"]
    idx = [i for i, v in enumerate(router) if v["outputKey"] == "complete_onboarding"][0]
    outs = c["Actions Sub-Router"]["main"]
    while len(outs) <= idx:
        outs.append([])
    if not outs[idx] or outs[idx][0]["node"] != "Exec: ensure_company":
        outs[idx] = [{"node": "Exec: ensure_company", "type": "main", "index": 0}]
        changes.append("wiring: complete_onboarding -> ensure_company")
    c["Exec: ensure_company"] = {"main": [[{"node": "Exec: link_user", "type": "main", "index": 0}]]}
    c["Exec: link_user"] = {"main": [[{"node": "Exec: complete_onboarding_workers", "type": "main", "index": 0}]]}
    c["Exec: complete_onboarding_workers"] = {"main": [[{"node": "Exec: complete_onboarding_profile", "type": "main", "index": 0}]]}
    c["Exec: complete_onboarding_profile"] = {"main": [[{"node": "Format Spoken Result", "type": "main", "index": 0}]]}

    print(f"{GW.name}: {len(changes)} change(s)")
    for ch in changes:
        print(f"  - {ch}")
    if check:
        return 0
    GW.write_text(json.dumps(w, indent=2, ensure_ascii=False) + "\n")
    print("written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
