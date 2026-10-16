"""Grounded coverage with a fake LLM and a fake retriever: CI stays offline (no Ollama, no DB)."""

from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from claimsight.agents.triage import (
    COVERAGE_PROMPT,
    CoverageOutput,
    TriageLLMOutput,
    TriagePredictor,
)
from claimsight.evals.coverage import coverage_block, load_proposals
from claimsight.evals.harness import load_golden, run
from claimsight.rag import store
from claimsight.rag.citations import section_of, validate_citations
from claimsight.rag.corpus import clauses_by_id, policy_language
from claimsight.rag.retriever import PolicyRetriever

PLAIN = TriageLLMOutput(claim_type="collision", prompt_injection_detected=False)


def _llm(output: Any, seen: list[Any] | None = None) -> RunnableLambda:
    def call(messages: Any) -> dict[str, Any]:
        if seen is not None:
            seen.append(messages)
        usage = {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}
        raw = AIMessage("", usage_metadata=usage)
        return {"raw": raw, "parsed": output}

    return RunnableLambda(call)


def _retriever(clause_ids: list[str], seen: list[str] | None = None) -> RunnableLambda:
    def call(query: str) -> list[Document]:
        if seen is not None:
            seen.append(query)
        return [
            Document(page_content=f"text of {cid}", metadata={"clause_id": cid})
            for cid in clause_ids
        ]

    return RunnableLambda(call)


def _predictor(classify: Any, coverage: Any, retrieved: list[str], seen_q: list[str] | None = None):
    retr = _retriever(retrieved, seen_q)
    return TriagePredictor(
        _llm(classify), retrievers={"en": retr, "es": retr}, coverage_llm=_llm(coverage)
    )


def _case(case_id: str):
    return next(c for c in load_golden() if c.case_id == case_id)


def test_validator_accepts_a_grounded_covered_decision() -> None:
    cited = ["CS-AUTO-2.1", "CS-AUTO-5.1"]
    result = validate_citations("covered", cited, set(cited))
    assert result.decision == "covered" and result.violations == []


def test_validator_rejects_a_citation_that_was_not_retrieved() -> None:
    result = validate_citations("covered", ["CS-AUTO-2.1", "CS-AUTO-9.9"], {"CS-AUTO-2.1"})
    assert result.decision == "needs_review"
    assert result.cited_clause_ids == ["CS-AUTO-2.1"]
    assert result.violations == ["not_retrieved:CS-AUTO-9.9"]


def test_covered_needs_a_coverage_clause_from_section_2_or_3() -> None:
    only_deductible = validate_citations("covered", ["CS-AUTO-5.1"], {"CS-AUTO-5.1"})
    assert only_deductible.violations == ["covered_without_coverage_clause"]
    assert only_deductible.decision == "needs_review"
    exclusion = validate_citations("covered", ["CS-AUTO-4.1"], {"CS-AUTO-4.1"})  # 4 is no cover
    assert exclusion.decision == "needs_review"
    assert validate_citations("not_covered", ["CS-AUTO-4.1"], {"CS-AUTO-4.1"}).violations == []
    assert validate_citations("needs_review", [], set()).decision == "needs_review"
    assert section_of("CS-AUTO-3.5") == "3"


def test_graph_retrieves_with_the_classified_type_and_validates() -> None:
    case = _case("GC-0053")  # claimed hail, narrative is a collision
    queries: list[str] = []
    seen: list[Any] = []
    out = CoverageOutput(
        coverage_decision="covered", cited_clause_ids=["CS-AUTO-2.1", "CS-AUTO-2.2", "CS-AUTO-5.1"]
    )
    predictor = TriagePredictor(
        _llm(PLAIN),
        retrievers={"en": _retriever(["CS-AUTO-2.1", "CS-AUTO-2.2"], queries)},
        coverage_llm=_llm(out, seen),
    )
    pred = predictor(case.policy, case.inputs, case.facts)
    assert queries[0].startswith("collision. ")  # classified type, not the claimed hail
    retrieved = predictor.last_usage["retrieved_clause_ids"]
    assert "CS-AUTO-5.1" in retrieved and "CS-AUTO-7.1" in retrieved  # map uses classified type
    assert "CS-AUTO-5.2" not in retrieved
    human = seen[0][1].content
    assert '<clause id="CS-AUTO-2.1">' in human and "<narrative>" in human
    assert seen[0][0].content == COVERAGE_PROMPT
    assert pred.coverage_decision == "covered" and pred.clause_ids == out.cited_clause_ids
    assert predictor.last_usage["violations_before"] == []


def test_violations_are_counted_before_the_validator_corrects() -> None:
    case = _case("GC-0004")
    bad = CoverageOutput(
        coverage_decision="covered", cited_clause_ids=["CS-AUTO-2.1", "CS-AUTO-9.9"]
    )
    predictor = _predictor(PLAIN, bad, ["CS-AUTO-2.1"])
    pred = predictor(case.policy, case.inputs, case.facts)
    usage = predictor.last_usage
    assert usage["violations_before"] == ["not_retrieved:CS-AUTO-9.9"]
    assert usage["cited_before_validation"] == ["CS-AUTO-2.1", "CS-AUTO-9.9"]
    assert usage["decision_before_validation"] == "covered"
    assert pred.coverage_decision == "needs_review"  # corrected
    assert "CS-AUTO-9.9" not in pred.clause_ids
    assert usage["input_tokens"] == 14 and usage["output_tokens"] == 6  # classify + generate


