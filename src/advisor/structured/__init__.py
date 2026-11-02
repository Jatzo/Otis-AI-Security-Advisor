"""Row S: structured lookups, no model.

Code reads a question's form and answers it from the store. It is the comparison row from ADR 0001:
if a database query can answer a question, the full system has to match it or explain why not.

It reads the question's wording (the templates the question builder uses, written out here by hand)
and never the gold. It does not import the builder and holds none of the lists the should-abstain
questions were made from; whether to decline comes from the store and from the scope in
eval/rules.md section 2: an ID the store does not hold, a package outside the 18, a form it does not
read. The hand-paraphrased descriptions of an advisory ("the Django flaw where...") are not read at
all, so they are declined.
"""

import re
import sqlite3

from advisor.generation.facts import Facts, canonical_package
from advisor.generation.reading import band, normal_id, version_key
from advisor.versions import UnparseableVersion, comparator, is_affected

GHSA = r"GHSA(?:-[0-9a-z]{4}){3}"
CVE = r"CVE-\d{4}-\d{4,}"
ANY = rf"(?:{GHSA}|{CVE})"
PKG = r"(?P<p>[A-Za-z0-9_.:-]+)"
VER = r"(?P<v>[^\s?]+)"
ID = rf"(?P<i>{ANY})"

# Each form is the wording of one template, matched in full.
FORMS: list[tuple[str, str]] = [
    ("fixed", rf"What is the first patched version of {PKG} for {ID}\?"),
    ("fixed", rf"In which version of {PKG} was {ID} fixed\?"),
    ("fixed", rf"Which release of {PKG} first contains the fix for {ID}\?"),
    ("severity", rf"What severity label does GitHub give {ID}\?"),
    ("severity", rf"How does GitHub rate the severity of {ID}\?"),
    ("severity", rf"Which GitHub severity rating \(low, moderate, high or critical\) applies to {ID}\?"),
    ("map_cve", rf"Which CVE ID does (?P<i>{GHSA}) cover\?"),
    ("map_ghsa", rf"Which GitHub advisory covers (?P<i>{CVE})\?"),
    ("kev_id", rf"Is (?P<i>{CVE}) on the CISA Known Exploited Vulnerabilities list\?"),
    ("kev_id", rf"Has CISA added (?P<i>{CVE}) to its Known Exploited Vulnerabilities catalogue\?"),
    ("verdict", rf"Is {PKG} {VER} affected by {ID}\?"),
    ("verdict", rf"Does {ID} affect {PKG} version {VER}\?"),
    ("verdict", rf"Would {PKG} {VER} be vulnerable to {ID}\?"),
    ("set", rf"Which advisories affect {PKG} {VER}\?"),
    ("set", rf"List the security advisories that apply to {PKG} {VER}\."),
    ("set", rf"Which known vulnerabilities, as advisory IDs, does {PKG} {VER} have\?"),
    ("nvd_score", rf"What CVSS v3 base score does NVD give the CVE behind {ID}\?"),
    ("nvd_score", rf"What is NVD's v3 base score for the CVE that {ID} covers\?"),
    ("kev_set", rf"Which advisories for {PKG} name a CVE on the CISA Known Exploited Vulnerabilities list\?"),
    ("kev_set", rf"Which {PKG} advisories involve a CVE that CISA lists as known exploited\?"),
    ("kev_pick", r"Which of (?P<l>.+) name a CVE on the CISA Known Exploited Vulnerabilities list\?"),
    ("kev_pick", r"From (?P<l>.+), which are linked to a CVE that CISA lists as known exploited\?"),
    ("intersect", rf"Which {PKG} advisories affect version {VER} and are rated (?P<lab>\w+) by GitHub\?"),
    ("intersect", rf"Of the advisories that apply to {PKG} {VER}, which does GitHub rate (?P<lab>\w+)\?"),
    ("higher", rf"Which has the higher GitHub CVSS v3 score: (?P<a>{ANY}) or (?P<b>{ANY})\?"),
    ("higher", rf"Between (?P<a>{ANY}) and (?P<b>{ANY}), which does GitHub score higher on CVSS v3\?"),
    ("older", rf"Which was published first: (?P<a>{ANY}) or (?P<b>{ANY})\?"),
    ("older", rf"Between (?P<a>{ANY}) and (?P<b>{ANY}), which advisory is older\?"),
    ("band", rf"What CVSS v3 base score do GitHub and NVD each give {ID}, and do they fall in the same severity band\?"),
    ("band", rf"Do GitHub and NVD put {ID} in the same severity band\? Give the score each one gives\."),
    ("fixed_pair", rf"Do GitHub and NVD agree on the first fixed version for {ID}\? Give the version each one names\."),
    ("fixed_pair", rf"Which version does GitHub say fixes {ID}, which does NVD say, and do they agree\?"),
    ("silent", rf"What CVSS v3 score do GitHub and NVD each give {ID}\?"),
    ("silent", rf"Do both GitHub and NVD score {ID} with CVSS v3\? Give each score\."),
]  # fmt: skip
COMPILED = [(name, re.compile(pattern)) for name, pattern in FORMS]


