"""Chunkers, metrics, corpus and proposed clause labels: offline, no Ollama and no database."""

from pathlib import Path

import pytest

from claimsight.baselines.rules import predict
from claimsight.evals.harness import load_golden
from claimsight.rag.chunking import (
    chunk_by_clause,
    chunk_fixed,
    load_policy,
    parse_policy,
)
from claimsight.rag.clause_map import is_semantic, mapped_clause_ids
from claimsight.rag.eval_retrieval import combined_recall, deterministic_exact, score_rows
from claimsight.rag.metrics import dedupe, mean, recall_at_k, reciprocal_rank

POLICY_DIR = Path("corpus/policies")
SAMPLE = """# Title

## 1. First

### CS-AUTO-1.1 Alpha
Alpha text.

### CS-AUTO-1.2 Beta
Beta text is a bit longer than alpha.

## 2. Second

### CS-AUTO-2.1 Gamma
Gamma text.
"""


def test_parse_policy_extracts_clauses_sections_and_trims_trailing_headings() -> None:
    clauses = parse_policy(SAMPLE, "en")
    assert [c.clause_id for c in clauses] == ["CS-AUTO-1.1", "CS-AUTO-1.2", "CS-AUTO-2.1"]
    assert [c.section for c in clauses] == ["1. First", "1. First", "2. Second"]
    assert "Second" not in clauses[1].text and clauses[1].text.startswith("### CS-AUTO-1.2")
    assert all(c.language == "en" for c in clauses)


def test_clause_chunker_is_one_chunk_per_clause() -> None:
    clauses = parse_policy(SAMPLE, "en")
    chunks = chunk_by_clause(clauses)
    assert [c.clause_id for c in chunks] == [c.clause_id for c in clauses]
    assert all(c.clause_ids == (c.clause_id,) for c in chunks)


def test_fixed_chunker_overlaps_and_covers_the_text() -> None:
    clauses = parse_policy(SAMPLE, "en")
    chunks = chunk_fixed(clauses, size=40, overlap=10)
    assert len(chunks) > 1 and all(len(c.text) <= 40 for c in chunks)
    for a, b in zip(chunks, chunks[1:], strict=False):  # consecutive windows share text
        assert a.text[-5:] in b.text or b.text[:5] in a.text
    joined = " ".join(c.text for c in chunks)
    for clause in clauses:
        assert clause.clause_id in joined


def test_fixed_chunker_assigns_the_clause_with_most_characters() -> None:
    clauses = parse_policy(SAMPLE, "en")
    chunks = chunk_fixed(clauses, size=60, overlap=0)
    first = chunks[0]
    assert first.clause_id == "CS-AUTO-1.1" and "CS-AUTO-1.1" in first.clause_ids
    assert any(len(c.clause_ids) > 1 for c in chunks)  # some window straddles two clauses


def test_fixed_chunker_rejects_bad_overlap() -> None:
    with pytest.raises(ValueError):
        chunk_fixed(parse_policy(SAMPLE, "en"), size=10, overlap=10)
    assert chunk_fixed([]) == []


def test_metrics() -> None:
    expected = ["A", "B"]
    assert recall_at_k(expected, ["X", "A", "Y", "B"], 3) == 0.5
    assert recall_at_k(expected, ["X", "A", "Y", "B"], 5) == 1.0
    assert reciprocal_rank(expected, ["X", "A", "B"]) == 0.5
    assert reciprocal_rank(expected, ["X", "X", "Y"]) == 0.0
    assert reciprocal_rank(expected, ["X", "X", "A"]) == 0.5  # duplicates count once
    assert dedupe(["a", "b", "a"]) == ["a", "b"]
    assert mean([]) is None and mean([1, 0]) == 0.5
    with pytest.raises(ValueError):
        recall_at_k([], ["A"], 3)


def test_score_rows_aggregates() -> None:
    rows = [
        {"expected": ["A"], "retrieved": ["A", "B", "C"]},
        {"expected": ["A"], "retrieved": ["B", "C", "D"]},
    ]
    result = score_rows(rows)
    assert result == {"n": 2, "recall@3": 0.5, "recall@5": 0.5, "mrr": 0.5}


def test_corpus_is_fictional_bilingual_and_has_the_same_ids() -> None:
    en = load_policy(POLICY_DIR / "claimsight-mutual-auto-policy.en.md")
    es = load_policy(POLICY_DIR / "claimsight-mutual-auto-policy.es.md")
    assert 20 <= len(en) <= 30
    assert [c.clause_id for c in en] == [c.clause_id for c in es]
    assert len({c.clause_id for c in en}) == len(en)
    for path in POLICY_DIR.glob("*.md"):
        header = path.read_text(encoding="utf-8")[:600].upper()
        assert "FICTIONAL" in header or "FICTICIO" in header


def test_golden_clause_labels_are_decided_exist_and_have_a_semantic_part() -> None:
    known = {c.clause_id for c in load_policy(POLICY_DIR / "claimsight-mutual-auto-policy.en.md")}
    for case in load_golden():
        ids = case.expected.clause_ids
        assert ids and set(ids) <= known and len(set(ids)) == len(ids), case.case_id
        assert any(is_semantic(c) for c in ids), case.case_id  # something to retrieve
        assert case.notes.startswith("Decided:"), case.case_id


