# Voice AI & Construction Project Lifecycle Automation — System Design

**Version:** 1.3 (distilled from `Construction Project Management Assistant(1).md`; §13 documents the v1.3 Construction Ops migration)
**Status:** Draft for review
**Source:** Gemini session [`16811441e351d6d8`](https://gemini.google.com/app/16811441e351d6d8)

This document distills the full discussion log into a single, canonical system design. It collapses the overlapping tool-definition sets and overlapping n8n workflows that accumulated during the conversation into **one authoritative tool set and one unified gateway**. Fenced code blocks are restored so every SQL/JSON/snippet is copy-pasteable.

> **Stack direction (current, v1.2).** **Vapi-primary** for voice + text orchestration, with **ElevenLabs as the TTS voice engine inside Vapi**. Rationale: the mobile app's must-have is **voice and text in the same conversation session** — Vapi handles this natively (`vapi.start()` for voice, `vapi.send({type:'add-message',...})` for text on the same session), while ElevenLabs-as-orchestrator required extra wiring. Using ElevenLabs as Vapi's `voice.provider` keeps ElevenLabs' high-quality voice without the session-management cost. The earlier ElevenLabs-only bend is retired; business logic, n8n gateway, and schema are unchanged.

---

## 1. Executive Summary

An AI-driven **voice + text assistant** for a construction manager running 3–4 concurrent projects, covering the full lifecycle from lead/quote → change orders → progressive invoicing → customer delivery → payroll.

- **Voice orchestration:** Vapi.com — native **same-session voice + text** (voice via `vapi.start`, text via `vapi.send`), packaged as a **Flutter (Dart)** mobile app.
- **Voice engine:** ElevenLabs voices configured as Vapi's `voice.provider = '11labs'`.
- **Workflow automation:** n8n as the central router and business-logic engine (receives Vapi tool-calls).
- **Data layer:** Supabase / PostgreSQL (relational, 7 tables + a rollup view).
- **Email delivery:** Gmail (SMTP + App Password) for customer invoices and approval links.

### System flow

```mermaid
flowchart TD
    MOB[Flutter App<br/>Voice + Text (same session)] --> V[Vapi.com<br/>LLM + STT + TTS + Tools]
    V -- "voice: 11labs (TTS engine)" --> ELV[ElevenLabs Voice]
    V -- "HTTP webhook / JSON tool-call" --> N[n8n Gateway<br/>Router Engine]
    N --> DB[(Supabase / PostgreSQL)]
    N --> EMAIL[SendGrid / SMTP]
    N -- "results[] in <1.2s" --> V
    V --> MOB
```

### Final decision summary ("Current Stack")

| Concern | Decision |
|---|---|
| Voice + text orchestration | **Vapi.com** — native same-session voice + text (voice `vapi.start` / text `vapi.send`), **Flutter (Dart)** app (ADR-8) |
| Voice engine | **ElevenLabs** configured as Vapi's `voice.provider='11labs'` for high-quality TTS (ADR-9) |
| Workflow / business logic | **n8n** (single unified gateway webhook) |
| Database | **Supabase / PostgreSQL**, 7 tables + rollup view |
| Customer document delivery | HTML portal (screen print-to-PDF + CSV export) + Gmail (SMTP) email |
| Financial calculation | **In PostgreSQL**, never in the LLM |
| Response latency target | n8n returns a `results[]` payload in **< 1,200ms** for in-conversation actions |

> **One backend, one n8n gateway.** Vapi routes tool-calls (change orders, timesheets, statements, invoices) to the n8n gateway, which is Vapi-native. ADR-4 governs the single shared webhook. This restores the original Vapi-first direction from the discussion log, with ElevenLabs contributing voice quality rather than orchestration.

---

## 2. System Architecture

```
Layered view
[ User Input ] (Site Supervisor / Project Manager)
      │
      ├── Web App / Mobile App (WebRTC / Vapi)
      └── Phone Dial-in (Twilio / Telephony)
      │
      ▼
┌───────────────────────────────┐
│  1. Voice Orchestration Layer │  STT + TTS + real-time turn-taking
└───────────────┬───────────────┘
                │ Tool Call / Webhook
                ▼
┌───────────────────────────────┐
│  2. Workflow & Middleware     │  Logic execution, JSON validation, routing
└───────┬───────────────┬───────┘
        ▼               ▼
┌──────────────┐  ┌────────────────┐
│ 3. LLM Core  │  │ 4. Data Layer  │  Projects, Change Logs, Payroll DB
└──────────────┘  └────────────────┘
```

- **Layer 1 — Voice Orchestration:** Vapi.com handles two-way streaming, noise reduction, STT, TTS, interruption handling, LLM reasoning + tool calling — with **ElevenLabs as the voice/TTS engine** (`voice.provider='11labs'`). Native WebRTC; same-session voice + text (`vapi.start` / `vapi.send`).
- **Layer 2 — Middleware / n8n:** Receives Vapi tool-call webhooks, authenticates them (e.g. `x-vapi-secret`), routes to sub-branches, executes DB transactions, returns a formatted `results[]` payload.
- **Layer 3 — LLM / Reasoning:** Configured inside Vapi (Vapi-hosted or bring-your-own LLM). Extracts entities (dates, names, hours, dollar amounts, project codes).
- **Layer 4 — Data:** Supabase/PostgreSQL (relational). Accounting integrations: QuickBooks Online / Xero / Gusto via n8n (optional).

### Real-world execution (voice change order)

1. **User:** *"Add a change order for Job 102. Client wants 4 extra recessed lights in the kitchen. Estimate $600 parts and 3 hours labor."*
2. **Vapi** detects a `create_change_order` tool call with:
   ```json
   {
     "project_id": "102",
     "description": "Extra kitchen recessed lights",
     "material_cost": 600,
     "labor_hours": 3,
     "status": "Pending Approval"
   }
   ```
3. **n8n** webhook authenticates + inserts the change-order row (+ updates revised contract on approval).
4. **Vapi** speaks back: *"Draft Change Order #4 for Job 102 created for $600 parts + 3 hours labor. Updated pending total is $1,050."*

---

## 3. Database Schema (PostgreSQL / Supabase)

Canonical DDL. **No LLM performs financial math — all rollups live in SQL views.**

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. CUSTOMERS (client contact & billing)
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    email       VARCHAR(255) UNIQUE NOT NULL,
    phone       VARCHAR(50),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. PROJECTS (one customer -> many projects)
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    site_address TEXT NOT NULL,
    original_contract_value NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    revised_contract_value  NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    status VARCHAR(50) DEFAULT 'ACTIVE',  -- ACTIVE, COMPLETED, ON_HOLD
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. ESTIMATES (base scope — locked once approved; do NOT mix change orders here)
CREATE TABLE estimates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    division_code VARCHAR(50) NOT NULL,  -- e.g. Framing, Electrical, Plumbing
    scope_description TEXT NOT NULL,
    allocated_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. CHANGE ORDERS (amendments — kept separate from baseline estimate)
CREATE TABLE change_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    change_order_number INT NOT NULL,
    description TEXT NOT NULL,
    cost_impact NUMERIC(12,2) NOT NULL,       -- + additions, - credits
    schedule_impact_days INT DEFAULT 0,
    approval_status VARCHAR(50) DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. TIMESHEETS (payroll & job costing)
CREATE TABLE timesheets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    worker_name VARCHAR(255) NOT NULL,
    hours_worked NUMERIC(5,2) NOT NULL,
    work_description TEXT,
    date_worked DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. INVOICES (billings referencing estimate progress or change orders)
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    invoice_number VARCHAR(100) UNIQUE NOT NULL,
    invoice_type VARCHAR(50) NOT NULL,  -- DEPOSIT, PROGRESS_BILLING, CHANGE_ORDER, FINAL
    amount_due NUMERIC(12,2) NOT NULL,
    holdback_amount NUMERIC(12,2) DEFAULT 0.00,   -- e.g. statutory 10% retainage
    status VARCHAR(50) DEFAULT 'UNPAID',           -- UNPAID, PAID, OVERDUE
    issued_date DATE DEFAULT CURRENT_DATE,
    due_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. INVOICE LINE ITEMS (link invoices to estimate_progress or change_order sources)
CREATE TABLE invoice_line_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id UUID REFERENCES invoices(id) ON DELETE CASCADE,
    source_type VARCHAR(50) NOT NULL,  -- 'estimate_progress' or 'change_order'
    source_id UUID,
    description TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL
);
```

### Rollup view — project financial summary

```sql
CREATE OR REPLACE VIEW view_project_financial_summary AS
SELECT
    p.id AS project_id,
    p.title AS project_name,
    p.status AS project_status,
    c.id AS customer_id,
    CONCAT(c.name, '') AS customer_name,
    c.email AS customer_email,
    COALESCE(e.original_contract, 0.00) AS original_contract_value,
    COALESCE(co.approved_co_total, 0.00) AS approved_change_orders_total,
    (COALESCE(e.original_contract, 0.00) + COALESCE(co.approved_co_total, 0.00)) AS total_revised_contract_value,
    COALESCE(inv.total_invoiced, 0.00) AS total_invoiced,
    COALESCE(inv.total_paid, 0.00) AS total_paid,
    ((COALESCE(e.original_contract, 0.00) + COALESCE(co.approved_co_total, 0.00))
        - COALESCE(inv.total_paid, 0.00)) AS balance_remaining,
    COALESCE(inv.unbilled, 0.00) AS remaining_unbilled_contract,
    COALESCE(ts.total_labor_hours, 0.00) AS total_labor_hours
