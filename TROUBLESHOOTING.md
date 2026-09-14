# Troubleshooting Log

Real issues hit while building this project, and how they were diagnosed and fixed. Kept here in case anyone else runs into the same things with Langflow, Supabase, or this stack in general.

---

## 1. Langflow container crash: `Username and password must be set`

**Error:**

Missing credentials: username=langflow, password=not set
ValueError: Username and password must be set
Application startup failed. Exiting.


**Cause:** `LANGFLOW_SUPERUSER_PASSWORD` was empty in `.env`. Langflow requires this when `LANGFLOW_AUTO_LOGIN=false` (the default).

**Fix:** Set all three in `.env`:

LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=langflow
LANGFLOW_SUPERUSER_PASSWORD=<a real password>

Recreate the container after changing `.env` — an already-running container won't pick up new values.

---

## 2. Custom components not showing up in the sidebar

**Symptom:** `custom_components/` correctly mounted into the container (confirmed via `docker exec langflow-jira ls -la /app/custom_components/tools/`), files present and valid — but searching for them in Langflow's UI returned nothing.

**Investigation:**
```bash
docker exec langflow-jira env | grep -i LANGFLOW_COMPONENTS
# → empty
```

**Root cause:** Mounting the folder isn't enough — Langflow needs to be explicitly told where to look. Setting `-e LANGFLOW_COMPONENTS_PATH=...` as an environment variable did *not* work in this version.

**Fix that actually worked:** pass it as a CLI argument to the `langflow run` command itself:
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
Found the correct flag name via `docker exec langflow-jira langflow run --help | grep -A5 components-path`.

---

## 3. `InvalidSignatureError: Signature verification failed`

**Symptom:** After swapping the Langflow SQLite database (restoring from a backup), the app started throwing JWT signature errors and the browser session appeared broken.

**Cause:** Each Langflow database has its own `secret_key` used to sign JWTs. Restoring an old database file (with a different secret key) while the browser still holds a JWT signed by the *previous* key causes verification to fail.

**Fix:** Log out / clear the site's cookies, or use a fresh incognito window, after swapping the underlying database.

---

## 4. API Request component works standalone but fails silently in Agent Tool Mode

**Symptom:** A generic `API Request` component with a complete, correct cURL command (real Jira URL, Basic Auth header, JSON body) worked when triggered directly, but once connected to an Agent as a Tool, the agent would respond *"I don't have Jira credentials"* — even though the credentials were right there in the component.

**Root cause:** This is a documented Langflow limitation — enabling Tool Mode on the generic `API Request` component changes what's exposed to the LLM; the underlying cURL/headers aren't reliably passed through the tool-call layer.

**Fix:** Don't use the generic `API Request` component as an Agent tool for anything requiring custom auth headers. Instead, write a small native Python custom component (`langflow.custom.Component`) with clean `tool_mode=True` inputs. The LLM fills in the meaningful fields (e.g. `summary`, `description`) and the component handles authentication internally via environment variables — the LLM never sees or needs the actual secret.

---

## 5. No free embedding model provider available

**Symptom:** Wanted to build a proper RAG/vector-search knowledge base, but:
- Groq doesn't offer embedding models at all (chat/completions only)
- HuggingFace's public inference API no longer supports embeddings (deprecated `api-inference.huggingface.co`, and their newer router endpoint is chat-only)

**Workaround considered:** Self-hosting Ollama locally with `nomic-embed-text` — works, but introduces Docker-to-host networking complexity (`--add-host=host.docker.internal:host-gateway` plus `LANGFLOW_SSRF_ALLOWED_HOSTS`).

**Final approach used:** Skipped vector search entirely for a small, static document set. Used an "agentic file reading" pattern instead — a `Read File` tool the agent calls on demand — which is simpler and sufficient at this scale.

---

## 6. Supabase `42501: permission denied for table incidents`

**Symptom:** REST API calls to `/rest/v1/incidents` failed with a permission error, despite the table existing and RLS policies looking correct (`Allow public read access` for `anon`, `Allow service role access` for `service_role`).

**Root cause:** RLS policies alone aren't sufficient — the underlying PostgreSQL role also needs an explicit `GRANT`:
```sql
GRANT SELECT ON public.incidents TO service_role;
```
This is a separate permission layer from RLS. Also required, after granting:
```sql
NOTIFY pgrst, 'reload schema';
```
to force PostgREST to pick up the change without restarting.

**Note:** Supabase's SQL Editor intermittently returned `Backend error! Retry your query` on this specific statement — a platform-side issue, not a config mistake. Retrying eventually succeeded.

---

## 7. WSL2 file paths — Downloads folder confusion

**Symptom:** Repeatedly tried to `mv` downloaded files from `~/Downloads` and got `No such file or directory`.

**Cause:** On WSL2, the Linux home directory (`~`) is separate from the Windows filesystem. Browser downloads on Windows land in `/mnt/c/Users/<username>/Downloads/`, not `~/Downloads`. Screenshot tools may also save to a different folder entirely (e.g. `Pictures/Screenshots` rather than `Downloads`).

**Fix:** Always check the actual Windows path:
```bash
find /mnt/c/Users/<username>/Downloads -maxdepth 1 -iname "*.png" -newer <some-reference-file>
```

---

## 8. Docker volumes not visible via direct host path on Docker Desktop/WSL2

**Symptom:** `sudo ls -la /var/lib/docker/volumes/langflow_data/_data/` → `No such file or directory`, even though `docker inspect` confirmed the volume was correctly mounted.

**Cause:** Docker Desktop on WSL2 runs Docker inside its own internal VM — named volumes aren't directly visible on the WSL host filesystem the way they would be on native Linux.

**Fix:** Use `docker cp` to move files in and out of a running container instead of trying to access the volume's files directly from the host:
```bash
docker cp <container>:/app/langflow/langflow.db ./backup.db
docker cp ./somefile.txt <container>:/app/somewhere/
```