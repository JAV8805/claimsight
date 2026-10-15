# ClaimSight — instructions for Claude Code

Portfolio project: multimodal, multi-agent auto-claims FNOL triage copilot (EN/ES).
Owner: José (git: JoseA <jose.angarita11@gmail.com>, GitHub: JAV8805). Learning project.

## Workflow
- Never commit to main (protected). Short branches, Conventional Commits, PR + squash merge.
- Before every commit: `make lint` and `make test` must pass.
- Open PRs with `gh pr create --title ...`; then `sleep 15 && gh pr checks --watch`.
- José reviews and merges. Never merge yourself.
- Every PR description explains what changed and why, for learning.

## Rules
- Functional behavior lives in docs/functional-spec.md (system behavior only).
  Test evidence goes in docs/evals/validation-log.md, never in the spec.
- Golden set: drafts (generated facts) + evals/golden/labels.json (human judgment)
  -> `make golden` -> evals/golden/v0.jsonl. Judgment labels are José's decision:
  propose them, never decide them silently.
- Never invent data (dates, VIN patterns, weather). Fetch it or ask.
- Real VINs: store only the first 11 characters. Never full VINs.
- Never commit .env. Verify any new package on PyPI before installing.
- Stack: uv, Python 3.12, src layout, ruff (line 100), pytest, Docker Compose (Postgres+pgvector, Redis).
