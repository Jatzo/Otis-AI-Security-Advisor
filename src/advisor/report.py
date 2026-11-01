"""Counts and disagreement statistics over the store, written to docs/data-report.md.

Everything is counted over the 18 corpus packages. An OSV advisory can also list packages
in other ecosystems (RubyGems, Go and so on); those ranges are in the store but are left
out of every figure here, and their number is reported so the omission is visible.

A "pair" is one (GitHub advisory, CVE) combination where NVD has a record for the CVE.
An advisory naming two CVEs makes two pairs, and the report says so rather than
calling them advisories.
"""

import sqlite3
from collections import Counter
from collections.abc import Sequence
from statistics import mean

from advisor.packages import PACKAGES


def counts_per_package(db: sqlite3.Connection) -> list[tuple[str, str, int]]:
    found = {
        (ecosystem, package): total
        for ecosystem, package, total in db.execute(
            "SELECT ecosystem, package, COUNT(DISTINCT record_id) FROM corpus_affected"
            " GROUP BY ecosystem, package"
        )
    }
    return [(p.ecosystem, p.name, found.get(p, 0)) for p in PACKAGES]


def source_counts(db: sqlite3.Connection) -> dict[str, int]:
    def one(query: str) -> int:
        return db.execute(query).fetchone()[0]

    return {
        "GitHub advisories": one("SELECT COUNT(*) FROM records WHERE source = 'ghsa'"),
        "GitHub advisories naming a CVE": one(
            "SELECT COUNT(DISTINCT record_id) FROM aliases WHERE alias LIKE 'CVE-%'"
        ),
        "CVEs named by GitHub advisories": one(
            "SELECT COUNT(DISTINCT alias) FROM aliases WHERE alias LIKE 'CVE-%'"
        ),
        "NVD records": one("SELECT COUNT(*) FROM records WHERE source = 'nvd'"),
        "KEV entries in the catalogue": one("SELECT COUNT(*) FROM kev"),
        "Corpus ranges with no fix and no last affected version": one(
            "SELECT COUNT(*) FROM corpus_affected WHERE fixed IS NULL AND last_affected IS NULL"
        ),
        "Version ranges for packages outside the corpus (ignored)": one(
            "SELECT COUNT(*) FROM affected a WHERE NOT EXISTS ("
            " SELECT 1 FROM corpus_packages c"
            " WHERE c.ecosystem = a.ecosystem AND c.package = a.package)"
        ),
    }


def severity_band(score: float | None) -> str:
    """NVD's own bands for CVSS v3, applied to a computed score."""
    if not score:
        return "none"
    if score < 4:
        return "low"
    if score < 7:
        return "medium"
    if score < 9:
        return "high"
    return "critical"


def metrics_of(vector: str) -> str:
    """The vector without its 'CVSS:3.x/' prefix, so 3.0 and 3.1 vectors can be compared."""
    return vector.split("/", 1)[1]


def cvss_comparison(db: sqlite3.Connection) -> dict[str, object]:
    pairs = db.execute(
        "SELECT github_v3_vector, github_v3_score, github_v4_vector,"
        " nvd_v3_vector, nvd_v3_score, nvd_v4_vector FROM source_pairs"
    ).fetchall()
    shape: Counter[str] = Counter()
    versions: Counter[str] = Counter()
    v4: Counter[str] = Counter()
    same_vector = same_metrics = same_score = band_changes = 0
    score_gaps: list[float] = []
    for g_vector, g_score, g_v4, n_vector, n_score, n_v4 in pairs:
        if g_vector and n_vector:
            shape["both have a v3 score"] += 1
            versions[f"{g_vector.split('/')[0]} vs {n_vector.split('/')[0]}"] += 1
            same_vector += g_vector == n_vector
            same_metrics += metrics_of(g_vector) == metrics_of(n_vector)
            same_score += g_score == n_score
            band_changes += severity_band(g_score) != severity_band(n_score)
            if g_score != n_score:
                score_gaps.append(abs(g_score - n_score))
        elif g_vector:
            shape["GitHub has v3, NVD has no v3 score"] += 1
        elif n_vector:
            shape["NVD has v3, GitHub has no v3 score"] += 1
        else:
            shape["neither has a v3 score"] += 1
        v4["GitHub has a v4 score"] += bool(g_v4)
        v4["NVD has a Primary v4 score"] += bool(n_v4)
        v4["both"] += bool(g_v4 and n_v4)
    return {
        "pairs": len(pairs),
        "shape": shape,
        "versions": versions,
        "v4": v4,
        "same_vector": same_vector,
        "same_metrics": same_metrics,
        "same_score": same_score,
        "band_changes": band_changes,
        "mean_gap": mean(score_gaps) if score_gaps else 0.0,
        "largest_gap": max(score_gaps, default=0.0),
    }


