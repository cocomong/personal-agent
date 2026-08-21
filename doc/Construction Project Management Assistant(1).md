# **Construction Project Management Assistant**

[https://gemini.google.com/app/16811441e351d6d8](https://gemini.google.com/app/16811441e351d6d8)

*User prompt: are you able to track multiple construction projects, 3-4 projects from initial quotation to start of construction to change     requests/quotes, track requests changes, invoice changes per projects, end of projects invoicing and payroll?        something like from a personal project assistant, book keeper to payroll person.*

Response: Yes, I can act as your project assistant, bookkeeper, and payroll helper to track 3–4 construction projects concurrently from initial quotation through change orders, progressive invoicing, and final job closeout.

While I do not natively host a live, persistent cloud database in a standard chat window, I can actively maintain structured logs, process raw notes or hours, calculate job costs, draft formal paperwork, and generate formatted spreadsheets or databases (like Notion, Airtable, or Excel schema) for you to run day-to-day operations seamlessly.

## **How I Handle Each Phase of the Lifecycle**

### **1\. Initial Quotation & Scope Baseline**

> * **Estimate Structuring:** Convert material lists, sub-trade quotes, and estimated labor hours into itemized scope proposals with fixed markup percentages.  
> * **Baseline Budget Setup:** Establish original contract baselines per project broken down by cost code (e.g., Framing, Plumbing, Finishes, Contingency).

### **2\. Change Request & Change Order (CO) Tracking**

> * **CO Documentation:** Turn client or site change requests into formal Change Order documents with detailed line items (materials, additional labor, timeline adjustments).  
> * **Cumulative Contract Log:** Maintain an updated **Change Order Log** per project that tracks:  
  * CO number and description  
  * Approval status (*Draft*, *Pending Client Approval*, *Approved*)  
  * Cost impact and schedule extension days  
  * Cumulative revised contract value

### **3\. Invoicing & Financial Accounting**

> * **Progress Invoicing:** Calculate progress billings based on percentage-of-completion or milestone achievements.  
> * **Change Order Billing:** Ensure approved change orders are added to the correct billing cycle and flagged separately from original scope items.  
> * **Accounts Receivable Ledger:** Track issued invoices, retainage/holdbacks, payments received, and outstanding balances across all 3–4 active projects.

### **4\. Payroll & Labor Allocation**

> * **Timesheet Processing:** Parse weekly raw timesheets or shift logs for workers and sub-trades.  
> * **Job Costing Breakdown:** Map hours worked directly to specific project IDs and cost codes to ensure payroll costs are accurately allocated to the right job budget.  
> * **Payroll Summaries:** Calculate gross pay, hourly rate splits, overtime hours, and trade-specific labor expenditures ready for payout or entry into your accounting software.

## **Operating Framework Options**

Depending on how you prefer to work, we can manage this in one of three ways:

| Workflow Style | How It Works | Best For |
| :---- | :---- | :---- |
| **Interactive Chat Workspace** | You paste daily shift notes, worker hours, material receipts, or change requests here. I update and format your project logs, draft your invoices/COs, and track running totals in real time. | Low setup time; fast conversational updates. |
| **Centralized Master Spreadsheet** | I design a custom multi-tab Google Sheet or Excel workbook with built-in formulas for job-costing, payroll calculation, change order tracking, and invoice schedules. | Hands-on data management with complete visibility. |
| **Automated System Integration** | I help you build schema and automation workflows (e.g., in Notion, Airtable, or n8n) that automatically pull email change requests, generate invoices, and route timesheets. | Scaling beyond 4 projects with minimal manual data entry. |

---

*User prompt: if I want to add a voice AI assistant type of interface to this, how the architecture would look like and what tools you will be needing.*

Response: To add a voice AI assistant to your construction project management workflow, you need an architecture that connects real-time audio processing to an automation engine and a centralized database.

## **1\. System Architecture Overview**

 `[ User Input ] (Site Supervisor / Project Manager)`  
       `│`  
       `├── Web App / Mobile App (WebRTC)`  
       `└── Phone Dial-in (Twilio / Telephony)`  
       `│`  
       `▼`  
 `┌─────────────────────────────────────────┐`  
 `│       1. Voice Orchestration Layer      │`  
 `│  • Speech-to-Text (STT)                 │`  
 `│  • Text-to-Speech (TTS)                 │`  
 `│  • Real-Time Turn-Taking & Latency      │`  
 `└────────────────────┬────────────────────┘`  
                      `│ Tool Call / Webhook`  
                      `▼`  
 `┌─────────────────────────────────────────┐`  
 `│    2. Workflow & Middleware Layer      │`  
 `│  • Logic execution & JSON validation    │`  
 `│  • Routing to specific sub-systems      │`  
 `└──────┬──────────────────────────┬───────┘`  
        `│                          │`  
        `▼                          ▼`  
 `┌──────────────┐          ┌────────────────┐`  
 `│ 3. LLM Core  │          │ 4. Data Layer  │`  
 `│  • Entity    │          │  • Projects    │`  
 `│    Extraction│          │  • Change Logs │`  
 `│  • Reasoning │          │  • Payroll DB  │`  
 `└──────────────┘          └────────────────┘`

When you speak to the assistant on site (e.g., *"Log 6 hours for Mark on the Fairview job under framing"*), the voice engine transcribes the speech, identifies the intent, triggers a function call to your middleware, and writes the structured record directly to your database.

## **2\. Component & Tool Breakdown**

### **Layer 1: Voice Orchestration Engine**

Handles two-way streaming, noise reduction, speech recognition, and natural voice response.

> * **Primary Platform Options:**  
  * **Vapi** or **Retell AI**: Purpose-built platforms designed for agentic voice calls. They allow you to define system prompts and custom tools (function calls) via HTTP endpoints.  
  * **LiveKit Agents**: For fully custom, low-latency WebRTC streaming if building directly into a mobile application.  
> * **Under the Hood Providers (usually integrated directly via Vapi/Retell):**  
  * **Speech-to-Text (STT):** Deepgram Nova-2 or Whisper (fast transcription tuned for speech accents and ambient site noise).  
  * **Text-to-Speech (TTS):** ElevenLabs or Cartesia (natural human-like voice synthesis).

### **Layer 2: Middleware & Automation Workflow**

Acts as the central router between the voice agent and your project accounting records.

> * **Primary Tools:**  
  * **n8n**: Ideal for orchestrating webhook requests coming from the voice platform. It parses incoming tool calls, verifies values, handles data transformation, and routes updates to databases or accounting software.  
  * **Custom Node.js / Express or Fastify API**: A tailored backend API if you require custom business logic and strict local compliance/security.

### **Layer 3: Reasoning & LLM Engine**

Extracts entities (dates, names, hours, dollar amounts, project codes) and formats responses.

> * **Primary Models:**  
  * **Google Gemini 2.5 Flash** or **OpenAI GPT-4o-mini**: Low-latency, cost-effective models for function calling and fast structured extraction.

### **Layer 4: Data & Business Systems**

Where project baseline numbers, change order statuses, invoices, and timesheets live.

> * **Database / Ledger Options:**  
  * **Relational DB:** Supabase (PostgreSQL) or Firebase for persistent relational project tracking.  
  * **Low-Code Databases:** Airtable or Google Sheets for quick visibility and manual overrides.  
> * **Accounting Integrations:**  
  * Direct API connections to **QuickBooks Online**, **Xero**, or **Gusto** via n8n for automated invoicing and payroll sync.

## **3\. Real-World Execution Flow (Example: Voice Change Order)**

> 1. **User Request:** You press a button on site and say: *"Add a change order for Job 102\. Client wants 4 extra recessed lights in the kitchen. Estimate $600 for parts and 3 hours labor."*  
> 2. **Function Trigger:** Vapi detects the create\_change\_order function tool call with arguments:  
>    `{`  
>      `"project_id": "102",`  
>      `"title": "Extra kitchen recessed lights",`  
>      `"material_cost": 600,`  
>      `"labor_hours": 3,`  
>      `"status": "Pending Approval"`  
>    `}`

> 3. **Webhook Processing:** Vapi sends this payload to an n8n webhook.  
> 4. **Database Write:** n8n updates the project log in Supabase/Airtable and generates a draft PDF invoice/quote.  
> 5. **Voice Confirmation:** Vapi speaks back: *"Draft Change Order \#4 for Job 102 created for $600 materials plus 3 hours labor. Updated pending total is $1,050. Shall I mark it sent to the client?"*

## **Recommended Stack for 3–4 Projects**

> * **Voice Platform:** Vapi (web dashboard or phone dialer setup)  
> * **Workflow Engine:** n8n (self-hosted or cloud)  
> * **LLM Engine:** Gemini Flash or GPT-4o-mini  
> * **Database & Frontend:** Supabase or Airtable \+ web/mobile app interface

**Sources**

> 1. [Awaisali36/Outbound-Real-State-Voice-AI-Agent-: Automated voice AI calling system using VAPI, n8n, and Airtable. Calls leads automatically, conducts natural conversations, and books appointments via Calendly. Multi-channel follow-up with email and WhatsApp. · GitHub](https://github.com/Awaisali36/Outbound-Real-State-Voice-AI-Agent-)  
> 2. [Automate order confirmations with VAPI Voice AI & timezone intelligence \- n8n](https://n8n.io/workflows/7380-automate-order-confirmations-with-vapi-voice-ai-and-timezone-intelligence/)

---

*User prompt: i am still exploring different to accomplish this. what about assistant like google assistant or apple siri, can they be set up to do something like this.*

Response: Yes, consumer assistants like Apple Siri and Google Assistant can be configured to manage this workflow, but they function as **command-and-response automation triggers** rather than fully conversational AI agents.

Instead of having a fluid, back-and-forth dialogue on site, you trigger a specific voice action (e.g., *"Hey Siri, Log Site Hours"*), the assistant prompts you for inputs, sends that data to your backend system, and reads back the confirmation.

## **1\. How to Set Up Apple Siri (iOS Shortcuts \+ Webhooks)**

Siri is currently the easiest consumer voice interface to adapt for custom business logic through the **iOS Shortcuts** app.

 `[ Voice Command ] ("Hey Siri, Add Change Order")`  
        `│`  
        `▼`  
 `[ iOS Shortcuts App ] (Captures voice dictation & parameters)`  
        `│`  
        `▼`  
 `[ HTTP POST / Webhook ] ──► [ n8n / Make.com / LLM ]`  
        `│                                │`  
        `▼                                ▼`  
 `[ Siri Dictates Result ] ◄── [ Writes to Airtable/DB ]`

### **Setup Steps:**

> 1. **Create an iOS Shortcut:** Name it something natural, like "Log Change Order" or "Submit Timesheet".  
> 2. **Add Input Actions:** Set the Shortcut to ask:  
   * *"Which project?"*  
   * *"What is the description?"*  
   * *"What is the cost or labor hours?"*  
> 3. **Send to Middleware (Webhook):** Add a Get Contents of URL action in Shortcuts that posts this JSON bundle to an **n8n**, **Make.com**, or **Airtable API** endpoint.  
> 4. **Process & Respond:** Your backend processes the entry, updates your database, and sends back a summary string (e.g., *"Change Order 04 logged for Fairview project at $850"*), which Siri reads out loud.  
> * **Pros:** 100% free, works natively on iPhone, Apple Watch, and CarPlay hands-free in your truck.  
> * **Cons:** Linear and rigid. If Siri mishears a project name, you generally have to re-run the entire shortcut rather than correcting it mid-conversation.

## **2\. How to Set Up Google Assistant / Gemini**

Google offers two main avenues depending on whether your database lives in Google Workspace or a third-party app.

### **Option A: Google Workspace \+ Gemini Mobile**

If your project tracking lives inside **Google Sheets** and **Google Drive**:

> * You can use Gemini on Android/iOS with Google Workspace extensions enabled.  
> * **Voice Action:** You speak directly to Gemini: *"Add a line item to my Fairview Construction Google Sheet under Change Orders: $450 for drywall repair."*  
> * **Pros:** Zero coding or webhooks required.  
> * **Cons:** Relies on Gemini's native file parsing, which can sometimes misinterpret table structures if the sheet layout is overly complex.

### **Option B: Google Assistant Routines \+ Webhooks (via Tasker / Make)**

> * **Setup:** Create a Custom Routine in Google Assistant triggered by a phrase like *"Log site hours"*.  
> * **Routing:** Use an integration tool like **Tasker** (Android) or **Make.com** to capture the voice text payload and send it to your central project database.  
> * **Pros:** Native trigger on Android devices and Google Home speakers.  
> * **Cons:** Harder to configure multi-variable prompts than iOS Shortcuts.

## **3\. Comparison: Consumer Assistants vs. Dedicated Voice AI**

| Feature | Consumer Voice (Siri / Google Assistant) | Dedicated Voice AI (Vapi / Retell / LiveKit) |
| :---- | :---- | :---- |
| **Cost** | **Free** (included on your device) | **\~$0.05 – $0.15 per minute** |
| **Interaction Model** | Command-and-response (structured Q\&A) | Fluid, human-like back-and-forth dialogue |
| **Interruption Handling** | None (must wait for prompt to finish) | Full support (can interrupt mid-sentence) |
| **Clarification Ability** | Poor (starts over if it misses data) | High (asks: *"Did you mean $500 total or $500 plus labor?"*) |
| **Hardware** | iPhone, Apple Watch, Android Phone | Any web browser, phone call, or custom mobile app |
| **Setup Effort** | Low-Code (1–2 hours using iOS Shortcuts) | Mid-Code (requires API keys, webhook endpoints) |

## **Recommended Strategy**

If you want to test a voice workflow **without spending money or building complex software**, start with **iOS Shortcuts \+ Google Sheets or Airtable**:

> 1. Build your central database in **Airtable** or **Google Sheets**.  
> 2. Create two simple iOS Shortcuts on your phone: Log Hours and New Change Order.  
> 3. Test using Siri in the field for 2 weeks.

If you find that Siri's strict Q\&A structure is too clunky while driving or working on site, that is the exact point to upgrade to a dedicated tool like Vapi for full conversational capability.

---

*User prompt: what about google agent developer kit?*

Response: Google’s **Agent Development Kit (ADK)** is an open-source, code-first framework designed for building, testing, and deploying custom AI agents and multi-agent systems.

Where consumer tools (like Siri) offer basic command execution and platforms like Vapi/n8n offer low-code orchestration, ADK gives you full programmatic control over agent logic, multi-agent collaboration, and real-time streaming.

## **How ADK Fits the Construction Project Assistant**

If you choose to build your system using ADK (available in Python, TypeScript, Go, and Kotlin/Android), it addresses the complexity of construction tracking through several key features:

### **1\. Multi-Agent Delegation**

Rather than relying on one mega-prompt to handle change orders, invoicing, and payroll simultaneously, ADK natively supports **hierarchical multi-agent architectures**:

> * **Root Orchestrator Agent:** Listens to the supervisor's voice/text input and routes the request to the correct specialist.  
> * **Change Order Agent:** Specialized in parsing scope changes, line-item material costs, markup calculations, and generating draft change orders.  
> * **Payroll & Timesheet Agent:** Focuses on worker rate codes, site-specific hours, and trade allocations.  
> * **Invoicing Agent:** Manages percentage-of-completion billing, holdbacks/retainage, and AR ledgers.

### **2\. Built-in Multimodal Voice & Streaming**

ADK includes native bidirectional audio streaming. This means you do not need third-party wrappers like Vapi or Retell to handle voice transport—ADK manages low-latency, human-like voice conversations directly with Gemini models.

### **3\. Mobile & On-Device Support (ADK for Android)**

With **ADK for Android**, agents can run locally on site-use tablets or phones using on-device models like Gemini Nano via ML Kit. This allows site supervisors to dictate timesheets or change notes even when working in remote areas with no cellular signal, syncing back to the main cloud database once reconnected.

## **Architectural Comparison for Your Project**

| Approach | Setup Effort | Flexibility & Control | Voice Capabilities | Best Used For |
| :---- | :---- | :---- | :---- | :---- |
| **Siri / Shortcuts** | Very Low | Low (rigid step-by-step Q\&A) | Basic voice dictation | Personal quick-logging without custom software |
| **Vapi \+ n8n \+ Airtable** | Medium | Medium (assembled via APIs) | Excellent real-time voice | Rapid prototyping with low-code tools |
| **Google ADK \+ Cloud Run / DB** | High (Code-first) | **Maximum** (full custom logic) | Native real-time streaming & multimodal | Building a custom, enterprise-grade app for site teams |

## **Example ADK Multi-Agent Structure (Python)**

In ADK, defining a multi-agent hierarchy for your projects requires only a few structured agent definitions:

`from google.adk import Agent, Workflow`

`# Specialized Sub-Agents`  
`timesheet_agent = Agent(`  
    `name="timesheet_agent",`  
    `model="gemini-2.5-flash",`  
    `instruction="Parse site hours, worker names, trade categories, and job IDs."`  
`)`

`change_order_agent = Agent(`  
    `name="change_order_agent",`  
    `model="gemini-2.5-flash",`  
    `instruction="Extract description, scope changes, material estimates, and labor hours."`  
`)`

`# Root Orchestrator`  
`root_orchestrator = Workflow(`  
    `name="construction_pm_assistant",`  
    `instruction="Identify whether the site input relates to labor/timesheets or change orders, and delegate accordingly.",`  
    `edges=[("START", timesheet_agent), ("START", change_order_agent)]`  
`)`

If you plan to package this into a dedicated web or mobile application that you or your team use on job sites, **ADK provides the cleanest software foundation**. If you prefer not to write custom backend code, the Vapi \+ n8n approach remains the faster route to operational deployment.

**Sources**

> 1. [Agent Development Kit: Making it easy to build multi-agent applications](https://developers.googleblog.com/agent-development-kit-easy-to-build-multi-agent-applications/)  
> 2. [Agent Development Kit | Gemini Enterprise Agent Platform | Google Cloud Documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk)  
> 3. [Build ADK agents for Android | AI](https://developer.android.com/ai/adk)  
> 4. [GitHub \- google/adk-python: An open-source, code-first Python toolkit for building, evaluating, and deploying sophisticated AI agents with flexibility and control.](https://github.com/google/adk-python)

---

*User prompt: I am leaning toward using vapi instead for now for I have been working with vapi for awhile*

Response: Leveraging Vapi gives you real-time conversational voice handling, native tool calling, and full control over latency. Combined with **n8n** for workflow orchestration and **Airtable or Supabase** for project records, this stack requires three primary setup components: the **Vapi Tool Definitions**, the **n8n Response Protocol**, and the **System Prompt**.

## **1\. Vapi Tool Definitions (Function Calling)**

In your Vapi Assistant dashboard, configure custom Server/Function tools pointing to your n8n webhook URL.

### **Tool 1: log\_timesheet**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "log_timesheet",`  
    `"description": "Logs daily worker hours, trade category, and rate code against a specific project ID.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": { "type": "string", "description": "Name or ID of the job (e.g., Fairview, Job 102)" },`  
        `"worker_name": { "type": "string", "description": "Full name of the worker" },`  
        `"trade": { "type": "string", "description": "Trade category (e.g., Framing, Electrical, Drywall)" },`  
        `"hours": { "type": "number", "description": "Number of hours worked" },`  
        `"overtime_hours": { "type": "number", "description": "Overtime hours worked, if any" }`  
      `},`  
      `"required": ["project_id", "worker_name", "hours"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-timesheet"`  
  `}`  
`}`

### **Tool 2: create\_change\_order**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "create_change_order",`  
    `"description": "Drafts a new change order or modification request for a project.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": { "type": "string", "description": "Target project identifier" },`  
        `"description": { "type": "string", "description": "Scope update description" },`  
        `"material_cost": { "type": "number", "description": "Estimated material cost in dollars" },`  
        `"labor_hours": { "type": "number", "description": "Estimated labor hours required" }`  
      `},`  
      `"required": ["project_id", "description"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-change-order"`  
  `}`  
`}`

## **2\. n8n Tool Response Protocol**

When Vapi triggers an n8n webhook during a call, n8n receives the toolCallId inside message.toolCalls\[0\].id or artifact.

To have Vapi speak the result back seamlessly, your n8n workflow must end with a **Respond to Webhook** node returning this JSON structure:

`{`  
  `"results": [`  
    `{`  
      `"toolCallId": "call_123456789",`  
      `"result": "Change Order #04 created for Fairview Project with $600 materials and 3 hours labor. Pending client approval."`  
    `}`  
  `]`  
`}`

### **n8n Execution Flow:**

> 1. **Webhook Node (POST):** Receives tool payload from Vapi.  
> 2. **Data Transformation (Edit Fields):** Formats values into database-ready columns.  
> 3. **Database Node (Airtable/Supabase):** Appends timesheet row or inserts Change Order record.  
> 4. **Calculations Node:** Sums current project budget \+ new change order cost.  
> 5. **Respond to Webhook Node:** Sends the concise success message back to Vapi to read aloud on site.

## **3\. Vapi System Prompt for Site Use**

To keep latency low and eliminate unnecessary back-and-forth speech on noise-heavy construction sites, structure your Vapi system prompt as follows:

`# Role`  
`You are a site-management voice assistant for a construction manager running 3-4 active projects (Fairview, Oakridge, Kitsilano, Main St).`

`# Communication Rules`  
`- Speak in ultra-concise, natural phrases (under 15 words per turn).`  
`- Never read back entire lists unless asked.`  
`- Confirm critical project names and dollar amounts before executing tool calls.`  
`- If a project name is ambiguous, ask for clarification immediately.`

`# Tool Usage`  
`- When logging hours or change orders, collect required fields first.`  
`- If hours are provided without a worker name, ask: "Who worked those hours?"`  
`- Once tool execution completes, summarize the outcome in one sentence.`

**Sources**

> 1. [AI-Driven Support Bot with Vapi, Twilio & n8n: Step-by-Step \- Lets Viz](https://lets-viz.com/blogs/building-an-ai-driven-customer-support-bot-with-vapi-twilio-n8n)  
> 2. [onyebuchidaniel60/Vapi-Inbound-Agent-Tools: A toolkit of n8n workflows for Vapi.ai voice agents. Includes a real-time Google Calendar booking tool and an automated post-call lead qualifier synced to Google Sheets, both powered by Google Gemini logic. · GitHub](https://github.com/onyebuchidaniel60/Vapi-Inbound-Agent-Tools)  
> 3. [Voice-driven AI assistant using VAPI and GPT-4.1-mini with memory | n8n workflow template](https://n8n.io/workflows/8866-voice-driven-ai-assistant-using-vapi-and-gpt-41-mini-with-memory/)

---

*User prompt: I am prototyping using google sheet first, and you missed project creation for new project site. create estimate, create invoice based on estimate and send customer invoice*

Response: Adding project initialization, estimates, invoice creation, and customer delivery completes the entire lifecycle from initial lead to final payment inside your Google Sheets prototype.

Here is how to structure your Google Sheet, configure the new Vapi tool calls, and wire up the n8n execution pipeline.

## **1\. Google Sheet Prototype Architecture**

Set up your workbook with 5 core tabs so n8n can query and write records cleanly:

| Tab Name | Key Columns |
| :---- | :---- |
| **Projects** | Project ID, Project Name, Client Name, Client Email, Site Address, Status, Original Contract Value, Revised Contract Value, Total Billed, Balance Due |
| **Estimates** | Estimate ID, Project ID, Scope Description, Labor Estimate, Material Estimate, Total Estimate, Status (*Draft / Sent / Approved*) |
| **Change\_Orders** | CO ID, Project ID, Description, Material Cost, Labor Cost, Total Cost, Status |
| **Invoices** | Invoice ID, Project ID, Estimate ID, Invoice Type (*Deposit / Progress / Final*), Amount, Status (*Draft / Sent / Paid*) |
| **Timesheets** | Entry ID, Project ID, Worker Name, Trade, Hours, Date |

## **2\. New Vapi Tool Definitions**

Paste these function definitions into your Vapi Assistant dashboard alongside your existing log\_timesheet and create\_change\_order tools.

### **Tool 1: create\_project**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "create_project",`  
    `"description": "Creates a new project site record in Google Sheets with client contact details.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_name": { "type": "string", "description": "Name or shorthand for the site (e.g., Kitsilano Reno, Main St)" },`  
        `"client_name": { "type": "string", "description": "Full name of the client" },`  
        `"client_email": { "type": "string", "description": "Client email address for quotes and invoicing" },`  
        `"site_address": { "type": "string", "description": "Street address of the job site" }`  
      `},`  
      `"required": ["project_name", "client_name"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-create-project"`  
  `}`  
`}`

### **Tool 2: create\_estimate**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "create_estimate",`  
    `"description": "Creates an initial job estimate or proposal breakdown for a project.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": { "type": "string", "description": "Target project name or ID" },`  
        `"scope_summary": { "type": "string", "description": "Summary of work covered under this quote" },`  
        `"labor_amount": { "type": "number", "description": "Estimated total labor dollar value" },`  
        `"material_amount": { "type": "number", "description": "Estimated total material dollar value" }`  
      `},`  
      `"required": ["project_id", "scope_summary"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-create-estimate"`  
  `}`  
`}`

### **Tool 3: create\_invoice**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "create_invoice",`  
    `"description": "Generates a draft invoice from an estimate or contract balance.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": { "type": "string", "description": "Target project name or ID" },`  
        `"invoice_type": { "type": "string", "enum": ["Deposit", "Progress", "Final"], "description": "Billing milestone type" },`  
        `"billing_percentage": { "type": "number", "description": "Percentage of contract/estimate to bill (e.g., 20 for 20% deposit)" },`  
        `"flat_amount": { "type": "number", "description": "Specific dollar amount if not billing by percentage" }`  
      `},`  
      `"required": ["project_id", "invoice_type"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-create-invoice"`  
  `}`  
`}`

### **Tool 4: send\_customer\_invoice**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "send_customer_invoice",`  
    `"description": "Triggers email delivery of a draft invoice or estimate to the client on file.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": { "type": "string", "description": "Target project name or ID" },`  
        `"invoice_id": { "type": "string", "description": "Specific invoice number to send (e.g., INV-1002)" }`  
      `},`  
      `"required": ["project_id"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-send-invoice"`  
  `}`  
`}`

## **3\. n8n Automation Workflows**

When these voice tools fire, n8n handles the heavy lifting between Google Sheets, document rendering, and email dispatch:

 `[ Vapi Voice Tool Call ]`  
            `│`  
            `▼`  
   `[ n8n Webhook Node ]`  
            `│`  
            `├──► 1. Lookup Project & Client Email in Google Sheets`  
            `├──► 2. Create Row in 'Estimates' / 'Invoices' Tab`  
            `├──► 3. Generate HTML-to-PDF Invoice Document`  
            `└──► 4. Send Gmail / SMTP Email with PDF Attachment`  
            `│`  
            `▼`  
   `[ Respond to Webhook ] ──► "Invoice INV-1002 sent to client@email.com for $2,500."`

### **n8n Execution Steps per Action:**

> 1. **Create Project:** Appends row to Projects tab. Generates unique Project ID (e.g., PRJ-101). Returns confirmation to Vapi.  
> 2. **Create Estimate:** Queries Projects tab to match Project ID. Appends line item to Estimates tab, calculates total (labor \+ materials), and updates Original Contract Value on Projects tab.  
> 3. **Create Invoice:** Pulls active estimate/contract value from Projects tab. Calculates billing amount based on percentage (e.g., 20% deposit) or flat rate. Appends record to Invoices tab with status Draft.  
> 4. **Send Invoice:** Retrieves client email from Projects tab and invoice summary from Invoices tab. Uses an **n8n HTML Node** or **Google Docs Template** to render a styled PDF invoice, attaches it to a **Gmail / SMTP Node**, emails the client, and updates status in Invoices tab to Sent.

## **4\. System Prompt Updates for Full Lifecycle Management**

Update your Vapi System Prompt so the assistant seamlessly handles creation through delivery:

`# Extended Capabilities`  
`You handle full project lifecycles: Project Setup -> Estimation -> Change Orders -> Progress Invoicing -> Customer Email Delivery -> Payroll.`

`# Voice Workflow Examples:`  
`1. "Set up a new project for John Doe called Kitsilano Reno, email john@example.com."`  
   ``-> Call `create_project`.``

`2. "Create an estimate for Kitsilano Reno: $5,000 labor and $3,200 materials for kitchen framing."`  
   ``-> Call `create_estimate`.``

`3. "Create a 20% deposit invoice for Kitsilano Reno based on the approved estimate."`  
   ``-> Call `create_invoice`.``

`4. "Send that deposit invoice to the client for Kitsilano Reno."`  
   `-> Confirm details first: "Send Invoice INV-1001 for $1,640 to john@example.com?"`  
   ``-> Upon user confirmation ("Yes"), call `send_customer_invoice`.``

---

*User prompt: should there be a customer sheet for customer info and should any change order part be the line item inside an project's estimate?*

Response: Yes to both questions, with one important structural distinction regarding how Change Orders are handled.

## **1\. Should you have a dedicated Customers sheet?**

**Yes, absolutely.** Creating a separate Customers sheet is best practice for relational databases and workflow automation.

### **Why separate Customers from Projects?**

> * **Repeat Clients:** A client (e.g., a real estate investor or homeowner) might hire you for a kitchen remodel this year and a deck next year. Storing customer info inside the Projects sheet forces you to duplicate their phone, email, and billing address.  
> * **Single Source of Truth:** If a client updates their phone number or billing email, you update it once in the Customers sheet, and all associated past, present, and future projects/invoices instantly reference the right details.  
> * **Vapi / Voice AI Efficiency:** When you say *"Create a new project for John Doe"*, n8n can first query the Customers sheet:  
  * If John Doe exists → link his Customer\_ID to the new project.  
  * If he doesn't exist → create a new customer row first, then create the project.

## **2\. Should Change Orders be line items inside a project's Estimate?**

**No, Change Orders should NOT overwrite or be added directly into the original Estimate.** However, they **should** be line items on your **Invoices**.

### **Why keep Estimates and Change Orders separate?**

> 1. **Preserving the Baseline (Legal & Financial Audit):** In construction, the **Original Estimate** forms the base contract signed by the client. Once signed, that initial estimate should be **locked**. If you add change orders directly into the original estimate sheet, you lose the ability to prove what was in the initial agreement versus what was added later.  
> 2. **Scope Creep Visibility:** Clients frequently ask: *"Why is my $50,000 renovation now costing $65,000?"* Keeping Change Orders as separate, approved amendments allows you to show:  
   * **Base Contract:** $50,000  
   * **CO \#1 (Recessed Lights):** \+$1,500  
   * **CO \#2 (Tile Upgrade):** \+$3,500  
   * **CO \#3 (Subfloor Repair):** \+$10,000  
   * **Total Revised Contract:** $65,000  
> 3. **Approval Tracking:** An estimate line item is either part of the base job or not. A Change Order has its own lifecycle (*Pending Client Signature*, *Approved*, *Rejected*, *Billed*).

## **3\. Recommended Multi-Tab Google Sheet Schema**

Here is the ideal structure for your prototype. It keeps records normalized so n8n can easily query and write data without confusion:

 `[ Customers ] ──1:N──► [ Projects ] ──1:N──► [ Estimates (Base Contract) ]`  
                             `│`  
                             `├──1:N──► [ Change_Orders (Amendments) ]`  
                             `│`  
                             `├──1:N──► [ Invoices (Billed Items) ]`  
                             `│`  
                             `└──1:N──► [ Timesheets (Labor Costs) ]`

### **Tab Breakdown**

| Tab Name | Role & Key Columns |
| :---- | :---- |
| **Customers** | **Stores client contact & billing details.** Customer\_ID (PK), First\_Name, Last\_Name, Company, Email, Phone, Billing\_Address |
| **Projects** | **High-level job summary & running balances.** Project\_ID (PK), Customer\_ID (FK), Project\_Name, Site\_Address, Status, Original\_Contract\_Total, Approved\_CO\_Total, Total\_Contract\_Value, Total\_Billed, Balance\_Due |
| **Estimates** | **Locked base scope quote.** Estimate\_ID (PK), Project\_ID (FK), Scope\_Description, Labor\_Estimate, Material\_Estimate, Total\_Estimate, Status (*Draft/Approved*) |
| **Change\_Orders** | **Contract modifications (Separate from Estimate).** CO\_ID (PK), Project\_ID (FK), CO\_Number (\#1, \#2), Description, Labor\_Cost, Material\_Cost, Total\_CO\_Amount, Status (*Pending/Approved/Rejected*) |
| **Invoices** | **Billings referencing Estimate or CO items.** Invoice\_ID (PK), Project\_ID (FK), Invoice\_Type (*Deposit / Progress / Change Order / Final*), Line\_Items\_Summary, Amount, Status (*Draft/Sent/Paid*) |
| **Timesheets** | **Worker hours logged against projects.** Entry\_ID (PK), Project\_ID (FK), Worker\_Name, Trade, Hours, Date |

## **How Invoicing Pulls it All Together**

When it comes time to generate a customer **Invoice**:

> 1. n8n calculates the total billing amount by combining:  
   * **Base Contract Progress** (e.g., 50% of Estimates.Total\_Estimate)  
   * **Approved Change Orders** (e.g., 100% of Change\_Orders.Total\_CO\_Amount where Status \= Approved)  
> 2. The generated invoice will display line items clearly separated:  
   * *Line 1:* Progress Billing \#2 \- Main Framing Scope (50%): $10,000  
   * *Line 2:* Change Order \#01 \- Extra Kitchen Recessed Lights: $1,500  
   * **Total Due:** $11,500

This gives you legal protection, clear client visibility, and a clean backend structure for n8n to query over voice.

---

*User prompt: yes also this has been expanded beyond a google sheet can do quickly, use a database instead?*

Response: Moving from Google Sheets to a relational database like **Supabase (PostgreSQL)** or **Airtable** is the right decision.

Google Sheets becomes fragile when handling relational multi-table queries (e.g., linking a customer to multiple projects, each with locked estimates, separate change orders, and itemized progress invoices). A relational database enforces data integrity (foreign keys), allows fast multi-table joins in n8n, and scales effortlessly.

Here is the complete relational architecture, database schema, updated Vapi tool definitions, and revised system prompt.

## **1\. Database Schema (PostgreSQL / Supabase)**

Using PostgreSQL gives you strong foreign key constraints and auto-calculating views for project totals.

`-- 1. CUSTOMERS TABLE`  
`CREATE TABLE customers (`  
    `id UUID PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `first_name VARCHAR(100) NOT NULL,`  
    `last_name VARCHAR(100) NOT NULL,`  
    `company VARCHAR(150),`  
    `email VARCHAR(255) UNIQUE NOT NULL,`  
    `phone VARCHAR(50),`  
    `created_at TIMESTAMP WITH TIMEZONE DEFAULT NOW()`  
`);`

`-- 2. PROJECTS TABLE`  
`CREATE TABLE projects (`  
    `id UUID PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,`  
    `project_name VARCHAR(150) NOT NULL,`  
    `site_address TEXT,`  
    `status VARCHAR(50) DEFAULT 'Quoting', -- Quoting, Active, Completed, On Hold`  
    `created_at TIMESTAMP WITH TIMEZONE DEFAULT NOW()`  
`);`

`-- 3. ESTIMATES TABLE (Base Contract - Locked once approved)`  
`CREATE TABLE estimates (`  
    `id UUID PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `project_id UUID REFERENCES projects(id) ON DELETE CASCADE,`  
    `scope_description TEXT NOT NULL,`  
    `labor_estimate DECIMAL(10,2) DEFAULT 0.00,`  
    `material_estimate DECIMAL(10,2) DEFAULT 0.00,`  
    `total_estimate DECIMAL(10,2) GENERATED ALWAYS AS (labor_estimate + material_estimate) STORED,`  
    `status VARCHAR(50) DEFAULT 'Draft', -- Draft, Sent, Approved, Rejected`  
    `created_at TIMESTAMP WITH TIMEZONE DEFAULT NOW()`  
`);`

`-- 4. CHANGE ORDERS TABLE (Scope Modifications)`  
`CREATE TABLE change_orders (`  
    `id UUID PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `project_id UUID REFERENCES projects(id) ON DELETE CASCADE,`  
    `co_number INT NOT NULL,`  
    `description TEXT NOT NULL,`  
    `labor_cost DECIMAL(10,2) DEFAULT 0.00,`  
    `material_cost DECIMAL(10,2) DEFAULT 0.00,`  
    `total_co_amount DECIMAL(10,2) GENERATED ALWAYS AS (labor_cost + material_cost) STORED,`  
    `status VARCHAR(50) DEFAULT 'Pending', -- Pending, Approved, Rejected`  
    `created_at TIMESTAMP WITH TIMEZONE DEFAULT NOW()`  
`);`

`-- 5. INVOICES TABLE`  
`CREATE TABLE invoices (`  
    `id UUID PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `project_id UUID REFERENCES projects(id) ON DELETE CASCADE,`  
    `invoice_number VARCHAR(50) UNIQUE NOT NULL,`  
    `invoice_type VARCHAR(50) NOT NULL, -- Deposit, Progress, Change Order, Final`  
    `status VARCHAR(50) DEFAULT 'Draft', -- Draft, Sent, Paid`  
    `issued_date DATE DEFAULT CURRENT_DATE,`  
    `total_amount DECIMAL(10,2) NOT NULL`  
`);`

`-- 6. INVOICE LINE ITEMS TABLE (Links Invoices to Estimates or Change Orders)`  
`CREATE TABLE invoice_line_items (`  
    `id UUID PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `invoice_id UUID REFERENCES invoices(id) ON DELETE CASCADE,`  
    `source_type VARCHAR(50) NOT NULL, -- 'estimate_progress' or 'change_order'`  
    `source_id UUID, -- References estimate_id or change_order_id`  
    `description TEXT NOT NULL,`  
    `amount DECIMAL(10,2) NOT NULL`  
`);`

`-- 7. TIMESHEETS TABLE (Payroll & Job Costing)`  
`CREATE TABLE timesheets (`  
    `id UUID PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `project_id UUID REFERENCES projects(id) ON DELETE CASCADE,`  
    `worker_name VARCHAR(100) NOT NULL,`  
    `trade VARCHAR(100),`  
    `hours_worked DECIMAL(5,2) NOT NULL,`  
    `work_date DATE DEFAULT CURRENT_DATE`  
`);`

## **2\. Updated Vapi Tool Definitions**

These tools give Vapi the ability to search/create customers, create projects, lock estimates, draft separate change orders, and build itemized invoices.

### **Tool 1: lookup\_or\_create\_customer**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "lookup_or_create_customer",`  
    `"description": "Checks if a customer exists by email or full name; creates a new customer if not found.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"first_name": { "type": "string", "description": "Customer's first name" },`  
        `"last_name": { "type": "string", "description": "Customer's last name" },`  
        `"email": { "type": "string", "description": "Customer email address" },`  
        `"phone": { "type": "string", "description": "Customer phone number" }`  
      `},`  
      `"required": ["first_name", "last_name", "email"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-customer"`  
  `}`  
`}`

### **Tool 2: create\_project**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "create_project",`  
    `"description": "Creates a new job site assigned to an existing customer ID.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"customer_id": { "type": "string", "description": "UUID of the customer from lookup_or_create_customer" },`  
        `"project_name": { "type": "string", "description": "Shorthand site name (e.g., Kitsilano Reno)" },`  
        `"site_address": { "type": "string", "description": "Physical site address" }`  
      `},`  
      `"required": ["customer_id", "project_name"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-create-project"`  
  `}`  
`}`

### **Tool 3: create\_estimate**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "create_estimate",`  
    `"description": "Creates the initial baseline quote for a project. (Base scope contract)",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": { "type": "string", "description": "Target project UUID or shorthand name" },`  
        `"scope_description": { "type": "string", "description": "Summary of baseline work scope" },`  
        `"labor_estimate": { "type": "number", "description": "Estimated labor cost" },`  
        `"material_estimate": { "type": "number", "description": "Estimated material cost" }`  
      `},`  
      `"required": ["project_id", "scope_description"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-create-estimate"`  
  `}`  
`}`

### **Tool 4: create\_change\_order**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "create_change_order",`  
    `"description": "Creates a standalone change order amendment. DO NOT use for initial estimates.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": { "type": "string", "description": "Target project UUID or shorthand name" },`  
        `"description": { "type": "string", "description": "Scope update or addition" },`  
        `"labor_cost": { "type": "number", "description": "Additional labor cost" },`  
        `"material_cost": { "type": "number", "description": "Additional material cost" }`  
      `},`  
      `"required": ["project_id", "description"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-create-change-order"`  
  `}`  
`}`

### **Tool 5: create\_invoice**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "create_invoice",`  
    `"description": "Generates a draft invoice pulling from progress on the base estimate or approved change orders.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": { "type": "string", "description": "Target project UUID or shorthand name" },`  
        `"invoice_type": { "type": "string", "enum": ["Deposit", "Progress", "Change Order", "Final"] },`  
        `"include_change_order_ids": {`   
          `"type": "array",`   
          `"items": { "type": "string" },`   
          `"description": "Array of Change Order UUIDs to include as separate line items"`   
        `},`  
        `"billing_percentage": { "type": "number", "description": "Percentage of base contract to bill (e.g. 25 for 25% progress)" }`  
      `},`  
      `"required": ["project_id", "invoice_type"]`  
    `}`  
  `},`  
  `"server": {`  
    `"url": "https://your-n8n-instance.com/webhook/vapi-create-invoice"`  
  `}`  
`}`

## **3\. Updated Vapi System Prompt**

`# Role & Context`  
`You are an executive voice project assistant managing 3-4 construction sites. You interact with database systems via tool calls to manage Customers, Projects, Estimates, Change Orders, Invoices, and Payroll.`

`# Rules of Operations & Logic`  
``1. **Customer First:** Before creating a project, verify or create the Customer record using `lookup_or_create_customer`.``  
`2. **Estimates vs Change Orders:**`  
   ``- Base scope = `create_estimate` (This sets the baseline contract value).``  
   ``- Any modifications after initial setup = `create_change_order` (Never overwrite the baseline estimate).``  
`3. **Invoicing:** Invoices can include progress percentages of the base estimate OR specific approved change orders as distinct line items.`  
`4. **Communication Style:**`  
   `- Speak in clear, short sentences (10–15 words max).`  
   `- Confirm critical details (Customer Name, Project Name, Dollar Amounts) before executing tools.`  
   `- Summarize tool execution outcomes in a single sentence.`

`# Conversation Examples`

`**User:** "I have a new client, Dave Miller, email dave@miller.com. Set up a project called Oakridge Build."`  
`**Assistant:** "First, I'll log Dave Miller's contact details, then create the Oakridge Build project. Processing now."`  
``*(Executes `lookup_or_create_customer` -> Executes `create_project`)*``

`**User:** "Add a change order for Oakridge: $800 materials and 4 hours labor to upgrade bathroom tile."`  
`**Assistant:** "Creating Change Order for Oakridge: $800 materials plus 4 hours labor for tile upgrade. Should I submit this?"`  
``*(User approves -> Executes `create_change_order`)*``

---

*User prompt: Provide n8n workflow configurations and PostgreSQL SQL queries to handle joins and rollups between Customers, Projects, Change Orders, and Invoices.*

Response: Here are the PostgreSQL rollup queries, n8n workflow configurations, and the complete JSON workflow snippet to connect Vapi voice tool calls directly to your PostgreSQL/Supabase database.

## **1\. PostgreSQL SQL Rollup & Join Queries**

### **Query 1: Master Project Financial Rollup (View Definition)**

This view joins all relational tables to calculate the original contract baseline, approved change orders, total contract value, billed amounts, paid totals, balance due, and labor hours per project.

`CREATE OR REPLACE VIEW view_project_financial_summary AS`  
`SELECT`   
    `p.id AS project_id,`  
    `p.project_name,`  
    `p.status AS project_status,`  
    `c.id AS customer_id,`  
    `CONCAT(c.first_name, ' ', c.last_name) AS customer_name,`  
    `c.email AS customer_email,`  
    `-- 1. Original Contract (Sum of Approved Base Estimates)`  
    `COALESCE(e.original_contract, 0.00) AS original_contract_value,`  
    `-- 2. Approved Change Orders Total`  
    `COALESCE(co.approved_co_total, 0.00) AS approved_change_orders_total,`  
    `-- 3. Total Revised Contract Value (Original + Approved COs)`  
    `(COALESCE(e.original_contract, 0.00) + COALESCE(co.approved_co_total, 0.00)) AS total_revised_contract_value,`  
    `-- 4. Invoicing Totals`  
    `COALESCE(inv.total_invoiced, 0.00) AS total_invoiced,`  
    `COALESCE(inv.total_paid, 0.00) AS total_paid,`  
    `-- 5. Remaining Balance Due to be Billed/Collected`  
    `((COALESCE(e.original_contract, 0.00) + COALESCE(co.approved_co_total, 0.00)) - COALESCE(inv.total_paid, 0.00)) AS balance_remaining,`  
    `-- 6. Total Job Labor Hours`  
    `COALESCE(ts.total_labor_hours, 0.00) AS total_labor_hours`  
`FROM projects p`  
`JOIN customers c ON p.customer_id = c.id`  
`LEFT JOIN (`  
    `SELECT project_id, SUM(total_estimate) AS original_contract`  
    `FROM estimates`  
    `WHERE status = 'Approved'`  
    `GROUP BY project_id`  
`) e ON p.id = e.project_id`  
`LEFT JOIN (`  
    `SELECT project_id, SUM(total_co_amount) AS approved_co_total`  
    `FROM change_orders`  
    `WHERE status = 'Approved'`  
    `GROUP BY project_id`  
`) co ON p.id = co.project_id`  
`LEFT JOIN (`  
    `SELECT`   
        `project_id,`   
        `SUM(total_amount) AS total_invoiced,`  
        `SUM(CASE WHEN status = 'Paid' THEN total_amount ELSE 0.00 END) AS total_paid`  
    `FROM invoices`  
    `GROUP BY project_id`  
`) inv ON p.id = inv.project_id`  
`LEFT JOIN (`  
    `SELECT project_id, SUM(hours_worked) AS total_labor_hours`  
    `FROM timesheets`  
    `GROUP BY project_id`  
`) ts ON p.id = ts.project_id;`

### **Query 2: Fetch Unbilled Approved Change Orders**

Used by n8n when building progress invoices to pull change orders that have been approved by the client but not yet linked to an invoice line item.

`SELECT`   
    `co.id AS change_order_id,`  
    `co.co_number,`  
    `co.description,`  
    `co.total_co_amount`  
`FROM change_orders co`  
`WHERE co.project_id = $1 -- Parameterized Project UUID or Name match`  
  `AND co.status = 'Approved'`  
  `AND co.id NOT IN (`  
      `SELECT source_id`   
      `FROM invoice_line_items`   
      `WHERE source_type = 'change_order' AND source_id IS NOT NULL`  
  `);`

### **Query 3: Customer Portfolio Rollup**

Generates a top-level financial summary across all active and completed projects for a specific customer.

`SELECT`   
    `c.id AS customer_id,`  
    `CONCAT(c.first_name, ' ', c.last_name) AS customer_name,`  
    `COUNT(p.id) AS total_projects,`  
    `SUM(v.total_revised_contract_value) AS total_portfolio_value,`  
    `SUM(v.total_invoiced) AS total_portfolio_invoiced,`  
    `SUM(v.balance_remaining) AS total_outstanding_balance`  
`FROM customers c`  
`JOIN projects p ON c.id = p.customer_id`  
`JOIN view_project_financial_summary v ON p.id = v.project_id`  
`WHERE c.id = $1`  
`GROUP BY c.id, c.first_name, c.last_name;`

## **2\. n8n Node-by-Node Workflow Configuration**

The n8n workflow acts as the bridge between Vapi and PostgreSQL.

`┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐`  
`│  1. Webhook     │────►│  2. PostgreSQL  │────►│  3. Code Node   │────►┌─────────────────┐`  
`│  (Vapi Tool)    │     │  Query Execution│     │  (Format String)│     │ 4. Respond to   │`  
`└─────────────────┘     └─────────────────┘     └─────────────────┘     │    Webhook      │`  
                                                                        `└─────────────────┘`

### **Node 1: Webhook Node (Vapi Trigger)**

> * **HTTP Method:** POST  
> * **Path:** vapi-project-summary  
> * **Response Mode:** On Received / Using 'Respond to Webhook' Node

### **Node 2: PostgreSQL Node (Execute Query)**

> * **Resource:** Database  
> * **Operation:** Execute Query  
> * **Query:**  
>   `SELECT * FROM view_project_financial_summary`   
>   `WHERE LOWER(project_name) LIKE LOWER($1)`   
>      `OR project_id::text = $1`   
>   `LIMIT 1;`

> * **Query Parameters:** \={{ $json.body.message.toolCalls\[0\].function.arguments.project\_id }}

### **Node 3: Code Node (Format Response for Vapi)**

Extracts database values and formats a short natural string for Vapi to speak back.

`const toolCall = $('Webhook').first().json.body.message.toolCalls[0];`  
`const toolCallId = toolCall.id;`  
`const dbResult = $input.first()?.json;`

`if (!dbResult) {`  
  `return [{`  
    `json: {`  
      `results: [{`  
        `toolCallId: toolCallId,`  
        `result: "I could not find a project matching that name in the database."`  
      `}]`  
    `}`  
  `}];`  
`}`

`// Format financial metrics into a spoken string`  
``const spokenSummary = `${dbResult.project_name} for ${dbResult.customer_name}: Revised contract is $${Number(dbResult.total_revised_contract_value).toLocaleString()}, with $${Number(dbResult.total_paid).toLocaleString()} collected. Outstanding balance is $${Number(dbResult.balance_remaining).toLocaleString()} with ${dbResult.total_labor_hours} labor hours logged.`;``

`return [{`  
  `json: {`  
    `results: [{`  
      `toolCallId: toolCallId,`  
      `result: spokenSummary`  
    `}]`  
  `}`  
`}];`

### **Node 4: Respond to Webhook Node**

> * **Respond With:** First Incoming Item  
> * **Response Code:** 200

## **3\. Complete n8n Workflow JSON Snippet**

Copy and paste this JSON into your n8n workflow canvas (**Import from JSON**):

`{`  
  `"name": "Vapi PostgreSQL Project Rollup Handler",`  
  `"nodes": [`  
    `{`  
      `"parameters": {`  
        `"httpMethod": "POST",`  
        `"path": "vapi-project-summary",`  
        `"responseMode": "responseNode",`  
        `"options": {}`  
      `},`  
      `"type": "n8n-nodes-base.webhook",`  
      `"typeVersion": 2,`  
      `"position": [0, 0],`  
      `"id": "webhook-vapi-receiver",`  
      `"name": "Vapi Webhook"`  
    `},`  
    `{`  
      `"parameters": {`  
        `"operation": "executeQuery",`  
        `"query": "SELECT * FROM view_project_financial_summary \nWHERE LOWER(project_name) LIKE '%' || LOWER($1) || '%'\nLIMIT 1;",`  
        `"options": {`  
          `"queryReplacement": "={{ $json.body.message.toolCalls[0].function.arguments.project_id }}"`  
        `}`  
      `},`  
      `"type": "n8n-nodes-base.postgres",`  
      `"typeVersion": 2.5,`  
      `"position": [220, 0],`  
      `"id": "postgres-financial-rollup",`  
      `"name": "PostgreSQL Query",`  
      `"credentials": {`  
        `"postgres": {`  
          `"id": "YOUR_POSTGRES_CREDENTIALS_ID",`  
          `"name": "Supabase PostgreSQL"`  
        `}`  
      `}`  
    `},`  
    `{`  
      `"parameters": {`  
        ``"jsCode": "const webhookData = $('Vapi Webhook').first().json;\nconst toolCall = webhookData.body.message.toolCalls[0];\nconst toolCallId = toolCall.id;\nconst dbResult = $input.first()?.json;\n\nif (!dbResult) {\n  return [{\n    json: {\n      results: [{\n        toolCallId: toolCallId,\n        result: \"Project not found. Please verify the project name.\"\n      }]\n    }\n  }];\n}\n\nconst spokenResult = `${dbResult.project_name} (${dbResult.customer_name}): Total revised contract is $${Number(dbResult.total_revised_contract_value).toLocaleString()}. Total paid to date is $${Number(dbResult.total_paid).toLocaleString()}, leaving a remaining balance of $${Number(dbResult.balance_remaining).toLocaleString()}. Total logged labor is ${dbResult.total_labor_hours} hours.`;\n\nreturn [{\n  json: {\n    results: [{\n      toolCallId: toolCallId,\n      result: spokenResult\n    }]\n  }\n}];"``  
      `},`  
      `"type": "n8n-nodes-base.code",`  
      `"typeVersion": 2,`  
      `"position": [440, 0],`  
      `"id": "code-format-vapi-response",`  
      `"name": "Format Vapi Speech"`  
    `},`  
    `{`  
      `"parameters": {`  
        `"respondWith": "allIncomingItems",`  
        `"options": {}`  
      `},`  
      `"type": "n8n-nodes-base.respondToWebhook",`  
      `"typeVersion": 1.1,`  
      `"position": [660, 0],`  
      `"id": "respond-to-vapi",`  
      `"name": "Respond to Vapi"`  
    `}`  
  `],`  
  `"connections": {`  
    `"Vapi Webhook": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "PostgreSQL Query",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `},`  
    `"PostgreSQL Query": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Format Vapi Speech",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `},`  
    `"Format Vapi Speech": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Respond to Vapi",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `}`  
  `}`  
`}`

---

*User prompt: it might be better to render it as a html page with a download option*

Response: Your HTML file is ready \[file-tag: code-generated-file-b7e509f4-58b9-40fe-b09f-afc4d53cd08d\]

### **Why an HTML Web Portal is Superior for Voice-Driven PM**

Rendering project statements as **dynamic HTML pages** rather than pre-generating static PDF attachments offers major technical and operational advantages:

> 1. **Real-Time Client & Manager Visibility:** When you log a change order or timesheet via Vapi on site, n8n updates PostgreSQL instantly. The client or project manager simply refreshes their web link (\[https://pm.yourdomain.com/portal?project\_id=kitsilano\](https://pm.yourdomain.com/portal?project\_id=kitsilano)) to see live running totals.  
> 2. **Zero Server Overhead for PDF Generation:** Instead of running heavy PDF engines on your backend for every minor update, the HTML dashboard uses native @media print CSS rules. Clicking **"Download PDF / Print"** invokes the browser's native print engine to generate a pixel-perfect PDF document on demand.  
> 3. **Built-in CSV Data Export:** Bookkeepers or sub-trades can click **"Export CSV"** to download raw tables for Excel or payroll processing.

### **Architectural Layout of the Generated Dashboard**

The generated file (construction\_project\_dashboard.html) incorporates the following sections:

> * **Top Action Bar (Screen-only):** Houses the interactive **Export CSV** and **Download PDF / Print** buttons (automatically hidden during printing).  
> * **Project & Customer Header Card:** Displays site address, status badges, client contacts, and statement dates.  
> * **Financial Metric Cards:** Live visual summary of Original Contract, Approved Change Orders, Total Revised Contract, Total Billed, and Balance Remaining.  
> * **1\. Baseline Scope Table:** Locked base contract breakdown (Demolition, Framing, Rough Plumbing/Electrical).  
> * **2\. Change Orders Table:** Separate tracking of approved vs. pending scope amendments with labor/material splits.  
> * **3\. Invoicing Ledger:** Historical log of progress and deposit billings with payment status badges (*Paid*, *Pending*).  
> * **4\. Voice AI Timesheet Log:** Site labor hours categorized by worker and trade code.

### **How to Serve this Dynamic Page in n8n**

You can configure n8n to serve this dynamic HTML dashboard directly to clients or internal teams whenever a link is opened or requested via Vapi:

 `[ Client / PM Clicks Link ] ──► [ n8n Webhook Node ] ──► [ PostgreSQL Query ] ──► [ n8n Code / HTML Node ] ──► [ Web Browser Render ]`

#### **n8n Node Setup:**

> 1. **Webhook Node (GET):**  
   * **Path:** project-portal  
   * **Response Mode:** Using 'Respond to Webhook' Node  
> 2. **PostgreSQL Node:**  
   * Executes SELECT \* FROM view\_project\_financial\_summary WHERE project\_id \= $1; using the URL parameter {{ $json.query.project\_id }}.  
> 3. **Respond to Webhook Node:**  
   * **Respond With:** Text  
   * **Response Body:** \={{ $json.rendered\_html\_template }}  
   * **Options / Custom Headers:**  
     * Content-Type: text/html; charset=utf-8

When Vapi finishes logging a change order, it can simply text or speak the portal URL: *"Change order logged. You can review the updated project statement at your project link."*

---

*User prompt: what would be in a project statement*

Response: A Construction Project Statement (or Statement of Account) is an executive financial and operational snapshot provided to clients, lenders, or project managers to track original contract commitments, approved scope changes, billing history, and remaining balances due.

## **1\. Header & Project Metadata**

Identifies the legal parties, site location, and statement timeline:

> * **Project Identifiers:** Project Name, Internal Project ID, and Contract Number.  
> * **Client Details:** Full Name, Company, Billing Address, and Email.  
> * **Contractor Details:** Company Name, Business Number, Site Manager Contact.  
> * **Site Address:** Physical construction location.  
> * **Statement Date:** Effective date of the report and billing period covered.

## **2\. Executive Financial Summary**

A top-level dashboard overview showing the exact macro-financial standing of the job:

> * **Original Contract Value:** The base quote agreed upon at signing.  
> * **Total Approved Change Orders:** The cumulative dollar addition or credit from approved amendments.  
> * **Revised Contract Value:** Original Contract+Approved Change Orders.  
> * **Total Billed to Date:** Cumulative amount invoiced across all milestones.  
> * **Total Paid to Date:** Actual funds collected from the client.  
> * **Current Balance Due:** Unpaid invoices currently awaiting payment.  
> * **Remaining Unbilled Contract:** Total contract value remaining to be billed upon future completion.

## **3\. Original Scope & Baseline Estimate**

Breaks down the initial contract by trade or major division of work:

> * **Division/Cost Code:** (e.g., Site Work, Framing, Mechanical, Finishes).  
> * **Scope Description:** Brief line-item description of contracted deliverables.  
> * **Allocated Amounts:** Labor vs. material split and total baseline price per division.

## **4\. Change Order Log**

Tracks all scope adjustments outside the initial contract to justify budget revisions:

> * **Change Order \#:** Sequentially numbered (e.g., CO-01, CO-02).  
> * **Description & Justification:** What changed (e.g., upgraded electrical panel, subfloor repair).  
> * **Cost Impact:** Labor and material adjustments (+/-).  
> * **Schedule Impact:** Additional days added to project completion timeline.  
> * **Approval Status:** *Draft*, *Pending Client Signature*, or *Approved*.

## **5\. Invoicing & Accounts Receivable Ledger**

Itemizes every invoice issued over the lifecycle of the project:

> * **Invoice \# & Issue Date:** Unique invoice identifier and posting date.  
> * **Invoice Type:** *Deposit*, *Progress Billing*, *Change Order Billing*, or *Final Release*.  
> * **Line Item Detail:** Specific deliverables covered under the invoice.  
> * **Holdback / Retainage:** Amount held back per legal requirements (e.g., standard 10% statutory holdback).  
> * **Payment Status:** *Draft*, *Sent*, *Paid* (with date), or *Overdue*.

## **6\. Project Schedule & Progress Tracking**

Connects financial progress to physical site completion:

> * **Overall Completion Percentage:** e.g., 65% complete.  
> * **Milestone Schedule:** Original target completion date vs. revised completion date.  
> * **Current Phase:** Active work phase (e.g., Rough-in inspection complete, Drywall ongoing).

## **7\. Payment Terms & Remittance**

Clear instructions on how the client can pay outstanding balances:

> * **Payment Terms:** (e.g., Net 15, Net 30).  
> * **Remittance Options:** Bank transfer details, Electronic Funds Transfer (EFT) info, or check mailing address.  
> * **Holdback Terms:** Conditions under which lien holdbacks will be released upon substantial completion.

---

*User prompt: can you summarize all these discussion in the appropriate markdown file including all the data schema , planning, architecture , n8n workflow and all the final decision such that I can download them*

`Response: # Voice AI & Project Lifecycle Automation System Architecture`  
`**Version:** 1.0`    
`**Stack:** Vapi.com (Voice Orchestration) | n8n (Workflow Automation) | Supabase/PostgreSQL (Database) | SendGrid / SMTP (Email Delivery)`

`---`

`## 1. Executive Summary & Architecture Overview`

`This document outlines the technical design, database schema, function calling protocols, and workflow automation specs for an AI-driven voice agent system integrated with an automated back-office backend.`

`### System Flow`  
`1. **User / Site Operator:** Communicates verbally via phone or mobile web app using **Vapi.com**.`  
`2. **Vapi Assistant:** Parses spoken intent, extracts structured arguments, and issues HTTP POST webhooks to **n8n**.`  
`3. **n8n Workflow Router:** Receives webhook requests, validates authentication headers, routes payload to appropriate sub-workflows (Timesheets, Change Orders, Project Statements, Invoices), executes database transactions in **Supabase / PostgreSQL**, and returns formatted text responses to Vapi within <1.5 seconds.`  
`4. **Notification Engine:** Generates billing documents, updates project totals, and dispatches customer emails asynchronously.`

   `+-------------------+`  
   `|   Voice Client    |`  
   `+---------+---------+`  
             `| (PSTN / WebRTC)`  
             `v`  
   `+-------------------+`  
   `|     Vapi.com      |`  
   `| (LLM + STT + TTS) |`  
   `+---------+---------+`  
             `| (HTTP Webhook / JSON)`  
             `v`  
   `+-------------------+`  
   `|   n8n Workflows   |`  
   `|  (Router Engine)  |`  
   `+----+----+----+----+`  
        `|    |    |`

\+--------+ | \+--------+ v v v \+------+ \+-------+ \+-------+ | DB | | Email | | PDF | \+------+ \+-------+ \+-------+

`---`

`## 2. Database Schema (PostgreSQL / Supabase)`

```` ```sql ````  
`-- Enable UUID extension`  
`CREATE EXTENSION IF NOT EXISTS "uuid-ossp";`

`-- CUSTOMERS TABLE`  
`CREATE TABLE customers (`  
    `id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),`  
    `name VARCHAR(255) NOT NULL,`  
    `company_name VARCHAR(255),`  
    `email VARCHAR(255) UNIQUE NOT NULL,`  
    `phone VARCHAR(50),`  
    `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP`  
`);`

`-- PROJECTS TABLE`  
`CREATE TABLE projects (`  
    `id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),`  
    `customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,`  
    `title VARCHAR(255) NOT NULL,`  
    `site_address TEXT NOT NULL,`  
    `original_contract_value NUMERIC(12, 2) NOT NULL DEFAULT 0.00,`  
    `revised_contract_value NUMERIC(12, 2) NOT NULL DEFAULT 0.00,`  
    `status VARCHAR(50) DEFAULT 'ACTIVE', -- ACTIVE, COMPLETED, ON_HOLD`  
    `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP`  
`);`

`-- ESTIMATES TABLE`  
`CREATE TABLE estimates (`  
    `id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),`  
    `project_id UUID REFERENCES projects(id) ON DELETE CASCADE,`  
    `division_code VARCHAR(50) NOT NULL, -- e.g., Framing, Electrical, Plumbing`  
    `scope_description TEXT NOT NULL,`  
    `allocated_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,`  
    `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP`  
`);`

`-- CHANGE ORDERS TABLE`  
`CREATE TABLE change_orders (`  
    `id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),`  
    `project_id UUID REFERENCES projects(id) ON DELETE CASCADE,`  
    `change_order_number INT NOT NULL,`  
    `description TEXT NOT NULL,`  
    `cost_impact NUMERIC(12, 2) NOT NULL, -- Positive for additions, negative for credits`  
    `schedule_impact_days INT DEFAULT 0,`  
    `approval_status VARCHAR(50) DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED`  
    `approved_at TIMESTAMP WITH TIME ZONE,`  
    `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP`  
`);`

`-- TIMESHEETS TABLE`  
`CREATE TABLE timesheets (`  
    `id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),`  
    `project_id UUID REFERENCES projects(id) ON DELETE CASCADE,`  
    `worker_name VARCHAR(255) NOT NULL,`  
    `hours_worked NUMERIC(5, 2) NOT NULL,`  
    `work_description TEXT,`  
    `date_worked DATE NOT NULL DEFAULT CURRENT_DATE,`  
    `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP`  
`);`

`-- INVOICES TABLE`  
`CREATE TABLE invoices (`  
    `id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),`  
    `project_id UUID REFERENCES projects(id) ON DELETE CASCADE,`  
    `invoice_number VARCHAR(100) UNIQUE NOT NULL,`  
    `invoice_type VARCHAR(50) NOT NULL, -- DEPOSIT, PROGRESS_BILLING, CHANGE_ORDER, FINAL`  
    `amount_due NUMERIC(12, 2) NOT NULL,`  
    `holdback_amount NUMERIC(12, 2) DEFAULT 0.00,`  
    `status VARCHAR(50) DEFAULT 'UNPAID', -- UNPAID, PAID, OVERDUE`  
    `issued_date DATE DEFAULT CURRENT_DATE,`  
    `due_date DATE NOT NULL,`  
    `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP`  
`);`

## **3\. Vapi Tool & Function Calling Definitions**

The following tool definitions must be configured within the Vapi Assistant settings to trigger backend execution via custom functions.

### **Tool 1: log\_timesheet**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "log_timesheet",`  
    `"description": "Logs worked hours for a worker on a specific construction or software project.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": {`  
          `"type": "string",`  
          `"description": "UUID of the project."`  
        `},`  
        `"worker_name": {`  
          `"type": "string",`  
          `"description": "Full name of the worker."`  
        `},`  
        `"hours_worked": {`  
          `"type": "number",`  
          `"description": "Number of hours to log (e.g., 7.5)."`  
        `},`  
        `"work_description": {`  
          `"type": "string",`  
          `"description": "Summary of tasks performed during these hours."`  
        `}`  
      `},`  
      `"required": ["project_id", "worker_name", "hours_worked"]`  
    `}`  
  `}`  
