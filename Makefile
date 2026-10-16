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

# --- Staged evals: ONE model in memory at a time (8 GB RAM cannot hold 7B chat + bge-m3) ---
# Recommended: run the Ollama server with OLLAMA_MAX_LOADED_MODELS=1 (see docs/rag.md). The
# targets below also unload each model explicitly (`ollama stop`) before the next stage.
# Order: make eval-classify; make eval-retrieval; make eval-coverage
CHAT = $(patsubst ollama:%,%,$(MODEL))
STAGED = set -a && . ./.env && set +a && uv run python -m claimsight.evals.staged_coverage

.PHONY: eval-classify eval-retrieval eval-coverage
eval-classify:  # stage 1 (chat model): claim type and signals per case, cached
> $(STAGED) classify --model $(MODEL)
> ollama stop $(CHAT) || true

eval-retrieval:  # embedding model only; reads the stage 1 cache for the classifier source
> set -a && . ./.env && set +a && uv run python -m claimsight.rag.eval_retrieval
> ollama stop bge-m3 || true

eval-coverage:  # stage 2 (embedding model), then stage 3 (chat model) from the cache
> $(STAGED) retrieve
> ollama stop bge-m3 || true
> $(STAGED) generate --model $(MODEL)
> ollama stop $(CHAT) || true
