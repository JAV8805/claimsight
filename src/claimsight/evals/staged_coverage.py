"""Staged coverage eval: one model in memory at a time.

A laptop with 8 GB of RAM cannot hold the 7B chat model and the embedding model together (the
machine froze and Ollama was killed by the OOM killer). The pipeline is therefore run in three
stages that communicate through small cache files under `.cache/claimsight/stages/`:

  1. classify  (chat model)      triage prediction per case: claim type and signals
  2. retrieve  (embedding model) clauses per case, from the *classified* type and signals
  3. generate  (chat model)      coverage decision + citations, validated deterministically

Stage 3 writes `evals/reports/coverage-<model>.json` through the normal harness. Between stages
the model of the previous stage is unloaded (`ollama stop`, done by the Makefile, and again here
through the API as a safety net). Each stage is resumable: finished cases are kept in the cache.

Usage: python -m claimsight.evals.staged_coverage classify|retrieve|generate [--model M]
"""

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from claimsight.agents.triage import (
    DEFAULT_MODEL,
    CoverageOutput,
    build_generation_graph,
    make_llm,
    make_predictor,
)
from claimsight.evals.harness import load_golden, report_name, run, write_report
from claimsight.evals.schema import CaseFacts, ClaimInput, Expected, GoldenCase, PolicyRecord
from claimsight.rag.embeddings import unload_model

STAGES_DIR = Path(".cache/claimsight/stages")
CLASSIFY_FILE = "classify.json"
RETRIEVE_FILE = "retrieve.json"


def case_key(policy: PolicyRecord, inputs: ClaimInput) -> str:
    """Stable key of a case's inputs (the predictor interface does not receive the case ID)."""
    return hashlib.sha256(f"{policy.policy_id}\n{inputs.narrative}".encode()).hexdigest()[:20]