`}`

### **Tool 2: create\_change\_order**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "create_change_order",`  
    `"description": "Records a new change order and updates project financial totals upon approval.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": {`  
          `"type": "string",`  
          `"description": "UUID of the project."`  
        `},`  
        `"description": {`  
          `"type": "string",`  
          `"description": "Detailed explanation of scope modifications."`  
        `},`  
        `"cost_impact": {`  
          `"type": "number",`  
          `"description": "Financial delta in dollars (e.g. 1500.00 or -300.00)."`  
        `},`  
        `"schedule_impact_days": {`  
          `"type": "integer",`  
          `"description": "Additional timeline days required."`  
        `}`  
      `},`  
      `"required": ["project_id", "description", "cost_impact"]`  
    `}`  
  `}`  
`}`

### **Tool 3: get\_project\_statement**

`{`  
  `"type": "function",`  
  `"function": {`  
    `"name": "get_project_statement",`  
    `"description": "Retrieves current financial summary, total billed, change orders, and balance due for a project.",`  
    `"parameters": {`  
      `"type": "object",`  
      `"properties": {`  
        `"project_id": {`  
          `"type": "string",`  
          `"description": "UUID of the project."`  
        `}`  
      `},`  
      `"required": ["project_id"]`  
    `}`  
  `}`  
