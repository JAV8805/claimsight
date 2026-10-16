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

Two sources of claim type and signals are compared (`sources` in the report):
- `claimed_event`: the claimed event and the rules baseline's signals (no LLM). The cases where
  the narrative contradicts the claimed event, and the prompt injection, are expected to miss.
- `classifier`: the L2.1 triage prediction (claim type classified from the narrative, prompt
  injection detected by the LLM). Needs Ollama; skip with `--no-classifier`.
"""

import json
import sys
from pathlib import Path
from typing import Any

from claimsight.baselines.rules import predict
from claimsight.evals.harness import load_golden
from claimsight.evals.schema import Expected, GoldenCase
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


def deterministic_exact(cases: list[GoldenCase], predictions: list[Expected]) -> dict[str, Any]:
    """Share of cases where the clause map equals the expected non-semantic clauses."""
    misses = []
    for case, prediction in zip(cases, predictions, strict=True):
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
    lines = []
    for source, block in report["sources"].items():
        lines += [
            f"\n### source: {source}",
            "| chunker | setting | part | queries | n | recall@3 | recall@5 | MRR |",
            "|---|---|---|---|---:|---:|---:|---:|",
        ]
        for chunker, settings in block["results"].items():
            for setting, parts in settings.items():
                for part, groups in parts.items():
                    for group, s in groups.items():
                        mrr = "n/a" if s.get("mrr") is None else f"{s['mrr']:.3f}"
                        lines.append(
                            f"| {chunker} | {setting} | {part} | {group} | {s['n']} | "
                            f"{s['recall@3']:.3f} | {s['recall@5']:.3f} | {mrr} |"
                        )
        det = block["deterministic"]
        lines.append(f"\ndeterministic clause map: exact match {det['exact_match']:.3f}")
    for case_id, by_source in report.get("language_dependent_cases", {}).items():
        lines.append(f"{case_id}: " + "; ".join(f"{k}: {v}" for k, v in by_source.items()))
    return "\n".join(lines)


def classifier_predictions(cases: list[GoldenCase]) -> list[Expected]:
    """L2.1 triage predictions from stage 1 (`make eval-classify`): claim type from the narrative,
    prompt injection detected by the LLM. Cached so only one model is in memory at a time."""
    from claimsight.evals.staged_coverage import load_classification

    return load_classification(cases)


def evaluate_source(
    conn: Any,
    embeddings: Any,
    cases: list[GoldenCase],
    predictions: list[Expected],
    narrative_vectors: list[list[float]],
) -> dict[str, Any]:
    """Pure-semantic, semantic, combined and deterministic results for one prediction source."""
    pairs = list(zip(cases, predictions, strict=True))
    hybrid_vectors = embeddings.embed_documents(
        [f"{p.claim_type}. {c.inputs.narrative}" for c, p in pairs]
    )
    mapped = [from_prediction(p, c.inputs.claimed_event) for c, p in pairs]
    results: dict[str, Any] = {}
    per_case: dict[str, dict[str, Any]] = {}
    for chunker in CHUNKERS:
        settings: dict[str, dict[str, Any]] = {}
        for setting in ("monolingual", "cross_lingual"):
            pure, semantic, combined = [], [], []
            for case, narr_vec, hyb_vec, ids in zip(
                cases, narrative_vectors, hybrid_vectors, mapped, strict=True
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
                if chunker == "clause" and setting == "monolingual":
                    per_case[case.case_id] = {
                        "recall@5": combined[-1]["recall@5"],
                        "semantic_top5": top,
                    }
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
        results[chunker] = settings
    return {
        "deterministic": deterministic_exact(cases, predictions),
        "results": results,
        "per_case": per_case,
        "predictions": {
            c.case_id: {"claim_type": p.claim_type, "fraud_signals": p.fraud_signals}
            for c, p in zip(cases, predictions, strict=True)
        },
    }


LANGUAGE_DEPENDENT = ("GC-0009", "GC-0012", "GC-0053")


def main(argv: list[str]) -> int:
    cases = load_golden()
    conn, embeddings = store.connect(), store.embedder()
    narratives = embeddings.embed_documents([c.inputs.narrative for c in cases])
    report: dict[str, Any] = {
        "embedding_model": store.EMBED_MODEL,
        "index": f"hnsw(m={store.HNSW_M}, ef_construction={store.HNSW_EF_CONSTRUCTION}) cosine",
        "labels": "expected.clause_ids in labels.json (decided)",
        "hybrid_query": "<claim type>. <narrative>",
        "chunks": {c: store.ingest(conn, c, embeddings) for c in CHUNKERS},
        "sources": {},
    }
    baseline = [predict(c.policy, c.inputs, c.facts) for c in cases]
    report["sources"]["claimed_event"] = evaluate_source(
        conn, embeddings, cases, baseline, narratives
    )
    if "--no-classifier" not in argv:
        triage = classifier_predictions(cases)
        report["sources"]["classifier"] = evaluate_source(
            conn, embeddings, cases, triage, narratives
        )
    summary: dict[str, dict[str, str]] = {}
    for case_id in LANGUAGE_DEPENDENT:
        summary[case_id] = {}
        for source, block in report["sources"].items():
            miss = [m for m in block["deterministic"]["misses"] if m["case_id"] == case_id]
            fixed = "map exact" if not miss else f"map wrong (got {miss[0]['mapped']})"
            recall = block["per_case"][case_id]["recall@5"]
            summary[case_id][source] = f"{fixed}, combined recall@5 {recall:.2f}"
    report["language_dependent_cases"] = summary
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(markdown(report))
    print(f"\nwrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
