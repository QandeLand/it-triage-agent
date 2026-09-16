#!/usr/bin/env bash
set -e

# Ensure the app stack is running first (creates the network)
docker compose -f ~/projects/it-triage-agent/docker-compose.yml up -d

# Start/restart Prometheus attached to the compose network
docker rm -f prometheus-demo 2>/dev/null || true

docker run -d \
  --name prometheus-demo \
  -p 9090:9090 \
  --network it-triage-agent_default \
  -v "$HOME/projects/it-triage-agent/monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  -v "$HOME/projects/it-triage-agent/monitoring/prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro" \
  prom/prometheus:latest \
  --config.file=/etc/prometheus/prometheus.yml

echo "Prometheus starting... check http://localhost:9090/targets in 20s"
