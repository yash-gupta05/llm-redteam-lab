import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server = StdioServerParameters(command=sys.executable, args=["mcp_server/server.py"])


async def main():
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            for category in ["direct", "indirect", "pii"]:
                result = await session.call_tool("generate_attacks", {"category": category, "n": 4})
                data = json.loads(result.content[0].text)
                print(f"\n--- {category}")
                for a in data["attacks"]:
                    print(f"  [{a['source']:8}] {a['prompt']}")

asyncio.run(main())