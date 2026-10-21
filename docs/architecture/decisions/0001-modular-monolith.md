# ADR 0001: Start with a modular monolith

- Status: Accepted
- Date: 2026-10-21

## Context
Praxis needs a shared execution model across CLI, web, API, scheduler, and bounded agent runtime. Premature service separation would increase deployment and consistency costs before boundaries are proven.

## Decision
Start as a modular monolith with explicit package boundaries. Keep web and local CLI as separate applications over one API and shared domain contracts. The worker/scheduler may be deployed separately later if reliability or scale requires it.

## Consequences
- Easier local development and end-to-end testing.
- Package boundaries must be enforced through imports and review.
- Long-running jobs must not block API requests.
- Split components only when measured operational needs justify it.
