"""What a visitor is shown, built from the checked reply and nothing else.

The checker reads one JSON object out of the reply and ignores any text before or after it, and
it lets extra keys through. Both come back unchanged in the checked text. So the page never shows
that text. This module reads the reply the way the checker does, keeps the known fields only, and
builds every link itself from an advisory or CVE ID. The page sets all of it with textContent.
"""

from advisor.generation.reading import ANY_ID, normal_id, read_reply

LIMIT = 4000
GITHUB = "https://github.com/advisories/"
NVD = "https://nvd.nist.gov/vuln/detail/"
UNREADABLE = "Otis could not read its own reply, so it is not giving one. Ask again."


def link_for(found: str) -> dict:
    """A link built from an ID that matched the ID pattern in full, and from nothing else."""
    base = GITHUB if found.startswith("GHSA-") else NVD
    return {"id": found, "url": base + found}


def text_or_none(value: object) -> str | None:
    return value[:LIMIT] if isinstance(value, str) else None


def view(checked_text: str) -> dict:
    answer, _ = read_reply(checked_text)
    if answer is None:
        return {"state": "unreadable", "explanation": UNREADABLE, "ids": [], "links": []}
    ids = []
    for raw in answer["ids"]:
        if ANY_ID.fullmatch(raw.strip()) and normal_id(raw) not in ids:
            ids.append(normal_id(raw))
    values = answer["disagreement"]["values"]
    return {
        "state": "declined" if answer["abstain"] else "answer",
        "verdict": answer["verdict"],
        "ids": ids,
        "value": text_or_none(answer["value"]),
        "sources_differ": answer["disagreement"]["flagged"],
        "scores": {"github": text_or_none(values["github"]), "nvd": text_or_none(values["nvd"])},
        "explanation": text_or_none(answer["explanation"]) or "",
        "links": [link_for(found) for found in ids],
    }
