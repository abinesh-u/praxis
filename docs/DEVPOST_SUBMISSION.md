# Praxis — Devpost Submission Entry

**Hackathon:** Nebius Global AI Hackathon 2026  
**Track:** Personal AI  
**Repository:** [https://github.com/abinesh-u/praxis](https://github.com/abinesh-u/praxis)  
**License:** MIT License  
**Eligible Model:** `nvidia/Nemotron-3_5-Lightning` via **Nebius Token Factory**  

---

## 🏷️ Elevator Pitch (under 200 characters)
*Praxis is a closed-loop personal AI execution partner that turns natural-language intentions into completed, verified actions using Nebius Token Factory and NVIDIA open-source models.*

---

## 💡 Inspiration
Modern knowledge workers and individuals struggling with executive function overhead, prospective memory lapses, and task-initiation inertia face a paradox: **they don't need another app to manage their tasks; they need help actually doing them.**

Traditional task managers are passive cemeteries of good intentions—todo lists grow endlessly, creating guilt, anxiety, and decision paralysis. On the other end of the spectrum, generic conversational AI chatbots provide open-ended text advice but lack durable state, real-world execution boundaries, and verification mechanisms. They cannot execute work on your behalf safely, and when they claim they did, you cannot trust them without proof.

We built **Praxis** to close the gap between *intention* and *execution*. Praxis is not a chat toy or another todo list. It is an opinionated, closed-loop execution partner designed to ground ambiguous commitments into physical next actions, guard consequential actions behind cryptographic human approval, execute bounded tools, verify outcomes through observable machine evidence, and distill reusable procedural skills.

---

## ⚙️ What It Does
Praxis provides a unified execution engine accessible through both a local-first terminal CLI and an editorial darkroom Next.js Web UI:

1. **Natural-Language Commitment Capture & AI Grounding:**
   - Users express commitments in natural conversational language (e.g., *"Review auth token expiry check in jwt.py by tomorrow 5pm"*).
   - Powered by **Nebius Token Factory** and **NVIDIA Nemotron 3.5 Lightning**, Praxis extracts the core obligation, resolves relative deadlines against the user's timezone into strict ISO-8601 timestamps, and decomposes the commitment into the single smallest, immediate physical next action.

2. **Today Agenda & Spotlight Prioritization:**
   - Instead of overwhelming users with a backlog of 50 tasks, Praxis surfaces a calm, focused **Today Agenda** with an actionable spotlight on the immediate next step.

3. **Bounded Autonomy & Cryptographic Human Agency:**
   - Praxis separates planning from execution.
   - Non-destructive steps run smoothly, but any consequential action (such as external webhooks, file writes, or credential access) triggers an explicit **Approval Gate**.
   - Approvals are single-use tokens cryptographically bound to the SHA-256 fingerprint of the exact action parameters. Tampering or replaying is impossible.

4. **Evidence-Based Completion & State Recovery:**
   - Praxis adheres strictly to **Evidence Over Assumptions**: an action is never considered complete simply because an LLM claimed it finished.
   - Execution attempts require verifiable machine evidence (e.g., provider transaction receipts, file hashes, HTTP response receipts).
   - If an external call times out or returns ambiguous status, Praxis preserves an `outcome_unknown` state and offers read-only reconciliation rather than blindly repeating destructive side effects.

5. **Procedural Skill Learning & Operator Validation Gate (M7 & M8):**
   - When multi-step agent workflows succeed, Praxis synthesizes machine evidence receipts and distills the procedure into reusable procedural knowledge.
   - **Candidate Quarantine (M7):** Unverified knowledge is strictly quarantined in storage and excluded from active prompt depth, preventing prompt injection or unvalidated instructions from hijacking future runs.
   - **Skills Library & Validation Gate (M8):** Operators inspect candidates via the Web UI (Tab `4`), reviewing source attempt provenance, evidence hashes, and tool requirements. Clicking **Promote Skill** triggers a multi-layer server validation gate (verifying SQLite attempt completion, cryptographic hash integrity, and tool allowlists) before activating the skill into prompt depth.

---

## 🛠️ How We Built It
Praxis was built as a clean modular monolith using a test-driven, security-first architecture:

- **Nebius Token Factory Integration:**
  - Runtime inference is routed through Nebius Token Factory (`https://api.tokenfactory.nebius.com/v1`) using `nvidia/Nemotron-3_5-Lightning`.
  - Built custom adapter [`NebiusTokenFactoryAdapter`](packages/core/src/praxis_core/models/providers/nebius.py) and [`NebiusTaskExtractor`](packages/core/src/praxis_core/models/extractor.py) handling token limits, timeout budgets, structured JSON schema validation, and offline fallbacks.
  - Model registry supports alternative profiles (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` and `nvidia/nemotron-3-super-120b-a12b`).
- **Backend API & Domain Core (`services/api`, `packages/core`):**
  - Python 3.13, FastAPI, Pydantic v2, and SQLite with unit-of-work persistence.
  - Fail-closed bearer token authentication isolating tenant data (cross-tenant requests return 404 with zero metadata disclosure).
  - Explicit finite-state machines for commitments, tasks, execution attempts, and approval lifecycles.
- **Agent Runtime & Skill Store (`packages/agent-runtime`):**
  - Bounded agent loop with strict tool call budgets, allowlisted filesystem tools (`fs_read_file`, `fs_write_file`, `fs_list_dir`), and reentrant locking (`threading.RLock()`) for atomic skill persistence (`tempfile.NamedTemporaryFile` + `os.replace`).
- **Editorial Darkroom Web UI (`apps/web`):**
  - Next.js 15, React 19, TypeScript, Tailwind CSS, and Radix UI primitives.
  - High-performance, anti-generic editorial darkroom aesthetic with tactile typography, keyboard navigation (`1`: Today, `2`: Queue, `3`: Approvals, `4`: Skills Library), candidate review modals, and real-time status transitions.
- **Command-Line Interface (`packages/cli`):**
  - Python Typer CLI with rich terminal formatting, diagnostic doctor checks (`praxis doctor`), and local or API-backed execution.

---

## 🧗 Challenges We Ran Into
1. **Model Hallucination of Execution Success:**
   - Early experiments showed LLMs frequently claim a task is complete when tools failed or timed out. We solved this by enforcing an architectural invariant: execution status is derived exclusively from typed tool receipts and database-backed evidence records, never from model-generated conversational text.
2. **Untrusted Procedural Knowledge & Prompt Injection:**
   - Allowing an agent to automatically generate instructions for future runs is a massive prompt injection vulnerability. If a malicious web response or file content enters the learning loop, it could inject persistent override headers. We resolved this through strict candidate quarantine, control tag sanitization (`<tool_call>`, `<system>`, `<prompt>`), and human operator promotion gates.
3. **Atomic File Persistence & Concurrency:**
   - Under concurrent review requests or multi-step execution, raw file writes risked partial reads or race conditions. We implemented slug-level reentrant locks combined with atomic POSIX file replacement (`tempfile` + `os.replace`), rejecting conflicting creates and ensuring terminal state transitions (rejected candidates cannot be retroactively promoted).
4. **Timezone & Relative Deadline Disambiguation:**
   - Converting phrases like *"by Friday 4pm"* into verifiable ISO-8601 strings requires strict reference time anchoring. We fed ISO reference timestamps and user timezone metadata directly into structured system prompts, achieving consistent deadline resolution with Nemotron.

---

## 🏆 Accomplishments That We're Proud Of
- **312 Automated Tests Passing in ~4.5s:** Comprehensive test suite spanning unit tests, SQLite persistence, schema migrations, adversarial security scenarios, and restart recovery.
- **Verified Live Nebius Token Factory Inference:** Built dedicated live smoke test suite [`tests/test_nebius_live.py`](tests/test_nebius_live.py) passing directly against the real Nebius API endpoint.
- **True Human Agency:** Approvals are not cosmetic UI checkboxes; they are single-use cryptographically bound authorization tokens enforced at the backend service boundary.
- **Dual Interface Parity:** Both the terminal CLI and the web application interact with the same underlying domain and persistence layer.
- **Anti-Generic Design Taste:** A calm, focused editorial darkroom UI designed specifically to lower cognitive load and promote task initiation.

---

## 📚 What We Learned
- **Bounded autonomy is the only safe autonomy:** Unbounded agent loops fail unpredictably. Explicit step budgets, allowlisted tools, and strict stop conditions make AI agents dependable partners rather than unpredictable liabilities.
- **NVIDIA Nemotron 3.5 Lightning excels at structured decomposition:** The model displayed remarkable speed and fidelity when parsing conversational input into strictly typed JSON schemas with ISO-8601 timestamps.
- **Quarantining learned procedural knowledge is essential:** Treating learned skills as untrusted candidates until validated bridges the gap between autonomous learning and enterprise security.

---

## 🚀 What's Next for Praxis
- **Multi-Channel Ingestion Gateways:** Telegram bot integration (already architected in `integrations/`) for instant audio note transcription and on-the-go capture.
- **Durable Scheduled Worker:** Asynchronous Celery/Redis queue for automated background reminders and periodic job claiming.
- **PostgreSQL Production Deployment:** Docker Compose deployment scripts targeting Nebius AI Cloud compute instances with managed PostgreSQL.
- **Expanded Capability Tool Packs:** Safe, bounded integrations for Google Calendar, GitHub PR reviews, and Slack status notifications.

---

## 🛠️ Built With
- `python`
- `fastapi`
- `nebius-token-factory`
- `nvidia-nemotron`
- `nextjs`
- `typescript`
- `tailwind-css`
- `sqlite`
- `pytest`
- `pydantic`
- `rich`
- `typer`

---

## 💬 Nebius Platform Feedback
1. **Token Factory API Speed & Reliability:** The OpenAI-compatible `/chat/completions` endpoint for `nvidia/Nemotron-3_5-Lightning` was exceptionally fast, consistently returning structured responses with low time-to-first-token.
2. **Developer Experience & Documentation:** Providing clear documentation for API keys and standard OpenAI SDK compatibility made integrating Nebius into custom Python adapters completely painless.
3. **Suggestions for Future Platform Capabilities:**
   - Native structured output / JSON Schema enforcement parameter (like OpenAI's `response_format: {"type": "json_schema"}`) would make complex schema validation even more seamless.
   - Built-in request tracing / observability dashboard within the Token Factory console to monitor latency, token usage, and rate limits in real time.
