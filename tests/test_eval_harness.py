"""CI regression gate for the rules baseline, plus unit tests of the harness metrics."""

import json
from pathlib import Path

from claimsight.baselines.rules import predict
from claimsight.evals.harness import flatten, load_golden, regressions, run, score
from claimsight.evals.schema import GoldenCase

COMMITTED = Path("evals/reports/baseline.json")


def test_baseline_does_not_regress() -> None:
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    current = run("baseline", load_golden(), predict)
    assert current["overall"]["n"] == committed["overall"]["n"], "golden set changed: run make eval"
    assert not regressions(committed, current), "baseline dropped below evals/reports/baseline.json"


def test_regressions_flags_drops_only() -> None:
    base = {"overall": {"n": 1, "metrics": {"a": 0.9, "b": 0.5, "c": None}}}
    worse = {"overall": {"n": 1, "metrics": {"a": 0.8, "b": 0.6, "c": 0.1}}}
    assert regressions(base, worse) == ["overall/a: 0.9 -> 0.8"]
    assert regressions(base, base) == []
    gone = {"overall": {"n": 1, "metrics": {"a": 0.9, "b": None, "c": None}}}
    assert regressions(base, gone) == ["overall/b: 0.5 -> None"]
    assert flatten(base) == {"overall/a": 0.9, "overall/b": 0.5, "overall/c": None}


def test_score_known_predictions() -> None:
    cases = load_golden()
    perfect = [(c, c.expected) for c in cases]
    metrics = score(perfect)["metrics"]
    assert all(v in (1.0, None) for v in metrics.values())
    assert metrics["fraud_flag_recall"] == 1.0

    miss = next(c for c in cases if c.expected.fraud_flag)
    wrong = miss.expected.model_copy(update={"fraud_flag": False, "fraud_signals": []})
    result = score([(miss, wrong)])["metrics"]
    assert result["fraud_flag_recall"] == 0.0
    assert result["fraud_flag_precision"] is None  # nothing predicted positive
    assert result["fraud_signals_exact_match"] == 0.0


def test_baseline_breakdowns_cover_every_case() -> None:
    report = run("baseline", load_golden(), predict)
    total = report["overall"]["n"]
    for group in ("by_language", "by_adversarial"):
        assert sum(b["n"] for b in report[group].values()) == total


def test_baseline_has_no_llm_cases_right_for_free() -> None:
    """The prompt-injection case needs language understanding: rules cannot see it."""
    case = next(c for c in load_golden() if "prompt_injection" in c.expected.fraud_signals)
    assert isinstance(case, GoldenCase)
    assert predict(case.policy, case.inputs, case.facts).fraud_signals == []
