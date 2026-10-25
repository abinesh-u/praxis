# M1 provider contract

This contract is required before enabling the webhook execution path against a
real provider. The provider must be disposable for validation and must not
receive consequential production actions.

## Dispatch

Praxis sends one `POST` request to `PRAXIS_WEBHOOK_URL` with:

- `Idempotency-Key: <Praxis execution-attempt ID>`
- Optional `Authorization: Bearer <provider credential>` from
  `PRAXIS_WEBHOOK_AUTH_TOKEN`
- JSON containing `task_id`, `attempt_id`, and the bounded action `payload`

The provider must retain the idempotency key for at least the maximum period in
which Praxis may retry or reconcile the attempt. Duplicate requests with the
same key must not create a second external effect.

The provider should return an operation identifier in either:

- JSON field `operation_id`, or
- response header `X-Operation-ID` (including when the response body may time out)

The operation identifier must be stable, opaque, and safe to place in a status
URL path. It must not contain credentials or arbitrary path syntax.

## Status lookup

Praxis performs a read-only `GET` against the configured status endpoint. The
response must contain a JSON object with one of these semantics:

If the status endpoint has a different origin from the dispatch endpoint,
configure `PRAXIS_WEBHOOK_STATUS_AUTH_TOKEN`. Praxis refuses to forward the
dispatch credential across origins.

| Provider response | Praxis state |
| --- | --- |
| `{"status":"completed"}` | Confirmed completion and machine evidence |
| `{"status":"pending"}` | `outcome_unknown`; reconcile later |
| `{"status":"failed","failure_final":true}` | Confirmed provider failure |
| Missing, malformed, or non-final failure | `outcome_unknown` |

HTTP acceptance alone is not completion evidence. A timeout, transport error,
missing operation ID, unavailable status endpoint, or indefinite pending state
must not trigger a new dispatch automatically.

## Required provider evidence

Before M1 is accepted, record the provider's documented answers for:

1. Idempotency-key scope, retention, and duplicate behavior.
2. Operation-ID availability after accepted requests and lost responses.
3. Status endpoint authentication, TLS requirements, and terminal-state meaning.
4. Status visibility delay and behavior during provider outages.
5. Whether final failure guarantees that no external effect occurred.

If the provider cannot answer these questions, Praxis must preserve
`outcome_unknown` and require operator investigation rather than manufacture an
exactly-once guarantee.

## Local disposable provider

`scripts/m1_disposable_provider.py` binds to loopback for local validation. To
use it, set `APP_ENV=development` and
`PRAXIS_WEBHOOK_ALLOW_PRIVATE_DESTINATIONS=m1-local-only`. This explicit
override requires an explicitly set `APP_ENV=development` or `APP_ENV=test`
and must never be set in staging or production. Authenticated external
endpoints must use HTTPS; plaintext HTTP is accepted only for loopback or
private destinations under this local harness.