`}`

## **4\. n8n Workflow Architecture & Logic**

### **Workflow 1: Primary Webhook Router & Execution**

> * **Trigger:** Webhook Node (POST /vapi-webhook)  
> * **Node 1: Authentication Check**  
  * Validates x-vapi-secret header against workflow environment variables.  
> * **Node 2: Switch / Router Node**  
  * Evaluates {{ $json.body.message.toolCalls\[0\].function.name }}:  
    * **Branch A (log\_timesheet):** Insert record into timesheets \-\> Return JSON success payload.  
    * **Branch B (create\_change\_order):**  
      * Execute PostgreSQL transaction:  
        1. Insert into change\_orders table (status='APPROVED').  
        2. Update projects table: revised\_contract\_value \= revised\_contract\_value \+ cost\_impact.  
      * Return revised totals.  
    * **Branch C (get\_project\_statement):**  
      * Query total contract value, cumulative sum of change orders, total billed invoices, and total payments.  
      * Compute Current Balance Due and Remaining Contract Balance.  
      * Format concise text summary for voice playback.

### **Standardized Response Payload (n8n \-\> Vapi)**

To maintain real-time conversational velocity, n8n must return HTTP 200 within 1,200ms using the following JSON structure:

`{`  
  `"results": [`  
    `{`  
      `"toolCallId": "{{ $json.body.message.toolCalls[0].id }}",`  
      `"result": "Change order #4 successfully created for $2,500. Revised contract total is now $48,500."`  
    `}`  
  `]`  