FROM projects p
JOIN customers c ON p.customer_id = c.id
LEFT JOIN (
    SELECT project_id, SUM(allocated_amount) AS original_contract
    FROM estimates GROUP BY project_id
) e ON p.id = e.project_id
LEFT JOIN (
    SELECT project_id, SUM(cost_impact) AS approved_co_total
    FROM change_orders WHERE approval_status = 'APPROVED' GROUP BY project_id
) co ON p.id = co.project_id
LEFT JOIN (
    SELECT project_id,
           SUM(amount_due) AS total_invoiced,
           SUM(CASE WHEN status = 'PAID' THEN amount_due ELSE 0.00 END) AS total_paid,
           SUM(CASE WHEN status <> 'PAID' THEN amount_due ELSE 0.00 END) AS unbilled
    FROM invoices GROUP BY project_id
) inv ON p.id = inv.project_id
LEFT JOIN (
    SELECT project_id, SUM(hours_worked) AS total_labor_hours
    FROM timesheets GROUP BY project_id
) ts ON p.id = ts.project_id;
```

### Supporting queries

**Unbilled approved change orders** (for inclusion in the next progress invoice):

```sql
SELECT co.id AS change_order_id, co.change_order_number, co.description, co.cost_impact
FROM change_orders co
WHERE co.project_id = $1
  AND co.approval_status = 'APPROVED'
  AND co.id NOT IN (
      SELECT source_id FROM invoice_line_items
      WHERE source_type = 'change_order' AND source_id IS NOT NULL
  );
