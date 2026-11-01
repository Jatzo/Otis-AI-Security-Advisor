"""Builds the evaluation set: questions.jsonl, gold.jsonl, evidence/ and review.md.

Everything is chosen by a seeded sample, over facts read by make_gold.py from GitHub's REST
API and the raw NVD and KEV files. No system exists when this runs. This script imports
nothing from the advisor package.

Usage: python eval/build_questions.py
"""

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_gold as g  # noqa: E402

SEED = 20261101
EVAL = g.ROOT / "eval"
EVIDENCE = EVAL / "evidence"
PRE_CUTOFF, POST_CUTOFF = "2026-06-01", "2026-07-01"
CORPUS = set(g.PACKAGES)
MAX_USES = 2  # no advisory is the subject of more than this many questions
MAX_SET = 8  # an answer that lists IDs lists at most this many

# type, subtype, dev, test. Processed in this order: scarce kinds first.
SLOTS = [
    ("abstain", "withdrawn", 1, 5),
    ("abstain", "out_of_scope", 1, 4),
    ("abstain", "unsupported", 2, 2),
    ("abstain", "fake_ghsa", 1, 3),
    ("abstain", "fake_cve", 1, 3),
    ("abstain", "fake_package", 1, 3),
    ("abstain", "off_topic", 1, 2),
    ("disagree", "fixed_differ", 1, 4),
    ("disagree", "fixed_agree", 1, 3),
    ("disagree", "one_silent", 1, 5),
    ("disagree", "band_differ", 3, 6),
    ("disagree", "band_agree", 2, 4),
    ("multihop", "a2_kev_set", 1, 2),
    ("multihop", "a3_kev_pick", 1, 2),
    ("lookup", "fixed_desc", 1, 2),
    ("lookup", "severity_desc", 0, 2),
    ("lookup", "identify_desc", 3, 7),
    ("lookup", "kev_id", 0, 3),
    ("multihop", "a1_nvd_score", 1, 3),
    ("version", "verdict", 5, 15),
    ("version", "set", 4, 11),
    ("multihop", "b_intersect", 2, 7),
    ("multihop", "c_published", 1, 2),
    ("multihop", "c_score", 1, 2),
    ("lookup", "fixed_id", 2, 3),
    ("lookup", "severity_id", 1, 2),
    ("lookup", "map_id", 1, 3),
]
# Ecosystem and expected answer for each version question, per split.
VERDICT_PLAN = {
    "dev": [("PyPI", "yes"), ("PyPI", "no"), ("Maven", "yes"), ("Maven", "no"), ("npm", "yes")],
    "test": [("PyPI", "yes")] * 3 + [("PyPI", "no")] * 4 + [("Maven", "yes")] * 3
    + [("Maven", "no")] * 3 + [("npm", "yes"), ("npm", "no")],
}  # fmt: skip
SET_PLAN = {
    "dev": ["PyPI", "PyPI", "Maven", "npm"],
    "test": ["PyPI"] * 6 + ["Maven"] * 4 + ["npm"],
}
OUT_OF_SCOPE = [
    ("PyPI", "numpy"),
    ("PyPI", "tensorflow"),
    ("Maven", "com.fasterxml.jackson.core:jackson-databind"),
    ("npm", "moment"),
    ("Maven", "org.apache.tomcat.embed:tomcat-embed-core"),
]
FAKE_PACKAGES = [
    "flask-guardrail", "django-sentinel-core", "requestz-lite", "pyyaml-safeload",
    "aiohttp-shield", "jinja-safeview", "urllib-fortress", "pillow-secure-io",
]  # fmt: skip
OFF_TOPIC = [
    "How do I configure nginx to redirect all HTTP traffic to HTTPS?",
    "Write a short poem about autumn rain.",
    "What is a good way to learn Spanish in three months?",
]
GHSA_ALPHABET = "23456789cfghjmpqrvwx"


@dataclass
class World:
    records: dict[str, dict]
    adv: dict[str, g.Advisory]
    withdrawn: dict[str, g.Advisory]
    osv: dict[str, dict]
    nvd: dict[str, dict]
    kev: set[str]
    universe: dict[tuple[str, str], list[str]]
    jar: g.MavenJar
    paraphrases: dict[str, str]


@dataclass
class Item:
    type: str
    subtype: str
    template: str
    question: str
    answers_with: str
    gold: dict
    derivation: str
    subjects: list[str]
    ghsa: list[str] = field(default_factory=list)
    nvd: list[str] = field(default_factory=list)
    kev: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    weak: bool = False
    maven_release: bool = False
    ecosystem: str | None = None
    tags: dict = field(default_factory=dict)


def answer(abstain=False, verdict=None, ids=(), value=None, flagged=False, github=None, nvd=None):
    return {
        "abstain": abstain,
        "verdict": verdict,
        "ids": sorted(ids),
        "value": value,
        "disagreement": {"flagged": flagged, "values": {"github": github, "nvd": nvd}},
    }


def has_any_v3(nvd_record: dict) -> bool:
    """Whether the NVD record carries a CVSS v3 score of any kind, the reporter's included.
    A record with only the reporter's (Secondary) score is not used for "NVD is silent",
    because a reader could fairly call that NVD's score."""
    metrics = nvd_record.get("metrics") or {}
    return bool(metrics.get("cvssMetricV31") or metrics.get("cvssMetricV30"))


def band(score: float | None) -> str:
    if not score:
        return "none"
    return "low" if score < 4 else "medium" if score < 7 else "high" if score < 9 else "critical"


def is_final(ecosystem: str, version: str) -> bool:
    """A plain release: no pre-release, snapshot or milestone, whose place in the order is
    arguable."""
    try:
        if ecosystem == "PyPI":
            parsed = g.Version(version)
            return not (parsed.is_prerelease or parsed.is_devrelease or parsed.local)
        if ecosystem == "npm":
            return not g.semver.Version.parse(version).prerelease
    except ValueError:
        return False
    return not re.search(r"alpha|beta|rc|snapshot|milestone|\bm\d|cr\d|-b\d|-a\d", version, re.I)


def version_sort_key(ecosystem: str):
    if ecosystem == "PyPI":
        return g.Version
    if ecosystem == "npm":
        return g.semver.Version.parse
    return g.univers_maven


