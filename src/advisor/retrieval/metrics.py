"""Scoring a ranked list of unit ids against a question's gold evidence."""


def evidence_ids(gold_row: dict) -> set[str]:
    """The namespaced ids a question needs. Matching is exact: a CVE's NVD unit does not stand in
    for its advisory, and the other way round."""
    evidence = gold_row["evidence"]
    return (
        {f"ghsa:{i}" for i in evidence["ghsa"]}
        | {f"nvd:{i}" for i in evidence["nvd"]}
        | {f"kev:{i}" for i in evidence["kev"]}
    )


def recall_at(ranked: list[str], needed: set[str], k: int) -> float:
    return len(needed & set(ranked[:k])) / len(needed)


def all_evidence_at(ranked: list[str], needed: set[str], k: int) -> bool:
    return needed <= set(ranked[:k])


def reciprocal_rank(ranked: list[str], needed: set[str]) -> float:
    for rank, unit_id in enumerate(ranked, start=1):
        if unit_id in needed:
            return 1.0 / rank
    return 0.0
