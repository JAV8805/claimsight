"""Chunkers, metrics, corpus and proposed clause labels: offline, no Ollama and no database."""

import json
from pathlib import Path

import pytest

from claimsight.evals.harness import load_golden
from claimsight.rag.chunking import (
    chunk_by_clause,
    chunk_fixed,
    load_policy,
    parse_policy,
)
from claimsight.rag.eval_retrieval import PROPOSALS, load_proposals, score_rows
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


def test_proposed_clause_labels_cover_every_case_with_existing_clauses() -> None:
    known = {c.clause_id for c in load_policy(POLICY_DIR / "claimsight-mutual-auto-policy.en.md")}
    proposals = load_proposals()
    assert set(proposals) == {c.case_id for c in load_golden()}
    for case_id, ids in proposals.items():
        assert ids and set(ids) <= known, case_id
    doc = json.loads(PROPOSALS.read_text(encoding="utf-8"))
    assert "PROPOSED" in doc["status"]
    assert all(p["rationale"] for p in doc["cases"].values())


def test_table_name_only_accepts_known_chunkers() -> None:
    from claimsight.rag.store import table_name

    assert table_name("clause") == "policy_chunks_clause"
    assert table_name("fixed") == "policy_chunks_fixed"
    with pytest.raises(ValueError):
        table_name("x; DROP TABLE policy_chunks_clause")
