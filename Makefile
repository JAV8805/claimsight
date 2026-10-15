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
