"""Runs the retrieval candidates on Dev-R, once, and applies the plan's adoption rule.

This is step 2 of docs/evidence-round-plan.md. It calls no model and no network. It needs the
local store (data/advisor.db) and Dev-R (eval-retrieval/), and it refuses to start unless:
- the tag eval-freeze-retrieval-v1 exists and everything frozen under eval-retrieval/ matches it;
- this script and src/advisor/retrieval/candidates.py are committed, unchanged since that tag;
- eval-retrieval/results/study2.json does not exist yet (the run is made once).

What it scores, on the answerable Dev-R questions, as "all the needed records are in the list":
- control R1 at 10, and R1 at 15, 20 (which is candidate R11) and 25;
- candidate R9 (linked records within 10) and R9x (the same up to 20, descriptive only);
- candidate R10 (the records of the one package the question names, up to 20).

The primary stratum is the questions that need two or more records: multi-hop, sources-disagree
and version-set. Questions that use an advisory only v1 dev used (`seen_dev`) are reported as their
own slice and carry no claim. A slice, for the do-no-harm rule, is a question type, or whether the
question names an ID. The prompt size is the character count of the user message the model would
see, a stand-in for input tokens. The real figure comes from the dev generation check.

Usage:
    python scripts/retrieval_study2.py --out docs/retrieval-study2.md
"""

import argparse
import importlib.util
import json
import re
import sqlite3
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.generation.evidence import user_message  # noqa: E402
from advisor.packages import PACKAGES  # noqa: E402
from advisor.retrieval import candidates  # noqa: E402
from advisor.retrieval.metrics import all_evidence_at, evidence_ids, recall_at  # noqa: E402
from advisor.retrieval.pipeline import Pipeline, Spec  # noqa: E402
from advisor.retrieval.units import build_units  # noqa: E402
from advisor.stats import mcnemar_p  # noqa: E402

TAG = "eval-freeze-retrieval-v1"
DEVR = ROOT / "eval-retrieval"
RESULTS_DIR = "eval-retrieval/results"
OUT = ROOT / RESULTS_DIR / "study2.json"
GUARD = ROOT / "scripts" / "check_eval_retrieval_frozen.py"
GUARDED = ["scripts/retrieval_study2.py", "src/advisor/retrieval/candidates.py"]
R1 = Spec("R1", bm25="header")
ID = re.compile(r"GHSA-[\w-]+|CVE-\d{4}-\d+", re.IGNORECASE)
MIN_PRIMARY = 140
MIN_SCOPED = 40
FLOOR_POINTS, FLOOR_QUESTIONS, ALPHA = 0.05, 6, 0.05
TOKEN_CEILING = {"R9": 1.3, "R10": 2.0, "R11": 2.0}
CHEAPER_FIRST = ["R9", "R11", "R10"]
LISTS = ["R1@10", "R1@15", "R1@20", "R1@25", "R9", "R9x", "R10"]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(ROOT), *args],  # noqa: S607
        capture_output=True, text=True, check=False,
    )  # fmt: skip


def problems() -> list[str]:
    """Every reason this run may not start."""
    spec = importlib.util.spec_from_file_location("check_eval_retrieval_frozen", GUARD)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    found = guard.check(ROOT, TAG)
    if not found:
        for path in GUARDED:
            at_tag = git("rev-parse", f"{TAG}:{path}")
            if at_tag.returncode != 0:
                found.append(f"{path} is not in {TAG}.")
            elif at_tag.stdout != git("rev-parse", f"HEAD:{path}").stdout:
                found.append(f"{path} was committed again after {TAG}.")
        # The guard compares commits. The run reads the files on disk, so an edit that is not
        # committed, or a new file, has to be caught too.
        loose = git(
            "status", "--porcelain", "--", "eval-retrieval", *GUARDED, f":(exclude){RESULTS_DIR}"
        )
        found += [
            f"{line[3:]} is changed or new and not committed." for line in loose.stdout.splitlines()
        ]
    if OUT.exists():
        found.append(f"{OUT.relative_to(ROOT)} exists. The run is made once.")
    return found


def read_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_items() -> list[dict]:
    questions = read_rows(DEVR / "questions.jsonl")
    gold = {g["id"]: g for g in read_rows(DEVR / "gold.jsonl")}
    items = []
    for q in questions:
        needed = evidence_ids(gold[q["id"]])
        items.append(
            {
                "id": q["id"],
                "type": q["type"],
                "subtype": q["subtype"],
                "question": q["question"],
                "needed": sorted(needed),
                "records": len(needed),
                "names_id": bool(ID.search(q["question"])),
                "seen_dev": q["seen_dev"],
                "primary": q["type"] in ("multihop", "disagree")
                or (q["type"] == "version" and q["subtype"] == "set"),
            }
        )
    return items


