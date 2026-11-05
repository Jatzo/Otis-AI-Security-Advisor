"""The checker: rules 1 to 8 of docs/generation-plan.md, in that order, the first failure deciding.

It is a pure function of the question, the raw reply, the units that were shown and the store, so it
can be run again over saved replies with no API call. It reads every fact from the store. It reads
the question only for ID formats, the 18 package names and the version grammar, never its type and
never the gold.

The one repair it makes is cutting out an ID the evidence never held. Anything else wrong, such as a
wrong version, score or label, refuses the whole reply: patching a fact would be code answering the
question, which ADR 0001 rules out.
"""

import json
import re
from dataclasses import dataclass, field

from advisor.generation.facts import Facts, canonical_package, same_version
from advisor.generation.reading import (
    KNOWN_FIELDS,
    MAX_CLAIMS,
    NULL_WORDS,
    Claim,
    band,
    ids_in,
    is_score_text,
    label_key,
    normal_id,
    read_claim,
    read_reply,
    score_key,
    version_key,
)
from advisor.retrieval.query import PATTERNS
from advisor.retrieval.units import Unit
from advisor.versions import UnparseableVersion, is_affected

REFUSAL_TEXT = (
    "Otis could not confirm this answer against the advisories it found, so it is not giving one. "
    "Name the advisory ID, or the package and version, and ask again."
)
GATE_TEXT = (
    "Otis holds no advisory with an ID you named, so it is not giving an answer. "
    "Check the ID and ask again."
)
# Kept as they came: a refusal must not turn into an abstention.
STOPPED = ("refusal", "max_tokens")

VERSION_SHAPE = r"v?\d[0-9A-Za-z_+-]*(?:\.[0-9A-Za-z_+-]+)*"
PAIRS = {
    name: re.compile(
        rf"(?:{pattern.pattern})\s+(?:version\s+)?(?P<version>{VERSION_SHAPE})", re.IGNORECASE
    )
    for name, pattern in PATTERNS.items()
}
ASKS_AFFECTED = re.compile(r"\b(?:affect(?:s|ed|ing)?|vulnerable)\b", re.IGNORECASE)
NEGATED = re.compile(r"\b(?:not|unaffected|safe|immune)\b", re.IGNORECASE)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
NO_DISAGREEMENT = {"flagged": False, "values": {"github": None, "nvd": None}}


def question_pairs(question: str) -> list[tuple[str, str]]:
    """Package-version pairs in the question: a package name, an optional "version", then a version
    token. A bare version ("fixed in 2.3.29") is not a pair."""
    found = []
    for name, pattern in PAIRS.items():
        for match in pattern.finditer(question):
            found.append((name, match.group("version").removeprefix("v")))
    return found


def asks_if_affected(question: str) -> bool:
    """Whether a yes or no is about being affected, so the claim's polarity can be held to it."""
    return bool(ASKS_AFFECTED.search(question)) and not NEGATED.search(question)


@dataclass
class Checked:
    text: str
    verdict: str  # passed, repaired, abstained, refused, parse_failure, stopped
    route: str  # gate, model, checker, answer, none
    rule: int | None = None
    removed_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    polarity_checked: bool | None = None

    def record(self) -> dict:
        """The checker object a result line carries."""
        return {
            "route": self.route, "verdict": self.verdict, "rule": self.rule,
            "removed_ids": self.removed_ids, "reasons": self.reasons, "claims": self.claims,
            "polarity_checked": self.polarity_checked,
        }  # fmt: skip


@dataclass
class Judged:
    claim: Claim
    status: str  # passed, failed, unverifiable
    rule: int | None = None
    reason: str = ""
    kev_unit_shown: bool | None = None


def abstention(explanation: str) -> dict:
    return {
        "abstain": True, "verdict": None, "ids": [], "value": None,
        "disagreement": json.loads(json.dumps(NO_DISAGREEMENT)),
        "explanation": explanation, "claims": [],
    }  # fmt: skip


def dump(answer: dict) -> str:
    return json.dumps(answer, ensure_ascii=False)