def load_world() -> World:
    records = g.read_cache(g.REST_CACHE)
    parsed = {k: g.parse_advisory(v) for k, v in records.items()}
    nvd = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in (g.ROOT / "data" / "raw" / "nvd").glob("CVE-*.json")
    }
    kev_path = g.ROOT / "data" / "raw" / "kev" / "known_exploited_vulnerabilities.json"
    osv = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in (g.ROOT / "data" / "raw" / "osv").glob("GHSA-*.json")
    }
    universe: dict[tuple[str, str], set[str]] = {}
    for record in osv.values():
        for entry in record.get("affected", []):
            name = g.canonical_package(entry["package"]["ecosystem"], entry["package"]["name"])
            key = (entry["package"]["ecosystem"], name)
            if key in CORPUS:
                universe.setdefault(key, set()).update(entry.get("versions") or [])
    for adv in parsed.values():
        for e in adv.ranges:  # npm has no version lists: the versions the ranges name
            if (e.ecosystem, e.package) in CORPUS and e.ecosystem == "npm":
                bounds = [v for _, v in g.parse_range(e.range_text)] + [e.first_patched or ""]
                universe.setdefault((e.ecosystem, e.package), set()).update(b for b in bounds if b)
    ordered = {}
    for key, versions in universe.items():
        usable = []
        for v in versions:
            try:
                version_sort_key(key[0])(v)
                usable.append(v)
            except ValueError:
                continue
        ordered[key] = sorted(usable, key=version_sort_key(key[0]))
    paraphrases = json.loads((EVAL / "paraphrases.json").read_text(encoding="utf-8"))["entries"]
    return World(
        records,
        {k: a for k, a in parsed.items() if not a.withdrawn_at},
        {k: a for k, a in parsed.items() if a.withdrawn_at},
        osv,
        nvd,
        g.kev_cve_ids(json.loads(kev_path.read_text(encoding="utf-8"))),
        ordered,
        g.MavenJar(),
        paraphrases,
    )


def get_status(url: str) -> tuple[int, dict | None]:
    headers = {"User-Agent": "otis-eval-gold"}
    if "api.github.com" in url and (token := os.environ.get("GITHUB_TOKEN")):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None


class Absence:
    """Checks that an invented ID or package really does not exist, and remembers the result
    in evidence/checks.json so the build can run again offline."""

    def __init__(self, path: Path, get: Callable = get_status, pause: float = 6.5) -> None:
        self.path, self.get, self.pause = path, get, pause
        self.known: dict[str, dict] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )

    def absent(self, kind: str, name: str) -> bool:
        key = f"{kind}:{name}"
        if key not in self.known:
            if kind == "ghsa":
                url = f"https://api.github.com/advisories/{name}"
            elif kind == "package":
                url = f"https://pypi.org/pypi/{name}/json"
            else:
                url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={name}"
                time.sleep(self.pause)
            status, body = self.get(url)
            gone = status == 404 or (
                kind == "cve" and status == 200 and not body["vulnerabilities"]
            )
            self.known[key] = {"absent": gone, "http_status": status, "url": url}
        return self.known[key]["absent"]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        g.write_json(self.path, self.known)


LIST_KINDS = {"set", "b_intersect", "a2_kev_set"}


def list_signature(item: "Item") -> tuple:
    """Two list questions with the same answer set add almost nothing to each other (flask
    1.1.0 and flask 2.1.2 can have the same advisories), so the second is refused."""
    if item.subtype in LIST_KINDS:
        return (item.subtype, tuple(item.gold["ids"]))
    return ()


class State:
    def __init__(self) -> None:
        self.split_of: dict[str, str] = {}
        self.uses: Counter = Counter()
        self.texts: set[str] = set()
        self.answer_sets: set[tuple] = set()
        self.items: list[tuple[str, Item]] = []
        self.answerable_test = self.post_test = 0

    def allowed(self, subjects: list[str], split: str) -> bool:
        return all(
            self.split_of.get(s, split) == split and self.uses[s] < MAX_USES for s in subjects
        )

    def take(self, item: Item, split: str, post: bool) -> None:
        for s in item.subjects:
            self.split_of[s] = split
            self.uses[s] += 1
        self.texts.add(item.question)
        self.answer_sets.add(list_signature(item))
        self.items.append((split, item))
        if split == "test" and not item.answers_with == "abstain":
            self.answerable_test += 1
            self.post_test += post


