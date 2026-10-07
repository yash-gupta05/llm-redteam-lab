import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = Path(__file__).resolve().parent / "generated_cases.json"

SERVER = StdioServerParameters(
    command=sys.executable,
    args=[str(ROOT / "mcp_server" / "server.py")],
)


async def generate(session: ClientSession, categories: list[str], n: int, seed: int) -> list[dict]:
    """Ask the MCP server for n attacks per category."""
    cases = []
    for category in categories:
        result = await session.call_tool(
            "generate_attacks", {"category": category, "n": n, "seed": seed}
        )
        if result.isError:
            print(f"{category}: tool error: {result.content[0].text}")
            continue
        data = json.loads(result.content[0].text)
        if "error" in data:
            print(f"{category}: {data['error']}")
            continue
        llm = sum(a["source"] == "llm" for a in data["attacks"])
        print(f"{category}: {len(data['attacks'])} attacks ({llm} LLM-written)")
        cases.extend(data["attacks"])
    return cases


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=6, help="attacks per category")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--categories", nargs="+", default=["direct", "indirect", "pii"])
    args = parser.parse_args()

    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            cases = await generate(session, args.categories, args.n, args.seed)

    OUT_FILE.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print(f"saved {len(cases)} cases to {OUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())