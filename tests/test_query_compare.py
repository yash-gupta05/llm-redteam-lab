import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server = StdioServerParameters(command=sys.executable, args=["mcp_server/server.py"])

QUERIES = [
    ("good: success rate per config",
     "SELECT runs.config_id, results.category, COUNT(*) AS n, ROUND(AVG(leaked), 2) AS leak_rate "
     "FROM results JOIN runs ON runs.id = results.run_id GROUP BY 1, 2"),
    ("good: row limit",
     "SELECT case_id, category FROM results", ),
    ("BAD: delete", "DELETE FROM results"),
    ("BAD: drop", "DROP TABLE results"),
    ("BAD: two statements", "SELECT 1; DELETE FROM results"),
    ("BAD: update hidden in a WITH", "WITH x AS (SELECT 1) UPDATE results SET leaked = 0"),
]


async def call(session, tool, args):
    r = await session.call_tool(tool, args)
    return json.loads(r.content[0].text)


async def main():
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for name, sql in QUERIES:
                out = await call(session, "query_results", {"sql": sql, "max_rows": 5})
                print(f"--- {name}")
                if "error" in out:
                    print("  REFUSED:", out["error"])
                else:
                    print(f"  {out['row_count']} rows, truncated={out['truncated']}")
                    for row in out["rows"]:
                        print("  ", row)

            print("\n=== compare_runs(1, 2): v1 vs v2 ===")
            out = await call(session, "compare_runs", {"run_a": 1, "run_b": 2})
            print(json.dumps(out, indent=2))

asyncio.run(main())