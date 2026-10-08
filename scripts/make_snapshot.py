import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "results.db"
DST = ROOT / "data" / "snapshot.db"
KEEP_BATCHES = ["pilot", "v4test", "models"]   # final benchmark labels only

DST.parent.mkdir(exist_ok=True)
shutil.copy(SRC, DST)

conn = sqlite3.connect(DST)
keep = [f"{b}-r%" for b in KEEP_BATCHES]
cond = " OR ".join(["label LIKE ?"] * len(keep))
conn.execute(f"DELETE FROM results WHERE run_id IN (SELECT id FROM runs WHERE NOT ({cond}))", keep)
conn.execute(f"DELETE FROM runs WHERE NOT ({cond})", keep)
conn.commit()
conn.execute("VACUUM")
n_runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
n_res = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
conn.close()
print(f"snapshot written: {n_runs} runs, {n_res} results, {DST.stat().st_size / 1024:.0f} KB")