def score_lists(item: dict, ranked: list[str], units, links, packages, by_id) -> dict:
    """Every list for one question, scored."""
    needed = set(item["needed"])
    scoped_list, scoped = candidates.r10(ranked, units, item["question"], packages)
    lists = {
        "R1@10": candidates.r1(ranked, 10),
        "R1@15": candidates.r1(ranked, 15),
        "R1@20": candidates.r1(ranked, 20),
        "R1@25": candidates.r1(ranked, 25),
        "R9": candidates.r9(ranked, links, 10),
        "R9x": candidates.r9(ranked, links, 20),
        "R10": scoped_list,
    }
    out = {"scoped": scoped}
    for name, ids in lists.items():
        shown = [by_id[i] for i in ids]
        out[name] = {
            "ids": ids,
            "all": all_evidence_at(ids, needed, len(ids)),
            "recall": recall_at(ids, needed, len(ids)),
            "chars": len(user_message(shown, item["question"])),
        }
    return out


def compare(rows: list[dict], candidate: str, control: str) -> dict:
    """Gained and lost questions, the exact McNemar p and the size of the gain."""
    gained = sum(r[candidate]["all"] and not r[control]["all"] for r in rows)
    lost = sum(r[control]["all"] and not r[candidate]["all"] for r in rows)
    n = len(rows)
    return {
        "n": n,
        "control_hits": sum(r[control]["all"] for r in rows),
        "candidate_hits": sum(r[candidate]["all"] for r in rows),
        "gained": gained,
        "lost": lost,
        "net": gained - lost,
        "p": mcnemar_p(gained, lost),
        "needed_net": max(FLOOR_POINTS * n, FLOOR_QUESTIONS),
    }