def test_clause_decisions_of_jose() -> None:
    by_id = {c.case_id: set(c.expected.clause_ids) for c in load_golden()}
    for case_id in ("GC-0050", "GC-0058"):  # 3.4 covers glass "whatever the cause"
        assert "CS-AUTO-4.4" not in by_id[case_id]
    for case_id in ("GC-0019", "GC-0033", "GC-0044"):  # external weather is not insured's info
        assert "CS-AUTO-7.1" not in by_id[case_id]
    assert "CS-AUTO-7.1" in by_id["GC-0003"] and "CS-AUTO-7.1" in by_id["GC-0017"]  # VIN
    assert "CS-AUTO-7.1" in by_id["GC-0009"] and "CS-AUTO-7.2" in by_id["GC-0012"]


def test_clause_map_rules() -> None:
    assert mapped_clause_ids("collision") == ["CS-AUTO-5.1"]
    assert mapped_clause_ids("glass") == ["CS-AUTO-5.3"]
    assert mapped_clause_ids("theft") == ["CS-AUTO-5.2", "CS-AUTO-6.3"]
    assert mapped_clause_ids("vandalism") == ["CS-AUTO-5.2", "CS-AUTO-6.3"]
    assert mapped_clause_ids("hail") == ["CS-AUTO-5.2"] and mapped_clause_ids("other") == []
    assert mapped_clause_ids("hail", vin_mismatch=True) == [
        "CS-AUTO-5.2",
        "CS-AUTO-1.1",
        "CS-AUTO-7.1",
    ]
    assert mapped_clause_ids("flood", vin_malformed=True)[1:] == ["CS-AUTO-6.4", "CS-AUTO-7.1"]
    assert mapped_clause_ids("collision", prompt_injection=True)[-1] == "CS-AUTO-7.2"
    both = mapped_clause_ids("collision", vin_mismatch=True, narrative_contradiction=True)
    assert both.count("CS-AUTO-7.1") == 1  # no duplicates
    assert not any(is_semantic(c) for c in mapped_clause_ids("theft", vin_mismatch=True))


def test_weather_mismatch_alone_never_cites_7_1() -> None:
    assert "CS-AUTO-7.1" not in mapped_clause_ids("hail")  # no insured inconsistency, no 7.1


def test_clause_map_reproduces_every_decided_non_semantic_label() -> None:
    """With the true claim type and signals the map must give exactly the decided 1/5/6/7 labels."""
    for case in load_golden():
        exp = case.expected
        got = mapped_clause_ids(
            exp.claim_type,
            vin_mismatch="vin_mismatch" in exp.fraud_signals,
            vin_malformed=not exp.vin_format_valid,
            narrative_contradiction=exp.claim_type != case.inputs.claimed_event,
            prompt_injection="prompt_injection" in exp.fraud_signals,
        )
        want = {c for c in exp.clause_ids if not is_semantic(c)}
        assert set(got) == want, case.case_id


def test_deterministic_part_misses_only_what_needs_the_llm() -> None:
    cases = load_golden()
    result = deterministic_exact(cases, [predict(c.policy, c.inputs, c.facts) for c in cases])
    assert {m["case_id"] for m in result["misses"]} == {"GC-0009", "GC-0012", "GC-0053"}
    assert result["exact_match"] == round(57 / 60, 4)


def test_combined_recall_unions_map_and_semantic_top_k() -> None:
    expected = ["CS-AUTO-3.5", "CS-AUTO-5.2", "CS-AUTO-7.1"]
    assert combined_recall(expected, ["CS-AUTO-5.2"], ["CS-AUTO-3.5", "X"], 3) == 2 / 3
    assert combined_recall(expected, ["CS-AUTO-5.2"], ["X", "Y", "CS-AUTO-3.5"], 2) == 1 / 3
    assert combined_recall(expected, ["CS-AUTO-5.2", "CS-AUTO-7.1"], ["CS-AUTO-3.5"], 3) == 1.0


def test_table_name_only_accepts_known_chunkers() -> None:
    from claimsight.rag.store import table_name

    assert table_name("clause") == "policy_chunks_clause"
    assert table_name("fixed") == "policy_chunks_fixed"
    with pytest.raises(ValueError):
        table_name("x; DROP TABLE policy_chunks_clause")


def test_cached_embeddings_embed_each_text_once(tmp_path) -> None:
    from claimsight.rag.embeddings import CachedEmbeddings

    class Counting:
        calls: list[list[str]] = []

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.calls.append(texts)
            return [[float(len(t))] for t in texts]

    inner, path = Counting(), tmp_path / "cache.json"
    cached = CachedEmbeddings(inner, "m", path)
    assert cached.embed_documents(["a", "bb", "a"]) == [[1.0], [2.0], [1.0]]
    assert cached.embed_query("bb") == [2.0] and inner.calls == [["a", "bb"]]  # second is a hit
    again = CachedEmbeddings(inner, "m", path)  # persisted on disk
    assert again.embed_query("a") == [1.0] and len(inner.calls) == 1
    other = CachedEmbeddings(inner, "other", path)  # a different model never shares vectors
    assert other.embed_query("a") == [1.0] and len(inner.calls) == 2
