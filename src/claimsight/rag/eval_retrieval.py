"""Retrieval eval: query the policy corpus with each golden narrative, score against the
proposed expected clauses. Run with `make eval-retrieval` (needs Postgres and Ollama).

Settings, per chunker: monolingual (query and clauses in the same language) and cross-lingual
(query in one language, clauses in the other), each reported overall and per query language.
"""

import json
import sys
from pathlib import Path
from typing import Any

from claimsight.evals.harness import load_golden
from claimsight.rag import store
from claimsight.rag.chunking import CHUNKERS
from claimsight.rag.metrics import mean, recall_at_k, reciprocal_rank

PROPOSALS = Path("evals/golden/clause_proposals.json")
REPORT = Path("evals/reports/retrieval.json")
KS = (3, 5)
OTHER = {"en": "es", "es": "en"}


def load_proposals(path: Path = PROPOSALS) -> dict[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {cid: p["expected_clause_ids"] for cid, p in data["cases"].items()}


def score_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-query rows ({expected, retrieved}) into recall@k and MRR."""
    out: dict[str, Any] = {"n": len(rows)}
    for k in KS:
        out[f"recall@{k}"] = mean([recall_at_k(r["expected"], r["retrieved"], k) for r in rows])
    out["mrr"] = mean([reciprocal_rank(r["expected"], r["retrieved"]) for r in rows])
    return out


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "| chunker | setting | queries | n | recall@3 | recall@5 | MRR |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for chunker, settings in report["results"].items():
        for setting, groups in settings.items():
            for group, s in groups.items():
                lines.append(
                    f"| {chunker} | {setting} | {group} | {s['n']} | {s['recall@3']:.3f} | "
                    f"{s['recall@5']:.3f} | {s['mrr']:.3f} |"
                )
    return "\n".join(lines)


def main() -> int:
    cases, proposals = load_golden(), load_proposals()
    conn, embeddings = store.connect(), store.embedder()
    vectors = embeddings.embed_documents([c.inputs.narrative for c in cases])
    report: dict[str, Any] = {
        "embedding_model": store.EMBED_MODEL,
        "index": f"hnsw(m={store.HNSW_M}, ef_construction={store.HNSW_EF_CONSTRUCTION}) cosine",
        "labels": PROPOSALS.name + " (proposed, pending review)",
        "chunks": {},
        "results": {},
    }
    for chunker in CHUNKERS:
        report["chunks"][chunker] = store.ingest(conn, chunker, embeddings)
        settings: dict[str, dict[str, Any]] = {"monolingual": {}, "cross_lingual": {}}
        for setting in settings:
            rows_by_group: dict[str, list[dict[str, Any]]] = {"all": []}
            for case, vec in zip(cases, vectors, strict=True):
                target = case.language if setting == "monolingual" else OTHER[case.language]
                row = {
                    "case_id": case.case_id,
                    "expected": proposals[case.case_id],
                    "retrieved": store.search(conn, chunker, vec, target, max(KS)),
                }
                rows_by_group["all"].append(row)
                rows_by_group.setdefault(f"{case.language} queries", []).append(row)
            settings[setting] = {g: score_rows(r) for g, r in sorted(rows_by_group.items())}
            report.setdefault("misses", {}).setdefault(chunker, {})[setting] = [
                {"case_id": r["case_id"], "expected": r["expected"], "retrieved": r["retrieved"]}
                for r in rows_by_group["all"]
                if recall_at_k(r["expected"], r["retrieved"], 5) < 1
            ]
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
