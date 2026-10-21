.PHONY: help setup sync test lint format api-dev cli-version web-dev web-build db-up db-down clean

help:
	@echo "Praxis Development Commands:"
	@echo "  make setup        Sync Python packages and install web dependencies"
	@echo "  make sync         Sync Python uv workspace"
	@echo "  make test         Run all Python tests via pytest"
	@echo "  make lint         Run Ruff lint and format checks"
	@echo "  make format       Auto-format Python code using Ruff"
	@echo "  make api-dev      Run FastAPI backend development server"
	@echo "  make cli-version  Run local Praxis CLI version check"
	@echo "  make web-dev      Run Next.js web application in development mode"
	@echo "  make web-build    Build Next.js web application"
	@echo "  make db-up        Start PostgreSQL container with Docker Compose"
	@echo "  make db-down      Stop PostgreSQL container"
	@echo "  make clean        Remove cache and build artifacts"

setup: sync
	cd apps/web && npm install

sync:
	uv sync --all-packages

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

api-dev:
	uv run --package praxis-api uvicorn praxis_api.main:app --reload --host 0.0.0.0 --port 8000

cli-version:
	uv run --package praxis-cli praxis version

web-dev:
	cd apps/web && npm run dev

web-build:
	cd apps/web && npm run build

db-up:
	docker compose -f infra/docker/compose.yaml up -d

db-down:
	docker compose -f infra/docker/compose.yaml down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
