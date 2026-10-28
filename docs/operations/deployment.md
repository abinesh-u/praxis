# Praxis Production Deployment & Operational Manual

Milestone M5 operational guidance for running Praxis in production environments.

---

## 1. System Topology & Seams

Praxis decomposes into two operational processes connected through an HTTP reverse-proxy transport seam:

```
[ Browser Client ]
       │
       ▼ (HTTPS)
[ Next.js Node Process (apps/web) ]
       │
       ▼ (/api/backend/* reverse proxy rewrite)
[ FastAPI Backend Engine (services/api:8000) ]
       │
       ├─► [ SQLite Durable Store (WAL Mode) ]
       └─► [ Outbound Webhooks (SSRF-Protected) ]
```

- **Frontend Tier (`apps/web`)**: Next.js 15 production server handling UI presentation, local view state, and client-side credential storage.
- **Backend Tier (`services/api`)**: Python/FastAPI application exposing deterministic domain use cases, enforcing tenant isolation, and recording execution evidence.
- **Persistence Layer**: SQLite database operating with write-ahead logging (`journal_mode=WAL`), busy timeouts, and optimistic revision locking.

---

## 2. Environment Configuration Reference

The following table documents all environment variables recognized across the codebase:

| Variable | Target Subsystem | Default | Description |
| --- | --- | --- | --- |
| `PRAXIS_AUTH_TOKENS` | `services/api` | `""` (Open local dev) | Comma-separated `tenant=bearer_token` pairs (e.g. `alice=sec_123,bob=sec_456`). When non-empty or in production, all endpoints enforce Bearer authentication. |
| `PRAXIS_ENV` | `services/api` | `development` | Environment mode (`production`, `development`, `test`). In non-development environments, skill management routes strictly fail closed if credentials are absent. |
| `PRAXIS_SKILLS_DIR` | `services/api` | `~/.praxis/skills` | Directory storing procedural knowledge markdown files with YAML frontmatter. Preserves file locality and atomic persistence. |
| `DATABASE_URL` | `services/api` | `sqlite:///praxis.db` | Path or URI to the SQLite database file. Supports absolute paths (e.g. `sqlite:////var/data/praxis.db`). |
| `PRAXIS_API_URL` | `apps/web` | `http://127.0.0.1:8000` | Target backend host address used by the Next.js `/api/backend/:path*` reverse proxy rewrite rule. |
| `PRAXIS_WEBHOOK_ALLOWED_HOSTS` | `services/api` | `""` (Blocks all outbound) | Comma-separated list of permitted outbound webhook destinations (e.g. `api.stripe.com,hooks.slack.com`). Prevents unauthorized network egress. |
| `PRAXIS_WEBHOOK_URL` | `services/api` | `None` | Default destination URL for `webhook_post` tool executions when not explicitly provided in action arguments. |
| `PRAXIS_HOME` | `packages/cli` | `~/.praxis` | Root configuration and state directory for CLI operations and local profile stores. |
| `PRAXIS_MODEL_NEBIUS_API_KEY` | `packages/core` | `""` | Authentication key for model extraction through the Nebius inference provider. |
| `PRAXIS_MODEL_DEFAULT` | `packages/core` | Provider default | Model name override for natural-language commitment extraction and proposal parsing. |

---

## 3. Verified HTTP Endpoints

All routes enforce strict owner isolation through `IdentityProvider.resolve`. When `PRAXIS_AUTH_TOKENS` is active, requests must include `Authorization: Bearer <token>`.

