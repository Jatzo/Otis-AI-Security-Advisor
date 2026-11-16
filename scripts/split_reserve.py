"""Splits the advisories no earlier question is about into Dev-R's eligible set and a reserve.

This is step 1, item 7, of docs/evidence-round-plan.md. Dev-R and a future Test v3 would draw from
the same few advisories no earlier question is about. If Dev-R took them all, a later test would
have nothing fresh. So half are set aside now, before Dev-R is built, and not read again until a
Test v3 is planned.

The split is seeded and done inside each package, so both halves keep the packages in proportion.
It reads only committed files and calls no retrieval and no model. The reserve is a list of IDs
and a hash. Writing the IDs down is not a look at them: no question, record text or label is read.

Advisories that only v1 dev used are not in either half. The plan lets them into Dev-R as a flagged
`seen_dev` slice, and they are never a candidate for a later test.

Usage:
    python scripts/split_reserve.py
"""

import hashlib
import json
import random
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "eval-retrieval" / "split.json"
SEED = 20261116  # the Dev-R seed fixed in the plan
PACKAGE = re.compile(r"Package: (\S+) \((\w+)\)")


def read_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def digest(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def main() -> int:
    corpus = json.loads((ROOT / "docs" / "demo" / "corpus.json").read_text(encoding="utf-8"))
    package_of = {}
    for unit in corpus["units"]:
        if unit["source"] == "ghsa":
            package_of[unit["id"].split(":", 1)[1]] = PACKAGE.search(unit["header"]).group(1)
    v1 = read_rows(ROOT / "eval" / "questions.jsonl")
    v2 = read_rows(ROOT / "eval-v2" / "questions.jsonl")
    test_v1 = {s for q in v1 if q["split"] != "dev" for s in q["subjects"]}
    dev_v1 = {s for q in v1 if q["split"] == "dev" for s in q["subjects"]}
    test_v2 = {s for q in v2 for s in q["subjects"]}
    unused = sorted(set(package_of) - test_v1 - dev_v1 - test_v2)
    dev_only = sorted((set(package_of) & dev_v1) - test_v1 - test_v2)

    by_package: dict[str, list[str]] = defaultdict(list)
    for ghsa in unused:
        by_package[package_of[ghsa]].append(ghsa)
    rng = random.Random(SEED)  # noqa: S311 - choosing a split, not secrets
    eligible: list[str] = []
    reserve: list[str] = []
    for package in sorted(by_package):
        ids = by_package[package]
        rng.shuffle(ids)
        half = (len(ids) + 1) // 2  # the odd one goes to Dev-R
        eligible += ids[:half]
        reserve += ids[half:]
    eligible.sort()
    reserve.sort()
    result = {
        "seed": SEED,
        "advisories_in_corpus": len(package_of),
        "unused_by_any_question": len(unused),
        "dev_r_eligible": {"count": len(eligible), "sha256": digest(eligible), "ids": eligible},
        "reserve": {"count": len(reserve), "sha256": digest(reserve), "ids": reserve},
        "seen_dev_only": {"count": len(dev_only), "sha256": digest(dev_only), "ids": dev_only},
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(
        f"{len(package_of)} advisories, {len(unused)} unused: {len(eligible)} to Dev-R, "
        f"{len(reserve)} reserved, {len(dev_only)} seen only by v1 dev."
    )
    print(f"reserve sha256 {result['reserve']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
