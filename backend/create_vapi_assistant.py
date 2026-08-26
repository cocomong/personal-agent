#!/usr/bin/env python3
"""Create or update the Vapi assistant for the Construction PM app.

Reads `backend/vapi_assistant.json` — the human-readable assistant payload
(model, voice, system prompt, 17 server tools -> n8n gateway) — and adapts it
to the Vapi API's modern shape:

  * `systemPrompt`       -> `model.messages[0].content` (system role)
  * `tools`              -> upserted as standalone Vapi "tool" resources,
                            referenced by `model.toolIds`
  * `transcriber`        -> explicit provider (deepgram) when not set

Idempotent: tools are matched by `function.name`, the assistant by `name`;
safe to re-run after editing the JSON.

Prints the assistant id + public key for `mobile-flutter/lib/config.dart`.

API key resolution (never printed):
  1. $VAPI_PRIVATE_KEY env var
  2. ~/.openclaw/agents/vapi/agent/SOUL.md (Dave's Vapi agent home)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.vapi.ai"
HERE = Path(__file__).resolve().parent
ASSISTANT_JSON = HERE / "vapi_assistant.json"


def api_key() -> str:
    key = os.environ.get("VAPI_PRIVATE_KEY")
    if key:
        return key
    soul = Path.home() / ".openclaw" / "agents" / "vapi" / "agent" / "SOUL.md"
    if soul.exists():
        m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", soul.read_text())
        if m:
            return m.group(0)
    sys.exit("error: VAPI_PRIVATE_KEY not set and no key found in SOUL.md")


def request(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Authorization", "Bearer " + api_key())
    req.add_header("Content-Type", "application/json")
    # Cloudflare bans default urllib UA (HTTP 403 / error 1010); curl works.
    req.add_header("User-Agent", "curl/8.5.0")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=45) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 429:  # rate limit — retry with backoff, then give up
            retries = int(e.headers.get("Retry-After", "3") or 3)
            print(f"  rate-limited, waiting {retries}s...")
            time.sleep(min(retries, 20))
            return request(method, path, body)
        detail = e.read().decode(errors="replace")[:1000]
        sys.exit(f"error: Vapi API {method} {path} -> HTTP {e.code}: {detail}")


def upsert_tools(tools: list[dict]) -> list[str]:
    """Create-or-update each server tool; return their ids in order."""
    existing = {t.get("function", {}).get("name"): t["id"]
                for t in request("GET", "/tool") if t.get("id")}
    ids: list[str] = []
    for tool in tools:
        fn_name = tool["function"]["name"]
        if fn_name in existing:
            request("PATCH", f"/tool/{existing[fn_name]}", tool)
            ids.append(existing[fn_name])
            print(f"  tool  updated: {fn_name}")
        else:
            created = request("POST", "/tool", tool)
            ids.append(created["id"])
            print(f"  tool  created: {fn_name}")
        time.sleep(0.5)  # stay under the API rate limit
    return ids


def main() -> None:
    payload = json.loads(ASSISTANT_JSON.read_text())
    tools = payload.pop("tools")
    system_prompt = payload.pop("systemPrompt")
    name = payload["name"]
    assert len(tools) == 19, f"expected 19 tools, got {len(tools)}"

    payload.setdefault("transcriber", {})
    payload["transcriber"].setdefault("provider", "deepgram")

    print("upserting tools...")
    tool_ids = upsert_tools(tools)

    payload["model"]["messages"] = [{"role": "system", "content": system_prompt}]
    payload["model"]["toolIds"] = tool_ids

    existing = [a for a in request("GET", "/assistant") if a.get("name") == name]
    if existing:
        assistant = request("PATCH", f"/assistant/{existing[0]['id']}", payload)
        action = "updated"
    else:
        assistant = request("POST", "/assistant", payload)
        action = "created"

    print(f"assistant {action}: {assistant['id']}")
    print(f"  name:      {assistant.get('name')}")
    print(f"  model:     {assistant.get('model', {}).get('provider')} "
          f"{assistant.get('model', {}).get('model')}")
    print(f"  tools:     {len(assistant.get('model', {}).get('toolIds', []))}")
    print(f"  publicKey: {assistant.get('publicKey')}")


if __name__ == "__main__":
    main()
