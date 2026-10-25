# M2 operational recovery hardening

M2 makes uncertain execution operable without manufacturing certainty. It does
not add integrations, scheduling, Telegram, web breadth, or PostgreSQL.

## Recovery rules

### Missing provider operation ID

Keep the attempt in `outcome_unknown`. Praxis must not construct a status URL
from untrusted response content or submit a second POST. An operator should:

1. Record the task and attempt IDs from `praxis show`.
2. Inspect the provider using an authorized operator channel and the original
   idempotency key or provider-side request logs.
3. Attach the external investigation reference to the incident record.
4. Reconcile only after a stable provider operation identifier is available.

If the provider cannot identify the operation, leave the attempt unresolved and
escalate for manual provider investigation.

### Permanently pending operation

Elapsed time is not proof of failure. A deployment should define an operator
review threshold (for example, 24 hours) and record the last status lookup,
provider response, and investigation reference. At the threshold, page or
queue an operator review; do not automatically fail or redispatch the action.

Only an authoritative provider result or an explicitly documented, auditable
manual decision may resolve the attempt.

## SQLite backup and restore

Use the online backup API while the service is running:

```bash
./.venv/bin/python scripts/sqlite_backup.py \
  sqlite:////var/lib/praxis/praxis.db \
  sqlite:////var/backups/praxis-$(date +%Y%m%d%H%M%S).db
```

The command verifies `PRAGMA integrity_check`. A restore drill must open the
backup with Praxis and verify tasks, execution attempts, idempotency linkage,
evidence, and audit events. Keep backups access-controlled and encrypted by
the deployment platform.

## Audit retention

Audit retention is an explicit operational decision, not an implicit delete.
Use a reviewed cutoff and dry-run first:

```bash
./.venv/bin/python scripts/prune_audit_events.py \
  sqlite:////var/lib/praxis/praxis.db \
  --before 2026-01-01T00:00:00+00:00 --dry-run
```

Retain the backup and change record associated with each pruning operation.
Never prune events needed for an unresolved attempt or an active incident.

## Secret-safe logs and reports

Ordinary logs and generated reports must exclude bearer tokens, approval
tokens, idempotency keys, credentials, and raw provider payloads. Safe fields
include task ID, attempt ID, provider operation ID when non-sensitive, status,
timestamps, and recovery guidance. Review deployment logs and M1/M2 artifacts
before sharing them outside the operator group.

