"""Builds Dev-R: questions.jsonl, gold.jsonl, review.md, evidence/ and build.json, all under
eval-retrieval/.

Dev-R is the retrieval-only development set of the evidence round (docs/evidence-round-plan.md,
step 2). It reuses the generators in eval/ and the Test v2 wrapper in eval-v2/ without changing
either. What is new:

- a new seed (20261116) and a new mix, fixed in SLOTS below after the pool count and the mix
  trial and before this script was first run to write files;
- subjects only from the advisories the reserve split left to Dev-R (eval-retrieval/split.json),
  and, where a kind has none left, advisories seen only by v1 dev, flagged `seen_dev`;
- no fallback to an advisory that a Test v1 or Test v2 question is about, and none to the reserve;
- v1 template wording only. No hand-written paraphrase, no abstain questions.

It makes no model call and no network request. It needs the local REST cache, the Maven jar and
Java for the version questions.

Usage: python eval-retrieval/build_questions.py
"""

import hashlib
import importlib.util
import json
import random
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVR = ROOT / "eval-retrieval"
sys.path.insert(0, str(ROOT / "eval"))

SEED = 20261116
SPLIT = "test"  # the v1 engine's name for a scored split; renamed "dev-r" when written
# type, subtype, questions. Scarce kinds first, as in v1 and Test v2. The counts are the mix
# approved on 17 November 2026; what each kind actually yields is in build.json.
SLOTS = [
    ("disagree", "fixed_differ", 4),
    ("disagree", "fixed_agree", 25),
    ("disagree", "one_silent", 25),
    ("disagree", "band_differ", 18),
    ("disagree", "band_agree", 25),
    ("multihop", "a2_kev_set", 1),
    ("multihop", "a3_kev_pick", 2),
    ("multihop", "a1_nvd_score", 35),
    ("version", "set", 6),
    ("multihop", "b_intersect", 5),
    ("multihop", "c_published", 25),
    ("multihop", "c_score", 25),
    ("version", "verdict", 24),
    ("lookup", "fixed_id", 12),
    ("lookup", "severity_id", 8),
    ("lookup", "map_id", 8),
]
PRIMARY = ("disagree", "multihop")  # plus version/set: the questions that need two or more records
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
# Role and mailing-list addresses that records quote as sources, plus a placeholder host and a
# pytest decorator that only look like addresses. Any other address is a person's.
KEEP_DOMAINS = (
    "lists.fedoraproject.org", "lists.opensuse.org", "github.com", "mitre.org", "nist.gov",
    "redhat.com", "debian.org", "vulncheck.com", "apache.org", "snyk.io",
    ".example", "pytest.mark.timeout",
)  # fmt: skip
PLAN_ROUNDS = 60  # long enough that a plan never runs out before its slot does


def refuse(*_args, **_kwargs):
    raise RuntimeError("The Dev-R build makes no network request.")


def load_v2():
    spec = importlib.util.spec_from_file_location(
        "eval_v2_build", ROOT / "eval-v2" / "build_questions.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_v2_build"] = module
    spec.loader.exec_module(module)
    return module


