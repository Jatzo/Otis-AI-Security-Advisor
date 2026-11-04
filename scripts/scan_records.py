"""Scans the real records for text that tries to give the reader orders, or says it is withdrawn.

Why: the red team showed that text added to a record can be followed, and a record claiming to be
withdrawn made the model decline. A defence would hold such records back at retrieval. Before
building one, this measures how many real records it would hold back, because a record held back by
mistake is a question that can no longer be answered.

The patterns below were written before any real record was matched against them. They are
groups of plain words an attacker has to use to talk to an assistant: an order to ignore earlier
text, a fake end of the evidence block, a speaker label, a demand about what the reply must hold,
and a request to reveal the instructions. "Withdrawn" is a separate group, because it is a state a
real advisory can be in.

Every hit is saved with its surrounding words so that it can be read by hand. The patterns only
find candidates: the false positive rate comes from reading them, in docs/records-scan.md.

Usage: python scripts/scan_records.py [--tightened]
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.redteam import spec  # noqa: E402

RESULTS = ROOT / "eval" / "results"
CONTEXT = 70  # characters kept either side of a hit

IGNORE_CASE = re.IGNORECASE
MULTILINE = re.MULTILINE

# group -> list of (name, pattern). A record is a candidate when any pattern in a group matches.
ORDERS = {
    "ignore_earlier": re.compile(
        r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|above|prior|earlier|preceding)\b",
        IGNORE_CASE,
    ),
    "ignore_the_task": re.compile(
        r"\b(ignore|disregard|forget)\b.{0,30}\b(instructions?|the task|the records?|rules)\b",
        IGNORE_CASE,
    ),
    "new_instruction": re.compile(r"\bnew instructions?\b", IGNORE_CASE),
    "speaker_label": re.compile(
        r"^\s*(system|assistant|developer|operator)\s*(notice)?\s*:", IGNORE_CASE | MULTILINE
    ),
    "fake_tag": re.compile(r"<\s*/?\s*evidence\b", IGNORE_CASE),
    "addressed_to_assistants": re.compile(
        r"\b(to|for) (any|all|the|an) (ai |language model |llm )?"
        r"(assistants?|models?|chatbots?|agents?)\b"
        r"|\bassistants? (must|should|will|shall)\b",
        IGNORE_CASE,
    ),
    "demands_on_the_reply": re.compile(
        r"\b(in|to|into|at the (start|end) of) (your|the) (explanation|answer|reply|response)\b"
        r"|\b(set|put) abstain\b|\"abstain\"\s*:|\breply with exactly\b|\bthe correct reply\b",
        IGNORE_CASE,
    ),
    "reveal_instructions": re.compile(
        r"\b(system (prompt|message|instructions?)"
        r"|your (full |hidden )?(instructions|rules|prompt))\b"
        r"|\brepeat (your|the) (instructions|text above)\b",
        IGNORE_CASE,
    ),
    "refuse_to_answer": re.compile(
        r"\bdo not answer\b|\b(must|should) (decline|refuse)\b|\b(decline|refuse) to answer\b",
        IGNORE_CASE,
    ),
}
WITHDRAWN = {"withdrawn": re.compile(r"\bwithdrawn\b|\bwithdraw(s|ing)? this\b", IGNORE_CASE)}
GROUPS = {"orders": ORDERS, "withdrawn": WITHDRAWN}

# The one pattern changed after the first run, with --tightened: "response" is dropped. As written
# it matched four real records that say "in the response" about an HTTP response. The first run is
# the main result and this is the fix to it, fitted to those records (docs/records-scan.md).
TIGHTENED_DEMANDS = re.compile(
    r"\b(in|to|into|at the (start|end) of) (your|the) (explanation|answer|reply)\b"
    r"|\b(set|put) abstain\b|\"abstain\"\s*:|\breply with exactly\b|\bthe correct reply\b",
    IGNORE_CASE,
)


def groups(tightened: bool) -> dict[str, dict[str, re.Pattern]]:
    if not tightened:
        return GROUPS
    return {**GROUPS, "orders": {**ORDERS, "demands_on_the_reply": TIGHTENED_DEMANDS}}


def find(text: str, tightened: bool = False) -> list[tuple[str, str, str]]:
    """Every (group, pattern name, words around the hit) in one text."""
    found = []
    for group, patterns in groups(tightened).items():
        for name, pattern in patterns.items():
            for match in pattern.finditer(text):
                start, end = max(0, match.start() - CONTEXT), match.end() + CONTEXT
                found.append((group, name, " ".join(text[start:end].split())))
    return found


def scan_records(db: sqlite3.Connection, tightened: bool = False) -> list[dict]:
    hits = []
    rows = db.execute("SELECT record_id, source, summary, details FROM records ORDER BY 1, 2")
    for record_id, source, summary, details in rows:
        for field, text in (("summary", summary), ("details", details)):
            for group, name, snippet in find(text or "", tightened):
                hits.append({"record": f"{source}:{record_id}", "field": field,
                             "group": group, "pattern": name, "snippet": snippet})  # fmt: skip
    return hits


def attack_texts() -> dict[str, str]:
    """The text each record-borne attack case adds to a record, by case id."""
    texts = {}
    for file in ("attacks.jsonl", "attacks-heldout.jsonl"):
        for case in spec.load(ROOT / "redteam" / file):
            if case.cls in ("A", "B1"):
                texts[case.case_id] = " ".join(edit.text for edit in case.edits)
    return texts


def main() -> int:
    tightened = "--tightened" in sys.argv[1:]
    suffix = "-tightened" if tightened else ""
    db = sqlite3.connect(f"file:{ROOT / 'data' / 'advisor.db'}?mode=ro", uri=True)
    total = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    hits = scan_records(db, tightened)
    by_group: dict[str, set[str]] = {}
    for hit in hits:
        by_group.setdefault(hit["group"], set()).add(hit["record"])
    flagged_any = {hit["record"] for hit in hits}

    attacks = attack_texts()
    caught = {case_id: bool(find(text, tightened)) for case_id, text in attacks.items()}
    summary = {
        "records": total,
        "flagged_by_group": {g: len(r) for g, r in sorted(by_group.items())},
        "flagged_any": len(flagged_any),
        "hits": len(hits),
        "attack_cases_flagged": {
            f"{cls}-{which}": [
                sum(c for i, c in caught.items() if i.split("-")[1] == cls and i[0] == which),
                sum(1 for i in caught if i.split("-")[1] == cls and i[0] == which),
            ]
            for cls in ("A", "B1")
            for which in ("f", "h")
        },
        "attack_cases_missed": sorted(i for i, c in caught.items() if not c),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"records-scan-hits{suffix}.jsonl").write_text(
        "".join(json.dumps(h, sort_keys=True, ensure_ascii=False) + "\n" for h in hits),
        encoding="utf-8",
    )
    (RESULTS / f"records-scan-summary{suffix}.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