| Method | Endpoint | Primary Responsibility |
| --- | --- | --- |
| `GET` | `/health` | System health check (`{"status": "ok"}`). Unauthenticated for load balancers. |
| `POST` | `/tasks` | Capture natural-language commitment and generate actionable task. |
| `POST` | `/commitments/{id}/clarify` | Submit user clarification response to resolve ambiguous intent. |
| `GET` | `/tasks/today` | Fetch daily agenda categorized into actionable and waiting items. |
| `GET` | `/tasks` | List paginated commitments for the authenticated tenant. |
| `GET` | `/tasks/{id}` | Inspect full task metadata, history, and current next action. |
| `POST` | `/tasks/{id}/complete` | Confirm completion with human audit evidence note. |
| `POST` | `/tasks/{id}/execute` | Dispatch next action execution through bounded tool adapter. |
| `POST` | `/tasks/{id}/reconcile` | Perform strictly read-only status observation for uncertain attempts. |
| `GET` | `/approvals` | List pending consequential action authorization requests. |
| `POST` | `/approvals/{id}/decision` | Submit approve or reject decision for an authorization request. |
| `GET` | `/skills` | List procedural skills filtered by status (`candidate`, `validated`, `rejected`). |
| `GET` | `/skills/{name}` | Inspect procedural skill metadata, instructions, and review audit. |
| `POST` | `/skills/{name}/promote` | Multi-layer validation gate and promotion of candidate to active status. |
| `POST` | `/skills/{name}/reject` | Terminal rejection and archiving of candidate skill with reason. |

---

## 4. Tenant Isolation & Security Invariants

1. **Authentication Enforcement**:
   - When `PRAXIS_AUTH_TOKENS` is populated, any request without a Bearer token or with an invalid token fails immediately with `401 Unauthorized`.
   - If an authenticated token for tenant `A` submits a payload specifying `owner_id: "B"`, the backend returns `403 Forbidden`.
2. **Access Control Locality**:
   - Cross-tenant lookups return `404 Not Found` (`EntityNotFoundError`) rather than leaking entity existence.
   - Tenant `B` cannot complete, execute, reconcile, clarify, or decide approvals for tenant `A`.
3. **Outbound SSRF Mitigations**:
   - `WebhookRunner` blocks private, loopback (`127.0.0.1`), link-local (`169.254.0.0/16`), and internal IP ranges.
   - Redirects are disabled to prevent open-redirect SSRF bypasses.
   - Only hosts declared in `PRAXIS_WEBHOOK_ALLOWED_HOSTS` are permitted.

---

## 5. Startup & Operational Verification

### Starting the Backend
```bash
export DATABASE_URL="sqlite:////var/data/praxis/praxis.db"
export PRAXIS_AUTH_TOKENS="tenant_prod=token_secure_987"
export PRAXIS_WEBHOOK_ALLOWED_HOSTS="api.external.com"

uv run uvicorn praxis_api.main:app --host 127.0.0.1 --port 8000 --workers 4
```

Verify backend health:
```bash
curl -f http://127.0.0.1:8000/health
# Output: {"status": "ok", "service": "praxis-api"}
```

### Starting the Web Dashboard
```bash
export PRAXIS_API_URL="http://127.0.0.1:8000"
export NODE_ENV="production"

cd apps/web
npm run build
npm run start -- -p 3000
```

---

## 6. Backup, WAL Checkpoints & Disaster Recovery

### Safe Online Backup
Praxis uses SQLite in WAL mode. Use the SQLite online backup utility to capture consistent snapshots without stopping active readers or writers:
```bash
sqlite3 /var/data/praxis/praxis.db ".backup /var/backups/praxis_$(date +%Y%m%d_%H%M%S).db"
```

### Crash Recovery & Uncertainty Reconciliation
If an unclean shutdown occurs during external tool execution:
1. Restart the backend process.
2. The SQLite database recovers committed transactions automatically from the WAL.
3. Any in-flight execution attempts remain in status `outcome_unknown`.
4. Operators or the user navigate to the web dashboard and click **Reconcile Status**.
5. The status reconciler issues a safe, read-only status query against the provider without re-dispatching the original action.

### Multi-Worker Concurrency & Procedural Skill Persistence
When deploying with multiple Uvicorn workers (`--workers N`):
- **SQLite Concurrency**: SQLite in WAL mode handles multiple worker processes safely with optimistic revision locking and busy timeouts.
- **Skill Storage Atomicity**: `SkillStore` writes to unique temporary files (`tempfile.NamedTemporaryFile`) and performs atomic renames (`os.replace`) within the same directory locality. POSIX guarantees atomic file replacement across worker processes without partial reads.
- **Review-Audit Recovery**: In the event of worker or process restarts, new workers parse YAML frontmatter directly from disk, completely reconstructing `status`, `review_audit` decisions, and immutable `provenance` without data corruption.
