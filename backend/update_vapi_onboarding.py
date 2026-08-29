#!/usr/bin/env python3
"""Add first-run onboarding support to backend/vapi_assistant.json (idempotent).

  1. Two new server tools: get_onboarding_status, complete_onboarding.
  2. A 'First-Run Setup (Onboarding)' section appended to the system prompt.

Sync to Vapi afterwards (needs your key):
    VAPI_PRIVATE_KEY=... python3 backend/create_vapi_assistant.py
"""
import json
from pathlib import Path

PATH = Path(__file__).parent / "vapi_assistant.json"
d = json.loads(PATH.read_text())

# ---- 1. tools --------------------------------------------------------------
names = {t.get("function", {}).get("name") for t in d["tools"]}

NEW_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_onboarding_status",
            "description": "Returns whether first-run setup is complete, plus the company name, PM name, preferred daily address, and active worker count.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "server": {"url": "https://n8n2.ordrnow.com/webhook/voice/gateway", "timeoutSeconds": 15},
    },
    {
        "type": "function",
        "function": {
            "name": "complete_onboarding",
            "description": "Completes first-run setup: records company name, PM full name, how the PM wants to be addressed daily, and the worker list (name, trade, hourly rate). Call ONLY after gathering all fields from the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "Company name"},
                    "pm_name": {"type": "string", "description": "Project manager full name"},
                    "preferred_name": {"type": "string", "description": "How the PM wants to be addressed every day, e.g. Dave or boss"},
                    "workers": {
                        "type": "array",
                        "description": "Crew members: name, trade, hourly rate",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Full worker name"},
                                "trade": {"type": "string", "description": "Trade, e.g. Framer, Electrician, Labourer"},
                                "hourly_rate": {"type": "number", "description": "Hourly rate in dollars"},
                            },
                            "required": ["name", "hourly_rate"],
                        },
                    },
                },
                "required": ["company_name", "pm_name", "preferred_name", "workers"],
            },
        },
        "server": {"url": "https://n8n2.ordrnow.com/webhook/voice/gateway", "timeoutSeconds": 15},
    },
]

for t in NEW_TOOLS:
    if t["function"]["name"] not in names:
        d["tools"].append(t)
        names.add(t["function"]["name"])

# ---- 2. system prompt ------------------------------------------------------
MARKER = "# First-Run Setup (Onboarding)"
SECTION = (
    "\n"
    "# First-Run Setup (Onboarding)\n"
    "- At the start of a conversation, if you do not already know whether setup is\n"
    "  complete, call `get_onboarding_status` once.\n"
    "- If setup is NOT complete, run the onboarding flow BEFORE any other work:\n"
    "  1. Ask for the company name.\n"
    "  2. Ask for the project manager's full name.\n"
    "  3. Ask how the PM wants to be addressed every day (e.g. \"Dave\" or \"boss\").\n"
    "  4. Ask for each worker's name, trade, and hourly rate, one at a time\n"
    "     (ask \"anyone else?\" until they say no).\n"
    "  5. When you have everything, call `complete_onboarding` with all fields\n"
    "     (workers as an array), then confirm: \"All set - everything is registered.\"\n"
    "- Keep each question short (10-15 words). Never call `complete_onboarding`\n"
    "  before you have company name, PM name, preferred address, and the worker\n"
    "  list (an empty workers array is allowed only if they have no crew yet).\n"
    "- If setup IS complete, never re-run onboarding unless the user asks to\n"
    "  change company details; use `add_worker` for new crew members.\n"
)

if MARKER not in d["systemPrompt"]:
    d["systemPrompt"] = d["systemPrompt"].rstrip() + SECTION

PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("vapi_assistant.json updated:")
print("  tools:", len(d["tools"]), "->", [t["function"]["name"] for t in d["tools"]][-2:])
print("  onboarding prompt section:", "present" if MARKER in d["systemPrompt"] else "MISSING")
