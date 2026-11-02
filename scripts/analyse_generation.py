"""The tables docs/generation-results.md reports, worked out from the saved dev results.

Reads the raw and checked result lines and their scored versions (eval/score.py --out), the
retrieval results for R1 and the committed ID snapshot. Writes
eval/results/generation-dev-analysis.json and prints it. Nothing here calls a model.
With --label v2 it reads the generation-v2-dev files, writes generation-v2-dev-analysis.json and
also compares the run with the first one.

Usage (R is eval/results/generation-dev):
    python eval/score.py score --results R-raw.jsonl --split dev --out R-raw.scored.jsonl
    python eval/score.py score --results R-checked.jsonl --split dev --out R-checked.scored.jsonl
    python scripts/analyse_generation.py
"""

import argparse
import importlib.util
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.generation.reading import ANY_ID, read_reply  # noqa: E402

RESULTS = ROOT / "eval" / "results"


def read_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_scorer():
    spec = importlib.util.spec_from_file_location("score", ROOT / "eval" / "score.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["score"] = module
    spec.loader.exec_module(module)
    return module


def keyed(rows: list[dict]) -> dict[tuple[int, str], dict]:
    return {(r["run"], r["id"]): r for r in rows}


def fabricated(score, ids, question: str, answer: dict, with_claims: bool) -> bool:
    """Whether the reply holds an ID the snapshot proves nonexistent, outside the question's own."""
    body = dict(answer)
    if not with_claims:
        body.pop("claims", None)
    asked = {score.normal_id(i) for i in ANY_ID.findall(question)}
    found = {score.normal_id(i) for i in ANY_ID.findall(json.dumps(body))} - asked
    return any(ids.label(i) == "nonexistent" for i in found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", help="read and write the files of a run with a changed prompt")
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()
    label, split = args.label, args.split
    if split == "test" and label:
        raise SystemExit("The test run has no label: it is run once.")
    if label is not None and not re.fullmatch(r"[a-z0-9]+", label):
        raise SystemExit(f"The label {label!r} must be lower-case letters and digits only.")
    if split == "test":
        stem = "test-generation"
    else:
        stem = f"generation-{label}-dev" if label else "generation-dev"
    score = load_scorer()
    questions = {
        q["id"]: q for q in read_lines(ROOT / "eval" / "questions.jsonl") if q["split"] == split
    }
    raw_lines = keyed(read_lines(RESULTS / f"{stem}-raw.jsonl"))
    checked_lines = keyed(read_lines(RESULTS / f"{stem}-checked.jsonl"))
    raw = keyed(read_lines(RESULTS / f"{stem}-raw.scored.jsonl"))
    checked = keyed(read_lines(RESULTS / f"{stem}-checked.scored.jsonl"))
    if split == "test":
        retrieval = json.loads((RESULTS / "test-retrieval.json").read_text(encoding="utf-8"))
        r1_rows = retrieval["rows"]
    else:
        retrieval = json.loads((RESULTS / "retrieval-dev.json").read_text(encoding="utf-8"))
        r1_rows = retrieval["results"]["R1"]["rows"]
    r1_all = {r["id"]: r["all@10"] for r in r1_rows}
    ids = score.load_ids()
    runs = sorted({run for run, _ in raw})
    out: dict = {"runs": runs}

    def right(table, run, qid):
        return table[(run, qid)]["outcome"] == "correct"

    types = sorted({q["type"] for q in questions.values()})
    out["correct_by_type"] = {
        name: {
            side: [
                sum(right(table, run, q) for q in questions if questions[q]["type"] == name)
                for run in runs
            ]
            for side, table in (("raw", raw), ("checked", checked))
        }
        | {"questions": sum(1 for q in questions.values() if q["type"] == name)}
        for name in types
    }
    out["correct_all"] = {
        side: [sum(right(table, run, q) for q in questions) for run in runs]
        for side, table in (("raw", raw), ("checked", checked))
    }
    answerable = [q for q in questions if questions[q]["answers_with"] != "abstain"]
    out["correct_answerable"] = {
        side: [sum(right(table, run, q) for q in answerable) for run in runs]
        for side, table in (("raw", raw), ("checked", checked))
    }

    # What the checker did, per reply.
    verdicts = Counter()
    by_rule = Counter()
    for line in checked_lines.values():
        info = line["checker"]
        verdicts[(info["route"], info["verdict"])] += 1
        if info["verdict"] == "refused" and info["route"] == "checker":
            by_rule[info["rule"]] += 1
    out["routes"] = {f"{route}/{verdict}": n for (route, verdict), n in sorted(verdicts.items())}
    out["checker_refusals_by_rule"] = dict(sorted(by_rule.items()))

    passed = [
        k
        for k, line in checked_lines.items()
        if line["checker"]["verdict"] in ("passed", "repaired")
    ]
    false_pass = [k for k in passed if not right(checked, *k)]
    out["passed_replies"] = len(passed)
    out["false_passes"] = {
        "count": len(false_pass),
        "share_of_passed_right": round(1 - len(false_pass) / len(passed), 3) if passed else None,
        "by_type": dict(Counter(questions[q]["type"] for _, q in false_pass)),
        "claim_kinds": {
            f"run{run} {q}": [c["kind"] for c in checked_lines[(run, q)]["checker"]["claims"]]
            for run, q in false_pass
        },
    }
    harmed = [k for k in raw if right(raw, *k) and not right(checked, *k)]
    helped = [
        k for k in raw
        if not right(raw, *k) and not raw[k]["abstained"]
        and checked_lines[k]["checker"]["route"] == "checker"
        and checked_lines[k]["checker"]["verdict"] in ("refused", "repaired")
    ]  # fmt: skip
    out["harmed"] = [
        {
            "run": run, "id": q, "rule": checked_lines[(run, q)]["checker"]["rule"],
            "reasons": checked_lines[(run, q)]["checker"]["reasons"],
        }
        for run, q in sorted(harmed, key=lambda k: (k[1], k[0]))
    ]  # fmt: skip
    out["helped"] = [{"run": run, "id": q} for run, q in sorted(helped)]
    by_route: dict[str, Counter] = defaultdict(Counter)
    for (_, qid), line in checked_lines.items():
        if line["checker"]["verdict"] in ("refused", "abstained"):
            route = line["checker"]["route"]
            by_route[route]["replies"] += 1
            by_route[route]["should_abstain"] += questions[qid]["answers_with"] == "abstain"
    out["abstention_by_route"] = {r: dict(c) for r, c in sorted(by_route.items())}
    out["repaired"] = sum(
        1 for line in checked_lines.values() if line["checker"]["verdict"] == "repaired"
    )

    # Claims by kind and outcome, and KEV claims with and without a KEV unit shown.
    tally: dict[str, Counter] = defaultdict(Counter)
    kev_shown = Counter()
    for line in checked_lines.values():
        for claim in line["checker"]["claims"]:
            tally[claim["kind"]][claim["status"]] += 1
            if claim["kind"] == "kev":
                kev_shown[(claim["status"], claim["kev_unit_shown"])] += 1
    out["claims_by_kind"] = {kind: dict(counts) for kind, counts in sorted(tally.items())}
    out["kev_claims"] = {
        f"{status}, kev unit shown {shown}": n
        for (status, shown), n in sorted(kev_shown.items(), key=str)
    }
    failed_kinds = Counter()
    for line in checked_lines.values():
        info = line["checker"]
        if info["route"] == "checker":
            for claim in info["claims"]:
                if claim["status"] != "passed":
                    failed_kinds[(info["rule"], claim["kind"], claim["status"])] += 1
    out["refusal_claims"] = {
        f"rule {r} {k} {s}": n for (r, k, s), n in sorted(failed_kinds.items())
    }
    out["polarity_unchecked_verdicts"] = sum(
        1
        for line in checked_lines.values()
        if line["checker"]["polarity_checked"] is False  # fmt: skip
    )

    # Fabricated IDs in the raw replies, twice, and in the checked replies.
    def fabrication(lines, with_claims):
        found = 0
        for (_, qid), line in lines.items():
            answer, _ = read_reply(line["text"])
            if answer and fabricated(score, ids, questions[qid]["question"], answer, with_claims):
                found += 1
        return found

    out["fabricated_replies"] = {
        "raw_fields_and_explanation": fabrication(raw_lines, False),
        "raw_with_claims": fabrication(raw_lines, True),
        "checked_with_claims": fabrication(checked_lines, True),
        "replies": len(raw_lines),
    }
    out["ids_removed_by_repair"] = sum(
        len(line["checker"]["removed_ids"]) for line in checked_lines.values()
    )

    # Retrieval against the answer, for the answerable questions that R1 was scored on.
    link = Counter()
    for (_, qid), row in checked.items():
        if qid in r1_all:
            evidence = "R1 had all evidence" if r1_all[qid] else "R1 missed evidence"
            result = "checked correct" if row["outcome"] == "correct" else "checked wrong"
            link[(evidence, result)] += 1
    out["retrieval_link"] = {f"{a} / {b}": n for (a, b), n in sorted(link.items())}

    # Cost and time, per query.
    costs = [line["cost_usd"] for line in raw_lines.values()]
    seconds = sorted(line["latency_s"] + line["retrieval_s"] for line in raw_lines.values())
    out["cost_per_query_usd"] = round(statistics.fmean(costs), 4)
    out["cost_total_usd"] = round(sum(costs), 2)
    out["tokens_per_query"] = {
        "input": round(statistics.fmean(line["usage"]["input"] for line in raw_lines.values())),
        "output": round(statistics.fmean(line["usage"]["output"] for line in raw_lines.values())),
    }
    out["latency_s"] = {
        "median": round(statistics.median(seconds), 2),
        "p95": round(seconds[min(len(seconds) - 1, int(0.95 * len(seconds)))], 2),
    }
    out["stop_reasons"] = dict(Counter(line["stop_reason"] for line in raw_lines.values()))
    out["parse_failures"] = sum(1 for r in checked.values() if r["outcome"] == "parse_failure")

    # Per question: the outcome in every run, raw and checked, with R1's evidence.
    def mark(table, run, q):
        return table[(run, q)]["outcome"][0] + ("*" if table[(run, q)]["abstained"] else "")

    def route(run, q):
        info = checked_lines[(run, q)]["checker"]
        return f"{info['route']}/{info['verdict']}"

    out["per_question"] = {
        q: {
            "type": questions[q]["type"],
            "subtype": questions[q]["subtype"],
            "r1_all_evidence": r1_all.get(q),
            "raw": [mark(raw, run, q) for run in runs],
            "checked": [mark(checked, run, q) for run in runs],
            "route": [route(run, q) for run in runs],
        }
        for q in questions
    }

    def verdict_set(lines):
        counts = Counter()
        for (_, qid), line in lines.items():
            reply, _ = read_reply(line["text"])
            if reply and reply["verdict"] is not None:
                counts[questions[qid]["type"]] += 1
        return dict(counts)

    out["verdict_set_by_type"] = verdict_set(raw_lines)
    out["rule7_refusals_on_disagree"] = sum(
        1
        for (_, qid), line in checked_lines.items()
        if line["checker"]["route"] == "checker"
        and line["checker"]["rule"] == 7
        and questions[qid]["type"] == "disagree"
    )
    if label:
        first_raw = keyed(read_lines(RESULTS / "generation-dev-raw.scored.jsonl"))
        first_checked = keyed(read_lines(RESULTS / "generation-dev-checked.scored.jsonl"))
        first_harmed = {
            k for k in first_raw if right(first_raw, *k) and not right(first_checked, *k)
        }
        out["first_run_verdict_set_by_type"] = verdict_set(
            keyed(read_lines(RESULTS / "generation-dev-raw.jsonl"))
        )
        out["raw_flips_against_first"] = [
            {
                "run": run,
                "id": qid,
                "first": first_raw[(run, qid)]["outcome"],
                "now": row["outcome"],
            }
            for (run, qid), row in sorted(raw.items(), key=lambda k: (k[0][1], k[0][0]))
            if (first_raw[(run, qid)]["outcome"], first_raw[(run, qid)]["abstained"])
            != (row["outcome"], row["abstained"])
        ]
        out["harmed_not_in_first"] = [
            {"run": run, "id": qid} for run, qid in sorted(set(map(tuple, harmed)) - first_harmed)
        ]
    path = RESULTS / f"{stem}-analysis.json"
    path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps({k: v for k, v in out.items() if k != "per_question"}, indent=1, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
