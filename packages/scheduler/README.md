# Scheduler

Owns durable reminders and recurring workflow scheduling.

Requirements: persisted schedules and execution state; explicit time-zone/DST handling; idempotency keys; bounded retries with backoff; observable failed jobs; recovery after restart. Process-local timers are not a durable source of truth.