`}`

## **5\. Implementation Planning & Milestones**

| Phase | Core Deliverables | Timeline |
| :---- | :---- | :---- |
| **Phase 1: Foundation** | Database migrations on Supabase, index optimization, API authentication rules. | Week 1 |
| **Phase 2: n8n Core** | Endpoint routing, SQL query nodes, JSON response formatter, error handling. | Week 2 |
| **Phase 3: Vapi Integration** | System prompts, function definitions, STT/TTS latency tuning, webhook binding. | Week 3 |
| **Phase 4: Billing & Mail** | Automated HTML-to-PDF invoice conversion, SendGrid email triggers, end-to-end testing. | Week 4 |

## **6\. Architectural Decision Record (ADR)**

> * **Decision 1: Synchronous Response for Voice Feedback**  
  * *Context:* Vapi requires quick acoustic feedback to prevent user drop-off or speech overlap.  
  * *Decision:* Database operations in n8n are executed synchronously with strict statement timeouts (3,000ms limit). Complex PDF generation or external email dispatches are offloaded to asynchronous background sub-workflows using n8n memory queues.  
> * **Decision 2: Strict Financial Calculation in Database**  
  * *Context:* LLMs struggle with precise cumulative financial arithmetic across complex change order logs.  
  * *Decision:* All financial balances, holdback percentages, and project statement summaries are calculated via SQL queries inside PostgreSQL rather than in the LLM context.  