def test_generation_failure_degrades_to_needs_review() -> None:
    case = _case("GC-0004")
    predictor = _predictor(PLAIN, None, ["CS-AUTO-2.1"])
    pred = predictor(case.policy, case.inputs, case.facts)
    assert pred.coverage_decision == "needs_review" and pred.clause_ids == []
    assert predictor.last_usage["llm_ok"] is False


def test_policy_language_follows_country_and_texts_exist() -> None:
    assert policy_language(_case("GC-0002").policy) == "es"
    assert policy_language(_case("GC-0001").policy) == "en"
    assert "CS-AUTO-2.1" in clauses_by_id("es") and "CS-AUTO-2.1" in clauses_by_id("en")


def test_retriever_is_a_langchain_retriever_with_clause_metadata(monkeypatch) -> None:
    calls: list[tuple[Any, ...]] = []

    class FakeEmbeddings:
        def embed_query(self, text: str) -> list[float]:
            return [0.0, 1.0]

    def fake_search(conn, chunker, vector, language, k, sections):
        calls.append((chunker, language, k, sections))
        return [("CS-AUTO-3.5", "3. Comprehensive", "### CS-AUTO-3.5 Hail ...")]

    monkeypatch.setattr(store, "search_chunks", fake_search)
    retriever = PolicyRetriever.model_construct(
        conn=None,
        embeddings=FakeEmbeddings(),
        language="en",
        chunker="clause",
        k=5,
        sections=("2", "3", "4"),
    )
    docs = retriever.invoke("hail dents")
    assert docs[0].metadata == {
        "clause_id": "CS-AUTO-3.5",
        "language": "en",
        "section": "3. Comprehensive",
    }
    assert calls == [("clause", "en", 5, ("2", "3", "4"))]


def test_coverage_block_metrics() -> None:
    cases = load_golden()[:2]
    proposals = load_proposals()
    pairs, per_case = [], []
    for case, decision, cited, viol in (
        (cases[0], proposals[cases[0].case_id], list(cases[0].expected.clause_ids), []),
        (cases[1], "needs_review", ["CS-AUTO-9.9"], ["not_retrieved:CS-AUTO-9.9"]),
    ):
        update = {"coverage_decision": decision, "clause_ids": cited[:1] if viol else cited}
        pairs.append((case, case.expected.model_copy(update=update)))
        per_case.append(
            {
                "latency_s": 2.0,
                "violations_before": viol,
                "cited_before_validation": cited,
                "decision_before_validation": "covered",
                "coverage_decision": decision,
            }
        )
    scored = {cases[0].case_id: proposals[cases[0].case_id], cases[1].case_id: "covered"}
    block = coverage_block(pairs, per_case, scored)
    assert block["coverage_accuracy"] == 0.5
    assert block["citation_violation_rate_before_validator"] == 0.5
    assert block["invalid_citations_before_validator"] == 1
    assert block["decisions_changed_by_validator"] == 1
    assert block["latency_s_mean"] == 2.0


def test_coverage_proposals_cover_every_case_and_are_marked_provisional() -> None:
    proposals = load_proposals()
    assert set(proposals) == {c.case_id for c in load_golden()}
    assert set(proposals.values()) <= {"covered", "not_covered", "needs_review"}


def test_harness_adds_a_coverage_block_for_coverage_predictors() -> None:
    cases = load_golden()[:3]
    out = CoverageOutput(coverage_decision="covered", cited_clause_ids=["CS-AUTO-2.1"])
    predictor = _predictor(PLAIN, out, ["CS-AUTO-2.1"])
    report = run("coverage-fake", cases, predictor)
    assert report["coverage"]["n"] == 3 and "coverage_accuracy" in report["coverage"]
    assert report["cost"]["total"]["cost_usd"] == 0.0


def test_staged_predictor_replays_cached_stages_and_runs_generation(tmp_path) -> None:
    import json

    from claimsight.baselines.rules import predict
    from claimsight.evals import staged_coverage as sc

    case = _case("GC-0004")
    key = sc.case_key(case.policy, case.inputs)
    prediction = predict(case.policy, case.inputs, case.facts)
    usage = {"input_tokens": 5, "output_tokens": 2, "latency_s": 1.0, "llm_ok": True}
    (tmp_path / sc.CLASSIFY_FILE).write_text(
        json.dumps({key: {"prediction": prediction.model_dump(mode="json"), "usage": usage}})
    )
    (tmp_path / sc.RETRIEVE_FILE).write_text(
        json.dumps(
            {key: {"retrieved": {"CS-AUTO-2.1": "text", "CS-AUTO-2.2": "t"}, "retrieve_s": 0.5}}
        )
    )
    out = CoverageOutput(coverage_decision="covered", cited_clause_ids=["CS-AUTO-2.1"])
    predictor = sc.StagedCoveragePredictor(_llm(out), tmp_path)
    result = predictor(case.policy, case.inputs, case.facts)
    assert result.coverage_decision == "covered" and result.clause_ids == ["CS-AUTO-2.1"]
    assert predictor.last_usage["llm_ok"] is True
    assert predictor.last_usage["retrieve_latency_s"] == 0.5
    assert sc.load_classification([case], tmp_path)[0].claim_type == prediction.claim_type
    other = _case("GC-0005")
    try:
        sc.load_classification([other], tmp_path)
    except RuntimeError as exc:
        assert "eval-classify" in str(exc)
    else:
        raise AssertionError("an unclassified case must fail loudly")