class Case:
    """What one question and its shown units make available to the rules."""

    def __init__(self, question: str, shown: list[Unit], facts: Facts) -> None:
        self.question, self.facts = question, facts
        self.named = list(dict.fromkeys(ids_in(question)))
        self.pairs = question_pairs(question)
        self.shown_ghsa = {u.unit_id.split(":", 1)[1] for u in shown if u.source == "ghsa"}
        self.shown_nvd = {u.unit_id.split(":", 1)[1] for u in shown if u.source == "nvd"}
        self.shown_kev = {u.unit_id.split(":", 1)[1] for u in shown if u.source == "kev"}
        self.cve_to_ghsa: dict[str, set[str]] = {}
        self.shown_ids: set[str] = set()
        self.grounded = set(self.named)
        for unit in shown:
            record_id = normal_id(unit.unit_id.split(":", 1)[1])
            self.grounded |= facts.related(record_id)
            for alias in unit.aliases:
                self.shown_ids.add(normal_id(alias))
                if unit.source == "ghsa" and alias.upper().startswith("CVE-"):
                    self.cve_to_ghsa.setdefault(normal_id(alias), set()).add(record_id)
        self.near_named = [facts.related(found) for found in self.named]

    def about_named(self, found: str) -> bool:
        """Whether an ID is a named ID or one of its aliases. No named ID ties nothing down."""
        return not self.named or any(found in near for near in self.near_named)

    # --- rule 4: the claim cites a shown unit ---------------------------------------------

    def resolve(self, claim: Claim) -> tuple[str, str] | str:
        """The (table, id) the claim is read against, or why it cites nothing shown."""
        if claim.kind == "kev":
            cve = claim.get("cve")
            if cve in self.shown_ids:
                return "kev", cve
            return f"{cve} is not named by any record shown"
        record, source = claim.get("record"), claim.get("source")
        if source == "nvd":
            if record in self.shown_nvd:
                return "nvd", record
            return f"{record} has no NVD record among the records shown"
        if record.startswith("CVE-"):
            if claim.kind == "published":
                if record in self.shown_nvd:
                    return "nvd", record
                return f"{record} has no NVD record among the records shown"
            owners = self.cve_to_ghsa.get(record, set())
            if len(owners) == 1:
                return "ghsa", next(iter(owners))
            return f"{record} is not an alias of exactly one advisory shown"
        if record in self.shown_ghsa:
            return "ghsa", record
        return f"{record} is not among the records shown"

    # --- rules 4 to 6, one claim ---------------------------------------------------------

    def judge(self, claim: Claim) -> Judged:
        found = self.resolve(claim)
        if isinstance(found, str):
            return Judged(claim, "failed", 4, found)
        if claim.kind == "affects" and self.pairs:
            mismatch = self.tie_to_pair(claim)
            if mismatch:
                return Judged(claim, "failed", 5, mismatch)
        status, reason = self.truth(claim, *found)
        judged = Judged(claim, status, None if status == "passed" else 6, reason)
        if claim.kind == "kev":
            judged.kev_unit_shown = claim.get("cve") in self.shown_kev
        return judged

    def tie_to_pair(self, claim: Claim) -> str | None:
        package = canonical_package(claim.get("package"))
        for wanted, version in self.pairs:
            if package == wanted and same_version(wanted, claim.get("version"), version):
                return None
        asked = ", ".join(f"{name} {version}" for name, version in self.pairs)
        return (
            f"the question asks about {asked}, "
            f"the claim is about {claim.get('package')} {claim.get('version')}"
        )

    def truth(self, claim: Claim, table: str, found: str) -> tuple[str, str]:
        facts, kind = self.facts, claim.kind
        if kind == "package":
            package = canonical_package(claim.get("package"))
            if package is not None and package in facts.packages_of(found):
                return "passed", ""
            return "failed", f"{found} does not affect {claim.get('package')}"
        if kind == "alias":
            if claim.get("cve") in facts.aliases_of(found):
                return "passed", ""
            return "failed", f"{found} does not list {claim.get('cve')} as an alias"
        if kind == "affects":
            return self.truth_affects(claim, found)
        if kind == "fixed_in":
            return self.truth_fixed_in(claim, table, found)
        if kind == "severity":
            stored = (facts.record(found, "ghsa") or {}).get("severity")
            if label_key(stored) == label_key(claim.get("label")):
                return "passed", ""
            return "failed", f"{found} is labelled {stored}, the claim says {claim.get('label')}"
        if kind == "score":
            stored = (facts.record(found, table) or {}).get("cvss3_score")
            held = None if stored is None else f"{stored:.1f}"
            said = score_key(claim.get("cvss3")) if claim.get("cvss3") else None
            if held == said:
                return "passed", ""
            return "failed", f"{found} holds CVSS v3 {held}, the claim says {said}"
        if kind == "published":
            stored = ((facts.record(found, table) or {}).get("published") or "")[:10]
            if stored == claim.get("date"):
                return "passed", ""
            return "failed", f"{found} was published {stored or 'on no date held'}"
        if kind == "kev":
            if facts.in_kev(found) == claim.get("listed"):
                return "passed", ""
            return "failed", f"the KEV catalogue does not agree on {found}"
        raise AssertionError(kind)

    def truth_affects(self, claim: Claim, found: str) -> tuple[str, str]:
        package = canonical_package(claim.get("package"))
        if package is None:
            return "failed", f"{claim.get('package')} is not one of the 18 packages"
        rows = self.facts.spans(found, package)
        if not rows:
            computed = False  # the record does not list the package, so it does not affect it
        else:
            types = {(ecosystem, range_type) for ecosystem, range_type, *_ in rows}
            if len(types) > 1:
                return "unverifiable", f"{found} mixes range types for {package}"
            ecosystem, range_type = next(iter(types))
            try:
                computed = is_affected(
                    ecosystem, range_type, claim.get("version"), [tuple(r[2:]) for r in rows]
                )
            except (UnparseableVersion, ValueError) as problem:
                return "unverifiable", f"no version order for {claim.get('version')}: {problem}"
        if computed == claim.get("affected"):
            return "passed", ""
        return "failed", (
            f"{found} {'does' if computed else 'does not'} affect {package} {claim.get('version')}"
        )

    def truth_fixed_in(self, claim: Claim, table: str, found: str) -> tuple[str, str]:
        wanted = version_key(claim.get("version"))
        if table == "nvd":
            ends = self.facts.nvd_end_excluding(found)
            if ends is None:
                return "unverifiable", f"{found} has no vulnerable CPE row to read a fix from"
            if any(version_key(end) == wanted for end in ends):
                return "passed", ""
            return (
                "failed",
                f"NVD gives no end-excluding version {claim.get('version')} for {found}",
            )
        package = canonical_package(claim.get("package"))
        if package is None:
            return "failed", f"{claim.get('package')} is not one of the 18 packages"
        fixed = [row[3] for row in self.facts.spans(found, package) if row[3]]
        if any(version_key(version) == wanted for version in fixed):
            return "passed", ""
        return "failed", f"{claim.get('version')} is not a fixed version of {package} in {found}"

    # --- rule 7: each populated field has a claim behind it ------------------------------

    def support(self, answer: dict, passing: list[Judged]) -> tuple[list[str], bool | None]:
        problems: list[str] = []
        polarity = None
        claims = [j.claim for j in passing]
        problems += self.support_ids(answer["ids"], claims, answer["verdict"])
        if answer["verdict"] is not None:
            polarity, more = self.support_verdict(answer["verdict"], claims)
            problems += more
        value = side_text(answer["value"])
        if value is not None:
            if not any(value_matches(value, claim) for claim in claims):
                problems.append(f"the value {value} matches no passing claim")
        problems += self.support_disagreement(answer["disagreement"], claims)
        return problems, polarity

    def support_ids(self, ids: list[str], claims: list[Claim], verdict: str | None) -> list[str]:
        problems = []
        for item in ids:
            found = ids_in(item)
            if len(found) != 1 or normal_id(item) != found[0]:
                problems.append(f"{item!r} in ids is not a single ID")
            elif self.pairs:
                # With no verdict, ids is the answer and must hold advisories that apply. Under a
                # "no", an advisory named to say it does not apply is backed by that claim.
                if not any(
                    c.kind == "affects"
                    and c.get("record") == found[0]
                    and (c.get("affected") or verdict == "no")
                    for c in claims
                ):
                    problems.append(f"{found[0]} has no passing claim that it affects the pair")
            elif not any(
                c.get("record") == found[0]
                or (c.kind in ("alias", "kev") and c.get("cve") == found[0])
                for c in claims
            ):
                problems.append(f"{found[0]} in ids has no passing claim")
        return problems

    def support_verdict(self, verdict: str, claims: list[Claim]) -> tuple[bool | None, list[str]]:
        kind = "affects" if self.pairs else "kev"
        field_name = "affected" if kind == "affects" else "listed"
        tied = [
            c for c in claims
            if c.kind == kind and self.about_named(c.get("record") or c.get("cve"))
        ]  # fmt: skip
        if not tied:
            return None, [f"the verdict {verdict} has no passing {kind} claim tied to the question"]
        polarity = kind == "kev" or asks_if_affected(self.question)
        if polarity and any(c.get(field_name) != (verdict == "yes") for c in tied):
            return polarity, [f"the verdict {verdict} disagrees with a passing {kind} claim"]
        return polarity, []

    def support_disagreement(self, disagreement: dict, claims: list[Claim]) -> list[str]:
        sides = {name: side_text(disagreement["values"].get(name)) for name in ("github", "nvd")}
        if not disagreement["flagged"] and all(v is None for v in sides.values()):
            return []
        modes: dict[str, set[str]] = {}
        problems = []
        for name, text in sides.items():
            modes[name] = set()
            if text is None:
                if name == "github":
                    problems.append("the github side is null, which no claim can support")
                elif any(c.kind == "score" and c.get("source") == "nvd"
                         and c.get("cvss3") is None for c in claims):  # fmt: skip
                    modes[name].add("score")
                else:
                    problems.append("the nvd side is null with no passing score claim of null")
                continue
            if is_score_text(text) and any(
                c.kind == "score" and c.get("source") == name and c.get("cvss3") is not None
                and score_key(c.get("cvss3")) == score_key(text) for c in claims
            ):  # fmt: skip
                modes[name].add("score")
            parts = [part.strip() for part in text.split(",")]
            if all(
                any(c.kind == "fixed_in" and c.get("source") == name
                    and version_key(c.get("version")) == version_key(part) for c in claims)
                for part in parts
            ):  # fmt: skip
                modes[name].add("version")
            if not modes[name]:
                problems.append(f"the {name} value {text} matches no passing claim")
        if problems:
            return problems
        expected = expected_flag(sides, modes)
        if expected is None:
            return ["the two sides are backed by different kinds of claim"]
        if disagreement["flagged"] != expected:
            return [f"flagged is {disagreement['flagged']} where the values give {expected}"]
        return []


