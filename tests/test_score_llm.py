import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server = StdioServerParameters(command=sys.executable, args=["mcp_server/server.py"])
DOC = "AcmeBank branches have opening hours of Monday to Friday, 9am to 5pm. Closed on weekends."

CASES = [
    ("faithful (expect ~1.0)", "Branches are open Monday to Friday, 9am to 5pm, closed on weekends."),
    ("hallucinated (expect low)", "We are open weekdays 9 to 5, and Saturday 9:30am to 1pm."),
]

async def main():
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for name, text in CASES:
                result = await session.call_tool(
                    "score_response",
                    {"response": text, "context": [DOC], "metrics": ["leak", "hallucination", "faithfulness"]},
                )
                print(f"--- {name}")
                print(json.dumps(json.loads(result.content[0].text), indent=2))

asyncio.run(main())