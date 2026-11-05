"""Builds docs/demo/data.json: the 40 dev questions, answered by the saved first run.

No model is called and nothing is fetched. The script reads the committed results files, the
frozen questions and gold, and the local store, and writes one JSON file for the static page in
docs/demo/. It does not import the API client or the answer module, and it reads no key and no
settings file. A test holds it to that.

Only the dev split is shown. The test split and Test v2 are not read.

Usage:
    python scripts/build_replay.py
    python -m http.server -d docs/demo
"""

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.generation.reading import normal_id, read_reply  # noqa: E402
from advisor.retrieval.units import build_units  # noqa: E402
from advisor.web.view import link_for, view  # noqa: E402

RESULTS = ROOT / "eval" / "results"
OUT = ROOT / "docs" / "demo" / "data.json"
RUN = 1  # the first of the three saved runs
RUN_DATE = "2 November 2026"
SYSTEMS = ("phase5-system-v1", "phase6-system-v1")
EXCERPT = 240
HEADER = 320
CLAIM_FIELDS = ("record", "source", "package", "version", "affected", "cve", "listed", "label",
                "cvss3", "date")  # fmt: skip


def read_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def first_run(lines: list[dict]) -> dict[str, dict]:
    return {x["id"]: x for x in lines if x["run"] == RUN}


def git(*args: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.strip()  # fmt: skip


def cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def record_entry(unit) -> dict:
    """A record as the page lists it: where it came from, its header, a short excerpt, and a link
    built from its ID. The link is the same one the answer view builds."""
    found = normal_id(unit.unit_id.split(":", 1)[1])
    return {
        "id": found, "source": unit.source, "header": cut(unit.header, HEADER),
        "excerpt": cut(unit.body, EXCERPT), "url": link_for(found)["url"],
    }  # fmt: skip


def claim_text(claim: object) -> str:
    """One claim as a short line of its known fields. The model wrote it, so the page treats it as
    text."""
    if not isinstance(claim, dict):
        return "(not an object)"
    parts = [str(claim.get("kind", "?"))]
    parts += [f"{name}={claim[name]}" for name in CLAIM_FIELDS if name in claim]
    return cut(" ".join(parts), 200)


def claims_of(raw_text: str, checker: dict) -> list[dict]:
    """The checker's verdict on each claim, with the claim as the model wrote it."""
    answer, _ = read_reply(raw_text)
    written = answer.get("claims", []) if answer else []
    out = []
    for item in checker.get("claims", []):
        index = item["index"]
        said = written[index - 1] if isinstance(written, list) and index <= len(written) else None
        out.append({
            "index": index, "claim": claim_text(said), "status": item["status"],
            "rule": item["rule"], "reason": cut(item["reason"] or "", 300),
        })  # fmt: skip
    return out


def outcome_of(row: dict) -> dict:
    return {"outcome": row["outcome"], "declined": bool(row["abstained"])}


def checked_entry(line: dict, raw_text: str, row: dict) -> dict:
    """What the checker did with the reply, and what a visitor would have been shown."""
    checker = line["checker"]
    return {
        **outcome_of(row), "verdict": checker["verdict"], "route": checker["route"],
        "rule": checker["rule"], "reasons": [cut(r, 300) for r in checker["reasons"]],
        "claims": claims_of(raw_text, checker), "view": view(line["text"]),
    }  # fmt: skip


def gold_text(question: dict, gold: dict) -> str:
    """The gold answer in a line, from the one field the question is answered with."""
    field, expected = question["answers_with"], gold["gold"]
    if field == "abstain":
        return "Nothing in the records answers this, so Otis should decline."
    if field == "verdict":
        return f"Verdict: {expected['verdict']}."
    if field == "value":
        return f"Value: {expected['value']}."
    if field == "disagreement":
        found = expected["disagreement"]
        sides = found["values"]
        return (
            f"The sources {'differ' if found['flagged'] else 'agree'}. "
            f"GitHub: {sides['github'] or 'none'}. NVD: {sides['nvd'] or 'none'}."
        )
    return "Records: " + ", ".join(expected["ids"]) + "."


def totals(rows: list[dict]) -> dict:
    return {"correct": sum(r["outcome"] == "correct" for r in rows), "of": len(rows)}


def build(db: sqlite3.Connection, files: dict, commits: dict) -> dict:
    """The data file as a dict. `files` holds the lines already read, so this reads no file."""
    units = {u.unit_id: u for u in build_units(db)}
    questions = [q for q in files["questions"] if q["split"] == "dev"]
    gold = {g["id"]: g for g in files["gold"]}
    raw = first_run(files["raw"])
    old, new = first_run(files["checked_old"]), first_run(files["checked_new"])
    score = {name: {r["id"]: r for r in files[name] if r["run"] == RUN}
             for name in ("scored_raw", "scored_old", "scored_new")}  # fmt: skip
    records: dict[str, dict] = {}
    out = []
    for question in questions:
        qid = question["id"]
        line = raw[qid]
        shown = [units[u] for u in line["shown"]]
        for unit in shown:
            records.setdefault(unit.unit_id, record_entry(unit))
        out.append({
            "id": qid, "type": question["type"], "question": question["question"],
            "gold": {
                "text": gold_text(question, gold[qid]),
                "derivation": cut(gold[qid]["derivation"], 400),
            },
            "raw": {**outcome_of(score["scored_raw"][qid]), "view": view(line["text"])},
            "phase5": checked_entry(old[qid], line["text"], score["scored_old"][qid]),
            "phase6": checked_entry(new[qid], line["text"], score["scored_new"][qid]),
            "shown": [u.unit_id for u in shown],
            "cost_usd": line["cost_usd"], "latency_s": line["latency_s"],
        })  # fmt: skip
    return {
        "meta": {
            "run": RUN, "run_date": RUN_DATE, "model": raw[questions[0]["id"]]["model"],
            "run_commit": raw[questions[0]["id"]]["commit"], "systems": commits,
            "questions": len(out),
            "totals": {name: totals(list(rows.values())) for name, rows in zip(
                ("raw", "phase5", "phase6"), score.values(), strict=True)},
            "cost_usd": round(sum(q["cost_usd"] for q in out), 4),
        },
        "records": records,
        "questions": out,
    }  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "advisor.db"))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    files = {
        "questions": read_lines(ROOT / "eval" / "questions.jsonl"),
        "gold": read_lines(ROOT / "eval" / "gold.jsonl"),
        "raw": read_lines(RESULTS / "generation-dev-raw.jsonl"),
        "checked_old": read_lines(RESULTS / "generation-dev-checked.jsonl"),
        "checked_new": read_lines(RESULTS / "generation-dev-checked-phase6.jsonl"),
        "scored_raw": read_lines(RESULTS / "generation-dev-raw.scored.jsonl"),
        "scored_old": read_lines(RESULTS / "generation-dev-checked.scored.jsonl"),
        "scored_new": read_lines(RESULTS / "generation-dev-checked-phase6.scored.jsonl"),
    }
    commits = {tag: git("rev-parse", f"{tag}^{{commit}}") for tag in SYSTEMS}
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    data = build(db, files, commits)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    size = Path(args.out).stat().st_size
    print(f"Wrote {args.out} ({size / 1024:.0f} KB, {data['meta']['questions']} questions).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
