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
