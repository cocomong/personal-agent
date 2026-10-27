#!/usr/bin/env bash
# deploy_invoice_templates.sh — ONE approval for the whole template-choice
# feature (built + locally verified overnight; every live step runs here).
#
# Order: pre-dump -> migrations 0037/0038 -> seed catalog -> deploy 3
# workflows (gateway, approve-invoice, invoice-template-preview) -> Vapi
# assistant (32 tools + prompt) -> E2E probe -> SCHEMA.md regen.
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root
HOST=ubuntu@n8n2.ordrnow.com
TS=$(date +%Y%m%d_%H%M%S)

echo "== 1. pre-deploy dump =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-postgres-1 pg_dump -U postgres -d postgres > /home/ubuntu/backups/pm/pre-tpl-${TS}.sql && ls -lh /home/ubuntu/backups/pm/pre-tpl-${TS}.sql | awk '{print \$5}'"

echo "== 2. migrations 0037 + verify 0038 =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q" < db/0037_invoice_templates.sql && echo "0037 OK"
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q" < db/0038_invoice_templates_verify.sql && echo "0038 verify OK"

echo "== 3. seed the catalog (idempotent upsert) =="
python3 backend/n8n/seed_invoice_templates.py > /tmp/tpl_seed.sql
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q" < /tmp/tpl_seed.sql
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec n8n-compose-postgres-1 psql -U postgres -d postgres -At -c \"SELECT key, is_active, length(html) FROM document_templates ORDER BY key\""

echo "== 4. deploy workflows: gateway + approve-invoice + invoice-template-preview =="
scp -q backend/n8n/workflows/voice-gateway.json backend/n8n/workflows/approve-invoice.json backend/n8n/workflows/invoice-template-preview.json "$HOST":/tmp/
ssh -o ConnectTimeout=10 "$HOST" "sudo cp /tmp/voice-gateway.json /tmp/approve-invoice.json /tmp/invoice-template-preview.json /home/ubuntu/n8n-compose/local-files/ && cd /home/ubuntu/n8n-compose && \
  sudo docker exec n8n-compose-n8n-1 n8n import:workflow --input=/files/voice-gateway.json 2>&1 | tail -1 && \
  sudo docker exec n8n-compose-n8n-1 n8n import:workflow --input=/files/approve-invoice.json 2>&1 | tail -1 && \
  sudo docker exec n8n-compose-n8n-1 n8n import:workflow --input=/files/invoice-template-preview.json 2>&1 | tail -1 && \
  sudo docker exec n8n-compose-n8n-1 n8n update:workflow --id=5Dswa943KQF0rnZ1 --active=true && \
  sudo docker exec n8n-compose-n8n-1 n8n update:workflow --id=invoice-approval-001 --active=true && \
  sudo docker exec n8n-compose-n8n-1 n8n update:workflow --id=tplPreview-001 --active=true && \
  echo 'restart...' && sudo docker restart n8n-compose-n8n-1 >/dev/null && sleep 18 && curl -s -o /dev/null -w 'healthz %{http_code}\n' https://n8n2.ordrnow.com/healthz"

echo "== 5. Vapi assistant: 32 tools + prompt (repo is synced to live) =="
python3 backend/create_vapi_assistant.py

echo "== 6. tool routing read-back =="
python3 qa/verify_vapi_tools.py

echo "== 7. E2E probe (set modern -> stored modern preview -> preview page -> tap-to-choose -> invalid refused -> revert) =="
python3 qa/template_choice_probe.py

echo "== 8. SCHEMA.md regen (0037 catalog) =="
ssh -o ConnectTimeout=10 "$HOST" "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -tA -q -v ON_ERROR_STOP=1" < qa/schema_extract.sql > /tmp/schema_dump.txt
python3 qa/schema_regen.py /tmp/schema_dump.txt > doc/SCHEMA.md
head -3 doc/SCHEMA.md | tail -1

echo "ALL DONE — commit the regenerated SCHEMA.md."
