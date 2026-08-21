# Vapi Assistant Configuration

How to build the construction-PM assistant in the Vapi dashboard, wired to the n8n gateway. Source of truth for assistant settings: `doc/SYSTEM_DESIGN.md`.

Target assistant voice + text is **voice-primary, text-secondary** on the **same Vapi call session** (ADR-8). The TTS engine is **ElevenLabs** (ADR-9).

---

## 1. Create the assistant

1. Log in to the [Vapi dashboard](https://dashboard.vapi.ai) → **Assistants** → **Create Assistant**.
2. Save it and note the **Assistant ID** (`YOUR_VAPI_ASSISTANT_ID`) and the **Public Key** (used in the mobile app `config.ts`).
3. Copy the Assistant ID + Public Key into `mobile/src/config.ts`.

---

## 2. Voice (ElevenLabs — ADR-9)

In the assistant's **Voice** section:

- **Provider:** `11labs`
- **Voice provider**: select an ElevenLabs `voiceId` (your chosen voice or a cloned one).
- **Model / stability settings** per taste (stability, similarity boost, style, speaking rate).

> No ElevenLabs API key is needed client-side; Vapi mediates TTS.

---

## 3. Model (LLM)

Under **Model**:

| Setting | Value |
|---|---|
| Provider | Choose your LLM (e.g. OpenAI GPT-4o-mini or Gemini) |
| Model | The specific model you selected (locked in the open question) |
| Temperature | 0.2 (deterministic for structured FM work) |

The system prompt (below) drives behavior.

---

## 4. System Prompt

Paste **Section 6** of `SYSTEM_DESIGN.md`:

```
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

## 5. Tools (function calling → n8n)

Configure each **server/function tool** from **Section 4** of `SYSTEM_DESIGN.md`. Every tool points at the unified n8n gateway webhook:

- **Endpoint:** `POST https://<n8n>/webhook/voice/gateway`
- **Auth:** include the n8n webhook auth header / secret as configured on the gateway.

Define the `function` name, description, and JSON `parameters` per Section 4. Summary of the 8 tools:

| Function name | Description | Required params |
|---|---|---|
| `lookup_or_create_customer` | Find or create a customer | `first_name`, `last_name`, `email` |
| `create_project` | Create a job site for a customer | `customer_id`, `project_name` |
| `create_estimate` | Baseline scope quote (locked once approved) | `project_id`, `scope_description` |
| `create_change_order` | Amendment — **never** for baseline scope | `project_id`, `description` |
| `log_timesheet` | Log worker hours | `project_id`, `worker_name`, `hours_worked` |
| `create_invoice` | Draft an invoice from progress/COs | `project_id`, `invoice_type` |
| `send_customer_invoice` | Email the draft invoice to the client | `project_id`, `invoice_id` |
| `get_project_statement` | Return the financial snapshot | `project_id` |
| `get_estimate_approval_link` | Customer approval link for the baseline estimate | `project_id` |
| `get_change_order_approval_link` | Customer approval link for a change order | `project_id`, `change_order_number` |
| `send_estimate_for_approval` | Email the baseline approval link to the client | `project_id` |
| `send_change_order_for_approval` | Email a change order approval link to the client | `project_id`, `change_order_number` |

> The `toolCallId` the assistant supplies on tool-calls must be echoed in the n8n `results[]` response so Vapi resolves the tool result to the right invocation (ADR-3 idempotency). The `tool_call_id` column in `db/0001_init.sql` makes inserts idempotent.

> **Gateway coverage.** The n8n `voice-gateway.json` wires **all 8 tools** to backends: 7 PostgreSQL executors plus a SendGrid email step for `send_customer_invoice`. Financial calc for invoices happens in SQL (`revised_contract_value * billing_percentage/100`), per ADR-2.

---

## 6. End-call / first-message settings (optional)

- **First message** (optional): *"Hi, I'm your project assistant. You can tell me site hours, change orders, or ask for a project statement."*
- **End-call message** (optional): a wrap-up line.
- **Latency / turn-taking**: set turn eagerness to a comfortable mode (e.g. `normal`) for field use.

---

## 7. Mobile SDK keys

In `mobile/src/config.ts`:

```ts
export const VAPI_PUBLIC_KEY = "<your_vapi_public_key>";
export const VAPI_ASSISTANT_ID = "<your_assistant_id>";
```

The app creates `new Vapi(VAPI_PUBLIC_KEY)`, calls `start(ASSISTANT_ID)` for voice, and `send({type:'add-message', ...})` for same-session text.

---

## Checklist

- [ ] Assistant created; ID + public key in `config.ts`
- [ ] Voice provider = `11labs` (ADR-9)
- [ ] Model chosen + locked
- [ ] System prompt (Section 6) pasted
- [ ] 8 function tools added, all → n8n `/voice/gateway`
- [ ] n8n gateway deployed + webhook URL reachable from Vapi
- [ ] DB migrated (`db/0001_init.sql`); test data loaded (`db/0003_seed.sql`);
      idempotency verified (`db/0002_idempotency_test.sql`)
- [ ] Voice + text same-session tested on device
