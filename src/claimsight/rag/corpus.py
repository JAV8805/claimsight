"""Policy clause texts by language, read straight from the corpus files (no database)."""

from functools import cache

from claimsight.evals.schema import PolicyRecord
from claimsight.rag.chunking import Clause, load_policy
from claimsight.rag.store import POLICY_DIR


@cache
def clauses_by_id(language: str) -> dict[str, Clause]:
    path = POLICY_DIR / f"claimsight-mutual-auto-policy.{language}.md"
    return {c.clause_id: c for c in load_policy(path)}


def policy_language(policy: PolicyRecord) -> str:
    """The policy wording language follows the policy's country (CO: Spanish, otherwise English)."""
    return "es" if policy.country == "CO" else "en"
