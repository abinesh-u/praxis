# M1 local recovery evidence

This is a sanitized record of the controlled loopback-provider validation. It
contains identifiers and counters only; it contains no credentials, payloads,
or raw provider responses.

## Environment

- Provider: disposable local HTTP provider in
  `timeout_after_acceptance` mode.
- Praxis: local API using SQLite.
- Private-destination override: enabled only in `APP_ENV=development`.
- Provider delay: 12 seconds; the dispatch client timed out before the delayed
  response was consumed.

## Observed lifecycle

| Check | Result |
| --- | --- |
| Dispatch status | `outcome_unknown` |
| Attempt ID | `e1879639-3624-4270-9fce-f15dd4500bb3` |
| Provider operation ID | `op-7fb51f15cc987aba` |
| Provider POST count | `1` |
| Provider effect count | `1` |
| API restart | Same SQLite database, provider left running |
| Reconciliation | `completed`, read-only GET |
| Provider GET count | `1` |
| Repeated reconciliation | HTTP `409`; counters unchanged |
| Persisted task | `completed` |
| Persisted evidence | `609894d0-8883-4c17-bfad-fc49d38d3c81` |
| Audit evidence | `task.completed` present |

## Scope and limitations

This proves the local real-HTTP recovery contract and independently observed
POST/GET/effect counts. It does not prove production TLS, public DNS, egress
policy, or a third-party provider's idempotency retention and status semantics.
Those checks remain deployment gates.