def _load(name: str, stages_dir: Path = STAGES_DIR) -> dict[str, Any]:
    try:
        return json.loads((stages_dir / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(name: str, data: dict[str, Any], stages_dir: Path = STAGES_DIR) -> None:
    stages_dir.mkdir(parents=True, exist_ok=True)
    (stages_dir / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _chat_name(model: str | None) -> str:
    return (model or DEFAULT_MODEL).split(":", 1)[-1]


def load_classification(cases: list[GoldenCase], stages_dir: Path = STAGES_DIR) -> list[Expected]:
    """Stage 1 output as predictions, in case order; fails if a case was not classified."""
    cache = _load(CLASSIFY_FILE, stages_dir)
    missing = [c.case_id for c in cases if case_key(c.policy, c.inputs) not in cache]
    if missing:
        raise RuntimeError(f"not classified: {missing[:3]}...; run `make eval-classify` first")
    return [
        Expected.model_validate(cache[case_key(c.policy, c.inputs)]["prediction"]) for c in cases
    ]


def stage_classify(cases: list[GoldenCase], model: str | None = None) -> None:
    cache = _load(CLASSIFY_FILE)
    todo = [c for c in cases if case_key(c.policy, c.inputs) not in cache]
    print(f"classify: {len(cases) - len(todo)} cached, {len(todo)} to run")
    if todo:
        predictor = make_predictor(model)
        for case in todo:
            prediction = predictor(case.policy, case.inputs, case.facts)
            if not predictor.last_usage["llm_ok"]:  # a silent fallback would fake the results
                raise RuntimeError(f"classifier failed on {case.case_id}: {predictor.last_usage}")
            cache[case_key(case.policy, case.inputs)] = {
                "case_id": case.case_id,
                "prediction": prediction.model_dump(mode="json"),
                "usage": predictor.last_usage,
            }
            _save(CLASSIFY_FILE, cache)  # resumable after a crash
    unload_model(_chat_name(model))


def stage_retrieve(cases: list[GoldenCase]) -> None:
    from claimsight.agents.triage import retrieval_query
    from claimsight.rag import store
    from claimsight.rag.clause_map import from_prediction
    from claimsight.rag.corpus import clauses_by_id, policy_language
    from claimsight.rag.retriever import PolicyRetriever

    predictions = load_classification(cases)
    conn, embeddings = store.connect(), store.embedder()
    store.ensure_ingested(conn, "clause", embeddings)
    retrievers = {
        lang: PolicyRetriever(conn=conn, embeddings=embeddings, language=lang)
        for lang in ("en", "es")
    }
    cache = _load(RETRIEVE_FILE)
    for case, prediction in zip(cases, predictions, strict=True):
        key = case_key(case.policy, case.inputs)
        if key in cache:
            continue
        lang = policy_language(case.policy)
        start = time.perf_counter()
        docs = retrievers[lang].invoke(retrieval_query(prediction, case.inputs))
        retrieved: dict[str, str] = {}
        for doc in docs:
            retrieved.setdefault(doc.metadata["clause_id"], doc.page_content)
        for clause_id in from_prediction(prediction, case.inputs.claimed_event):
            retrieved.setdefault(clause_id, clauses_by_id(lang)[clause_id].text)
        cache[key] = {
            "case_id": case.case_id,
            "retrieved": retrieved,
            "retrieve_s": round(time.perf_counter() - start, 3),
        }
        _save(RETRIEVE_FILE, cache)
    print(f"retrieve: {len(cache)} cases cached")
    unload_model(store.EMBED_MODEL)


class StagedCoveragePredictor:
    """Harness predictor that replays stages 1 and 2 from the cache and runs stage 3 live."""

    reports_coverage = True

    def __init__(self, coverage_llm: Any, stages_dir: Path = STAGES_DIR) -> None:
        self._graph = build_generation_graph(coverage_llm)
        self._classify = _load(CLASSIFY_FILE, stages_dir)
        self._retrieve = _load(RETRIEVE_FILE, stages_dir)
        self.last_usage: dict[str, Any] = {}

    def __call__(self, policy: PolicyRecord, inputs: ClaimInput, facts: CaseFacts) -> Expected:
        key = case_key(policy, inputs)
        stage1, stage2 = self._classify[key], self._retrieve[key]
        state = self._graph.invoke(
            {
                "policy": policy,
                "inputs": inputs,
                "facts": facts,
                "prediction": Expected.model_validate(stage1["prediction"]),
                "retrieved": stage2["retrieved"],
                "retrieve_s": stage2["retrieve_s"],
                "usage": stage1["usage"],
            }
        )
        self.last_usage = {
            **state["usage"],
            "llm_ok": stage1["usage"]["llm_ok"] and state["usage"]["generation_ok"],
        }
        return state["prediction"]


def stage_generate(cases: list[GoldenCase], model: str | None = None) -> None:
    load_classification(cases)
    if len(_load(RETRIEVE_FILE)) < len(cases):
        raise RuntimeError("retrieval not cached; run `make eval-coverage` (stage 2) first")
    llm = make_llm(model).with_structured_output(CoverageOutput, include_raw=True)
    name = report_name("coverage", model or DEFAULT_MODEL)
    report = run(name, cases, StagedCoveragePredictor(llm))
    report["model"] = model or DEFAULT_MODEL
    out = write_report(name, report)
    print(json.dumps(report["coverage"], indent=2, ensure_ascii=False))
    print(f"\nwrote {out}")
    unload_model(_chat_name(model))


def main(argv: list[str]) -> int:
    model = None
    if "--model" in argv:
        i = argv.index("--model")
        model = argv[i + 1]
        argv = argv[:i] + argv[i + 2 :]
    stages = {
        "classify": lambda c: stage_classify(c, model),
        "retrieve": stage_retrieve,
        "generate": lambda c: stage_generate(c, model),
    }
    if len(argv) != 1 or argv[0] not in stages:
        print("usage: staged_coverage classify|retrieve|generate [--model provider:name]")
        return 2
    stages[argv[0]](load_golden())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