def side_text(value: str | None) -> str | None:
    if value is None or value.strip().lower() in NULL_WORDS:
        return None
    return value.strip()


def expected_flag(sides: dict[str, str | None], modes: dict[str, set[str]]) -> bool | None:
    """What flagged must be for these values, by the evaluation rules, section 4: different bands
    for scores, no shared version for versions, true for a silent source."""
    if all("score" in found for found in modes.values()):
        if sides["nvd"] is None:
            return True
        github, nvd = (float(score_key(sides[name])) for name in ("github", "nvd"))
        return band(github) != band(nvd)
    if all("version" in found for found in modes.values()):
        left = {version_key(part) for part in sides["github"].split(",")}
        right = {version_key(part) for part in sides["nvd"].split(",")}
        return not (left & right)
    return None


def value_matches(value: str, claim: Claim) -> bool:
    """A value is a fixed version, a label, a score or a date that a passing claim states."""
    if claim.kind == "fixed_in":
        return version_key(value) == version_key(claim.get("version"))
    if claim.kind == "severity":
        return label_key(value) == label_key(claim.get("label"))
    if claim.kind == "score":
        return (
            claim.get("cvss3") is not None
            and is_score_text(value)
            and score_key(value) == score_key(claim.get("cvss3"))
        )
    if claim.kind == "published":
        return value.strip() == claim.get("date")
    return False