> * **Decision 3: Idempotency Keys on Functions**  
  * *Context:* Voice reconnects or retries can double-trigger billing or change order additions.  
  * *Decision:* Pass Vapi toolCallId or call transaction ID as an idempotency key to prevent duplicate entries in timesheets and change\_orders.

`<FollowUp label="Want me to generate the complete n8n workflow JSON file for import?" query="Generate the complete n8n workflow JSON file so I can import it directly into n8n."/>`

---

*User prompt: how do I create a document that can capture all that we have discussed here.*

Response: Here are the standard methods to save and convert the architecture document onto your local computer.

## **Method 1: Save directly as a Markdown File (.md)**

Markdown (.md) is the standard format for technical documentation, GitHub repositories, and tools like Obsidian or Notion.

### **Using VS Code or any Code Editor**

> 1. Open **VS Code** (or your preferred editor).  
> 2. Create a new file named ARCHITECTURE.md or SYSTEM\_DESIGN.md.  
> 3. Copy the Markdown code block from the response above and paste it into the file.  
> 4. Press Cmd \+ Shift \+ V (Mac) or Ctrl \+ Shift \+ V (Windows) to preview the rendered document.

### **Using the Terminal (Mac / Linux)**

Run this command in your terminal to create the file directly in your project folder:

`cat << 'EOF' > ARCHITECTURE.md`  
`# Paste the Markdown content here`  
`EOF`

