#!/usr/bin/env bash
set -e
docker stop langflow-jira 2>/dev/null || true
docker rm   langflow-jira 2>/dev/null || true

docker run -d \
  --name langflow-jira \
  -p 7860:7860 \
  -v langflow_data:/app/langflow \
  -v /home/qandeel/projects/it-triage-agent/custom_components:/app/custom_components:ro \
  --env-file /home/qandeel/projects/it-triage-agent/.env.langflow \
  -e LANGFLOW_CONFIG_DIR=/app/langflow \
  -e LANGFLOW_SAVE_DB_IN_CONFIG_DIR=true \
  -e LANGFLOW_AUTO_LOGIN=false \
  -e LANGFLOW_SUPERUSER=langflow \
  -e LANGFLOW_HOST=0.0.0.0 \
  -e LANGFLOW_PORT=7860 \
  --restart unless-stopped \
  langflowai/langflow:latest

for i in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7860/health || true)
  [ "$code" = "200" ] && { echo "Ready: http://localhost:7860"; exit 0; }
  sleep 3
done
exit 1
