"""Deterministic citation validator (FR-14): generated citations must be a subset of the
retrieved clauses, and a "covered" decision needs a coverage clause (section 2 or 3).

The validator never trusts the model: on any violation the decision becomes needs_review and
the violation is recorded. Callers count violations *before* correction to measure how often
the model breaks the rules (the validator would otherwise hide it).
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Literal

CoverageDecision = Literal["covered", "not_covered", "needs_review"]
COVERAGE_SECTIONS = frozenset({"2", "3"})


def section_of(clause_id: str) -> str:
    return clause_id.removeprefix("CS-AUTO-").split(".")[0]


@dataclass(frozen=True)
class Validated:
    decision: CoverageDecision
    cited_clause_ids: list[str]  # only clauses that were retrieved, without duplicates
    violations: list[str] = field(default_factory=list)  # found before any correction


def validate_citations(
    decision: CoverageDecision, cited: Sequence[str], retrieved: Collection[str]
) -> Validated:
    kept = [c for c in dict.fromkeys(cited) if c in retrieved]
    violations = [f"not_retrieved:{c}" for c in dict.fromkeys(cited) if c not in retrieved]
    if decision == "covered" and not any(section_of(c) in COVERAGE_SECTIONS for c in kept):
        violations.append("covered_without_coverage_clause")
    return Validated("needs_review" if violations else decision, kept, violations)
