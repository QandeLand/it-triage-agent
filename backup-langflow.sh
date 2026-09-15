#!/usr/bin/env bash
set -e
cd ~/projects/it-triage-agent
mkdir -p backups
docker cp langflow-jira:/app/langflow/langflow.db \
  "./backups/langflow.db.$(date +%Y%m%d-%H%M%S)"
# Keep only last 14 backups
ls -1t backups/langflow.db.* | tail -n +15 | xargs -r rm