def reply(**fields) -> dict:
    body = {
        "abstain": False, "verdict": None, "ids": [], "value": None,
        "disagreement": {"flagged": False, "values": {"github": None, "nvd": None}},
        "explanation": "Looked up in the store.",
    }  # fmt: skip
    return {**body, **fields}


def declined(why: str) -> dict:
    return reply(abstain=True, explanation=why)


class Lookups:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db
        self.facts = Facts(db)

    # --- the store, one fact at a time -----------------------------------------------------

    def ghsas_for(self, found: str) -> list[str]:
        """The advisories an ID names: itself for a GHSA ID the store holds, the advisories that
        list it as an alias for a CVE."""
        found = normal_id(found)
        if found.startswith("GHSA-"):
            row = self.db.execute(
                "SELECT record_id FROM records WHERE record_id = ? AND source = 'ghsa'", (found,)
            ).fetchone()
            return [row[0]] if row else []
        rows = self.db.execute(
            "SELECT DISTINCT a.record_id FROM aliases a JOIN records r"
            " ON r.record_id = a.record_id AND r.source = 'ghsa' WHERE a.alias = ? ORDER BY 1",
            (found,),
        )
        return [r[0] for r in rows]

    def cves_of(self, ghsa: str) -> list[str]:
        return sorted(c for c in self.facts.aliases_of(ghsa) if c.startswith("CVE-"))

    def github(self, ghsa: str) -> dict:
        return self.facts.record(ghsa, "ghsa") or {}

    def nvd_score(self, cve: str) -> float | None:
        return (self.facts.record(cve, "nvd") or {}).get("cvss3_score")

    def packages(self, ghsa: str) -> set[str]:
        return self.facts.packages_of(ghsa)

    def one(self, found: str) -> str | None:
        """The single advisory an ID names, or None when it names none or several."""
        found_ids = self.ghsas_for(found)
        return found_ids[0] if len(found_ids) == 1 else None

    def affected(self, ghsa: str, package: str, version: str) -> bool | None:
        """Whether the version is in the advisory's ranges for the package, or None when the code
        cannot tell (a version it cannot order, ranges of mixed kinds)."""
        rows = self.facts.spans(ghsa, package)
        if not rows:
            return False
        kinds = {(eco, kind) for eco, kind, *_ in rows}
        if len(kinds) > 1:
            return None
        (eco, kind) = next(iter(kinds))
        try:
            return is_affected(eco, kind, version, [tuple(r[2:]) for r in rows])
        except (UnparseableVersion, ValueError):
            return None

    def advisories_affecting(self, package: str, version: str) -> list[str] | None:
        rows = self.db.execute(
            "SELECT DISTINCT record_id FROM corpus_affected WHERE package = ? ORDER BY 1",
            (package,),
        )
        found = []
        for (ghsa,) in rows:
            verdict = self.affected(ghsa, package, version)
            if verdict is None:
                return None
            if verdict:
                found.append(ghsa)
        return found

    def first_fixed(self, ghsa: str, package: str) -> str | None:
        fixed = sorted({r[3] for r in self.facts.spans(ghsa, package) if r[3]})
        if not fixed:
            return None
        rows = self.facts.spans(ghsa, package)
        eco, kind = rows[0][0], rows[0][1]
        try:
            order = comparator(eco, kind)
            lowest = fixed[0]
            for version in fixed[1:]:
                if order(version, lowest) < 0:
                    lowest = version
            return lowest
        except (UnparseableVersion, ValueError):
            return fixed[0]

    def in_kev(self, ghsa: str) -> bool:
        return any(self.facts.in_kev(cve) for cve in self.cves_of(ghsa))

    # --- answering ---------------------------------------------------------------------------

    def answer(self, question: str) -> dict:
        for name, pattern in COMPILED:
            match = pattern.fullmatch(question.strip())
            if match:
                return getattr(self, f"form_{name}")(match.groupdict())
        return declined("The question is not in a form that can be looked up.")

    def package(self, found: dict) -> str | None:
        return canonical_package(found["p"])

    def form_fixed(self, g: dict) -> dict:
        package, ghsa = self.package(g), self.one(g["i"])
        if package is None or ghsa is None:
            return declined("No advisory or package in the store matches.")
        fixed = self.first_fixed(ghsa, package)
        return reply(value=fixed) if fixed else declined("The advisory names no fixed version.")

    def form_severity(self, g: dict) -> dict:
        ghsa = self.one(g["i"])
        label = (self.github(ghsa).get("severity") or "").lower() if ghsa else ""
        return reply(value=label) if label else declined("No severity label is held.")

    def form_map_cve(self, g: dict) -> dict:
        ghsa = self.one(g["i"])
        cves = self.cves_of(ghsa) if ghsa else []
        return reply(ids=cves) if cves else declined("No CVE is listed for that advisory.")

    def form_map_ghsa(self, g: dict) -> dict:
        found = self.ghsas_for(g["i"])
        return reply(ids=found) if found else declined("No advisory names that CVE.")

    def form_kev_id(self, g: dict) -> dict:
        if not self.facts.holds_id(normal_id(g["i"])):
            return declined("The store does not hold that CVE.")
        return reply(verdict="yes" if self.facts.in_kev(normal_id(g["i"])) else "no")

    def form_verdict(self, g: dict) -> dict:
        package, ghsa = self.package(g), self.one(g["i"])
        if package is None or ghsa is None:
            return declined("No advisory or package in the store matches.")
        verdict = self.affected(ghsa, package, g["v"])
        if verdict is None:
            return declined("The version cannot be ordered against the ranges.")
        return reply(verdict="yes" if verdict else "no")

    def form_set(self, g: dict) -> dict:
        package = self.package(g)
        found = self.advisories_affecting(package, g["v"]) if package else None
        return reply(ids=found) if found is not None else declined("The version cannot be ordered.")

    def form_nvd_score(self, g: dict) -> dict:
        ghsa = self.one(g["i"])
        scores = [self.nvd_score(c) for c in self.cves_of(ghsa)] if ghsa else []
        scores = [s for s in scores if s is not None]
        if len(scores) != 1:
            return declined("NVD holds no single v3 score for it.")
        return reply(value=f"{scores[0]:.1f}")

    def form_kev_set(self, g: dict) -> dict:
        package = self.package(g)
        if package is None:
            return declined("That is not one of the packages.")
        rows = self.db.execute(
            "SELECT DISTINCT record_id FROM corpus_affected WHERE package = ? ORDER BY 1",
            (package,),
        )
        return reply(ids=[ghsa for (ghsa,) in rows if self.in_kev(ghsa)])

    def form_kev_pick(self, g: dict) -> dict:
        listed = re.findall(GHSA, g["l"])
        return reply(ids=[normal_id(i) for i in listed if self.in_kev(normal_id(i))])

    def form_intersect(self, g: dict) -> dict:
        package = self.package(g)
        found = self.advisories_affecting(package, g["v"]) if package else None
        if found is None:
            return declined("The version cannot be ordered.")
        label = g["lab"].lower()
        return reply(
            ids=[x for x in found if (self.github(x).get("severity") or "").lower() == label]
        )

    def form_higher(self, g: dict) -> dict:
        first, second = self.one(g["a"]), self.one(g["b"])
        scores = [self.github(x).get("cvss3_score") if x else None for x in (first, second)]
        if None in scores or scores[0] == scores[1]:
            return declined("The two scores cannot be ranked.")
        return reply(ids=[first if scores[0] > scores[1] else second])

    def form_older(self, g: dict) -> dict:
        first, second = self.one(g["a"]), self.one(g["b"])
        dates = [self.github(x).get("published") if x else None for x in (first, second)]
        if None in dates or dates[0] == dates[1]:
            return declined("The two dates cannot be ranked.")
        return reply(ids=[first if dates[0] < dates[1] else second])

    def scores(self, found: str) -> tuple[float | None, float | None] | None:
        ghsa = self.one(found)
        if ghsa is None:
            return None
        nvd = [s for s in (self.nvd_score(c) for c in self.cves_of(ghsa)) if s is not None]
        return self.github(ghsa).get("cvss3_score"), (nvd[0] if len(nvd) == 1 else None)

    def form_band(self, g: dict) -> dict:
        both = self.scores(g["i"])
        if both is None or both[0] is None:
            return declined("GitHub holds no v3 score for it.")
        github, nvd = both
        flagged = nvd is None or band(github) != band(nvd)
        values = {"github": f"{github:.1f}", "nvd": None if nvd is None else f"{nvd:.1f}"}
        return reply(disagreement={"flagged": flagged, "values": values})

    form_silent = form_band

    def form_fixed_pair(self, g: dict) -> dict:
        ghsa = self.one(g["i"])
        if ghsa is None:
            return declined("No single advisory matches.")
        packages = sorted(self.packages(ghsa))
        github = self.first_fixed(ghsa, packages[0]) if len(packages) == 1 else None
        ends: list[str] = []
        for cve in self.cves_of(ghsa):
            ends += self.facts.nvd_end_excluding(cve) or []
        nvd = sorted(set(ends))
        if github is None or not nvd:
            return declined("One of the two sources names no fixed version.")
        shared = version_key(github) in {version_key(v) for v in nvd}
        values = {"github": github, "nvd": ", ".join(nvd)}
        return reply(disagreement={"flagged": not shared, "values": values})
