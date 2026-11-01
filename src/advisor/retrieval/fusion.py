"""Reciprocal rank fusion: joins ranked lists without comparing their scores."""


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Each list gives an item 1 / (k + rank). Items are ordered by the sum, ties by id."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda item: (-scores[item], item))
