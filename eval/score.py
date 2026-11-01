"""The deterministic scorer for the evaluation. No model judges an answer.

It reads the questions, the gold and a results file (one line per reply, written by the
runner) and applies eval/rules.md, sections 5 and 6, as written. It does not import the
advisor package, so a fault in the system cannot change how the system is marked.

Usage:
    python eval/score.py snapshot
    python eval/score.py score --results eval/results/baseline-dev.jsonl --split dev [--online]
    python eval/score.py compare eval/results/a.scored.jsonl eval/results/b.scored.jsonl
"""

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path

EVAL = Path(__file__).resolve().parent
SNAPSHOT_FILE = EVAL / "id_snapshot.json"
LOOKUPS_FILE = EVAL / "results" / "id_lookups.json"

ANY_ID = re.compile(r"GHSA(?:-[0-9a-z]{4}){3}|CVE-\d{4}-\d{4,}", re.IGNORECASE)
CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)
FENCE = re.compile(r"\A\s*```[A-Za-z]*[ \t]*\n(.*?)\n?[ \t]*```\s*\Z", re.DOTALL)
NULL_WORDS = {"", "none", "n/a", "null"}

# Which way a `value` or a disagreement value is compared, by question subtype. Anything not
# listed is a version: "5.30" is a different version from "5.3" but the same score.
SCORE_SUBTYPES = {"a1_nvd_score", "band_agree", "band_differ", "one_silent"}
LABEL_SUBTYPES = {"severity_id", "severity_desc"}
TRIVIAL_ABSTAIN = {"fake_cve", "fake_ghsa", "fake_package", "off_topic"}


# --- reading a reply -------------------------------------------------------------------------


def schema_problem(answer: object) -> str | None:
    """Says what is wrong with an answer, or None. Checks answer_schema.json by hand so the
    scorer needs no extra package."""
    if not isinstance(answer, dict):
        return "the reply is not a JSON object"
    for key in ("abstain", "verdict", "ids", "value", "disagreement", "explanation"):
        if key not in answer:
            return f"the field {key} is missing"
    if not isinstance(answer["abstain"], bool):
        return "abstain is not true or false"
    if answer["verdict"] not in ("yes", "no", None):
        return "verdict is not yes, no or null"
    ids = answer["ids"]
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return "ids is not a list of text"
    if answer["value"] is not None and not isinstance(answer["value"], str):
        return "value is not text or null"
    if not isinstance(answer["explanation"], str):
        return "explanation is not text"
    disagreement = answer["disagreement"]
    if not isinstance(disagreement, dict) or not isinstance(disagreement.get("flagged"), bool):
        return "disagreement.flagged is not true or false"
    values = disagreement.get("values")
    if not isinstance(values, dict) or not {"github", "nvd"} <= set(values):
        return "disagreement.values lacks github or nvd"
    if not all(v is None or isinstance(v, str) for v in (values["github"], values["nvd"])):
        return "a disagreement value is not text or null"
    return None


def read_reply(text: str) -> tuple[dict | None, str | None]:
    """Rules, section 5: strip one surrounding code fence, parse the first top-level JSON
    object, repair nothing else."""
    body = text.strip()
    fenced = FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    start = body.find("{")
    if start < 0:
        return None, "no JSON object in the reply"
    try:
        answer, _ = json.JSONDecoder().raw_decode(body[start:])
    except ValueError:
        return None, "the reply is not valid JSON"
    problem = schema_problem(answer)
    return (None, problem) if problem else (answer, None)


# --- normalising ---------------------------------------------------------------------------


def normal_id(text: str) -> str:
    cleaned = text.strip()
    if cleaned.upper().startswith("GHSA-"):
        return "GHSA-" + cleaned[5:].lower()
    return cleaned.upper()


def version_key(text: str | None) -> tuple[str, ...] | None:
    if text is None or text.strip().lower() in NULL_WORDS:
        return None
    parts = text.strip().lower().removeprefix("v").split(".")
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return tuple(parts)


def score_key(text: str | None) -> str | None:
    """The number in a score, to one decimal: "8.6 (High)" reads as "8.6"."""
    if text is None:
        return None
    found = re.search(r"\d+(?:\.\d+)?", text)
    return f"{float(found.group()):.1f}" if found else None