## **Method 2: Convert to PDF**

If you need to distribute the document to clients, stakeholders, or team members as a non-editable PDF:

### **Option A: VS Code Extension (Easiest)**

> 1. Install the **Markdown PDF** extension in VS Code.  
> 2. Open your ARCHITECTURE.md file.  
> 3. Right-click anywhere in the editor and select **Markdown PDF: Export (pdf)**.

### **Option B: Using Pandoc (Command Line)**

If you have pandoc installed via Homebrew (brew install pandoc):

`pandoc ARCHITECTURE.md -o ARCHITECTURE.pdf --pdf-engine=wkhtmltopdf`

## **Method 3: Import into Documentation Tools**

> * **Notion:** Create a new page → Click **Import** → Select **Markdown** → Choose your ARCHITECTURE.md file.  
> * **GitHub / GitLab:** Commit the file into your project repository under a /docs directory (e.g., docs/ARCHITECTURE.md). GitHub will automatically render the schema, formatting, and tables on the web.  
> * **Google Docs:** Copy the formatted rendered preview text directly from VS Code or a Markdown viewer and paste it into a Google Doc.

---

*User prompt: to continue the voice assistant discussion, when a voice assistant is created in vapi, the platform give you a link to voice test the assistant or vapi has api to build a voice and text chat widget for the assistant. can I package this widget as a mobile app so user can voice or text chat with the assistant.*

Response: Yes, you can package a Vapi voice and text assistant into a mobile application. You have two main approaches to accomplish this: using **Native Mobile SDKs** (recommended for production) or using a **WebView Wrapper** (fastest for prototyping).

## **Approach 1: Native Mobile SDK Integration (Recommended)**

Instead of loading the web widget inside a browser wrapper, you use Vapi’s native SDKs (e.g., Flutter, React Native, iOS/Swift, Android/Kotlin) directly inside your app.

### **Why Native SDKs Are Best**

> * **Low-Latency WebRTC:** Native SDKs manage the WebRTC audio connection directly through the device's audio hardware rather than browser abstraction layers.  
> * **Flawless Microphone Permissions:** Handles OS-level hardware permissions natively without WebView security blocks.  
> * **Background Audio:** Keeps calls active even if the user switches apps or locks their screen.  
> * **Custom UI Control:** Allows you to build your own custom voice call buttons, visual sound waves, and text chat interfaces while delegating audio orchestration to Vapi.

### **How It Works (Example: Flutter / Mobile SDK)**

> 1. **Initialize Vapi Client:** Pass your Vapi Public API Key and Assistant ID.  
> 2. **Handle Call Events:** Subscribe to events like call-start, call-end, speech-update, and transcript.  
> 3. **Send Text Messages:** Use text endpoints or function calls to send text input directly to the assistant during an active session.

`import 'package:vapi/vapi.dart'; // Vapi SDK package`

`final vapi = Vapi('YOUR_PUBLIC_KEY');`

`// Start a Voice Session`  
`void startVoiceCall() async {`  
  `await vapi.start(assistantId: 'YOUR_ASSISTANT_ID');`  
`}`

`// Stop a Voice Session`  
`void stopVoiceCall() async {`  
  `await vapi.stop();`  
`}`

`// Listen for Transcripts & Function Call Outputs`  
`void listenToAssistant() {`  
  `vapi.onEvent.listen((event) {`  
    `if (event.type == 'transcript') {`  
      `print("User/Assistant spoken text: ${event.data['transcript']}");`  
    `}`  
  `});`  
`}`

## **Approach 2: WebView Wrapper (Quick Prototype)**

You can package the Vapi web widget inside an in-app WebView (a hidden or embedded browser component within your iOS or Android app).

### **Limitations to Keep in Mind**

> * **Microphone Permission Blocks:** Both iOS (WKWebView) and Android (Chromium WebView) strictly block WebRTC microphone access inside web views by default. You must explicitly grant origin-level media permissions inside native code.  
> * **Audio Session Drops:** If a user receives a phone call or navigates away from the WebView tab, the WebRTC audio stream will break.

## **Mobile OS Configuration Checklist**

To package your voice app for Apple App Store or Google Play Store deployment, you must enable hardware-level audio permissions:

### **1\. iOS Configuration (Info.plist)**

`<!-- Request Microphone Access -->`  
`<key>NSMicrophoneUsageDescription</key>`  
`<string>This app requires microphone access to communicate with the AI Assistant.</string>`

`<!-- Enable Background Audio Execution -->`  
`<key>UIBackgroundModes</key>`  
`<array>`  
    `<string>audio</string>`  
    `<string>voip</string>`  
`</array>`

### **2\. Android Configuration (AndroidManifest.xml)**

`<!-- Request Hardware Permissions -->`  
`<uses-permission android:name="android.permission.RECORD_AUDIO" />`  
`<uses-permission android:name="android.permission.INTERNET" />`  
`<uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />`

## **Combining Voice and Text in One App UI**

A standard pattern for combining voice and text in a single Vapi mobile interface:

| Component | State / Action |
| :---- | :---- |
| **Voice Button** | Triggers vapi.start() over WebRTC for continuous duplex streaming. |
| **Text Input Bar** | Sends typed strings to Vapi's backend or custom API endpoint, returning the assistant's text response without playing audio. |
| **Transcript View** | Displays real-time streaming transcripts received via Vapi's transcript event listeners. |

---

*User prompt: what about elevenlab, what kind of capability does it offer for mobile app*

Response: ElevenLabs provides two main integration paths for mobile applications: using **ElevenAgents (their end-to-end Conversational AI platform)** or using their **standalone Audio APIs (Text-to-Speech, Voice Cloning, and Speech-to-Speech)**.

## **1\. End-to-End Voice Agents (ElevenAgents)**

ElevenLabs offers a complete voice assistant orchestration system similar to Vapi. It handles WebRTC streaming, Speech-to-Text (STT), Large Language Model (LLM) processing, and Text-to-Speech (TTS) in a single connection.

### **Key Mobile Capabilities**

> * **Native Mobile SDKs:** Official SDKs for **Swift (iOS/macOS)** and **React Native / Expo**, with WebSockets/WebRTC support for Flutter and Android.  
> * **Low-Latency WebRTC Streaming:** Built on top of LiveKit WebRTC to deliver sub-second speech responses directly to mobile device speakers.  
> * **Client Tool Calling:** Allows the AI agent to trigger actions *inside the mobile app* during a live conversation (e.g., navigating to a screen, toggling device settings, or grabbing current GPS coordinates).  
> * **Text & Voice Hybrid Mode:** Supports both typed text and voice streaming over the same session—allowing users to mute their mic and type without losing conversation state.  
> * **Interrupt Handling:** Automatically pauses audio playback on the mobile device when the user starts speaking over the agent.

## **2\. Ultra-Realistic Streaming TTS (Text-to-Speech)**

If you already manage your agent logic on your own server or via n8n, you can use ElevenLabs purely as a high-fidelity voice rendering engine.

> * **WebSocket Audio Chunks:** Streams PCM/MP3 audio buffers in real-time. Mobile apps can feed these chunks directly into native audio players (AVPlayer on iOS, ExoPlayer on Android, or just\_audio in Flutter) to start playing speech before the full response is generated.  
> * **5,000+ Voices & 30+ Languages:** Includes automatic language detection and switching mid-sentence.  
> * **Dynamic Voice Customization:** Control parameters like stability, clarity, emotion, and speech rate programmatically per request.

## **3\. Specialized Audio Features for Mobile Apps**

| Feature | Mobile Use Case |
| :---- | :---- |
| **Instant Voice Cloning** | Users record a 1-minute sample using the phone mic, and the app instantly creates a cloned voice model via the API. |
| **Speech-to-Speech (STS)** | Transforms user microphone input into a different voice while preserving their exact pacing, cadence, and emotion. |
| **Voice Isolator API** | Cleans up background noise, traffic, or wind from microphone audio captured on mobile devices before processing. |
| **Sound Effects Generation** | Generates dynamic UI sound effects or game audio assets on the fly from text descriptions. |

## **4\. Mobile Integration Options**

                    `┌──────────────────────────────────────────────┐`  
                    `│            Your Mobile Application           │`  
                    `└──────┬────────────────────────────────┬──────┘`  
                           `│                                │`  
            `(Option A: Full Voice Agent)      (Option B: TTS Only)`  
                           `│                                │`  
                           `v                                v`  
               `┌───────────────────────┐        ┌───────────────────────┐`  
               `│     ElevenAgents      │        │  ElevenLabs TTS API   │`  
               `│ (WebRTC Voice Session)│        │ (WebSocket Stream)    │`  
               `└───────────┬───────────┘        └───────────┬───────────┘`  
                           `│                                │`  
                           `v                                v`  
               `┌───────────────────────┐        ┌───────────────────────┐`  
               `│ Built-in LLM & Tools  │        │ Your Custom Backend / │`  
               `│     (or n8n Webhook)  │        │     n8n / Vapi        │`  
               `└───────────────────────┘        └───────────────────────┘`

### **Option A: ElevenLabs as a Standalone Platform**

You use ElevenAgents and their Swift/React Native SDKs directly inside your app. ElevenLabs handles the LLM, system prompt, knowledge base, and voice rendering directly.

### **Option B: ElevenLabs Combined with Vapi**

You use **Vapi** for overall voice call orchestration, backend routing, and n8n webhooks, but select **ElevenLabs** as the Voice Engine within Vapi's dashboard. This gives you Vapi's workflow features paired with ElevenLabs' voice quality.

---

*User prompt: I want to see how react native integration*

Response: ElevenLabs provides an official React Native SDK (@elevenlabs/react-native) for voice agents. It uses **LiveKit WebRTC** under the hood to ensure sub-second latency audio streaming and full-duplex communication (allowing interruptions).

## **1\. Installation & Dependencies**

Install the core package alongside LiveKit peer dependencies:

`npm install @elevenlabs/react-native @livekit/react-native @livekit/react-native-webrtc livekit-client`

*If using **Expo**, ensure you run npx expo prebuild or use the Expo Dev Client, as WebRTC relies on native C++ modules.*

## **2\. Platform Permissions Setup**

### **iOS Setup (ios/YourProject/Info.plist)**

Add permission to use the microphone:

`<key>NSMicrophoneUsageDescription</key>`  
`<string>This app requires microphone access to communicate with the voice assistant.</string>`

### **Android Setup (android/app/src/main/AndroidManifest.xml)**

Grant required audio hardware permissions:

`<uses-permission android:name="android.permission.RECORD_AUDIO" />`  
`<uses-permission android:name="android.permission.INTERNET" />`  
`<uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />`

## **3\. Implementation Example**

Here is a complete, production-ready React Native component featuring voice control, call status handling, and **Client Tool Calling** (allowing the agent to perform actions inside your mobile app):

`import React from 'react';`  
`import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';`  
`import { useConversation } from '@elevenlabs/react-native';`

`export default function VoiceAssistantScreen() {`  
  `const conversation = useConversation({`  
    `onConnect: () => console.log('Connected to ElevenLabs Agent'),`  
    `onDisconnect: () => console.log('Disconnected'),`  
    `onMessage: (message) => {`  
      `// Receives real-time transcript updates from user & agent`  
      `console.log('Message:', message);`  
    `},`  
    `onError: (error) => console.error('Voice Error:', error),`  
  `});`

  `const handleToggleCall = async () => {`  
    `if (conversation.status === 'connected') {`  
      `await conversation.endSession();`  
    `} else {`  
      `// Start session using your ElevenLabs Agent ID`  
      `await conversation.startSession({`  
        `agentId: 'YOUR_ELEVENLABS_AGENT_ID',`  
          
        `// Client Tools: Functions the AI agent can execute inside your app`  
        `clientTools: {`  
          `navigateToScreen: async ({ screenName }: { screenName: string }) => {`  
            ``console.log(`Agent requested navigation to: ${screenName}`);``  
            `// Trigger your React Navigation logic here`  
            ``return `Successfully navigated to ${screenName}`;``  
          `},`  
        `},`  
      `});`  
    `}`  
  `};`

  `const isConnected = conversation.status === 'connected';`  
  `const isConnecting = conversation.status === 'connecting';`

  `return (`  
    `<View style={styles.container}>`  
      `<Text style={styles.statusText}>`  
        `Status: <Text style={styles.bold}>{conversation.status}</Text>`  
      `</Text>`

      `{/* Mic Volume Visualizer Indicator */}`  
      `{isConnected && (`  
        `<Text style={styles.speakingText}>`  
          `{conversation.isSpeaking ? 'Agent is speaking...' : 'Listening...'}`  
        `</Text>`  
      `)}`

      `{/* Main Action Button */}`  
      `<TouchableOpacity`  
        `style={[styles.button, isConnected ? styles.buttonDisconnect : styles.buttonConnect]}`  
        `onPress={handleToggleCall}`  
        `disabled={isConnecting}`  
      `>`  
        `{isConnecting ? (`  
          `<ActivityIndicator color="#fff" />`  
        `) : (`  
          `<Text style={styles.buttonText}>`  
            `{isConnected ? 'End Conversation' : 'Start Voice Chat'}`  
          `</Text>`  
        `)}`  
      `</TouchableOpacity>`  
    `</View>`  
  `);`  
