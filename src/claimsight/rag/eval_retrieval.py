"""Retrieval eval for hybrid retrieval (FR-13). Run with `make eval-retrieval`
(needs Postgres and Ollama).

Hybrid = deterministic clause map (deductibles, duties, signal-triggered clauses) + semantic
retrieval of coverage and exclusion clauses (sections 2 to 4). Reported per chunker and per
setting (monolingual, or cross-lingual: the query language differs from the clause language):

- pure_semantic: the previous method, for comparison. Query = narrative; every expected clause
  must come from search.
- semantic: the semantic part of the hybrid. Query = claim type + narrative, search limited to
  sections 2-4, scored against the expected clauses of sections 2-4 only.
- combined: end-to-end recall of (clause map + top-k semantic) against all expected clauses.
- deterministic: exact-match rate of the clause map against the expected clauses outside
  sections 2-4 (language independent).

The claim type fed to both parts is `claimed_event`, and the map's signals come from the rules
baseline, so the LLM classifier is not in this loop yet: the cases where the narrative
contradicts the claimed event, and the prompt injection, are expected to miss.
"""

import json
import sys
from pathlib import Path
from typing import Any

from claimsight.baselines.rules import predict
from claimsight.evals.harness import load_golden
from claimsight.evals.schema import GoldenCase
from claimsight.rag import store
from claimsight.rag.chunking import CHUNKERS
from claimsight.rag.clause_map import from_prediction, is_semantic
from claimsight.rag.metrics import mean, recall_at_k, reciprocal_rank

REPORT = Path("evals/reports/retrieval.json")
KS = (3, 5)
OTHER = {"en": "es", "es": "en"}
SEMANTIC_SECTIONS = ["2", "3", "4"]


def score_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-query rows ({expected, retrieved}) into recall@k and MRR."""
    out: dict[str, Any] = {"n": len(rows)}
    for k in KS:
        out[f"recall@{k}"] = mean([recall_at_k(r["expected"], r["retrieved"], k) for r in rows])
    out["mrr"] = mean([reciprocal_rank(r["expected"], r["retrieved"]) for r in rows])
    return out


def combined_recall(expected: list[str], mapped: list[str], retrieved: list[str], k: int) -> float:
    """Recall of all expected clauses by the clause map plus the top k semantic results."""
    found = set(mapped) | set(retrieved[:k])
    return sum(e in found for e in set(expected)) / len(set(expected))


def deterministic_exact(cases: list[GoldenCase]) -> dict[str, Any]:
    """Share of cases where the clause map equals the expected non-semantic clauses."""
    misses = []
    for case in cases:
        prediction = predict(case.policy, case.inputs, case.facts)
        got = set(from_prediction(prediction, case.inputs.claimed_event))
        want = {c for c in case.expected.clause_ids if not is_semantic(c)}
        if got != want:
            misses.append(
                {"case_id": case.case_id, "expected": sorted(want), "mapped": sorted(got)}
            )
    return {
        "n": len(cases),
        "exact_match": round(1 - len(misses) / len(cases), 4),
        "misses": misses,
    }


def _groups(cases: list[GoldenCase], rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {"all": rows}
    for case, row in zip(cases, rows, strict=True):
        groups.setdefault(f"{case.language} queries", []).append(row)
    return dict(sorted(groups.items()))


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "| chunker | setting | part | queries | n | recall@3 | recall@5 | MRR |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for chunker, settings in report["results"].items():
        for setting, parts in settings.items():
            for part, groups in parts.items():
                for group, s in groups.items():
                    mrr = "n/a" if s.get("mrr") is None else f"{s['mrr']:.3f}"
                    lines.append(
                        f"| {chunker} | {setting} | {part} | {group} | {s['n']} | "
                        f"{s['recall@3']:.3f} | {s['recall@5']:.3f} | {mrr} |"
                    )
    det = report["deterministic"]
    lines.append(f"\ndeterministic clause map: exact match {det['exact_match']:.3f} (n={det['n']})")
    return "\n".join(lines)


def main() -> int:
    cases = load_golden()
    conn, embeddings = store.connect(), store.embedder()
    narratives = embeddings.embed_documents([c.inputs.narrative for c in cases])
    hybrid_queries = [f"{c.inputs.claimed_event}. {c.inputs.narrative}" for c in cases]
    hybrid_vectors = embeddings.embed_documents(hybrid_queries)
    mapped = [
        from_prediction(predict(c.policy, c.inputs, c.facts), c.inputs.claimed_event) for c in cases
    ]
    report: dict[str, Any] = {
        "embedding_model": store.EMBED_MODEL,
        "index": f"hnsw(m={store.HNSW_M}, ef_construction={store.HNSW_EF_CONSTRUCTION}) cosine",
        "labels": "expected.clause_ids in labels.json (decided)",
        "claim_type_source": "claimed_event (the LLM classifier is not in this loop)",
        "hybrid_query": "<claimed_event>. <narrative>",
        "chunks": {},
        "deterministic": deterministic_exact(cases),
        "results": {},
    }
    for chunker in CHUNKERS:
        report["chunks"][chunker] = store.ingest(conn, chunker, embeddings)
        settings: dict[str, dict[str, Any]] = {}
        for setting in ("monolingual", "cross_lingual"):
            pure, semantic, combined = [], [], []
            for case, narr_vec, hyb_vec, ids in zip(
                cases, narratives, hybrid_vectors, mapped, strict=True
            ):
                lang = case.language if setting == "monolingual" else OTHER[case.language]
                expected = case.expected.clause_ids
                sem_expected = [c for c in expected if is_semantic(c)]
                top = store.search(conn, chunker, hyb_vec, lang, max(KS), SEMANTIC_SECTIONS)
                pure.append(
                    {
                        "expected": expected,
                        "retrieved": store.search(conn, chunker, narr_vec, lang, max(KS)),
                    }
                )
                semantic.append({"expected": sem_expected, "retrieved": top})
                combined.append({f"recall@{k}": combined_recall(expected, ids, top, k) for k in KS})
            comb_groups = {}
            for group, rows in _groups(cases, combined).items():
                comb_groups[group] = {
                    "n": len(rows),
                    **{f"recall@{k}": mean([r[f"recall@{k}"] for r in rows]) for k in KS},
                    "mrr": None,
                }
            settings[setting] = {
                "pure_semantic": {g: score_rows(r) for g, r in _groups(cases, pure).items()},
                "semantic": {g: score_rows(r) for g, r in _groups(cases, semantic).items()},
                "combined": comb_groups,
            }
        report["results"][chunker] = settings
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(markdown(report))
    print(f"\nwrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
