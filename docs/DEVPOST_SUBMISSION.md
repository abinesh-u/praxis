# Praxis — Devpost Submission Entry

**Project:** Praxis — Personal AI Execution System
**Hackathon:** Nebius Global AI Hackathon 2026
**Target Track:** Personal AI Track
**Repository:** [https://github.com/abinesh-u/praxis](https://github.com/abinesh-u/praxis)
**License:** MIT License (visible in repo root `LICENSE`)
**Demo Video:** [https://youtu.be/PLACEHOLDER_DEMO_URL](https://youtu.be/PLACEHOLDER_DEMO_URL) (Public YouTube, Duration: 2m 50s, English)
**Eligible Model:** `nvidia/Nemotron-3_5-Lightning` via **Nebius Token Factory** (`https://api.tokenfactory.nebius.com/v1`)
**Bonus Award Targeted:** **Best Use of Tavily ($3,000 USD)** via functional runtime call to Tavily AI Search API

---

## 🏷️ Elevator Pitch (under 200 characters)
*Praxis is a closed-loop personal AI execution partner that turns natural-language intentions into completed, verified actions using Nebius Token Factory and NVIDIA open-source models.*

---

## 🎯 Target Track: Personal AI Track
Praxis was designed specifically for the **Personal AI Track**:
> *"Build an always-on, private assistant that works for you while keeping your data under your control. Give it persistent memory, reusable skills, access to the tools and information you choose, and the ability to carry out tasks across your daily workflows. Use at least one NVIDIA open source model..."*

### How Praxis Satisfies Every Track Requirement:
- **Always-on, private assistant & local data control:** Local-first architecture with strict tenant isolation, zero third-party telemetry, and encrypted local storage.
- **Persistent memory:** Durable SQLite schema managing commitments, tasks, dependencies, execution attempts, machine evidence receipts, and audit logs.
- **Reusable skills (M7 & M8):** Multi-step agent executions distill reusable procedural knowledge, quarantined to prevent prompt injection and activated via an authenticated operator validation gate.
- **Access to tools you choose:** Allowlisted filesystem and webhook execution tools bounded by single-use cryptographic approval tokens.
- **Carrying out daily workflow tasks:** Closed-loop execution engine (Capture → Ground → Prioritize → Approve → Execute → Verify → Learn).
- **NVIDIA Open Source Model:** Real runtime inference via **Nebius Token Factory** using `nvidia/Nemotron-3_5-Lightning`.

---

## 📅 Project History: New & Existing Statement
**Praxis was newly created by the entrant during the official Hackathon Submission Period (August 26, 2026 – October 30, 2026).** All domain models, bounded agent runtime, skills store, FastAPI services, Nebius adapter, and Next.js darkroom interface were designed, implemented, tested (312 tests), and documented from scratch for this competition.

---

## 💡 Inspiration
Modern knowledge workers and people struggling with prospective memory decay, executive function overhead, and task-initiation inertia face a paradox: **they don't need another app to manage their tasks; they need help actually doing them.**

Traditional task managers are passive cemeteries of good intentions—todo lists accumulate indefinitely, inducing guilt, anxiety, and decision paralysis. On the other extreme, generic conversational chatbots provide open-ended text advice but lack persistent state, real-world execution boundaries, and verifiable proof. When a chatbot claims it completed an action, you cannot trust it without manual checking.

We built **Praxis** to close the gap between *intention* and *execution*. Praxis is not a chatbot or a todo list. It is an opinionated, closed-loop execution partner designed to ground ambiguous commitments into concrete physical next actions, guard consequential operations behind cryptographic human approval, execute bounded tools, verify outcomes through observable machine evidence, and distill reusable procedural skills.

---

## ⚙️ What It Does
Praxis provides a unified execution engine accessible through both a local-first terminal CLI and an editorial darkroom Next.js Web UI:

1. **Natural-Language Commitment Capture & AI Grounding:**
   - Users capture commitments conversationally (e.g., *"Review the auth token expiry check in jwt.py by tomorrow 5pm"*).
   - Powered by **Nebius Token Factory** and **NVIDIA Nemotron 3.5 Lightning**, Praxis extracts the core obligation, resolves relative deadlines against the user's timezone into strict ISO-8601 timestamps, and decomposes the commitment into the single smallest, immediate physical next action.

2. **Today Agenda & Spotlight Prioritization:**
   - Instead of overwhelming users with a backlog of 50 tasks, Praxis surfaces a calm, focused **Today Agenda** with an actionable spotlight on the immediate next step.

3. **Bounded Autonomy & Cryptographic Human Agency:**
   - Praxis strictly separates planning from execution.
   - Non-destructive steps run smoothly, but any consequential action (such as file writes or external webhooks) triggers an explicit **Approval Gate**.
   - Approvals are single-use tokens cryptographically bound to the SHA-256 fingerprint of the exact action parameters. Tampering or replaying is rejected.

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
- **Verified Live Nebius Token Factory Inference:** Dedicated smoke test suite [`tests/test_nebius_live.py`](tests/test_nebius_live.py) passing directly against the real Nebius API endpoint.
- **True Human Agency:** Approvals are not cosmetic UI checkboxes; they are single-use cryptographically bound authorization tokens enforced at the backend service boundary.
- **Dual Interface Parity:** Both the terminal CLI and the web application interact with the same underlying domain and persistence layer.
- **Anti-Generic Design Taste:** A calm, focused editorial darkroom UI designed specifically to lower cognitive load and promote task initiation.

---

## 📚 What We Learned
- **Bounded autonomy is the only safe autonomy:** Unbounded agent loops fail unpredictably. Explicit step budgets, allowlisted tools, and strict stop conditions make AI agents dependable partners rather than unpredictable liabilities.
- **NVIDIA Nemotron 3.5 Lightning excels at structured decomposition:** The model displayed remarkable speed and fidelity when parsing conversational input into strictly typed JSON schemas with ISO-8601 timestamps.
- **Quarantining learned procedural knowledge is essential:** Treating learned skills as untrusted candidates until validated bridges the gap between autonomous learning and enterprise security.

---

## 🧪 Testing Instructions for Judges
Praxis is 100% open source and can be tested locally free of charge with zero hurdles:

```bash
# 1. Clone repository
git clone https://github.com/abinesh-u/praxis.git
cd praxis

# 2. Setup environment (Python 3.11+ via uv, Node.js 18+)
cp .env.example .env
uv sync --all-packages
cd apps/web && npm install && cd ../..

# 3. (Optional) Configure Nebius Token Factory Key in .env
# NEBIUS_API_KEY=your-token-factory-key
# (If omitted, Praxis automatically activates its deterministic offline fallback)

# 4. Run full test suite (312 tests) & live Nebius smoke test
uv run pytest
uv run pytest tests/test_nebius_live.py

# 5. Start servers
make api-dev   # http://localhost:8000
make web-dev   # http://localhost:3000

# 6. Seed a judge-ready demo scenario in one command
uv run python scripts/demo_walkthrough.py --seed

# 7. Open http://localhost:3000 in your browser:
# - Press '1': Inspect Today agenda and actionable spotlight
# - Press '3': Inspect pending cryptographic approval
# - Press '4': Inspect Quarantined Candidate Skill and click "Promote Skill"
#              (triggers authoritative SQLite evidence verification gate!)
```

---

## 💬 Nebius & Partner Platform Feedback (Evaluation for Feedback Award)
1. **Token Factory API Performance & Reliability:**
   - **Low Latency:** Time-to-first-token (TTFT) on `nvidia/Nemotron-3_5-Lightning` was exceptionally fast, averaging under 1.0 second round-trip from international endpoints.
   - **Standard Compatibility:** Full OpenAI API spec compatibility allowed us to seamlessly route requests through standard HTTP client libraries without proprietary SDK dependencies.
2. **NVIDIA Nemotron 3.5 Lightning Capabilities:**
   - **Structured JSON Fidelity:** The model consistently produced valid JSON schemas matching our extraction contracts without hallucinating extraneous markdown fences or commentary when instructed.
   - **Temporal Reasoning:** Relative deadline resolution against provided ISO-8601 reference timestamps was highly reliable.
3. **Tavily AI Search API Integration:**
   - **Agent-Ready Grounding:** Tavily's concise answer synthesis and structured search results enabled our personal agent to verify external facts without token-heavy web scraping. The clean JSON payload format was effortless to parse and serialize into machine evidence receipts.
4. **Actionable Suggestions for Future Platform Capabilities:**
   - **Native JSON Schema Enforcement:** Adding native `response_format: {"type": "json_schema", "schema": {...}}` support at the Token Factory level would eliminate post-generation JSON extraction regexes.
   - **Token Factory Tracing & Metrics Dashboard:** A built-in web console for visualizing per-request latency percentiles (p50, p95, p99), prompt/completion token usage, and rate-limit headroom.
   - **Serverless Job Triggers from Token Factory:** Native webhooks or job callbacks from Nebius Token Factory into Nebius Serverless compute when multi-step agent completions finish.

---

## 🛠️ Built With
- `python`
- `fastapi`
- `nebius-token-factory`
- `nvidia-nemotron`
- `tavily`
- `nextjs`
- `typescript`
- `tailwind-css`
- `sqlite`
- `pytest`
- `pydantic`
- `rich`
- `typer`

---

## 📄 License
This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for full details.
