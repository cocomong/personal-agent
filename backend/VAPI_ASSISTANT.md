# Vapi Assistant Configuration

How to build the construction-PM assistant in the Vapi dashboard, wired to the n8n gateway. Source of truth for assistant settings: `doc/SYSTEM_DESIGN.md`.

Target assistant voice + text is **voice-primary, text-secondary** on the **same Vapi call session** (ADR-8). The TTS engine is **ElevenLabs** (ADR-9).

---

## 1. Create the assistant

> ✅ **Done.** The assistant **"Ireh Construction PM Assistant"** exists on Vapi
> (id `67e2850c-1028-484d-bf52-d948826b2a7e`), created via the idempotent
> deployer:
>
> ```bash
> python3 backend/create_vapi_assistant.py   # creates or updates, safe to re-run
> ```
>
> It reads `backend/vapi_assistant.json` (model, voice, system prompt, 23
> server tools). The script adapts the JSON to the Vapi API's modern shape:
> the system prompt goes into `model.messages`, and tools are upserted as
> standalone **tool resources** referenced by `model.toolIds`. To change any
> assistant setting, edit the JSON and re-run the script.

Steps (only if creating from scratch in the dashboard):

1. Log in to the [Vapi dashboard](https://dashboard.vapi.ai) → **Assistants** → **Create Assistant**.
2. Save it and note the **Assistant ID** and the **org Public Key** (Settings → Public Key — it is org-level in this API version, not per-assistant).
3. Copy the Assistant ID + Public Key into `mobile-flutter/lib/config.dart`.

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

> **Onboarding (first-run setup).** The current system prompt in
> `backend/vapi_assistant.json` contains a "First-Run Setup (Onboarding)"
> section: call `get_onboarding_status` when setup state is unknown; if
> incomplete, walk the user through company name → PM name → daily preferred
> address → workers (one at a time) and finish with `complete_onboarding`.
> See `doc/ONBOARDING_WIZARD_NOTES.md` (decisions) and SYSTEM_DESIGN.md §15
> (design). **LIVE end-to-end** — assistant synced to 23 tools; the deployer
> (`create_vapi_assistant.py`) reads `VAPI_PRIVATE_KEY` from `~/.hermes/.env`.

---

## 5. Tools (function calling → n8n)

Configure each **server/function tool** from **Section 4** of `SYSTEM_DESIGN.md`. Every tool points at the unified n8n gateway webhook:

- **Endpoint:** `POST https://<n8n>/webhook/voice/gateway`
- **Auth:** include the n8n webhook auth header / secret as configured on the gateway.

Define the `function` name, description, and JSON `parameters` per Section 4. Summary of the 17 tools (12 original + 5 new from the Construction Ops migration):

| Function name | Description | Required params |
|---|---|---|
| `lookup_or_create_customer` | Find or create a customer | `first_name`, `last_name`, `email` |
| `create_project` | Create a job site for a customer | `customer_id`, `project_name` |
| `create_estimate` | Baseline scope quote (locked once approved) | `project_id`, `scope_description` |
| `create_change_order` | Amendment — **never** for baseline scope | `project_id`, `description` |
| `log_timesheet` | Log worker hours (worker matched by name/code/id) | `project_id`, `worker_name`, `hours_worked` |
| `create_invoice` | Draft an invoice from progress/COs | `project_id`, `invoice_type` |
| `send_customer_invoice` | Email the draft invoice to the client | `project_id`, `invoice_id` |
| `get_project_statement` | Return the financial snapshot | `project_id` |
| `get_estimate_approval_link` | Customer approval link for the baseline estimate | `project_id` |
| `get_change_order_approval_link` | Customer approval link for a change order | `project_id`, `change_order_number` |
| `send_estimate_for_approval` | Email the baseline approval link to the client | `project_id` |
| `send_change_order_for_approval` | Email a change order approval link to the client | `project_id`, `change_order_number` |
| `record_payment` | Record a payment against an invoice | `invoice_number`, `amount` |
| `run_payroll` | Compute payroll for a period from timesheets | — |
| `get_payroll_summary` | Return the latest payroll run summary | — |
| `add_worker` | Add/update a worker and rates | `name`, `hourly_rate` |
| `get_dashboard_summary` | Financial dashboard for one/all projects | — |

> The full JSON for the 5 new tools — and the added params on `create_invoice` (`pst_applicable`), `create_change_order` (`reason`), `create_estimate` (`revision`/`status`/`valid_until`), and `log_timesheet` (`overtime_hours`) — is in `backend/vapi_tools_additions.json`.

> The `toolCallId` the assistant supplies on tool-calls must be echoed in the n8n `results[]` response so Vapi resolves the tool result to the right invocation (ADR-3 idempotency). The `tool_call_id` column in `db/0001_init.sql` makes inserts idempotent.

> **Gateway coverage.** The n8n `voice-gateway.json` wires **all 17 tools** to backends: 12 PostgreSQL executors, a `record_payment`→status recompute pair, a `run_payroll`/`get_payroll_summary` pair, and SendGrid/Gmail steps for the email tools. Financial calc for invoices and payroll happens in SQL (ADR-2), reading rates from `company_profile`.

---

## 6. End-call / first-message settings (optional)

- **First message** (optional): *"Hi, I'm your project assistant. You can tell me site hours, change orders, or ask for a project statement."*
- **End-call message** (optional): a wrap-up line.
- **Latency / turn-taking**: set turn eagerness to a comfortable mode (e.g. `normal`) for field use.

---

## 7. Mobile SDK keys

In `mobile-flutter/lib/config.dart`:

```dart
const String vapiPublicKey  = "<org_public_key_from_dashboard_Settings>";
const String vapiAssistantId = "67e2850c-1028-484d-bf52-d948826b2a7e";
```

> The public key is **org-level** — get it from the Vapi dashboard
> (Settings → Public Key). The assistant id is already filled in.

The app creates `VapiClient(VAPI_PUBLIC_KEY)`, calls `start(ASSISTANT_ID)` for voice, and `send({type:'add-message', ...})` for same-session text.

---

## Checklist

- [x] Assistant created ("Ireh Construction PM Assistant", id `67e2850c-1028-484d-bf52-d948826b2a7e`) via `backend/create_vapi_assistant.py`
- [ ] Org public key in `mobile-flutter/lib/config.dart` (dashboard → Settings → Public Key)
- [x] Voice configured — `vapi`/Elliot (ADR-9 specified 11labs; edit `voice` in `backend/vapi_assistant.json` if an ElevenLabs voiceId is preferred)
- [x] Model locked — `openai/gpt-4.1-mini`, temperature 0.2
- [x] System prompt (Section 6) configured (`model.messages` in this API version)
- [x] 23 function tools added (12 original + 5 new + get_schedule/set_briefing_time + get_onboarding_status/complete_onboarding), all → n8n `/voice/gateway`
- [ ] n8n gateway deployed + webhook URL reachable from Vapi
- [ ] DB migrated (`db/0001` → `0011`); test data loaded (`db/0003_seed.sql` + `db/0012_seed_v2.sql`);
      idempotency verified (`db/0002_idempotency_test.sql` + `db/0013_verification.sql`)
- [ ] `company_profile` seeded with Ireh Construction branding + rates
- [ ] Voice + text same-session tested on device
