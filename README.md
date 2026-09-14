# IT Anomaly Triage & Auto-Response Agent

An AI agent that triages IT incidents, checks historical context, and automatically opens a Jira ticket and sends a Slack alert — but only when the situation genuinely warrants it.

Built with **Langflow** (self-hosted, Docker), **Groq** for LLM reasoning, **Supabase** for historical incident data, and native **Jira** and **Slack** integrations via custom Python tool components.

---

## What it does

Given an incident description, the agent:

1. **Assesses severity** (P1–P4) against a defined alert severity policy
2. **Checks historical incidents** for the affected service via Supabase, to spot recurring patterns
3. **Decides whether to act**, using explicit tiered logic:
   - **P1/P2 in production** → creates a Jira ticket **and** sends a Slack alert
   - **P3/P4, staging/non-production, or transient/self-resolved issues** → reports the assessment only, no ticket or noise
4. **Responds with a structured summary**: severity, environment, confidence, relevant history, and the action taken

This mirrors how a real NOC/on-call workflow should behave — escalate what matters, stay quiet on noise.

---

## Architecture

Chat Input
│
▼
Agent (Groq LLM — openai/gpt-oss-120b)
│
├── Supabase Incident History Tool → queries historical incidents by service
├── Jira Ticket Tool → creates a ticket (Basic Auth, REST API v3)
└── Slack Notification Tool → posts to a Slack channel via Incoming Webhook
│
▼
Chat Output


Each tool is a native Langflow **custom component** (not a generic HTTP request block) — this matters because Langflow's generic `API Request` component has a documented limitation when used in Agent Tool Mode: authentication headers and request bodies aren't reliably passed through. Writing dedicated Python components with `tool_mode=True` inputs solved this cleanly, and lets the agent fill in ticket summaries and Slack messages dynamically per incident.

---

## Tech stack

| Component | Tool |
|---|---|
| Agent orchestration | Langflow (self-hosted, Docker) |
| LLM | Groq (`openai/gpt-oss-120b`, OpenAI-compatible API) |
| Historical data | Supabase (Postgres) |
| Ticketing | Jira Cloud REST API v3 |
| Alerting | Slack Incoming Webhooks |
| Custom tools | Python (`langflow.custom.Component`) |

---

## Setup

### Prerequisites
- Docker
- A Groq API key (free tier — [console.groq.com](https://console.groq.com))
- A Jira Cloud site + API token
- A Slack workspace + Incoming Webhook URL
- A Supabase project with an `incidents` table

### 1. Clone and configure
```bash
git clone https://github.com/QandeLand/it-triage-agent.git
cd it-triage-agent
cp .env.example .env
# fill in your real values in .env
```

### 2. Run Langflow with the custom components mounted
```bash
docker run -d \
  --name langflow-jira \
  -p 7860:7860 \
  --env-file .env \
  --mount type=volume,source=langflow_data,target=/app/langflow \
  --mount type=bind,source="$(pwd)/custom_components",target=/app/custom_components,readonly \
  langflowai/langflow:latest \
  langflow run --components-path /app/custom_components
```

### 3. Open Langflow

http://localhost:7860

Log in with the `LANGFLOW_SUPERUSER` / `LANGFLOW_SUPERUSER_PASSWORD` you set in `.env`.

### 4. Load the flow
Import `flows/it-triage-agent-flow.json`, or rebuild from scratch:
- Add an Agent, set the Language Model to Groq (OpenAI-compatible, base URL `https://api.groq.com/openai/v1`)
- Add the **Jira Ticket Tool**, **Slack Notification**, and **Supabase Incident History** components (auto-discovered from `custom_components/`)
- Connect all three to the Agent's Tools input
- Add Chat Input → Agent → Chat Output

### 5. Set up your Supabase `incidents` table
```sql
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
```

---

## Environment variables

See `.env.example` for the full list. Never commit a real `.env` — it's gitignored.

JIRA_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
SLACK_WEBHOOK_URL=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=
LANGFLOW_SUPERUSER_PASSWORD=


---

## Example runs

**Production P1 — triggers automation:**
> "Production payments-api is returning 35% HTTP 500 errors for the last 10 minutes. The normal error rate is below 1%. Customers are currently unable to complete payments."

Severity: P1 (Critical)
Environment: production
Confidence: 100%
Historical pattern: No prior incidents for payments-api in the historical database.
Action taken: Jira ticket SCRUM-16 created and Slack notification sent.


**Staging noise — correctly takes no action:**
> "Staging payments-api briefly returned 3 HTTP 500 errors during a deployment. The service recovered automatically and no customers were affected."

Severity: P4 (Low)
Environment: non-production (staging)
Confidence: High
Historical pattern: No matching incidents in the Supabase history.
Action taken: No action (no Jira ticket, no Slack notification).


---

## Notable engineering challenges solved

- **Langflow's generic API Request component silently fails auth in Agent Tool Mode** — a known platform limitation. Solved by writing native Python custom components instead, with clean `tool_mode=True` parameters the LLM can fill dynamically.
- **No free embedding provider available** (Groq doesn't offer embeddings; HuggingFace's public inference API no longer supports them) — worked around by using an agentic file-reading pattern instead of a vector store for the knowledge base, appropriate given the small, static document set.
- **Docker networking**: connecting a host-installed Ollama instance to a containerized Langflow required `--add-host=host.docker.internal:host-gateway` plus explicitly allow-listing the host in `LANGFLOW_SSRF_ALLOWED_HOSTS`.
- **Supabase permission errors (`42501`)** on a table that existed with correct RLS policies — root cause was a missing underlying PostgreSQL `GRANT SELECT` privilege, not the RLS policy itself.
- **Langflow requires `--components-path` (or the container recreated with it) for custom components to be discovered** — the mount alone isn't enough.

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
| Runbook / on-call knowledge base | 🔜 Planned |

---

## Author

Qandeel Javed — DevOps Engineer, Stockholm
[github.com/QandeLand](https://github.com/QandeLand) · [linkedin.com/in/qandeeljaved](https://www.linkedin.com/in/qandeeljaved)