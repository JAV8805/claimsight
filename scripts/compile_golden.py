"""Compile the golden set: generated facts (drafts) + human judgments (labels) -> v0.jsonl.

Usage: uv run python scripts/compile_golden.py
Fails (exit 1) if a draft has no labels, a label has no draft, or a case is inconsistent.
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from claimsight.evals.schema import GoldenCase

GOLDEN = Path("evals/golden")


def main() -> int:
    drafts = {
        p.stem: json.loads(p.read_text(encoding="utf-8")) for p in GOLDEN.glob("drafts/*.json")
    }
    labels = json.loads((GOLDEN / "labels.json").read_text(encoding="utf-8"))
    errors = [f"{cid}: no labels" for cid in sorted(drafts.keys() - labels.keys())]
    errors += [f"{cid}: labels without draft" for cid in sorted(labels.keys() - drafts.keys())]
    lines = []
    for cid in sorted(drafts.keys() & labels.keys()):
        case = drafts[cid]
        case["expected"].update(labels[cid]["expected"])
        case["notes"] = labels[cid].get("notes", "")
        try:
            GoldenCase.model_validate(case)
        except ValidationError as exc:
            errors.append(f"{cid}: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}")
            continue
        lines.append(json.dumps(case, ensure_ascii=False, sort_keys=True))
    if errors:
        print("\n".join(errors))
        return 1
    (GOLDEN / "v0.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"v0.jsonl: {len(lines)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
