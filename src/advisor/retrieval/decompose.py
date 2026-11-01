"""Rung R8: a model turns a question into a few short search queries.

The model, effort and token limit are fixed here and the sub-queries are saved, so a rerun costs
nothing and the same sub-queries can be inspected. Sampling cannot be set on this model, so the
ladder runs this rung three times and shows the spread.
"""

import json
from pathlib import Path

MODEL = "claude-sonnet-5-5"
EFFORT = "medium"
MAX_TOKENS = 2000
MAX_QUERIES = 4
PRICE = {"input": 2.00, "output": 10.00}  # dollars per million tokens

SYSTEM = f"""You turn a question about software vulnerabilities into search queries for an \
index of GitHub advisories, NVD records and CISA KEV entries.

Reply with one JSON object and nothing else: {{"queries": ["...", "..."]}}.
- Write at most {MAX_QUERIES} short queries. One query per fact the answer needs.
- A question that needs one fact gets one query: the question itself, or a tighter version.
- Keep advisory IDs, CVE IDs, package names and version numbers exactly as written.
- Do not answer the question and do not invent IDs."""


def parse_queries(text: str, question: str) -> list[str]:
    """The queries in a reply, or the question itself if the reply cannot be read."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        queries = json.loads(text[start:end])["queries"]
    except (ValueError, KeyError, TypeError):
        return [question]
    if not isinstance(queries, list):
        return [question]
    cleaned = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
    return cleaned[:MAX_QUERIES] or [question]


def decompose(question: str, run: int, client, cache_path: Path) -> tuple[list[str], float]:
    """The sub-queries for one question in one run, and what asking cost (zero when saved)."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    key = f"{run}|{question}"
    if key in cache:
        return cache[key]["queries"], 0.0
    reply = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": EFFORT},
        messages=[{"role": "user", "content": question}],
    )
    text = "".join(b.text for b in reply.content if b.type == "text")
    cost = (
        reply.usage.input_tokens * PRICE["input"] + reply.usage.output_tokens * PRICE["output"]
    ) / 1_000_000
    queries = parse_queries(text, question)
    cache[key] = {"queries": queries, "cost_usd": cost, "model": reply.model}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return queries, cost
