#!/usr/bin/env python3
"""Text-chat battery: scripted PM questions through the app's own chat path, with tool-level truth.

Two layers, because they answer different questions:

  Layer A (app path) - POST {root}/webhook/chat, exactly what
    mobile-flutter/lib/session/chat_controller.dart sends. Proves the user-visible answer:
    the turn returned, the text is a real answer, and it never carries the failure
    boilerplate that hid four dead tools for three days ("No result returned...").

  Layer B (tool truth) - POST api.vapi.ai/chat with the same assistant, reading the tool-call
    frames. The n8n proxy returns only the final text, so a tool that 404s still produces a
    plausible-sounding reply. Layer B asserts WHICH tools fired and whether they returned
    anything at all. This is the half that would have caught the 2026-09-10 incident on its own.

  Layer C (--side-effects, off by default) - row counts in the app DB before and after, so a
    read-only turn is proven to have changed nothing.

READ-ONLY BY DESIGN. Every case here uses a read-only tool. The write tools on this assistant
(send_customer_invoice, send_invoice_to_phone, send_payment_receipt, record_payment, run_payroll,
create_*, add_worker, update_*, complete_onboarding, set_briefing_time, lookup_or_create_customer)
are deliberately NOT exercised: they send real email and SMS to real customers and write live
rows. Add them only against a dedicated test company, never in a nightly run.

Fixtures are read from the live DB (project/customer names), so the battery does not rot when
the data changes; it falls back to the last known values if ssh is unavailable.

Usage:
  python3 qa/chat_text_battery.py                    # layer A + B, fixtures from the DB
  python3 qa/chat_text_battery.py --layer app        # only the app's own path
  python3 qa/chat_text_battery.py --side-effects     # + DB before/after (needs ssh)
  python3 qa/chat_text_battery.py --root https://n8n2.ordrnow.com --ssh ubuntu@n8n2.ordrnow.com

Exit 0 = every check passed; exit 1 = at least one failed.

NOTE (Step 3): with no X-User-Token the workflow resolves uid=null and falls back to company 1,
so this battery needs no secret - and the endpoint currently answers as company 1 for anyone who
has the URL. When Step 3 lands, this battery must gain a token-path case and a
"a foreign/absent token cannot reach another company" case.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ASSISTANT_ID = "67e2850c-1028-484d-bf52-d948826b2a7e"
DEFAULT_ROOT = "https://n8n2.ordrnow.com"
DEFAULT_SSH = "ubuntu@n8n2.ordrnow.com"
UA = "curl/8.5.0"  # Cloudflare in front of api.vapi.ai 403s urllib's default User-Agent (code 1010)

# The failure signature of a misrouted tool: Vapi substitutes this text when a tool call fails,
# and the model then reads it as "the record does not exist".
FORBIDDEN = (
    "no result returned",
    "tool call failed",
    "internal server error",
    "unexpected error",
    "network error",
)
MONEY = re.compile(r"\$\s?\d[\d,]*")
HONESTY = re.compile(
    r"no (?:project|estimate|customer|record|invoice|match|such)|"
    r"not find|didn't find|did not find|don't have|do not have|"
    r"nothing (?:found|on file|by that)|unable to find|not in (?:the )?(?:system|records)",
    re.IGNORECASE,
)


def env_key() -> str:
    key = os.environ.get("VAPI_PRIVATE_KEY")
    if key:
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("VAPI_PRIVATE_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("error: VAPI_PRIVATE_KEY not found (env or ~/.hermes/.env)")


def sql(ssh: str, statement: str, single: bool = True):
    """Run SQL over ssh -> docker psql (-tA), the same path qa/e2e_estimate_approval.py uses.

    ON_ERROR_STOP is set on purpose: without it psql prints an ERROR and still exits 0, so a
    broken statement looks exactly like an empty result. That is how the first version of this
    battery's side-effect check passed while comparing two empty strings.
    """
    cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", ssh,
        "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -t -A -q "
        "-v ON_ERROR_STOP=1",
    ]
    proc = subprocess.run(cmd, input=statement.encode(), capture_output=True, timeout=120)
    stderr = proc.stderr.decode()
    if proc.returncode != 0 or "ERROR" in stderr:
        raise RuntimeError("psql failed: " + (stderr.strip() or proc.stdout.decode())[:200])
    lines = [line.strip() for line in proc.stdout.decode().splitlines() if line.strip()]
    return (lines[0] if lines else "") if single else lines


# Fingerprint of the app's data: counts plus money sums plus the newest rows. Comparing counts
# alone would miss a read-only turn that *modified* a row (an invoice flipping to paid, say).
DB_FINGERPRINT = """
    select (select count(*) from projects) || ',' ||
           (select count(*) from customers) || ',' ||
           (select count(*) from estimates) || ',' ||
           (select count(*) from invoices) || ',' ||
           (select count(*) from approval_log) || ',' ||
           (select coalesce(sum(allocated_amount), 0)::text from estimates) || ',' ||
           (select coalesce(sum(amount), 0)::text from payments) || ',' ||
           (select coalesce(sum(amount_due), 0)::text from invoices) || ',' ||
           (select coalesce(sum(net_amount), 0)::text from invoices) || ',' ||
           (select count(*) from invoices where email_sent_at is not null) || ',' ||
           (select count(*) from payments)
