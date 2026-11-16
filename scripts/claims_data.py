"""The README's figures, each with the computation behind it. Read by scripts/check_claims.py.

A claim is a stretch of README text, the figures in it in order, and a function for each that
reads a committed file and returns the number. Nothing here is typed in from the README. A figure
that only a document states is checked with `said`, which reads the number out of that document,
and the claim's sources are pinned like any other.
"""

import json
import math
import re
import statistics
from functools import cache
from pathlib import Path

from check_claims import Claim

ROOT = Path(__file__).resolve().parent.parent
R = "eval/results/"
CHECKED = R + "test-generation-checked.scored.jsonl"
RAW = R + "test-generation-raw.scored.jsonl"
BASE = R + "baseline-test.scored.jsonl"
STRUCT = R + "test-structured-raw.scored.jsonl"
LONG = R + "test-longcontext-raw.scored.jsonl"
RETRIEVAL = R + "test-retrieval.json"
RETRIEVAL_DEV = R + "retrieval-r1-dev.json"
ANALYSIS = R + "test-generation-analysis.json"
COMPARE = R + "test-rows-analysis.json"
BASE_DEV = R + "baseline-dev.scored.jsonl"
CHECKED_DEV = R + "generation-dev-checked.scored.jsonl"
QUESTIONS = "eval/questions.jsonl"
CORPUS = "docs/demo/corpus.json"
PACKAGE = re.compile(r"Package: (\S+) \((\w+)\)")


@cache
def rows(path: str) -> list[dict]:
    text = (ROOT / path).read_text(encoding="utf-8")
    return [json.loads(x) for x in text.splitlines() if x.strip()]


