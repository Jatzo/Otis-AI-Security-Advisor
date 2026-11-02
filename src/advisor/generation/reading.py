"""Reading a reply and the claims in it.

The reply is read the way eval/score.py reads it (rules, section 5), and a test holds the two
together. Nothing is repaired here: a reply that does not parse stays a parse failure, and a claim
that does not fit its kind is reported as it is.
"""

import json
import re
from dataclasses import dataclass, field

ANY_ID = re.compile(r"GHSA(?:-[0-9a-z]{4}){3}|CVE-\d{4}-\d{4,}", re.IGNORECASE)
GHSA_ID = re.compile(r"GHSA(?:-[0-9a-z]{4}){3}", re.IGNORECASE)
CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)
FENCE = re.compile(r"\A\s*```[A-Za-z]*[ \t]*\n(.*?)\n?[ \t]*```\s*\Z", re.DOTALL)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
NULL_WORDS = {"", "none", "n/a", "null"}
SOURCES = ("github", "nvd")
MAX_CLAIMS = 40
KNOWN_FIELDS = ("abstain", "verdict", "ids", "value", "disagreement", "explanation", "claims")


def normal_id(text: str) -> str:
    cleaned = text.strip()
    if cleaned.upper().startswith("GHSA-"):
        return "GHSA-" + cleaned[5:].lower()
    return cleaned.upper()


def ids_in(text: str) -> list[str]:
    """Every advisory or CVE ID in the text, in standard form, in order of appearance."""
    return [normal_id(found) for found in ANY_ID.findall(text)]


def schema_problem(answer: object) -> str | None:
    """Says what is wrong with an answer, or None. Checks answer_schema.json by hand."""
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
    """Strip one surrounding code fence, parse the first top-level JSON object, repair nothing."""
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


# --- numbers, dates and versions as the claims write them ----------------------------------


def score_key(text: str | None) -> str | None:
    """The number in a score, to one decimal: "8.6 (High)" reads as "8.6"."""
    if text is None:
        return None
    found = re.search(r"\d+(?:\.\d+)?", text)
    return f"{float(found.group()):.1f}" if found else None


SCORE_TEXT = re.compile(r"\d+(?:\.\d+)?(?:\s*\(.*\))?")


def is_score_text(text: str) -> bool:
    """A score is a number alone, or a number and a label in brackets. "2.3.29" is a version."""
    return SCORE_TEXT.fullmatch(text.strip()) is not None


def label_key(text: str | None) -> str | None:
    if text is None or text.strip().lower() in NULL_WORDS:
        return None
    word = text.strip().lower()
    return "moderate" if word == "medium" else word


def version_key(text: str) -> tuple[str, ...]:
    """Versions that differ only in trailing zeros are the same version."""
    parts = text.strip().lower().removeprefix("v").split(".")
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return tuple(parts)


def band(score: float) -> str:
    if score == 0:
        return "none"
    if score < 4.0:
        return "low"
    if score < 7.0:
        return "medium"
    if score < 9.0:
        return "high"
    return "critical"


# --- claims ----------------------------------------------------------------------------------

# Each kind and the fields it must carry. "ghsa" and "cve" are ID formats; "id" is either; "text"
# is a non-empty string; "source" is github or nvd; "score" is text with a number, or null.
KINDS: dict[str, tuple[tuple[str, str], ...]] = {
    "package": (("record", "ghsa"), ("package", "text")),
    "alias": (("record", "ghsa"), ("cve", "cve")),
    "affects": (
        ("record", "ghsa"),
        ("package", "text"),
        ("version", "text"),
        ("affected", "bool"),
    ),  # fmt: skip
    "fixed_in": (("record", "id"), ("source", "source"), ("package", "text"), ("version", "text")),
    "severity": (("record", "ghsa"), ("label", "text")),
    "score": (("record", "id"), ("source", "source"), ("cvss3", "score")),
    "published": (("record", "id"), ("date", "date")),
    "kev": (("cve", "cve"), ("listed", "bool")),
}


@dataclass(frozen=True)
class Claim:
    index: int
    kind: str
    fields: dict = field(default_factory=dict)

    def get(self, name: str):
        return self.fields.get(name)


def _read_field(kind: str, value: object):
    """The field in standard form. Raises ValueError with what is wrong."""
    if kind in ("ghsa", "cve", "id"):
        pattern = {"ghsa": GHSA_ID, "cve": CVE_ID, "id": ANY_ID}[kind]
        if not isinstance(value, str) or not pattern.fullmatch(value.strip()):
            raise ValueError("is not an ID of the right kind")
        return normal_id(value)
    if kind == "text":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("is not text")
        return value.strip()
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError("is not true or false")
        return value
    if kind == "source":
        if not isinstance(value, str) or value.strip().lower() not in SOURCES:
            raise ValueError("is not github or nvd")
        return value.strip().lower()
    if kind == "date":
        if not isinstance(value, str) or not DATE.fullmatch(value.strip()):
            raise ValueError("is not a date written YYYY-MM-DD")
        return value.strip()
    if kind == "score":
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("is not text or null")
        if value.strip().lower() in NULL_WORDS:
            return None
        if score_key(value) is None:
            raise ValueError("holds no number")
        return value.strip()
    raise AssertionError(kind)


def read_claim(raw: object, index: int) -> Claim | str:
    """A claim in standard form, or a sentence saying why it does not fit its kind."""
    if not isinstance(raw, dict):
        return f"claim {index} is not an object"
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        return f"claim {index} has no known kind"
    fields = {}
    for name, form in KINDS[kind]:
        if name not in raw:
            return f"claim {index} ({kind}) lacks {name}"
        try:
            fields[name] = _read_field(form, raw[name])
        except ValueError as problem:
            return f"claim {index} ({kind}): {name} {problem}"
    return Claim(index, kind, fields)
