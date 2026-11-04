"""Picks the advisories that the description-style lookups of Test v2 are about, by seeded sample.

Same method as eval/pick_descriptions.py, with a new seed and one extra rule: no advisory that any
v1 question (dev or test) was about. The pick is made before any change to the system. A paraphrase
is then written by hand for each advisory, into eval-v2/paraphrases.json. This script imports
nothing from the advisor package.

Usage: python eval-v2/pick_descriptions.py
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import make_gold as gold  # noqa: E402
import pick_descriptions as v1  # noqa: E402

SEED = 20261102
QUOTA = {"PyPI": 7, "npm": 3, "Maven": 6}  # 16 picked for 14 questions, two spare
POST_CUTOFF_AT_LEAST = 4
POST_CUTOFF = "2026-07-01"
PER_PACKAGE = 2


def v1_subjects() -> set[str]:
    rows = (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    return {s for row in rows for s in json.loads(row)["subjects"]}


def pick(advisories: list[gold.Advisory], seed: int = SEED) -> list[gold.Advisory]:
    rng = random.Random(seed)
    banned = v1_subjects()
    pool = [a for a in v1.candidates(advisories) if a.ghsa_id not in banned]
    chosen: list[gold.Advisory] = []

    def fits(advisory: gold.Advisory) -> bool:
        first = advisory.ranges[0]
        in_ecosystem = sum(c.ranges[0].ecosystem == first.ecosystem for c in chosen)
        in_package = sum(c.ranges[0].package == first.package for c in chosen)
        return in_ecosystem < QUOTA.get(first.ecosystem, 0) and in_package < PER_PACKAGE

    post = [a for a in pool if a.published >= POST_CUTOFF]
    rng.shuffle(post)
    for advisory in post:
        if sum(a.published >= POST_CUTOFF for a in chosen) < POST_CUTOFF_AT_LEAST and fits(
            advisory
        ):
            chosen.append(advisory)
    rest = [a for a in pool if a not in chosen]
    rng.shuffle(rest)
    for advisory in rest:
        if fits(advisory):
            chosen.append(advisory)
    return sorted(chosen, key=lambda a: a.ghsa_id)


def main() -> None:
    records = gold.read_cache(gold.REST_CACHE)
    advisories = [gold.parse_advisory(r) for r in records.values() if not r.get("withdrawn_at")]
    for advisory in pick(advisories):
        record = records[advisory.ghsa_id]
        print(  # noqa: T201
            json.dumps(
                {
                    "ghsa": advisory.ghsa_id,
                    "package": advisory.ranges[0].package,
                    "published": advisory.published[:10],
                    "cve": advisory.cve_id,
                    "fixed": advisory.ranges[0].first_patched,
                    "severity": advisory.label,
                    "summary": advisory.summary,
                    "description": (record.get("description") or "")[:420],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
