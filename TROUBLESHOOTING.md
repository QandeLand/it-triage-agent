Troubleshooting Log
Real issues encountered while building this project, how they were diagnosed, and how they were resolved. This is kept as a practical reference for anyone running into similar problems with Langflow, Supabase, Docker, or this stack in general.

1. Jira/Slack/Supabase Integration: Generic API Request Failed in Agent Tool Mode
This was the single most time-consuming issue in the build. The problem affected the external integrations because the generic API Request component worked when executed standalone but failed when exposed to the Langflow Agent as a Tool.

Multiple approaches were tested before finding a reliable solution.

Attempt 1 — API Request Component, URL Mode
The Jira REST endpoint, and separately the Supabase REST endpoint, were configured using the component's URL and authentication/header fields.

The component worked correctly when executed by itself.

However, once it was connected to the Agent as a Tool, the Agent reported that it did not have credentials for the service, even though the credentials were visibly configured inside the component.

Attempt 2 — API Request Component, cURL Mode
A complete cURL command was then supplied to the component instead:

curl -X POST -H "Authorization: Basic ..." ...

This produced the same behavior:

Worked when the component was run standalone
Failed when invoked through Agent Tool Mode
Authentication information was not reliably available during the Agent tool call
A separate cURL parsing issue was also discovered.

A multi-line command using \ line continuations was incorrectly interpreted, with content after the first \ being appended to the URL.

Changing the command to a single unbroken line fixed the cURL parsing problem, but did not solve the underlying Agent Tool authentication problem.

Attempt 3 — Python Interpreter Component
The built-in Langflow Python Interpreter component (RUN_PYTHON_REPL) was also tested.

The idea was to execute the Jira API request as Python code and bypass the authentication behavior of the generic API component.

This was not a good fit because the Python Interpreter component is primarily intended for quick calculations and scripts with print() output rather than structured, reusable API integrations with proper error handling.

It also did not solve the credential-passing problem in Agent Tool Mode.

Diagnosis
The problem was determined to be related to how the generic API Request component behaves when exposed as an Agent Tool.

Authentication configured directly on the component was not reliably available when the LLM invoked the component through the tool layer.

The issue was therefore not simply an incorrect Jira, Slack, or Supabase credential.

Fix — Dedicated Custom Langflow Components
The generic API Request approach was abandoned for the integrations.

Instead, dedicated Python components were created under:

custom_components/tools/

with separate components for:

jira_component.py
slack_component.py
supabase_component.py

Each custom component:

Uses Langflow's langflow.custom.Component
Exposes only meaningful inputs to the LLM
Marks LLM-facing inputs with tool_mode=True
Reads credentials directly from environment variables inside the component
Keeps URLs, tokens, and authentication headers out of the LLM-facing tool schema
Returns structured Langflow Data objects with clear success/failure results
For example, the Agent only needs to see a tool interface such as:

create_jira_ticket(summary, description)

or:

search_history(service)

The LLM never receives the actual credentials or authentication configuration.

This approach also made the integrations reusable and easier to debug because the authentication logic is handled entirely inside the custom component.

Result
The dedicated custom components successfully solved the Agent Tool integration problem for Jira, Slack, and Supabase.

The custom components themselves then required a separate fix before Langflow could discover them. See Issue 3.

2. Langflow UI Showed "Create Your First Flow" Despite Existing Flows
Symptom
After opening:

http://localhost:7860

Langflow was already logged in, but the UI displayed:

Create your first flow

even though the Langflow SQLite database contained existing flows.

Initial Investigation
Authentication was initially considered, but this was ruled out because the Langflow session was already active.

The next step was to inspect the SQLite database directly instead of deleting data, recreating the environment, or attempting to log in again.

Database Investigation
The Langflow database was inspected from inside the Docker container.

The folder/project records were checked:

docker exec langflow-jira python -c "import sqlite3; c=sqlite3.connect('/app/langflow/langflow.db'); print('FOLDERS:'); print(*c.execute(\"SELECT * FROM folder\").fetchall(), sep='\\n'); c.close()"

The flow table structure was also inspected:

docker exec langflow-jira python -c "import sqlite3; c=sqlite3.connect('/app/langflow/langflow.db'); print(*c.execute(\"PRAGMA table_info(flow)\").fetchall(), sep='\\n'); c.close()"

Diagnosis
The problem was not authentication and the flows had not simply disappeared.

The investigation showed that the UI's project/folder context and the existing flow records needed to be examined rather than treating the situation as a login problem.

Solution
The Langflow project/folder and flow relationship was investigated and corrected without deleting the existing project data or recreating the Docker volume.

Result
The existing Langflow work was preserved and the application could continue using the existing flows.

3. Custom Components Not Showing Up in the Langflow Sidebar
Symptom
The custom_components/ directory was correctly mounted into the Langflow container.

This was verified with:

docker exec langflow-jira ls -la /app/custom_components/tools/

The Python files existed and were syntactically valid, but the components did not appear anywhere in the Langflow UI.

Searching for the component names returned nothing.

Investigation
The container environment was checked:

docker exec langflow-jira env | grep -i LANGFLOW_COMPONENTS

The result was empty.

Root Cause
Mounting the directory into the container was not enough.

Langflow also needed to be explicitly told where the custom components were located.

Setting:

LANGFLOW_COMPONENTS_PATH

as a normal environment variable did not work in the Langflow version being used, despite the variable appearing in some documentation.

Fix
The available Langflow CLI options were checked with:

langflow run --help

The working solution was to pass the component path directly to the Langflow process:

docker run -d \
  --name langflow-jira \
  -p 7860:7860 \
  --env-file .env \
  --mount type=volume,source=langflow_data,target=/app/langflow \
  --mount type=bind,source="$(pwd)/custom_components",target=/app/custom_components,readonly \
  langflowai/langflow:latest \
  langflow run --components-path /app/custom_components

Result
Langflow successfully discovered the custom components and they became available in the component sidebar.

4. Lost the Entire Wired Flow After a Database Swap
Problem
While troubleshooting an unrelated Langflow login issue, the SQLite database was replaced with an older backup in an attempt to recover another problem.

The backup appeared to be valid, but after restoring it, the actual IT Triage Agent flow was gone.

Several backups were checked, including:

langflow.db.backup
.tar.gz archive
langflow_data_backup/

They contained only the default, unmodified Langflow "Simple Agent" starter template rather than the completed flow with the Jira, Slack, and Supabase tools connected.

Impact
The complete visual wiring of the Agent had to be rebuilt:

Agent connections
Tool connections
Agent Instructions
Jira integration wiring
Slack integration wiring
Supabase integration wiring
The actual flow had never been exported or stored outside Langflow's internal SQLite database.

What Limited the Damage
The custom Python components were stored separately on disk and tracked in Git:

custom_components/tools/

Therefore, the components themselves did not need to be recreated or re-debugged.

Only the visual Langflow wiring had to be rebuilt.

Lesson
Langflow's internal SQLite database should not be treated as the only source of truth for important flow configuration.

Process Fix
The following process was adopted:

Export important Langflow flows to JSON regularly.
Store exported flows in the repository, for example:
flows/it-triage-agent-flow.json

Take dated snapshots of a working langflow.db after major milestones.
Keep database backups separate from ordinary source-code backups.
Treat configuration that exists only inside a running container as ephemeral until it has been exported or version-controlled.
Result
The flow was rebuilt successfully, and the experience led to a more reliable backup and version-control strategy.

5. Supabase REST API Returned 42501: permission denied for table incidents
Symptom
Requests to the Supabase REST endpoint:

/rest/v1/incidents

returned:

42501: permission denied for table incidents

The table existed and Row Level Security policies appeared to be configured correctly.

For example:

Allow public read access
Allow service role access

Root Cause
Row Level Security policies and PostgreSQL table privileges are separate permission layers.

Having an appropriate RLS policy does not automatically grant the underlying PostgreSQL role the required table privilege.

The service_role therefore also required an explicit table-level grant.

Fix
The following SQL was used:

GRANT SELECT ON public.incidents TO service_role;

After changing the database permissions, PostgREST was notified to reload its schema:

NOTIFY pgrst, 'reload schema';

Additional Complication
The Supabase SQL Editor intermittently returned:

Backend error! Retry your query

when executing the GRANT statement.

The SQL itself was valid. Retrying the same statement eventually succeeded.

Result
The underlying PostgreSQL permission problem was addressed.

However, REST-level access and reliable Agent-level querying are separate concerns. The Agent integration still required the dedicated custom Supabase component described in Issue 1.

6. Langflow Container Failed to Start: Username and password must be set
Error
The Langflow container failed during startup with an error similar to:

Missing credentials: username=langflow, password=not set
ValueError: Username and password must be set
Application startup failed. Exiting.
Worker (pid:18) exited with code 3.

Cause
The .env file had:

LANGFLOW_AUTO_LOGIN=false

but LANGFLOW_SUPERUSER_PASSWORD was empty or unset.

When automatic login is disabled, Langflow requires valid superuser credentials.

Fix
The following variables were configured together:

LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=langflow
LANGFLOW_SUPERUSER_PASSWORD=<real-password>

Important Docker Detail
Updating .env does not automatically update an already-created Docker container.

The container must be removed and recreated so the new environment variables are loaded.

For example:

docker rm -f langflow-jira

followed by starting the container again with the updated .env.

Result
Langflow successfully started with authentication enabled.

Architecture Decisions
7. Replaced RAG with Agentic File Reading
Problem
The original plan was to create a traditional RAG/vector-search knowledge base for runbooks and postmortems.

This introduced an additional requirement: an embedding model/provider.

Investigation
Several options were considered:

Groq does not provide embedding models.
The previously used Hugging Face inference approach was not suitable for the required embedding workflow.
Self-hosting Ollama with nomic-embed-text was considered.
Ollama Complication
Using Ollama with a containerized Langflow instance introduced additional Docker-to-host networking requirements.

A container cannot normally reach a host service through:

localhost

from inside the container.

The setup would require host gateway configuration such as:

--add-host=host.docker.internal:host-gateway

and additional Langflow SSRF allow-list configuration.

Architectural Decision
The knowledge base contained only a small, static set of documents.

Instead of introducing a complete embedding/vector-search pipeline, the architecture was simplified to an agentic file-reading approach.

The Agent can call a Read File tool when it needs information from a runbook or postmortem.

Reasoning
For a small number of static documents, this approach:

Removes the embedding-model dependency
Removes vector database complexity
Avoids additional Docker networking
Reduces configuration
Is easier to debug
Is sufficient for the current document count
Result
The project avoided unnecessary RAG infrastructure while still allowing the Agent to access runbooks and postmortems on demand.

Key Lessons
The main engineering lessons from these issues were:

Do not assume a component that works standalone will behave identically as an Agent Tool.
Keep credentials inside backend/custom-component code rather than exposing them through LLM-facing tool inputs.
Mounting a custom component directory is not always enough; the application must also know where to discover it.
Do not treat an application's internal database as the only backup of important configuration.
Export visual/low-code workflows into version-controlled files.
RLS policies and PostgreSQL privileges are separate layers in Supabase.
Docker containers must be recreated when environment variables change.
Prefer the simplest architecture that solves the actual problem instead of adding infrastructure unnecessarily.