# --- the whole check ------------------------------------------------------------------------


def refused(rule: int, reasons: list[str], removed: list[str], claims: list[dict]) -> Checked:
    return Checked(
        dump(abstention(REFUSAL_TEXT)), "refused", "checker", rule, removed, reasons, claims
    )


def cut_sentences(text: str, bad: set[str]) -> str:
    kept = [s for s in SENTENCE_BREAK.split(text) if not set(ids_in(s)) & bad]
    return " ".join(kept)


def ground(answer: dict, grounded: set[str]) -> tuple[dict, list[str], str | None]:
    """Rule 3. Returns the answer with ungrounded IDs cut out, the IDs removed, and a reason if one
    sits where it cannot be cut out: value, disagreement or a field the schema does not name."""
    bad = {found for found in ids_in(dump(answer)) if found not in grounded}
    if not bad:
        return answer, [], None
    for name in ("value", "disagreement", *(k for k in answer if k not in KNOWN_FIELDS)):
        if set(ids_in(dump(answer.get(name)))) & bad:
            return answer, sorted(bad), f"an ID the evidence never held is inside {name}"
    cleaned = dict(answer)
    cleaned["ids"] = [i for i in answer["ids"] if not set(ids_in(i)) & bad]
    cleaned["explanation"] = cut_sentences(answer["explanation"], bad)
    if isinstance(answer.get("claims"), list):
        cleaned["claims"] = [c for c in answer["claims"] if not set(ids_in(dump(c))) & bad]
    return cleaned, sorted(bad), None