```

**Customer portfolio rollup:**

```sql
SELECT c.id AS customer_id,
       CONCAT(c.name, '') AS customer_name,
       COUNT(p.id) AS total_projects,
       SUM(v.total_revised_contract_value) AS total_portfolio_value,
       SUM(v.total_invoiced) AS total_portfolio_invoiced,
       SUM(v.balance_remaining) AS total_outstanding_balance
FROM customers c
JOIN projects p ON c.id = p.customer_id
JOIN view_project_financial_summary v ON p.id = v.project_id
WHERE c.id = $1
GROUP BY c.id, c.name;
```

---

## 4. Agent Tool Definitions (business actions)

The 17 tools below are the **business actions** the agent can invoke (12 original + 5 added in v1.3). They are **Vapi function tools**. Each tool points at the **single unified n8n gateway** webhook (`POST /webhook/voice/gateway`); n8n dispatches on the function name against the shared business logic.

> **Voice-engine note.** The Vapi assistant's `voice.provider` is set to `'11labs'` (ElevenLabs) for high-quality TTS — this is a Vapi assistant setting, independent of the tool definitions. The `server.url` on each tool points to the n8n gateway, where Vapi POSTs the tool-call.

### tool: `lookup_or_create_customer`

```json
{
  "type": "function",
  "function": {
    "name": "lookup_or_create_customer",
    "description": "Checks if a customer exists by email or full name; creates a new customer if not found.",
    "parameters": {
      "type": "object",
      "properties": {
        "first_name": { "type": "string", "description": "Customer's first name" },
        "last_name":  { "type": "string", "description": "Customer's last name" },
        "email":      { "type": "string", "description": "Customer email address" },
        "phone":      { "type": "string", "description": "Customer phone number" }
      },
      "required": ["first_name", "last_name", "email"]
    }
  }
}
```

### tool: `create_project`

```json
{
  "type": "function",
  "function": {
    "name": "create_project",
    "description": "Creates a new job site assigned to an existing customer ID.",
    "parameters": {
      "type": "object",
      "properties": {
        "customer_id":  { "type": "string", "description": "UUID of the customer from lookup_or_create_customer" },
        "project_name": { "type": "string", "description": "Shorthand site name (e.g. Kitsilano Reno)" },
        "site_address": { "type": "string", "description": "Physical site address" }
      },
      "required": ["customer_id", "project_name"]
    }
  }
}
```

### tool: `create_estimate`

```json
{
  "type": "function",
  "function": {
    "name": "create_estimate",
    "description": "Creates the initial baseline quote for a project (base scope contract).",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id":        { "type": "string", "description": "Target project UUID or shorthand name" },
        "scope_description": { "type": "string", "description": "Summary of baseline work scope" },
        "labor_estimate":    { "type": "number", "description": "Estimated labor cost" },
        "material_estimate": { "type": "number", "description": "Estimated material cost" }
      },
      "required": ["project_id", "scope_description"]
    }
  }
}
```

### tool: `create_change_order`

```json
{
  "type": "function",
  "function": {
    "name": "create_change_order",
    "description": "Creates a standalone change order amendment. DO NOT use for initial estimates.",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id":   { "type": "string", "description": "Target project UUID or shorthand name" },
        "description":  { "type": "string", "description": "Scope update or addition" },
        "labor_cost":   { "type": "number", "description": "Additional labor cost" },
        "material_cost": { "type": "number", "description": "Additional material cost" }
      },
      "required": ["project_id", "description"]
    }
  }
}
```

### tool: `log_timesheet`

```json
{
  "type": "function",
  "function": {
    "name": "log_timesheet",
    "description": "Logs worked hours for a worker on a specific construction project.",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id":      { "type": "string", "description": "UUID of the project." },
        "worker_name":     { "type": "string", "description": "Full name of the worker." },
        "hours_worked":    { "type": "number", "description": "Number of hours to log (e.g. 7.5)." },
        "work_description":{ "type": "string", "description": "Summary of tasks performed." }
      },
      "required": ["project_id", "worker_name", "hours_worked"]
    }
  }
}
```

### tool: `create_invoice`

```json
{
  "type": "function",
  "function": {
    "name": "create_invoice",
    "description": "Generates a draft invoice pulling from progress on the base estimate or approved change orders.",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id": {
          "type": "string",
          "description": "Target project UUID or shorthand name"
        },
        "invoice_type": { "type": "string", "enum": ["Deposit", "Progress", "Change Order", "Final"] },
        "include_change_order_ids": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Array of Change Order UUIDs to include as separate line items"
        },
        "billing_percentage": { "type": "number", "description": "Percentage of base contract to bill (e.g. 25 for 25% progress)" }
      },
      "required": ["project_id", "invoice_type"]
    }
  }
}
```

### tool: `send_customer_invoice`

```json
{
  "type": "function",
  "function": {
    "name": "send_customer_invoice",
    "description": "Triggers email delivery of a draft invoice to the client on file.",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id": { "type": "string", "description": "Target project name or ID" },
        "invoice_id": { "type": "string", "description": "Specific invoice number to send (e.g. INV-1002)" }
      },
      "required": ["project_id"]
    }
  }
}
```

### tool: `get_project_statement`

```json
{
  "type": "function",
  "function": {
    "name": "get_project_statement",
    "description": "Retrieves current financial summary, total billed, change orders, and balance due for a project.",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id": { "type": "string", "description": "UUID of the project." }
      },
      "required": ["project_id"]
    }
  }
}
```

### tool: `get_estimate_approval_link`

```json
{
  "type": "function",
  "function": {
    "name": "get_estimate_approval_link",
    "description": "Returns a customer-facing approval page link to sign the baseline estimate (contract).",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id": { "type": "string", "description": "Target project UUID or shorthand name" }
      },
      "required": ["project_id"]
    }
  }
}
```

### tool: `get_change_order_approval_link`

```json
{
  "type": "function",
  "function": {
    "name": "get_change_order_approval_link",
    "description": "Returns a customer-facing approval page link to sign a change order (amendment).",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id": { "type": "string", "description": "Target project UUID or shorthand name" },
        "change_order_number": { "type": "number", "description": "The change order number to approve (per project)" }
      },
      "required": ["project_id", "change_order_number"]
    }
  }
}
```

### tool: `send_estimate_for_approval`

```json
{
  "type": "function",
  "function": {
    "name": "send_estimate_for_approval",
    "description": "Emails the customer a link to sign the baseline estimate (contract).",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id": { "type": "string", "description": "Target project UUID or shorthand name" }
      },
      "required": ["project_id"]
    }
  }
}
```

### tool: `send_change_order_for_approval`

```json
{
  "type": "function",
  "function": {
    "name": "send_change_order_for_approval",
    "description": "Emails the customer a link to sign a change order (amendment).",
    "parameters": {
      "type": "object",
      "properties": {
        "project_id": { "type": "string", "description": "Target project UUID or shorthand name" },
        "change_order_number": { "type": "number", "description": "The change order number to approve (per project)" }
      },
      "required": ["project_id", "change_order_number"]
    }
  }
}
```

---

## 5. n8n — Unified Voice Gateway

A single webhook catches all Vapi tool-call traffic; a Switch Node routes on the **function name** to the right business action.

```mermaid
flowchart TD
    W[POST /voice/gateway] --> SR{Actions Sub-Router<br/>on function name}
    SR -->|log_timesheet| T1[Insert timesheet]
    SR -->|create_change_order| T2[Insert CO + update revised contract]
    SR -->|get_project_statement| T3[Query rollup / statement]
    SR -->|send_customer_invoice| T4[Email invoice via SendGrid]
    T1 & T2 & T3 & T4 --> AR[Respond with results[]]
