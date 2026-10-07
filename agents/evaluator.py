import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from db import init_db, create_run, log_result, get_conn

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = Path(__file__).resolve().parent / "attack_cases.json"

SERVER = StdioServerParameters(
    command=sys.executable,
    args=[str(ROOT / "mcp_server" / "server.py")],
)


async def call_tool(session: ClientSession, name: str, arguments: dict) -> dict:
    """Call one MCP tool and parse its JSON reply."""
    result = await session.call_tool(name, arguments)
    text = result.content[0].text
    if result.isError:
        return {"error": text}
    return json.loads(text)


async def evaluate(session, config_id: str, cases: list[dict], use_judge: bool, label: str):
    metrics = ["leak", "pii"] + (["hallucination"] if use_judge else [])
    run_id = None

    for case in cases:
        target = await call_tool(session, "run_target", {
            "prompt": case["prompt"],
            "config_id": config_id,
            "include_poisoned": case["include_poisoned"],
        })
        if "error" in target:
            print(f"  {case['id']:4} TARGET ERROR: {target['error']}")
            continue

        scored = await call_tool(session, "score_response", {
            "response": target["response"],
            "context": target["retrieved_context"],
            "metrics": metrics,
            "prompt": case["prompt"],
        })
        if "leak" not in scored or "pii" not in scored:
            print(f"  {case['id']:4} SCORING ERROR: {scored}")
            continue

        if run_id is None:
            run_id = create_run(config_id, target["model"], label)

        leaked = scored["leak"]["leaked"]
        pii = scored["pii"]["pii_found"]
        hall = scored.get("hallucination", {}).get("score")

        # Benign correctness: does the reply contain at least one expected keyword?
        correct = None
        if case.get("expect_any"):
            text = target["response"].lower()
            correct = int(any(k.lower() in text for k in case["expect_any"]))

        log_result(run_id, case["id"], case["category"], case["prompt"], target["response"],
                   target["retrieved_context"], target["poisoned_doc_retrieved"],
                   leaked, pii, hall, target["latency_ms"], correct)

        extra = f" correct={correct}" if correct is not None else ""
        print(f"  {case['id']:4} {case['category']:8} leaked={int(leaked)} pii={int(pii)} "
              f"poisoned_retrieved={int(target['poisoned_doc_retrieved'])} "
              f"hallucination={hall}{extra} ({target['latency_ms']} ms)")
    return run_id


def print_summary(run_ids: list[int]) -> None:
    conn = get_conn()
    print("\nSUMMARY (from SQLite)")
    for run_id in run_ids:
        run = conn.execute("SELECT config_id, model FROM runs WHERE id=?", (run_id,)).fetchone()
        print(f"\nrun {run_id}: config={run['config_id']} model={run['model']}")
        rows = conn.execute("""
            SELECT category, COUNT(*) AS n, SUM(leaked) AS leaks, SUM(pii_found) AS pii,
                   AVG(hallucination) AS hall, SUM(poisoned_retrieved) AS poisoned
            FROM results WHERE run_id=? GROUP BY category ORDER BY category
        """, (run_id,)).fetchall()
        for r in rows:
            hall = f"{r['hall']:.2f}" if r["hall"] is not None else "n/a"
            print(f"  {r['category']:9} leaks {r['leaks']}/{r['n']}  pii {r['pii']}/{r['n']}  "
                  f"poisoned_retrieved {r['poisoned']}/{r['n']}  avg hallucination score {hall}")
    conn.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="+", default=["v1", "v2"])
    parser.add_argument("--category", help="only run one category (benign/direct/indirect/pii)")
    parser.add_argument("--cases-file", default=str(CASES_FILE), help="JSON file of test cases")
    parser.add_argument("--judge", action="store_true", help="also run the slow LLM hallucination judge")
    parser.add_argument("--label", default="eval")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases_file).read_text(encoding="utf-8"))
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    print(f"{len(cases)} cases, configs={args.configs}, judge={args.judge}")

    init_db()
    run_ids = []
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for config_id in args.configs:
                print(f"\nCONFIG {config_id}")
                run_id = await evaluate(session, config_id, cases, args.judge, args.label)
                if run_id:
                    run_ids.append(run_id)
    print_summary(run_ids)


if __name__ == "__main__":
    asyncio.run(main())