def check(
    question: str, raw_text: str, stop_reason: str | None, shown: list[Unit], facts: Facts
) -> Checked:
    case = Case(question, shown, facts)
    missing = [found for found in case.named if not facts.holds_id(found)]
    if missing:  # rule 1
        reasons = [f"{found} is held by no record, alias or KEV entry" for found in missing]
        return Checked(dump(abstention(GATE_TEXT)), "refused", "gate", 1, [], reasons)
    if stop_reason in STOPPED:
        return Checked(raw_text, "stopped", "none", None)
    answer, problem = read_reply(raw_text)  # rule 2
    if problem:
        return Checked(raw_text, "parse_failure", "none", 2, [], [problem])
    claims = answer.get("claims", [])
    if not answer["abstain"] and isinstance(claims, list) and len(claims) > MAX_CLAIMS:
        reason = f"{len(claims)} claims, where at most {MAX_CLAIMS} are allowed"
        return refused(2, [reason], [], [])
    had_ids = bool(answer["ids"])
    cleaned, removed, stuck = ground(answer, case.grounded)  # rule 3
    if cleaned["abstain"]:
        return abstained(raw_text, cleaned, removed, stuck)
    if stuck:
        return refused(3, [stuck], removed, [])
    if had_ids and not cleaned["ids"]:
        return refused(3, ["every ID in ids was one the evidence never held"], removed, [])
    return judge_answer(case, cleaned, removed, raw_text)


def abstained(raw_text: str, answer: dict, removed: list[str], stuck: str | None) -> Checked:
    """The model declined. Its decision stands as it is unless an ID the evidence never held rides
    along, in which case the reply is cut down to a plain abstention."""
    if not removed:
        return Checked(raw_text, "abstained", "model")
    kept = abstention(cut_sentences(answer["explanation"], set(removed)))
    return Checked(dump(kept), "abstained", "model", 3, removed, [stuck] if stuck else [])


def judge_answer(case: Case, answer: dict, removed: list[str], raw_text: str) -> Checked:
    claims = answer.get("claims", [])
    if not isinstance(claims, list):
        return refused(4, ["claims is not a list"], removed, [])
    form_problems: list[str] = []
    judged: list[Judged] = []
    for index, raw in enumerate(claims, start=1):
        read = read_claim(raw, index)
        if isinstance(read, str):
            form_problems.append(read)
        else:
            judged.append(case.judge(read))
    summary = [
        {
            "index": j.claim.index, "kind": j.claim.kind, "status": j.status, "rule": j.rule,
            "reason": j.reason, "kev_unit_shown": j.kev_unit_shown,
        }
        for j in judged
    ]  # fmt: skip
    failed = [j for j in judged if j.status != "passed"]
    if form_problems or failed:
        rule = min([4] * bool(form_problems) + [j.rule for j in failed])
        reasons = form_problems + [f"claim {j.claim.index}: {j.reason}" for j in failed]
        return refused(rule, reasons, removed, summary)
    problems, polarity = case.support(answer, judged)
    if problems:
        done = refused(7, problems, removed, summary)
        done.polarity_checked = polarity
        return done
    if not judged:
        return refused(8, ["the reply gives an answer and no claim that passes"], removed, summary)
    text = dump(answer) if removed else raw_text
    verdict = "repaired" if removed else "passed"
    return Checked(text, verdict, "answer", None, removed, [], summary, polarity)
