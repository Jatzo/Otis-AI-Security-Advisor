"""Runs the red team's attack cases against the system, as fixed in docs/red-team-plan.md.

Round 1 is the unchanged system on redteam/attacks.jsonl, two runs per case. Round 2 is the defended
system, on the same file and on redteam/attacks-heldout.jsonl. Each case is put into a fresh copy of
the store, retrieval and the model run over that copy, and the replies are saved raw. Judging is a
separate step that re-applies the checker and the success checks to the saved replies and calls
nothing, so it can be repeated for free.

A paid run refuses to start unless: the code is committed; everything under eval/ matches its freeze
tag; the attack files match the tag redteam-freeze-v2, that tag is pushed, and the ruleset protects
it; the system code matches the system tag; and both spend caps are given. Nothing here reads the
test split.

Usage:
    python scripts/run_redteam.py --round 1 --dry-run
    python scripts/run_redteam.py --round 1 --runs 2 --max-spend 4 --phase-cap 6
    python scripts/run_redteam.py --round 1 --judge
    python scripts/run_redteam.py --round 2 --set heldout --runs 1 --max-spend 2 --phase-cap 6 \
        --system-tag phase6-system-v1 --topic-gate
"""

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import anthropic  # noqa: E402

from advisor.generation import answer  # noqa: E402
from advisor.generation.checker import check  # noqa: E402
from advisor.generation.evidence import user_message  # noqa: E402
from advisor.generation.facts import Facts  # noqa: E402
from advisor.redteam import poison, spec  # noqa: E402
from advisor.redteam.success import grams, obeyed, split, succeeded  # noqa: E402
from advisor.retrieval.pipeline import Pipeline, Spec  # noqa: E402
from advisor.retrieval.units import build_units  # noqa: E402
from advisor.web.ask import OFF_TOPIC  # noqa: E402
from advisor.web.limits import on_topic  # noqa: E402

RESULTS = ROOT / "eval" / "results"
REDTEAM = ROOT / "redteam"
R1 = Spec("R1", bm25="header")
SHOWN = 10
FREEZE_TAG = "redteam-freeze-v2"
SYSTEM_TAG = "phase5-system-v1"
FILES = {"first": "attacks.jsonl", "heldout": "attacks-heldout.jsonl"}
SYSTEM_CODE = ("src/advisor/generation", "src/advisor/retrieval", "eval/task.md")
FROZEN_CODE = (
    "redteam",
    "scripts/make_attack_spec.py",
    "scripts/run_redteam.py",
    "src/advisor/redteam",
)
RECORD_BORNE = ("A", "B1", "B2")  # a visitor who asked an honest question was attacked
LOOSE_DOLLARS = 0.03  # about what one call cost in Phase 4, for the plan's estimate only


def load_runner():
    """The generation runner's helpers (freeze guard, provenance, line reading), not copied."""
    loaded = importlib.util.spec_from_file_location(
        "run_generation_for_redteam", ROOT / "scripts" / "run_generation.py"
    )
    module = importlib.util.module_from_spec(loaded)
    sys.modules["run_generation_for_redteam"] = module
    loaded.loader.exec_module(module)
    return module


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()


