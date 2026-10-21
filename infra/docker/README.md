# Local Infrastructure

Docker Compose configuration for local development dependencies.

## PostgreSQL

To start the local PostgreSQL service:

```bash
docker compose -f infra/docker/compose.yaml up -d
```

To stop it:

```bash
docker compose -f infra/docker/compose.yaml down
```

Credentials match `.env.example`:
- **Host**: `localhost`
- **Port**: `5432`
- **User**: `praxis`
- **Password**: `praxis`
- **Database**: `praxis`
- **URL**: `postgresql+psycopg://praxis:praxis@localhost:5432/praxis`
