import json
import sqlite3
import uuid

DB_PATH = "/app/langflow/langflow.db"
JSON_PATH = "/app/langflow/it-triage-agent-flow.json"

with open(JSON_PATH) as f:
    exported = json.load(f)

# The exported file's top-level "data" key holds the actual flow diagram
# (nodes/edges) that Langflow's flow.data column expects.
flow_data = exported.get("data", exported)

conn = sqlite3.connect(DB_PATH)

# Find the langflow user and the "Starter Project" folder to attach the flow to
user_row = conn.execute("SELECT id FROM user WHERE username = 'langflow'").fetchone()
folder_row = conn.execute("SELECT id FROM folder WHERE name = 'Starter Project'").fetchone()

if not user_row:
    raise RuntimeError("Could not find user 'langflow' in the database.")
if not folder_row:
    raise RuntimeError("Could not find folder 'Starter Project' in the database.")

user_id = user_row[0]
folder_id = folder_row[0]
new_flow_id = uuid.uuid4().hex

conn.execute(
    """
    INSERT INTO flow (
        id, name, description, data, user_id, folder_id,
        access_type, flow_type, is_component, webhook,
        mcp_enabled, locked, a2a_enabled
    )
    VALUES (?, ?, ?, ?, ?, ?, 'PRIVATE', 'workflow', 0, 0, 0, 0, 0)
    """,
    (
        new_flow_id,
        "IT-triage-agent-restored",
        "Restored from flows/it-triage-agent-flow.json",
        json.dumps(flow_data),
        user_id,
        folder_id,
    ),
)

conn.commit()
conn.close()

print("Restored flow with id:", new_flow_id)