# Domain Core

Framework-independent business rules and use cases live here.

Planned modules:
- `entities/`: Task, Commitment, Reminder, Approval, Execution
- `value_objects/`: TaskStatus, DueAt, WorkspaceScope, ActionRisk
- `use_cases/`: CaptureCommitment, CompleteTask, DeferTask, RescheduleTask
- `policies/`: PermissionPolicy, ApprovalPolicy, RetryPolicy
- `ports/`: TaskRepository, Clock, Scheduler, AuditSink

Keep FastAPI, React, Typer, database-specific code, and model-provider SDKs out of the domain layer.
