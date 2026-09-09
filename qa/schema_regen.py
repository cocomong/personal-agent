#!/usr/bin/env python3
"""Regenerate doc/SCHEMA.md from a catalog dump produced by qa/schema_extract.sql.

Usage:
  ssh ubuntu@n8n2.ordrnow.com "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -tA -q -v ON_ERROR_STOP=1" < qa/schema_extract.sql > /tmp/schema_dump.txt
  python3 qa/schema_regen.py /tmp/schema_dump.txt > doc/SCHEMA.md

Run from the repo root (db/*.sql provenance glob). Sections in the dump:
TABLES / COLUMNS / CONSTRAINTS / INDEXES / VIEWS / FUNCTIONS / SEQUENCES,
each a JSON array on a bare ==NAME== marker line.
"""
import json, re, sys, glob
from datetime import date

raw = open(sys.argv[1]).read()
sections = {}
cur = None
buf = []
for line in raw.splitlines():
    m = re.match(r"^==(\w+)==$", line.strip())
    if m:
        if cur: sections[cur] = "".join(buf)
        cur = m.group(1); buf = []
    else:
        buf.append(line)
if cur: sections[cur] = "".join(buf)

def load(sec):
    return json.loads(sections[sec]) or []

tables = {t['name']: t for t in load('TABLES')}
columns = {}
for c in load('COLUMNS'):
    columns.setdefault(c['table_name'], []).append(c)
constraints = {}
for c in load('CONSTRAINTS'):
    constraints.setdefault(c['table_name'], []).append(c)
indexes = {}
for i in load('INDEXES'):
    indexes.setdefault(i['table_name'], []).append(i)
views = load('VIEWS')
functions = load('FUNCTIONS')
sequences = [s['name'] for s in load('SEQUENCES')]

def strip_default(d):
    if not d: return None
    return re.sub(r"::[a-z ]+(?:\(\d+(?:,\d+)?\))?$", "", d)

def fmt_default(d):
    d = strip_default(d)
    return f"default {d}" if d else ""

# provenance: which db/00NN file created/extended each table/column
provenance = {}
for f in sorted(glob.glob('db/*.sql')):
    n = re.search(r"(\d{4})_([a-z0-9_]+)\.sql", f)
    if not n: continue
    tag = f"{n.group(1)}_{n.group(2)}"
    txt = open(f).read()
    for m in re.finditer(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)", txt):
        provenance.setdefault(m.group(1), []).append(tag)
    for m in re.finditer(r"ALTER TABLE (\w+)\s+ADD COLUMN(?: IF NOT EXISTS)?\s+(\w+)", txt):
        key = (m.group(1), m.group(2))
        provenance.setdefault(key, []).append(tag)

def prov_line(tname):
    created = [p for p in provenance.get(tname, [])]
    extra = []
    for k, p in provenance.items():
        if isinstance(k, tuple) and k[0] == tname:
            extra.extend(p if isinstance(p, list) else [p])
    allp = created + extra
    if not allp: return ""
    return f"*created in {', '.join(sorted(set(allp)))}*\n"

def col_row(c):
    flags = []
    if c['not_null']: flags.append("NOT NULL")
    d = fmt_default(c['default_expr'])
    if d: flags.append(d)
    if c['comment']: flags.append(c['comment'])
    return f"| `{c['column_name']}` | `{c['data_type']}` | {', '.join(flags)} |"

out = []
out.append("# Database Schema — live (generated)")
out.append("")
out.append(f"> **Generated {date.today().isoformat()} from the live production DB** (n8n2.ordrnow.com, container `n8n-compose-postgres-1`, db `postgres`, PostgreSQL 17). Reflects migrations 0001–0031 applied. This file is machine-generated, not hand-maintained — after any schema change, re-run the extraction in the Appendix and regenerate.")
out.append("")
out.append("## Conventions")
out.append("- Every business table PK is `id UUID DEFAULT uuid_generate_v4()` (uuid-ossp).")
out.append("- Write tools carry a `tool_call_id` UNIQUE column (ADR-3): replayed Vapi tool calls `ON CONFLICT (tool_call_id) DO NOTHING` instead of double-inserting.")
out.append("- `company_id SMALLINT NOT NULL DEFAULT 1 REFERENCES company_profile(id)` on every directly-scoped table (Step 2, migration 0019). `DEFAULT 1` = the original Ireh row; Step 3 (scoped gateway) drops the default and writes company_id explicitly. `company_profile.id` is a sequence (`company_profile_id_seq`, starts at 2) — one profile per company.")
out.append("- Invoice numbers are per-company sequential: `invoice_prefix + LPAD(invoice_last_number, 4)` (migration 0021), e.g. INV-0001. Legacy timestamp numbers are grandfathered.")
out.append("- Outbound invoice emails (preview / client / resend / reject) are audited in `invoice_email_log` (0021). `invoices.email_sent_at` = first client send; `last_client_html` = the canonical client HTML stored at preview time (approve emails that copy, so previewed == sent).")
out.append("- Children that inherit tenancy via a parent's `project_id` (estimates, change_orders, timesheets, invoice_line_items, payments, payroll_entries) carry no company_id column.")
out.append("- Worker identity: `workers.id` (uuid) is the FK target; `worker_code` (W-###) is a per-company unique display/code handle — two companies may each have a W-001.")
out.append("- Baseline-estimate workflow state lives on `projects.baseline_status`: CREATED (on file, never sent) → SENT (awaiting customer) → APPROVED / REJECTED (0031). `approval_log` (0029) is the evidence trail; never consult it as current state.")

