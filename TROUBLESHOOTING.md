# Troubleshooting Log

Real issues encountered while building this project, how they were diagnosed, and how they were resolved. Kept as a practical reference for anyone running into similar problems with Langflow, Supabase, Docker, or this stack in general.

| # | Issue | Severity |
|---|---|---|
| [1](#1-jiraslacksupabase-integration-generic-api-request-failed-in-agent-tool-mode) | Generic API Request failed in Agent Tool Mode | 🔴 Critical |
| [2](#2-lost-the-entire-wired-flow-after-a-database-swap) | Lost the entire wired flow after a database swap | 🔴 Critical |
| [3](#3-langflow-ui-showed-create-your-first-flow-despite-existing-flows) | UI showed "Create your first flow" despite existing data | 🟠 High |
| [4](#4-custom-components-not-showing-up-in-the-sidebar) | Custom components not showing up in the sidebar | 🟠 High |
| [5](#5-supabase-rest-api-returned-42501-permission-denied) | Supabase REST API returned `42501: permission denied` | 🟡 Medium |
| [6](#6-langflow-container-failed-to-start) | Langflow container failed to start | 🟡 Medium |
| [7](#7-architecture-decision-replaced-rag-with-agentic-file-reading) | Replaced RAG with agentic file reading | 🔵 Design decision |

---

## 1. Jira/Slack/Supabase integration: generic API Request failed in Agent Tool Mode

**Severity: 🔴 Critical — the single most time-consuming issue in the build.**

The problem affected every external integration: the generic `API Request` component worked correctly when executed standalone, but failed once it was exposed to the Agent as a Tool.

### Attempt 1 — API Request component, URL mode
The Jira REST endpoint, and separately the Supabase REST endpoint, were configured using the component's URL and authentication/header fields.

- Worked correctly when executed by itself
- Once connected to the Agent as a Tool, the Agent reported it had **no credentials** for the service — despite them being visibly configured inside the component

### Attempt 2 — API Request component, cURL mode
A complete cURL command was supplied instead:
```bash
curl -X POST -H "Authorization: Basic ..." ...
```

Same result:
- Worked standalone
- Failed through Agent Tool Mode — auth information wasn't reliably available during the tool call

A separate parsing bug was also found here: a multi-line command using `\` line continuations was misread, with everything after the first `\` appended onto the URL. Rewriting it as a single unbroken line fixed the parsing, but **not** the underlying Tool Mode auth problem.

### Attempt 3 — Python Interpreter component
Tried Langflow's built-in `Python Interpreter` (`RUN_PYTHON_REPL`) to execute the Jira request as inline Python, hoping to bypass whatever was stripping auth in Tool Mode.

- Not a good fit — designed for quick calculations/scripts with `print()` output, not structured, reusable API integrations with proper error handling
- Did not solve the credential-passing problem either

### Diagnosis
The issue was determined to be how the generic `API Request` component behaves when exposed as an Agent Tool: authentication configured directly on the component isn't reliably available when the LLM invokes it through the tool layer. **This was not an incorrect credential** for Jira, Slack, or Supabase individually — it was structural.

### ✅ Fix — dedicated custom Langflow components
The generic `API Request` approach was abandoned entirely. Dedicated Python components were written under:
```
custom_components/tools/
├── jira_component.py
├── slack_component.py
└── supabase_component.py
```

Each custom component:
- Uses Langflow's `langflow.custom.Component`
- Exposes **only** meaningful inputs to the LLM, marked `tool_mode=True`
- Reads credentials directly from environment variables **inside** the component — never exposed through the tool schema
- Returns a structured `Data` object with a clear success/failure result

The Agent only ever sees a clean interface, e.g.:
```python
create_jira_ticket(summary, description)
search_history(service)
```
The LLM never receives the actual credentials or auth configuration — there's nothing for the Tool Mode bug to strip, because no auth data exists on the LLM-facing side at all.

**Result:** solved the Agent Tool integration problem for all three services. The components themselves then needed a separate fix before Langflow could discover them at all — see [Issue 4](#4-custom-components-not-showing-up-in-the-sidebar).

---

## 2. Lost the entire wired flow after a database swap

**Severity: 🔴 Critical — real data loss.**

While troubleshooting an unrelated login issue, the Langflow SQLite database was replaced with an older backup to try to recover a different problem. After restoring it, the actual IT Triage Agent flow was gone.

Every backup checked — `langflow.db.backup`, a `.tar.gz` archive, and a separate `langflow_data_backup/` directory — contained only the default, unmodified "Simple Agent" starter template, not the completed flow with Jira/Slack/Supabase tools connected.

### Impact
The complete visual wiring of the Agent had to be rebuilt from scratch:
- Agent connections
- Tool connections
- Agent Instructions
- Jira, Slack, and Supabase integration wiring

The flow had never been exported or stored outside Langflow's internal SQLite database.

### What limited the damage
The custom Python components (`custom_components/tools/`) were stored separately on disk and tracked in git — they didn't need to be recreated or re-debugged. Only the visual wiring had to be rebuilt, which took a fraction of the original build time.

### Lesson
Langflow's internal SQLite database should not be treated as the only source of truth for important flow configuration.

### ✅ Process fix adopted
- Export important flows to JSON regularly and store them in the repo (`flows/it-triage-agent-flow.json`)
- Take dated snapshots of a working `langflow.db` after major milestones
- Keep database backups separate from ordinary source-code backups
- Treat anything that only exists inside a running container as **ephemeral** until it's been exported or version-controlled

---

## 3. Langflow UI showed "Create your first flow" despite existing flows

**Severity: 🟠 High.**

### Symptom
Opening `http://localhost:7860` showed the user already logged in, but the UI displayed **"Create your first flow"** even though the SQLite database contained existing flows.

### Investigation
Authentication was ruled out early since the session was already active. Instead of deleting data or recreating the environment, the database was inspected directly:

```bash
docker exec langflow-jira python -c "import sqlite3; c=sqlite3.connect('/app/langflow/langflow.db'); print('FOLDERS:'); print(*c.execute(\"SELECT * FROM folder\").fetchall(), sep='\n'); c.close()"
```
```bash
docker exec langflow-jira python -c "import sqlite3; c=sqlite3.connect('/app/langflow/langflow.db'); print(*c.execute(\"PRAGMA table_info(flow)\").fetchall(), sep='\n'); c.close()"
```

### Diagnosis
The flows had not disappeared and this was not an authentication problem — the UI's project/folder context needed to be examined rather than assumed broken.

### ✅ Result
The project/folder and flow relationship was investigated and corrected **without** deleting existing project data or recreating the Docker volume — preserving the existing work.

---

## 4. Custom components not showing up in the sidebar

**Severity: 🟠 High.**

### Symptom
`custom_components/` was correctly mounted into the container, confirmed via:
```bash
docker exec langflow-jira ls -la /app/custom_components/tools/
```
Files existed and were syntactically valid, but the components didn't appear anywhere in the Langflow UI — searching for them returned nothing.

### Investigation
```bash
docker exec langflow-jira env | grep -i LANGFLOW_COMPONENTS
# → empty
```

### Root cause
Mounting the directory isn't enough — Langflow needs to be explicitly told where to look. Setting `LANGFLOW_COMPONENTS_PATH` as a plain environment variable **did not work** in this version, despite appearing in some documentation.

### ✅ Fix
Checked the actual CLI options:
```bash
langflow run --help
```
The working solution was passing the path directly to the process:
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

**Result:** Langflow successfully discovered the custom components; they became available in the sidebar.

---

## 5. Supabase REST API returned `42501: permission denied`

**Severity: 🟡 Medium.**

### Symptom
Requests to `/rest/v1/incidents` returned:
```json
{"code": "42501", "message": "permission denied for table incidents"}
```
The table existed and Row Level Security policies appeared correctly configured (`Allow public read access`, `Allow service role access`).

### Root cause
RLS policies and PostgreSQL table privileges are **separate permission layers**. Having an appropriate RLS policy does not automatically grant the underlying role the required table privilege — `service_role` also needed an explicit grant.

### ✅ Fix
```sql
GRANT SELECT ON public.incidents TO service_role;
```
Followed by a schema reload so PostgREST picks up the change:
```sql
NOTIFY pgrst, 'reload schema';
```

### Complication
Supabase's SQL Editor intermittently returned `Backend error! Retry your query` on this exact statement — a platform-side issue, not invalid SQL. Retrying the identical statement eventually succeeded.

**Result:** the underlying permission problem was resolved. REST-level access and reliable Agent-level querying are separate concerns, though — the Agent integration still needed the dedicated custom Supabase component from [Issue 1](#1-jiraslacksupabase-integration-generic-api-request-failed-in-agent-tool-mode).

---

## 6. Langflow container failed to start

**Severity: 🟡 Medium.**

### Error
```
Missing credentials: username=langflow, password=not set
ValueError: Username and password must be set
Application startup failed. Exiting.
Worker (pid:18) exited with code 3.
```

### Cause
`.env` had `LANGFLOW_AUTO_LOGIN=false` but `LANGFLOW_SUPERUSER_PASSWORD` was empty. When auto-login is disabled, Langflow requires valid superuser credentials.

### ✅ Fix
```
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=langflow
LANGFLOW_SUPERUSER_PASSWORD=<a real password>
```

### Important Docker detail
Updating `.env` does **not** automatically update an already-created container — it must be removed and recreated:
```bash
docker rm -f langflow-jira
# then start again with the updated .env
```

**Result:** Langflow started successfully with authentication enabled.

---

## 7. Architecture decision: replaced RAG with agentic file reading

**Category: 🔵 Design decision, not a bug.**

### Problem
The original plan was a traditional RAG/vector-search knowledge base for runbooks and postmortems — which required an embedding model provider.

### Investigation
- Groq does not provide embedding models at all
- HuggingFace's inference API was not suitable for the required embedding workflow
- Self-hosting Ollama with `nomic-embed-text` was considered, but introduced Docker-to-host networking complexity: a container can't reach a host service via `localhost`, requiring `--add-host=host.docker.internal:host-gateway` plus additional Langflow SSRF allow-list configuration

### ✅ Architectural decision
The knowledge base contained only a small, static set of documents. Rather than introduce a full embedding/vector-search pipeline, the architecture was simplified to **agentic file reading** — the Agent calls a `Read File` tool on demand.

### Reasoning
For a small number of static documents, this approach:
- Removes the embedding-model dependency
- Removes vector database complexity
- Avoids additional Docker networking
- Reduces configuration surface
- Is easier to debug
- Is sufficient at this document count

**Result:** avoided unnecessary RAG infrastructure while still giving the Agent on-demand access to runbooks and postmortems.

---

## Key lessons

1. Don't assume a component that works standalone will behave identically as an Agent Tool.
2. Keep credentials inside backend/custom-component code — never expose them through LLM-facing tool inputs.
3. Mounting a custom component directory isn't always enough; the application must also be told where to discover it.
4. Don't treat an application's internal database as the only backup of important configuration — export visual/low-code workflows into version-controlled files.
5. RLS policies and PostgreSQL privileges are separate layers in Supabase.
6. Docker containers must be recreated when environment variables change — editing `.env` alone isn't enough.
7. Prefer the simplest architecture that solves the actual problem instead of adding infrastructure unnecessarily.