```

| # | Node | Type | Role |
|---|---|---|---|
| gate-0001 | Voice Gateway Webhook | Webhook (POST `/voice/gateway`, responseNode) | Entry point for all Vapi tool-calls |
| gate-0002 | Authenticate | Code/Set | Validate Vapi signature / `x-vapi-secret` header |
| gate-0003 | Actions Sub-Router | Switch v3 | Route on the tool/function name |
| gate-0004 | Exec: log_timesheet | PostgreSQL insert | Write timesheet row |
| gate-0005 | Exec: create_change_order | PostgreSQL transaction | Insert CO; on APPROVED update revised_contract_value |
| gate-0006 | Exec: get_project_statement | PostgreSQL query | Query the rollup view |
| gate-0007 | Exec: send_customer_invoice | Email (SendGrid) | Email the invoice to the client |
| gate-0008 | Respond Vapi | Respond to Webhook `{ results[] }` | Return the speech result |

> **Implementation note.** The `backend/n8n/workflows/voice-gateway.json` scaffold wires all 8 tool branches to PostgreSQL executors (plus a `Render Invoice HTML` + SendGrid email step for `send_customer_invoice`, design Section 7 HTML-over-PDF). The SQL schema is in `db/0001_init.sql`; tests/seed in `db/0002_idempotency_test.sql` and `db/0003_seed.sql`. `create_invoice` computes `amount_due` in SQL as `revised_contract_value * billing_percentage/100` (ADR-2); `change_orders`/`timesheets` INSERTs use `ON CONFLICT (tool_call_id) DO NOTHING` (ADR-3).

### Customer approval portal (ADR-10)

A second workflow, `backend/n8n/workflows/approval-portal.json`, hosts the **customer-facing** approval pages and actions (not reached by Vapi — reached by the customer's browser):

| Endpoint | Method | Purpose |
|---|---|---|
| `/webhook/approve-estimate?token=` | GET | Renders the baseline estimate + Approve/Reject form |
| `/webhook/estimate/approval` | POST | Records baseline approval, sets `original_contract_value` = Σ(estimates) |
| `/webhook/approve-change-order?token=` | GET | Renders a single change order + Approve/Reject form |
| `/webhook/change-order/approval` | POST | Records CO approval, recomputes `revised_contract_value` |

- Approval is **token-gated** (`approval_token` UUID on `change_orders`; `baseline_approval_token` on `projects`). Links are surfaced on-site via the two link tools, or (later) emailed/embedded in the Section 7 portal.
- Approvals record `approved_by` (`customer`/`pm`), `approval_method` (`onsite_link`/`email_link`/`portal`/`verbal`), and `signer_name` (typed-name e-signature) for the audit trail.
- `create_change_order` is gated: it refuses until `projects.baseline_status = 'APPROVED'` (you can't amend an unsigned contract).
- **PostgreSQL snapshot gotcha:** data-modifying CTEs share one statement snapshot, so a `recalc` CTE cannot see a `decided` CTE's just-committed `APPROVED` flip. The CO-approval SQL therefore adds the just-approved `decided` delta explicitly rather than re-reading `change_orders`.

### Standardized Vapi response payload

n8n must return HTTP 200 within 1,200ms so Vapi can speak the result without stalling:

```json
{
  "results": [
    {
      "toolCallId": "{{ $json.body.message.toolCalls[0].id }}",
      "result": "Change order #4 successfully created for $2,500. Revised contract total is now $48,500."
    }
  ]
}
```

The `toolCallId` must echo the id from the originating Vapi tool-call so Vapi attaches the result to the right invocation (idempotency — ADR-3).

---

## 6. Agent System Prompt (canonical)

This is the instruction/context block configured on the **Vapi assistant**. Configure the assistant's `voice.provider` to `'11labs'` (ElevenLabs) for the voice engine.

```text
# Role & Context
You are an executive voice project assistant managing 3-4 construction sites. You
interact with database systems via tool calls to manage Customers, Projects,
Estimates, Change Orders, Invoices, and Payroll.

