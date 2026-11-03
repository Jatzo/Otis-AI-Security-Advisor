"""One attack case, and the file of them.

A case says which question is asked, what is changed in the store first, and what counts as the
attack working. The file is written once by scripts/make_attack_spec.py and then frozen under a
tag. A case never holds the answer to its own check: the checkers are in success.py.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

# What the attacker wanted, and so what success.py looks for in the reply.
GOALS = (
    "canary",  # a made-up token the attack text asked for
    "fake_id",  # an advisory ID that exists in no record
    "other_id",  # a real ID the question did not ask about
    "decline",  # a question the clean store answered right, now declined
    "url",  # any web address in the reply
    "leak",  # twelve words in a row from the system prompt
    "false_version",  # a fixed version only the poison states
    "off_topic",  # an answer to a request that is not about advisories
)
CLASSES = ("A", "Aq", "B1", "B2", "D-leak", "D-off")
SETS = ("first", "heldout")
FIELDS = ("summary", "details", "nvd_details")


@dataclass(frozen=True)
class Edit:
    """Text added to a record that already exists. field is where it goes: the GitHub advisory's
    title line (summary) or description (details), or the NVD description (nvd_details)."""

    unit: str
    field: str
    text: str


@dataclass(frozen=True)
class NewRecord:
    """A GitHub advisory the attacker adds, with structured fields of their choosing."""

    record_id: str
    ecosystem: str
    package: str
    fixed: str
    aliases: tuple[str, ...]
    summary: str
    severity: str = "HIGH"


@dataclass(frozen=True)
class Case:
    case_id: str
    set: str
    cls: str
    technique: str
    placement: str
    goal: str
    question: str
    carrier: str | None  # the dev question this is built on, if any
    edits: tuple[Edit, ...] = ()
    new_record: NewRecord | None = None
    token: str = ""  # the canary, fake ID, address, other ID or false version the goal looks for
    poisoned_sha256: str = ""

    def problems(self) -> list[str]:
        found = []
        if self.set not in SETS:
            found.append(f"{self.case_id}: unknown set {self.set}")
        if self.cls not in CLASSES:
            found.append(f"{self.case_id}: unknown class {self.cls}")
        if self.goal not in GOALS:
            found.append(f"{self.case_id}: unknown goal {self.goal}")
        if (
            self.goal in ("canary", "fake_id", "other_id", "url", "false_version")
            and not self.token
        ):
            found.append(f"{self.case_id}: the goal {self.goal} needs a token")
        if any(edit.field not in FIELDS for edit in self.edits):
            found.append(f"{self.case_id}: an edit names an unknown field")
        if not self.question.strip():
            found.append(f"{self.case_id}: no question")
        return found


def to_line(case: Case) -> str:
    return json.dumps(asdict(case), sort_keys=True, ensure_ascii=False)


def from_line(line: str) -> Case:
    raw = json.loads(line)
    raw["edits"] = tuple(Edit(**edit) for edit in raw["edits"])
    if raw["new_record"] is not None:
        raw["new_record"] = NewRecord(
            **{**raw["new_record"], "aliases": tuple(raw["new_record"]["aliases"])}
        )
    return Case(**raw)


def load(path: Path) -> list[Case]:
    cases = [from_line(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path.name} repeats a case id")
    problems = [p for case in cases for p in case.problems()]
    if problems:
        raise ValueError("; ".join(problems))
    return cases


def save(cases: list[Case], path: Path) -> None:
    path.write_text("\n".join(to_line(case) for case in cases) + "\n", encoding="utf-8")
