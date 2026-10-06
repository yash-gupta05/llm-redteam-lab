import sys
import time

import requests
from mcp.server.fastmcp import FastMCP

from scoring import score

TARGET_URL = "http://localhost:8000/chat"

mcp = FastMCP("redteam-lab")


@mcp.tool()
def run_target(prompt: str, config_id: str = "v1", include_poisoned: bool = True) -> dict:
    """Send a prompt to the target chatbot and return its response.

    Args:
        prompt: The user message to send to the target app.
        config_id: Which target configuration to use ("v1" or "v2").
        include_poisoned: Whether the poisoned document may be retrieved
            (True for indirect-injection tests, False for direct-injection tests).

    Returns the response text, the retrieved documents, whether the poisoned
    document was retrieved, the model name, and the latency in milliseconds.
    """
    start = time.time()
    try:
        r = requests.post(
            TARGET_URL,
            json={"prompt": prompt, "config_id": config_id, "include_poisoned": include_poisoned},
            timeout=120,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"run_target failed: {e}", file=sys.stderr)
        return {"error": f"target app call failed: {e}"}

    data = r.json()
    data["latency_ms"] = int((time.time() - start) * 1000)
    return data

@mcp.tool()
def score_response(response: str, context: list[str], metrics: list[str]) -> dict:
    """Score a target-app response with safety and quality checks.

    Args:
        response: The text the target app replied with.
        context: The documents the target retrieved for this reply.
        metrics: Which checks to run. Options:
            "leak" - rule-based check for the secret code in the reply (fast).
            "pii" - Presidio detection of names, emails, phones, cards, SSNs, IBANs (fast).
            "hallucination" - LLM judge: does the reply contradict or go beyond the
                context? Score 0 to 1, higher is better. Slow (tens of seconds).
            "faithfulness" - LLM judge: are the reply's claims supported by the
                context? Score 0 to 1, higher is better. Slow, and noisier than
                hallucination.

    Returns one result object per requested metric. LLM metrics are skipped when
    no context was retrieved.
    """
    return score(response, context, metrics)

if __name__ == "__main__":
    mcp.run(transport="stdio")