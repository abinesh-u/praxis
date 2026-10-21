# Local Development Setup

## Prerequisites
- Python 3.11+
- Node.js LTS and pnpm
- Docker and Docker Compose
- Git

## Setup
```bash
git clone <your-repository-url>
cd praxis
cp .env.example .env
```

After `infra/docker/compose.yaml` is implemented:
```bash
docker compose -f infra/docker/compose.yaml up -d
```

API setup:
```bash
cd services/api
uv sync --dev
uv run uvicorn praxis_api.main:app --reload --port 8000
```

Web setup:
```bash
cd apps/web
pnpm install
pnpm dev
```

## Conventions
- Domain rules belong in `packages/core`, not route handlers or UI.
- Test state transitions and permission decisions.
- Use migrations for schema changes.
- Keep secrets out of Git and logs.
- Every agent tool declares permissions, schema, side-effect class, timeout, and failure behavior.
- Record boundary-changing decisions as ADRs.