def github_labels_vs_nvd_band(db: sqlite3.Connection) -> Counter[tuple[str, str]]:
    """GitHub's own label (a reviewer's choice) against the band of NVD's computed score."""
    rows = db.execute(
        "SELECT github_label, nvd_v3_score FROM source_pairs WHERE nvd_v3_score IS NOT NULL"
    )
    # GitHub says "moderate" where CVSS bands say "medium"; they are the same band.
    return Counter(
        ((label or "none").lower().replace("moderate", "medium"), severity_band(score))
        for label, score in rows
    )


def nvd_statuses(db: sqlite3.Connection) -> list[tuple[str, int, int]]:
    return db.execute(
        "SELECT status, COUNT(*), SUM(cvss3_vector IS NULL) FROM records"
        " WHERE source = 'nvd' GROUP BY status ORDER BY COUNT(*) DESC"
    ).fetchall()


def why_no_v3(db: sqlite3.Connection) -> list[tuple[str, int]]:
    return db.execute(
        "SELECT no_v3_reason, COUNT(*) FROM records WHERE no_v3_reason IS NOT NULL"
        " GROUP BY no_v3_reason ORDER BY COUNT(*) DESC"
    ).fetchall()


def kev_hits(db: sqlite3.Connection) -> tuple[int, list[tuple[str, str, int]]]:
    """GitHub advisories with a CVE on KEV (through record_cves), and the split by package."""
    total = db.execute(
        "SELECT COUNT(DISTINCT rc.record_id) FROM record_cves rc"
        " JOIN kev USING (cve_id) JOIN records r ON r.record_id = rc.record_id"
        " WHERE r.source = 'ghsa'"
    ).fetchone()[0]
    by_package = db.execute(
        "SELECT ecosystem, package, COUNT(DISTINCT record_id) FROM corpus_affected"
        " JOIN record_cves USING (record_id) JOIN kev USING (cve_id)"
        " GROUP BY ecosystem, package ORDER BY COUNT(DISTINCT record_id) DESC, package"
    ).fetchall()
    return total, by_package