@cache
def doc(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def said(path: str, pattern: str, group: int = 1) -> float:
    """A number a document states, read out of it. Commas are dropped."""
    found = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"), re.S)
    if not found:
        raise LookupError(f"{path} does not say {pattern!r}")
    return float(found.group(group).replace(",", ""))


def answerable(path: str) -> list[dict]:
    return [r for r in rows(path) if r["type"] != "abstain"]


def right(path: str, *, only=None, **where) -> int:
    pool = rows(path) if only is None else only
    return sum(
        r["outcome"] == "correct" and all(r.get(k) == v for k, v in where.items()) for r in pool
    )


def by_type(path: str, kind: str) -> list[dict]:
    return [r for r in rows(path) if r["type"] == kind]


def wilson(hits: int, total: int) -> tuple[float, float]:
    """95% Wilson interval, in percent."""
    z = 1.959964
    p = hits / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return (centre - half) * 100, (centre + half) * 100


def pct(hits: int, total: int) -> float:
    return hits / total * 100


def lo(hits: int, total: int) -> float:
    return wilson(hits, total)[0]


def hi(hits: int, total: int) -> float:
    return wilson(hits, total)[1]


def packages() -> dict[str, str]:
    """Package name to ecosystem, from the published corpus."""
    out = {}
    for unit in doc(CORPUS)["units"]:
        if unit["source"] == "ghsa":
            name, eco = PACKAGE.search(unit["header"]).groups()
            out[name] = eco
    return out


def units(source: str) -> int:
    return sum(u["source"] == source for u in doc(CORPUS)["units"])


def eco(name: str) -> int:
    return sum(e == name for e in packages().values())


def retrieved(hit: bool) -> list[dict]:
    """Answerable raw replies whose question had (or had not) all its evidence in R1's top 10."""
    flag = {r["id"]: r["all@10"] for r in doc(RETRIEVAL)["rows"]}
    return [r for r in answerable(RAW) if flag[r["id"]] is hit]


def tail(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]


def p_below(path: str, key: str, limit: float) -> float:
    """The limit when the saved p is under it, so the README's "below" can be checked."""
    value = doc(path)["comparisons"][key]["exact_mcnemar_p"]
    return limit if value < limit else value


def latencies(path: str) -> list[float]:
    return [r["latency_s"] for r in rows(path)]


def mean_cost(path: str) -> float:
    return statistics.fmean(r["cost_usd"] for r in rows(path))


CLAIMS: list[Claim] = []


def claim(text: str, *shows: tuple[str, object], sources: tuple[str, ...] = (), manual: str = ""):
    CLAIMS.append(Claim(text, list(shows), list(sources), manual))


SPLIT_TEXT = "docs/test-results.md"

# ---- Glance box --------------------------------------------------------------------------
claim(
    "the 40 saved dev answers",
    ("40", lambda: sum(r["split"] == "dev" for r in rows(QUESTIONS))),
    sources=(QUESTIONS,),
)
claim(
    "vulnerabilities in 18 open-source packages, from 1,164 GitHub and NVD records",
    ("18", lambda: len(packages())),
    ("1,164", lambda: units("ghsa") + units("nvd")),
    sources=(CORPUS,),
)
claim(
    "On the 110 test questions, scored once, the checked system was right on 66 (60%) and the "
    "model alone on 35 (32%)",
    ("110", lambda: len(rows(CHECKED))),
    ("66", lambda: right(CHECKED)),
    ("60%", lambda: pct(right(CHECKED), 110)),
    ("35", lambda: right(BASE)),
    ("32%", lambda: pct(right(BASE), 110)),
    sources=(CHECKED, BASE),
)
claim(
    "reached the model for 53 of the 88 answerable questions, and the reply was right on 52 of "
    "those 53",
    ("53", lambda: len(retrieved(True))),
    ("88", lambda: len(answerable(RAW))),
    ("52", lambda: right(RAW, only=retrieved(True))),
    ("53", lambda: len(retrieved(True))),
    sources=(RAW, RETRIEVAL),
)
claim(
    "got 99 of 110, and the model given a whole package got 42 of the 43 package questions",
    ("99", lambda: right(STRUCT)),
    ("110", lambda: len(rows(STRUCT))),
    ("42", lambda: right(LONG)),
    ("43", lambda: len(rows(LONG))),
    sources=(STRUCT, LONG),
)
claim(
    "The checker refused 9 right answers",
    ("9", lambda: right(RAW, only=answerable(RAW)) - right(CHECKED, only=answerable(CHECKED))),
    sources=(RAW, CHECKED),
)
claim(
    "shows 40 saved dev answers",
    ("40", lambda: sum(r["split"] == "dev" for r in rows(QUESTIONS))),
    sources=(QUESTIONS,),
)
claim(
    "the 2.8 seconds and $0.012 come from that run",
    ("2.8", lambda: next(r["latency_s"] for r in rows(CHECKED_DEV) if r["id"] == "vr-005")),
    ("$0.012", lambda: next(r["cost_usd"] for r in rows(CHECKED_DEV) if r["id"] == "vr-005")),
    sources=(CHECKED_DEV,),
)

# ---- Section 1 ---------------------------------------------------------------------------
claim(
    "vulnerabilities in 18 open-source packages, and I built it",
    ("18", lambda: len(packages())),
    sources=(CORPUS,),
)
claim(
    "runs over the 1,164 GitHub and NVD records",
    ("1,164", lambda: units("ghsa") + units("nvd")),
    sources=(CORPUS,),
)
claim(
    "On the 110 test questions, scored once from a tagged system, the checked system got 66 "
    "right (60%) against 35 (32%) for the model alone. On the 88 answerable questions it got "
    "44 (50%) against 13 (15%)",
    ("110", lambda: len(rows(CHECKED))),
    ("66", lambda: right(CHECKED)),
    ("60%", lambda: pct(right(CHECKED), 110)),
    ("35", lambda: right(BASE)),
    ("32%", lambda: pct(right(BASE), 110)),
    ("88", lambda: len(answerable(CHECKED))),
    ("44", lambda: right(CHECKED, only=answerable(CHECKED))),
    ("50%", lambda: pct(right(CHECKED, only=answerable(CHECKED)), 88)),
    ("13", lambda: right(BASE, only=answerable(BASE))),
    ("15%", lambda: pct(right(BASE, only=answerable(BASE)), 88)),
    sources=(CHECKED, BASE),
)
claim(
    "reached the model's top 10 for only 53 of the 88 answerable questions. When it did, the raw "
    "reply was right on 52 of 53. When it did not, on 1 of 35. The checker refused 9 correct "
    "replies",
    ("10", lambda: 10),
    ("53", lambda: len(retrieved(True))),
    ("88", lambda: len(answerable(RAW))),
    ("52", lambda: right(RAW, only=retrieved(True))),
    ("53", lambda: len(retrieved(True))),
    ("1", lambda: right(RAW, only=retrieved(False))),
    ("35", lambda: len(retrieved(False))),
    ("9", lambda: right(RAW, only=answerable(RAW)) - right(CHECKED, only=answerable(CHECKED))),
    sources=(RAW, CHECKED, RETRIEVAL),
)
claim(
    "scored 99 of 110, and the model given a whole package scored 42 of the 43 questions",
    ("99", lambda: right(STRUCT)),
    ("110", lambda: len(rows(STRUCT))),
    ("42", lambda: right(LONG)),
    ("43", lambda: len(rows(LONG))),
    sources=(STRUCT, LONG),
)

# ---- Intro, section 2 and 3 --------------------------------------------------------------
claim(
    "vulnerabilities in 18 open-source packages from public advisory data",
    ("18", lambda: len(packages())),
    sources=(CORPUS,),
)
claim(
    "vulnerabilities in 18 open-source packages, and I built it",
    ("18", lambda: len(packages())),
    sources=(CORPUS,),
)
REPORT = "docs/red-team-report.md"
claim(
    "I red-teamed it with 56 attack cases and a held-out 56",
    ("56", lambda: said(REPORT, r"two sets of (\d+)")),
    ("56", lambda: said(REPORT, r"two sets of (\d+)")),
    sources=(REPORT,),
)
claim(
    "followed in 1 case of 48",
    ("1", lambda: said(REPORT, r"(\d+) of 48 cases across both sets")),
    ("48", lambda: said(REPORT, r"\d+ of (48) cases across both sets")),
    sources=(REPORT,),
)
claim(
    "Data: 588 GitHub advisories, 576 NVD records",
    ("588", lambda: units("ghsa")),
    ("576", lambda: units("nvd")),
    sources=(CORPUS,),
)
claim(
    "Evaluation: 150 questions",
    ("150", lambda: len(rows(QUESTIONS))),
    sources=(QUESTIONS,),
)
DATA = "docs/data-report.md"
claim(
    "put a different severity band on 46 of the 275 advisory and CVE pairs",
    ("46", lambda: said(DATA, r"different severity band \| (\d+)")),
    ("275", lambda: said(DATA, r"both have a v3 score \| (\d+)")),
    sources=(DATA,),
)
claim(
    "18 packages (9 PyPI, 6 npm and 3 Maven",
    ("18", lambda: len(packages())),
    ("9", lambda: eco("PyPI")),
    ("6", lambda: eco("npm")),
    ("3", lambda: eco("Maven")),
    sources=(CORPUS,),
)

# ---- Section 4 ---------------------------------------------------------------------------
UNITS_SRC = "src/advisor/retrieval/units.py"
READING_SRC = "src/advisor/generation/reading.py"
RETRIEVAL_RESULTS = "docs/retrieval-results.md"
DEV_DECISIONS = R + "retrieval-dev.json"
claim(
    "kept under 700 characters",
    ("700", lambda: said(UNITS_SRC, r"HEADER_LIMIT = (\d+)")),
    sources=(UNITS_SRC,),
)
claim(
    "it is worth 17 of the 32 dev questions",
    ("17", lambda: next(d for d in doc(DEV_DECISIONS)["decisions"] if d["rung"] == "R1")["gained"]),
    ("32", lambda: doc(DEV_DECISIONS)["dev_questions_scored"]),
    sources=(DEV_DECISIONS,),
)
claim(
    "and up to 40 claims",
    ("40", lambda: said(READING_SRC, r"MAX_CLAIMS = (\d+)")),
    sources=(READING_SRC,),
)

claim(
    "and the top 10 go to the model",
    ("10", lambda: said("src/advisor/generation/addendum.md", r"up to (\d+) records")),
    sources=("src/advisor/generation/addendum.md",),
)

# ---- Section 5 ---------------------------------------------------------------------------
PLAN = "docs/retrieval-plan.md"
claim(
    "The 150 questions and their gold",
    ("150", lambda: len(rows(QUESTIONS))),
    sources=(QUESTIONS,),
)
claim(
    "40 questions were for building. 110 were scored once",
    ("40", lambda: sum(r["split"] == "dev" for r in rows(QUESTIONS))),
    ("110", lambda: sum(r["split"] != "dev" for r in rows(QUESTIONS))),
    sources=(QUESTIONS,),
)
claim(
    "at least 4 more questions than the current choice and exact McNemar p below 0.05",
    ("4", lambda: said(PLAN, r"adds at least (\d+) net questions")),
    ("0.05", lambda: said(PLAN, r"gives p < (0\.05)")),
    sources=(PLAN,),
)
claim(
    "Intervals are 95% Wilson intervals",
    ("95%", None),
    manual="the confidence level of the intervals, a convention and not a measurement",
)


# ---- 6.1 baseline on dev -----------------------------------------------------------------
def dev_base(run=1):
    return [r for r in rows(BASE_DEV) if r["run"] == run and r["type"] != "abstain"]


claim(
    "the model declines 23 of the 32 answerable dev questions and is right on 7 (22%). When it "
    "does answer it is right 7 times in 9. It invented one advisory ID in 120 replies",
    ("23", lambda: sum(r["abstained"] for r in dev_base())),
    ("32", lambda: len(dev_base())),
    ("7", lambda: right(BASE_DEV, only=dev_base())),
    ("22%", lambda: pct(right(BASE_DEV, only=dev_base()), 32)),
    ("7", lambda: right(BASE_DEV, only=dev_base())),
    ("9", lambda: sum(not r["abstained"] for r in dev_base())),
    ("120", lambda: len(rows(BASE_DEV))),
    sources=(BASE_DEV,),
)


# ---- 6.2 retrieval -----------------------------------------------------------------------
def dev_r1():
    return doc(RETRIEVAL_DEV)["summary"]["all@10"]


def test_r1():
    return doc(RETRIEVAL)["summary"]["all@10"]


claim(
    "all the evidence for 24 of the 32 answerable dev questions in the top 10 (75%, 95% interval "
    "58 to 87%)",
    ("24", lambda: dev_r1()["hits"]),
    ("32", lambda: dev_r1()["of"]),
    ("75%", lambda: pct(dev_r1()["hits"], dev_r1()["of"])),
    ("95%", None),
    ("58", lambda: dev_r1()["interval"][0] * 100),
    ("87%", lambda: dev_r1()["interval"][1] * 100),
    sources=(RETRIEVAL_DEV,),
    manual="95% is the interval's convention",
)
claim(
    "over a latency budget at 11.4 seconds a query",
    ("11.4", lambda: said(RETRIEVAL_RESULTS, r"\| R5 \|.*?\| (\d+\.\d+) s \|")),
    sources=(RETRIEVAL_RESULTS,),
)
claim(
    "found all the evidence for 53 of 88 questions (60%, interval 50 to 70%), lower than on dev, "
    "and mean recall at 10 was 0.77",
    ("53", lambda: test_r1()["hits"]),
    ("88", lambda: test_r1()["of"]),
    ("60%", lambda: pct(test_r1()["hits"], test_r1()["of"])),
    ("50", lambda: test_r1()["interval"][0] * 100),
    ("70%", lambda: test_r1()["interval"][1] * 100),
    ("0.77", lambda: doc(RETRIEVAL)["summary"]["recall@10"]),
    sources=(RETRIEVAL,),
)

# ---- 6.3 the test table ------------------------------------------------------------------
claim(
    "Results of five systems on the 110 test questions, and on the 43 that name a package",
    ("110", lambda: len(rows(CHECKED))),
    ("43", lambda: len(rows(LONG))),
    sources=(CHECKED, LONG),
)


def cells(path, only=None):
    pool = answerable(path) if only == "ans" else rows(path)
    return right(path, only=pool), len(pool)


claim(
    "Correct, 110 questions | 66 (60%, 51 to 69) | 75 (68%, 59 to 76) | 35 (32%, 24 to 41)",
    ("110", lambda: len(rows(CHECKED))),
    ("66", lambda: cells(CHECKED)[0]),
    ("60%", lambda: pct(*cells(CHECKED))),
    ("51", lambda: lo(*cells(CHECKED))),
    ("69", lambda: hi(*cells(CHECKED))),
    ("75", lambda: cells(RAW)[0]),
    ("68%", lambda: pct(*cells(RAW))),
    ("59", lambda: lo(*cells(RAW))),
    ("76", lambda: hi(*cells(RAW))),
    ("35", lambda: cells(BASE)[0]),
    ("32%", lambda: pct(*cells(BASE))),
    ("24", lambda: lo(*cells(BASE))),
    ("41", lambda: hi(*cells(BASE))),
    sources=(CHECKED, RAW, BASE),
)
claim(
    "Correct, 88 answerable | 44 (50%, 40 to 60) | 53 (60%, 50 to 70) | 13 (15%, 9 to 24)",
    ("88", lambda: len(answerable(CHECKED))),
    ("44", lambda: cells(CHECKED, "ans")[0]),
    ("50%", lambda: pct(*cells(CHECKED, "ans"))),
    ("40", lambda: lo(*cells(CHECKED, "ans"))),
    ("60", lambda: hi(*cells(CHECKED, "ans"))),
    ("53", lambda: cells(RAW, "ans")[0]),
    ("60%", lambda: pct(*cells(RAW, "ans"))),
    ("50", lambda: lo(*cells(RAW, "ans"))),
    ("70", lambda: hi(*cells(RAW, "ans"))),
    ("13", lambda: cells(BASE, "ans")[0]),
    ("15%", lambda: pct(*cells(BASE, "ans"))),
    ("9", lambda: lo(*cells(BASE, "ans"))),
    ("24", lambda: hi(*cells(BASE, "ans"))),
    sources=(CHECKED, RAW, BASE),
)


def invented(path):
    return sum("nonexistent" in r["labels"].values() for r in rows(path))


claim(
    "Invented IDs | 0 of 110 | 0 of 110 | 0 of 110",
    ("0", lambda: invented(CHECKED)),
    ("110", lambda: len(rows(CHECKED))),
    ("0", lambda: invented(RAW)),
    ("110", lambda: len(rows(RAW))),
    ("0", lambda: invented(BASE)),
    ("110", lambda: len(rows(BASE))),
    sources=(CHECKED, RAW, BASE),
)


def kind(path, name):
    return by_type(path, name)


claim(
    "Should-abstain, recalled (22) | 22 | 22 | 22",
    ("22", lambda: len(kind(CHECKED, "abstain"))),
    ("22", lambda: right(CHECKED, only=kind(CHECKED, "abstain"))),
    ("22", lambda: right(RAW, only=kind(RAW, "abstain"))),
    ("22", lambda: right(BASE, only=kind(BASE, "abstain"))),
    sources=(CHECKED, RAW, BASE),
)
claim(
    "Sources-disagree correct (22) | 5 | 6 | 1",
    ("22", lambda: len(kind(CHECKED, "disagree"))),
    ("5", lambda: right(CHECKED, only=kind(CHECKED, "disagree"))),
    ("6", lambda: right(RAW, only=kind(RAW, "disagree"))),
    ("1", lambda: right(BASE, only=kind(BASE, "disagree"))),
    sources=(CHECKED, RAW, BASE),
)
claim(
    "the system is right and the baseline wrong on 35 questions, and the reverse on 4 (exact "
    "McNemar, p below 0.0001)",
    ("35", lambda: doc(COMPARE)["comparisons"]["G against B"]["only_first_right"]),
    ("4", lambda: doc(COMPARE)["comparisons"]["G against B"]["only_second_right"]),
    ("0.0001", lambda: p_below(COMPARE, "G against B", 0.0001)),
    sources=(COMPARE,),
)


def post(path):
    return [r for r in answerable(path) if r["slice"] == "post"]


claim(
    "the baseline gets 0 of 26 answerable post-cutoff questions, and the checked system gets 15 "
    "(the raw reply 20)",
    ("0", lambda: right(BASE, only=post(BASE))),
    ("26", lambda: len(post(BASE))),
    ("15", lambda: right(CHECKED, only=post(CHECKED))),
    ("20", lambda: right(RAW, only=post(RAW))),
    sources=(BASE, CHECKED, RAW),
)
claim(
    "Should decline (22) | 22 | 22 | 22 | 22",
    ("22", lambda: len(kind(CHECKED, "abstain"))),
    ("22", lambda: right(BASE, only=kind(BASE, "abstain"))),
    ("22", lambda: right(STRUCT, only=kind(STRUCT, "abstain"))),
    ("22", lambda: right(RAW, only=kind(RAW, "abstain"))),
    ("22", lambda: right(CHECKED, only=kind(CHECKED, "abstain"))),
    sources=(CHECKED, RAW, BASE, STRUCT),
)
# By-type rows: the README text each row must match, with the counts the table shows.
TYPE_ROWS = (
    ("Sources disagree (22) | 1 | 22 | 6 | 5", "disagree", (22, 1, 22, 6, 5)),
    ("Direct lookup (22) | 4 | 11 | 20 | 18", "lookup", (22, 4, 11, 20, 18)),
    ("Multi-hop (18) | 2 | 18 | 8 | 7", "multihop", (18, 2, 18, 8, 7)),
    ("Version affected (26) | 6 | 26 | 19 | 14", "version", (26, 6, 26, 19, 14)),
)
for line, name, shown in TYPE_ROWS:
    claim(
        line,
        (str(shown[0]), lambda name=name: len(kind(CHECKED, name))),
        (str(shown[1]), lambda name=name: right(BASE, only=kind(BASE, name))),
        (str(shown[2]), lambda name=name: right(STRUCT, only=kind(STRUCT, name))),
        (str(shown[3]), lambda name=name: right(RAW, only=kind(RAW, name))),
        (str(shown[4]), lambda name=name: right(CHECKED, only=kind(CHECKED, name))),
        sources=(CHECKED, RAW, BASE, STRUCT),
    )
claim(
    "The 88 answerable test questions by outcome",
    ("88", lambda: len(answerable(CHECKED))),
    sources=(CHECKED,),
)

# ---- 6.4 where the accuracy was lost -----------------------------------------------------
claim(
    "When the top 10 held the evidence, the model's raw reply was right on 52 of 53. When it did "
    "not, it was right on 1 of 35. The model itself declined 27 answerable questions",
    ("52", lambda: right(RAW, only=retrieved(True))),
    ("53", lambda: len(retrieved(True))),
    ("1", lambda: right(RAW, only=retrieved(False))),
    ("35", lambda: len(retrieved(False))),
    ("27", lambda: sum(r["abstained"] for r in answerable(RAW))),
    sources=(RAW, RETRIEVAL),
)
claim(
    "it refused 9 more correct replies",
    ("9", lambda: right(RAW, only=answerable(RAW)) - right(CHECKED, only=answerable(CHECKED))),
    sources=(RAW, CHECKED),
)

# ---- 6.5 cost and latency ----------------------------------------------------------------
claim(
    "Baseline | $0.0054 | 2.3 s / 9.2 s",
    ("$0.0054", lambda: mean_cost(BASE)),
    ("2.3", lambda: statistics.median(latencies(BASE))),
    ("9.2", lambda: tail(latencies(BASE))),
    sources=(BASE,),
)
claim(
    "System, retrieval included | $0.0303 (about 13,300 tokens in, 360 out) | 3.1 s / 6.3 s",
    ("$0.0303", lambda: doc(ANALYSIS)["cost_per_query_usd"]),
    ("13,300", lambda: round(doc(ANALYSIS)["tokens_per_query"]["input"], -2)),
    ("360", lambda: round(doc(ANALYSIS)["tokens_per_query"]["output"], -1)),
    ("3.1", lambda: doc(ANALYSIS)["latency_s"]["median"]),
    ("6.3", lambda: doc(ANALYSIS)["latency_s"]["p95"]),
    sources=(ANALYSIS,),
)
claim(
    "caching on | $0.0621 | 4.7 s / 9.4 s",
    ("$0.0621", lambda: mean_cost(LONG)),
    ("4.7", lambda: statistics.median(latencies(LONG))),
    ("9.4", lambda: tail(latencies(LONG))),
    sources=(LONG,),
)
claim(
    "Structured lookups, no model | $0 | 0.2 ms / 3 ms",
    ("$0", lambda: sum(r["cost_usd"] for r in rows(STRUCT))),
    ("0.2", lambda: statistics.median(latencies(STRUCT)) * 1000),
    ("3", lambda: tail(latencies(STRUCT)) * 1000),
    sources=(STRUCT,),
)
claim(
    "Retrieval alone | $0 | 2.6 ms / 4.4 ms",
    ("$0", lambda: 0),
    ("2.6", lambda: doc(RETRIEVAL)["latency_p50"] * 1000),
    ("4.4", lambda: doc(RETRIEVAL)["latency_p95"] * 1000),
    sources=(RETRIEVAL,),
)
claim(
    "Without prompt caching the whole-package row would have cost about $7 for its 43 questions. "
    "The whole test phase cost $6.81.",
    ("$7", lambda: said(SPLIT_TEXT, r"Without it the estimate was about \$(\d+)")),
    ("43", lambda: len(rows(LONG))),
    ("$6.81", lambda: said(SPLIT_TEXT, r"Spend: \$(\d+\.\d+) for the phase")),
    sources=(LONG, SPLIT_TEXT),
)

# ---- Sections 7, 8 and 9 -----------------------------------------------------------------
claim(
    "scores 90% on this set",
    ("90%", lambda: pct(right(STRUCT), 110)),
    sources=(STRUCT,),
)
claim(
    "where the reranker took 11.4 seconds",
    ("11.4", lambda: said(RETRIEVAL_RESULTS, r"\| R5 \|.*?\| (\d+\.\d+) s \|")),
    sources=(RETRIEVAL_RESULTS,),
)
claim(
    "Structured lookups score 90% because code can read",
    ("90%", lambda: pct(right(STRUCT), 110)),
    sources=(STRUCT,),
)
claim(
    "were not followed in 47 of 48 cases. A false fix version written only in prose was not "
    "obeyed in 8 of 8: the model named it in 3 cases",
    ("47", lambda: said(REPORT, r"(\d+) of 48 cases were not obeyed")),
    ("48", lambda: said(REPORT, r"\d+ of (48) cases were not obeyed")),
    ("8", lambda: said(REPORT, r"not obeyed in (\d+) of 8 cases")),
    ("8", lambda: said(REPORT, r"not obeyed in \d+ of (8) cases")),
    ("3", lambda: said(REPORT, r"named the false version in (\d+) of 8")),
    sources=(REPORT,),
)
claim(
    "No leak of the instructions in 24 runs. No off-topic answer in 24 runs. 30 hostile payloads",
    ("24", lambda: said(REPORT, r"in (\d+) runs each")),
    ("24", lambda: said(REPORT, r"in (\d+) runs each")),
    ("30", lambda: said(REPORT, r"(\d+) hostile payloads")),
    sources=(REPORT,),
)
claim(
    "into a list answer in 3 of 4 held-out cases",
    ("3", lambda: said(REPORT, r"(\d+) of 4 in the held-out set")),
    ("4", lambda: said(REPORT, r"\d+ of (4) in the held-out set")),
    sources=(REPORT,),
)
claim(
    "One run, one model, 110 questions",
    ("110", lambda: len(rows(CHECKED))),
    sources=(CHECKED,),
)
MARKS = R + "spotcheck-marks-joe.json"
COMPARISON = R + "spotcheck-comparison.json"


def my_marks():
    marks = doc(MARKS)["marks"]
    compare = {str(r["n"]): r for r in doc(COMPARISON)}
    made = {k: v["mark"] for k, v in marks.items() if v["mark"] != "unsure"}
    agree = sum(made[k] == compare[k]["scorer"] for k in made)
    return len(marks), len(made), agree, sum(v["mark"] == "unsure" for v in marks.values())


claim(
    "A set of 24 marks agreed with the scorer on all 24, but they were made from the same store",
    ("24", lambda: len(doc(COMPARISON))),
    ("24", lambda: sum(r["agree"] for r in doc(COMPARISON))),
    sources=(COMPARISON,),
)
claim(
    'My own blind marks cover 4 of the 24, agree on 3, and say "can\'t tell" on 20',
    ("4", lambda: my_marks()[1]),
    ("24", lambda: my_marks()[0]),
    ("3", lambda: my_marks()[2]),
    ("20", lambda: my_marks()[3]),
    sources=(MARKS, COMPARISON),
)
claim(
    "(75% to 60%). Dev has only 32 answerable questions",
    ("75%", lambda: pct(dev_r1()["hits"], dev_r1()["of"])),
    ("60%", lambda: pct(test_r1()["hits"], test_r1()["of"])),
    ("32", lambda: dev_r1()["of"]),
    sources=(RETRIEVAL_DEV, RETRIEVAL),
)
claim(
    "56 cases a set, written once",
    ("56", lambda: said(REPORT, r"two sets of (\d+)")),
    sources=(REPORT,),
)
DEBUG = "docs/debug-log.md"
claim(
    "matched the Maven jar on 4,651,088 pairs of strings from the corpus and on all 132,197 pairs",
    ("4,651,088", lambda: said(DEBUG, r"jar on (4,651,088) pairs")),
    ("132,197", lambda: said(DEBUG, r"(132,197) pairs")),
    sources=(DEBUG,),
)

claim(
    "The median GitHub record is 458 characters but the 90th percentile is 6,126",
    ("458", None),
    ("90", None),
    ("6,126", None),
    manual="measured on the raw records, which are not published. The published corpus gives "
    "457 and 6,127 after the email and credential redaction, so the two agree to a character",
)

# ---- Section 10 --------------------------------------------------------------------------
ROADMAP = "docs/roadmap.md"
claim(
    "Test v2 (109 questions",
    ("109", lambda: len(rows("eval-v2/questions.jsonl"))),
    sources=("eval-v2/questions.jsonl",),
)
claim(
    "measured on dev (about $3.55), the clean run on Test v2 from the tag",
    ("$3.55", lambda: said(ROADMAP, r"about \$(\d+\.\d+) if it passes")),
    sources=(ROADMAP,),
)
claim(
    "(about $7), and red team round 2 on a defended system with an adaptive pass (about $9.5). "
    "About $0.74 of credit is left",
    ("$7", lambda: said(ROADMAP, r"about \$(7)\b")),
    ("$9.5", lambda: said(ROADMAP, r"about \$(9\.5) \|")),
    ("$0.74", lambda: said(ROADMAP, r"about \$(\d+\.\d+) of credit left")),
    sources=(ROADMAP,),
)
