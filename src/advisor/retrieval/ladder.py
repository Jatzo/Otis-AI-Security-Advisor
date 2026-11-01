"""Scoring the ladder on the dev questions, and the rule for adopting a rung.

Everything here reads the dev split only. The test questions are dropped as the file is read,
before any other work, so nothing downstream can see them.
"""

import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from advisor.retrieval.metrics import (
    all_evidence_at,
    evidence_ids,
    recall_at,
    reciprocal_rank,
)
from advisor.stats import mcnemar_p, wilson

KS = (5, 10, 20)
PRIMARY_K = 10
MIN_NET_WINS = 4
ALPHA = 0.05


@dataclass(frozen=True)
class Item:
    question_id: str
    type: str
    template: str
    query: str
    needed: frozenset[str]


def read_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_dev_items(questions_path: Path, gold_path: Path) -> tuple[list[Item], int]:
    """The answerable dev questions, and how many dev questions were left out for having no
    evidence (the ones that should be declined). Rows from any other split are dropped first."""
    questions = [q for q in read_lines(questions_path) if q["split"] == "dev"]
    gold = {g["id"]: g for g in read_lines(gold_path)}
    items = []
    for q in questions:
        needed = evidence_ids(gold[q["id"]])
        if needed:
            items.append(Item(q["id"], q["type"], q["template"], q["question"], frozenset(needed)))
    return items, len(questions) - len(items)


def score_ranking(item: Item, ranked: list[str]) -> dict:
    row = {"id": item.question_id, "type": item.type, "template": item.template}
    needed = set(item.needed)
    kev = {i for i in needed if i.startswith("kev:")}
    for k in KS:
        row[f"recall@{k}"] = recall_at(ranked, needed, k)
        row[f"all@{k}"] = all_evidence_at(ranked, needed, k)
    row["rr"] = reciprocal_rank(ranked, needed)
    row["kev_recall@10"] = recall_at(ranked, kev, 10) if kev else None
    row["impossible@5"] = len(needed) > 5
    return row


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    out = {"questions": n, "mrr": statistics.fmean(r["rr"] for r in rows) if n else 0.0}
    for k in KS:
        hits = sum(r[f"all@{k}"] for r in rows)
        out[f"all@{k}"] = {"hits": hits, "of": n, "interval": wilson(hits, n)}
        out[f"recall@{k}"] = statistics.fmean(r[f"recall@{k}"] for r in rows) if n else 0.0
    out["impossible@5"] = sum(r["impossible@5"] for r in rows)
    kev = [r["kev_recall@10"] for r in rows if r["kev_recall@10"] is not None]
    out["kev_recall@10"] = {"questions": len(kev), "mean": statistics.fmean(kev) if kev else None}
    return out


def adopt(candidate: list[bool], current: list[bool]) -> dict:
    """The adoption rule: at least MIN_NET_WINS more questions than the rung it is compared with
    on all-evidence@10, and an exact McNemar p below ALPHA."""
    gained = sum(c and not o for c, o in zip(candidate, current, strict=True))
    lost = sum(o and not c for c, o in zip(candidate, current, strict=True))
    p = mcnemar_p(gained, lost)
    return {
        "gained": gained,
        "lost": lost,
        "net": gained - lost,
        "p": p,
        "adopted": gained - lost >= MIN_NET_WINS and p < ALPHA,
    }


def pick_dense(a: list[dict], b: list[dict]) -> str:
    """The R2 against R3 fork: higher all-evidence@10, then higher recall@10, then the smaller
    model, which is B."""

    def key(rows: list[dict]) -> tuple[int, float]:
        return (
            sum(r[f"all@{PRIMARY_K}"] for r in rows),
            sum(r[f"recall@{PRIMARY_K}"] for r in rows),
        )

    return "a" if key(a) > key(b) else "b"
