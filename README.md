# IT Anomaly Triage & Auto-Response Agent

[![CI](https://github.com/QandeLand/it-triage-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/QandeLand/it-triage-agent/actions/workflows/ci.yml)
[![Container](https://img.shields.io/badge/ghcr.io-it--triage--agent-blue?logo=docker&logoColor=white)](https://github.com/QandeLand/it-triage-agent/pkgs/container/it-triage-agent)
[![Python](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-multi--stage-2496ED?logo=docker&logoColor=white)](./app/Dockerfile)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#)

An end-to-end incident response system that ingests alerts, triages them with an LLM agent, and **acts only when warranted** — opening a Jira ticket and paging Slack for real production incidents, staying silent on staging noise.

Combines a **containerized Flask webhook/metrics service**, a **self-hosted Langflow AI agent**, **Groq** for LLM reasoning, **Supabase** for historical context, and native **Jira** + **Slack** integrations — all wired into a **GitHub Actions CI/CD pipeline** that tests, builds, and publishes a signed container image to **GitHub Container Registry**.

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Quick start (local dev)](#quick-start-local-dev)
- [Setting up the AI agent](#setting-up-the-ai-agent)
- [CI/CD pipeline](#cicd-pipeline)
- [Observability](#observability)
- [Environment variables](#environment-variables)
- [Example runs](#example-runs)
- [Engineering challenges solved](#engineering-challenges-solved)
- [Status](#status)
- [Author](#author)

---

## What it does

Given an incident description, the agent:

1. **Assesses severity** (P1–P4) against a defined alert severity policy
2. **Checks historical incidents** for the affected service via Supabase, to spot recurring patterns
3. **Decides whether to act**, using explicit tiered logic:
   - **P1/P2 in production** → creates a Jira ticket **and** sends a Slack alert
   - **P3/P4, staging/non-production, or transient/self-resolved issues** → reports the assessment only, no ticket or noise
4. **Responds with a structured summary**: severity, environment, confidence, relevant history, and the action taken

This mirrors how a real NOC / on-call workflow should behave — escalate what matters, stay quiet on noise.

---

## Architecture

\```
┌──────────────────────┐
│   Alert source        │
│ (Prometheus, etc.)    │
└──────────┬─────────────┘
           │ incident payload
           ▼
┌──────────────────────┐
│   Flask webhook app   │  /webhook  /health  /metrics
│   (Docker, port 5000) │
└──────────┬─────────────┘
           ▼
┌──────────────────────┐
│   Langflow AI Agent   │
│      (Groq LLM)       │
└──────────┬─────────────┘
           │
   ┌───────┼────────────────┐
   ▼       ▼                ▼
┌─────────┐ ┌─────────────┐ ┌──────────────┐
│Supabase │ │ Jira Ticket │ │    Slack     │
│Incident │ │    Tool     │ │ Notification │
│History  │ │ (REST v3)   │ │  (Webhook)   │
└─────────┘ └─────────────┘ └──────────────┘

Prometheus ──scrape──▶ /metrics on the Flask app
\```

Two services, one system:

| Layer | Component | Role |
|---|---|---|
| **Ingress** | Flask app (`app/`) | Receives alerts, exposes `/health` and Prometheus `/metrics` |
| **Reasoning** | Langflow agent (`flows/`, `custom_components/`) | Classifies severity, queries history, decides action |
| **Action** | Jira + Slack custom tools | Creates tickets, sends alerts |
| **Observability** | Prometheus + (Grafana) | Scrapes the Flask app, visualizes pipeline health |
| **Delivery** | GitHub Actions → GHCR | Tests, builds, publishes the container image |

Each Langflow tool is a native custom Python component (not a generic HTTP block) — see [Engineering challenges](#engineering-challenges-solved) for why.

---

## Tech stack

| Layer | Tool |
|---|---|
| Agent orchestration | Langflow (self-hosted, Docker) |
| LLM | Groq (`openai/gpt-oss-120b`, OpenAI-compatible API) |
| Historical data | Supabase (Postgres) |
| Ticketing | Jira Cloud REST API v3 |
| Alerting | Slack Incoming Webhooks |
| Custom tools | Python (`langflow.custom.Component`) |
| Webhook receiver | Flask 3 + Gunicorn |
| Containerization | Docker (multi-stage, non-root, healthcheck) |
| Local orchestration | Docker Compose |
| CI/CD | GitHub Actions → GitHub Container Registry (GHCR) |
| Metrics | Prometheus (client library `prometheus-client`) |
| Testing | pytest (4 tests, runs in CI) |

---

## Quick start (local dev)

**Prerequisites:** Docker, Docker Compose.

\```bash
git clone https://github.com/QandeLand/it-triage-agent.git
cd it-triage-agent
cp .env.example .env
# fill in real values in .env

# Start the webhook service
docker compose up --build -d

# Verify
docker compose ps                      # STATUS should say (healthy)
curl localhost:5000/health             # {"status":"ok"}
curl localhost:5000/metrics | head
\```

To pull and run the published image instead of building locally:

\```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u QandeLand --password-stdin
docker pull ghcr.io/qandeland/it-triage-agent:latest
docker run --rm -d -p 5000:5000 --name triage ghcr.io/qandeland/it-triage-agent:latest
curl localhost:5000/health
\```

Run the tests locally in a venv (Debian/Ubuntu block system pip — PEP 668):

\```bash
cd app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest -v
\```

---

## Setting up the AI agent

### 1. Run Langflow with the custom components mounted

\```bash
docker run -d \
  --name langflow-jira \
  -p 7860:7860 \
  --env-file .env \
  --mount type=volume,source=langflow_data,target=/app/langflow \
  --mount type=bind,source="$(pwd)/custom_components",target=/app/custom_components,readonly \
  langflowai/langflow:latest \
  langflow run --components-path /app/custom_components
\```

> ⚠️ The `--components-path` flag (or recreating the container with it) is required — mounting alone does not make Langflow discover custom components.

### 2. Open Langflow

http://localhost:7860

Log in with `LANGFLOW_SUPERUSER` / `LANGFLOW_SUPERUSER_PASSWORD` from `.env`.

### 3. Load the flow

Import `flows/it-triage-agent-flow.json`, or rebuild from scratch:

- Add an **Agent**, set the Language Model to **Groq** (OpenAI-compatible, base URL `https://api.groq.com/openai/v1`)
- Add the **Jira Ticket Tool**, **Slack Notification**, and **Supabase Incident History** components (auto-discovered from `custom_components/`)
- Connect all three to the Agent's **Tools** input
- Wire **Chat Input → Agent → Chat Output**

### 4. Supabase schema

\```sql
CREATE TABLE incidents (
    id SERIAL PRIMARY KEY,
    service_name TEXT NOT NULL,
    incident_timestamp TIMESTAMP NOT NULL,
    metric_type TEXT NOT NULL,
    baseline_value NUMERIC,
    observed_value NUMERIC,
    severity TEXT,
    root_cause TEXT,
    resolved BOOLEAN DEFAULT TRUE,
    resolution_minutes INTEGER
);
\```

---

## CI/CD pipeline

GitHub Actions workflow: `.github/workflows/ci.yml`

\```
push / PR to main
       │
       ▼
┌────────────────────┐
│  Test app           │  ✓ set up Python 3.12
│  (ubuntu-latest)     │  ✓ install deps + pytest
│                      │  ✓ pytest -v   → 4 passed
└──────────┬───────────┘
           │ needs: test
           ▼
┌────────────────────┐
│  Build & publish    │  ✓ Docker Buildx (with GHA layer cache)
│                      │  ✓ login to ghcr.io via GITHUB_TOKEN
│                      │  ✓ metadata: latest + sha-<commit>
│                      │  ✓ push only on main
└──────────┬───────────┘
           ▼
  ghcr.io/qandeland/it-triage-agent:latest
  ghcr.io/qandeland/it-triage-agent:sha-<commit>
\```

Design decisions:

- **`needs: test`** — the image is never built from code that fails tests.
- **No long-lived secrets** — uses the auto-provisioned `GITHUB_TOKEN` with scoped permissions: `packages: write`. No PAT to rotate.
- **Multi-tag strategy** — `latest` for convenience, `sha-<commit>` for immutable traceability. Any running container maps back to a commit.
- **PR vs main** — PRs build the image (`push: false`) to catch Dockerfile regressions, but only `main` publishes.
- **Layer cache via `type=gha`** — repeat runs drop from ~45s to a few seconds.

Verified end-to-end: the published image was pulled locally and answered `{"status":"ok"}` on `/health`.

---

## Observability

The Flask app exposes Prometheus metrics at `/metrics` using the `prometheus-client` library. A local Prometheus instance (`prometheus-demo` container) scrapes it automatically.

\```bash
# Confirm metrics are live
curl localhost:5000/metrics | head

# Prometheus UI
open http://localhost:9090
\```

Custom metric exposed by the app:

\```
# HELP app_requests_total Total HTTP requests handled
# TYPE app_requests_total counter
app_requests_total{method="GET",endpoint="/health"} 42.0
\```
<!-- VERIFY: adjust the metric name/help text to match app.py -->

Grafana is planned as the next step for visualization. <!-- VERIFY: remove if not planned -->

---

## Environment variables

See `.env.example` for the full list. Never commit a real `.env` — it's gitignored.

\```env
JIRA_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
SLACK_WEBHOOK_URL=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=
LANGFLOW_SUPERUSER_PASSWORD=
\```

---

## Example runs

### Production P1 — triggers automation ✅

> "Production payments-api is returning 35% HTTP 500 errors for the last 10 minutes. The normal error rate is below 1%. Customers are currently unable to complete payments."

\```
Severity:            P1 (Critical)
Environment:         production
Confidence:          100%
Historical pattern:  No prior incidents for payments-api in the historical database.
Action taken:        Jira ticket SCRUM-16 created and Slack notification sent.
\```

### Staging noise — correctly takes no action ✅

> "Staging payments-api briefly returned 3 HTTP 500 errors during a deployment. The service recovered automatically and no customers were affected."

\```
Severity:            P4 (Low)
Environment:         non-production (staging)
Confidence:          High
Historical pattern:  No matching incidents in the Supabase history.
Action taken:        No action (no Jira ticket, no Slack notification).
\```

---

## Engineering challenges solved

- Langflow's generic API Request component silently fails auth in Agent Tool Mode — a known platform limitation. Solved by writing native Python custom components instead, with clean `tool_mode=True` parameters the LLM can fill dynamically.
- No free embedding provider available (Groq doesn't offer embeddings; HuggingFace's public inference API no longer supports them) — worked around by using an agentic file-reading pattern instead of a vector store, appropriate given the small, static document set.
- Docker networking: connecting a host-installed Ollama instance to a containerized Langflow required `--add-host=host.docker.internal:host-gateway` plus explicitly allow-listing the host in `LANGFLOW_SSRF_ALLOWED_HOSTS`.
- Supabase permission errors (42501) on a table that existed with correct RLS policies — root cause was a missing underlying PostgreSQL `GRANT SELECT` privilege, not the RLS policy itself.
- Langflow requires `--components-path` (or container recreation with it) for custom components to be discovered — the mount alone isn't enough.
- Malformed CI workflow on first push — the YAML was duplicated in the editor, producing "workflow file issue" with zero jobs created. Diagnosed via `gh api repos/.../actions/runs/<id>/jobs` (empty array), fixed with a clean rewrite, verified by schema assertion before commit. The broken and fixed commits are both preserved in history.

---

## Status

| Capability | Status |
|---|---|
| Severity classification (P1–P4) | ✅ Working |
| Production vs non-production detection | ✅ Working |
| Historical incident lookup (Supabase) | ✅ Working |
| Jira ticket creation | ✅ Working |
| Slack notification | ✅ Working |
| Tiered auto-trigger logic | ✅ Working |
| Flask webhook + `/health` + `/metrics` | ✅ Working |
| Multi-stage Docker image (non-root, healthcheck) | ✅ Working |
| Local docker compose stack | ✅ Working |
| GitHub Actions CI (tests + Docker build) | ✅ Working |
| Publish image to GHCR (multi-tagged) | ✅ Working |
| Prometheus scraping | ✅ Working |
| Grafana dashboards | 🔜 Planned |
| Runbook / on-call knowledge base | 🔜 Planned |
| IaC (Terraform) for deployment target | 🔜 Planned |
| Image vulnerability scanning (Trivy) in CI | 🔜 Planned |

---

## Author

**Qandeel Javed** — DevOps Engineer, Stockholm

[github.com/QandeLand](https://github.com/QandeLand) · [linkedin.com/in/qandeeljaved](https://linkedin.com/in/qandeeljaved)