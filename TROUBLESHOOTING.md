# Troubleshooting Log

Real issues encountered while building this project, how they were diagnosed, and how they were resolved. Kept as a practical reference for anyone running into similar problems with Langflow, Supabase, Docker, or this stack in general.

| # | Issue | Severity |
|---|---|---|
| [1](#1-jiraslacksupabase-integration-generic-api-request-failed-in-agent-tool-mode) | Generic API Request failed in Agent Tool Mode | Critical |
| [2](#2-lost-the-entire-wired-flow-after-a-database-swap) | Lost the entire wired flow after a database swap | Critical |
| [3](#3-langflow-ui-showed-create-your-first-flow-despite-existing-flows) | UI showed "Create your first flow" despite existing data | High |
| [4](#4-custom-components-not-showing-up-in-the-sidebar) | Custom components not showing up in the sidebar | High |
| [5](#5-supabase-rest-api-returned-42501-permission-denied) | Supabase REST API returned `42501: permission denied` | Medium |
| [6](#6-langflow-container-failed-to-start) | Langflow container failed to start | Medium |
| [7](#7-architecture-decision-replaced-rag-with-agentic-file-reading) | Replaced RAG with agentic file reading | Design decision |
| [8](#8-github-actions-workflow-failed-with-zero-jobs-created) | GitHub Actions workflow failed with zero jobs created | High |
| [9](#9-docker-build-failed-dockerfile-no-such-file-or-directory) | Docker build failed: `Dockerfile: no such file or directory` | Medium |
| [10](#10-docker-compose-up-failed-port-5000-already-allocated) | `docker compose up` failed: port 5000 already allocated | Medium |
| [11](#11-github-folder-not-tracked-push-succeeded-but-no-workflow-ran) | `.github/` folder not tracked — push succeeded, no workflow ran | Medium |
| [12](#12-pip-install-blocked-by-pep-668-externally-managed-environment) | `pip install` blocked by PEP 668 on Debian/Ubuntu | Low |
| [13](#13-heredoc-terminator-mangled-when-pasting-into-terminal) | Heredoc terminator mangled when pasting into terminal | Low |
| [14](#14-curl-recv-failure-connection-reset-by-peer-right-after-compose-up) | `curl: (56) Recv failure` right after `docker compose up` | Low |
| [15](#15-langflow-flow-not-rendering-after-db-restore-across-versions) | Langflow flow not rendering after DB restore across versions | Critical |
| [16](#16-prometheus-target-down--app-not-resolvable-from-monitoring-container) | Prometheus target down — app not resolvable from monitoring container | Low |

---

## 1. Jira/Slack/Supabase integration: generic API Request failed in Agent Tool Mode

**Severity: Critical — the single most time-consuming issue in the build.**

The problem affected every external integration: the generic `API Request` component worked correctly when executed standalone, but failed once it was exposed to the Agent as a Tool.

### Attempt 1 — API Request component, URL mode
The Jira REST endpoint, and separately the Supabase REST endpoint, were configured using the component's URL and authentication/header fields.

- Worked correctly when executed by itself
- Once connected to the Agent as a Tool, the Agent reported it had no credentials for the service — despite them being visibly configured inside the component

### Attempt 2 — API Request component, cURL mode
A complete cURL command was supplied instead:
```bash
curl -X POST -H "Authorization: Basic ..." ...
```

Same result:
- Worked standalone
- Failed through Agent Tool Mode — auth information wasn't reliably available during the tool call

A separate parsing bug was also found here: a multi-line command using `\` line continuations was misread, with everything after the first `\` appended onto the URL. Rewriting it as a single unbroken line fixed the parsing, but not the underlying Tool Mode auth problem.

### Attempt 3 — Python Interpreter component
Tried Langflow's built-in `Python Interpreter` (`RUN_PYTHON_REPL`) to execute the Jira request as inline Python, hoping to bypass whatever was stripping auth in Tool Mode.

- Not a good fit — designed for quick calculations/scripts with `print()` output, not structured, reusable API integrations with proper error handling
- Did not solve the credential-passing problem either

### Diagnosis
The issue was determined to be how the generic `API Request` component behaves when exposed as an Agent Tool: authentication configured directly on the component isn't reliably available when the LLM invokes it through the tool layer. This was not an incorrect credential for Jira, Slack, or Supabase individually — it was structural.

### Fix — dedicated custom Langflow components
The generic `API Request` approach was abandoned entirely. Dedicated Python components were written under:
```
custom_components/tools/
├── jira_component.py
├── slack_component.py
└── supabase_component.py
```

Each custom component:
- Uses Langflow's `langflow.custom.Component`
- Exposes only meaningful inputs to the LLM, marked `tool_mode=True`
- Reads credentials directly from environment variables inside the component — never exposed through the tool schema
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

**Severity: Critical — real data loss.**

While troubleshooting an unrelated login issue, the Langflow SQLite database was replaced with an older backup to try to recover a different problem. After restoring it, the actual IT Triage Agent flow was gone.

### Backup investigation
Several backup files existed from earlier sessions: `langflow.db.backup`, `langflow_app_data_backup.tar.gz`, and a separate `langflow_data_backup/` directory. Each was checked in turn before assuming the work was unrecoverable.

On Docker Desktop with WSL2, the volume's files aren't directly accessible from the host filesystem the way they would be on native Linux:
```bash
sudo ls -la /var/lib/docker/volumes/langflow_data/_data/
# ls: cannot access '/var/lib/docker/volumes/langflow_data/_data/': No such file or directory
```
`docker cp` had to be used instead to inspect backups without risking the currently running state. To check a backup's contents *without* overwriting the live database, it was copied into the container under a different filename first:
```bash
docker cp ./langflow.db.backup langflow-jira:/app/langflow/langflow.db.test

docker exec langflow-jira python -c "import sqlite3; c=sqlite3.connect('/app/langflow/langflow.db.test'); print(c.execute(\"SELECT id, name, user_id FROM flow WHERE user_id IS NOT NULL\").fetchall()); c.close()"
```
This is the safer pattern: verify what a backup actually contains before committing to a restore, since restoring the wrong one just compounds the problem.

Every backup checked this way — `langflow.db.backup`, the `.tar.gz` archive, and `langflow_data_backup/` — turned out to contain only the default, unmodified "Simple Agent" starter template, not the actual flow with the Jira/Slack/Supabase tools wired in.

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

### Process fix adopted
- Export important flows to JSON regularly and store them in the repo (`flows/it-triage-agent-flow.json`)
- Take dated snapshots of a working `langflow.db` after major milestones, using `docker cp` rather than trying to access the volume directly
- Keep database backups separate from ordinary source-code backups
- Treat anything that only exists inside a running container as ephemeral until it's been exported or version-controlled

---

## 3. Langflow UI showed "Create your first flow" despite existing flows

**Severity: High.**

### Symptom
Opening `http://localhost:7860` showed the user already logged in, but the UI displayed "Create your first flow" even though the SQLite database contained existing flows.

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

### Result
The project/folder and flow relationship was investigated and corrected without deleting existing project data or recreating the Docker volume — preserving the existing work.

---

## 4. Custom components not showing up in the sidebar

**Severity: High.**

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
Mounting the directory isn't enough — Langflow needs to be explicitly told where to look. Setting `LANGFLOW_COMPONENTS_PATH` as a plain environment variable did not work in this version, despite appearing in some documentation.

### Fix
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

**Severity: Medium.**

### Symptom
Requests to `/rest/v1/incidents` returned:
```json
{"code": "42501", "message": "permission denied for table incidents"}
```
The table existed and Row Level Security policies appeared correctly configured (`Allow public read access`, `Allow service role access`).

### Root cause
RLS policies and PostgreSQL table privileges are separate permission layers. Having an appropriate RLS policy does not automatically grant the underlying role the required table privilege — `service_role` also needed an explicit grant.

### Fix
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

**Severity: Medium.**

### Error
```
Missing credentials: username=langflow, password=not set
ValueError: Username and password must be set
Application startup failed. Exiting.
Worker (pid:18) exited with code 3.
```

### Cause
`.env` had `LANGFLOW_AUTO_LOGIN=false` but `LANGFLOW_SUPERUSER_PASSWORD` was empty. When auto-login is disabled, Langflow requires valid superuser credentials.

### Fix
```
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=langflow
LANGFLOW_SUPERUSER_PASSWORD=<a real password>
```

### Important Docker detail
Updating `.env` does not automatically update an already-created container — it must be removed and recreated:
```bash
docker rm -f langflow-jira
# then start again with the updated .env
```

**Result:** Langflow started successfully with authentication enabled.

---

## 7. Architecture decision: replaced RAG with agentic file reading

**Category: Design decision, not a bug.**

### Problem
The original plan was a traditional RAG/vector-search knowledge base for runbooks and postmortems — which required an embedding model provider.

### Investigation
- Groq does not provide embedding models at all
- HuggingFace's inference API was not suitable for the required embedding workflow
- Self-hosting Ollama with `nomic-embed-text` was considered, but introduced Docker-to-host networking complexity: a container can't reach a host service via `localhost`, requiring `--add-host=host.docker.internal:host-gateway` plus additional Langflow SSRF allow-list configuration

### Architectural decision
The knowledge base contained only a small, static set of documents. Rather than introduce a full embedding/vector-search pipeline, the architecture was simplified to agentic file reading — the Agent calls a `Read File` tool on demand.

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

## 8. GitHub Actions workflow failed with zero jobs created

**Severity: High — no logs, no error message, no obvious signal.**

### Symptom
The first push with a new `.github/workflows/ci.yml` produced a run with conclusion `failure` and `0s` elapsed time. The Actions UI showed:
```
✗ This run likely failed because of a workflow file issue.
```
No job names, no steps, no logs — because no jobs were ever created.

### Investigation
The standard log commands returned nothing useful:
```bash
gh run view --log-failed
# failed to get run log: log not found
```
The run metadata was still accessible via the API:
```bash
gh api repos/QandeLand/it-triage-agent/actions/runs/35013296469 --jq '.conclusion, .display_title, .head_commit.message'
# failure
# Add CI workflow for tests and Docker build
# Add CI workflow for tests and Docker build
```
Critically, the jobs endpoint returned an empty array:
```bash
gh api repos/QandeLand/it-triage-agent/actions/runs/35013296469/jobs --jq '.[] | {name, conclusion}'
# expected an object but got: array ([])
```
An empty jobs array on a non-empty run is the signature of a workflow file that failed to parse.

### Root cause
The file had been edited in `nano` and the content had been duplicated several times — the same workflow YAML written back-to-back inside the same file.
```bash
wc -l .github/workflows/ci.yml
# 257

head -60 .github/workflows/ci.yml
# (showed the workflow once, then starting over: "name: CI" appearing again)
```
The file was ~5 copies of a ~50-line workflow concatenated. YAML only permits one document per file unless separated by `---`, so validation failed at the first line of the second copy:
```
yaml.scanner.ScannerError: mapping values are not allowed here
  in ".github/workflows/ci.yml", line 104, column 42
```
The generic `python3 -c "import yaml; yaml.safe_load(...)"` earlier had passed because the file being validated at that moment was a different, single-copy version — the broken multi-copy version was the one that got committed.

### Fix
Rewrote the file from scratch using a `cat > file << 'EOF'` heredoc (see Issue 13 for a follow-up gotcha), then validated with a schema assertion, not just generic YAML parsing:
```bash
python3 -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
assert 'jobs' in d, 'no jobs key'
assert 'test' in d['jobs'], 'no test job'
assert 'docker' in d['jobs'], 'no docker job'
assert 'cache-to' in d['jobs']['docker']['steps'][-1]['with']
print('schema OK')
"
```
The commit diff told the story:
```
1 file changed, 1 insertion(+), 206 deletions(-)
```

### Result
The next run was green:
```
✓ Test app in 10s
✓ Build Docker image in 21s
✓ Run CI completed with 'success'
```
Both the broken commit and the fixed commit were kept in history — a visible before/after on the Actions tab.

### Lesson
`python3 -c "import yaml; yaml.safe_load(...)"` passing is not sufficient validation for a GitHub Actions workflow. Generic YAML parsing doesn't know about the Actions schema. Always assert the specific structure you expect (`jobs`, `steps`, required keys) before committing. And when a run has zero jobs, don't chase logs — inspect the run metadata via the API; an empty jobs array means the file itself never parsed.

---

## 9. Docker build failed: `Dockerfile: no such file or directory`

**Severity: Medium.**

### Symptom
```bash
docker build -t it-triage-agent .
# ERROR: failed to build: failed to solve: failed to read dockerfile:
#   open Dockerfile: no such file or directory
```

### Cause
The command was run from the repository root, but the Dockerfile lives in a subdirectory:
```
it-triage-agent/
├── app/
│   └── Dockerfile   ← here
├── monitoring/
└── ...
```
`docker build .` uses the current directory as both the build context and the default Dockerfile location. From the repo root, there was no Dockerfile at that path.

### Investigation
```bash
ls -la ./Dockerfile     # nothing
ls -la ./app/Dockerfile     # exists
```

### Fix — two valid approaches

**Option A: build from the subdirectory (simple)**
```bash
cd app
docker build -t it-triage-agent .
```
The `app/` folder becomes the build context, and any `COPY` instructions inside the Dockerfile are resolved relative to `app/`.

**Option B: build from the root with `-f` (needed for Compose)**
```bash
docker build -f app/Dockerfile -t it-triage-agent .
```
With `-f`, the path to the Dockerfile is explicit — but the build context is still the current directory, so any `COPY requirements.txt .` inside the Dockerfile resolves against the repo root, not `app/`. This breaks unless paths are adjusted.

### What Compose does differently
`docker-compose.yml` disambiguates both:
```yaml
services:
  app:
    build:
      context: ./app
      dockerfile: Dockerfile
```
`context: ./app` — the build context is `app/`
`dockerfile: Dockerfile` — the file is resolved relative to the context, not the compose file

This is why the same build works under Compose but not a bare `docker build .` from the root.

### Result
`docker compose up --build` succeeded with the context/Dockerfile split as above.

### Lesson
`docker build .` conflates three things: build context, Dockerfile location, and working directory. Compose separates them explicitly. Whenever a project moves the Dockerfile off the root, either build from inside its directory or supply `-f` and verify any `COPY` paths still resolve correctly.

---

## 10. `docker compose up` failed: port 5000 already allocated

**Severity: Medium.**

### Symptom
```bash
docker compose up --build -d
# Error response from daemon: failed to set up container networking:
#   driver failed programming external connectivity on endpoint it-triage-agent:
#   Bind for 0.0.0.0:5000 failed: port is already allocated
```
The container failed to start, but `curl localhost:5000/health` still returned `{"status":"ok"}` — which was confusing until the cause was identified.

### Cause
A previous `docker run -d --rm -p 5000:5000 --name it-triage it-triage-agent` had been started manually earlier in the session. It was still running and holding the host-side port 5000. A second orphaned container (`mystifying_boyd`) from an even earlier `docker run` was also running without a port mapping.

Docker assigns host ports on a first-come basis. The first process to bind `0.0.0.0:5000` wins, and Compose can't override that.

The `curl` that "worked" was hitting the still-running manual container, not the compose-managed one — masking the failure until `docker ps` was checked.

### Investigation
```bash
docker ps
# CONTAINER ID   IMAGE             ...   PORTS                     NAMES
# acfa52a5fa9f   it-triage-agent   ...   0.0.0.0:5000->5000/tcp    it-triage
# ca511bfb4928   it-triage-agent   ...   5000/tcp                  mystifying_boyd
# eaffb708833f   prom/prometheus   ...   0.0.0.0:9090->9090/tcp    prometheus-demo
```
Two orphaned containers from earlier `docker run` invocations, both still alive.

### Fix
Stop the conflicting containers before bringing the Compose stack up:
```bash
docker stop it-triage mystifying_boyd

docker compose up --build -d
docker compose ps
# NAME              ...   STATUS                   PORTS
# it-triage-agent   ...   Up X seconds (healthy)   0.0.0.0:5000->5000/tcp
```

### Result
Compose acquired the port cleanly, and `docker compose ps` showed `(healthy)`.

### Lesson
When migrating from ad-hoc `docker run` to Compose, always `docker stop` the previously launched containers first. A `curl` succeeding after a Compose error is a red flag — it usually means something else is answering on that port, not the service you just tried to start. `docker ps` is the ground truth, not the client-side request.

---

## 11. `.github/` folder not tracked — push succeeded, but no workflow ran

**Severity: Medium.**

### Symptom
A workflow file was created at `.github/workflows/ci.yml`, a `git add .github/ .gitignore`, `git commit`, and `git push` were all executed successfully — with the familiar "writing objects... done" output. But:
```bash
gh run list --limit 3
# no runs found
```
And `git log` showed the most recent commit was the previous one (the Compose commit), not the CI commit.

### Investigation
```bash
git log --oneline -3
# 823fcd8 (HEAD -> main, origin/main) Add docker-compose for local dev
# f8bcdc1 Add monitoring configuration
# f71904b Add app tests

git status
# Changes not staged for commit:
#   modified: .gitignore
# Untracked files:
#   .github/
```
The `.github/` directory was still untracked — the `git add` had either been run from the wrong directory, mis-typed, or the shell hadn't executed it as expected. Nothing was actually staged, so nothing was committed, so nothing was pushed.

### Root cause
Silent no-op. There was no error message from any of the commands — `git add` on a path that isn't a valid match is not an error, and `git commit` on an empty index prints a message that can be missed ("nothing added to commit but untracked files present").

This is one of the most dangerous classes of bug in git workflows: a push that succeeds without containing the change you intended.

### Fix
```bash
git add .github/ .gitignore

# verify staging before commit — this is the step that was skipped
git status
# Changes to be committed:
#   new file:   .github/workflows/ci.yml
#   modified:   .gitignore

git commit -m "Add CI workflow for tests and Docker build"
git push

git log --oneline -3
# c68ed0b (HEAD -> main, origin/main) Add CI workflow for tests and Docker build
# 823fcd8 Add docker-compose for local dev
# f8bcdc1 Add monitoring configuration
```

### Result
The commit landed, the push went through, and `gh run list` immediately showed a new run.

### Lesson
`git add` + `git commit` + `git push` all "succeeding" does not mean the intended change is in the commit. Always inspect staging between add and commit:
```bash
git status
git diff --cached --stat
```
For pipelines and CI, a missing commit is often silent until a downstream signal (an Actions run that never appears) reveals it. Never assume; always verify the thing you're waiting for actually exists.

---

## 12. `pip install` blocked by PEP 668 (externally-managed-environment)

**Severity: Low — but easy to solve incorrectly.**

### Symptom
```bash
pip install -r requirements.txt pytest
# error: externally-managed-environment
# × This environment is externally managed
# ╰─> To install Python packages system-wide, try apt install python3-xyz...
# hint: See PEP 668 for the detailed specification.
```

### Cause
Debian 12 (and Ubuntu 23.04+) enforce PEP 668: the system Python is marked as "externally managed" so `pip` refuses to install packages directly into it. The intent is to prevent users from breaking OS-level Python tooling (which the OS package manager `apt` is responsible for).

The default workaround suggested by some guides — `pip install --break-system-packages` — is dangerous and should not be used. It's a foot-gun that can leave the OS with a broken Python that `apt` can no longer fix.

### Fix — use a virtual environment
```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pytest
python -m pytest -v
# 4 passed in 0.21s
deactivate
```
Add `.venv/` to `.gitignore` so it's never committed:
```bash
echo ".venv/" >> .gitignore
```

### Result
Tests ran locally in an isolated environment identical to what CI uses (both use the same Python version and the same pinned `requirements.txt`).

### Lesson
PEP 668 isn't an obstacle — it's a signal that the correct pattern is a virtual environment (or a container). The `--break-system-packages` flag should be treated as a red flag in any documentation that recommends it. For CI, this issue is moot — GitHub Actions runners are ephemeral and don't have the PEP 668 protections on the default Python install path.

---

## 13. Heredoc terminator mangled when pasting into terminal

**Severity: Low — but produced a silently truncated file.**

### Symptom
A multi-line heredoc was used to rewrite `.github/workflows/ci.yml`:
```bash
cat > .github/workflows/ci.yml <<'EOF'
name: CI
...
      - name: Build image
        uses: docker/build-push-action@v6
        with:
EOF       cache-to: type=gha,mode=max
```
The final line — `EOF       cache-to: type=gha,mode=max` — shows the heredoc terminator and the last YAML directive ended up on the same visual line. This is a terminal paste artifact: when pasting multi-line content, some terminals mangle the newline handling around the terminator.

### Impact
`python3 -c "import yaml; yaml.safe_load(...)"` passed, because `with:` with no children is syntactically valid YAML — it parses as `{'with': None}`.

But the actual file was truncated: the `docker build-push-action` step had no `context`, `file`, `push`, `tags`, `cache-from`, or `cache-to` values. It would have failed on the next commit with a schema error, not a parse error.

### Detection
```bash
tail -20 .github/workflows/ci.yml
# the file ended at "with:" with nothing underneath

wc -l .github/workflows/ci.yml
# fewer lines than expected
```

### Fix — replace the file via a Python heredoc
Writing the content from within Python avoids the shell pasting problem entirely:
```bash
python3 << 'PYEOF'
content = """name: CI
...
        with:
          context: ./app
          file: ./app/Dockerfile
          push: false
          tags: it-triage-agent:ci
          cache-from: type=gha
          cache-to: type=gha,mode=max
"""
open('.github/workflows/ci.yml', 'w').write(content)
print("written")
PYEOF
```

### Result
The file was written in full. Verified with structural assertions rather than just "valid YAML":
```bash
python3 -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
assert 'cache-to' in d['jobs']['docker']['steps'][-1]['with']
print('schema OK')
"
```

### Lesson
Heredocs are convenient but fragile when pasted through terminal emulators. Two defenses:

After writing a file this way, check the tail and count lines — don't trust that the paste delivered everything.

Validate with structural assertions, not just generic parsers. YAML saying "valid" doesn't mean the file says what you intended.

For anything important, prefer writing through Python (`open(...).write(...)`) over `cat << EOF` in the terminal.

---

## 14. `curl: (56) Recv failure: Connection reset by peer` right after `docker compose up`

**Severity: Low — timing, not a bug.**

### Symptom
Immediately after `docker compose up --build -d`, this sequence was run:
```bash
docker compose ps
# NAME              ...   STATUS
# it-triage-agent   ...   Up 1 second (health: starting)

curl localhost:5000/health
# curl: (56) Recv failure: Connection reset by peer
```
The container was "up" but not yet answering requests.

### Cause
`docker compose up -d` returns as soon as the container process starts, not when the application inside is ready to serve. Gunicorn takes a few seconds to boot workers and bind the port. During that window, the TCP connection is refused or reset.

The `(health: starting)` status is Docker's way of saying: the container is running, but the `HEALTHCHECK` instruction hasn't seen a healthy response yet.

### Fix — poll or wait for the health status
Quick version:
```bash
sleep 5
docker compose ps    # now shows (healthy)
curl localhost:5000/health
# {"status":"ok"}
```
Better version — wait for the healthy status programmatically:
```bash
until [ "$(docker inspect --format '{{.State.Health.Status}}' it-triage-agent)" = "healthy" ]; do
  sleep 1
done
curl localhost:5000/health
```
Or with Compose v2's built-in wait:
```bash
docker compose up -d --wait
```
`--wait` blocks until all services are running or healthy before returning.

### Result
`curl` returned `{"status":"ok"}` cleanly once the health status transitioned to `healthy`.

### Lesson
"Up" does not mean "ready." Any process, however fast, has a startup window between container start and application readiness. Health checks (and `docker compose up --wait`) exist specifically to close this gap. In a real deployment pipeline, an immediate `curl` (or a load balancer health check) against a freshly-started container will periodically fail — plan for a readiness gate, not an assumption of instant availability.

---

## 15. Langflow flow not rendering after DB restore across versions

**Severity: Critical — cost several hours.**

### Symptom

After restoring a `langflow.db` backup into a newer Langflow container, flows existed in the DB (verified via SQLite) but did not appear in the sidebar. Navigating to the flow URL produced a blank "Untitled Flow" canvas. The sidebar alternated between "Create your first flow" and "Create a new project" regardless of DB contents.

### What was tried and did NOT fix it

- Fixing `tags = None` → `'[]'`
- Fixing `mcp_enabled = 0` → `1`
- Sanitizing render state (`viewport`, `measured` fields)
- Stripping custom tool nodes (`ext:tools:*@extra`)
- Stripping `note` nodes
- Merging flow data into a known-working flow row
- Copying all row metadata from a working flow
- Restoring from multiple DB backups
- `chmod` fixing the DB file for write access
- Full container + volume wipe, fresh restore from backup

### Root cause

The flow's `data` JSON was authored under Langflow `1.12.1` and stored with `lf_version: "1.12.1"` on each node. Restoring the DB into a `:latest` container ran Alembic schema migrations that rewrote portions of the flow structure. The React frontend silently fails to render flows whose stored node schema does not match what the current UI expects — no error in the browser console, no error in the container logs.

The failure is silent: the API returns the flow row correctly, the DB has valid JSON, but the frontend canvas refuses to draw.

### What actually worked

**Rebuilding the flow in the UI.** The valuable content (custom Python tools, agent system prompt, credentials) was already preserved in git and in `.env`. Only the visual wiring needed to be redone — 10 minutes of drag-and-drop in a fresh Blank Flow.

The custom components loaded correctly (the container's `--components-path` flag was already correct), the Agent was reconfigured with Groq + the saved system prompt, tools were rewired to the Agent's Tools input, the flow was tested in the Playground (P1 → Jira + Slack, P4 → no action), exported, and committed.

### Lesson

A Langflow flow's `.db` file is **not portable across Langflow versions**. The DB is a cache, not a source of truth. For anything important:

1. Export the flow to JSON after every session
2. Commit the JSON to git
3. Treat the `.db` as disposable
4. If you must restore across versions, rebuild in the UI rather than debugging the data layer

Debugging the frontend's silent failure is not worth the time — the rebuild is faster than the diagnosis.

---

## 16. Prometheus target `down` — app not resolvable from monitoring container

**Severity: Low.**

### Symptom

Prometheus running as `prometheus-demo`, config pointing at `app:5000`, but the target shows:

```
payment-service -> down
```

`curl http://localhost:9090/api/v1/targets` returns the target with `health: down` and `lastError: no such host`.

### Cause

The Prometheus container was started on Docker's default bridge network. The Flask app runs on the compose network `it-triage-agent_default`. Docker DNS only resolves container names within the same network — so from Prometheus's perspective, `app` doesn't exist.

### What did NOT fix it

- Adding `--add-host=host.docker.internal:host-gateway` (only relevant if using `host.docker.internal` as the target, not `app`)
- Restarting Prometheus without changing its network
- Editing `prometheus.yml` to reference `localhost` (worse — inside the container, `localhost` is the container itself)

### Fix

Attach Prometheus to the compose network:

```bash
docker rm -f prometheus-demo

docker run -d \
  --name prometheus-demo \
  -p 9090:9090 \
  --network it-triage-agent_default \
  -v "$(pwd)/monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  -v "$(pwd)/monitoring/prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro" \
  prom/prometheus:latest \
  --config.file=/etc/prometheus/prometheus.yml
```

### Result

```
payment-service -> up
prometheus -> up
```

### Lesson

In Docker, hostname resolution is scoped to the network a container is attached to. Two containers on different networks can't reach each other by name even though they're on the same host. For service-to-service discovery, attach both to a shared user-defined network (preferred) or use `host.docker.internal` with the appropriate flag. Compose does this automatically for services declared in the same `docker-compose.yml` — but only for containers Compose manages.

---

## Key lessons

1. Don't assume a component that works standalone will behave identically as an Agent Tool.
2. Keep credentials inside backend/custom-component code — never expose them through LLM-facing tool inputs.
3. Mounting a custom component directory isn't always enough; the application must also be told where to discover it.
4. Don't treat an application's internal database as the only backup of important configuration — export visual/low-code workflows into version-controlled files.
5. RLS policies and PostgreSQL privileges are separate layers in Supabase.
6. Docker containers must be recreated when environment variables change — editing `.env` alone isn't enough.
7. Prefer the simplest architecture that solves the actual problem instead of adding infrastructure unnecessarily.
8. `python3 -c "import yaml; yaml.safe_load(...)"` passing is not sufficient validation for a GitHub Actions workflow — assert the specific structure you expect before committing.
9. When a CI run has zero jobs, don't chase logs — the run metadata API (`gh api .../jobs`) will show an empty array, which means the workflow file never parsed.
10. `docker build .` conflates context, Dockerfile location, and working directory. Compose separates them via `context:` and `dockerfile:` — use Compose's split whenever the Dockerfile lives off the repository root.
11. When migrating from `docker run` to `docker compose`, stop the old containers first. A `curl` succeeding right after a Compose failure is a red flag — something else is on the port.
12. `git add` + `git commit` + `git push` all printing success does not mean the change was committed. Always run `git status` or `git diff --cached --stat` between add and commit.
13. PEP 668 is a signal to use a virtual environment, not a signal to use `--break-system-packages`. Never break the system Python.
14. Heredocs pasted through a terminal can silently truncate. Verify the tail and line count after writing, and prefer `python3 -c "open(..., 'w').write(...)"` for anything important.
15. "Up" is not "ready." Health checks and `docker compose up --wait` exist to close the gap between container start and application readiness.
16. Langflow DBs are not portable across versions. The DB is a cache; the JSON export is the source of truth.
17. Docker hostname resolution is network-scoped. Containers on different networks can't reach each other by name, even on the same host.