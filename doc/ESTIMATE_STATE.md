# Estimate state machine — CREATED → SENT → APPROVED/REJECTED (2026-09-08, D54+)

Build owner: autonomous overnight window (user: "plan every step toward the full
version and build it step by step"). Full version, per the session-end decision
(@session:default/20260904_091130_97017f msg 6250): the state machine becomes
REAL behavior, not documentation.

## Principle (settled with the PM, msg 6249-6250)

Entity state column = the truth of the entity. approval_log = the evidence trail
(proof/audit/push), append-only, NEVER consulted as current state. Every
transition writes the new state AND its log event; they never disagree. LLM
reads state for "where is it"; log only as proof.

## State model (new)

projects.baseline_status — ONE workflow state for the baseline estimate/contract:

    CREATED   (default)  estimate on file, never asked for signature
    SENT                  emailed or link-pushed to the customer, awaiting decision
    APPROVED              customer signed; contract value set (sum of estimate lines)
    REJECTED              customer declined; PM may revise + re-send (back to SENT)

- estimates.status (per scope line): on-file marker ONLY — CREATED / DRAFT
  (renamed from ACCEPTED). NEVER implies customer acceptance. Line status does
  not drive the workflow; baseline_status does. (Live ACCEPTED rows → CREATED.)
- approval_log: unchanged table. estimate_sent = EMAIL proof (recipient + Gmail
  message id). Customer decisions logged estimate_approved / estimate_rejected.
  "Was it sent?" → baseline_status SENT (log row as the email proof, when the
  channel was email).

## Transition rules (implemented in gateway + portal)

1. send_estimate_for_approval (email channel):
   - Allowed from CREATED / REJECTED / SENT. BLOCKED from APPROVED — the email
     must not go out; spoken text says already approved by <who> on <date>.
   - On send: rotate baseline_approval_token BEFORE render (email carries the
     fresh token) → gmail → flip status to SENT + INSERT estimate_sent log in
     ONE postgres statement (atomic flip+log; state and proof can't disagree).
     Token rotation means each new request supersedes earlier links.
   - If gmail throws, the chain dies before flip → status stays CREATED/REJECTED
     (token was rotated; no valid link outstanding for an unsent estimate —
     harmless, self-heals on retry). Tool reports failure honestly (no Format
     text), TOOL HONESTY RULES apply.
2. get_estimate_approval_link (on-site/PM-phone presentation):
   - Also transitions CREATED/REJECTED → SENT (the PM is presenting the request;
     the portal already records approval_method='onsite_link' for this). Rotate
     the token so the delivered link is current. No estimate_sent log row (no
     email proof exists; the portal decision log covers the audit).
3. Portal Estimate Approval Update: accepts a decision ONLY when
   baseline_status = 'SENT' (token match AND status). Decided/never-sent rows
   no-op (0 rows → empty 200, same as today). Render page: SENT → show form;
   CREATED → "not yet sent for approval"; APPROVED/REJECTED → already decided.
4. create_project: new default CREATED (no more born-PENDING fiction).
5. create_change_order gate baseline_status='APPROVED' — unchanged.

## Decisions (D54+)

- D54: State column is truth; log is evidence (adopted, msg 6250).
- D55: Full version — send + link delivery flip state; portal gates on SENT.
- D56: estimate line status ACCEPTED → CREATED (default + live rows); vocabulary
  on the line is CREATED/DRAFT only; acceptance lives ONLY on baseline_status.
- D57: Email send rotates the token pre-render; flip+log atomic post-gmail.
  Link push rotates too; no log row for push (portal decision log covers audit).
- D58: Live remap in db/0031: PENDING → SENT iff an estimate_sent log exists for
  the project (evidence); backfill Test Approval's documented 2026-08-26 send
  (NEXT_STEPS message id 1a037d86d907038d, recipient support.ordrnow@gmail.com)
  so the general rule maps it SENT; remaining PENDING → CREATED. 5650 Camino
  ($270k line) and Oakridge ($30k line) ACCEPTED → CREATED. No CHECK constraint
  (consistent with free-text VARCHAR everywhere); vocabulary enforced by SQL
  defaults + tool descriptions + this doc.
- D59: E2E stays email-free: harness flips fixture to SENT via SQL (send email
  has its own smoke layer); asserts CREATED-gate no-op + SENT-gate approve.
- D60: No zero-line send gate (out of scope; Test Approval demo has no lines).

## File change list

- db/0031_estimate_state.sql — default CREATED on projects.baseline_status;
  estimates.status default CREATED + remap ACCEPTED→CREATED; PENDING remap by
  sent-log evidence; Test Approval log backfill.
- db/0032_estimate_state_verify.sql — self-rolling-back asserts.
- deploy/migrate.sh — register 0031 (MIGRATIONS), 0032 (VERIFY).
- backend/n8n/workflows/voice-gateway.json:
  - create_estimate SQL default + queryReplacement + tool desc default ACCEPTED→CREATED.
  - send_estimate_for_approval chain: lookup exposes baseline_status +
    baseline_approved_by/at; IF gate blocks APPROVED; NEW rotate-token node
    (pre-render); log node gains atomic flip+log CTE.
  - get_estimate_approval_link chain: flip CREATED/REJECTED→SENT + rotate.
  - list_estimate_status Format case: speak CREATED/SENT/APPROVED/REJECTED.
- backend/n8n/workflows/customer-approval-portal.json:
  - Estimate Approval Update SQL: gate PENDING → SENT.
  - Estimate Approval Render + Confirm jsCode vocabulary.
- ~~backend/n8n/workflows/approval-portal.json — stale pre-audit duplicate (same
  workflow id lWJJelblgGSpoJUY, 16 vs 19 nodes); delete to stop drift risk~~ DONE:
  file removed; README/DEPLOY/SYSTEM_DESIGN refs now point at
  customer-approval-portal.json.
- backend/vapi_assistant.json — create_estimate status param default/enum;
  send_estimate_for_approval + get_estimate_approval_link + list_estimate_status
  descriptions (vocabulary + never-create rule); systemPrompt Status Model
  section (~10 lines).
- qa/e2e_estimate_approval.py — SENT-gate flow.
- doc/ESTIMATE_STATE.md (this), doc/NEXT_STEPS.md (D-numbers), doc/SCHEMA.md
  regen (post-migration), doc/APPROVAL_AUDIT.md cross-ref.
- backend/README.md + doc/SYSTEM_DESIGN.md + backend/DEPLOY.md: approval-portal
  filename refs → customer-approval-portal.json.

## Order + QA gates

All phases DONE (2026-09-08): migrations hermetic + live (9512fda), gateway
(b5fe795), portal (0538d3a), Vapi (fbf43ab), E2E 12/12 + real-send probe
(5659205), deployed + marker-verified (10/10), docs below.

1. Migrations → hermetic (zonky scratch full migrate.sh order) → live pg_dump
   snapshot → apply → verify. Commit. ✅
2. Gateway JSON mutation → validation gates (parse/unique/connections/switch
   parity/node --check) → SQL hermetic harness (all branches incl. APPROVED
   block + NONE fallback) → commit. ✅
3. Portal JSON mutation → same validation → SQL branch probe → commit. ✅
4. Vapi assistant JSON (tool defs + prompt) → create_vapi_assistant.py → read-back. ✅
5. E2E script update → L1 live run (12/12) + real-send probe (email→SENT→
   token rotate→log row with Gmail message id). ✅
6. Deploy gateway + portal to VPS (scp/import/activate/restart) → export-verify
   markers (10/10 PASS) → curl routing + live probes green. ✅
7. Docs + SCHEMA regen + skill/memory update + final commit/push. ← this commit