`}`

`const styles = StyleSheet.create({`  
  `container: {`  
    `flex: 1,`  
    `justifyContent: 'center',`  
    `alignItems: 'center',`  
    `backgroundColor: '#0F172A',`  
  `},`  
  `statusText: {`  
    `color: '#94A3B8',`  
    `fontSize: 16,`  
    `marginBottom: 10,`  
  `},`  
  `bold: {`  
    `fontWeight: 'bold',`  
    `color: '#F8FAFC',`  
  `},`  
  `speakingText: {`  
    `color: '#38BDF8',`  
    `fontSize: 14,`  
    `marginBottom: 30,`  
  `},`  
  `button: {`  
    `paddingVertical: 16,`  
    `paddingHorizontal: 32,`  
    `borderRadius: 30,`  
    `elevation: 3,`  
  `},`  
  `buttonConnect: {`  
    `backgroundColor: '#2563EB',`  
  `},`  
  `buttonDisconnect: {`  
    `backgroundColor: '#DC2626',`  
  `},`  
  `buttonText: {`  
    `color: '#FFFFFF',`  
    `fontSize: 18,`  
    `fontWeight: '600',`  
  `},`  
`});`

## **Key Features Provided Out-of-the-Box**

> 1. **useConversation Hook:** Manages session state (disconnected, connecting, connected), audio playback controls, and mic permissions automatically.  
> 2. **Built-in Echo Cancellation & Interruption:** If the user speaks while the agent is talking, LiveKit instantly cuts off the agent’s audio playback on the mobile device.  
> 3. **In-App Client Tools:** You can pass JavaScript functions into clientTools when calling startSession(). When the ElevenLabs agent decides to run a local action (e.g., fetching local device GPS data, switching tabs, or logging state), it executes that code on the device and continues talking.

---

*User prompt: How do I handle authentication and generate signed URLs for private ElevenLabs voice agents in a mobile app?*

Response: To secure a private ElevenLabs agent in a mobile app, **never include your master xi-api-key inside the mobile app bundle**. Hardcoding long-lived secrets inside React Native or mobile binaries makes them vulnerable to extraction via reverse engineering.

Instead, use an **ephemeral authorization pattern** where your backend mints short-lived signed URLs or WebRTC tokens on demand.

`[ Mobile Client ] --(1. Auth with User JWT)--> [ Your Backend Server ]`  
`[ Mobile Client ] <--(3. Returns Signed URL)-- [ Your Backend Server ]`  
                                                     `|`  
                                        `(2. Mints URL using xi-api-key)`  
                                                     `v`  
                                             `[ ElevenLabs API ]`

`[ Mobile Client ] =====(4. Connects via Signed WebSockets/WebRTC)=====> [ ElevenLabs ]`

ElevenLabs offers two authentication endpoints for minting short-lived access:

> * **GET /v1/convai/conversation/get-signed-url** (WebSocket / Text-only mode)  
> * **GET /v1/convai/conversation/token** (WebRTC Voice mode)

### **1\. Backend Implementation (Node.js / Express)**

Create a protected endpoint on your server (or n8n / Supabase Edge Function) that validates the user's session and requests a temporary signed URL from ElevenLabs using your server-side API key.

`// server.js (Node.js / Express backend)`  
`import express from 'express';`

`const app = express();`

`app.post('/api/elevenlabs/session', async (req, res) => {`  
  `// 1. Verify user authentication (e.g. validate JWT from authorization header)`  
  `const userToken = req.headers.authorization;`  
  `if (!userToken) {`  
    `return res.status(401).json({ error: 'Unauthorized access' });`  
  `}`

  `const agentId = process.env.ELEVENLABS_AGENT_ID;`  
  `const apiKey = process.env.ELEVENLABS_API_KEY; // Master key stored securely in server env`

  `try {`  
    `// 2. Request a short-lived signed URL from ElevenLabs`  
    `const response = await fetch(`  
      `` `https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?agent_id=${agentId}`, ``  
      `{`  
        `method: 'GET',`  
        `headers: {`  
          `'xi-api-key': apiKey,`  
        `},`  
      `}`  
    `);`

    `if (!response.ok) {`  
      ``throw new Error(`ElevenLabs API error: ${response.statusText}`);``  
    `}`

    `const data = await response.json();`  
      
    `// Returns { signed_url: "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=...&conversation_signature=..." }`  
    `res.json({ signedUrl: data.signed_url });`  
  `} catch (error) {`  
    `console.error('Failed to generate ElevenLabs signed URL:', error);`  
    `res.status(500).json({ error: 'Failed to generate session token' });`  
  `}`  
`});`

### **2\. Mobile Client Implementation (React Native)**

In your mobile application, call your backend endpoint first to obtain the temporary signedUrl, then pass it directly to conversation.startSession().

`import React from 'react';`  
`import { View, TouchableOpacity, Text, StyleSheet } from 'react-native';`  
`import { useConversation } from '@elevenlabs/react-native';`

`export default function VoiceAgentScreen({ userAuthToken }: { userAuthToken: string }) {`  
  `const conversation = useConversation({`  
    `onConnect: () => console.log('Connected using signed URL'),`  
    `onDisconnect: () => console.log('Session ended'),`  
    `onError: (err) => console.error('Voice Error:', err),`  
  `});`

  `const handleStartCall = async () => {`  
    `try {`  
      `// 1. Request short-lived signed URL from YOUR backend`  
      `const response = await fetch('https://your-backend.com/api/elevenlabs/session', {`  
        `method: 'POST',`  
        `headers: {`  
          ``Authorization: `Bearer ${userAuthToken}`,``  
        `},`  
      `});`

      `const { signedUrl } = await response.json();`

      `// 2. Connect to ElevenLabs using the temporary signed URL`  
      `await conversation.startSession({`  
        `signedUrl,`  
      `});`  
    `} catch (error) {`  
      `console.error('Failed to initiate secure call:', error);`  
    `}`  
  `};`

  `const isConnected = conversation.status === 'connected';`

  `return (`  
    `<View style={styles.container}>`  
      `<TouchableOpacity`  
        `style={[styles.button, isConnected ? styles.buttonActive : styles.buttonInactive]}`  
        `onPress={isConnected ? () => conversation.endSession() : handleStartCall}`  
      `>`  
        `<Text style={styles.buttonText}>`  
          `{isConnected ? 'End Conversation' : 'Start Secure Session'}`  
        `</Text>`  
      `</TouchableOpacity>`  
    `</View>`  
  `);`  
`}`

`const styles = StyleSheet.create({`  
  `container: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0F172A' },`  
  `button: { paddingVertical: 14, paddingHorizontal: 28, borderRadius: 25 },`  
  `buttonInactive: { backgroundColor: '#2563EB' },`  
  `buttonActive: { backgroundColor: '#DC2626' },`  
  `buttonText: { color: '#FFF', fontWeight: '600' },`  
`});`

### **3\. Security Checklist**

> * **Token Lifespan:** Signed URLs expire after 15 minutes if unused. Once connected, the WebSocket or WebRTC connection remains active for the duration of the call.  
> * **Single-Use Behavior:** Generate a new signed URL every time the user starts a session or reconnects after a dropped connection.  
> * **Rate-Limiting:** Implement IP and user-level rate limiting on your backend endpoint to prevent malicious users from spamming call initialization requests and draining your ElevenLabs credit quota.

To see a full demonstration of how signed URLs work in ElevenLabs and how to configure authentication settings in the dashboard, watch [Secure Your Agents: Allowlists & Signed URL Authentication](https://www.youtube.com/watch?v=8hZ4IWL7iqw). This tutorial breaks down signed URL generation, token expiration timelines, and best practices for securing client applications.

---

*User prompt: what is a signed url and whats a signed url authentication*

Response: A **signed URL** is a web address that includes embedded cryptographic parameters, granting temporary and restricted access to a specific resource without requiring the user or client application to possess an API key, master password, or active session login.

## **Structure of a Signed URL**

A signed URL looks like a standard web address, but it appends critical security query parameters to the end:

`https://api.service.com/v1/media/stream?`  
  `resource_id=12345`  
  `&expires=1711929600`  
  `&action=read`  
  `&signature=a8f5f167f44f4964e6c998dee827110c`

It consists of four primary components:

> 1. **Target Resource / Path:** The actual endpoint or file location (e.g., /media/stream).  
> 2. **Permissions / Constraints:** What action is allowed (e.g., read, write, GET, PUT).  
> 3. **Expiration Timestamp:** The exact date and time after which the URL becomes invalid.  
> 4. **Cryptographic Signature:** An HMAC (Hash-based Message Authentication Code) generated using a private secret key held only by the server.

## **What is Signed URL Authentication?**

**Signed URL authentication** is the verification process that takes place when a client makes a request using a signed link. Instead of checking a cookie or an HTTP Authorization header, the receiving server validates the cryptographic signature attached directly to the URL string.

### **How the Authentication Process Works**

`[ Un-authenticated Client ]                    [ Your Application Server ]                   [ Storage / Media Server ]`  
             `|                                              |                                            |`  
             `|--- 1. Request access (User JWT / Session) -->|                                            |`  
             `|                                              |--- 2. Generates Signed URL using ----------|`  
             `|                                              |       Private Secret & Expiration          |`  
             `|<-- 3. Returns Signed URL String -------------|                                            |`  
             `|                                                                                           |`  
             `|----------------------- 4. Makes request using Signed URL -------------------------------->|`  
             `|                                                                                           |-- 5. Re-calculates signature`  
             `|                                                                                           |   6. Checks expiration time`  
             `|<---------------------- 7. Streams data / grants access -------------------------------+-- 7. Validates & matches!`

> 1. **Generation (Server-Side):** When an authorized user requests access, your backend server takes the resource path, expiration time, and permissions, and hashes them using a **private secret key**:  
>    Signature=HMAC-SHA256(ResourcePath+Expiration+Permissions,SecretKey)  
>    The server attaches this signature to the URL and sends the complete URL string to the client.  
> 2. **Transmission (Client-Side):** The client (mobile app, browser, or third-party service) receives the URL and uses it directly to make an HTTP request to the target server (such as S3, Google Cloud Storage, or a WebRTC streaming node).  
> 3. **Verification (Receiving Server):** When the target server receives the request, it performs two fast checks:  
   * **Expiration Check:** Is current\_time \< expiration\_time? If the link has expired, it immediately rejects the request with HTTP 403 Forbidden.  
   * **Integrity & Authenticity Check:** The server extracts the resource path and expiration parameters from the incoming request and re-calculates the signature using its own copy of the SecretKey.  
   * **Verdict:** If the newly calculated signature matches the signature provided in the URL query string, the server knows the link was created by an authorized source and has **not been tampered with**. The request is approved.

## **Key Benefits of Signed URLs**

> * **Zero Key Exposure:** Client applications (such as mobile apps or browser JS) never hold long-lived master API keys or database credentials, preventing keys from being extracted via reverse engineering.  
> * **Bandwidth Offloading:** Your main application server does not need to act as a middleman (proxy) to stream heavy files, audio, or video. The app server simply issues a quick signed link, allowing the client to fetch media directly from cloud infrastructure or media servers.  
> * **Tamper Prevention:** If a user attempts to edit the URL parameters (e.g., changing expires=10min to expires=10years or changing file\_id=12 to file\_id=13), the cryptographic signature will no longer match, instantly invalidating the link.  
> * **Auto-Expiring Access:** Access automatically revokes itself after a set period (e.g., 5 to 15 minutes), minimizing the damage if a link is intercepted or leaked.

---

*User prompt: Show me how to create an n8n webhook workflow that mints ElevenLabs signed URLs for mobile apps.*

Response: Here is a complete n8n workflow setup to mint ElevenLabs signed URLs for mobile apps, including the architecture flow, step-by-step node configuration, and a copy-pasteable n8n workflow JSON.

## **Workflow Overview**

`[ Mobile App ] ──(1. POST /elevenlabs/signed-url w/ Auth Header)──> [ n8n Webhook ]`  
                                                                            `│`  
                                                                 `(2. Validate Auth)`  
                                                                            `│`  
                                                                            `▼`  
`[ Mobile App ] <──(4. Return JSON: { signedUrl })─────── [ HTTP Request: ElevenLabs ]`  
                                                          `(Mints URL via xi-api-key)`

## **Step-by-Step Node Configuration**

### **1\. Webhook Node (n8n-nodes-base.webhook)**

> * **HTTP Method:** POST  
> * **Path:** elevenlabs/signed-url  
> * **Respond:** Using 'Respond to Webhook' Node  
> * **Authentication:** Header Auth or managed inside workflow logic.

### **2\. Validate Token Node (n8n-nodes-base.if or Code)**

Checks that the request includes a valid authorization header from your mobile app before calling ElevenLabs.

> * **Condition:** {{ $json.headers.authorization }} is not empty.

### **3\. Mint Signed URL Node (n8n-nodes-base.httpRequest)**

> * **Method:** GET  
> * **URL:** \[https://api.elevenlabs.io/v1/convai/conversation/get-signed-url\](https://api.elevenlabs.io/v1/convai/conversation/get-signed-url)  
> * **Query Parameters:**  
  * Name: agent\_id | Value: {{ $json.body.agent\_id }}  
> * **Headers:**  
  * Name: xi-api-key | Value: {{ $env.ELEVENLABS\_API\_KEY }} *(or use n8n Credentials)*

### **4\. Respond to Webhook Node (n8n-nodes-base.respondToWebhook)**

> * **Respond With:** JSON  
> * **Response Body:**  
>   `{`  
>     `"signedUrl": "{{ $json.signed_url }}",`  
>     `"expiresAt": "{{ $now.plus(15, 'minutes').toISO() }}"`  
>   `}`

## **Importable n8n Workflow JSON**

Copy the code below, open your n8n canvas, press **Ctrl \+ V** (or **Cmd \+ V**), and paste it directly onto the canvas:

`{`  
  `"name": "ElevenLabs Signed URL Minter",`  
  `"nodes": [`  
    `{`  
      `"parameters": {`  
        `"httpMethod": "POST",`  
        `"path": "elevenlabs/signed-url",`  
        `"responseMode": "responseNode",`  
        `"options": {}`  
      `},`  
      `"id": "1a2b3c4d-0001",`  
      `"name": "Mobile Webhook Trigger",`  
      `"type": "n8n-nodes-base.webhook",`  
      `"typeVersion": 1,`  
      `"position": [250, 300]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"conditions": {`  
          `"string": [`  
            `{`  
              `"value1": "={{ $json.headers.authorization }}",`  
              `"operation": "isNotEmpty"`  
            `}`  
          `]`  
        `}`  
      `},`  
      `"id": "1a2b3c4d-0002",`  
      `"name": "Check Auth Header",`  
      `"type": "n8n-nodes-base.if",`  
      `"typeVersion": 1,`  
      `"position": [480, 300]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"method": "GET",`  
        `"url": "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",`  
        `"sendQuery": true,`  
        `"queryParameters": {`  
          `"parameters": [`  
            `{`  
              `"name": "agent_id",`  
              `"value": "={{ $json.body.agent_id }}"`  
            `}`  
          `]`  
        `},`  
        `"sendHeaders": true,`  
        `"headerParameters": {`  
          `"parameters": [`  
            `{`  
              `"name": "xi-api-key",`  
              `"value": "={{ $env.ELEVENLABS_API_KEY }}"`  
            `}`  
          `]`  
        `},`  
        `"options": {}`  
      `},`  
      `"id": "1a2b3c4d-0003",`  
      `"name": "Fetch ElevenLabs Signed URL",`  
      `"type": "n8n-nodes-base.httpRequest",`  
      `"typeVersion": 4.1,`  
      `"position": [700, 200]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"respondWith": "json",`  
        `"responseBody": "={\n  \"signedUrl\": \"{{ $json.signed_url }}\"\n}",`  
        `"options": {`  
          `"responseCode": 200`  
        `}`  
      `},`  
      `"id": "1a2b3c4d-0004",`  
      `"name": "Success Response",`  
      `"type": "n8n-nodes-base.respondToWebhook",`  
      `"typeVersion": 1,`  
      `"position": [920, 200]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"respondWith": "json",`  
        `"responseBody": "{\n  \"error\": \"Unauthorized request. Authorization header missing.\"\n}",`  
        `"options": {`  
          `"responseCode": 401`  
        `}`  
      `},`  
      `"id": "1a2b3c4d-0005",`  
      `"name": "Unauthorized Response",`  
      `"type": "n8n-nodes-base.respondToWebhook",`  
      `"typeVersion": 1,`  
      `"position": [700, 420]`  
    `}`  
  `],`  
  `"connections": {`  
    `"Mobile Webhook Trigger": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Check Auth Header",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `},`  
    `"Check Auth Header": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Fetch ElevenLabs Signed URL",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `],`  
        `[`  
          `{`  
            `"node": "Unauthorized Response",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `},`  
    `"Fetch ElevenLabs Signed URL": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Success Response",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `}`  
  `}`  
