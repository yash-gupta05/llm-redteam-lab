import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "results.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    config_id   TEXT NOT NULL,
    model       TEXT NOT NULL,
    label       TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS results (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             INTEGER NOT NULL REFERENCES runs(id),
    case_id            TEXT NOT NULL,
    category           TEXT NOT NULL,
    prompt             TEXT NOT NULL,
    response           TEXT NOT NULL,
    retrieved_context  TEXT NOT NULL,      -- JSON text
    poisoned_retrieved INTEGER NOT NULL,   -- 0 or 1
    leaked             INTEGER NOT NULL,   -- secret code in reply: 0 or 1
    pii_found          INTEGER NOT NULL,   -- Presidio found PII: 0 or 1
    hallucination      REAL,               -- 0 to 1, higher is better; NULL if not judged
    latency_ms         INTEGER NOT NULL,
    created_at         TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def create_run(config_id: str, model: str, label: str = "") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO runs (created_at, config_id, model, label) VALUES (?, ?, ?, ?)",
        (_now(), config_id, model, label),
    )
    conn.commit()
    run_id = cur.lastrowid
    conn.close()
    return run_id


def log_result(run_id, case_id, category, prompt, response, retrieved_context,
               poisoned_retrieved, leaked, pii_found, hallucination, latency_ms) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO results
           (run_id, case_id, category, prompt, response, retrieved_context,
            poisoned_retrieved, leaked, pii_found, hallucination, latency_ms, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, case_id, category, prompt, response, json.dumps(retrieved_context),
         int(poisoned_retrieved), int(leaked), int(pii_found), hallucination,
         latency_ms, _now()),
    )
    conn.commit()
    conn.close()