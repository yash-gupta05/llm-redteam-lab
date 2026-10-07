import sqlite3

conn = sqlite3.connect("results.db")
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT run_id, case_id, leaked, response FROM results "
    "WHERE case_id = ? AND run_id IN (?, ?)",
    ("d7", 1, 3),
).fetchall()

for r in rows:
    print(f"run {r['run_id']} {r['case_id']} leaked={r['leaked']}")
    print("   ", r["response"][:200].replace("\n", " "))