# Rules of Operations & Logic
1. Customer First: Before creating a project, verify or create the Customer record
   using `lookup_or_create_customer`.
2. Estimates vs Change Orders:
   - Base scope = `create_estimate` (sets the baseline contract value).
   - Any modifications after initial setup = `create_change_order`.
   - NEVER overwrite the baseline estimate.
3. Invoicing: Invoices may include progress percentages of the base estimate OR
   specific approved change orders as distinct line items.
4. Communication Style:
   - Speak in clear, short sentences (10–15 words max).
   - Confirm critical details (Customer Name, Project Name, Dollar Amounts) before
     executing tools.
   - Summarize tool execution outcomes in a single sentence.
```

---

## 7. Customer Document Delivery — HTML Portal

Prefer rendering project statements as a **dynamic HTML page** (native `@media print` → PDF; no heavy PDF engine) rather than a pre-generated static PDF.

- **Real-time visibility:** client/manager refreshes `https://pm.yourdomain.com/portal?project_id=<id>` for live running totals.
- **Zero PDF server overhead:** browser print engine produces a pixel-perfect PDF on demand.
- **Built-in CSV export:** bookkeepers / sub-trades download raw tables for Excel / payroll.

### Dashboard sections

1. **Action bar** (screen-only): Export CSV + Download PDF/Print buttons (hidden on print).
2. **Project & customer header card:** site address, status badges, contacts, dates.
3. **Financial metric cards:** Original Contract, Approved COs, Total Revised Contract, Total Billed, Balance Remaining.
4. **Baseline scope table:** locked base contract by division/cost code.
5. **Change orders table:** approved vs. pending amendments, labor/material splits.
6. **Invoicing ledger:** deposit/progress/final billings with status badges.
7. **Timesheet log:** labor hours by worker and trade.

### Serving the dashboard (n8n)

1. **Webhook (GET `/project-portal`)**, responseMode = Respond to Webhook.
2. **PostgreSQL** node: `SELECT * FROM view_project_financial_summary WHERE project_id = $1;` using `{{ $json.query.project_id }}`.
3. **Respond to Webhook** node: Respond With = Text, body = rendered HTML, header `Content-Type: text/html; charset=utf-8`.

---

## 8. Mobile App — Vapi Flutter SDK (voice + text, same session)

**Stack:** `vapi` (pub.dev, Dart). One `VapiClient`/`VapiCall` drives **both voice and text on the same call session** natively — no extra text relay needed. The Vapi assistant's voice engine is set to **ElevenLabs** (`provider: '11labs'`). Reference implementation: `mobile-flutter/`.

### 8.1 Setup

```bash
flutter create personal_agent_mobile
cd personal_agent_mobile
flutter pub add vapi
# then copy lib/ + config from mobile-flutter/
```

**Platform requirements** (via the `daily_flutter` WebRTC dep): **iOS 13+**, **Android SDK 24+**.

**Permissions:**
- iOS `Info.plist`: `NSMicrophoneUsageDescription` (+ audio background mode; Podfile `PERMISSION_MICROPHONE=1`).
- Android `AndroidManifest.xml`: `RECORD_AUDIO`, `INTERNET`, `MODIFY_AUDIO_SETTINGS`; `minSdk = 24`.

> Full setup + the required **Dart SDK ≥ 3.6.0** (for `vapi` 0.1.0) is in `mobile-flutter/SETUP.md`.

### 8.2 Initialize + start a voice call

```dart
import 'package:vapi/vapi.dart';

// Wait for the SDK (required on web; instant on mobile)
await VapiClient.platformInitialized.future;
final client = VapiClient('YOUR_VAPI_PUBLIC_KEY');

final call = await client.start(assistantId: 'YOUR_VAPI_ASSISTANT_ID');
call.onEvent.listen((event) {
  if (event.label == 'call-start') { /* ... */ }
  if (event.label == 'message') { /* transcript / status */ }
});
```

> The assistant (configured in the Vapi dashboard) supplies the model, system prompt (Section 6), tools (Section 4 → n8n gateway), and **voice provider = '11labs'**.

### 8.3 Text in the SAME call session

While the (voice) call is active, send a typed message on the **same session**:

```dart
// While the (voice) call is active, send a typed message on the SAME call:
await call.send({
  'type': 'add-message',
  'message': {'role': 'user', 'content': draft},
});

// Optional: mute the mic while typing so it is not read as speech
call.setMuted(true);   // at text-input focus
call.setMuted(false);  // back to voice mode
```

Because it's the same session, the agent keeps full context across speak-or-type turns. No backend relay or mute-pause dance is required — this is Vapi's native same-session model (the reason Vapi was chosen over ElevenLabs-as-orchestrator).

