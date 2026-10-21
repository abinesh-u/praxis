# Permission Model

## Default-deny principles
- No local file access until the user selects a workspace.
- Resolve paths and verify they remain inside an approved root.
- No unrestricted shell or arbitrary code execution in the MVP.
- Tools are allowlisted per workflow.
- Model output cannot change permissions.
- Consequential external actions require explicit approval.
- Keep file contents local unless a specific authorized operation requires sending them to a model.

## Action classes
| Class | Examples | Default policy |
|---|---|---|
| Read-only | List tasks, inspect approved filenames | Allowed within granted scope |
| Local reversible | Create a draft in approved workspace | Confirm or workspace allowlist |
| Destructive | Delete or overwrite important files | Explicit approval |
| External side effect | Send, publish, submit | Explicit approval |
| High impact | Financial, legal, account/security changes | Out of MVP |

Every tool call records actor, capability, target, policy decision, and outcome.