"""
DB_FINGERPRINT_FIELDS = 11  # fields a real snapshot must carry: projects,customers,estimates,invoices,
# approvals, estimate$, payments$, amount_due$, net_amount$, emailed invoices, payments


# --------------------------------------------------------------------------- turns

def app_turn(root: str, text: str, chat_id: str | None, timeout: int = 180) -> dict:
    """One typed turn through the app's own endpoint (n8n chat proxy -> Vapi /chat)."""
    body = {"input": text}
    if chat_id:
        body["chatId"] = chat_id
    request = urllib.request.Request(
        f"{root.rstrip('/')}/webhook/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA, "Accept": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload, status = json.load(response), response.status
    except urllib.error.HTTPError as exc:
        payload, status = {"error": exc.read(300).decode("utf-8", "replace")}, exc.code
    except Exception as exc:  # noqa: BLE001 - a dead endpoint is a failed check, not a crash
        payload, status = {"error": f"{type(exc).__name__}: {exc}"}, 0
    return {
        "status": status,
        "seconds": round(time.monotonic() - started, 1),
        "reply": str(payload.get("reply") or payload.get("error") or payload.get("raw_error") or ""),
        "chat_id": payload.get("chatId") or chat_id,
    }


def vapi_turn(assistant_id: str, text: str, timeout: int = 180) -> dict:
    """One turn straight from Vapi, where the tool-call frames are still visible."""
    request = urllib.request.Request(
        "https://api.vapi.ai/chat",
        data=json.dumps({"assistantId": assistant_id, "input": text}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + env_key(),
            "User-Agent": UA,
            "Accept": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except Exception as exc:  # noqa: BLE001
        return {"seconds": round(time.monotonic() - started, 1), "tools": [], "results": [],
                "final": "", "error": f"{type(exc).__name__}: {exc}"}

    tools, results, final = [], [], ""
    for message in payload.get("output") or []:
        calls = message.get("toolCalls") or message.get("tool_calls") or []
        for call in calls:
            name = (call.get("function") or {}).get("name") or call.get("name")
            if name:
                tools.append(str(name))
        if message.get("role") == "tool":
            content = message.get("content")
            text_out = content if isinstance(content, str) else json.dumps(content)[:400]
            results.append(str(text_out))
        if message.get("role") == "assistant":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                final = content.strip()
            elif isinstance(content, list):
                joined = " ".join(p.get("text", "") for p in content if isinstance(p, dict)).strip()
                if joined:
                    final = joined
    return {"seconds": round(time.monotonic() - started, 1), "tools": tools, "results": results,
            "final": final, "error": ""}


# --------------------------------------------------------------------------- cases

@dataclass
class Case:
    name: str
    utterance: str
    why: str
    tools: set[str] = field(default_factory=set)     # acceptable tool names (layer B)
    must_all: tuple[str, ...] = ()                   # regexes that all must appear in the reply
    must_any: tuple[str, ...] = ()                   # at least one must appear
    forbid: tuple[str, ...] = ()                     # regexes that must not appear
    honest: bool = False                             # must read like a not-found, with no money


def _money_regex(digits: str) -> str:
    """270000 -> a regex that matches how a person writes it: 270000, 270,000, $270,000."""
    clean = re.sub(r"\D", "", digits)
    if not clean:
        return r"\$\s?\d[\d,]*"
    return r"\$?\s?" + re.sub(r"(?<=\d)(?=(\d{3})+$)", r"[,\\s]?", clean)


def build_cases(fixtures: dict) -> list[Case]:
    project = fixtures.get("project") or "5650 Camino"
    project2 = fixtures.get("project2") or "Oakridge Build"
    customer = fixtures.get("customer") or "David Tam"
    # The estimate case targets the project that actually has estimate lines, so it can assert a
    # real figure rather than just the word "approved".
    estimated = fixtures.get("estimated_project") or project
    figure = _money_regex(fixtures.get("estimate_total", ""))
    return [
        Case("projects_list", "list my projects",
             "the most basic read path: the model must reach the projects tool",
             tools={"list_projects", "get_dashboard_summary"},
             must_any=(re.escape(project), re.escape(project2))),
        Case("estimate_status", f"estimate status for {estimated}",
             "the tool that was silently dead until 2026-09-10",
             tools={"list_estimate_status"},
             must_any=(figure, r"approved")),
        Case("customer_lookup", f"do we have a customer called {customer}?",
             "find_customer - the second tool that was silently dead",
             tools={"find_customer"},
             must_any=(re.escape(customer),)),
        Case("honest_missing", "what is the estimate status for 9999 Nowhere Avenue?",
             "a question about nothing must not produce invented money",
             tools={"list_estimate_status", "get_project_statement", "find_customer", "list_projects"},
             forbid=(r"\$\s?\d",),
             honest=True),
        Case("dashboard", "show me the financial dashboard for all projects",
             "aggregate read path (GET_DASHBOARD_SUMMARY)",
             tools={"get_dashboard_summary"}),
        Case("invoices", "list the invoices",
             "invoice list + payment status",
             tools={"list_invoices"},
             must_any=(r"INV-", r"\d{3,}")),
        Case("schedule", "what is on the schedule?",
             "schedule read path",
             tools={"get_schedule", "list_projects"}),
        Case("payroll", "give me the latest payroll summary",
             "payroll read path (no payroll run is created by reading)",
             tools={"get_payroll_summary"}),
        Case("setup_status", "is my setup complete?",
             "onboarding status read path",
             tools={"get_onboarding_status"}),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT, help="n8n base URL")
    ap.add_argument("--assistant", default=ASSISTANT_ID)
    ap.add_argument("--ssh", default=DEFAULT_SSH)
    ap.add_argument("--layer", choices=("app", "vapi", "both"), default="both")
    ap.add_argument("--side-effects", action="store_true",
                    help="count app-DB rows before and after: read-only turns must change nothing")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    checks: list[tuple[bool, str, str]] = []

    def check(ok: bool, label: str, detail: str = "") -> bool:
        checks.append((ok, label, detail))
        print(f"  {'ok  ' if ok else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
        return ok

    # ---------------------------------------------------------------- fixtures (grounded, not hardcoded)
    fixtures, fixture_source = {}, "built-in fallback"
    try:
        rows = str(sql(args.ssh, """
            select 'project=' || coalesce((select title from projects order by id limit 1), '')
                || '|project2=' || coalesce((select title from projects order by id offset 1 limit 1), '')
                || '|customer=' || coalesce((select name from customers order by id limit 1), '')
                || '|estimated_project=' || coalesce((select p.title from projects p
                        join estimates e on e.project_id = p.id
                        group by p.title order by sum(e.allocated_amount) desc limit 1), '')
                || '|estimate_total=' || coalesce((select trunc(sum(e.allocated_amount))::bigint::text
                        from estimates e join projects p on p.id = e.project_id
                        where p.title = (select p2.title from projects p2
                                join estimates e2 on e2.project_id = p2.id
                                group by p2.title order by sum(e2.allocated_amount) desc limit 1)), '')
        """))
        for pair in rows.split("|"):
            key, _, value = pair.partition("=")
            if value.strip():
                fixtures[key.strip()] = value.strip()
        fixture_source = f"live DB via {args.ssh}"
    except Exception as exc:  # noqa: BLE001
        fixture_source = f"built-in fallback ({type(exc).__name__})"
    print(f"fixtures: {fixture_source}  {fixtures or '(none)'}")

    cases = build_cases(fixtures)
    before = None
    if args.side_effects:
        try:
            before = str(sql(args.ssh, DB_FINGERPRINT))
            print(f"app fingerprint before: {before}")
        except Exception as exc:  # noqa: BLE001
            print(f"  (side-effect baseline unavailable: {type(exc).__name__}: {exc})")

    # ---------------------------------------------------------------- layer A: the app's own path
    chain_id: str | None = None
    if args.layer in ("app", "both"):
        print(f"\nlayer A — the app's chat path ({args.root}/webhook/chat)")
        for case in cases:
            turn = app_turn(args.root, case.utterance, None, args.timeout)
            reply = turn["reply"]
            print(f"\n  Q: {case.utterance}")
            print(f"     [{turn['status']} in {turn['seconds']}s] {reply[:240]}")
            check(turn["status"] == 200, f"{case.name}: the turn returned 200",
                  f"status={turn['status']}")
            check(bool(reply.strip()), f"{case.name}: the reply is not empty")
            hit = next((marker for marker in FORBIDDEN if marker in reply.lower()), "")
            check(not hit, f"{case.name}: no failure boilerplate in the reply",
                  f"found {hit!r}" if hit else "")
            for pattern in case.forbid:
                check(not re.search(pattern, reply), f"{case.name}: reply must not match {pattern!r}",
                      reply[:120] if re.search(pattern, reply) else "")
            if case.must_all:
                missing = [p for p in case.must_all if not re.search(p, reply, re.IGNORECASE)]
                check(not missing, f"{case.name}: reply carries the expected content", f"missing {missing}")
            if case.must_any:
                present = [p for p in case.must_any if re.search(p, reply, re.IGNORECASE)]
                check(bool(present), f"{case.name}: reply carries the expected content",
                      f"matched {present}" if present else f"none of {list(case.must_any)}")
            if case.honest:
                check(bool(HONESTY.search(reply)), f"{case.name}: says it found nothing, rather than inventing")

        # Multi-turn: the app carries the chain through chatId, so context must survive a turn.
        # Target the project that HAS estimate lines — a follow-up asking "how much was that?"
        # cannot be answered for a project with none, and a nightly gate must not be flaky about
        # which project the DB happens to return first.
        print("\n  multi-turn continuity (chatId chain)")
        anchor_project = fixtures.get("estimated_project") or fixtures.get("project") or "5650 Camino"
        figure_regex = _money_regex(fixtures.get("estimate_total", "")) if fixtures.get("estimate_total") else MONEY.pattern
        first = app_turn(args.root, f"estimate status for {anchor_project}", None, args.timeout)
        chain_id = first["chat_id"]
        check(bool(chain_id), "multi-turn: a chat id came back", f"chatId={str(chain_id)[:12]}")
        second = app_turn(args.root, "and how much was that again?", chain_id, args.timeout)
        print(f"     Q: and how much was that again?  ->  [{second['status']}] {second['reply'][:200]}")
        check(second["status"] == 200 and bool(second["reply"].strip()),
              "multi-turn: the follow-up answered")
        check(bool(re.search(figure_regex, second["reply"])),
              "multi-turn: the follow-up resolved the reference (the same figure came back)",
              f"reply={second['reply'][:120]!r}")

    # ---------------------------------------------------------------- layer B: tool truth
    if args.layer in ("vapi", "both"):
        print("\nlayer B — which tools actually fired (Vapi /chat frames)")
        for case in cases:
            turn = vapi_turn(args.assistant, case.utterance, args.timeout)
            called = set(turn["tools"])
            print(f"\n  Q: {case.utterance}")
            print(f"     [{turn['seconds']}s] tools={sorted(called) or 'none'}")
            if turn["error"]:
                check(False, f"{case.name}: the Vapi turn completed", turn["error"][:120])
                continue
            check(bool(turn["final"]), f"{case.name}: the turn produced an answer")
            if case.tools:
                check(bool(called & case.tools), f"{case.name}: called one of the expected tools",
                      f"called={sorted(called)} expected one of {sorted(case.tools)}")
            failed = [r for r in turn["results"]
                      if not r.strip() or any(m in r.lower() for m in FORBIDDEN)]
            check(not failed, f"{case.name}: every tool result came back with content",
                  f"{len(failed)} empty/failed result(s): {failed[:1]}")

    # ---------------------------------------------------------------- layer C: nothing changed
    if args.side_effects:
        print("\nlayer C — read-only turns must not change the app database")
        if before is None:
            check(False, "side-effects: a baseline was captured")
        else:
            # A snapshot that came back empty is not evidence of anything: assert it looks like a
            # real fingerprint before comparing. (The first version of this check compared two
            # empty strings and passed — psql reports a bad statement without failing.)
            check(len(before.split(",")) == DB_FINGERPRINT_FIELDS,
                  "side-effects: the baseline is a real fingerprint",
                  f"{len(before.split(','))} of {DB_FINGERPRINT_FIELDS} fields: {before!r}")
            try:
                after = str(sql(args.ssh, DB_FINGERPRINT))
                print(f"     before: {before}\n     after : {after}")
                check(len(after.split(",")) == DB_FINGERPRINT_FIELDS,
                      "side-effects: the after-snapshot is a real fingerprint", after)
                check(before == after, "side-effects: no row was created or changed",
                      f"{before} -> {after}")
            except Exception as exc:  # noqa: BLE001
                check(False, "side-effects: an after-snapshot was captured", str(exc)[:120])

    failed = [c for c in checks if not c[0]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    for _ok, label, detail in failed:
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
    if failed:
        print("\nFAIL - a text turn or a tool call is broken; the failure mode to look for first is "
              "a tool without its own server.url (see qa/verify_vapi_tools.py)")
        return 1
    print("\nOK - every scripted turn answered and called the tools it should")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
