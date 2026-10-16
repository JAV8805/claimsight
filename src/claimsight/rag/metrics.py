"""Retrieval metrics. `retrieved` is the ranked list of clause IDs (duplicates allowed)."""

from collections.abc import Sequence


def dedupe(ranked: Sequence[str]) -> list[str]:
    """Keep the first occurrence of each clause ID: a clause counts once, at its best rank."""
    return list(dict.fromkeys(ranked))


def recall_at_k(expected: Sequence[str], retrieved: Sequence[str], k: int) -> float:
    """Share of the expected clauses found in the top k retrieved chunks."""
    if not expected:
        raise ValueError("a case without expected clauses has no recall")
    top = set(retrieved[:k])
    return sum(e in top for e in set(expected)) / len(set(expected))


def reciprocal_rank(expected: Sequence[str], retrieved: Sequence[str]) -> float:
    """1 / rank of the first expected clause among the deduplicated results; 0 if none."""
    wanted = set(expected)
    for rank, clause_id in enumerate(dedupe(retrieved), start=1):
        if clause_id in wanted:
            return 1 / rank
    return 0.0


def mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None
