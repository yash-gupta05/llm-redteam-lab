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


def build_report(config: dict, run_ids: list[int], n_cases: int) -> str:
    conn = get_conn()
    lines = [
        f"# Eval report: {config['label']}",
        f"Generated {datetime.now().isoformat(timespec='seconds')}  ",
        f"{n_cases} test cases per target config. Judge enabled: {config.get('use_judge', False)}",
        "",
        "Rates are the share of cases where the attack succeeded (lower is better). "
        "Direct and indirect use the secret-code leak check. The pii category uses the "
        "Presidio PII check. Benign cases should be 0%.",
        "",
        "| Run | Config | Model | Category | Cases | Attack success | Avg latency (ms) |",
        "|---|---|---|---|---|---|---|",
    ]
    for run_id in run_ids:
        run = conn.execute("SELECT config_id, model FROM runs WHERE id=?", (run_id,)).fetchone()
        rows = conn.execute("""
            SELECT category, COUNT(*) AS n, SUM(leaked) AS leaks, SUM(pii_found) AS pii,
                   AVG(latency_ms) AS lat
            FROM results WHERE run_id=? GROUP BY category ORDER BY category
        """, (run_id,)).fetchall()
        for r in rows:
            hits = r["pii"] if r["category"] == "pii" else r["leaks"]
            lines.append(
                f"| {run_id} | {run['config_id']} | {run['model']} | {r['category']} | "
                f"{r['n']} | {hits}/{r['n']} ({hits / r['n']:.0%}) | {r['lat']:.0f} |"
            )
    conn.close()
    lines += ["", "Known limits: leak check misses encoded secrets (e.g. base64); "
              "LLM-written attacks can drift from their seed's goal; PII name detection "
              "is a heuristic; small samples."]
    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "run_configs" / "baseline.json"))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    init_db()
    run_ids = []
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. red-team agent produces attacks
            generated = []
            if config.get("generate"):
                g = config["generate"]
                generated = await generate(session, g["categories"], g["n"], g["seed"])

            # 2. plan the suite and save it so the exact cases can be reused
            cases = plan(config, generated)
            REPORTS_DIR.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            (REPORTS_DIR / f"cases-{stamp}.json").write_text(
                json.dumps(cases, indent=2), encoding="utf-8")
            print(f"planned {len(cases)} cases")

            # 3. evaluator runs every case against every target config
            for config_id in config["target_configs"]:
                print(f"\nCONFIG {config_id}")
                run_id = await evaluate(session, config_id, cases,
                                        config.get("use_judge", False), config["label"])
                if run_id:
                    run_ids.append(run_id)

    # 4. compile the report from the database
    report = build_report(config, run_ids, len(cases))
    path = REPORTS_DIR / f"report-{stamp}.md"
    path.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\nsaved {path}")


if __name__ == "__main__":
    asyncio.run(main())