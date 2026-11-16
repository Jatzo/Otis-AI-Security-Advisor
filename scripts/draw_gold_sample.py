"""Draws the 30 Test v2 questions a second person reviews, before anyone reads the gold for them.

This is step 1, item 2, of docs/evidence-round-plan.md. The draw is seeded and uses only each
question's id, type and ecosystem, never its text or gold. It is stratified by type, with
sources-disagree and Maven questions picked more often than their share, because those are
where a wrong gold answer is most likely. The sample is written to docs/gold-review-sample.json
and committed before the sheet is built, so the choice cannot follow what the reviewer finds.

The reviewer sees the question and the record extracts first and writes their own answer. Only
then is the gold shown, and they mark agree, disagree or can't tell, with a reason.

Usage:
    python scripts/draw_gold_sample.py
"""

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "gold-review-sample.json"
SEED = 20261116
BY_TYPE = {"lookup": 4, "version": 6, "multihop": 5, "abstain": 3, "disagree": 8}
# Further Maven questions from whatever type is left, so Maven is not left to chance.
EXTRA_MAVEN = 4


def main() -> int:
    path = ROOT / "eval-v2" / "questions.jsonl"
    questions = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    rng = random.Random(SEED)  # noqa: S311 - a seeded, repeatable choice, not security
    chosen: list[dict] = []
    for name, count in BY_TYPE.items():
        pool = sorted((q for q in questions if q["type"] == name), key=lambda q: q["id"])
        chosen += rng.sample(pool, count)
    taken = {q["id"] for q in chosen}
    maven = sorted(
        (q for q in questions if q["ecosystem"] == "Maven" and q["id"] not in taken),
        key=lambda q: q["id"],
    )
    chosen += rng.sample(maven, EXTRA_MAVEN)
    rng.shuffle(chosen)
    sample = [
        {"n": n, "id": q["id"], "type": q["type"], "ecosystem": q["ecosystem"]}
        for n, q in enumerate(chosen, start=1)
    ]
    result = {
        "seed": SEED,
        "rows": sample,
        "maven_rows": sum(r["ecosystem"] == "Maven" for r in sample),
        "disagree_rows": sum(r["type"] == "disagree" for r in sample),
    }
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(sample)} rows: {result['maven_rows']} Maven, {result['disagree_rows']} disagree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
