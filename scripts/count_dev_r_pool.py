"""Counts how many Dev-R questions each kind of question could yield, before Dev-R is built.

This is the pool count in step 1 of docs/evidence-round-plan.md. It calls no retrieval and no model
and makes no network request: it asks the question generators in eval/ how many questions of each
subtype they can still make about advisories that no earlier question is about. The Test v2 builder
ran short on some kinds, so the answer decides what mix Dev-R can have.

Two pools are counted, each for every subtype on its own:
- disjoint: advisories that no v1 question (dev or test) and no Test v2 question is about;
- seen_dev: the same, but v1 dev advisories are allowed (the plan's flagged `seen_dev` slice).

Counting a subtype on its own gives the most the generator can make of it. Dev-R takes many
subtypes at once and the same advisory cannot serve them all, so the final mix will be smaller.
Wording is the v1 template wording, so no hand-written paraphrase is involved.

Needs the local REST cache, the Maven jar and Java for the version questions.

Usage:
    python scripts/count_dev_r_pool.py --out docs/dev-r-pool.md
"""

import argparse
import importlib.util
import json
import random
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

SEED = 20261116  # the Dev-R seed fixed in the plan
SPLIT = "test"  # the engine's name for a scored split
# The subtypes that need evidence from the records, with no hand-written wording. Description
# lookups are left out because their paraphrases are written by hand.
SUBTYPES = [
    ("lookup", "kev_id"), ("lookup", "fixed_id"), ("lookup", "severity_id"), ("lookup", "map_id"),
    ("version", "verdict"), ("version", "set"),
    ("multihop", "a1_nvd_score"), ("multihop", "a2_kev_set"), ("multihop", "a3_kev_pick"),
    ("multihop", "b_intersect"), ("multihop", "c_published"), ("multihop", "c_score"),
    ("disagree", "fixed_differ"), ("disagree", "fixed_agree"), ("disagree", "one_silent"),
    ("disagree", "band_differ"), ("disagree", "band_agree"),
]  # fmt: skip
PLAN_ROUNDS = 400  # long enough that a plan never runs out before the pool does
GIVE_UP = 8  # consecutive failures that mean the pool for a subtype is used up


def refuse(*_args, **_kwargs):
    raise RuntimeError("The pool count makes no network request.")


def load_v2_builder():
    spec = importlib.util.spec_from_file_location(
        "eval_v2_build", ROOT / "eval-v2" / "build_questions.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_v2_build"] = module
    spec.loader.exec_module(module)
    return module


def read_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def used_subjects() -> tuple[set[str], set[str], set[str], set[str]]:
    v1 = read_rows(ROOT / "eval" / "questions.jsonl")
    v2 = read_rows(ROOT / "eval-v2" / "questions.jsonl")
    test = {s for q in v1 if q["split"] != "dev" for s in q["subjects"]}
    dev = {s for q in v1 if q["split"] == "dev" for s in q["subjects"]}
    v2_subjects = {s for q in v2 for s in q["subjects"]}
    texts = {q["question"] for q in v1 + v2}
    return test, dev, v2_subjects, texts


def counter_for(v2, bq, world, banned: set[str], texts: set[str], workdir: Path):
    """One builder per subtype, so each count is that subtype on its own."""

    def make(kind: str, sub: str):
        absence = bq.Absence(workdir / "checks.json")
        builder = v2.Builder(world, absence, [])
        builder.st = v2.State(banned)  # a fresh state, with this pool's advisories kept out
        builder.v1_text = texts
        builder.rng = random.Random(SEED)  # noqa: S311 - choosing questions, not secrets
        cycle = [(e, w) for e in ("PyPI", "Maven", "npm") for w in ("yes", "no")]
        builder.plans = {
            "verdict": {SPLIT: cycle * PLAN_ROUNDS},
            "set": {SPLIT: ["PyPI", "Maven", "npm"] * PLAN_ROUNDS},
        }
        builder.free = False
        dispatch = {
            ("lookup", "fixed_id"): builder.l_fixed_id,
            ("lookup", "severity_id"): builder.l_severity_id,
            ("lookup", "map_id"): builder.l_map_id, ("lookup", "kev_id"): builder.l_kev_id,
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
        return builder, dispatch[(kind, sub)]

    def count(kind: str, sub: str) -> int:
        builder, call = make(kind, sub)
        made = misses = 0
        while misses < GIVE_UP:
            builder.used_free = False
            try:
                item = call(sub, SPLIT)
            except IndexError:  # a plan ran out
                break
            if item is None:
                misses += 1
                continue
            misses = 0
            item.tags.setdefault("form", "v1")
            builder.st.take(item, SPLIT, item.tags["slice"] == "post")
            made += 1
        return made

    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="write the table as Markdown to this path")
    args = parser.parse_args()
    urllib.request.urlopen = refuse  # nothing here may reach the network
    v2 = load_v2_builder()
    bq = sys.modules["build_questions"]
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        # The engine reads paraphrases.json from EVAL when it loads. eval-v2 is only read here,
        # and anything the engine would write goes to the temporary folder instead.
        bq.SEED, bq.EVAL, bq.EVIDENCE = SEED, ROOT / "eval-v2", work / "evidence"
        world = bq.load_world()
        jar_cache = ROOT / "data" / "tools" / "jar_cache.json"
        bq.load_jar_cache(world.jar, jar_cache)  # read only: it is never saved back
        test, dev, v2_subjects, texts = used_subjects()
        pools = {
            "disjoint": test | dev | v2_subjects,
            "seen_dev": test | v2_subjects,
        }
        table: dict[str, dict[str, int]] = {name: {} for name in pools}
        for name, banned in pools.items():
            count = counter_for(v2, bq, world, banned, texts, work)
            for kind, sub in SUBTYPES:
                table[name][f"{kind}/{sub}"] = count(kind, sub)
                print(f"{name:9} {kind}/{sub}: {table[name][f'{kind}/{sub}']}", flush=True)
    advisories = len(world.adv)
    lines = [
        "# Dev-R pool count",
        "",
        "Written by `scripts/count_dev_r_pool.py`, with no retrieval, no model and no network. See "
        "[the plan](evidence-round-plan.md), step 1, item 4.",
        "",
        f"The store holds {advisories} advisories with REST records. Subjects used by earlier "
        f"questions: v1 test {len(test)}, v1 dev {len(dev)}, Test v2 {len(v2_subjects)}.",
        "",
        "Most questions of each subtype the generator can still make on its own, with seed "
        f"{SEED}. The same advisory cannot serve every subtype, so a mix drawn from several will "
        "be smaller.",
        "",
        "| Subtype | disjoint | seen_dev |",
        "|---|---|---|",
        *[
            f"| {key} | {table['disjoint'][key]} | {table['seen_dev'][key]} |"
            for key in table["disjoint"]
        ],
        "",
    ]
    if args.out:
        Path(args.out).write_text("\n".join(lines), encoding="utf-8", newline="\n")
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
