#!/usr/bin/env python3
"""Read-back verification of the deployed Vapi assistant + its tool routing.

Assertion that matters: EVERY tool on the assistant must carry its own
server.url pointing at the n8n gateway. A tool without one silently inherits
the assistant-level serverUrl (the call-start hook endpoint), so its calls 404
and Vapi reports "No result returned" - which reads to the model like a
not-found result. This script is the read-back half of that guard; the
deployer (backend/create_vapi_assistant.py) refuses to deploy such a tool.

Usage:  python3 qa/verify_vapi_tools.py [--base https://n8n2.ordrnow.com/webhook/voice/gateway]
Exit 0 = all tools routed correctly; exit 1 = at least one tool misrouted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ASSISTANT_NAME = "Ireh Construction PM Assistant"
DEFAULT_BASE = "https://n8n2.ordrnow.com/webhook/voice/gateway"


def api_key() -> str:
    key = os.environ.get("VAPI_PRIVATE_KEY")
    if key:
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("VAPI_PRIVATE_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("error: VAPI_PRIVATE_KEY not found (env or ~/.hermes/.env)")


def get(path: str):
    req = urllib.request.Request("https://api.vapi.ai" + path)
    req.add_header("Authorization", "Bearer " + api_key())
    req.add_header("User-Agent", "curl/8.5.0")
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE, help="expected tool server URL")
    args = ap.parse_args()

    assistants = [a for a in get("/assistant") if a.get("name") == ASSISTANT_NAME]
    if not assistants:
        sys.exit(f"error: assistant '{ASSISTANT_NAME}' not found")
    assistant = get(f"/assistant/{assistants[0]['id']}")
    tool_ids = assistant.get("model", {}).get("toolIds", [])

    tools = get("/tool?limit=200")
    tools = tools if isinstance(tools, list) else tools.get("results", [])
    by_id = {t["id"]: t for t in tools if t.get("id")}

    bad, unknown, ok = [], [], 0
    print(f"assistant: {assistant['id']}  tools: {len(tool_ids)}")
    for tid in tool_ids:
        t = by_id.get(tid)
        if t is None:
            unknown.append(tid)
            continue
        name = (t.get("function") or {}).get("name") or t.get("name") or tid
        url = (t.get("server") or {}).get("url")
        if url == args.base:
            ok += 1
        else:
            bad.append((name, url or "NO server.url -> inherits assistant serverUrl"))
    print(f"  routed correctly: {ok}/{len(tool_ids)}")
    for name, url in bad:
        print(f"  MISROUTED: {name:<28} {url}")
    for tid in unknown:
        print(f"  UNRESOLVED tool id: {tid}")

    if bad or unknown:
        print("\nFAIL - fix backend/vapi_assistant.json and re-run "
              "backend/create_vapi_assistant.py")
        return 1
    print("\nOK - every tool has its own gateway URL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
