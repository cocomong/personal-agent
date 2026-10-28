#!/usr/bin/env python3
"""E2E probe for voice-call context (run AFTER deploy).

Exercises the real chain over HTTPS, no LLM and no Vapi credits:
  1. call start  -> pending row created, call_ref echoed in assistantOverrides
  2. report      -> row flips to 'reported' with transcript/ended_reason/duration
  3. re-delivery -> idempotent, still one row
  4. next start  -> recent_context carries the transcript tail
  5. ignored event (status-update) -> 200, no DB write
  6. cleanup     -> probe rows deleted so the PM's next call never inherits QA text

Run: python3 qa/voice_context_probe.py
"""
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOST = "ubuntu@n8n2.ordrnow.com"
HOOK = "https://n8n2.ordrnow.com/webhook/vapi/assistant-hook"
MARKER = "QA voice context probe"
SIG_HELPER = (
    "import hmac,hashlib,base64,sys;"
    "print(base64.urlsafe_b64encode("
    "hmac.new(sys.argv[1].encode(),sys.argv[2].encode(),hashlib.sha256).digest()"
    ").decode().rstrip('='))"
)

failures = []


def check(cond, msg, detail=""):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg} {detail}")
        failures.append(msg)


def ssh(cmd: str) -> str:
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=10", HOST, cmd],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ssh failed: {r.stderr[:400]}")
    return r.stdout.strip()


def db(q: str) -> str:
    return ssh(f'sudo docker exec n8n-compose-postgres-1 psql -U postgres -d postgres -At -c {json.dumps(q)}')


def mint_token(uid: str) -> str:
    payload = json.dumps({"uid": uid, "exp": int(time.time()) + 3600}, separators=(",", ":"))
    pb64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = ssh(f"cd /home/ubuntu/n8n-compose && SECRET=$(sudo docker exec "
              f"n8n-compose-n8n-1 printenv AUTH_TOKEN_SECRET) && "
              f"python3 -c {json.dumps(SIG_HELPER)} \"$SECRET\" \"{pb64}\"")
    return f"v1.{pb64}.{sig}"


def post(body: dict, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json", "User-Agent": "curl/8.5.0"}
    if token:
        headers["X-User-Token"] = token
    req = urllib.request.Request(HOOK, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read() or b"{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        return e.code, {"error": (e.read() or b"").decode()[:200]}


def main() -> int:
    uid = db("SELECT id FROM users ORDER BY created_at LIMIT 1")
    if not uid:
        print("no user row; using company-1 fallback (uid omitted)")
    token = mint_token(uid) if uid else None

    db(f"DELETE FROM voice_calls WHERE vapi_call_id LIKE 'qa-probe-%' OR transcript LIKE '%{MARKER}%'")
    call_id = f"qa-probe-{int(time.time())}"

    try:
        print("1) call start")
        status, body = post({}, token)
        check(status == 200, f"hook answers 200 (got {status})")
        ov = body.get("assistantOverrides") or {}
        vv = ov.get("variableValues") or {}
        ref = vv.get("call_ref")
        check(bool(ref), "call_ref handed back to Vapi")
        check("recent_context" in vv, "recent_context key present (empty, never a literal placeholder)")
        check(vv.get("company_name") == "Ireh Construction", "company variables unchanged",
              str(vv.get("company_name")))
        check(bool(ov.get("firstMessage")), "greeting unchanged")
        check(db(f"SELECT status FROM voice_calls WHERE call_ref = '{ref}'") == "pending",
              "pending row written for call_ref")

        print("\n2) end-of-call-report")
        started = "2026-10-28T05:00:00.000Z"
        ended = "2026-10-28T05:00:12.000Z"
        report = {"message": {
            "type": "end-of-call-report",
            "endedReason": "customer-ended-call",
            "call": {"id": call_id, "startedAt": started, "endedAt": ended,
                     "assistantOverrides": {"variableValues": {"call_ref": ref}}},
            "artifact": {"transcript": f"AI: inventory check. User: {MARKER} - switch Oakridge to compact.",
                         "messages": [{"role": "user", "message": f"{MARKER}"}]},
        }}
        status, body = post(report, token)
        check(status == 200 and body.get("ok") is True, f"report accepted (got {status} {body})")
        row = db(f"SELECT status || '|' || coalesce(vapi_call_id,'') || '|' || "
                 f"coalesce(ended_reason,'') || '|' || coalesce(duration_seconds::text,'') "
                 f"FROM voice_calls WHERE call_ref = '{ref}'")
        check(row.startswith("reported|" + call_id), "row flipped to reported and matched by call_ref", row)
        check("customer-ended-call" in row, "ended_reason stored", row)
        check(abs(float(row.split("|")[3] or 0) - 12.0) < 0.5, "duration derived and stored", row)

        print("\n3) re-delivery")
        before = db("SELECT count(*) FROM voice_calls")
        post(report, token)
        after = db("SELECT count(*) FROM voice_calls")
        check(before == after, f"duplicate report does not create a row ({before} -> {after})")

        print("\n4) next call start sees the context")
        status, body = post({}, token)
        vv = (body.get("assistantOverrides") or {}).get("variableValues") or {}
        ctx = vv.get("recent_context") or ""
        check(MARKER in ctx, "recent_context carries the transcript tail", ctx[:120])
        check("customer ended call" in ctx, "ended reason humanised", ctx[:120])
        check(len(ctx) < 1100, f"context stays bounded ({len(ctx)} chars)")

        print("\n5) ignored Vapi event")
        before = db("SELECT count(*) FROM voice_calls")
        status, body = post({"message": {"type": "status-update", "status": "ended",
                                        "call": {"id": call_id}}}, token)
        after = db("SELECT count(*) FROM voice_calls")
        check(status == 200 and body.get("ignored") is True, f"event answered without work ({body})")
        check(before == after, "no row written for a non-report event")
    finally:
        print("\n6) cleanup")
        db(f"DELETE FROM voice_calls WHERE vapi_call_id LIKE 'qa-probe-%' OR transcript LIKE '%{MARKER}%'")
        left = db(f"SELECT count(*) FROM voice_calls WHERE transcript LIKE '%{MARKER}%'")
        check(left == "0", "probe rows removed (the PM's next call cannot inherit QA text)")

    print()
    if failures:
        print(f"{len(failures)} FAILURES")
        return 1
    print("probe green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