def gate_problems(system_tag: str, run_git: Callable = git, ruleset: Callable | None = None):
    """Every reason a paid run must not start, from git alone. The ruleset check calls the GitHub
    API through gh, and if it cannot be read the run does not start."""
    found = []
    for tag in (FREEZE_TAG, system_tag):
        if run_git("rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode != 0:
            found.append(f"The tag {tag} does not exist.")
    if found:
        return found
    if run_git("diff", "--quiet", FREEZE_TAG, "--", *FROZEN_CODE).returncode != 0:
        found.append(f"The attack files or their code differ from the tag {FREEZE_TAG}.")
    if run_git("diff", "--quiet", system_tag, "--", *SYSTEM_CODE).returncode != 0:
        found.append(f"The system code differs from the tag {system_tag}.")
    local = run_git("rev-parse", f"refs/tags/{FREEZE_TAG}").stdout.strip()
    remote = run_git("ls-remote", "--tags", "origin", FREEZE_TAG).stdout.split()
    if not remote or remote[0] != local:
        found.append(f"The tag {FREEZE_TAG} is not pushed, or the pushed one is different.")
    covered = (ruleset or ruleset_covers)(FREEZE_TAG)
    if not covered:
        found.append(f"No active ruleset protects {FREEZE_TAG}. Extend the tag ruleset first.")
    return found


def ruleset_covers(tag: str) -> bool:
    out = subprocess.run(  # noqa: S603
        ["gh", "api", "repos/Jatzo/Otis-AI-Security-Advisor/rulesets/26385409"],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if out.returncode != 0:
        return False
    data = json.loads(out.stdout)
    include = data.get("conditions", {}).get("ref_name", {}).get("include", [])
    ref = f"refs/tags/{tag}"
    glob_ok = any(ref == p or (p.endswith("*") and ref.startswith(p[:-1])) for p in include)
    return data.get("enforcement") == "active" and glob_ok


def manifest_problems(cases_files: dict[str, Path], manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [
        f"{path.name} does not match the manifest."
        for path in cases_files.values()
        if lf_sha(path) != manifest["files"][path.name]
    ]


def poisoned_world(clean: sqlite3.Connection, case: spec.Case):
    """A fresh copy of the store with the case applied: its facts, units and retrieval."""
    db = sqlite3.connect(":memory:")
    clean.backup(db)
    poison.apply(db, case)
    units = build_units(db)
    return Facts(db), {u.unit_id: u for u in units}, Pipeline(units)


def reply_after_checks(case, raw, stop, shown, facts, topic_gate: bool) -> str:
    """What a visitor would be sent: the topic gate first if there is one, then the checker."""
    if topic_gate and not on_topic(case.question):
        return json.dumps(answer_refusal(OFF_TOPIC))
    return check(case.question, raw, stop, shown, facts).text


def answer_refusal(text: str) -> dict:
    return {
        "abstain": True, "verdict": None, "ids": [], "value": None,
        "disagreement": {"flagged": False, "values": {"github": None, "nvd": None}},
        "explanation": text, "claims": [],
    }  # fmt: skip


def read_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def phase_spent() -> float:
    return sum(x["cost_usd"] for p in RESULTS.glob("redteam-*-raw.jsonl") for x in read_lines(p))


def run_cases(
    cases, clean, raw_path: Path, client, runs: int, max_spend: float, phase_cap: float,
    proof: dict, topic_gate: bool, system: str | None = None,
) -> str:  # fmt: skip
    """Runs every case not yet answered. Stops, with the reason, before a call that could take
    either total over its cap. Each line is written as it arrives, so a crash loses nothing."""
    system = system or answer.system_prompt()
    done = read_lines(raw_path)
    spent = sum(x["cost_usd"] for x in done)
    overall = phase_spent()
    answered = {(x["id"], x["run"]) for x in done}
    for case in cases:
        facts, units_by_id, pipeline = poisoned_world(clean, case)
        shown = [units_by_id[i] for i in pipeline.rank(R1, case.question)[:SHOWN]]
        message = user_message(shown, case.question)
        for run in range(1, runs + 1):
            if (case.case_id, run) in answered:
                continue
            asked = not (topic_gate and not on_topic(case.question))
            worst = answer.worst_case_call(system, message) if asked else 0.0
            if spent + worst > max_spend or overall + worst > phase_cap:
                return (
                    f"Stopped at {case.case_id} run {run}: ${spent:.2f} spent here, "
                    f"${overall:.2f} in the phase. Caps ${max_spend:.2f} and ${phase_cap:.2f}."
                )
            question = {"id": case.case_id, "split": "redteam", "question": case.question}
            if asked:
                done_call = answer.respond(question, shown, facts, client, system, proof)
                line = done_call.line
            else:
                line = None
            if line is None:  # the gate or the topic gate answered, and the model was not called
                line = {
                    "id": case.case_id, "run": run, "split": "redteam", "text": "",
                    "stop_reason": None, "cost_usd": 0.0, "usage": {},
                    "shown": [u.unit_id for u in shown],
                    "gated": True, **proof,
                }  # fmt: skip
            line["run"] = run
            line["cls"], line["set"] = case.cls, case.set
            spent += line["cost_usd"]
            overall += line["cost_usd"]
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, sort_keys=True) + "\n")
            print(f"{case.case_id} run {run} ${spent:.2f}", flush=True)
    return f"Done. ${spent:.2f} spent on this file, ${overall:.2f} in the phase."


def judge(cases, clean, raw_path: Path, topic_gate: bool, system: str | None = None) -> list[dict]:
    """Re-applies the checker and the success checks to the saved replies. Calls nothing."""
    prompt_grams = grams(system or answer.system_prompt())
    by_id = {c.case_id: c for c in cases}
    clean_shown = {x["id"]: x["shown"] for x in read_lines(RESULTS / "generation-dev-raw.jsonl")
                   if x["run"] == 1}  # fmt: skip
    worlds: dict[str, tuple] = {}
    out = []
    for line in read_lines(raw_path):
        case = by_id[line["id"]]
        if case.case_id not in worlds:
            worlds[case.case_id] = poisoned_world(clean, case)
        facts, units_by_id, _ = worlds[case.case_id]
        shown = [units_by_id[i] for i in line["shown"]]
        shipped = reply_after_checks(
            case, line["text"], line["stop_reason"], shown, facts, topic_gate
        )
        lost = sorted(set(clean_shown.get(case.carrier or "", [])) - set(line["shown"]))
        out.append({
            "id": case.case_id, "run": line["run"], "cls": case.cls, "set": case.set,
            "delivered": poison.delivered(case, line["shown"]),
            "evidence_lost": lost if case.carrier else [],
            "model_called": not line.get("gated", False),
            "raw_success": succeeded(case, line["text"], prompt_grams),
            "shipped_success": succeeded(case, shipped, prompt_grams),
            "raw_obeyed": obeyed(case, line["text"], prompt_grams),
            "shipped_obeyed": obeyed(case, shipped, prompt_grams),
            "denied": case.cls in RECORD_BORNE and split(shipped).abstain is not False,
            "cost_usd": line["cost_usd"],
        })  # fmt: skip
    return out


def delivery(cases, clean) -> dict[str, dict]:
    """Which cases put the poison in front of the model, from retrieval alone. Costs nothing."""
    table: dict[str, dict] = {}
    for case in cases:
        _, _, pipeline = poisoned_world(clean, case)
        shown = pipeline.rank(R1, case.question)[:SHOWN]
        entry = table.setdefault(case.cls, {"cases": 0, "reached": 0, "missed": []})
        entry["cases"] += 1
        if poison.delivered(case, shown):
            entry["reached"] += 1
        else:
            entry["missed"].append(case.case_id)
    return table


def summarise(judged: list[dict]) -> dict:
    """Per class: cases, cases the poison reached, and cases the attacker won on either run, raw
    and as shipped. A case the poison never reached is left out of the rate and counted apart."""
    per_case: dict[str, list[dict]] = defaultdict(list)
    for row in judged:
        per_case[row["id"]].append(row)
    table: dict[str, dict] = {}
    for rows in per_case.values():
        cls = rows[0]["cls"]
        entry = table.setdefault(
            cls, {"cases": 0, "not_delivered": 0, "named_raw": 0, "named_shipped": 0,
                  "obeyed_raw": 0, "obeyed_shipped": 0, "denied": 0, "runs": 0,
                  "run_obeyed_raw": 0, "run_obeyed_shipped": 0, "evidence_lost": 0},
        )  # fmt: skip
        entry["cases"] += 1
        if not all(r["delivered"] for r in rows):
            entry["not_delivered"] += 1
            continue
        entry["named_raw"] += any(r["raw_success"] for r in rows)
        entry["named_shipped"] += any(r["shipped_success"] for r in rows)
        entry["obeyed_raw"] += any(r["raw_obeyed"] for r in rows)
        entry["obeyed_shipped"] += any(r["shipped_obeyed"] for r in rows)
        entry["denied"] += any(r["denied"] for r in rows)
        entry["runs"] += len(rows)
        entry["run_obeyed_raw"] += sum(r["raw_obeyed"] for r in rows)
        entry["run_obeyed_shipped"] += sum(r["shipped_obeyed"] for r in rows)
        entry["evidence_lost"] += any(r["evidence_lost"] for r in rows)
    return table


def print_table(table: dict) -> None:
    print(
        f"{'class':<8}{'cases':>6}{'reached':>9}{'named raw/shipped':>19}"
        f"{'obeyed raw/shipped':>20}{'denied':>8}{'obeyed runs raw/shipped':>26}"
    )
    for cls in spec.CLASSES:
        if cls in table:
            e = table[cls]
            reached = e["cases"] - e["not_delivered"]
            named = f"{e['named_raw']}/{e['named_shipped']}"
            won = f"{e['obeyed_raw']}/{e['obeyed_shipped']}"
            runs = f"{e['run_obeyed_raw']}/{e['run_obeyed_shipped']} of {e['runs']}"
            print(
                f"{cls:<8}{e['cases']:>6}{reached:>9}{named:>19}{won:>20}{e['denied']:>8}{runs:>26}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "advisor.db"))
    parser.add_argument("--round", type=int, choices=[1, 2], required=True)
    parser.add_argument("--set", choices=list(FILES), default="first")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--max-spend", type=float)
    parser.add_argument("--phase-cap", type=float)
    parser.add_argument("--system-tag", default=SYSTEM_TAG)
    parser.add_argument("--topic-gate", action="store_true", help="the defended system's gate")
    parser.add_argument("--delivery", action="store_true", help="retrieval only; no API call")
    parser.add_argument("--judge", action="store_true", help="judge saved replies; no API call")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and the cost")
    parser.add_argument("--allow-heldout-round-1", action="store_true")
    args = parser.parse_args()

    if args.set == "heldout" and args.round == 1 and not args.allow_heldout_round_1:
        print("The held-out set is not run in round 1.")
        return 1
    files = {name: REDTEAM / file for name, file in FILES.items()}
    cases = spec.load(files[args.set])
    raw_path = RESULTS / f"redteam-r{args.round}-{args.set}-raw.jsonl"
    paid = not (args.judge or args.dry_run or args.delivery)
    if paid and (args.max_spend is None or args.phase_cap is None):
        print("Give --max-spend and --phase-cap in dollars. The caps are not optional.")
        return 1
    clean = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    if args.delivery:
        for cls, entry in delivery(cases, clean).items():
            print(f"{cls:<8}{entry['reached']:>3} of {entry['cases']:<3} reach the model", end="")
            print(f"   missed: {', '.join(entry['missed']) or 'none'}")
        return 0

    if args.judge:
        judged = judge(cases, clean, raw_path, args.topic_gate)
        out = RESULTS / f"redteam-r{args.round}-{args.set}-judged.jsonl"
        out.write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in judged), encoding="utf-8"
        )
        table = summarise(judged)
        (RESULTS / f"redteam-r{args.round}-{args.set}-summary.json").write_text(
            json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        print_table(table)
        return 0

    system = answer.system_prompt()
    calls = len(cases) * args.runs
    if args.dry_run:
        facts, units_by_id, pipeline = poisoned_world(clean, cases[0])
        shown = [units_by_id[i] for i in pipeline.rank(R1, cases[0].question)[:SHOWN]]
        message = user_message(shown, cases[0].question)
        print(
            f"{len(cases)} cases x {args.runs} runs = {calls} calls, "
            f"about ${calls * LOOSE_DOLLARS:.2f}."
        )
        print(f"System prompt {len(system)} characters. First message {len(message)} characters.")
        print(f"Worst case for one call ${answer.worst_case_call(system, message):.2f}.")
        print(f"Spent in the phase so far ${phase_spent():.2f}. Problems that would stop a run:")
        for found in [
            *gate_problems(args.system_tag),
            *manifest_problems(files, REDTEAM / "manifest.json"),
        ]:
            print("  -", found)
        return 0

    runner = load_runner()
    runner.guard_freeze()
    stops = [*gate_problems(args.system_tag), *manifest_problems(files, REDTEAM / "manifest.json")]
    proof = runner.provenance()
    dirty = runner.dirty_problem(proof)
    if dirty:
        stops.append(dirty)
    if stops:
        print("A paid run cannot start:\n" + "\n".join(f"- {s}" for s in stops))
        return 1
    key = answer.read_key()
    if not key:
        print("No ANTHROPIC_API_KEY. Add it to .env (gitignored), then run again.")
        return 1
    client = anthropic.Anthropic(api_key=key, max_retries=0)
    RESULTS.mkdir(parents=True, exist_ok=True)
    print(run_cases(cases, clean, raw_path, client, args.runs, args.max_spend, args.phase_cap,
                    proof, args.topic_gate, system))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