def fixed_version_strings(db: sqlite3.Connection) -> Counter[str]:
    """GitHub's 'fixed' versions against NVD's 'versionEndExcluding', compared as plain text.

    This is a first look at range disagreement, not a verdict: strings that differ may
    still mean the same version, and the version-aware comparison comes with the comparators.
    """
    github: dict[str, set[str]] = {}
    for record_id, fixed in db.execute(
        "SELECT record_id, fixed FROM corpus_affected WHERE fixed IS NOT NULL"
    ):
        github.setdefault(record_id, set()).add(fixed)
    nvd: dict[str, set[str]] = {}
    for record_id, end in db.execute(
        "SELECT record_id, version_end_excluding FROM cpe_matches"
        " WHERE vulnerable = 1 AND version_end_excluding IS NOT NULL"
    ):
        nvd.setdefault(record_id, set()).add(end)
    result: Counter[str] = Counter()
    for record_id, cve_id in db.execute("SELECT ghsa_id, cve_id FROM source_pairs"):
        ours, theirs = github.get(record_id, set()), nvd.get(cve_id, set())
        if not ours:
            result["GitHub names no fixed version"] += 1
        elif not theirs:
            result["NVD names no end-excluding version"] += 1
        elif ours == theirs:
            result["same set of fixed versions"] += 1
        elif ours < theirs:
            result["GitHub's versions are a subset of NVD's"] += 1
        elif theirs < ours:
            result["NVD's versions are a subset of GitHub's"] += 1
        elif ours & theirs:
            result["the sets overlap but neither contains the other"] += 1
        else:
            result["no version in common"] += 1
    return result


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    def cell(value: object) -> str:
        # Some of this text comes from upstream feeds, so it must not carry markup or break a row.
        text = str(value).replace("<", "&lt;").replace(">", "&gt;")
        return text.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def render(db: sqlite3.Connection, snapshot_id: str) -> str:
    cvss = cvss_comparison(db)
    kev_total, kev_by_package = kev_hits(db)
    shape: Counter[str] = cvss["shape"]  # type: ignore[assignment]
    versions: Counter[str] = cvss["versions"]  # type: ignore[assignment]
    v4: Counter[str] = cvss["v4"]  # type: ignore[assignment]
    both = shape["both have a v3 score"]
    sections = [
        "# Data report",
        f"Snapshot `{snapshot_id}`, generated by `python -m advisor.ingest report`.",
        "## Records per source",
        table(["Count", "Value"], list(source_counts(db).items())),
        "## GitHub advisories per package",
        table(["Ecosystem", "Package", "Advisories"], counts_per_package(db)),
        "## CVSS v3: GitHub against NVD",
        f"{cvss['pairs']} (advisory, CVE) pairs where NVD has a record. Two CVEs make two pairs.",
        table(["Pairs", "Count"], sorted(shape.items(), key=lambda item: -item[1])),
        "CVSS v4, counted apart from the v3 figures:",
        table(["v4 scores", "Pairs"], list(v4.items())),
        f"Of the {both} pairs with a v3 score on both sides:",
        table(["Version pair", "Count"], sorted(versions.items(), key=lambda item: -item[1])),
        table(
            ["Measure", "Count"],
            [
                ("identical vector strings", cvss["same_vector"]),
                ("same metrics (prefix may differ)", cvss["same_metrics"]),
                ("same computed score", cvss["same_score"]),
                ("different severity band", cvss["band_changes"]),
                ("mean score gap where scores differ", f"{cvss['mean_gap']:.2f}"),
                ("largest score gap", f"{cvss['largest_gap']:.1f}"),
            ],
        ),
        "Scores are computed from each vector by the same library. An identical vector may mean"
        " two independent assessments or one copied from the other; the data cannot say which.",
        "## GitHub's label against NVD's computed band",
        table(
            ["GitHub label", "NVD band", "Pairs"],
            [(a, b, n) for (a, b), n in sorted(github_labels_vs_nvd_band(db).items())],
        ),
        "## NVD analysis status",
        table(["Status", "Records", "With no Primary v3 score"], nvd_statuses(db)),
        "Why NVD has no Primary v3 score:",
        table(["Reason", "Records"], why_no_v3(db)),
        "## CISA KEV",
        f"{kev_total} GitHub advisories name a CVE that is on KEV (through `record_cves`).",
        table(["Ecosystem", "Package", "Advisories on KEV"], kev_by_package),
        "## Fixed versions, compared as text",
        "GitHub's `fixed` against NVD's `versionEndExcluding`, per pair. A first look only.",
        table(
            ["Relation", "Pairs"],
            sorted(fixed_version_strings(db).items(), key=lambda item: -item[1]),
        ),
    ]
    return "\n\n".join(sections) + "\n"