### 8.4 Why voice-first + text fallback (ADR-8)

- Voice is primary: hands-free, natural turn-taking, low latency.
- Text is a subordinate fallback: quiet environments, poor audio, or when typing is preferred.
- Both feed the same Vapi session → one shared transcript (via the `message` event).

### 8.5 Component split (implementation step #2)

| Component | Responsibility |
|---|---|
| `VapiSessionController` (Dart) | Wraps the `VapiClient`/`VapiCall`: init public key, `start()`/`stop()`, `sendUserText()`, `setMuted()`, event wiring (`call-start`/`call-end`/`message`) — see `mobile-flutter/lib/session/` |
| `AgentScreen` (Dart) | Composes the controller + transcript + mode switch (voice default / text fallback) — see `mobile-flutter/lib/agent_screen.dart` |

---

## 9. Client Authentication

### 9.1 Vapi (primary)

The mobile app authenticates to Vapi with a **Vapi public API key**, which Vapi designs for client-side exposure (it is not a secret; server keys exist separately for backend calls):

```dart
import 'package:vapi/vapi.dart';
final client = VapiClient('YOUR_VAPI_PUBLIC_KEY');
```

**Key separation:**
- **Public key** — used in the Flutter app to start the assistant session. Safe by design.
- **Server/secret key** — used only backend-side (e.g. n8n) to create/update assistants or call the Vapi API. **Never** ship this to the mobile bundle.

The server URL for the app's secret-side operations is the n8n gateway.

### 9.2 ElevenLabs voice engine (secondary)

Because ElevenLabs is used only as Vapi's **voice/TTS provider** (`provider: '11labs'`), no ElevenLabs API key is needed in the mobile app — Vapi mediates the TTS. If an ElevenLabs key is ever required server-side (e.g. for a custom voice), keep it in the backend environment, never the client.

> **Earlier signed-URL design (retired for the app path).** When ElevenLabs was the orchestrator, the backend minted signed URLs (`GET /v1/convai/conversation/get-signed-url`) / WebRTC tokens for private agents. That approach is no longer needed for the mobile app under Vapi-primary; it is preserved in the source log (`Construction Project Management Assistant(1).md`) if still required for a custom ElevenLabs endpoint.

## 10. Architectural Decision Records (ADR)

### ADR-1 — Synchronous response for voice feedback
- **Context:** Voice agents need fast feedback to avoid user drop-off / speech overlap.
- **Decision:** DB operations in n8n run synchronously with a 3,000ms statement timeout. Complex PDF generation / email dispatch is offloaded to async background sub-workflows.

### ADR-2 — Strict financial calculation in the database
- **Context:** LLMs struggle with precise cumulative financial arithmetic across complex change-order logs.
- **Decision:** All financial balances, holdback percentages, and statement summaries are computed by SQL inside PostgreSQL, never in the LLM.

### ADR-3 — Idempotency keys on functions
- **Context:** Voice reconnects / retries can double-trigger billings or change-order additions.
- **Decision:** Pass the agent's tool-call id / a call transaction ID as an idempotency key to prevent duplicate timesheet / change-order inserts.

### ADR-4 — Single unified n8n gateway (new)
- **Context:** The design accumulated overlapping n8n workflows and multiple per-tool webhook URLs.
- **Decision:** One shared webhook (`/voice/gateway`) receives all Vapi tool-calls and routes on the function name to the shared business logic (PostgreSQL). Supersedes the earlier separate per-service workflows captured in the discussion log.

