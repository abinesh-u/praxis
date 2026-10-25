# M1 validation matrix

Run each scenario against a disposable provider and record the provider's own
POST/GET counters independently from Praxis execution-attempt records.

| Scenario | Provider behavior | Expected Praxis behavior |
| --- | --- | --- |
| Immediate completion | POST returns operation ID and `completed` | One POST; attempt completed with evidence |
| Rejected request | POST returns documented rejection | No false success; final failure only if authoritative |
| Accepted then lost response | Provider accepts, response times out | One POST; `outcome_unknown`; operation ID retained if available |
| Missing operation ID | Provider accepts without an ID | `outcome_unknown`; no automatic retry; operator escalation |
| Delayed visibility | GET returns `pending`, then `completed` | Remains uncertain, then resolves on later GET |
| Status unavailable | GET times out or returns transport error | Remains uncertain; no POST |
| Final failure | GET returns `failed` plus `failure_final: true` | Confirmed failure; no POST |
| Ambiguous failure | GET returns failure without finality | Remains uncertain; no POST |
| Repeated reconciliation | Multiple reconciliation requests | GET-only behavior; one terminal state and consistent evidence |
| Owner mismatch | Another owner requests task/attempt | Denial without metadata disclosure or provider request |

The M1 exit evidence must include the provider contract, environment and
network checks, sanitized Praxis responses, provider request counters, and any
limitations that prevent an exactly-once claim.

The disposable provider supports these reproducible modes: `complete`,
`pending`, `reject`, `timeout_after_acceptance`, `missing_id`, `final_failure`,
and `ambiguous_failure`.