def label_key(text: str | None) -> str | None:
    if text is None or text.strip().lower() in NULL_WORDS:
        return None
    word = text.strip().lower()
    return "moderate" if word == "medium" else word


def value_key(subtype: str, text: str | None) -> object:
    if subtype in SCORE_SUBTYPES:
        return score_key(text)
    if subtype in LABEL_SUBTYPES:
        return label_key(text)
    return version_key(text)


# --- the ID snapshot -----------------------------------------------------------------------


class Ids:
    """Which IDs exist, and which advisory a CVE belongs to. Built from the committed
    snapshot file, so a laptop and CI label the same ID the same way."""

    def __init__(self, snapshot: dict, lookups: dict | None = None) -> None:
        self.advisories: dict[str, list[str]] = snapshot["advisories"]
        self.out_of_scope: set[str] = set(snapshot["out_of_scope"])
        self.nonexistent: set[str] = set(snapshot["nonexistent"])
        self.lookups = lookups or {}
        self.owners: dict[str, list[str]] = defaultdict(list)
        for ghsa, cves in self.advisories.items():
            for cve in cves:
                self.owners[cve].append(ghsa)

    def canonical(self, text: str) -> str:
        """The advisory an ID stands for. A CVE named by two advisories stands for neither."""
        found = normal_id(text)
        if found in self.advisories:
            return found
        owners = self.owners.get(found, [])
        return owners[0] if len(owners) == 1 else found

    def label(self, found: str) -> str:
        if found in self.advisories or found in self.owners:
            return "corpus"
        if found in self.out_of_scope:
            return "out_of_scope"
        if found in self.nonexistent:
            return "nonexistent"
        return self.lookups.get(found, {}).get("label", "unchecked")