def slices(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(f"type {r['type']}", []).append(r)
        out.setdefault(f"names an ID: {r['names_id']}", []).append(r)
    return dict(sorted(out.items()))


def do_no_harm(rows: list[dict], candidate: str, control: str) -> dict:
    """At most 1 question lost on each slice, and at most 1 point lost on the whole set."""
    lost = {name: compare(part, candidate, control)["lost"] for name, part in slices(rows).items()}
    overall = compare(rows, candidate, control)
    drop = overall["control_hits"] - overall["candidate_hits"]
    return {
        "slice_lost": lost,
        "net_drop_overall": drop,
        "passes": max(lost.values(), default=0) <= 1 and drop <= 0.01 * len(rows),
    }


def holm(p_values: dict[str, float]) -> dict[str, bool]:
    """Step-down: the smallest p against 0.05 / m, the next against 0.05 / (m - 1), and so on,
    stopping at the first that fails."""
    order = sorted(p_values, key=p_values.get)
    result = dict.fromkeys(p_values, False)
    for place, name in enumerate(order):
        if p_values[name] < ALPHA / (len(order) - place):
            result[name] = True
        else:
            break
    return result


def analyse(rows: list[dict]) -> dict:
    """The plan's rules 1 to 5 on scored rows. Rows with seen_dev are held out of the tests."""
    fresh = [r for r in rows if not r["seen_dev"]]
    primary = [r for r in fresh if r["primary"]]
    report: dict = {
        "questions": len(rows),
        "fresh_questions": len(fresh),
        "seen_dev_questions": len(rows) - len(fresh),
        "primary_fresh": len(primary),
        "rule1_enough_primary": len(primary) >= MIN_PRIMARY,
    }
    scoped = [r for r in primary if r["scoped"]]
    report["r10_scoped_primary"] = len(scoped)
    report["r10_scoped_all"] = sum(r["scoped"] for r in rows)
    report["r10_judged"] = len(scoped) >= MIN_SCOPED
    tests = {
        "R9": compare(primary, "R9", "R1@10"),
        "R11": compare(primary, "R1@20", "R1@10"),
    }
    if report["r10_judged"]:
        tests["R10"] = compare(scoped, "R10", "R1@20")
    held = holm({name: t["p"] for name, t in tests.items()})
    harm = {
        "R9": do_no_harm(fresh, "R9", "R1@10"),
        "R11": do_no_harm(fresh, "R1@20", "R1@10"),
    }
    if report["r10_judged"]:
        kept = [r for r in fresh if r["scoped"]]
        own, wider = do_no_harm(kept, "R10", "R1@20"), do_no_harm(kept, "R10", "R1@10")
        harm["R10"] = {
            "against_R1@20": own,
            "against_R1@10": wider,
            "passes": own["passes"] and wider["passes"],
        }
    passed = {}
    for name, test in tests.items():
        passed[name] = (
            report["rule1_enough_primary"]
            and test["net"] >= test["needed_net"]
            and held[name]
            and harm[name]["passes"]
        )
    yardstick = {
        "R9": compare(primary, "R9", "R1@10"),
        "R11": compare(primary, "R1@20", "R1@10"),
        "R10": compare(primary, "R10", "R1@10"),
        "R9x": compare(primary, "R9x", "R1@10"),
        "R1@15": compare(primary, "R1@15", "R1@10"),
        "R1@25": compare(primary, "R1@25", "R1@10"),
    }
    winners = [n for n in CHEAPER_FIRST if passed.get(n)]
    best = max(winners, key=lambda n: (yardstick[n]["net"], -CHEAPER_FIRST.index(n)), default=None)
    report |= {
        "tests": tests,
        "holm_pass": held,
        "do_no_harm": harm,
        "passes_rules_1_to_3": passed,
        "yardstick_on_primary": yardstick,
        "leading_candidate": best,
    }
    base = statistics.fmean(r["R1@10"]["chars"] for r in rows)
    report["prompt_chars_ratio_to_R1@10"] = {
        name: round(statistics.fmean(r[name]["chars"] for r in rows) / base, 3) for name in LISTS
    }
    report["prompt_chars_ceiling"] = TOKEN_CEILING
    return report


def table(rows: list[dict], title: str, key) -> list[str]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(str(key(r)), []).append(r)
    head = ["Group", "n", *LISTS]
    lines = [f"### {title}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for name, part in sorted(groups.items()):
        cells = [f"{sum(r[x]['all'] for r in part)}/{len(part)}" for x in LISTS]
        lines.append(f"| {name} | {len(part)} | " + " | ".join(cells) + " |")
    return [*lines, ""]


def markdown(rows: list[dict], report: dict) -> str:
    fresh = [r for r in rows if not r["seen_dev"]]
    held = [r for r in rows if r["seen_dev"]]
    lines = [
        "# Retrieval study 2 on Dev-R",
        "",
        "Written by `scripts/retrieval_study2.py`, with no model and no network. See "
        "[the plan](evidence-round-plan.md), step 2. A cell is questions where every needed "
        "record was in the list, over questions in the group. R1@20 is candidate R11.",
        "",
        f"{report['questions']} questions, {report['fresh_questions']} on advisories no earlier "
        f"question used and {report['seen_dev_questions']} on advisories only v1 dev used "
        f"(held out, no claim). Primary stratum without the held-out ones: "
        f"{report['primary_fresh']} (rule 1 needs {MIN_PRIMARY}). R10 scoped "
        f"{report['r10_scoped_primary']} of them (it needs {MIN_SCOPED} to be judged) and "
        f"{report['r10_scoped_all']} questions in all.",
        "",
        "## Tests against the controls",
        "",
        "| Candidate | against | n | control | candidate | gained | lost | net | needed net | p |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    against = {"R9": "R1@10", "R11": "R1@10", "R10": "R1@20"}
    for name, t in report["tests"].items():
        lines.append(
            f"| {name} | {against[name]} | {t['n']} | {t['control_hits']} | {t['candidate_hits']} "
            f"| {t['gained']} | {t['lost']} | {t['net']} | {t['needed_net']:.1f} | {t['p']:.4f} |"
        )
    lines += [
        "",
        f"Holm: {report['holm_pass']}. Do no harm: "
        f"{ {k: v['passes'] for k, v in report['do_no_harm'].items()} }. "
        f"Passes rules 1 to 3: {report['passes_rules_1_to_3']}. "
        f"Leading candidate: {report['leading_candidate'] or 'none'}.",
        "",
        "## Against R1 at 10 on the whole primary stratum (the common yardstick)",
        "",
        "| List | candidate hits | control hits | gained | lost | net |",
        "|---|---|---|---|---|---|",
    ]
    for name, t in report["yardstick_on_primary"].items():
        lines.append(
            f"| {name} | {t['candidate_hits']} | {t['control_hits']} | {t['gained']} "
            f"| {t['lost']} | {t['net']} |"
        )
    lines += [
        "",
        "## Prompt size, as a share of R1 at 10 (characters of the user message)",
        "",
        f"{report['prompt_chars_ratio_to_R1@10']}. Ceilings for the dev generation check: "
        f"{report['prompt_chars_ceiling']}.",
        "",
        "## Where the hits are",
        "",
        *table(
            [r for r in fresh if r["primary"]], "Primary stratum by subtype", lambda r: r["subtype"]
        ),
        *table(fresh, "All fresh questions by type", lambda r: r["type"]),
        *table(
            fresh,
            "All fresh questions by whether the question names an ID",
            lambda r: r["names_id"],
        ),
        *table(held, "Held out (seen_dev), no claim", lambda r: f"{r['type']}/{r['subtype']}"),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="write the tables as Markdown to this path")
    parser.add_argument("--db", default=str(ROOT / "data" / "advisor.db"))
    args = parser.parse_args()
    stop = problems()
    if stop:
        for line in stop:
            print(f"STOP: {line}", file=sys.stderr)
        return 1
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    units = build_units(db)
    by_id = {u.unit_id: u for u in units}
    pipeline = Pipeline(units)
    links = candidates.Links(units)
    packages = [p.name for p in PACKAGES]
    rows = []
    for item in load_items():
        ranked = pipeline.rank(R1, item["question"])
        rows.append({**item, **score_lists(item, ranked, units, links, packages, by_id)})
    report = analyse(rows)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps({"report": report, "rows": rows}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    text = markdown(rows, report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
