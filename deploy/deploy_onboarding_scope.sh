#!/usr/bin/env bash
# deploy_onboarding_scope.sh - deploy the per-user company scope change.
#
# Order: pre-dump -> migrations 0041/0042 -> import+activate hook & gateway ->
# restart -> verify the LIVE exports carry the new nodes -> live checks.
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=ubuntu@n8n2.ordrnow.com
TS=$(date +%Y%m%d_%H%M%S)
# Workflow ids come from the files (the gateway id is not a slug).
HOOK_ID=$(python3 -c "import json;print(json.load(open('backend/n8n/workflows/vapi-assistant-hook.json'))['id'])")
GW_ID=$(python3 -c "import json;print(json.load(open('backend/n8n/workflows/voice-gateway.json'))['id'])")

echo "== 1. pre-deploy dump =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-postgres-1 pg_dump -U postgres -d postgres > /home/ubuntu/backups/pm/pre-onboard-${TS}.sql && ls -lh /home/ubuntu/backups/pm/pre-onboard-${TS}.sql | awk '{print \$5}'"

echo "== 2. migrations =="
for f in db/0041_owner_backfill.sql db/0042_company_identity_defaults.sql; do
  ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q" < "$f"
  echo "  $f OK"
done

echo "== 3. deploy hook + gateway =="
scp -q backend/n8n/workflows/vapi-assistant-hook.json backend/n8n/workflows/voice-gateway.json "$HOST":/tmp/
ssh -o ConnectTimeout=10 "$HOST" "sudo cp /tmp/vapi-assistant-hook.json /tmp/voice-gateway.json /home/ubuntu/n8n-compose/local-files/ && cd /home/ubuntu/n8n-compose && \
  sudo docker exec n8n-compose-n8n-1 n8n import:workflow --input=/files/vapi-assistant-hook.json 2>&1 | tail -1 && \
  sudo docker exec n8n-compose-n8n-1 n8n import:workflow --input=/files/voice-gateway.json 2>&1 | tail -1 && \
  sudo docker exec n8n-compose-n8n-1 n8n update:workflow --id="$HOOK_ID" --active=true && \
  sudo docker exec n8n-compose-n8n-1 n8n update:workflow --id="$GW_ID" --active=true && \
  echo 'restart...' && sudo docker restart n8n-compose-n8n-1 >/dev/null && sleep 18 && curl -s -o /dev/null -w 'healthz %{http_code}\n' https://n8n2.ordrnow.com/healthz"

echo "== 4. verify the LIVE exports (import can succeed on a stale file) =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-n8n-1 n8n export:workflow --id=$HOOK_ID --output=/tmp/hook-live.json >/dev/null 2>&1; sudo docker exec n8n-compose-n8n-1 cat /tmp/hook-live.json" > /tmp/vapi-assistant-hook-live.json
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-n8n-1 n8n export:workflow --id=$GW_ID --output=/tmp/gw-live.json >/dev/null 2>&1; sudo docker exec n8n-compose-n8n-1 cat /tmp/gw-live.json" > /tmp/voice-gateway-live.json
python3 - <<'PY'
import json
hook = json.load(open('/tmp/vapi-assistant-hook-live.json'))[0]
gw = json.load(open('/tmp/voice-gateway-live.json'))[0]
hn = {n['name'] for n in hook['nodes']}
gn = {n['name'] for n in gw['nodes']}
need_h = {'Exec: read_setup_status', 'Exec: start_call_row', 'Build Hook Variables'}
need_g = {'Extract Tool Call', 'Resolve Call Scope', 'Normalize Tool Call',
          'Onboarding Guard', 'Respond Setup First', 'Exec: ensure_company', 'Exec: link_user'}
missing = (need_h - hn) | (need_g - gn)
if missing:
    raise SystemExit(f"FAIL: live workflows missing {sorted(missing)}")
q = [n for n in hook['nodes'] if n['name'] == 'Exec: read_setup_status'][0]['parameters']['query']
if 'COALESCE((SELECT company_id FROM users' in q:
    raise SystemExit('FAIL: live hook still has the single-tenant fallback')
c = [n for n in hook['nodes'] if n['name'] == 'Build Hook Variables'][0]['parameters']['jsCode']
if 'user_id: userId' not in c:
    raise SystemExit('FAIL: live hook does not transport user_id')
print(f"live hook ok ({len(hn)} nodes), live gateway ok ({len(gn)} nodes)")
PY
