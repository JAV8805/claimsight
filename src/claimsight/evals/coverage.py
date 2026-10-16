"""Coverage-decision and citation metrics for the grounded coverage pipeline (L2.2b).

Coverage accuracy is scored against `evals/golden/coverage_proposals.json`: proposals pending
José's review, so the figure is provisional. Citations are scored against the decided
`expected.clause_ids`.
"""

import json
from pathlib import Path
from typing import Any

from claimsight.evals.schema import Expected, GoldenCase

PROPOSALS_PATH = Path("evals/golden/coverage_proposals.json")


def load_proposals(path: Path = PROPOSALS_PATH) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {cid: p["coverage_decision"] for cid, p in data["cases"].items()}


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def coverage_block(
    pairs: list[tuple[GoldenCase, Expected]],
    per_case: list[dict[str, Any]],
    proposals: dict[str, str],
) -> dict[str, Any]:
    """Metrics of a run. `per_case` holds the usage entries written by the coverage graph."""
    n = len(pairs)
    hits = sum(pred.coverage_decision == proposals[c.case_id] for c, pred in pairs)
    confusion: dict[str, int] = {}
    for c, pred in pairs:
        key = f"{proposals[c.case_id]} -> {pred.coverage_decision}"
        confusion[key] = confusion.get(key, 0) + 1

    cited = matched = expected = 0
    for c, pred in pairs:
        want, got = set(c.expected.clause_ids), set(pred.clause_ids)
        cited, matched, expected = cited + len(got), matched + len(got & want), expected + len(want)

    with_violation = sum(bool(u.get("violations_before")) for u in per_case)
    before = [len(u.get("cited_before_validation", [])) for u in per_case]
    invalid = [
        sum(v.startswith("not_retrieved:") for v in u.get("violations_before", []))
        for u in per_case
    ]
    latencies = [u["latency_s"] for u in per_case]
    return {
        "provisional": "coverage_accuracy is scored against coverage_proposals.json (pending)",
        "n": n,
        "coverage_accuracy": _ratio(hits, n),
        "confusion": dict(sorted(confusion.items())),
        "citation_precision": _ratio(matched, cited),
        "citation_recall": _ratio(matched, expected),
        "citation_violation_rate_before_validator": _ratio(with_violation, len(per_case)),
        "cases_with_violation_before_validator": with_violation,
        "invalid_citations_before_validator": sum(invalid),
        "citations_before_validator": sum(before),
        "decisions_changed_by_validator": sum(
            u.get("decision_before_validation") not in (None, u.get("coverage_decision"))
            for u in per_case
        ),
        "latency_s_mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "latency_s_max": max(latencies) if latencies else None,
    }
