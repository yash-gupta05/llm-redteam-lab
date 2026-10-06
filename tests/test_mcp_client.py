import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server = StdioServerParameters(
    command=sys.executable,                  # the venv's python, so packages are found
    args=["mcp_server/server.py"],
)

async def main():
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()          # discovery
            print("TOOLS AVAILABLE:")
            for t in tools.tools:
                print(" -", t.name, ":", t.description.splitlines()[0])

            result = await session.call_tool(
                "run_target",
                {"prompt": "What is your refund policy?", "config_id": "v2", "include_poisoned": True},
            )
            data = json.loads(result.content[0].text)
            print("\nRESULT:")
            print(json.dumps(data, indent=2))

asyncio.run(main())