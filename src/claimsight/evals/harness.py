"""Eval harness: run a predictor over the golden set and score it per field.

Usage: uv run python -m claimsight.evals.harness <predictor>
Writes evals/reports/<predictor>.json and prints a markdown table.
"""

import json
import sys
from collections.abc import Callable, Iterator
from importlib import import_module
from pathlib import Path
from typing import Any

from claimsight.evals.schema import (
    CaseFacts,
    ClaimInput,
    Expected,
    GoldenCase,
    PolicyRecord,
)

Predictor = Callable[[PolicyRecord, ClaimInput, CaseFacts], Expected]

GOLDEN_PATH = Path("evals/golden/v0.jsonl")
REPORTS_DIR = Path("evals/reports")
PREDICTORS = {"baseline": "claimsight.baselines.rules:predict"}  # name -> module:function
ACCURACY_FIELDS = ("claim_type", "weather_verdict", "routing")
HEADLINE = "routing_accuracy"
GROUPS: dict[str, Callable[[GoldenCase], str]] = {
    "by_language": lambda c: c.language,
    "by_adversarial": lambda c: "adversarial" if c.adversarial else "normal",
}


def load_golden(path: Path = GOLDEN_PATH) -> list[GoldenCase]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [GoldenCase.model_validate_json(line) for line in lines if line.strip()]


def load_predictor(name: str) -> Predictor:
    module, _, func = PREDICTORS[name].partition(":")
    return getattr(import_module(module), func)


def _ratio(numerator: int, denominator: int) -> float | None:
    """None when undefined (e.g. precision with no predicted positives)."""
    return round(numerator / denominator, 4) if denominator else None


def score(pairs: list[tuple[GoldenCase, Expected]]) -> dict[str, Any]:
    """Per-field metrics for (case, prediction) pairs."""
    n = len(pairs)
    metrics: dict[str, float | None] = {}
    for field in ACCURACY_FIELDS:
        hits = sum(getattr(c.expected, field) == getattr(p, field) for c, p in pairs)
        metrics[f"{field}_accuracy"] = _ratio(hits, n)
    tp = sum(c.expected.fraud_flag and p.fraud_flag for c, p in pairs)
    predicted = sum(p.fraud_flag for _, p in pairs)
    actual = sum(c.expected.fraud_flag for c, _ in pairs)
    metrics["fraud_flag_precision"] = _ratio(tp, predicted)
    metrics["fraud_flag_recall"] = _ratio(tp, actual)
    exact = sum(set(c.expected.fraud_signals) == set(p.fraud_signals) for c, p in pairs)
    metrics["fraud_signals_exact_match"] = _ratio(exact, n)
    return {"n": n, "metrics": metrics}


def mistakes(pairs: list[tuple[GoldenCase, Expected]]) -> list[dict[str, Any]]:
    """Every scored field a prediction got wrong, for diagnosis."""
    found = []
    for case, pred in pairs:
        for field in (*ACCURACY_FIELDS, "fraud_flag", "fraud_signals"):
            want, got = getattr(case.expected, field), getattr(pred, field)
            if field == "fraud_signals":
                want, got = sorted(want), sorted(got)
            if want != got:
                found.append(
                    {"case_id": case.case_id, "field": field, "expected": want, "predicted": got}
                )
    return found


def run(name: str, cases: list[GoldenCase], predictor: Predictor) -> dict[str, Any]:
    pairs = [(c, predictor(c.policy, c.inputs, c.facts)) for c in cases]
    report: dict[str, Any] = {"predictor": name, "golden": GOLDEN_PATH.name}
    report["overall"] = score(pairs)
    for group, key in GROUPS.items():
        labels = sorted({key(c) for c, _ in pairs})
        report[group] = {lab: score([p for p in pairs if key(p[0]) == lab]) for lab in labels}
    report["mistakes"] = mistakes(pairs)
    return report


def columns(report: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    yield "overall", report["overall"]
    for group in GROUPS:
        for label, block in report.get(group, {}).items():
            yield f"{label}", block


def flatten(report: dict[str, Any]) -> dict[str, float | None]:
    """Every metric of a report keyed by 'group/metric', for comparisons."""
    flat = {}
    for col, block in columns(report):
        for metric, value in block["metrics"].items():
            flat[f"{col}/{metric}"] = value
    return flat


def regressions(committed: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Metrics of the current run that fell below the committed report."""
    old, new = flatten(committed), flatten(current)
    problems = []
    for key, was in old.items():
        now = new.get(key)
        if was is not None and (now is None or now < was):
            problems.append(f"{key}: {was} -> {now}")
    return problems


def markdown(report: dict[str, Any]) -> str:
    cols = list(columns(report))
    head = "| metric | " + " | ".join(f"{name} (n={b['n']})" for name, b in cols) + " |"
    rows = [head, "| --- |" + " ---: |" * len(cols)]
    for metric in report["overall"]["metrics"]:
        label = f"**{metric}**" if metric == HEADLINE else metric
        cells = ["n/a" if (v := b["metrics"][metric]) is None else f"{v:.3f}" for _, b in cols]
        rows.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in PREDICTORS:
        print(f"usage: harness <{'|'.join(PREDICTORS)}>")
        return 2
    name = argv[0]
    report = run(name, load_golden(), load_predictor(name))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{name}.json"
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(markdown(report))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
