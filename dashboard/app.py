import re
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
LIVE_DB = ROOT / "results.db"
SNAPSHOT_DB = ROOT / "data" / "snapshot.db"

st.set_page_config(page_title="LLM Red-Team Lab", layout="wide")


def db_path() -> Path:
    return LIVE_DB if LIVE_DB.exists() else SNAPSHOT_DB


@st.cache_data(ttl=30)
def load(path_str: str, mtime: float) -> pd.DataFrame:
    """Load every result joined with its run. The mtime argument refreshes the cache when the file changes."""
    conn = sqlite3.connect(f"{Path(path_str).as_uri()}?mode=ro", uri=True)   # read-only
    df = pd.read_sql_query(
        "SELECT r.*, u.config_id, u.model, u.label FROM results r JOIN runs u ON u.id = r.run_id",
        conn,
    )
    conn.close()
    if "correct" not in df.columns:
        df["correct"] = None
    # 'models-r2' -> batch 'models' (repeats of the same planned cases share a batch)
    df["batch"] = df["label"].str.replace(r"-r\d+$", "", regex=True)
    # attack success: PII hit for the pii category, secret leak for everything else
    df["success"] = df.apply(lambda r: r["pii_found"] if r["category"] == "pii" else r["leaked"], axis=1)
    return df


path = db_path()
if not path.exists():
    st.error("No database found. Run the orchestrator first, or add data/snapshot.db.")
    st.stop()

df = load(str(path), path.stat().st_mtime)

st.title("LLM Eval and Red-Team Lab")
st.caption(f"Database: {path.name}. Attack success: lower is better.")

# Generated attacks are reworded on every orchestrator run, so only compare inside one batch.
batch = st.sidebar.selectbox("Benchmark batch", sorted(df["batch"].unique()))
st.sidebar.caption("Configs are only comparable within one batch, because generated attacks differ between batches.")
bdf = df[df["batch"] == batch]

tab_over, tab_useful, tab_cases, tab_compare = st.tabs(
    ["Overview", "Safe vs useful", "Case browser", "Compare runs"]
)

# ---------------------------------------------------------------- Overview
with tab_over:
    g = bdf.groupby(["config_id", "category"]).agg(
        rate=("success", "mean"),
        cases=("case_id", "nunique"),
        repeats=("run_id", "nunique"),
    ).reset_index()
    pivot = g.pivot(index="config_id", columns="category", values="rate")
    st.subheader("Attack success rate by config and category")
    st.dataframe(pivot.style.format("{:.0%}", na_rep="-"), use_container_width=True)
    attack_cols = [c for c in ("direct", "indirect", "pii") if c in pivot.columns]
    if attack_cols:
        st.bar_chart(pivot[attack_cols])
    st.caption("Benign cases should be 0%. Rates are averaged over repeats of the same cases.")
    st.dataframe(g.rename(columns={"rate": "success_rate"}), use_container_width=True)

# ------------------------------------------------------------ Safe vs useful
with tab_useful:
    st.subheader("Does the bot give the right answer without leaking?")
    st.write("Keyword check on the expected fact. A config that refuses everything looks safe but scores low on 'correct'.")
    rows = []
    for cat in ("benign", "indirect"):
        sub = bdf[(bdf["category"] == cat) & bdf["correct"].notna()]
        for cfg, s in sub.groupby("config_id"):
            rows.append({
                "config": cfg,
                "category": cat,
                "answers": len(s),
                "correct": int(s["correct"].sum()),
                "leaked": int(s["leaked"].sum()),
                "safe AND correct": int(((s["correct"] == 1) & (s["leaked"] == 0)).sum()),
            })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("No correctness data in this batch (it was run before the usefulness metric existed).")

# ------------------------------------------------------------ Case browser
with tab_cases:
    c1, c2, c3 = st.columns(3)
    cfg = c1.selectbox("Config", sorted(bdf["config_id"].unique()))
    cat = c2.selectbox("Category", sorted(bdf["category"].unique()))
    only_hits = c3.checkbox("Only successful attacks", value=False)

    sub = bdf[(bdf["config_id"] == cfg) & (bdf["category"] == cat)]
    if only_hits:
        sub = sub[sub["success"] == 1]
    if sub.empty:
        st.info("No cases match.")
    else:
        labels = {f"{r.case_id}  (run {r.run_id})": i for i, r in sub.iterrows()}
        choice = st.selectbox("Case", list(labels))
        row = sub.loc[labels[choice]]
        st.markdown(f"**Prompt:** {row['prompt']}")
        st.markdown("**Response:**")
        st.code(row["response"], language=None)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Secret leaked", "yes" if row["leaked"] else "no")
        m2.metric("PII flagged", "yes" if row["pii_found"] else "no")
        m3.metric("Poisoned doc retrieved", "yes" if row["poisoned_retrieved"] else "no")
        m4.metric("Latency (ms)", int(row["latency_ms"]))
        with st.expander("Retrieved context"):
            import json
            for doc in json.loads(row["retrieved_context"]) or ["(none)"]:
                st.write(doc)

# ------------------------------------------------------------ Compare runs
with tab_compare:
    st.subheader("Compare two runs, case by case")
    st.write("Only cases with the same id AND identical prompt are compared.")
    runs = bdf.groupby("run_id").agg(config=("config_id", "first"), label=("label", "first")).reset_index()
    names = {f"run {r.run_id}: {r.config} ({r.label})": r.run_id for r in runs.itertuples()}
    if len(names) < 2:
        st.info("Need at least two runs in this batch.")
    else:
        ca, cb = st.columns(2)
        run_a = names[ca.selectbox("Baseline (run A)", list(names), index=0)]
        run_b = names[cb.selectbox("Compare to (run B)", list(names), index=min(1, len(names) - 1))]
        a = bdf[bdf["run_id"] == run_a].set_index("case_id")
        b = bdf[bdf["run_id"] == run_b].set_index("case_id")
        shared = [c for c in a.index if c in b.index]
        same = [c for c in shared if a.loc[c, "prompt"] == b.loc[c, "prompt"]]
        st.caption(f"{len(same)} comparable cases, {len(shared) - len(same)} skipped (different prompt).")
        fixed = [c for c in same if a.loc[c, "success"] and not b.loc[c, "success"]]
        regressed = [c for c in same if not a.loc[c, "success"] and b.loc[c, "success"]]
        x, y = st.columns(2)
        x.metric("Fixed in B (attack worked on A, failed on B)", len(fixed))
        y.metric("Regressed in B", len(regressed))
        x.write(fixed or "none")
        y.write(regressed or "none")