`}`

## **Testing Request (cURL)**

Execute this request against your active n8n instance to test URL generation:

`curl -X POST https://your-n8n-instance.com/webhook/elevenlabs/signed-url \`  
  `-H "Authorization: Bearer USER_SESSION_TOKEN" \`  
  `-H "Content-Type: application/json" \`  
  `-d '{`  
    `"agent_id": "YOUR_ELEVENLABS_AGENT_ID"`  
  `}'`

**Expected 200 OK Response:**

`{`  
  `"signedUrl": "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=YOUR_AGENT_ID&conversation_signature=eyJhbGciOi..."`  
`}`

---

*User prompt: Show me how to expand this n8n workflow to handle both ElevenLabs signed URLs and Vapi tool call webhooks.*

Response: To combine both services into a single n8n workflow, you create a **Unified Voice API Gateway**. A central Webhook node catches all incoming traffic, and an n8n **Switch Node** routes the request based on payload signatures:

> 1. **ElevenLabs Requests:** Contain an explicit action: "mint\_elevenlabs\_url" parameter from your mobile app.  
> 2. **Vapi Tool Webhooks:** Contain Vapi's system wrapper structure (message.type \= "tool-calls" or message.toolCalls).

## **Architectural Flow**

                                 `┌───────────────────────┐`  
                                 `│  POST /voice/gateway  │`  
                                 `└───────────┬───────────┘`  
                                             `│`  
                                             `v`  
                                 `┌───────────────────────┐`  
                                 `│  Router (Switch Node) │`  
                                 `└─────┬───────────┬─────┘`  
                                       `│           │`  
            `┌──────────────────────────┘           └──────────────────────────┐`  
            `│ (action == 'mint_elevenlabs_url')               (message.type == 'tool-calls')`  
            `v                                                                 v`  
`┌───────────────────────┐                                         ┌───────────────────────┐`  
`│ ElevenLabs API Call   │                                         │ Vapi Tool Sub-Router  │`  
`└───────────┬───────────┘                                         └───────────┬───────────┘`  
            `│                                                                 │`  
            `v                                               ┌─────────────────┼─────────────────┐`  
`┌───────────────────────┐                                   │                 │                 │`  
`│ Respond { signedUrl } │                                   v                 v                 v`  
`└───────────────────────┘                            [log_timesheet] [create_change_order] [get_statement]`  
                                                            `│                 │                 │`  
                                                            `└─────────────────┼─────────────────┘`  
                                                                              `│`  
                                                                              `v`  
                                                                  `┌───────────────────────┐`  
                                                                  `│  Respond to Vapi      │`  
                                                                  `│  { results: [...] }   │`  
                                                                  `└───────────────────────┘`

## **Unified n8n Workflow JSON**

Copy the JSON below and paste it directly onto your n8n canvas (**Ctrl \+ V** or **Cmd \+ V**):

`{`  
  `"name": "Unified Voice Gateway (ElevenLabs + Vapi)",`  
  `"nodes": [`  
    `{`  
      `"parameters": {`  
        `"httpMethod": "POST",`  
        `"path": "voice/gateway",`  
        `"responseMode": "responseNode",`  
        `"options": {}`  
      `},`  
      `"id": "gate-0001",`  
      `"name": "Voice Gateway Webhook",`  
      `"type": "n8n-nodes-base.webhook",`  
      `"typeVersion": 1,`  
      `"position": [240, 300]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"rules": {`  
          `"values": [`  
            `{`  
              `"conditions": {`  
                `"options": {`  
                  `"caseSensitive": true,`  
                  `"leftValue": "",`  
                  `"typeValidation": "strict"`  
                `},`  
                `"conditions": [`  
                  `{`  
                    `"leftValue": "={{ $json.body.action }}",`  
                    `"rightValue": "mint_elevenlabs_url",`  
                    `"operator": {`  
                      `"type": "string",`  
                      `"operation": "equals"`  
                    `}`  
                  `}`  
                `],`  
                `"combinator": "and"`  
              `},`  
              `"renameOutput": true,`  
              `"outputKey": "ElevenLabs URL Mint"`  
            `},`  
            `{`  
              `"conditions": {`  
                `"options": {`  
                  `"caseSensitive": true,`  
                  `"leftValue": "",`  
                  `"typeValidation": "strict"`  
                `},`  
                `"conditions": [`  
                  `{`  
                    `"leftValue": "={{ $json.body.message.type }}",`  
                    `"rightValue": "tool-calls",`  
                    `"operator": {`  
                      `"type": "string",`  
                      `"operation": "equals"`  
                    `}`  
                  `}`  
                `],`  
                `"combinator": "and"`  
              `},`  
              `"renameOutput": true,`  
              `"outputKey": "Vapi Tool Call"`  
            `}`  
          `]`  
        `},`  
        `"options": {}`  
      `},`  
      `"id": "gate-0002",`  
      `"name": "Gateway Router",`  
      `"type": "n8n-nodes-base.switch",`  
      `"typeVersion": 3,`  
      `"position": [480, 300]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"method": "GET",`  
        `"url": "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",`  
        `"sendQuery": true,`  
        `"queryParameters": {`  
          `"parameters": [`  
            `{`  
              `"name": "agent_id",`  
              `"value": "={{ $json.body.agent_id }}"`  
            `}`  
          `]`  
        `},`  
        `"sendHeaders": true,`  
        `"headerParameters": {`  
          `"parameters": [`  
            `{`  
              `"name": "xi-api-key",`  
              `"value": "={{ $env.ELEVENLABS_API_KEY }}"`  
            `}`  
          `]`  
        `},`  
        `"options": {}`  
      `},`  
      `"id": "gate-0003",`  
      `"name": "ElevenLabs Mint Request",`  
      `"type": "n8n-nodes-base.httpRequest",`  
      `"typeVersion": 4.1,`  
      `"position": [760, 160]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"respondWith": "json",`  
        `"responseBody": "={\n  \"signedUrl\": \"{{ $json.signed_url }}\"\n}",`  
        `"options": {`  
          `"responseCode": 200`  
        `}`  
      `},`  
      `"id": "gate-0004",`  
      `"name": "Respond ElevenLabs",`  
      `"type": "n8n-nodes-base.respondToWebhook",`  
      `"typeVersion": 1,`  
      `"position": [1000, 160]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"rules": {`  
          `"values": [`  
            `{`  
              `"conditions": {`  
                `"options": {`  
                  `"caseSensitive": true,`  
                  `"leftValue": "",`  
                  `"typeValidation": "strict"`  
                `},`  
                `"conditions": [`  
                  `{`  
                    `"leftValue": "={{ $json.body.message.toolCalls[0].function.name }}",`  
                    `"rightValue": "log_timesheet",`  
                    `"operator": {`  
                      `"type": "string",`  
                      `"operation": "equals"`  
                    `}`  
                  `}`  
                `],`  
                `"combinator": "and"`  
              `},`  
              `"renameOutput": true,`  
              `"outputKey": "log_timesheet"`  
            `},`  
            `{`  
              `"conditions": {`  
                `"options": {`  
                  `"caseSensitive": true,`  
                  `"leftValue": "",`  
                  `"typeValidation": "strict"`  
                `},`  
                `"conditions": [`  
                  `{`  
                    `"leftValue": "={{ $json.body.message.toolCalls[0].function.name }}",`  
                    `"rightValue": "create_change_order",`  
                    `"operator": {`  
                      `"type": "string",`  
                      `"operation": "equals"`  
                    `}`  
                  `}`  
                `],`  
                `"combinator": "and"`  
              `},`  
              `"renameOutput": true,`  
              `"outputKey": "create_change_order"`  
            `}`  
          `]`  
        `},`  
        `"options": {}`  
      `},`  
      `"id": "gate-0005",`  
      `"name": "Vapi Tool Sub-Router",`  
      `"type": "n8n-nodes-base.switch",`  
      `"typeVersion": 3,`  
      `"position": [760, 420]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"assignments": {`  
          `"assignments": [`  
            `{`  
              `"id": "res-1",`  
              `"name": "toolResult",`  
              `"value": "Work hours successfully logged into database.",`  
              `"type": "string"`  
            `}`  
          `]`  
        `},`  
        `"options": {}`  
      `},`  
      `"id": "gate-0006",`  
      `"name": "Exec: log_timesheet",`  
      `"type": "n8n-nodes-base.set",`  
      `"typeVersion": 3.4,`  
      `"position": [1000, 360]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"assignments": {`  
          `"assignments": [`  
            `{`  
              `"id": "res-2",`  
              `"name": "toolResult",`  
              `"value": "Change order recorded and revised project value updated.",`  
              `"type": "string"`  
            `}`  
          `]`  
        `},`  
        `"options": {}`  
      `},`  
      `"id": "gate-0007",`  
      `"name": "Exec: create_change_order",`  
      `"type": "n8n-nodes-base.set",`  
      `"typeVersion": 3.4,`  
      `"position": [1000, 480]`  
    `},`  
    `{`  
      `"parameters": {`  
        `"respondWith": "json",`  
        `"responseBody": "={\n  \"results\": [\n    {\n      \"toolCallId\": \"{{ $('Voice Gateway Webhook').item.json.body.message.toolCalls[0].id }}\",\n      \"result\": \"{{ $json.toolResult }}\"\n    }\n  ]\n}",`  
        `"options": {`  
          `"responseCode": 200`  
        `}`  
      `},`  
      `"id": "gate-0008",`  
      `"name": "Respond Vapi",`  
      `"type": "n8n-nodes-base.respondToWebhook",`  
      `"typeVersion": 1,`  
      `"position": [1260, 420]`  
    `}`  
  `],`  
  `"connections": {`  
    `"Voice Gateway Webhook": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Gateway Router",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `},`  
    `"Gateway Router": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "ElevenLabs Mint Request",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `],`  
        `[`  
          `{`  
            `"node": "Vapi Tool Sub-Router",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `},`  
    `"ElevenLabs Mint Request": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Respond ElevenLabs",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `},`  
    `"Vapi Tool Sub-Router": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Exec: log_timesheet",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `],`  
        `[`  
          `{`  
            `"node": "Exec: create_change_order",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `},`  
    `"Exec: log_timesheet": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Respond Vapi",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `},`  
    `"Exec: create_change_order": {`  
      `"main": [`  
        `[`  
          `{`  
            `"node": "Respond Vapi",`  
            `"type": "main",`  
            `"index": 0`  
          `}`  
        `]`  
      `]`  
    `}`  
  `}`  
`}`

## **How to Test Each Route**

### **Route A: ElevenLabs Signed URL Request (Mobile App)**

`curl -X POST https://your-n8n-instance.com/webhook/voice/gateway \`  
  `-H "Content-Type: application/json" \`  
  `-d '{`  
    `"action": "mint_elevenlabs_url",`  
    `"agent_id": "YOUR_ELEVENLABS_AGENT_ID"`  
  `}'`

### **Route B: Vapi Tool Call Webhook (Vapi Assistant)**

`curl -X POST https://your-n8n-instance.com/webhook/voice/gateway \`  
  `-H "Content-Type: application/json" \`  
  `-d '{`  
    `"message": {`  
      `"type": "tool-calls",`  
      `"toolCalls": [`  
        `{`  
          `"id": "call_abc123",`  
          `"function": {`  
            `"name": "log_timesheet",`  
            `"arguments": {`  
              `"worker_name": "John Doe",`  
              `"hours_worked": 8`  
            `}`  
          `}`  
        `}`  
      `]`  
    `}`  
  `}'`

---

