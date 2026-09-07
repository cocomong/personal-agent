# Customer identity & tool honesty fixes (2026-09-07, D42–D46)

Follow-up to the MSI dot com chat (052e9b30): user created a project + customer
that the assistant then could not find ("Tom Smith" + d_tam@yahoo.com, which
belongs to David Tam). Post-mortem found a 4-defect chain; this batch fixes it.

## What actually broke (evidence: chat turns 16:55–17:06 + DB + n8n logs)

1. lookup_or_create_customer returned NOTHING when the email already existed
   (INSERT-only query, no RETURNING on the found path) — the assistant never
   got a customer id and improvised.
2. create_project and create_estimate bound tool args straight into uuid
   columns: `invalid input syntax for type uuid: "5056 Camino"` and
   `... "Smith_Tom"` in the container logs. Silent crashes.
3. A crashed gateway node answers HTTP 200 EMPTY → Vapi reports "No result
   returned" → the model fabricated success ("I created the project 5056
   Camino for customer Tom Smith" — no such row ever existed).
4. No recovery path: update_customer said "not found" (true — customer never
   existed) and there was no way to list/search customers ("I cannot list
   customers directly").

## Changes (D42–D46)

- lookup_or_create_customer (D42): guaranteed-row SQL. Outcome = FOUND (by
  email OR exact name, with a by_email flag) / CREATED / MISSING_INFO. When
  the email belongs to someone else it returns THAT customer and the reply
  says "That email is already on file for <name> - I will use that customer."
  No duplicate is ever inserted on an existing email (unique
  (company_id, email) preserved).
- create_project (D43): resolves customer by id::text OR exact name in a CTE
  (no uuid cast), falls back site_address to the title (column is NOT NULL),
  returns CREATED / CUSTOMER_NOT_FOUND / MISSING_TITLE.
- create_estimate (D44): resolves project by id::text OR shorthand-name LIKE
  in a CTE, validates valid_until (bad date strings become NULL instead of a
  crash), returns CREATED / PROJECT_NOT_FOUND / MISSING_SCOPE. NOTE: the
  node's queryReplacement param list was rewritten in lockstep with the SQL
  (8 params, labor/material passed separately — the old node summed them into
  one allocated_amount param).
- find_customer (D45, NEW tool): code-node best-match over the company's
  customers (option B, no pg_trgm): exact / close match (substring, prefix,
  bigram overlap for single-edit typos) / possible match / email / phone
  (country-code-tolerant suffix match). Returns up to 3 candidates with a
  percent; a clean miss says so honestly. Used proactively when a name does
  not resolve, and called by the assistant instead of inventing IDs.
- Honesty rules (D46): system prompt section "TOOL HONESTY RULES" — only
  confirm success after a positive tool result; quote the reason on failure;
  never invent customer IDs; reuse the customer an email already belongs to.
  update_customer's not-found reply now points at find_customer.

## Error-output wiring (attempted, then DEFERRED)

Per-node `onError: continueErrorOutput` + main[1] error branches to a
tool_failed_message node were built and deployed, and broke EVERY gateway
execution on n8n 2.35.7 ("No active execution found" / "There was a problem
executing the workflow" — the manual error-branch wiring pattern does not load
under the 2.35 publish model). Reverted; silent-death protection currently
rests on guaranteed-row SQL + the honesty rules. Revisit via the n8n UI or
docs for the correct 2.35 error-handling shape before re-attempting.

## Deploy learnings (n8n 2.35.7 — add to the recipe)

- NEW postgres nodes need `"operation": "executeQuery"` AND a credentials
  block identical to existing nodes, or every run of the workflow fails up
  front: "Parameter 'Table' is required" (no operation) and "Node does not
  have any credentials set" (no credentials). The failure surfaces as an
  EMPTY webhook body + an n8n workflow.failed event; the real message is in
  the container's n8nEventLog-1.log payload.errorMessage.
- Rewriting a node's query REQUIRES re-checking its queryReplacement arity
  and ORDER against the new $N placeholders (create_estimate crashed with
  `invalid input syntax for type integer: "ACCEPTED"` until the repl matched).
- n8n 2.35 keeps workflow VERSIONS: `import:workflow` creates a new version
  and deactivates; `update:workflow --id=... --active=true` + container
  restart still required, and a second import without re-activation yields
  webhook "Active version not found for workflow with id ...".
- Execution forensics in 2.35: statuses in execution_entity (id/status/
  startedAt); the node error text lives in n8nEventLog-1.log under
  n8n.workflow.failed → payload.errorMessage; execution_data rows are
  reference-deduped JSON (strings that are pure digits point into later
  dicts) — decode by scanning for the message string, not by naive parse.

## Verified live (all via gateway probes, then QA rows deleted)

- lookup_or_create Tom Smith + d_tam@yahoo.com -> "That email is already on
  file for David Tam ... I will use that customer." (no insert)
- create_project customer "Tom Smith" -> CUSTOMER_NOT_FOUND text (no crash)
- create_project "David Tam" by name, no site -> CREATED "Project 5056 Camino
  created for customer David Tam."
- create_estimate "5056 Camino" by shorthand -> "$105,000"; bad date ->
  still created w/ NULL validity; unknown project -> not-found text.
- find_customer: "Tom Smith" -> none (honest); "Tam" -> David Tam 85%; 
  "Miller" -> Dave Miller 85%; typo "Davd" -> Dave Miller 0.66 (hermetic).
- DB restored to pre-test state (3 projects / 5 customers / 1 estimate).
- Vapi synced to 28 tools. Commit XXXXX pending.
