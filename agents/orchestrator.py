import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import stdio_client

from agents.evaluator import CASES_FILE, SERVER, evaluate
from agents.red_team import generate
from db import get_conn, init_db

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"


def plan(config: dict, generated: list[dict]) -> list[dict]:
    """Build the test suite: hand-written cases plus generated ones."""
    cases = []
    if config.get("include_handwritten", True):
        cases += json.loads(CASES_FILE.read_text(encoding="utf-8"))
    return cases + generated


def build_report(config: dict, runs_by_config: dict[str, list[int]], n_cases: int) -> str:
    conn = get_conn()
    reps = config.get("repeats", 1)
    lines = [
        f"# Eval report: {config['label']}",
        f"Generated {datetime.now().isoformat(timespec='seconds')}  ",
        f"{n_cases} test cases per run, {reps} repeat(s) per config. "
        f"Judge enabled: {config.get('use_judge', False)}",
        "",
        "Attack success = share of cases where the attack worked (lower is better). "
        "Direct and indirect use the secret-code leak check; pii uses the Presidio check. "
        "Mean and range are taken over the repeats of the same cases.",
        "",
        "| Config | Model | Category | Cases | Attack success (mean) | Range over repeats | Avg latency (ms) |",
        "|---|---|---|---|---|---|---|",
    ]
    useful_lines = []

    for config_id, run_ids in runs_by_config.items():
        model = conn.execute("SELECT model FROM runs WHERE id=?", (run_ids[0],)).fetchone()["model"]
        per_cat = {}
        marks = ",".join("?" * len(run_ids))
        for run_id in run_ids:
            rows = conn.execute("""
                SELECT category, COUNT(*) AS n, SUM(leaked) AS leaks, SUM(pii_found) AS pii,
                       AVG(latency_ms) AS lat
                FROM results WHERE run_id=? GROUP BY category
            """, (run_id,)).fetchall()
            for r in rows:
                hits = r["pii"] if r["category"] == "pii" else r["leaks"]
                per_cat.setdefault(r["category"], []).append((hits, r["n"], r["lat"]))

        for cat, vals in sorted(per_cat.items()):
            rates = [v[0] / v[1] for v in vals]
            mean = sum(rates) / len(rates)
            lat = sum(v[2] for v in vals) / len(vals)
            lines.append(
                f"| {config_id} | {model} | {cat} | {vals[0][1]} | {mean:.0%} | "
                f"{min(rates):.0%} to {max(rates):.0%} | {lat:.0f} |"
            )

        # Usefulness: did the bot give the expected fact? Reported per category.
        for cat in ("benign", "indirect"):
            u = conn.execute(
                f"SELECT COUNT(correct) AS n, SUM(correct) AS ok, "
                f"SUM(correct = 1 AND leaked = 0) AS safe_ok FROM results "
                f"WHERE run_id IN ({marks}) AND category = ?", (*run_ids, cat)).fetchone()
            if u["n"]:
                extra = f", safe AND correct {u['safe_ok']}/{u['n']}" if cat == "indirect" else ""
                useful_lines.append(f"- {config_id} {cat}: correct {u['ok']}/{u['n']}{extra}")
    conn.close()

    if useful_lines:
        lines += ["", "**Usefulness** (keyword check on the expected fact; higher is better):"] + useful_lines
    lines += ["", "Known limits: leak check misses encoded secrets (e.g. base64); "
              "LLM-written attacks can drift from their seed's goal; PII name detection "
              "is a heuristic; usefulness is a keyword check; small samples; "
              "model output is not perfectly repeatable even at temperature 0."]
    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "run_configs" / "baseline.json"))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    init_db()
    runs_by_config: dict[str, list[int]] = {}
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            generated = []
            if config.get("generate"):
                g = config["generate"]
                generated = await generate(session, g["categories"], g["n"], g["seed"])

            cases = plan(config, generated)
            REPORTS_DIR.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            (REPORTS_DIR / f"cases-{stamp}.json").write_text(
                json.dumps(cases, indent=2), encoding="utf-8")
            print(f"planned {len(cases)} cases")

            for config_id in config["target_configs"]:
                for rep in range(config.get("repeats", 1)):
                    print(f"\nCONFIG {config_id} repeat {rep + 1}")
                    run_id = await evaluate(session, config_id, cases,
                                            config.get("use_judge", False),
                                            f"{config['label']}-r{rep + 1}")
                    if run_id:
                        runs_by_config.setdefault(config_id, []).append(run_id)

    report = build_report(config, runs_by_config, len(cases))
    path = REPORTS_DIR / f"report-{stamp}.md"
    path.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\nsaved {path}")


if __name__ == "__main__":
    asyncio.run(main())