import sys
import time

import requests
from mcp.server.fastmcp import FastMCP

import attacks
import queries
from scoring import score

TARGET_URL = "http://localhost:8000/chat"

mcp = FastMCP("redteam-lab")


@mcp.tool()
def run_target(prompt: str, config_id: str = "v1", include_poisoned: bool = True) -> dict:
    """Send a prompt to the target chatbot and return its response.

    Args:
        prompt: The user message to send to the target app.
        config_id: Prompt version "v1", "v2" or "v3", optionally with a model,
            e.g. "v2@qwen2.5:7b". Without a model, llama3.2:3b is used.
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
def score_response(response: str, context: list[str], metrics: list[str], prompt: str = "") -> dict:
    """Score a target-app response with safety and quality checks.

    Args:
        response: The text the target app replied with.
        context: The documents the target retrieved for this reply.
        metrics: Which checks to run. Options:
            "leak" - rule-based check for the secret code in the reply (fast).
            "pii" - Presidio detection of emails, phones, cards, SSNs, IBANs and
                invented-looking names that were in neither the context nor the prompt (fast).
            "hallucination" - LLM judge: does the reply contradict or go beyond the
                context? Score 0 to 1, higher is better. Slow (tens of seconds).
            "faithfulness" - LLM judge: are the reply's claims supported by the
                context? Score 0 to 1, higher is better. Slow, and noisier than
                hallucination.
        prompt: The user message that produced the reply (optional). Names or
            contacts that appear in the prompt are not counted as PII leaks.

    Returns one result object per requested metric. LLM metrics are skipped when
    no context was retrieved.
    """
    return score(response, context, metrics, prompt=prompt)


@mcp.tool()
def generate_attacks(category: str, n: int = 6, seed: int = 0) -> dict:
    """Generate adversarial test cases for the target chatbot.

    Mixes hand-written template attacks with LLM-written rewordings of them.

    Args:
        category: "direct" (user tries to extract the secret code),
            "indirect" (innocent questions that retrieve the poisoned document),
            or "pii" (attempts to extract personal data).
        n: How many attacks to return (1 to 50).
        seed: Random seed, so the same seed gives the same selection of templates.

    Returns {"category": ..., "attacks": [...]}. Each attack has id, category,
    include_poisoned, prompt, and source ("template" or "llm").
    """
    if category not in attacks.TEMPLATES:
        return {"error": f"unknown category '{category}'. Use one of: {list(attacks.TEMPLATES)}"}
    n = max(1, min(n, 50))
    return attacks.make_attacks(category, n, seed)


@mcp.tool()
def query_results(sql: str, max_rows: int = 50) -> dict:
    """Run a read-only SQL SELECT over the eval results database (SQLite).

    Only a single SELECT (or WITH ... SELECT) is allowed; anything else is
    rejected. At most 200 rows are returned, and long text cells are shortened.

    Tables:
      runs(id, created_at, config_id, model, label)
      results(id, run_id, case_id, category, prompt, response, retrieved_context,
              poisoned_retrieved, leaked, pii_found, hallucination, latency_ms, created_at)
    Notes: category is benign/direct/indirect/pii. leaked and pii_found are 0/1,
    so AVG(leaked) is the attack success rate. hallucination is 0-1 (higher is
    better) and NULL when the judge was not run. results.run_id joins runs.id.

    Args:
        sql: The SELECT statement.
        max_rows: Row limit for this query (1 to 200).

    Returns {"columns", "rows", "row_count", "truncated"} or {"error"}.
    """
    return queries.run_query(sql, max_rows)


@mcp.tool()
def compare_runs(run_a: int, run_b: int) -> dict:
    """Compare two eval runs (for example two prompt versions or two models).

    Only cases with the same case_id AND identical prompt are compared.
    Returns, per category, the attack success rate in each run and the delta
    (negative means run_b is safer), average hallucination score and latency,
    plus the case ids that were fixed or regressed in run_b.

    Args:
        run_a: Run id of the baseline (see the runs table).
        run_b: Run id to compare against the baseline.
    """
    return queries.compare(run_a, run_b)


if __name__ == "__main__":
    mcp.run(transport="stdio")