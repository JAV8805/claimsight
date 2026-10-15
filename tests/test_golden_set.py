"""CI gate: the committed golden set must be valid, unique and in sync with its sources."""

import json
from pathlib import Path

import pytest

from claimsight.evals.schema import GoldenCase

GOLDEN = Path("evals/golden")
LINES = (GOLDEN / "v0.jsonl").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("line", LINES, ids=lambda s: json.loads(s)["case_id"])
def test_every_case_is_valid(line: str) -> None:
    GoldenCase.model_validate_json(line)


def test_case_ids_are_unique() -> None:
    ids = [json.loads(line)["case_id"] for line in LINES]
    assert len(ids) == len(set(ids))


def test_every_labeled_case_is_compiled() -> None:
    labels = json.loads((GOLDEN / "labels.json").read_text(encoding="utf-8"))
    ids = {json.loads(line)["case_id"] for line in LINES}
    assert ids == set(labels), "run: make golden"
