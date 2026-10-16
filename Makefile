.RECIPEPREFIX = >
.PHONY: lint format test run

lint:
> uv run ruff check .
> uv run ruff format --check .

format:
> uv run ruff check --fix .
> uv run ruff format .

test:
> uv run pytest -q

run:
> uv run uvicorn claimsight.api.main:app --app-dir src --reload

COMPOSE = docker compose -f infra/docker-compose.yml --env-file .env

.PHONY: up down ps psql
up:
> $(COMPOSE) up -d --wait

down:
> $(COMPOSE) down

ps:
> $(COMPOSE) ps

psql:
> $(COMPOSE) exec postgres psql -U claimsight -d claimsight

.PHONY: redis-cli
redis-cli:
> $(COMPOSE) exec redis redis-cli

.PHONY: check-vins
check-vins:
> uv run python scripts/check_vin_patterns.py

golden-drafts:
> uv run python scripts/build_golden_drafts.py

golden:
> uv run python scripts/compile_golden.py

.PHONY: eval
eval:
> uv run python -m claimsight.evals.harness baseline

# Local LLM triage (needs Ollama running): make eval-llm MODEL=ollama:qwen2.5:7b
MODEL ?= ollama:qwen2.5:7b
.PHONY: eval-llm
eval-llm:
> uv run python -m claimsight.evals.harness triage --model $(MODEL)

# Retrieval eval: ingests the policy corpus into pgvector and scores recall@k / MRR.
# Needs `make up` (Postgres) and Ollama with bge-m3.
.PHONY: eval-retrieval
eval-retrieval:
> set -a && . ./.env && set +a && uv run python -m claimsight.rag.eval_retrieval
