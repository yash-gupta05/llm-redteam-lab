import json
import sqlite3
import sys

sys.path.insert(0, "mcp_server")
from scoring import check_pii

conn = sqlite3.connect("results.db")
conn.row_factory = sqlite3.Row


def fetch(config_id, case_ids):
    marks = ",".join("?" * len(case_ids))
    return conn.execute(
        f"""SELECT r.case_id, r.prompt, r.response, r.leaked, r.retrieved_context
            FROM results r JOIN runs u ON u.id = r.run_id
            WHERE u.config_id = ? AND u.label = 'pilot-r1' AND r.case_id IN ({marks})
            ORDER BY r.id""",
        (config_id, *case_ids),
    ).fetchall()


print("=== v3 indirect answers (does it still give the refund facts?) ===")
ids = ["i1", "i2", "i3", "i4", "i5"] + [f"g-indirect-{i}" for i in range(1, 7)]
for r in fetch("v3", ids):
    print(f"\n[{r['case_id']}] leaked={r['leaked']}")
    print("PROMPT:  ", r["prompt"])
    print("RESPONSE:", r["response"][:300].replace("\n", " "))

print("\n\n=== v2 g-pii-6 ===")
for r in fetch("v2", ["g-pii-6"]):
    print("PROMPT:  ", r["prompt"])
    print("RESPONSE:", r["response"])
    out = check_pii(r["response"], json.loads(r["retrieved_context"]), r["prompt"])
    print("FLAGGED: ", out["entities"])