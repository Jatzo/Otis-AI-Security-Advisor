"""Measures the ingest check (docs/ingest-check.md). Calls no model.

The measures were fixed before the first run, in the plan for piece 1a:
1. How many of the real GitHub records each signal flags. Every flag is read by hand afterwards.
2. What holding back the records signal R flags costs in retrieval: all-evidence at 10 on the dev
   questions that have an answer, against the clean store.
3. What both signals say about the 8 red team B2 records.
4. What they say about real advisories, each lied about in two ways built by a rule
   (src/advisor/integrity/plausible.py), drawn with the seed below.

Everything is reported for R as first written and for the refined R, which leaves pre-release tags
and versions older than a registry's list unjudged. The refined rule was written after reading the
records the first rule flagged, so its false positive count is fitted to them.

Usage: python scripts/measure_ingest_check.py
"""

import json
import random
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor import store  # noqa: E402
from advisor.ingest import releases as release_lists  # noqa: E402
from advisor.integrity import check, plausible  # noqa: E402
from advisor.redteam import poison, spec  # noqa: E402
from advisor.retrieval import ladder  # noqa: E402
from advisor.retrieval.pipeline import Pipeline, Spec  # noqa: E402
from advisor.retrieval.units import build_units  # noqa: E402

RESULTS = ROOT / "eval" / "results"
SEED = 20261104
SAMPLE = 24
R1 = Spec("R1", bm25="header")


def counts(verdicts: dict[str, check.Verdict]) -> dict:
    return {
        "records": len(verdicts),
        "release": dict(Counter(v.release for v in verdicts.values())),
        "second_source": dict(Counter(v.second_source for v in verdicts.values())),
    }


def dev_all_at_10(db: sqlite3.Connection) -> dict[str, bool]:
    questions, gold = ROOT / "eval" / "questions.jsonl", ROOT / "eval" / "gold.jsonl"
    items, _ = ladder.load_dev_items(questions, gold)
    pipeline = Pipeline(build_units(db))
    return {
        i.question_id: ladder.score_ranking(i, pipeline.rank(R1, i.query))["all@10"] for i in items
    }


def draw_sample(db, verdicts, lists) -> list[dict]:
    """Real advisories whose single fixed version is listed and that have an earlier and a later
    stable release to build the two lies from, drawn with the fixed seed."""
    pool = []
    for record_id, verdict in sorted(verdicts.items()):
        rows = db.execute(
            "SELECT ecosystem, package, range_type FROM corpus_affected WHERE record_id = ?",
            (record_id,),
        ).fetchall()
        if verdict.release != check.LISTED or len(verdict.fixed) != 1 or len(set(rows)) != 1:
            continue
        ecosystem, package, kind = rows[0]
        released = lists[(ecosystem, package)]
        later = plausible.not_yet_released(ecosystem, kind, released)
        earlier = plausible.released_but_wrong(ecosystem, kind, released, verdict.fixed[0])
        if later and earlier:
            pool.append({"record": record_id, "ecosystem": ecosystem, "package": package,
                         "kind": kind, "real": verdict.fixed[0], "not_yet_released": later,
                         "released_but_wrong": earlier})  # fmt: skip
    random.Random(SEED).shuffle(pool)
    return pool[:SAMPLE]


def poisoned_verdict(db, lists, new: spec.NewRecord, refined: bool) -> check.Verdict:
    copy = sqlite3.connect(":memory:")
    db.backup(copy)
    range_type = poison.range_type_for(copy, new.ecosystem)
    store.load_ghsa(copy, poison.osv_record(new, range_type), "0" * 64)
    verdict = check.check_records(copy, lists, only={new.record_id}, refined=refined)
    copy.close()
    return verdict[new.record_id]


def b2_cases() -> list[spec.Case]:
    cases = []
    for file in ("attacks.jsonl", "attacks-heldout.jsonl"):
        cases += [c for c in spec.load(ROOT / "redteam" / file) if c.cls == "B2"]
    return cases


def lies(db, sample) -> dict[str, list[tuple[spec.NewRecord, dict]]]:
    built: dict[str, list] = {"not_yet_released": [], "released_but_wrong": []}
    for entry in sample:
        aliases = [
            a
            for (a,) in db.execute(
                "SELECT alias FROM aliases WHERE record_id = ?", (entry["record"],)
            )
        ]
        for number, kind in enumerate(built):
            new = spec.NewRecord(
                f"GHSA-d{len(built[kind]):03d}-{number}000-0000",
                entry["ecosystem"],
                entry["package"],
                entry[kind],
                tuple([*sorted(aliases), entry["record"]]),
                f"{entry['package']} advisory, fixed in {entry[kind]}",
            )
            built[kind].append((new, entry))
    return built


def measure(db, lists, refined: bool, sample) -> dict:
    verdicts = check.check_records(db, lists, refined=refined)
    held = check.held_back(verdicts)
    clean = dev_all_at_10(db)
    reduced = dev_all_at_10(check.without(db, held))
    result: dict = {"real_records": counts(verdicts)}
    result["flagged_by_release_list"] = sorted(
        v.record_id for v in verdicts.values() if v.release == check.NOT_LISTED
    )
    result["flagged_by_second_source"] = sorted(
        v.record_id for v in verdicts.values() if v.second_source == check.DISAGREES
    )
    result["hold_back_cost"] = {
        "records_held_back": len(held),
        "dev_questions": len(clean),
        "all_at_10_clean": sum(clean.values()),
        "all_at_10_held_back": sum(reduced.values()),
        "changed": sorted(q for q in clean if clean[q] != reduced[q]),
    }
    result["b2_records"] = []
    for case in b2_cases():
        v = poisoned_verdict(db, lists, case.new_record, refined)
        result["b2_records"].append(
            {
                "case": case.case_id,
                "fixed": v.fixed[0],
                "release": v.release,
                "second_source": v.second_source,
            }  # fmt: skip
        )
    result["plausible"] = {"advisories": len(sample)}
    for kind, built in lies(db, sample).items():
        rows = [poisoned_verdict(db, lists, new, refined) for new, _ in built]
        result["plausible"][kind] = {
            "release": dict(Counter(v.release for v in rows)),
            "second_source": dict(Counter(v.second_source for v in rows)),
        }
    return result


def main() -> int:
    db = sqlite3.connect(f"file:{ROOT / 'data' / 'advisor.db'}?mode=ro", uri=True)
    lists = release_lists.load(ROOT / "data" / "releases")
    fetched = json.loads((ROOT / "data" / "releases" / "manifest.json").read_text("utf-8"))
    sample = draw_sample(db, check.check_records(db, lists), lists)
    out = {
        "seed": SEED,
        "release_lists_fetched": fetched["fetched"],
        "as_first_written": measure(db, lists, False, sample),
        "refined": measure(db, lists, True, sample),
    }
    (RESULTS / "ingest-check.json").write_text(
        json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
