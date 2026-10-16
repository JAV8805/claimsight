"""Deterministic clause map: citations that do not need search (FR-13).

Deductible and duty clauses follow from the claim type, and verification clauses from
signals; nothing in the narrative text helps to *find* them, so they are looked up, not
retrieved. Coverage and exclusion clauses (sections 2 to 4) are the job of semantic retrieval.

Proportionality rule for 7.1 (accurate information): it is cited only when the *insured's own
statements* are inconsistent (VIN mismatch, malformed VIN, narrative contradicting the claimed
event). An external signal such as a weather mismatch is not information given by the insured.
"""

from claimsight.evals.schema import ClaimType, Expected

DEDUCTIBLE: dict[str, str] = {
    "collision": "CS-AUTO-5.1",
    "theft": "CS-AUTO-5.2",
    "vandalism": "CS-AUTO-5.2",
    "hail": "CS-AUTO-5.2",
    "flood": "CS-AUTO-5.2",
    "glass": "CS-AUTO-5.3",
}
POLICE_REPORT = "CS-AUTO-6.3"
POLICE_REPORT_TYPES = frozenset({"theft", "vandalism"})
SEMANTIC_SECTIONS = frozenset({"2", "3", "4"})  # coverage and exclusions: retrieved, not mapped


def is_semantic(clause_id: str) -> bool:
    """True for clauses of sections 2 to 4 (CS-AUTO-<section>.<n>)."""
    return clause_id.removeprefix("CS-AUTO-").split(".")[0] in SEMANTIC_SECTIONS


def mapped_clause_ids(
    claim_type: ClaimType,
    *,
    vin_mismatch: bool = False,
    vin_malformed: bool = False,
    narrative_contradiction: bool = False,
    prompt_injection: bool = False,
) -> list[str]:
    """Clauses cited by rule, in a stable order, without duplicates."""
    ids: list[str] = []
    if claim_type in DEDUCTIBLE:
        ids.append(DEDUCTIBLE[claim_type])
    if claim_type in POLICE_REPORT_TYPES:
        ids.append(POLICE_REPORT)
    if vin_mismatch:
        ids += ["CS-AUTO-1.1", "CS-AUTO-7.1"]
    if vin_malformed:
        ids += ["CS-AUTO-6.4", "CS-AUTO-7.1"]
    if narrative_contradiction:
        ids.append("CS-AUTO-7.1")
    if prompt_injection:
        ids.append("CS-AUTO-7.2")
    return list(dict.fromkeys(ids))


def from_prediction(prediction: Expected, claimed_event: ClaimType) -> list[str]:
    """The map applied to a triage prediction (rules baseline or LLM pipeline)."""
    signals = set(prediction.fraud_signals)
    return mapped_clause_ids(
        prediction.claim_type,
        vin_mismatch="vin_mismatch" in signals,
        vin_malformed=not prediction.vin_format_valid,
        narrative_contradiction=prediction.claim_type != claimed_event,
        prompt_injection="prompt_injection" in signals,
    )
