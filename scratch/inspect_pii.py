import json
import sqlite3
import sys

sys.path.insert(0, "mcp_server")
from scoring import check_pii

conn = sqlite3.connect("results.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT run_id, case_id, prompt, response, retrieved_context FROM results WHERE pii_found=1"
).fetchall()
for r in rows:
    print(f"--- run {r['run_id']} case {r['case_id']}")
    out = check_pii(r["response"], json.loads(r["retrieved_context"]), r["prompt"])
    for e in out["entities"]:
        print("   FLAGGED:", e)