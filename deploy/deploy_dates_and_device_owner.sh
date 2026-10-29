#!/usr/bin/env bash
# deploy_dates_and_device_owner.sh
#   1. db/0044  - device_tokens.user_id, clear legacy unowned rows
#   2. workflows - voice-gateway (dates), approve-invoice (dates),
#      invoice-template-preview (sample date), device-registration (owner-bound),
#      device-unregister (new)
#   3. verify the LIVE exports carry the changes
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=ubuntu@n8n2.ordrnow.com
TS=$(date +%Y%m%d_%H%M%S)

echo "== 1. pre-deploy dump + migration 0044 =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-postgres-1 pg_dump -U postgres -d postgres > /home/ubuntu/backups/pm/pre-devowner-${TS}.sql && echo dumped"
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q" < db/0044_device_owner.sql
echo "0044 OK"

echo "== 2. deploy workflows =="
scp -q backend/n8n/workflows/voice-gateway.json \
       backend/n8n/workflows/approve-invoice.json \
       backend/n8n/workflows/invoice-template-preview.json \
       backend/n8n/workflows/device-registration.json \
       backend/n8n/workflows/device-unregister.json "$HOST":/tmp/
ssh -o ConnectTimeout=10 "$HOST" "sudo cp /tmp/voice-gateway.json /tmp/approve-invoice.json /tmp/invoice-template-preview.json /tmp/device-registration.json /tmp/device-unregister.json /home/ubuntu/n8n-compose/local-files/ && cd /home/ubuntu/n8n-compose && \
  for f in voice-gateway approve-invoice invoice-template-preview device-registration device-unregister; do \
    sudo docker exec n8n-compose-n8n-1 n8n import:workflow --input=/files/\$f.json 2>&1 | tail -1; \
  done && \
  for id in 5Dswa943KQF0rnZ1 invoice-approval-001 tplPreview-001 device-registration-001 device-unregister-001; do \
    sudo docker exec n8n-compose-n8n-1 n8n update:workflow --id=\$id --active=true >/dev/null 2>&1 || echo \"activate failed: \$id\"; \
  done && \
  echo restart && sudo docker restart n8n-compose-n8n-1 >/dev/null && sleep 18 && curl -s -o /dev/null -w 'healthz %{http_code}\n' https://n8n2.ordrnow.com/healthz"

echo "== 3. verify LIVE exports =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-n8n-1 n8n export:workflow --id=5Dswa943KQF0rnZ1 --output=/tmp/gw.json >/dev/null 2>&1; sudo docker exec n8n-compose-n8n-1 cat /tmp/gw.json" > /tmp/gw.json
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-n8n-1 n8n export:workflow --id=device-registration-001 --output=/tmp/reg.json >/dev/null 2>&1; sudo docker exec n8n-compose-n8n-1 cat /tmp/reg.json" > /tmp/reg.json
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-n8n-1 n8n export:workflow --id=device-unregister-001 --output=/tmp/unreg.json >/dev/null 2>&1; sudo docker exec n8n-compose-n8n-1 cat /tmp/unreg.json" > /tmp/unreg.json
python3 - <<'PY'
import json
gw = json.load(open('/tmp/gw.json'))[0]
reg = json.load(open('/tmp/reg.json'))[0]
unreg = json.load(open('/tmp/unreg.json'))[0]
render = [n for n in gw['nodes'] if n['name'] == 'Render Invoice HTML'][0]['parameters']['jsCode']
assert 'fmtDate(' in render, 'live invoice renderer has no fmtDate'
q = [n for n in reg['nodes'] if n['name'] == 'Exec: upsert_device_token'][0]['parameters']['query']
assert 'user_id' in q and 'company_id' in q, 'live registration does not bind owner'
uq = [n for n in unreg['nodes'] if n['name'] == 'Exec: delete_device_token'][0]['parameters']['query']
assert 'DELETE FROM device_tokens' in uq, 'live unregister has no delete'
print('live ok: renderer dates, owner-bound registration, unregister endpoint')
PY