def build_snapshot(raw_dir: Path, rest_dir: Path, evidence_dir: Path) -> dict:
    """The corpus IDs from the raw OSV files, the real-but-outside IDs from the REST cache and
    the evidence, and the IDs the question build proved absent."""
    advisories: dict[str, list[str]] = {}
    for path in sorted((raw_dir / "osv").glob("GHSA-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        advisories[record["id"]] = sorted(
            {normal_id(a) for a in record.get("aliases", []) if CVE_ID.fullmatch(a)}
        )
    outside: set[str] = set()
    for path in sorted(rest_dir.glob("GHSA-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["ghsa_id"] not in advisories:
            outside |= {record["ghsa_id"], *_cve(record)}
    for path in sorted((evidence_dir / "out_of_scope").glob("GHSA-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        outside |= {record["ghsa_id"], *_cve(record)}
    cached = evidence_dir / "out_of_scope_cache.json"
    for record in json.loads(cached.read_text(encoding="utf-8")):
        outside |= {record["ghsa_id"], *_cve(record)}
    checks = json.loads((evidence_dir / "checks.json").read_text(encoding="utf-8"))
    absent = {
        normal_id(key.split(":", 1)[1])
        for key, value in checks.items()
        if value["absent"] and key.split(":", 1)[0] in ("ghsa", "cve")
    }
    manifest = json.loads((raw_dir.parent / "manifest.json").read_text(encoding="utf-8"))
    return {
        "snapshot": manifest["snapshot_id"],
        "advisories": advisories,
        "out_of_scope": sorted({normal_id(i) for i in outside} - set(advisories)),
        "nonexistent": sorted(absent),
    }


def _cve(record: dict) -> set[str]:
    return {normal_id(record["cve_id"])} if record.get("cve_id") else set()


# --- looking up an ID that nothing committed knows ---------------------------------------


def http_status(url: str) -> tuple[int, dict | None]:
    headers = {"User-Agent": "otis-eval-scorer", "Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None
    except (urllib.error.URLError, TimeoutError):
        return 0, None


def look_up(found: str, get: Callable[[str], tuple[int, dict | None]], pause: float = 0) -> dict:
    """GitHub's REST API or NVD first, then OSV. A 404 from both (or an empty NVD answer and a
    404 from OSV) is nonexistent. Anything else that is not a clear yes or no stays unchecked."""
    if found.startswith("GHSA-"):
        first = f"https://api.github.com/advisories/{found}"
    else:
        first = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={found}"
        time.sleep(pause)
    status, body = get(first)
    if status == 200 and (found.startswith("GHSA-") or body and body.get("vulnerabilities")):
        return {"label": "out_of_scope", "checked": [first]}
    if status not in (200, 404):
        return {"label": "unchecked", "checked": [first], "status": status}
    second = f"https://api.osv.dev/v1/vulns/{found}"
    osv_status, _ = get(second)
    if osv_status == 200:
        return {"label": "out_of_scope", "checked": [first, second]}
    if osv_status == 404:
        return {"label": "nonexistent", "checked": [first, second]}
    return {"label": "unchecked", "checked": [first, second], "status": osv_status}


def settle_lookups(wanted: set[str], path: Path, get=http_status, pause: float = 6.5) -> dict:
    """Looks up each wanted ID once and keeps the answers, so a second run is offline."""
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for found in sorted(wanted):
        if known.get(found, {}).get("label") in (None, "unchecked"):
            known[found] = look_up(found, get, pause)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(known, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return known


# --- marking one reply ---------------------------------------------------------------------


def mark(question: dict, gold: dict, answer: dict, ids: Ids) -> tuple[bool, float | None]:
    """Rules, section 6: the one field the gold names decides. Returns correct and set F1."""
    field, subtype, expected = question["answers_with"], question["subtype"], gold["gold"]
    if field == "abstain":
        return answer["abstain"], None
    if answer["abstain"]:
        return False, None
    if field == "verdict":
        return answer["verdict"] == expected["verdict"], None
    if field == "value":
        return value_key(subtype, answer["value"]) == value_key(subtype, expected["value"]), None
    if field == "disagreement":
        said, wanted = answer["disagreement"], expected["disagreement"]
        same = said["flagged"] == wanted["flagged"] and all(
            value_key(subtype, said["values"][side]) == value_key(subtype, wanted["values"][side])
            for side in ("github", "nvd")
        )
        return same, None
    convert = normal_id if subtype == "map_id" else ids.canonical
    given = {convert(i) for i in answer["ids"]}
    wanted_ids = {convert(i) for i in expected["ids"]}
    hits = len(given & wanted_ids)
    precision = hits / len(given) if given else 0.0
    recall = hits / len(wanted_ids) if wanted_ids else 0.0
    f1 = 2 * precision * recall / (precision + recall) if hits else 0.0
    return given == wanted_ids, f1


def score_question(question: dict, gold: dict, line: dict, ids: Ids) -> dict:
    stop = line.get("stop_reason")
    answer, problem = (None, "the reply was refused") if stop == "refusal" else (None, None)
    if stop == "max_tokens":
        problem = "the reply was cut short by the token limit"
    elif stop != "refusal":
        answer, problem = read_reply(line.get("text") or "")
    row = {
        key: question[key]
        for key in ("id", "type", "subtype", "split", "slice", "stale_risk", "maven_release")
    }
    row.update(
        ecosystem=question["ecosystem"],
        answers_with=question["answers_with"],
        run=line.get("run", 1),
        outcome="refusal" if stop == "refusal" else "parse_failure" if problem else "wrong",
        abstained=False,
        over_abstained=False,
        f1=None,
        echoed=[],
        labels={},
        problem=problem,
        cost_usd=line.get("cost_usd"),
        latency_s=line.get("latency_s"),
    )
    if answer is None:
        return row
    correct, row["f1"] = mark(question, gold, answer, ids)
    row["outcome"] = "correct" if correct else "wrong"
    row["abstained"] = answer["abstain"]
    row["over_abstained"] = answer["abstain"] and question["answers_with"] != "abstain"
    asked = {normal_id(i) for i in ANY_ID.findall(question["question"])}
    found = {normal_id(i) for i in ANY_ID.findall(json.dumps(answer))}
    row["echoed"] = sorted(found & asked)
    row["labels"] = {i: ids.label(i) for i in sorted(found - asked)}
    return row


def reply_ids(question: dict, line: dict) -> set[str]:
    """The IDs a reply holds that are not in the question, for deciding what to look up."""
    answer, _ = read_reply(line.get("text") or "")
    if answer is None:
        return set()
    asked = {normal_id(i) for i in ANY_ID.findall(question["question"])}
    return {normal_id(i) for i in ANY_ID.findall(json.dumps(answer))} - asked


# --- summarising ---------------------------------------------------------------------------


def wilson(hits: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z, p = 1.96, hits / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    scale = 1 + z * z / total
    return max(0.0, (centre - spread) / scale), min(1.0, (centre + spread) / scale)


def show(hits: int, total: int) -> str:
    if total == 0:
        return "0/0"
    low, high = wilson(hits, total)
    return f"{hits}/{total} ({100 * hits / total:.0f}%, 95% CI {100 * low:.0f} to {100 * high:.0f})"


def share(rows: list[dict], test: Callable[[dict], bool]) -> tuple[int, int]:
    return sum(1 for r in rows if test(r)), len(rows)


def is_right(row: dict) -> bool:
    return row["outcome"] == "correct"


def summarise(rows: list[dict]) -> dict:
    """Every figure the rules ask for, as plain numbers, for one run."""
    answerable = [r for r in rows if r["answers_with"] != "abstain"]
    parsed = [r for r in rows if r["outcome"] in ("correct", "wrong")]
    fabricated = sum(1 for r in parsed if "nonexistent" in r["labels"].values())
    unchecked = sum(
        1
        for r in parsed
        if "unchecked" in r["labels"].values() and "nonexistent" not in r["labels"].values()
    )
    said_abstain = [r for r in parsed if r["abstained"]]
    gold_abstain = [r for r in rows if r["answers_with"] == "abstain"]
    verdicts = [r for r in rows if r["answers_with"] == "verdict"]
    cost = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    seconds = sorted(r["latency_s"] for r in rows if r["latency_s"] is not None)

    def groups(key: str, pool: list[dict]) -> dict:
        names = sorted({str(r[key]) for r in pool if r[key] is not None})
        return {n: share([r for r in pool if str(r[key]) == n], is_right) for n in names}

    return {
        "questions": len(rows),
        "all": share(rows, is_right),
        "answerable": share(answerable, is_right),
        "by_type": groups("type", rows),
        "by_slice": groups("slice", answerable),
        "by_ecosystem": groups("ecosystem", answerable),
        "stale_risk": share([r for r in answerable if r["stale_risk"]], is_right),
        "maven_release": share([r for r in answerable if r["maven_release"]], is_right),
        "abstain_trivial": share(
            [r for r in gold_abstain if r["subtype"] in TRIVIAL_ABSTAIN], is_right
        ),
        "abstain_hard": share(
            [r for r in gold_abstain if r["subtype"] not in TRIVIAL_ABSTAIN], is_right
        ),
        "abstain_precision": share(said_abstain, lambda r: r["answers_with"] == "abstain"),
        "abstain_recall": share(gold_abstain, lambda r: r["abstained"]),
        "over_abstained": share(answerable, lambda r: r["over_abstained"]),
        "parse_failures": sum(1 for r in rows if r["outcome"] == "parse_failure"),
        "refusals": sum(1 for r in rows if r["outcome"] == "refusal"),
        "abstentions": len(said_abstain),
        "fabricated": (fabricated, len(parsed)),
        "fabricated_upper": (fabricated + unchecked, len(parsed)),
        "unchecked_ids": sum(list(r["labels"].values()).count("unchecked") for r in parsed),
        "echoed": sum(len(r["echoed"]) for r in parsed),
        "majority_floor": (
            max(Counter(r.get("gold_verdict") for r in verdicts).values(), default=0),
            len(verdicts),
        ),
        "mean_f1": statistics.fmean([r["f1"] for r in rows if r["f1"] is not None] or [0.0]),
        "cost_total": sum(cost),
        "cost_per_query": statistics.fmean(cost) if cost else 0.0,
        "latency_median": statistics.median(seconds) if seconds else 0.0,
        "latency_p95": seconds[min(len(seconds) - 1, math.ceil(0.95 * len(seconds)) - 1)]
        if seconds
        else 0.0,
    }


def render(summary: dict, title: str) -> str:
    out = [f"== {title} ({summary['questions']} questions)"]

    def line(name: str, pair: tuple[int, int]) -> None:
        out.append(f"{name:<34}{show(*pair)}")

    line("correct, all", summary["all"])
    line("correct, answerable only", summary["answerable"])
    for name, pair in summary["by_type"].items():
        line(f"  type {name}", pair)
    for name, pair in summary["by_slice"].items():
        line(f"  slice {name} (answerable)", pair)
    for name, pair in summary["by_ecosystem"].items():
        line(f"  ecosystem {name} (answerable)", pair)
    line("  stale-risk (answerable)", summary["stale_risk"])
    line("  Maven RELEASE (answerable)", summary["maven_release"])
    line("abstain, trivial", summary["abstain_trivial"])
    line("abstain, hard", summary["abstain_hard"])
    line("abstention precision", summary["abstain_precision"])
    line("abstention recall", summary["abstain_recall"])
    line("over-abstention", summary["over_abstained"])
    low, high = summary["fabricated"], summary["fabricated_upper"]
    if low == high:
        line("fabrication rate", low)
    else:
        out.append(f"{'fabrication rate':<34}{show(*low)} up to {show(*high)}")
        out.append(f"{'':<34}{summary['unchecked_ids']} IDs unchecked; run again with --online")
    out.append(
        f"{'parse failures / refusals':<34}{summary['parse_failures']} / {summary['refusals']}"
    )
    out.append(f"{'abstentions':<34}{summary['abstentions']}")
    out.append(f"{'IDs repeated from the question':<34}{summary['echoed']}")
    floor = summary["majority_floor"]
    out.append(f"{'yes/no majority floor':<34}{floor[0]}/{floor[1]}")
    out.append(f"{'mean set F1 (ID questions)':<34}{summary['mean_f1']:.2f}")
    out.append(
        f"{'cost':<34}${summary['cost_total']:.2f} total, ${summary['cost_per_query']:.4f} a query"
    )
    out.append(
        f"{'latency':<34}median {summary['latency_median']:.1f}s, p95 {summary['latency_p95']:.1f}s"
    )
    return "\n".join(out)


def mcnemar_p(only_a: int, only_b: int) -> float:
    """Exact two-sided McNemar test: the chance of a split this lopsided if the two systems
    were equally likely to win each question they disagree on."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(only_a, only_b) + 1)) / 2**n
    return min(1.0, 2 * tail)


# --- running it ----------------------------------------------------------------------------


def read_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def with_errata(gold: dict[str, dict], errata_path: Path | None) -> dict[str, dict]:
    if errata_path is None or not errata_path.exists():
        return gold
    fixed = dict(gold)
    for entry in read_lines(errata_path):
        fixed[entry["id"]] = {**fixed[entry["id"]], "gold": entry["gold"]}
    return fixed


def score_all(
    questions: list[dict], gold: dict[str, dict], lines: list[dict], ids: Ids
) -> dict[int, list[dict]]:
    """Rows per run. A question with two lines in one run is an error: the runner never does it."""
    by_id = {q["id"]: q for q in questions}
    seen: set[tuple[int, str]] = set()
    runs: dict[int, list[dict]] = defaultdict(list)
    for line in lines:
        question = by_id.get(line["id"])
        if question is None:
            continue
        key = (line.get("run", 1), line["id"])
        if key in seen:
            raise ValueError(
                f"Question {line['id']} appears twice in run {key[0]}. Check the file."
            )
        seen.add(key)
        row = score_question(question, gold[line["id"]], line, ids)
        row["gold_verdict"] = gold[line["id"]]["gold"]["verdict"]
        runs[row["run"]].append(row)
    return runs


def load_ids(online_for: set[str] | None = None) -> Ids:
    snapshot = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    if online_for:
        lookups = settle_lookups(online_for, LOOKUPS_FILE)
    else:
        lookups = (
            json.loads(LOOKUPS_FILE.read_text(encoding="utf-8")) if LOOKUPS_FILE.exists() else {}
        )
    return Ids(snapshot, lookups)


def command_score(args: argparse.Namespace) -> int:
    questions = [q for q in read_lines(EVAL / "questions.jsonl") if q["split"] == args.split]
    gold = {g["id"]: g for g in read_lines(EVAL / "gold.jsonl")}
    lines = read_lines(Path(args.results))
    wanted = {q["id"]: q for q in questions}
    ignored = sum(1 for x in lines if x["id"] not in wanted)
    lines = [x for x in lines if x["id"] in wanted]
    pending: set[str] = set()
    if args.online:
        base = load_ids()
        for x in lines:
            pending |= {i for i in reply_ids(wanted[x["id"]], x) if base.label(i) == "unchecked"}
    ids = load_ids(pending)
    errata = Path(args.errata) if args.errata else EVAL / "errata.jsonl"
    if args.errata and not errata.exists():
        raise SystemExit(f"The errata file {errata} does not exist. Check the path.")
    versions = [("as frozen", gold)]
    if errata.exists() and errata.read_text(encoding="utf-8").strip():
        versions.append(("with errata applied", with_errata(gold, errata)))
    written: list[dict] = []
    for name, golds in versions:
        runs = score_all(questions, golds, lines, ids)
        for run, rows in sorted(runs.items()):
            print(render(summarise(rows), f"{args.split}, run {run}, gold {name}"))
            missing = len(questions) - len(rows)
            if missing:
                print(f"NOT RUN: {missing} {args.split} questions have no reply in run {run}")
            print()
            written += [{**r, "errata_applied": name != "as frozen"} for r in rows]
        if len(runs) > 1:
            same = sum(
                1
                for qid in wanted
                if len({r["outcome"] for rs in runs.values() for r in rs if r["id"] == qid}) == 1
            )
            print(f"Same outcome in every run ({name}): {same}/{len(wanted)}\n")
    if ignored:
        print(f"Ignored {ignored} reply lines for questions outside the {args.split} split.")
    if args.out:
        Path(args.out).write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in written), encoding="utf-8"
        )
    return 0


def command_compare(args: argparse.Namespace) -> int:
    tables = []
    for path in (args.first, args.second):
        rows = [r for r in read_lines(Path(path)) if r["errata_applied"] == args.errata_applied]
        runs = {r["run"] for r in rows}
        if len(runs) != 1:
            print(f"{path} holds runs {sorted(runs)}. Compare needs one run per file.")
            return 1
        tables.append({r["id"]: r for r in rows})
    first, second = tables
    shared = sorted(set(first) & set(second))
    only_first = [i for i in shared if is_right(first[i]) and not is_right(second[i])]
    only_second = [i for i in shared if is_right(second[i]) and not is_right(first[i])]
    both = sum(1 for i in shared if is_right(first[i]) and is_right(second[i]))
    neither = len(shared) - both - len(only_first) - len(only_second)
    print(f"{len(shared)} shared questions: both right {both}, only first {len(only_first)},")
    print(f"only second {len(only_second)}, both wrong {neither}")
    print(f"Exact McNemar p = {mcnemar_p(len(only_first), len(only_second)):.4f}")
    for qid in only_first + only_second:
        print(f"  {qid}: {'first' if qid in only_first else 'second'} only")
    return 0


def command_snapshot(args: argparse.Namespace) -> int:
    root = EVAL.parent
    snapshot = build_snapshot(
        root / "data" / "raw", root / "data" / "rest_cache", EVAL / "evidence"
    )
    SNAPSHOT_FILE.write_text(
        json.dumps(snapshot, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"{len(snapshot['advisories'])} advisories, {len(snapshot['out_of_scope'])} outside, "
        f"{len(snapshot['nonexistent'])} proved absent"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("snapshot").set_defaults(run=command_snapshot)
    score = commands.add_parser("score")
    score.add_argument("--results", required=True)
    score.add_argument("--split", choices=["dev", "test"], required=True)
    score.add_argument("--errata")
    score.add_argument("--out")
    score.add_argument("--online", action="store_true", help="look up IDs nothing committed knows")
    score.set_defaults(run=command_score)
    compare = commands.add_parser("compare")
    compare.add_argument("first")
    compare.add_argument("second")
    compare.add_argument("--errata-applied", action="store_true")
    compare.set_defaults(run=command_compare)
    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