class Builder:
    def __init__(self, world: World, absence: Absence, out_of_scope: list[dict]) -> None:
        self.w, self.absence, self.out_of_scope = world, absence, out_of_scope
        self.rng = random.Random(SEED)
        self.st = State()
        self.drops: Counter = Counter()
        self.short: Counter = Counter()
        self.plans = {k: {s: list(v) for s, v in d.items()} for k, d in
                      {"verdict": VERDICT_PLAN, "set": SET_PLAN}.items()}  # fmt: skip
        self.desc_pool = sorted(world.paraphrases)
        self.fakes: dict[str, set[str]] = {"ghsa": set(), "cve": set(), "package": set()}

    # --- small helpers -----------------------------------------------------------------

    def keys(self, adv: g.Advisory) -> list[tuple[str, str]]:
        return sorted({(e.ecosystem, e.package) for e in adv.ranges} & CORPUS)

    def nvd_record(self, adv: g.Advisory) -> dict | None:
        record = self.w.nvd.get(adv.cve_id or "")
        return None if not record or record.get("notInNvd") else record

    def dates(self, adv: g.Advisory) -> list[str]:
        nvd = self.nvd_record(adv)
        return [adv.published] + ([nvd["published"]] if nvd and nvd.get("published") else [])

    def slice_of(self, ids: list[str]) -> str:
        every = [d for i in ids if i in self.w.adv for d in self.dates(self.w.adv[i])]
        if not every:
            return "none"
        if max(every) < PRE_CUTOFF:
            return "pre"
        return "post" if min(every) >= POST_CUTOFF else "boundary"

    def stale(self, ids: list[str]) -> bool:
        late = [
            self.w.adv[i].updated >= POST_CUTOFF
            for i in ids
            if i in self.w.adv and self.slice_of([i]) == "pre"
        ]
        return any(late)

    def shuffled(self, items, split: str, subject_of: Callable | None = None, answerable=True):
        items = sorted(items)
        self.rng.shuffle(items)
        if split == "test" and answerable and subject_of:
            behind = self.st.post_test < 0.28 * (self.st.answerable_test + 1)
            if behind:
                items.sort(key=lambda c: 0 if self.slice_of(subject_of(c)) == "post" else 1)
        return items

    def releases_so_far(self) -> int:
        return sum(1 for _, i in self.st.items if i.maven_release)

    def prefer_release(self, items, version_of):
        """Maven questions about a version with a RELEASE suffix test the reading the plan
        calls riskiest, so they go first until there are enough of them."""
        if self.releases_so_far() < 6:
            items.sort(key=lambda c: 0 if "release" in version_of(c).lower() else 1)
        return items

    def ident(self, adv: g.Advisory) -> str:
        return adv.cve_id if adv.cve_id and self.rng.random() < 0.5 else adv.ghsa_id

    def pick_template(self, options: list[str]) -> tuple[int, str]:
        index = self.rng.randrange(len(options))
        return index, options[index]

    def single_patched(self, adv: g.Advisory, key) -> str | None:
        fixed = {e.first_patched for e in adv.ranges if (e.ecosystem, e.package) == key}
        fixed.discard(None)
        return fixed.pop() if len(fixed) == 1 else None

    def decide(self, adv, key, version, compare=None):
        """Whether the version is affected, by two routes that must agree. None when they
        do not, or the version cannot be read; the reason is counted."""
        compare = compare or g.univers_maven_compare
        eco, pkg = key
        entries = [e for e in adv.ranges if (e.ecosystem, e.package) == key]
        osv = self.w.osv[adv.ghsa_id]
        try:
            rest = g.affected_by_any(entries, version, compare)
            ranges = g.osv_range_affected(osv, eco, pkg, version, compare)
        except (ValueError, TypeError):
            self.drops["a version could not be read by a library"] += 1
            return None
        listed = g.osv_listed_versions(osv, eco, pkg)
        in_list = None if listed is None else version in listed
        if ranges is not None and ranges != rest:
            self.drops["REST range and OSV range events disagree"] += 1
            return None
        if in_list is not None and in_list != rest:
            self.drops["REST range and OSV registry list disagree"] += 1
            return None
        return rest, in_list is None

    def make_item(self, split, item: Item) -> Item | None:
        if item.question in self.st.texts or not self.st.allowed(item.subjects, split):
            return None
        if list_signature(item) and list_signature(item) in self.st.answer_sets:
            self.drops["a list question repeated an earlier answer set"] += 1
            return None
        if not item.subtype.endswith("_desc") and set(item.subjects) & set(self.w.paraphrases):
            return None  # kept for the description lookups
        item.tags = {
            "slice": self.slice_of(item.subjects),
            "stale_risk": self.stale(item.subjects),
        }
        return item

    # --- the engine --------------------------------------------------------------------

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
        for typ, sub, n_dev, n_test in SLOTS:
            for split, n in (("dev", n_dev), ("test", n_test)):
                for _ in range(n):
                    item = dispatch[(typ, sub)](sub, split)
                    if item is None:
                        self.short[(typ, sub, split)] += 1
                        continue
                    post = item.tags["slice"] == "post"
                    self.st.take(item, split, post)

    # --- lookups -----------------------------------------------------------------------

    def l_fixed_id(self, sub, split):
        pool = [
            i for i, a in self.w.adv.items() if any(self.single_patched(a, k) for k in self.keys(a))
        ]
        for ghsa in self.shuffled(pool, split, lambda c: [c]):
            adv = self.w.adv[ghsa]
            key = next(k for k in self.keys(adv) if self.single_patched(adv, k))
            fixed = self.single_patched(adv, key)
            n, text = self.pick_template(
                [
                    "What is the first patched version of {p} for {i}?",
                    "In which version of {p} was {i} fixed?",
                    "Which release of {p} first contains the fix for {i}?",
                ]
            )
            ident = self.ident(adv)
            item = Item(
                "lookup", sub, f"L1-{'abc'[n]}", text.format(p=key[1], i=ident), "value",
                answer(value=fixed), f"GitHub REST first_patched_version for {adv.ghsa_id} ({key[1]}) is {fixed}.",
                [ghsa], [ghsa], ecosystem=key[0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def l_severity_id(self, sub, split):
        pool = [i for i, a in self.w.adv.items() if a.label]
        for ghsa in self.shuffled(pool, split, lambda c: [c]):
            adv = self.w.adv[ghsa]
            n, text = self.pick_template(
                [
                    "What severity label does GitHub give {i}?",
                    "How does GitHub rate the severity of {i}?",
                    "Which GitHub severity rating (low, moderate, high or critical) applies to {i}?",
                ]
            )
            item = Item(
                "lookup", sub, f"L2-{'abc'[n]}", text.format(i=self.ident(adv)), "value",
                answer(value=adv.label.lower()), f"GitHub REST severity for {adv.ghsa_id} is {adv.label}.",
                [ghsa], [ghsa], ecosystem=self.keys(adv)[0][0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def l_map_id(self, sub, split):
        pool = [i for i, a in self.w.adv.items() if a.cve_id]
        for ghsa in self.shuffled(pool, split, lambda c: [c]):
            adv = self.w.adv[ghsa]
            if self.rng.random() < 0.5:
                n, q, target = 0, f"Which CVE ID does {adv.ghsa_id} cover?", adv.cve_id
            else:
                n, q, target = 1, f"Which GitHub advisory covers {adv.cve_id}?", adv.ghsa_id
            item = Item(
                "lookup", sub, f"L3-{'ab'[n]}", q, "ids", answer(ids=[target]),
                f"GitHub REST pairs {adv.ghsa_id} with {adv.cve_id}.", [ghsa], [ghsa],
                ecosystem=self.keys(adv)[0][0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def l_kev_id(self, sub, split):
        want_yes = (
            sum(1 for s, i in self.st.items if i.subtype == "kev_id" and i.gold["verdict"] == "yes")
            < 1
        )
        pool = [
            i for i, a in self.w.adv.items()
            if a.cve_id and (a.cve_id in self.w.kev) == want_yes
        ]  # fmt: skip
        for ghsa in self.shuffled(pool, split, lambda c: [c]):
            adv = self.w.adv[ghsa]
            n, text = self.pick_template(
                [
                    "Is {c} on the CISA Known Exploited Vulnerabilities list?",
                    "Has CISA added {c} to its Known Exploited Vulnerabilities catalogue?",
                ]
            )
            item = Item(
                "lookup", sub, f"L4-{'ab'[n]}", text.format(c=adv.cve_id), "verdict",
                answer(verdict="yes" if want_yes else "no"),
                f"{adv.cve_id} {'is' if want_yes else 'is not'} in the raw KEV catalogue.",
                [ghsa], [ghsa], kev=[adv.cve_id] if want_yes else [], ecosystem=self.keys(adv)[0][0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def l_desc(self, sub, split):
        """Description lookups use the 15 paraphrased advisories, each once."""
        used = {s for _, i in self.st.items for s in i.subjects}
        free = [i for i in self.desc_pool if i not in used]
        need_fix = sub == "fixed_desc"
        for ghsa in self.shuffled(free, split, lambda c: [c]):
            adv = self.w.adv[ghsa]
            key = self.keys(adv)[0]
            fixed = None
            if need_fix:
                key = next((k for k in self.keys(adv) if self.single_patched(adv, k)), None)
                if key is None:
                    continue
                fixed = self.single_patched(adv, key)
            desc = self.w.paraphrases[ghsa]
            if sub == "identify_desc":
                n, text = self.pick_template(
                    ["Which advisory describes {d}?", "What is the advisory ID for {d}?"]
                )
                tpl, field_, ans = f"L5-{'ab'[n]}", "ids", answer(ids=[ghsa])
                how = f"Hand-written description of {ghsa}; its REST summary is {adv.summary!r}."
            elif sub == "fixed_desc":
                n, text = self.pick_template(
                    [
                        "In which version was {d} first fixed?",
                        "What is the first patched version for {d}?",
                    ]
                )
                tpl, field_, ans = f"L1d-{'ab'[n]}", "value", answer(value=fixed)
                how = f"Description of {ghsa}; first_patched_version is {fixed}."
            else:
                n, text = self.pick_template(
                    ["What severity label does GitHub give {d}?", "How does GitHub rate {d}?"]
                )
                tpl, field_, ans = f"L2d-{'ab'[n]}", "value", answer(value=adv.label.lower())
                how = f"Description of {ghsa}; GitHub severity is {adv.label}."
            item = Item("lookup", sub, tpl, text.format(d=desc), field_, ans, how, [ghsa], [ghsa],
                        ecosystem=key[0])  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    # --- version questions -------------------------------------------------------------

    def edges(self, adv, key) -> list[str]:
        eco = key[0]
        universe = self.w.universe.get(key, [])
        sort_key = version_sort_key(eco)
        out = []
        for fixed in sorted(
            {e.first_patched for e in adv.ranges if (e.ecosystem, e.package) == key} - {None}
        ):
            try:
                below = [u for u in universe if is_final(eco, u) and sort_key(u) < sort_key(fixed)]
            except (ValueError, TypeError):
                continue
            if below:
                out.append(below[-1])
            if is_final(eco, fixed):
                out.append(fixed)
        return out

    def v_verdict(self, sub, split):
        eco, want = self.plans["verdict"][split].pop(0)
        cands = []
        for ghsa, adv in sorted(self.w.adv.items()):
            for key in self.keys(adv):
                if key[0] != eco:
                    continue
                for version in self.edges(adv, key):
                    cands.append((ghsa, key[1], version))
        ordered = self.shuffled(cands, split, lambda c: [c[0]])
        if eco == "Maven":
            ordered = self.prefer_release(ordered, lambda c: c[2])
        for ghsa, pkg, version in ordered:
            adv = self.w.adv[ghsa]
            key = (eco, pkg)
            decided = self.decide(adv, key, version)
            if decided is None or ("yes" if decided[0] else "no") != want:
                continue
            if eco == "Maven":  # the real Maven jar has the last word
                decided = self.decide(adv, key, version, self.w.jar.compare)
                if decided is None or ("yes" if decided[0] else "no") != want:
                    self.drops["the Maven jar disagrees with univers"] += 1
                    continue
            n, text = self.pick_template(
                [
                    "Is {p} {v} affected by {i}?",
                    "Does {i} affect {p} version {v}?",
                    "Would {p} {v} be vulnerable to {i}?",
                ]
            )
            fixed = self.single_patched(adv, key)
            item = Item(
                "version", sub, f"V1-{'abc'[n]}", text.format(p=pkg, v=version, i=self.ident(adv)),
                "verdict", answer(verdict=want),
                f"{pkg} {version}: GitHub range {[e.range_text for e in adv.ranges if (e.ecosystem, e.package) == key]}"
                f" (first patched {fixed}); routes agree: {'REST, OSV ranges, OSV list' if not decided[1] else 'REST, OSV ranges'}"
                f"{', Maven jar' if eco == 'Maven' else ''}.",
                [ghsa], [ghsa], weak=decided[1], maven_release="release" in (version + str(fixed)).lower(),
                ecosystem=eco,
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def affected_set(self, key, version, compare=None):
        """Advisories for the package affecting the version, or None if any pair of routes
        disagrees for it."""
        members, weak = [], False
        for ghsa, adv in sorted(self.w.adv.items()):
            if key not in self.keys(adv):
                continue
            decided = self.decide(adv, key, version, compare)
            if decided is None:
                return None
            weak = weak or decided[1]
            if decided[0]:
                members.append(ghsa)
        return members, weak

    def set_candidates(self, eco, split):
        keys = sorted(k for k in self.w.universe if k[0] == eco)
        pairs = []
        for key in keys:
            versions = [v for v in self.w.universe[key] if is_final(eco, v)]
            newest, older = versions[-30:], versions[:-30]
            self.rng.shuffle(older)
            chosen = set(newest + older[:20])
            if eco == "Maven":
                chosen |= {v for v in older if "release" in v.lower()}
            pairs += [(key[1], v) for v in sorted(chosen)]
        ordered = self.shuffled(pairs, split)
        return self.prefer_release(ordered, lambda c: c[1]) if eco == "Maven" else ordered

    def v_set(self, sub, split):
        planned = self.plans["set"][split].pop(0)
        for eco in [planned] + [e for e in ("PyPI", "Maven", "npm") if e != planned]:
            made = self.v_set_for(sub, split, eco)
            if made:
                return made
        return None

    def v_set_for(self, sub, split, eco):
        for pkg, version in self.set_candidates(eco, split):
            key = (eco, pkg)
            quick = self.affected_set(key, version)
            if quick is None or not 1 <= len(quick[0]) <= MAX_SET:
                continue
            members, weak = quick
            if eco == "Maven":  # decide again with Maven's own jar
                members_weak = self.affected_set(key, version, self.w.jar.compare)
                if members_weak is None or not 1 <= len(members_weak[0]) <= MAX_SET:
                    continue
                members, weak = members_weak
            n, text = self.pick_template(
                [
                    "Which advisories affect {p} {v}?",
                    "List the security advisories that apply to {p} {v}.",
                    "Which known vulnerabilities, as advisory IDs, does {p} {v} have?",
                ]
            )
            item = Item(
                "version", sub, f"V2-{'abc'[n]}", text.format(p=pkg, v=version), "ids",
                answer(ids=members),
                f"Every GitHub advisory for {pkg} whose range holds {version}: {', '.join(members)}.",
                members, members, weak=weak, maven_release=eco == "Maven" and "release" in version.lower(),
                ecosystem=eco,
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    # --- multi-hop ---------------------------------------------------------------------

    def kev_advisories(self, key=None):
        out = []
        for ghsa, adv in sorted(self.w.adv.items()):
            if adv.cve_id in self.w.kev and (key is None or key in self.keys(adv)):
                out.append(ghsa)
        return out

    def m_nvd_score(self, sub, split):
        pool = [
            i for i, a in self.w.adv.items()
            if self.nvd_record(a) and g.nvd_primary_v3(self.nvd_record(a))
        ]  # fmt: skip
        for ghsa in self.shuffled(pool, split, lambda c: [c]):
            adv = self.w.adv[ghsa]
            score = g.nvd_primary_v3(self.nvd_record(adv))[0]
            n, text = self.pick_template(
                [
                    "What CVSS v3 base score does NVD give the CVE behind {i}?",
                    "What is NVD's v3 base score for the CVE that {i} covers?",
                ]
            )
            item = Item(
                "multihop", sub, f"M1-{'ab'[n]}", text.format(i=ghsa), "value",
                answer(value=f"{score:.1f}"),
                f"{ghsa} names {adv.cve_id}; the raw NVD record's Primary v3 baseScore is {score}.",
                [ghsa], [ghsa], nvd=[adv.cve_id], ecosystem=self.keys(adv)[0][0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def m_kev_set(self, sub, split):
        keys = sorted({k for i in self.kev_advisories() for k in self.keys(self.w.adv[i])})
        for key in self.shuffled(keys, split, lambda c: self.kev_advisories(c)):
            members = self.kev_advisories(key)
            if not 1 <= len(members) <= MAX_SET:
                continue
            n, text = self.pick_template(
                [
                    "Which advisories for {p} name a CVE on the CISA Known Exploited Vulnerabilities list?",
                    "Which {p} advisories involve a CVE that CISA lists as known exploited?",
                ]
            )
            item = Item(
                "multihop", sub, f"M2-{'ab'[n]}", text.format(p=key[1]), "ids", answer(ids=members),
                f"Advisories for {key[1]} whose CVE is in the raw KEV catalogue: {', '.join(members)}.",
                members, members, kev=[self.w.adv[i].cve_id for i in members], ecosystem=key[0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def m_kev_pick(self, sub, split):
        kev_all = set(self.kev_advisories())
        free = lambda i: self.st.allowed([i], split) and i not in self.w.paraphrases  # noqa: E731
        keys = sorted({k for i in kev_all for k in self.keys(self.w.adv[i])})
        for key in self.shuffled(keys, split, lambda c: self.kev_advisories(c)):
            on_kev = [i for i in self.kev_advisories(key) if free(i)]
            others = [
                i for i, a in sorted(self.w.adv.items())
                if key in self.keys(a) and i not in kev_all and free(i)
            ]  # fmt: skip
            if not on_kev or len(others) < 3:
                continue
            chosen_kev = sorted(self.rng.sample(on_kev, min(len(on_kev), self.rng.choice([1, 2]))))
            chosen = sorted(chosen_kev + self.rng.sample(others, 4 - len(chosen_kev)))
            n, text = self.pick_template(
                [
                    "Which of {l} name a CVE on the CISA Known Exploited Vulnerabilities list?",
                    "From {l}, which are linked to a CVE that CISA lists as known exploited?",
                ]
            )
            item = Item(
                "multihop", sub, f"M3-{'ab'[n]}", text.format(l=", ".join(chosen)), "ids",
                answer(ids=chosen_kev),
                f"Of the four, the CVEs in the raw KEV catalogue belong to {', '.join(chosen_kev)}.",
                chosen, chosen, kev=[self.w.adv[i].cve_id for i in chosen_kev], ecosystem=key[0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def m_intersect(self, sub, split):
        eco_cycle = ["PyPI", "Maven", "npm", "PyPI", "PyPI", "Maven", "npm"]
        eco = eco_cycle[
            len([1 for _, i in self.st.items if i.subtype == "b_intersect"]) % len(eco_cycle)
        ]
        for pkg, version in self.set_candidates(eco, split):
            key = (eco, pkg)
            quick = self.affected_set(key, version)
            if quick is None or len(quick[0]) < 2:
                continue
            by_label: dict[str, list[str]] = {}
            for i in quick[0]:
                by_label.setdefault((self.w.adv[i].label or "none").lower(), []).append(i)
            for label, members in sorted(by_label.items()):
                if (
                    label == "none"
                    or not 1 <= len(members) <= MAX_SET
                    or len(members) >= len(quick[0])
                ):
                    continue
                if eco == "Maven":
                    exact = self.affected_set(key, version, self.w.jar.compare)
                    if exact is None:
                        break
                    members = [i for i in exact[0] if (self.w.adv[i].label or "").lower() == label]
                    if not members:
                        break
                n, text = self.pick_template(
                    [
                        "Which {p} advisories affect version {v} and are rated {l} by GitHub?",
                        "Of the advisories that apply to {p} {v}, which does GitHub rate {l}?",
                    ]
                )
                item = Item(
                    "multihop", sub, f"M4-{'ab'[n]}", text.format(p=pkg, v=version, l=label), "ids",
                    answer(ids=members),
                    f"Advisories for {pkg} affecting {version} (routes agree), filtered to GitHub severity {label}: {', '.join(members)}.",
                    members, members, weak=quick[1], ecosystem=eco,
                    maven_release=eco == "Maven" and "release" in version.lower(),
                )  # fmt: skip
                made = self.make_item(split, item)
                if made:
                    return made
        return None

    def m_pair(self, sub, split):
        by_score = sub == "c_score"
        pool = sorted(
            i for i, a in self.w.adv.items() if (a.v3_score is not None if by_score else True)
        )
        self.rng.shuffle(pool)
        for a_id in pool:
            for b_id in pool:
                if a_id >= b_id:
                    continue
                a, b = self.w.adv[a_id], self.w.adv[b_id]
                if self.keys(a)[:1] != self.keys(b)[:1]:
                    continue
                if by_score and abs(a.v3_score - b.v3_score) < 0.5:
                    continue
                if (
                    not by_score
                    and abs(
                        int(a.published[:4]) * 12
                        + int(a.published[5:7])
                        - int(b.published[:4]) * 12
                        - int(b.published[5:7])
                    )
                    < 3
                ):
                    continue
                if by_score:
                    n, text = self.pick_template(
                        [
                            "Which has the higher GitHub CVSS v3 score: {a} or {b}?",
                            "Between {a} and {b}, which does GitHub score higher on CVSS v3?",
                        ]
                    )
                    win = a_id if a.v3_score > b.v3_score else b_id
                    how = f"GitHub v3 scores: {a_id} {a.v3_score}, {b_id} {b.v3_score}."
                    tpl = f"M5-{'ab'[n]}"
                else:
                    n, text = self.pick_template(
                        [
                            "Which was published first: {a} or {b}?",
                            "Between {a} and {b}, which advisory is older?",
                        ]
                    )
                    win = a_id if a.published < b.published else b_id
                    how = f"GitHub published dates: {a_id} {a.published[:10]}, {b_id} {b.published[:10]}."
                    tpl = f"M6-{'ab'[n]}"
                item = Item("multihop", sub, tpl, text.format(a=a_id, b=b_id), "ids", answer(ids=[win]),
                            how, [a_id, b_id], [a_id, b_id], ecosystem=self.keys(a)[0][0])  # fmt: skip
                made = self.make_item(split, item)
                if made:
                    return made
        return None

    # --- should-abstain ----------------------------------------------------------------

    def a_withdrawn(self, sub, split):
        pool = sorted(self.w.withdrawn)
        for ghsa in self.shuffled(pool, split, answerable=False):
            if ghsa in self.st.split_of:
                continue
            n, text = self.pick_template(
                [
                    "What versions does {i} affect?",
                    "What is the severity of {i}?",
                    "In which version was {i} fixed?",
                ]
            )
            adv = self.w.withdrawn[ghsa]
            item = Item(
                "abstain", sub, f"H1-{'abc'[n]}", text.format(i=ghsa), "abstain", answer(abstain=True),
                f"{ghsa} is withdrawn (withdrawn_at {adv.withdrawn_at[:10]}), so it is not in the corpus.",
                [ghsa], [ghsa], ecosystem=adv.ranges[0].ecosystem if adv.ranges else None,
            )  # fmt: skip
            item.tags = {"slice": "none", "stale_risk": False}
            if item.question not in self.st.texts and self.st.allowed([ghsa], split):
                return item
        return None

    def a_scope(self, sub, split):
        for record in self.out_of_scope:
            ghsa = record["ghsa_id"]
            if ghsa in self.st.split_of:
                continue
            vuln = record["vulnerabilities"][0]
            pkg = vuln["package"]["name"]
            item = Item(
                "abstain", sub, "H2-a",
                f"What is the first patched version of {pkg} for {ghsa}?", "abstain", answer(abstain=True),
                f"{ghsa} is a real GitHub-reviewed advisory for {pkg}, which is not one of the 18 packages.",
                [ghsa], [], extra={f"out_of_scope/{ghsa}.json": record},
                ecosystem=REST_TO_OSV.get(vuln["package"]["ecosystem"]),
            )  # fmt: skip
            item.tags = {"slice": "none", "stale_risk": False}
            if self.st.allowed([ghsa], split) and item.question not in self.st.texts:
                return item
        return None

    def a_unsupported(self, sub, split):
        have = [i.template for _, i in self.st.items if i.subtype == "unsupported"]
        have = [
            t for t in have if have.count(t) > min(have.count(o) for o in ("H3-a", "H3-b", "H3-c"))
        ]
        options = [
            (
                "H3-a",
                "What is the EPSS score for {c}?",
                "EPSS scores are not in GitHub advisories, NVD or KEV.",
            ),
            (
                "H3-b",
                "Is there a public Metasploit module for {c}?",
                "None of the three sources records exploit modules.",
            ),
            (
                "H3-c",
                "Which Debian package version fixed {c}?",
                "None of the three sources records Debian fixes.",
            ),
        ]
        pool = sorted(i for i, a in self.w.adv.items() if a.cve_id)
        for tpl, text, why in options:
            if tpl in have:
                continue
            for ghsa in self.shuffled(pool, split, answerable=False):
                adv = self.w.adv[ghsa]
                item = Item(
                    "abstain", sub, tpl, text.format(c=adv.cve_id), "abstain", answer(abstain=True),
                    f"{adv.cve_id} is in the corpus but the field asked for is not. {why}",
                    [ghsa], [ghsa], ecosystem=self.keys(adv)[0][0],
                )  # fmt: skip
                item.tags = {"slice": "none", "stale_risk": False}
                if self.st.allowed([ghsa], split) and item.question not in self.st.texts:
                    return item
        return None

    def a_fake(self, sub, split):
        for _ in range(30):
            if sub == "fake_ghsa":
                name = "GHSA-" + "-".join(
                    "".join(self.rng.choice(GHSA_ALPHABET) for _ in range(4)) for _ in range(3)
                )
                kind, tpl = "ghsa", "T1-a"
                text = self.rng.choice(
                    ["What is the first patched version in {n}?", "What does {n} describe?"]
                )
            elif sub == "fake_cve":
                name = f"CVE-2025-{self.rng.randrange(80000, 99999)}"
                kind, tpl = "cve", "T2-a"
                text = self.rng.choice(
                    ["What is the CVSS v3 score of {n}?", "Which package does {n} affect?"]
                )
            else:
                name = self.rng.choice(FAKE_PACKAGES)
                kind, tpl = "package", "T3-a"
                text = "Which versions of {n} are affected by known vulnerabilities?"
            if name in self.fakes[kind] or not self.absence.absent(kind, name):
                continue
            self.fakes[kind].add(name)
            item = Item(
                "abstain", sub, tpl, text.format(n=name), "abstain", answer(abstain=True),
                f"{name} does not exist: {self.absence.known[f'{kind}:{name}']['url']} returned {self.absence.known[f'{kind}:{name}']['http_status']}.",
                [], [],
            )  # fmt: skip
            item.tags = {"slice": "none", "stale_risk": False}
            if item.question not in self.st.texts:
                return item
        return None

    def a_off_topic(self, sub, split):
        used = {i.question for _, i in self.st.items}
        for text in OFF_TOPIC:
            if text not in used:
                item = Item("abstain", sub, "T4-a", text, "abstain", answer(abstain=True),
                            "Not a question about security advisories.", [], [])  # fmt: skip
                item.tags = {"slice": "none", "stale_risk": False}
                return item
        return None

    # --- sources disagree --------------------------------------------------------------

    def d_band(self, sub, split):
        want_differ = sub == "band_differ"
        pool = []
        for ghsa, adv in sorted(self.w.adv.items()):
            nvd = self.nvd_record(adv)
            n = g.nvd_primary_v3(nvd) if nvd else None
            if adv.v3_score is not None and n and (band(adv.v3_score) != band(n[0])) == want_differ:
                pool.append(ghsa)
        for ghsa in self.shuffled(pool, split, lambda c: [c]):
            adv = self.w.adv[ghsa]
            score = g.nvd_primary_v3(self.nvd_record(adv))[0]
            n, text = self.pick_template(
                [
                    "What CVSS v3 base score do GitHub and NVD each give {i}, and do they fall in the same severity band?",
                    "Do GitHub and NVD put {i} in the same severity band? Give the score each one gives.",
                ]
            )
            item = Item(
                "disagree", sub, f"D1-{'ab'[n]}", text.format(i=self.ident(adv)), "disagreement",
                answer(ids=[ghsa], flagged=want_differ, github=f"{adv.v3_score:.1f}", nvd=f"{score:.1f}"),
                f"GitHub v3 {adv.v3_score} ({band(adv.v3_score)}), NVD Primary v3 {score} ({band(score)}).",
                [ghsa], [ghsa], nvd=[adv.cve_id], ecosystem=self.keys(adv)[0][0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def fixed_pair(self, adv):
        """(GitHub's fixed version, NVD's end version) when each names exactly one plain
        dotted-numeric version and the advisory has a single range, else None."""
        nvd = self.nvd_record(adv)
        if not nvd:
            return None
        keys = [k for k in self.keys(adv)]
        entries = [e for e in adv.ranges if (e.ecosystem, e.package) in CORPUS]
        if len(keys) != 1 or len(entries) != 1 or not entries[0].first_patched:
            return None
        ends = g.nvd_end_excluding(nvd)
        numeric = re.compile(r"\d+(\.\d+)*")
        if len(ends) != 1 or not numeric.fullmatch(entries[0].first_patched):
            return None
        end = next(iter(ends))
        return (entries[0].first_patched, end) if numeric.fullmatch(end) else None

    def d_fixed(self, sub, split):
        want_differ = sub == "fixed_differ"
        pool = []
        for ghsa, adv in sorted(self.w.adv.items()):
            pair = self.fixed_pair(adv)
            if pair and (pair[0] != pair[1]) == want_differ:
                pool.append(ghsa)
        for ghsa in self.shuffled(pool, split, lambda c: [c]):
            adv = self.w.adv[ghsa]
            gh, nv = self.fixed_pair(adv)
            n, text = self.pick_template(
                [
                    "Do GitHub and NVD agree on the first fixed version for {i}? Give the version each one names.",
                    "Which version does GitHub say fixes {i}, which does NVD say, and do they agree?",
                ]
            )
            item = Item(
                "disagree", sub, f"D2-{'ab'[n]}", text.format(i=self.ident(adv)), "disagreement",
                answer(ids=[ghsa], flagged=want_differ, github=gh, nvd=nv),
                f"GitHub first_patched_version {gh}; NVD versionEndExcluding {nv}.",
                [ghsa], [ghsa], nvd=[adv.cve_id], ecosystem=self.keys(adv)[0][0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None

    def d_silent(self, sub, split):
        pool = []
        for ghsa, adv in sorted(self.w.adv.items()):
            nvd = self.w.nvd.get(adv.cve_id or "")
            if adv.v3_score is not None and nvd and not nvd.get("notInNvd") and not has_any_v3(nvd):
                pool.append(ghsa)
        for ghsa in self.shuffled(pool, split, lambda c: [c]):
            adv = self.w.adv[ghsa]
            n, text = self.pick_template(
                [
                    "What CVSS v3 score do GitHub and NVD each give {i}?",
                    "Do both GitHub and NVD score {i} with CVSS v3? Give each score.",
                ]
            )
            item = Item(
                "disagree", sub, f"D3-{'ab'[n]}", text.format(i=self.ident(adv)), "disagreement",
                answer(ids=[ghsa], flagged=True, github=f"{adv.v3_score:.1f}", nvd=None),
                f"GitHub v3 {adv.v3_score}; the raw NVD record has status {self.w.nvd[adv.cve_id].get('vulnStatus')} and no v3 score of any kind.",
                [ghsa], [ghsa], nvd=[adv.cve_id], ecosystem=self.keys(adv)[0][0],
            )  # fmt: skip
            made = self.make_item(split, item)
            if made:
                return made
        return None


REST_TO_OSV = g.REST_ECOSYSTEM


def fetch_out_of_scope(cache: Path) -> list[dict]:
    """One recent reviewed advisory for each of a few packages that are not in the corpus."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    found = []
    for ecosystem, name in OUT_OF_SCOPE:
        query = f"ecosystem={g.ECOSYSTEM_PARAMETER[ecosystem]}&affects={name}&per_page=20"
        page, _ = g.http_get(f"{g.REST_URL}?{query}")
        usable = [
            r
            for r in page
            if r.get("type") == "reviewed"
            and not r.get("withdrawn_at")
            and r.get("vulnerabilities")
        ]
        if usable:
            found.append(sorted(usable, key=lambda r: r["published_at"])[-1])
    g.write_json(cache, found)
    return found


def write_outputs(builder: Builder) -> dict:
    order = ["lookup", "version", "multihop", "abstain", "disagree"]
    prefix = {"lookup": "lk", "version": "vr", "multihop": "mh", "abstain": "ab", "disagree": "dg"}
    rows = sorted(
        builder.st.items,
        key=lambda si: (order.index(si[1].type), si[0] != "dev", si[1].subtype, si[1].question),
    )
    counters: Counter = Counter()
    questions, golds = [], []
    evidence: dict[str, bytes] = {}
    kev_ids: set[str] = set()
    for split, item in rows:
        counters[item.type] += 1
        qid = f"{prefix[item.type]}-{counters[item.type]:03d}"
        questions.append({
            "id": qid, "split": split, "type": item.type, "subtype": item.subtype,
            "template": item.template, "question": item.question, "answers_with": item.answers_with,
            "slice": item.tags["slice"], "stale_risk": item.tags["stale_risk"],
            "ecosystem": item.ecosystem, "weak_second_route": item.weak,
            "maven_release": item.maven_release, "subjects": sorted(item.subjects),
        })  # fmt: skip
        for ghsa in item.ghsa:
            evidence[f"ghsa/{ghsa}.json"] = (
                json.dumps(builder.w.records[ghsa], sort_keys=True, indent=1) + "\n"
            ).encode()
        for cve in item.nvd:
            evidence[f"nvd/{cve}.json"] = (
                g.ROOT / "data" / "raw" / "nvd" / f"{cve}.json"
            ).read_bytes()
        for path, record in item.extra.items():
            evidence[path] = (json.dumps(record, sort_keys=True, indent=1) + "\n").encode()
        kev_ids.update(item.kev)
        golds.append({
            "id": qid, "answers_with": item.answers_with, "gold": item.gold,
            "derivation": item.derivation,
            "evidence": {"ghsa": sorted(item.ghsa), "nvd": sorted(item.nvd), "kev": sorted(item.kev),
                         "out_of_scope": sorted(Path(p).stem for p in item.extra)},
        })  # fmt: skip
    for path in sorted(EVIDENCE.glob("*/*.json")):
        path.unlink()
    for rel, data in evidence.items():
        target = EVIDENCE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    g.write_json(
        EVIDENCE / "kev_entries.json",
        {
            "cves": sorted(kev_ids),
            "note": "CVEs from the raw KEV catalogue (2026.10.30) that the gold relies on.",
        },
    )
    lines = lambda rows_: "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows_)  # noqa: E731
    (EVAL / "questions.jsonl").write_text(lines(questions), encoding="utf-8", newline="\n")
    (EVAL / "gold.jsonl").write_text(lines(golds), encoding="utf-8", newline="\n")
    return {"questions": questions, "gold": golds}


def render_gold(q: dict, gold: dict) -> str:
    answer_ = gold["gold"]
    if q["answers_with"] == "abstain":
        return "ABSTAIN (the corpus does not hold it)"
    if q["answers_with"] == "ids":
        return "ids: " + ", ".join(answer_["ids"])
    if q["answers_with"] == "verdict":
        return f"verdict: {answer_['verdict']}"
    if q["answers_with"] == "value":
        return f"value: {answer_['value']}"
    d = answer_["disagreement"]
    shown = ", ".join(f"{k} {v if v is not None else 'none'}" for k, v in d["values"].items())
    return f"they {'DIFFER' if d['flagged'] else 'AGREE'}: {shown}"


def cell(text: object) -> str:
    cleaned = str(text).replace("|", "/").replace(g.raw_newline(), " ")
    return cleaned.replace("<", "&lt;").replace(">", "&gt;")


def links(ev: dict) -> str:
    out = [f"[{i}](https://github.com/advisories/{i})" for i in ev["ghsa"] + ev["out_of_scope"]]
    out += [f"[{c}](https://nvd.nist.gov/vuln/detail/{c})" for c in ev["nvd"]]
    out += [f"KEV {c}" for c in ev["kev"]]
    return " ".join(out) or "none"


def write_review(questions: list[dict], golds: list[dict], builder: Builder) -> None:
    by_id = {g_["id"]: g_ for g_ in golds}
    counts = Counter((q["type"], q["split"]) for q in questions)
    answerable = [q for q in questions if q["answers_with"] != "abstain"]
    test_answerable = [q for q in answerable if q["split"] == "test"]
    lines = [
        "# Review table for the evaluation set",
        "",
        "Generated by `eval/build_questions.py`. Read each row: is the question clear, is the gold answer right, and does the evidence link show it?",
        "",
        "## Counts",
        "",
        "| Type | Dev | Test |",
        "|---|---|---|",
    ]
    for t in ("lookup", "version", "multihop", "abstain", "disagree"):
        lines.append(f"| {t} | {counts[(t, 'dev')]} | {counts[(t, 'test')]} |")
    slices = Counter(q["slice"] for q in test_answerable)
    lines += [
        "",
        f"Total {len(questions)}. Answerable test questions: {len(test_answerable)}, of which post-cutoff {slices['post']} "
        f"({slices['post'] / len(test_answerable):.0%}), boundary month {slices['boundary']}, pre-cutoff {slices['pre']}.",
        f"Second route weaker (OSV range events only, no registry version list): {sum(q['weak_second_route'] for q in questions)} questions.",
        f"Maven RELEASE slice: {sum(q['maven_release'] for q in questions)} questions. Stale-risk (pre-cutoff, edited after): {sum(q['stale_risk'] for q in questions)}.",
        f"Candidates refused (routes disagreed, or an answer set repeated): {dict(builder.drops) or 'none'}. Short of plan: {dict(('/'.join(k), n) for k, n in builder.short.items()) or 'none'}.",
        "",
        "## Rows",
        "",
        "| id | split | kind | question | gold answer | how the gold was derived | evidence | flags |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for q in questions:
        gd = by_id[q["id"]]
        flags = [q["slice"] + "-cutoff" if q["slice"] in ("pre", "post") else q["slice"]]
        flags += ["stale-risk"] * q["stale_risk"] + ["weak-2nd-route"] * q["weak_second_route"]
        flags += ["maven-RELEASE"] * q["maven_release"]
        lines.append(
            "| "
            + " | ".join(
                cell(x)
                for x in (
                    q["id"],
                    q["split"],
                    f"{q['type']}/{q['subtype']} ({q['template']})",
                    q["question"],
                    render_gold(q, gd),
                    gd["derivation"],
                    "",
                    ", ".join(flags),
                )
            )
            + " |"
        )
        lines[-1] = lines[-1].replace("|  |", "| " + links(gd["evidence"]) + " |", 1)
    newline = g.raw_newline()
    text = newline.join(lines) + newline
    (EVAL / "review.md").write_text(text, encoding="utf-8", newline=newline)


def load_jar_cache(jar: g.MavenJar, path: Path) -> None:
    """Maven's answers for a pair of versions never change, so they are kept between builds."""
    if path.exists():
        for key, value in json.loads(path.read_text(encoding="utf-8")).items():
            left, right = key.split("|")
            jar.seen[(left, right)] = value


def save_jar_cache(jar: g.MavenJar, path: Path) -> None:
    g.write_json(path, {f"{a}|{b}": v for (a, b), v in sorted(jar.seen.items())})


def main() -> None:
    world = load_world()
    jar_cache = g.ROOT / "data" / "tools" / "jar_cache.json"
    load_jar_cache(world.jar, jar_cache)
    absence = Absence(EVIDENCE / "checks.json")
    out_of_scope = fetch_out_of_scope(EVIDENCE / "out_of_scope_cache.json")
    builder = Builder(world, absence, out_of_scope)
    builder.build()
    save_jar_cache(world.jar, jar_cache)
    absence.save()
    written = write_outputs(builder)
    write_review(written["questions"], written["gold"], builder)
    summary = Counter((q["split"], q["type"]) for q in written["questions"])
    print(json.dumps({  # noqa: T201
        "built": {f"{s}/{t}": n for (s, t), n in sorted(summary.items())},
        "shortfalls": {"/".join(k): n for k, n in builder.short.items()},
        "dropped_by_reason": dict(builder.drops),
    }, indent=1))  # fmt: skip


if __name__ == "__main__":
    main()
