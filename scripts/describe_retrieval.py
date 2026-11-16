"""Describes where R1 misses and how big each package is, from files already saved.

This is step 1, items 5 and 6, of docs/evidence-round-plan.md. It calls no retrieval and no model
and reads only committed files: the saved R1 results for the v1 dev and test splits, the v1
questions and gold, and the published corpus. Nothing here is tuned on or chosen from the numbers.

Two things are reported:
- R1's misses by question type, by how many records the answer needs, by whether the question
  names an ID and by whether it names exactly one package. A miss is a question whose needed
  records did not all reach the top 10.
- How many advisories each of the 18 packages has, which shows how much of a package fits in
  the 20 records candidate R10 would hold.

Usage:
    python scripts/describe_retrieval.py --out docs/retrieval-descriptives.md
"""

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = {"dev": "retrieval-r1-dev.json", "test": "test-retrieval.json"}
PACKAGE = re.compile(r"Package: (\S+) \((\w+)\)")
ID = re.compile(r"GHSA-[\w-]+|CVE-\d{4}-\d+", re.IGNORECASE)
CAP = 20  # the depth planned for candidate R10


def read_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def package_sizes() -> dict[str, int]:
    corpus = json.loads((ROOT / "docs" / "demo" / "corpus.json").read_text(encoding="utf-8"))
    sizes: Counter = Counter()
    for unit in corpus["units"]:
        if unit["source"] == "ghsa":
            sizes[PACKAGE.search(unit["header"]).group(1)] += 1
    return dict(sizes)


def names_one_package(text: str, packages: list[str]) -> bool:
    """Whole-word, case-insensitive match on the short package name, exactly one package."""
    found = {
        p
        for p in packages
        if re.search(r"(?<![\w.-])" + re.escape(p.split(":")[-1]) + r"(?![\w-])", text, re.I)
    }
    return len(found) == 1


def record_count(gold_row: dict) -> int:
    evidence = gold_row["evidence"]
    return len(evidence["ghsa"]) + len(evidence["nvd"]) + len(evidence["kev"])


def cell(rows: list[dict], key: str) -> str:
    return f"{sum(r[key] for r in rows)}/{len(rows)}"


def table(title: str, groups: dict[str, list[dict]]) -> list[str]:
    head = [
        f"### {title}",
        "",
        "| Group | dev top 10 | dev top 20 | test top 10 | test top 20 |",
        "|---|---|---|---|---|",
    ]
    body = []
    for name, rows in groups.items():
        parts = []
        for split in ("dev", "test"):
            part = [r for r in rows if r["split"] == split]
            parts += [cell(part, "all@10"), cell(part, "all@20")] if part else ["0/0", "0/0"]
        body.append(f"| {name} | " + " | ".join(parts) + " |")
    return [*head, *body, ""]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="write the tables as Markdown to this path")
    args = parser.parse_args()
    sizes = package_sizes()
    packages = sorted(sizes)
    questions = {q["id"]: q for q in read_rows(ROOT / "eval" / "questions.jsonl")}
    gold = {g["id"]: g for g in read_rows(ROOT / "eval" / "gold.jsonl")}
    rows = []
    for split, name in RESULTS.items():
        saved = json.loads((ROOT / "eval" / "results" / name).read_text(encoding="utf-8"))
        for row in saved["rows"]:
            question = questions[row["id"]]
            text = question["question"]
            rows.append(
                {
                    "split": split,
                    "type": question["type"],
                    "records": record_count(gold[row["id"]]),
                    "names_id": bool(ID.search(text)),
                    "names_package": names_one_package(text, packages),
                    "all@10": bool(row["all@10"]),
                    "all@20": bool(row["all@20"]),
                }
            )

    def group(key) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            out[str(key(r))].append(r)
        return dict(sorted(out.items()))

    lines = [
        "# R1 misses and package sizes",
        "",
        "Written by `scripts/describe_retrieval.py` from files already saved, with no retrieval, "
        "no model and no network. See [the plan](evidence-round-plan.md), step 1, items 5 and 6. "
        "It is descriptive. It led to a post hoc plan amendment (R1 at depth 20 added as a "
        "candidate), and it counts as a look in [the ledger](ledger.md).",
        "",
        f"Answerable questions only: {sum(r['split'] == 'dev' for r in rows)} on v1 dev and "
        f"{sum(r['split'] == 'test' for r in rows)} on v1 test. Each cell is questions where all "
        "the needed records were in the list, over questions in the group. A miss is the "
        "difference.",
        "",
        *table("By question type", group(lambda r: r["type"])),
        *table(
            "By how many records the answer needs",
            group(lambda r: r["records"] if r["records"] < 4 else "4 or more"),
        ),
        *table("By whether the question names an ID", group(lambda r: r["names_id"])),
        *table(
            "By whether the question names exactly one package", group(lambda r: r["names_package"])
        ),
    ]
    scoped = [r for r in rows if r["names_package"]]
    unscoped = [r for r in rows if not r["names_package"]]
    lines += [
        "### What R10 could change",
        "",
        f"R10 would scope {len(scoped)} of {len(rows)} answerable questions (the ones that name "
        f"exactly one package). The other {len(unscoped)} would get R1's top 10 unchanged. On "
        f"the scoped questions R1's top 10 holds all the needed records for "
        f"{cell(scoped, 'all@10')} and its top 20 for {cell(scoped, 'all@20')}.",
        "",
        "The match is on the package name as written in the corpus, so wordings such as "
        "'Log4j Core', 'Spring MVC' or 'Struts 2' are not counted. The share of questions that "
        "name a package is a floor, and R10 will scope fewer free-form questions than this.",
        "",
        "## Package sizes",
        "",
        f"Advisories per package in the published corpus. The cap for R10 is {CAP} records.",
        "",
        "| Package | Advisories | Fits in the cap |",
        "|---|---|---|",
        *[
            f"| {name} | {count} | {'yes' if count <= CAP else 'no'} |"
            for name, count in sorted(sizes.items(), key=lambda item: -item[1])
        ],
        "",
        f"Median {statistics.median(sizes.values()):g}, largest {max(sizes.values())}. "
        f"{sum(c <= CAP for c in sizes.values())} of {len(sizes)} packages fit in {CAP} records. "
        "The rest cannot be held whole, so for those R10 is R1's ranking filtered to the "
        "package, and a completeness check could not be satisfied.",
        "",
    ]
    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
