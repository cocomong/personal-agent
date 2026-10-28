#!/usr/bin/env bash
# deploy_voice_context.sh — ONE approval for the whole voice-context feature.
#
# Order: pre-dump -> migration 0039 + verify 0040 -> import/activate
# vapi-assistant-hook (+ retention workflow) -> restart -> Vapi assistant prompt
# -> tool-routing read-back -> E2E probe -> SCHEMA.md regen.
#
# Nothing here touches serverMessages: capture rides Vapi's default set, which
# already delivers end-of-call-report to the hook.
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root
HOST=ubuntu@n8n2.ordrnow.com
TS=$(date +%Y%m%d_%H%M%S)

echo "== 1. pre-deploy dump =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-postgres-1 pg_dump -U postgres -d postgres > /home/ubuntu/backups/pm/pre-vctx-${TS}.sql && ls -lh /home/ubuntu/backups/pm/pre-vctx-${TS}.sql | awk '{print \$5}'"

echo "== 2. migration 0039 + verify 0040 =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q" < db/0039_voice_context.sql && echo "0039 OK"
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q" < db/0040_voice_context_verify.sql && echo "0040 verify OK"
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-postgres-1 psql -U postgres -d postgres -At -c \"SELECT count(*) FROM voice_calls\""

echo "== 3. deploy hook + retention workflow =="
scp -q backend/n8n/workflows/vapi-assistant-hook.json backend/n8n/workflows/voice-context-retention.json "$HOST":/tmp/
ssh -o ConnectTimeout=10 "$HOST" "sudo cp /tmp/vapi-assistant-hook.json /tmp/voice-context-retention.json /home/ubuntu/n8n-compose/local-files/ && cd /home/ubuntu/n8n-compose && \
  sudo docker exec n8n-compose-n8n-1 n8n import:workflow --input=/files/vapi-assistant-hook.json 2>&1 | tail -1 && \
  sudo docker exec n8n-compose-n8n-1 n8n import:workflow --input=/files/voice-context-retention.json 2>&1 | tail -1 && \
  sudo docker exec n8n-compose-n8n-1 n8n update:workflow --id=vapi-assistant-hook-001 --active=true && \
  sudo docker exec n8n-compose-n8n-1 n8n update:workflow --id=voice-context-retention-001 --active=true && \
  echo 'restart...' && sudo docker restart n8n-compose-n8n-1 >/dev/null && sleep 18 && curl -s -o /dev/null -w 'healthz %{http_code}\n' https://n8n2.ordrnow.com/healthz"

echo "== 3b. verify the LIVE hook carries the new nodes (import can succeed on a stale file) =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-n8n-1 n8n export:workflow --id=vapi-assistant-hook-001 --output=/tmp/hook-live.json >/dev/null 2>&1; sudo docker exec n8n-compose-n8n-1 cat /tmp/hook-live.json" > /tmp/hook-live.json
python3 - <<'PY'
import json
w = json.load(open('/tmp/hook-live.json'))[0]
names = [n['name'] for n in w['nodes']]
need = {'Route By Event Type', 'Extract Call Report', 'Exec: upsert_call_report',
        'Exec: start_call_row', 'Respond Report (ok)', 'Respond Event (ignored)'}
missing = need - set(names)
if missing:
    raise SystemExit(f"FAIL: live hook missing {sorted(missing)}")
print(f"live hook nodes: {len(names)} (new nodes present)")
PY

echo "== 4. Vapi assistant: prompt section (recent_context) =="
python3 backend/create_vapi_assistant.py

echo "== 5. tool routing read-back =="
python3 qa/verify_vapi_tools.py

echo "== 6. E2E probe (start -> report -> re-delivery -> context -> ignored event -> cleanup) =="
python3 qa/voice_context_probe.py

echo "== 7. SCHEMA.md regen (0039 voice_calls) =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -tA -q -v ON_ERROR_STOP=1" < qa/schema_extract.sql > /tmp/schema_dump.txt
python3 qa/schema_regen.py /tmp/schema_dump.txt > doc/SCHEMA.md
grep -c "voice_calls" doc/SCHEMA.md

echo "ALL DONE — commit the regenerated SCHEMA.md."