def read_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    urllib.request.urlopen = refuse
    v2 = load_v2()
    bq = sys.modules["build_questions"]
    # The v1 engine reads these module values when it runs, so they are set before it does.
    # The engine reads paraphrases.json from EVAL when it loads. Dev-R has no hand-written
    # paraphrases, so the world is loaded from the Test v2 folder (read only) and the outputs
    # are pointed at this folder afterwards.
    bq.SEED, bq.EVAL, bq.EVIDENCE = SEED, ROOT / "eval-v2", DEVR / "evidence"
    world = bq.load_world()
    bq.EVAL = DEVR
    jar_cache = ROOT / "data" / "tools" / "jar_cache.json"
    bq.load_jar_cache(world.jar, jar_cache)  # read only: it is not saved back
    split = json.loads((DEVR / "split.json").read_text(encoding="utf-8"))
    eligible = set(split["dev_r_eligible"]["ids"])
    seen_dev = set(split["seen_dev_only"]["ids"])
    everything = set(world.adv)
    strict_ban = everything - eligible
    relaxed_ban = everything - eligible - seen_dev
    earlier = read_rows(ROOT / "eval" / "questions.jsonl") + read_rows(
        ROOT / "eval-v2" / "questions.jsonl"
    )

    builder = v2.Builder(world, bq.Absence(DEVR / "evidence" / "checks.json"), [])
    builder.rng = random.Random(SEED)  # noqa: S311 - choosing questions, not secrets
    builder.v1_text = {q["question"] for q in earlier}
    builder.st = v2.State(strict_ban)
    cycle = [(e, w) for e in ("PyPI", "Maven", "npm") for w in ("yes", "no")]
    builder.plans = {
        "verdict": {SPLIT: cycle * PLAN_ROUNDS},
        "set": {SPLIT: ["PyPI", "Maven", "npm"] * PLAN_ROUNDS},
    }
    builder.free = False
    dispatch = {
        ("lookup", "fixed_id"): builder.l_fixed_id,
        ("lookup", "severity_id"): builder.l_severity_id,
        ("lookup", "map_id"): builder.l_map_id,
        ("version", "verdict"): builder.v_verdict, ("version", "set"): builder.v_set,
        ("multihop", "a1_nvd_score"): builder.m_nvd_score,
        ("multihop", "a2_kev_set"): builder.m_kev_set,
        ("multihop", "a3_kev_pick"): builder.m_kev_pick,
        ("multihop", "b_intersect"): builder.m_intersect,
        ("multihop", "c_published"): builder.m_pair, ("multihop", "c_score"): builder.m_pair,
        ("disagree", "band_differ"): builder.d_band, ("disagree", "band_agree"): builder.d_band,
        ("disagree", "fixed_differ"): builder.d_fixed,
        ("disagree", "fixed_agree"): builder.d_fixed,
        ("disagree", "one_silent"): builder.d_silent,
    }  # fmt: skip
    for kind, sub, count in SLOTS:
        for _ in range(count):
            item = None
            for relaxed in (False, True):  # fresh advisories first, seen_dev ones only if none left
                builder.st.banned = relaxed_ban if relaxed else strict_ban
                builder.used_free = False
                try:
                    item = dispatch[(kind, sub)](sub, SPLIT)
                except IndexError:
                    item = None
                if item is not None:
                    break
            if item is None:
                builder.short[(kind, sub, SPLIT)] += 1
                continue
            item.tags.setdefault("form", "v1")
            item.tags["seen_dev"] = bool(set(item.subjects) & seen_dev)
            builder.st.take(item, SPLIT, item.tags["slice"] == "post")
    builder.st.banned = strict_ban

    written = bq.write_outputs(builder)
    bq.write_review(written["questions"], written["gold"], builder)
    finish(builder, written, eligible, seen_dev)
    scrubbed = scrub_evidence()
    summary = Counter(f"{q['type']}/{q['subtype']}" for q in written["questions"])
    primary = [q for q in written["questions"] if is_primary(q)]
    report = {
        "seed": SEED,
        "slots": [list(s) for s in SLOTS],
        "built": dict(sorted(summary.items())),
        "total": len(written["questions"]),
        "primary_stratum": len(primary),
        "primary_unflagged": sum(not q["seen_dev"] for q in primary),
        "seen_dev_questions": sum(q["seen_dev"] for q in written["questions"]),
        "advisories_used": len(builder.st.uses),
        "uses": dict(sorted(Counter(builder.st.uses.values()).items())),
        "shortfalls": {"/".join(k[:2]): n for k, n in builder.short.items()},
        "dropped_by_reason": dict(builder.drops),
        "evidence_files_with_a_personal_email_replaced": scrubbed,
        "sha256": {name: sha256(DEVR / name) for name in ("questions.jsonl", "gold.jsonl")},
    }
    (DEVR / "build.json").write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, indent=1, sort_keys=True))  # noqa: T201


def scrub_evidence() -> int:
    """Replaces a person's email address in the evidence copies. The records the questions are
    built from are untouched, so no question or gold changes."""
    changed = 0

    def swap(match: re.Match) -> str:
        return match.group(0) if match.group(1).endswith(KEEP_DOMAINS) else "[email removed]"

    for path in sorted((DEVR / "evidence").glob("*/*.json")):
        text = path.read_text(encoding="utf-8")
        scrubbed = EMAIL.sub(swap, text)
        if scrubbed != text:
            path.write_text(scrubbed, encoding="utf-8", newline="\n")
            changed += 1
    return changed


def is_primary(q: dict) -> bool:
    return q["type"] in PRIMARY or (q["type"] == "version" and q["subtype"] == "set")


def finish(builder, written: dict, eligible: set[str], seen_dev: set[str]) -> None:
    """Gives the ids a dr- prefix, the split the name dev-r, and each question its flags."""
    tags = {i.question: i.tags for _, i in builder.st.items}
    questions, golds = written["questions"], written["gold"]
    for q in questions:
        q["id"], q["split"] = f"dr-{q['id']}", "dev-r"
        q["form"] = tags[q["question"]]["form"]
        q["seen_dev"] = tags[q["question"]]["seen_dev"]
        if not set(q["subjects"]) <= eligible | seen_dev:
            raise RuntimeError(f"{q['id']} is about an advisory Dev-R may not use.")
    for gd in golds:
        gd["id"] = f"dr-{gd['id']}"
    lines = lambda rows: "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)  # noqa: E731
    (DEVR / "questions.jsonl").write_text(lines(questions), encoding="utf-8", newline="\n")
    (DEVR / "gold.jsonl").write_text(lines(golds), encoding="utf-8", newline="\n")
    review = DEVR / "review.md"
    text = review.read_text(encoding="utf-8")
    text = re.sub(r"\| (lk|vr|mh|ab|dg)-(\d{3}) \| test \|", r"| dr-\1-\2 | dev-r |", text)
    text = text.replace("Review table for the evaluation set", "Review table for Dev-R")
    text = text.replace("eval/build_questions.py", "eval-retrieval/build_questions.py")
    text = text.replace("| Type | Dev | Test |", "| Type | (none) | Dev-R |")
    text = text.replace("Answerable test questions", "Answerable Dev-R questions")
    review.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