def table_block(tname):
    cols = columns.get(tname, [])
    if not cols: return
    out.append(f"### {tname}")
    out.append("")
    out.append("| Column | Type | Flags / default |")
    out.append("|--------|------|-----------------|")
    for c in cols:
        out.append(col_row(c))
    for c in constraints.get(tname, []):
        if c['type'] == 'f':
            m = re.match(r"FOREIGN KEY \((\w+)\) REFERENCES (\w+)\((\w+)\)", c['definition'])
            out.append(f"- FK: `{m.group(1)}` → `{m.group(2)}({m.group(3)})`" if m else f"- FK: {c['definition']}")
    for c in constraints.get(tname, []):
        if c['type'] == 'u':
            m = re.match(r"UNIQUE \(([^)]+)\)", c['definition'])
            cols_txt = m.group(1) if m else c['definition']
            out.append(f"- UNIQUE constraint `{c['name']}` ({cols_txt})")
    for c in constraints.get(tname, []):
        if c['type'] == 'p':
            out.append(f"- PK constraint `{c['name']}`")
    for c in constraints.get(tname, []):
        if c['type'] == 'c':
            out.append(f"- CHECK: {c['definition']}")
    for i in indexes.get(tname, []):
        out.append(f"- index `{i['name']}`")
    p = prov_line(tname)
    if p:
        out.append("")
        out.append(p.rstrip("\n"))
    out.append("")

# known subsystem groupings; anything else lands in "Other tables"
GROUPS = [
    ("Company & tenancy", ["company_profile", "users"]),
    ("Customers & projects", ["customers", "projects", "estimates", "change_orders", "approval_log"]),
    ("Workers & payroll", ["workers", "payroll_runs", "payroll_entries", "tax_payments", "timesheets", "schedule_items"]),
    ("Invoicing & payments", ["invoices", "invoice_line_items", "invoice_email_log", "payments"]),
    ("App & device", ["device_tokens"]),
]
emitted = set()
for heading, tlist in GROUPS:
    present = [t for t in tlist if t in tables]
    if not present: continue
    out.append(f"## {heading}")
    out.append("")
    for t in present:
        table_block(t)
        emitted.add(t)
rest = [t for t in tables if t not in emitted and columns.get(t)]
if rest:
    out.append("## Other tables")
    out.append("")
    for t in rest:
        table_block(t)
        emitted.add(t)

out.append("## Views")
out.append("")
for v in views:
    out.append(f"### {v['name']}")
    out.append("")
    out.append("```sql")
    out.append(v['definition'].strip())
    out.append("```")
    out.append("")

out.append("## Functions")
out.append("")
for f in functions:
    out.append(f"- `{f['name']}({f['args']})` → `{f['result']}`")
out.append("")
out.append("## Sequences")
out.append("")
for s in sequences:
    out.append(f"- `{s}`")
out.append("")
out.append("## Appendix — how to regenerate")
out.append("")
out.append("1. Extract the catalog: `ssh ubuntu@n8n2.ordrnow.com` → `sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -tA -q -v ON_ERROR_STOP=1` < `qa/schema_extract.sql` (stdin). Sections: TABLES / COLUMNS / CONSTRAINTS / INDEXES / VIEWS / FUNCTIONS / SEQUENCES, each a JSON array on `==NAME==` markers.")
out.append("2. Regenerate this file: `python3 qa/schema_regen.py /tmp/schema_dump.txt > doc/SCHEMA.md` (from the repo root).")
out.append("3. Commit: the header date and contents must match the applied migrations.")

print("\n".join(out))
