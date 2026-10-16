# Eval harness

The harness scores any predictor against the golden set (`evals/golden/v0.jsonl`, 60 cases, EN/ES) and writes a per-field report. Every later pipeline (LLM agents, RAG) is measured with the same code, so scores are comparable.

## Running it

```
make eval        # runs the rules baseline, writes evals/reports/baseline.json, prints a table
```

A predictor is a function `(policy: PolicyRecord, inputs: ClaimInput, facts: CaseFacts) -> Expected`. `facts` are the generated facts of the case (NHTSA decode, Open-Meteo weather); the expected labels are never passed in. Predictors are registered by name in `PREDICTORS` in `src/claimsight/evals/harness.py`, and `python -m claimsight.evals.harness <name>` writes `evals/reports/<name>.json`.

## Metrics

| Field | Metric | Notes |
| --- | --- | --- |
| `claim_type` | accuracy | |
| `weather_verdict` | accuracy | "No verdict" (`None`) counts as a value: predicting a verdict for a non-weather claim is an error |
| `routing` | accuracy | **Headline metric** |
| `fraud_flag` | precision and recall | Positive class = fraud flagged. Precision is `n/a` when nothing is predicted positive, recall when nothing is positive (for example the normal slice has no fraud) |
| `fraud_signals` | exact match | Set equality; a missing or extra signal is a miss |

Every metric is reported overall and broken down by language (`en`, `es`) and by `adversarial` vs `normal`. The report also lists every wrong field (`mistakes`) so a score can be traced to cases.

## Why routing accuracy is the headline

Routing is the decision the business acts on: it says whether a claim is paid quickly, handled by a person or investigated. The other fields are inputs to it. The two routing errors are not symmetric: fast-tracking a claim that needed review leaks money, and referring an honest claimant to SIU harms a customer. One number that covers the whole chain is what we want to improve, and the other fields explain *why* it moves.

Read it with the other fields, not alone: a case can be routed correctly for the wrong reasons (GC-0009 and GC-0053 route correctly with a wrong claim type, see the validation log).

## Regression gate

`tests/test_eval_harness.py::test_baseline_does_not_regress` re-runs the baseline and fails if any metric (overall or in any breakdown) is below `evals/reports/baseline.json`. Improvements pass. After an intended change, or when the golden set changes, run `make eval` and commit the new report in the same PR; the PR description should say why the numbers moved.

## The rules baseline

`src/claimsight/baselines/rules.py` uses no LLM: `claim_type` is the claimed event; VIN checks follow FR-05; the weather verdict comes from `claimsight.rules.weather` with the case's precipitation; routing follows FR-03. It sets the floor that a model must beat. FR-03 says fast track *requires* a VIN match and no fraud, but not which claims qualify; the baseline fast-tracks only collision and glass, as the golden labels do.

## Known limitation: label-rule circularity

The labels were proposed from the same rules the baseline implements, so baseline accuracy measures policy consistency, not real-world accuracy. A high score here shows the code follows the policy; it does not show the policy is right or that the system would do well on real claims. The informative signal is the language-dependent failures (GC-0009, GC-0012, GC-0053), and routing in GC-0009 and GC-0053 is right for the wrong reason. The golden set must grow with cases rules cannot solve.
