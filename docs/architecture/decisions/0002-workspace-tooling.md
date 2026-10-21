# ADR 0002: Monorepo Workspace with UV and Next.js

- Status: Accepted
- Date: 2026-10-21

## Context
Praxis requires a modular monolith where domain logic (`packages/core`) is reused across HTTP endpoints (`services/api`), bounded background runtimes (`packages/agent-runtime`, `packages/scheduler`), and a local CLI (`packages/cli`). Meanwhile, the web front-end (`apps/web`) is a TypeScript/Next.js application.

## Decision
1. Use `uv` workspace to manage all Python packages and services under a single root lockfile, with editable workspace resolution (`{ workspace = true }`).
2. Use Ruff for unified formatting and linting across all Python code with py311+ targets and 100-character line lengths.
3. Use Next.js (App Router) in `apps/web` with standard TypeScript configurations.
4. Keep Docker Compose under `infra/docker/compose.yaml` for local database (PostgreSQL 16) provisioning.
5. Provide a root `Makefile` exposing standard operations (`make test`, `make lint`, `make setup`, `make api-dev`).

## Consequences
- Single `uv sync --all-packages` resolves and installs all packages cleanly.
- Tests can run workspace-wide via `uv run pytest`.
- Imports between `praxis_core`, `praxis_api`, `praxis_cli`, etc., are immediately resolvable and type-checkable.
- CI is excluded for Phase 0 as requested; all validation is executable locally.
