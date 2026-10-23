# Praxis execution release-readiness checklist

This checklist applies before exposing the webhook execution path to real
users. The automated suite validates the lifecycle against a deterministic
provider transport; a disposable real-provider run is still required before
production use.

## Provider and network

- [ ] Provider documents `Idempotency-Key` retention and duplicate-request
      behavior.
- [ ] Provider returns a stable `operation_id` (in the response body or
      `X-Operation-ID` header) before any response can become ambiguous.
- [ ] Provider status lookup distinguishes `completed`, `pending`, and a
      final failure (`failure_final: true`). Ambiguous failures remain
      `outcome_unknown`.
- [ ] `PRAXIS_WEBHOOK_URL` and optional `PRAXIS_WEBHOOK_STATUS_URL` use HTTPS,
      expected hosts, bounded timeouts, and no embedded credentials.
- [ ] DNS resolution, TLS, and network egress restrictions are validated in
      the deployment environment. Redirects remain disabled.
- [ ] A disposable action has been used for the real-provider test; no
      consequential production action is used for validation.

## Authentication and isolation

- [ ] `PRAXIS_AUTH_TOKENS` and `PRAXIS_API_TOKEN` are provisioned through a
      secret manager or protected environment, never committed or logged.
- [ ] Requests derive the owner from the authenticated bearer token.
- [ ] Cross-owner task, attempt, approval, Today, and reconciliation requests
      return the expected denial without disclosing metadata.
- [ ] Logs and terminal output contain no bearer tokens, idempotency keys, or
      raw provider payloads.

## Persistence and recovery

- [ ] SQLite backups are scheduled and a restore has been tested.
- [ ] Audit retention and access are defined for the deployment.
- [ ] After a process restart, attempts retain their attempt ID, provider
      operation ID, idempotency linkage, status, evidence, and recovery text.
- [ ] The provider never returns an operation ID: keep the attempt
      `outcome_unknown`, verify the external system manually, and do not retry
      automatically.
- [ ] Status lookup is unavailable: keep the attempt unresolved and retry
      read-only reconciliation later; do not dispatch another POST.
- [ ] The operation remains pending indefinitely: record the last lookup,
      escalate for manual provider investigation, and resolve only with
      authoritative evidence or an explicitly documented manual decision.

## Verification commands

Run before release:

```bash
./.venv/bin/pytest
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
git diff --check
```

The controlled-provider test must independently assert the provider call
sequence (`POST`, then `GET`) rather than inferring dispatch from Praxis's
internal execution-attempt records.

For M1 provider validation, use [the provider contract](m1-provider-contract.md),
[the validation matrix](m1-validation-matrix.md), and the two-phase helper:

```bash
PRAXIS_API_URL=http://localhost:8000 \
PRAXIS_OWNER_ID=... \
PRAXIS_TASK_ID=... \
PRAXIS_API_TOKEN=... \
PRAXIS_APPROVAL_TOKEN=... \
./.venv/bin/python scripts/m1_validate_provider.py dispatch \
  --idempotency-key m1-disposable-001

PRAXIS_API_URL=http://localhost:8000 \
PRAXIS_OWNER_ID=... \
PRAXIS_TASK_ID=... \
PRAXIS_API_TOKEN=... \
./.venv/bin/python scripts/m1_validate_provider.py reconcile \
  --attempt-id <attempt-id-from-dispatch>
```

The helper performs one dispatch or one read-only reconciliation only; it does
not retry uncertain actions. Its API client timeout defaults to 30 seconds so
Praxis can finish recording a provider timeout; override it with
`PRAXIS_API_TIMEOUT` when the deployment contract requires a different bound.

## Manual unresolved-attempt procedure

1. Run `praxis show <task-id>` and record the attempt ID and provider request
   ID shown by Praxis.
2. Query the provider's documented status endpoint using the provider request
   ID, through an authorized operator channel.
3. If authoritative completion is available, run the API-backed
   `praxis reconcile <task-uuid> <attempt-uuid>` operation.
4. If the provider cannot establish an outcome, leave the attempt uncertain;
   attach the external investigation reference to the incident record rather
   than forcing a retry.
