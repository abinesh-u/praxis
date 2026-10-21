.PHONY: help api-dev api-test lint
help:
	@echo "api-dev   Run FastAPI development server"
	@echo "api-test  Run API tests"
	@echo "lint      Run Python lint checks"
api-dev:
	cd services/api && uv run uvicorn praxis_api.main:app --reload --host 0.0.0.0 --port 8000
api-test:
	cd services/api && uv run pytest
lint:
	cd services/api && uv run ruff check .
