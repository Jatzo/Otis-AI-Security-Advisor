"""Picks the advisories that the description-style lookups are about, by seeded sample.

The pick is made before any system exists. Its output, with the paraphrase written for each
advisory, is eval/paraphrases.json. This script imports nothing from the advisor package.

Usage: python eval/pick_descriptions.py
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_gold as gold  # noqa: E402

SEED = 20261101
QUOTA = {"PyPI": 7, "npm": 3, "Maven": 5}
POST_CUTOFF_AT_LEAST = 4  # of the 15, so the post-cutoff slice has description lookups too
POST_CUTOFF = "2026-07-01"
PER_PACKAGE = 2  # so no single package dominates the description lookups


def candidates(advisories: list[gold.Advisory]) -> list[gold.Advisory]:
    """Advisories whose summary is specific enough to paraphrase without being ambiguous:
    long enough, and not shared with any other advisory."""
    titles = Counter(a.summary.strip().lower() for a in advisories)
    return [
        a
        for a in advisories
        if len(a.summary) >= 40 and titles[a.summary.strip().lower()] == 1 and len(a.ranges) >= 1
    ]


def pick(advisories: list[gold.Advisory], seed: int = SEED) -> list[gold.Advisory]:
    rng = random.Random(seed)
    pool = candidates(advisories)
    chosen: list[gold.Advisory] = []

    def fits(advisory: gold.Advisory) -> bool:
        first = advisory.ranges[0]
        in_ecosystem = sum(c.ranges[0].ecosystem == first.ecosystem for c in chosen)
        in_package = sum(c.ranges[0].package == first.package for c in chosen)
        return in_ecosystem < QUOTA.get(first.ecosystem, 0) and in_package < PER_PACKAGE

    post = [a for a in pool if a.published >= POST_CUTOFF]
    rng.shuffle(post)
    for advisory in post:
        if len(chosen) < POST_CUTOFF_AT_LEAST and fits(advisory):
            chosen.append(advisory)
    rest = [a for a in pool if a not in chosen]
    rng.shuffle(rest)
    chosen += []
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
                    "summary": advisory.summary,
                    "description": (record.get("description") or "")[:420],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