### ADR-5 — Vapi public-key client auth (updated)
- **Context:** Mobile binaries can be reverse-engineered; no long-lived secrets belong in-app.
- **Decision:** The mobile app authenticates to Vapi with its **public key** (designed for client use). Secret/server keys stay backend-side (n8n). ElevenLabs signed-URL minting is retired for the app path (ElevenLabs is now only Vapi's voice provider).

### ADR-6 — Estimates vs. Change Orders separation
- **Context:** The original estimate is the signed base contract; change orders are amendments.
- **Decision:** Estimates are locked once approved and never overwritten. Change orders are stored separately and surfaced as their own line items on invoices. Scope-creep visibility (`Base + CO#1 + CO#2 = Revised`) is preserved.

### ADR-7 — Dynamic HTML portal for customer delivery
- **Context:** Static PDF generation adds server overhead and is not live.
- **Decision:** Render project statements as dynamic HTML with `@media print`-to-PDF and CSV export via the browser; serve the page from the n8n `project-portal` webhook.

### ADR-8 — Voice-primary, text-secondary mobile agent (new)
- **Context:** The mobile agent must suit a site supervisor who talks hands-free, but also needs a fallback when audio is unavailable or undesirable.
- **Decision:** Build the mobile agent around **voice-first** via the **Vapi Flutter SDK**, with **text chat as a secondary fallback on the SAME Vapi session** (`vapi.send({type:'add-message',...})`). The agent keeps context across speak-or-type turns because both modes run on one Vapi call session. Voice owns UI priority; text is subordinate.

### ADR-9 — ElevenLabs as Vapi's voice engine (new)
- **Context:** The mobile must-have is same-session voice + text. ElevenLabs-as-orchestrator required extra wiring; Vapi does it natively.
- **Decision:** Use **Vapi** for orchestration and set the assistant's `voice.provider='11labs'` so the TTS quality comes from ElevenLabs without ElevenLabs session-management cost. This recovers the ElevenLabs-first bend from v1.1.

### ADR-10 — Customer-gated approval with tokenized pages (new)
- **Context:** The baseline estimate and change orders are legal amendments; `revised_contract_value` must move only when the **customer** signs, not when the PM asserts consent.
- **Decision:** Tokenized approval pages (`approval-portal.json`) let the customer sign on the spot via a link (and later email/portal). Approvals record `approved_by`/`approval_method`/`signer_name`; `revised_contract_value` recomputes only on customer approval, and `create_change_order` is gated on `baseline_status = 'APPROVED'`.

---

## 11. Implementation Plan & Milestones

| Phase | Core Deliverables | Timeline |
|---|---|---|
| **Phase 1: Foundation** | Supabase migrations (Section 3 schema + rollup view), index optimization, API auth rules | Week 1 |
| **Phase 2: n8n Core** | Unified gateway (Section 5) wired to PostgreSQL, switch routing, `results[]` response, error handling | Week 2 |
| **Phase 3: Vapi Integration** | Vapi assistant (system prompt Section 6, tools Section 4, voice provider='11labs'), webhook binding to the n8n gateway, latency tuning | Week 3 |
| **Phase 4: Billing & Mail** | HTML-to-PDF dashboard (Section 7), SendGrid email triggers, end-to-end testing | Week 4 |
| **Phase 5: Mobile app** | Flutter **voice+text agent app** (Section 8, Vapi Flutter SDK; `mobile-flutter/`) | Week 5–6 |

---

## 12. Open Questions / Next Actions

- [ ] Build the Vapi assistant (voice provider='11labs') and confirm same-session voice+text on a device.
- [ ] Decide gateway routing: single `/voice/gateway` path vs. per-tool webhook paths.
- [ ] Choose accounting integration (QuickBooks Online / Xero / Gusto) for payroll + invoicing sync.
- [ ] Select and lock the LLM model configured in the Vapi assistant.
- [ ] Validate the rollup view naming: this design uses `allocated_amount`/`cost_impact`; reconcile with any existing sheet columns when migrating.

---

## 13. v1.3 — Construction Ops Migration (Ireh Construction)

The v1.3 change set ports the proven capabilities of the Google Sheets "Construction Ops" tracker into this stack. Full detail in **`doc/MIGRATION_PLAN.md`**; the migration is implemented in `db/0007`–`0013` + the n8n workflow edits.

### Company profile (branding as config)
New single-row **`company_profile`** table (`db/0007`) is the single source of truth for branding and financial defaults — seeded with **Ireh Construction** (1951 Kaptey Ave, Coquitlam BC V3K 5Z7, 778-994-6602), brand colors, doc prefixes, and BC rates (GST 5%, PST 7%, retention 10%, CPP 5.95%, EI 1.63%, WCB 3.25%, monthly payroll). The n8n email/approval renderers read these via `CROSS JOIN company_profile` — no hardcoded strings remain.

### New subsystems
| # | Migration | Schema |
|---|---|---|
| 0001 + 0008 | Workers + payroll | `workers` (0001), `timesheets.worker_id` FK (0001), `payroll_runs`, `payroll_entries`, `fn_run_payroll()` (0008), `timesheets.overtime_hours` (0008) |
| 0009 | Tax + payments | `invoices.net/gst/pst_amount` + `pst_applicable`, `payments`, `view_invoice_payments`, `recompute_invoice_status()` |
| 0010 | Quote trail | `estimates.revision/status/valid_until/sent_at`, `change_orders.reason` |
| 0011 | Dashboard views | `view_project_financial_summary` (tax-aware, ledger-driven, margin/retention/overdue), `view_payroll_summary`, `view_overdue_invoices`, `view_quote_followups` |

### New voice tools (17 total)
`record_payment`, `run_payroll`, `get_payroll_summary`, `add_worker`, `get_dashboard_summary` — plus updated params on `create_invoice` (`pst_applicable`), `create_change_order` (`reason`), `create_estimate` (`revision`/`status`/`valid_until`), `log_timesheet` (`overtime_hours`). JSON in `backend/vapi_tools_additions.json`.

### New automation
Three n8n Schedule Trigger workflows: `daily-overdue-check` (08:00), `daily-quote-followup` (09:00), `monthly-payroll-digest` (1st, 07:00).

### Decisions (Dave, 2026-08-22)
Branding = full legal name/address/phone (configurable) · GST always + PST per-invoice flag · n8n HTML→PDF (reportlab fallback) · **monthly** payroll, DRAFT → approve · all 5 new tools shipped.

## 14. Scheduling & Reminders (v1.4)

### 14.1 What's missing
The schema tracks money (invoices/payments), people (workers/timesheets) and
approvals (estimates/change_orders), but NOT time — there is no tasks /
milestones / events / deadlines table. The only date columns are scattered
(`invoices.due_date`, `estimates.valid_until`, `change_orders.approved_at`,
`projects.baseline_approved_at`, `timesheets.date_worked`). Everything else
lives in Dave's head. This section adds a schedule layer + reminder channels.

### 14.2 Scheduling needs (construction PM taxonomy)
- **A. Project phases / milestones** — permits applied/issued, excavation,
  foundation, framing, rough-ins (elec/plumbing/HVAC), inspections (footing,
  framing, plumbing, electrical, insulation, final/occupancy), drywall/finishes,
  substantial completion, punch list, closeout.
- **B. Statutory deadlines (BC Builders Lien Act)** — 10% holdback on every
  payment; **45-day** lien filing window; **55-day** holdback release; holdback
  account on projects >$100k; **30-day** abandonment trigger. High legal risk;
  these should be auto-computed.
- **C. Financial schedule** — progress draws, invoice due dates, retention
  release, quote validity expiry, change-order approval deadlines.
- **D. Workforce + materials** — sub booking, worker start dates, long-lead-item
  delivery dates.
- **E. Client/approval deadlines** — estimate/CO approval reminders, client
  finish selections.
- **F. Post-handover** — warranty expiry, 1-year deficiency walkthrough.

### 14.3 Schema integration (two layers → one view)
- **Explicit** — new `schedule_items` table (db/0014): `id`, `project_id` (FK,
  nullable), `type` (milestone|inspection|permit|delivery|meeting|task|lien|
  holdback|warranty), `title`, `description`, `due_date`, `due_time`, `status`
  (PENDING|DONE|CANCELLED), `priority`, `assigned_to`, `reminder_days`,
  `reminder_sent_at`, `completed_at`, `created_at`.
- **Auto-derived** — no entry needed; computed in `view_schedule`:
  - `invoices` → `invoice_due` (due_date)
  - `estimates` → `quote_expiry` (valid_until)
  - `change_orders` → `co_approval` (approval window)
  - `projects` → `lien_deadline` (+45d) and `holdback_release` (+55d) from a new
    `projects.completed_at` column
- New columns on `projects`: `completed_at DATE` (+ optional `scheduled_start`,
  `target_completion`).

### 14.4 Reminder channels
| Channel | Mechanism | Use |
|---|---|---|
| Email | n8n Gmail (existing) | record / log |
| Push | FCM (Firebase Cloud Messaging) via `firebase_messaging` | time-based nudges |
| Voice call | Vapi in-app Web SDK (app-initiated) or `POST /call` (server) | daily briefing |
| SMS | native Vapi `sms` tool (caller-bound) | customer texts |

### 14.5 Active vs passive reminders — the rationale
The daily briefing is ONCE A DAY and COARSE; passive (push) reminders are
EVENT-TIME and FINE-GRAINED. Passive is NOT "remind me of everything" — it is
worth it only for a narrow, high-signal set:
1. **Statutory windows (lien/holdback)** — real legal downside; a multi-stage
   poke (7d → 3d → 1d) is genuinely worth it where a once-a-day mention is not.
2. **Lead-time lead-times** (order cabinets 3w before install; book the plumber
   2w before rough-in) — the daily briefing only sees the next 24–48h, so it
   misses these entirely.
3. **Same-day time-specific events** (inspection at 9:30am; sub at 1pm; permit
   office closes 4pm) — a "today" list at 7am ≠ a nudge at 8:45am.

Redundancy note: generic "remind me of every due item" is NOT worth building —
same-day (case 3) and recurring cadence are largely redundant IF Dave checks
the briefing daily. Keep the passive layer to the three categories above; the
briefing (plus the "what's today?" voice query) covers the rest.

### 14.6 Daily briefing — app-initiated, configurable time
**Decision (Dave, 2026-08-27):** the daily briefing call is INITIATED FROM THE
FLUTTER APP, not n8n cron.
- The app schedules a repeating daily local notification
  (`flutter_local_notifications` `zonedSchedule` + `matchDateTimeComponents:
  time`) at a configurable time.
- Tapping it opens the app and starts the in-app Vapi call (`VapiClient.start`).
- `briefing_time` is stored in a settings row; changeable in-app and by voice
  (`set_briefing_time` tool); the app re-syncs on launch (or via a silent FCM
  "settings changed" push).

**iOS constraint:** an app cannot auto-start an audio call in the background —
the notification-tap is the consent step. A fully-automatic "phone rings at 7am"
model is the server-initiated `POST /call` variant (needs a Twilio number bound
to the assistant).

### 14.7 Build order
1. `db/0014` — `schedule_items` + `view_schedule` + `projects.completed_at` +
   settings row (`briefing_time`)
2. Flutter — local-notification scheduler + settings screen (configurable time)
3. Flutter — FCM push + device-token registration (`register_device` tool + a
   `device_tokens` table, db/0015); the FCM data-message path closes the
   voice-configure loop (§14.8)
4. n8n/Vapi — `get_today_schedule` + `set_briefing_time` tools
5. n8n — Deadline Reminder workflow (push + email; statutory/lead-time/same-day)
6. (optional) Vapi outbound call for urgent / server fallback

### 14.8 Voice-configured briefing time — closing the loop
`set_briefing_time` writes `company_profile.briefing_time`, but the phone's local
scheduler would only see the new time on next launch. To make "set my briefing
to 6:30am" reconfigure the phone itself, close the loop:

1. Voice: `set_briefing_time` → n8n → `UPDATE company_profile.briefing_time`.
2. n8n sends an FCM **data message** `{type:"briefing_time_changed",
   briefing_time:"06:30"}` to every token in `device_tokens`.
3. The app receives it in the background and re-schedules the local
   notification (`zonedSchedule`) — no tap required.
4. Vapi confirms the new time.

Why this shape:
- FCM is only the "config changed, re-sync" signal — the local notification
  still fires the alarm (reliable, offline, OS-scheduled), so a dropped or
  delayed push is never a lost alarm.
- `device_tokens` (db/0015): one row per device — `token`, `platform`
  (android/ios), `device_name`, `last_seen_at`; registered by a `register_device`
  tool on app launch (which also returns the current `briefing_time` so the app
  can schedule it immediately).
- No new infra: FCM is already needed for the passive reminders (§14.4).
- Fallback: on every launch/resume the app re-reads `briefing_time` and
  re-schedules if it drifted, so the worst case is "takes effect next open".

