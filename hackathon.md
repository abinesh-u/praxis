# HACKATHON.md — Praxis

**Project:** Praxis — Personal AI Execution System  
**Hackathon:** Nebius Global AI Hackathon 2026  
**Target Track:** Personal AI  
**Purpose:** Mandatory constraints and implementation guidance for all coding agents.

## 1. Official Rules

Source of truth: https://nebiusglobalaihackathon.devpost.com/rules

- Read and comply with the official hackathon rules.
- Hackathon requirements take precedence over project preferences.
- Do not assume an API, model, or deployment approach is eligible without verification.
- Confirm Nebius Token Factory account provisioning and API access from India before committing to the implementation.
- Keep the final submission within the official submission window.

## 2. Mandatory Platform Requirements

- Make real runtime inference calls through **Nebius Token Factory**, or deploy the application on **Nebius AI Cloud**, as permitted by the rules.
- Use at least one eligible **NVIDIA open-source model**.
- Document the exact model identifier, provider, and integration path.
- Do not substitute an unrelated model provider for the mandatory NVIDIA/Nebius integration.
- Do not fake inference results or simulate platform integration in the final demo.

## 3. Product Definition

Praxis is a personal execution system for people who struggle to turn intentions into completed actions.

It helps users capture commitments, remember relevant context, plan next steps, schedule follow-ups, and execute permitted actions through controlled tools.

**Core product promise:** Turn intentions into reliable, verifiable execution.

Praxis is not merely a chatbot, task manager, or unrestricted autonomous agent.

## 4. Model Strategy

Start with **one eligible NVIDIA open-source model served through Nebius Token Factory**.

The previously proposed Nemotron model is a candidate, not a confirmed selection. Verify its exact identifier, current availability, open-source eligibility, pricing, and tool-calling capabilities before implementation.

Requirements:

- Keep the model provider behind a modular interface.
- Support structured outputs and tool-call orchestration in application code.
- Validate all model-generated arguments against schemas.
- Handle timeouts, rate limits, malformed responses, and provider errors.
- Evaluate task extraction, planning, and tool selection against representative examples.
- Do not introduce multi-model routing unless evaluation demonstrates a meaningful benefit.

## 5. MVP Priorities

Implement in this order:

1. **Task capture:** Convert natural-language input into structured commitments.
2. **Persistent memory:** Store tasks, deadlines, preferences, and relevant context.
3. **Execution engine:** Convert approved plans into bounded tool calls.
4. **Scheduling:** Persist reminders and execute due jobs reliably.
5. **Verification:** Record execution status, outcomes, and failures.
6. **User interface:** Provide a clear way to review tasks, approve actions, and inspect results.
7. **Demonstration:** Deliver one complete end-to-end workflow using real model inference.

Prioritize one polished, reliable workflow over numerous incomplete features.

## 6. Architecture Guardrails

- Separate the LLM interface, orchestration, memory, tools, scheduler, API, and user interface.
- Keep durable state in a persistent database.
- Treat scheduled jobs as application-managed, durable jobs—not in-memory timers alone.
- Keep credentials and secrets server-side and out of source control.
- Require user approval for sensitive or consequential actions.
- Apply least-privilege permissions to filesystem access and external integrations.
- Make execution idempotent where possible.
- Implement bounded retries, timeouts, audit logs, and explicit failure states.
- Never treat model-generated text as proof that an action succeeded.
- Verify actions against the relevant tool or system result.

## 7. Judging Priorities

The project must balance four equally weighted judging dimensions:

- **Technological implementation:** Genuine platform integration and a working technical system.
- **Design:** A coherent, usable experience.
- **Potential impact:** A meaningful user problem and credible benefit.
- **Quality of the idea:** A distinctive, well-executed product concept.

Do not optimize exclusively for backend sophistication. The final product must be understandable and demonstrable to judges.

## 8. Submission Requirements

Before submission, verify the current official rules and complete all applicable requirements:

- Public source-code repository.
- Recognized open-source license, visible in the repository.
- Clear README with setup, configuration, and execution instructions.
- Working application or demo that judges can access.
- Required NVIDIA/Nebius integration documented.
- Public YouTube demonstration under three minutes.
- English documentation and demonstration materials.
- Required hackathon/platform feedback submitted.
- Final Devpost entry submitted before the deadline.
- Any required judging credentials or access instructions provided securely.

**Target deadline:** October 30, 2026, at 10:00 a.m. Pacific Daylight Time (10:30 p.m. IST). Verify the official submission page before relying on this timestamp.

## 9. Definition of Done

The MVP is ready when:

- [ ] A real eligible NVIDIA model is called through the required platform integration.
- [ ] A user can submit a natural-language commitment.
- [ ] Praxis extracts and persists the structured task.
- [ ] A scheduled or tool-based action can be executed.
- [ ] The user can inspect the execution status and outcome.
- [ ] Failures are surfaced rather than falsely reported as success.
- [ ] The main workflow can be reproduced during a live demo.
- [ ] The repository and submission satisfy the applicable official rules.

## 10. Coding Agent Instructions

Before implementing a feature:

1. Read `HACKATHON.md`, `AGENTS.md`, and the relevant architecture documentation.
2. Check whether the feature supports the MVP or a mandatory requirement.
3. Prefer the smallest implementation that satisfies the requirement.
4. Keep changes modular, testable, and documented.
5. Add tests for critical execution paths and failure conditions.
6. Never hardcode credentials or fabricate integration results.
7. Record unresolved eligibility, access, or technical blockers explicitly.
8. Update documentation when architectural decisions change.

Do not build speculative infrastructure, unnecessary abstractions, or optional integrations before the core workflow works.

## Guiding Principle

**Build the smallest real, reliable, and judgeable version of Praxis that satisfies the hackathon requirements and demonstrates meaningful personal AI execution.**