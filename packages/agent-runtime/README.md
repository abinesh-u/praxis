# Agent Runtime

A bounded orchestration loop for model-assisted planning and tool execution.

Each tool defines its input/output schema, required capability and scope, side-effect class, timeout/retry policy, approval requirement, and evidence returned on success.

Enforce step/time budgets, persist checkpoints, validate tool arguments, and stop on permission denial or ambiguous high-risk outcomes. Model output is never authorization.
