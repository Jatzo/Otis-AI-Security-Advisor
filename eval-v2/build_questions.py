"""Builds Test v2: questions.jsonl, gold.jsonl, evidence/ and review.md, all under eval-v2/.

It reuses the v1 engine in eval/build_questions.py and the gold code in eval/make_gold.py without
changing either (both are frozen under eval-freeze-v1). What is new:

- a new seed, a new mix (110 questions, all of them one split called "v2") and new subjects:
  no advisory that any v1 question was about, unless a kind of question has run out, in which case
  the advisory is reused and the question is flagged `reuses_v1`;
- about half of the answerable questions are worded in forms that the structured row's patterns do
  not match ("form": "free"), so that row stops being a ceiling;
- new description paraphrases, new out-of-scope packages, new invented names, new off-topic questions.

No system exists to be tuned on when this runs. This script imports nothing from the advisor package.

Usage: python eval-v2/build_questions.py
"""

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "eval-v2"
sys.path.insert(0, str(ROOT / "eval"))
import build_questions as bq  # noqa: E402

SEED = 20261102
SPLIT = "test"  # the v1 engine's name for a scored split; renamed "v2" when written
# type, subtype, questions, of which worded in forms the structured row cannot read.
# Scarce kinds first, as in v1.
SLOTS = [
    ("abstain", "withdrawn", 4, 0),
    ("abstain", "out_of_scope", 4, 0),
    ("abstain", "unsupported", 3, 0),
    ("abstain", "fake_ghsa", 3, 0),
    ("abstain", "fake_cve", 3, 0),
    ("abstain", "fake_package", 2, 0),
    ("abstain", "off_topic", 1, 0),
    ("disagree", "fixed_differ", 3, 2),
    ("disagree", "fixed_agree", 2, 1),
    ("disagree", "one_silent", 4, 2),
    ("disagree", "band_differ", 6, 3),
    ("disagree", "band_agree", 5, 3),
    ("multihop", "a2_kev_set", 2, 1),
    ("multihop", "a3_kev_pick", 2, 1),
    ("lookup", "fixed_desc", 3, 0),
    ("lookup", "severity_desc", 3, 0),
    ("lookup", "identify_desc", 7, 0),
    ("lookup", "kev_id", 3, 2),
    ("multihop", "a1_nvd_score", 4, 2),
    ("version", "verdict", 10, 6),
    ("version", "set", 12, 7),
    ("multihop", "b_intersect", 8, 5),
    ("multihop", "c_published", 4, 2),
    ("multihop", "c_score", 4, 2),
    ("lookup", "fixed_id", 4, 1),
    ("lookup", "severity_id", 2, 1),
    ("lookup", "map_id", 2, 0),
]
PAD = 12  # spare plan entries, because a retry takes the next one
VERDICT_PLAN = (
    [("PyPI", "yes"), ("PyPI", "no")] * 2
    + [("Maven", "yes"), ("Maven", "no")] * 2
    + [("npm", "yes"), ("npm", "no")]
    + [("PyPI", "yes"), ("PyPI", "no")] * (PAD // 2)
)  # fmt: skip
SET_PLAN = ["PyPI"] * 6 + ["Maven"] * 4 + ["npm"] * 2 + ["PyPI"] * PAD
OUT_OF_SCOPE = [
    ("PyPI", "scrapy"),
    ("PyPI", "paramiko"),
    ("npm", "mongoose"),
    ("Maven", "org.apache.commons:commons-text"),
    ("Maven", "org.apache.tomcat:tomcat-catalina"),
]
FAKE_PACKAGES = [
    "fastapi-armor", "pydantic-sentinel", "expressjs-guardrail", "lodash-secure-core",
    "spring-shieldkit", "cryptography-vault", "axios-guardian", "jsonwebtoken-plus",
]  # fmt: skip
OFF_TOPIC = [
    "Can you recommend a good recipe for a vegetarian lasagne?",
    "What is the capital city of Australia?",
    "How do I turn a Word document into a PDF on a Mac?",
]

# The first wording of a v1 template maps to as many new wordings as the template has. None of
# them is read by the structured row; a test checks that against the built questions.
FREE = {
    "What is the first patched version of {p} for {i}?": [
        "I run {p}. Which version do I need to move to so that {i} no longer applies to me?",
        "Which version of {p} should I upgrade to in order to be clear of {i}?",
        "{i}: what is the earliest {p} release that has it patched?",
    ],
    "What severity label does GitHub give {i}?": [
        "How serious is {i} according to GitHub's advisory database?",
        "Tell me the severity level GitHub lists for {i}.",
        "At what severity does GitHub list {i}?",
    ],
    "Is {c} on the CISA Known Exploited Vulnerabilities list?": [
        "According to CISA's known exploited list, is {c} being exploited?",
        "Does CISA's catalogue of known exploited vulnerabilities include {c}?",
    ],
    "Is {p} {v} affected by {i}?": [
        "Does {p} {v} fall inside the vulnerable range for {i}?",
        "Is a deployment running {p} {v} exposed to {i}?",
        "{i} and {p} {v}: is that version vulnerable?",
    ],
    "Which advisories affect {p} {v}?": [
        "I am on {p} {v}. Which advisories do I need to look at?",
        "What is the full list of advisory IDs against {p} {v}?",
        "Which GitHub advisories is {p} {v} exposed to?",
    ],
    "What CVSS v3 base score does NVD give the CVE behind {i}?": [
        "Look at the CVE behind {i}: what CVSS v3 base score did NVD assign it?",
        "NVD scored the CVE that {i} covers on CVSS v3. What number did it give?",
    ],
    "Which advisories for {p} name a CVE on the CISA Known Exploited Vulnerabilities list?": [
        "For {p}, which advisories correspond to vulnerabilities that CISA knows are being exploited?",
        "Name the {p} advisories whose CVE appears in CISA's known exploited list.",
    ],
    "Which of {l} name a CVE on the CISA Known Exploited Vulnerabilities list?": [
        "Of these advisories, {l}, which ones relate to a CVE that CISA marks as known exploited?",
        "Which of the following, {l}, appear in CISA's known exploited catalogue through their CVE?",
    ],
    "Which {p} advisories affect version {v} and are rated {l} by GitHub?": [
        "Among the advisories for {p} that cover version {v}, which have GitHub's {l} rating?",
        "For {p} {v}, narrow the applicable advisories down to the ones GitHub classes as {l}.",
    ],
    "Which has the higher GitHub CVSS v3 score: {a} or {b}?": [
        "{a} versus {b}: which carries the higher CVSS v3 score on GitHub?",
        "GitHub gives {a} and {b} CVSS v3 scores. Which one is bigger?",
    ],
    "Which was published first: {a} or {b}?": [
        "Which of {a} and {b} came out earlier?",
        "{a} or {b}: which advisory was published earlier?",
    ],
    "What CVSS v3 base score do GitHub and NVD each give {i}, and do they fall in the same severity band?": [
        "GitHub and NVD both score {i} on CVSS v3. Are the scores in the same severity band, and what are they?",
        "What are the two CVSS v3 scores for {i}, GitHub's and NVD's, and do they land in the same band?",
    ],
    "Do GitHub and NVD agree on the first fixed version for {i}? Give the version each one names.": [
        "GitHub and NVD each name a fixed version for {i}. Do they name the same one, and what are they?",
        "What version fixes {i} according to GitHub, and what does NVD say? Do these match?",
    ],
    "What CVSS v3 score do GitHub and NVD each give {i}?": [
        "Does NVD have a CVSS v3 score for {i} as well as GitHub? Give both.",
        "{i}: what is GitHub's CVSS v3 score, and what is NVD's, if it has one?",
    ],
}  # fmt: skip


def v1_subjects() -> set[str]:
    rows = (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    return {s for row in rows for s in json.loads(row)["subjects"]}


def v1_questions() -> set[str]:
    rows = (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    return {json.loads(row)["question"] for row in rows}


class State(bq.State):
    """Keeps v1's advisories out until a kind of question has run out."""

    def __init__(self, banned: set[str]) -> None:
        super().__init__()
        self.banned = banned
        self.relaxed = False

    def allowed(self, subjects: list[str], split: str) -> bool:
        if not self.relaxed and set(subjects) & self.banned:
            return False
        return super().allowed(subjects, split)


class Builder(bq.Builder):
    def __init__(self, world: bq.World, absence: bq.Absence, out_of_scope: list[dict]) -> None:
        super().__init__(world, absence, out_of_scope)
        self.rng = random.Random(SEED)
        self.v1 = v1_subjects()
        self.v1_text = v1_questions()
        self.st = State(self.v1)
        self.plans = {"verdict": {SPLIT: list(VERDICT_PLAN)}, "set": {SPLIT: list(SET_PLAN)}}
        self.free = False
        self.used_free = False

    def pick_template(self, options: list[str]) -> tuple[int, str]:
        if self.free and options[0] in FREE:
            alternatives = FREE[options[0]]
            assert len(alternatives) == len(options), options[0]
            self.used_free = True
            index = self.rng.randrange(len(alternatives))
            return index, alternatives[index]
        return super().pick_template(options)

    def make_item(self, split: str, item: bq.Item) -> bq.Item | None:
        if item.question in self.v1_text:
            return None
        made = super().make_item(split, item)
        if made is not None:
            made.tags["form"] = "free" if self.used_free or made.subtype.endswith("_desc") else "v1"
            if self.used_free:
                made.template = "F-" + made.template
        return made

    def build(self) -> None:
        dispatch = {
            ("lookup", "fixed_id"): self.l_fixed_id, ("lookup", "severity_id"): self.l_severity_id,
            ("lookup", "map_id"): self.l_map_id, ("lookup", "kev_id"): self.l_kev_id,
            ("lookup", "identify_desc"): self.l_desc, ("lookup", "fixed_desc"): self.l_desc,
            ("lookup", "severity_desc"): self.l_desc,
            ("version", "verdict"): self.v_verdict, ("version", "set"): self.v_set,
            ("multihop", "a1_nvd_score"): self.m_nvd_score, ("multihop", "a2_kev_set"): self.m_kev_set,
            ("multihop", "a3_kev_pick"): self.m_kev_pick, ("multihop", "b_intersect"): self.m_intersect,
            ("multihop", "c_published"): self.m_pair, ("multihop", "c_score"): self.m_pair,
            ("abstain", "withdrawn"): self.a_withdrawn, ("abstain", "out_of_scope"): self.a_scope,
            ("abstain", "unsupported"): self.a_unsupported, ("abstain", "fake_ghsa"): self.a_fake,
            ("abstain", "fake_cve"): self.a_fake, ("abstain", "fake_package"): self.a_fake,
            ("abstain", "off_topic"): self.a_off_topic,
            ("disagree", "band_differ"): self.d_band, ("disagree", "band_agree"): self.d_band,
            ("disagree", "fixed_differ"): self.d_fixed, ("disagree", "fixed_agree"): self.d_fixed,
            ("disagree", "one_silent"): self.d_silent,
        }  # fmt: skip
        for kind, sub, count, n_free in SLOTS:
            for k in range(count):
                self.free = k < n_free
                item = None
                for relaxed in (False, True):  # fresh advisories first, v1's only if none is left
                    self.st.relaxed = relaxed
                    self.used_free = False
                    item = dispatch[(kind, sub)](sub, SPLIT)
                    if item is not None:
                        break
                self.st.relaxed = False
                if item is None:
                    self.short[(kind, sub, SPLIT)] += 1
                    continue
                item.tags.setdefault("form", "v1")
                item.tags["reuses_v1"] = bool(set(item.subjects) & self.v1)
                self.st.take(item, SPLIT, item.tags["slice"] == "post")


def finish(builder: Builder, written: dict) -> None:
    """Gives the ids a v2 prefix, the split the name v2, and each question its form."""
    tags = {i.question: i.tags for _, i in builder.st.items}
    rename = lambda qid: f"v2-{qid}"  # noqa: E731
    questions, golds = written["questions"], written["gold"]
    for q in questions:
        q["id"], q["split"] = rename(q["id"]), "v2"
        q["form"], q["reuses_v1"] = tags[q["question"]]["form"], tags[q["question"]]["reuses_v1"]
    for gd in golds:
        gd["id"] = rename(gd["id"])
    lines = lambda rows: "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)  # noqa: E731
    (V2 / "questions.jsonl").write_text(lines(questions), encoding="utf-8", newline="\n")
    (V2 / "gold.jsonl").write_text(lines(golds), encoding="utf-8", newline="\n")
    review = V2 / "review.md"
    text = review.read_text(encoding="utf-8")
    text = re.sub(r"\| (lk|vr|mh|ab|dg)-(\d{3}) \| test \|", r"| v2-\1-\2 | v2 |", text)
    text = text.replace("Review table for the evaluation set", "Review table for Test v2")
    text = text.replace("eval/build_questions.py", "eval-v2/build_questions.py")
    form = Counter(q["form"] for q in questions)
    answerable = [q for q in questions if q["answers_with"] != "abstain"]
    reused = [q["id"] for q in questions if q["reuses_v1"]]
    extra = [
        "",
        f"Wording: {form['free']} of {len(questions)} questions are free-form (the structured row's "
        f"patterns do not read them, {sum(q['form'] == 'free' for q in answerable)} of them answerable); "
        f"{form['v1']} use v1 wordings.",
        f"Reuses a v1 advisory because its kind ran out: {len(reused)} ({', '.join(reused) or 'none'}).",
        "",
    ]
    marker = "## Rows"
    review.write_text(
        text.replace(marker, "\n".join(extra) + marker, 1), encoding="utf-8", newline="\n"
    )


def main() -> None:
    # The v1 engine reads these module values when it runs, so they are set before it does.
    bq.SEED, bq.EVAL, bq.EVIDENCE = SEED, V2, V2 / "evidence"
    bq.OUT_OF_SCOPE, bq.FAKE_PACKAGES, bq.OFF_TOPIC = OUT_OF_SCOPE, FAKE_PACKAGES, OFF_TOPIC
    world = bq.load_world()
    jar_cache = ROOT / "data" / "tools" / "jar_cache.json"
    bq.load_jar_cache(world.jar, jar_cache)
    absence = bq.Absence(bq.EVIDENCE / "checks.json")
    out_of_scope = bq.fetch_out_of_scope(bq.EVIDENCE / "out_of_scope_cache.json")
    builder = Builder(world, absence, out_of_scope)
    builder.build()
    bq.save_jar_cache(world.jar, jar_cache)
    absence.save()
    written = bq.write_outputs(builder)
    bq.write_review(written["questions"], written["gold"], builder)
    finish(builder, written)
    summary = Counter(q["type"] for q in written["questions"])
    print(json.dumps({  # noqa: T201
        "built": dict(sorted(summary.items())),
        "free_form": sum(q["form"] == "free" for q in written["questions"]),
        "reuses_v1": sum(q["reuses_v1"] for q in written["questions"]),
        "shortfalls": {"/".join(k): n for k, n in builder.short.items()},
        "dropped_by_reason": dict(builder.drops),
    }, indent=1))  # fmt: skip


if __name__ == "__main__":
    main()
