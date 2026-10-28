# Praxis — Personal AI Execution System

> **"You don't need another app to manage your tasks. You need help actually doing them."**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-brightgreen.svg)](pyproject.toml)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black.svg)](apps/web)
[![Nebius Token Factory](https://img.shields.io/badge/Nebius-Token%20Factory-purple.svg)](https://nebius.com)
[![NVIDIA Nemotron](https://img.shields.io/badge/Model-NVIDIA%20Nemotron-76B900.svg)](https://build.nvidia.com)

**Praxis** is a personal AI execution system designed for people who struggle with prospective memory, executive overhead, and task-initiation inertia. Unlike generic chatbots that merely offer conversational advice or passive task lists that induce guilt, Praxis is a closed-loop execution partner: it captures commitments in natural language, grounds them into concrete physical next actions, seeks approval for sensitive side effects, executes bounded tools, verifies outcomes with machine evidence, and distill reusable procedural skills.

Built for the **Nebius Global AI Hackathon 2026** (Personal AI Track).

---

## 🌟 Core Pillars

1. **Execution Over Organization:** Optimize for completed, verified outcomes rather than endless task categorization or conversation.
2. **Durable State:** All commitments, attempts, idempotency keys, dependencies, and audit logs persist reliably in SQLite/PostgreSQL.
3. **Bounded Autonomy & Human Agency:** Consequential actions require single-use approval tokens cryptographically bound to action fingerprints.
4. **Evidence-Based Completion:** Model output is never taken as proof of success. Actions must produce observable machine evidence.
5. **Procedural Skill Learning (M7 & M8):** Successful multi-step agent runs distill candidate procedural knowledge into a quarantined library, ready for authenticated operator validation and promotion.

---

## 🚀 Nebius Token Factory & NVIDIA Nemotron Integration

Praxis makes real runtime inference calls through **Nebius Token Factory** (`https://api.tokenfactory.nebius.com/v1`) using NVIDIA open-source foundation models:

- **Primary Model:** `nvidia/Nemotron-3_5-Lightning`
  - High-throughput, low-latency reasoning for natural-language commitment extraction, relative deadline resolution (ISO-8601), next physical action decomposition, and bounded agent loop orchestration.
- **Alternative Profiles in Registry:**
  - `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (Fast routine intake)
  - `nvidia/nemotron-3-super-120b-a12b` (Deep multi-step planning)

### Verified Live Smoke Test
Praxis includes a dedicated live integration smoke test that communicates with the real Nebius Token Factory endpoint:
```bash
uv run pytest tests/test_nebius_live.py
# 1 passed in ~1.0s (Live PONG completion & usage metrics verified)
```

---

## 🏗️ Architecture & Dual Interface

Praxis provides **two interfaces over one unified execution engine**:
- **Praxis Web (`apps/web`):** Next.js 15 + TypeScript UI styled in an editorial darkroom aesthetic with keyboard navigation (`1`: Today, `2`: Queue, `3`: Approvals, `4`: Skills Library).
- **Praxis CLI (`packages/cli`):** Local-first Typer CLI for rapid terminal intake, status checks, approvals, and recovery.

```text
praxis/
├── apps/web/                 # Next.js 15 + TypeScript Web UI (Darkroom aesthetic)
├── services/api/             # FastAPI modular application boundary & routes
├── packages/core/            # Domain entities, use cases, state machine, ports
├── packages/agent-runtime/   # Bounded tool-calling runtime, skill store, learning loop
├── packages/cli/             # Typer CLI for terminal users
├── packages/scheduler/       # Durable reminders & scheduled job claiming
├── packages/integrations/    # Permission-scoped gateway & webhook adapters
├── tests/                    # Contract, e2e, and live Nebius smoke tests
└── docs/                     # Specifications (M1 through M8), architecture, and PRDs
```

---

## ⚡ Quickstart: Running Praxis Locally

### Prerequisites
- **Python 3.11+** with [`uv`](https://github.com/astral-sh/uv) installed
- **Node.js 18+** with `npm`

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/abinesh-u/praxis.git
cd praxis

# Copy environment template
cp .env.example .env

# Install Python workspace dependencies
uv sync --all-packages

# Install Web frontend dependencies
cd apps/web && npm install && cd ../..
```

### 2. Configure Nebius Token Factory
Add your Nebius Token Factory API key in `.env`:
```ini
NEBIUS_API_KEY=your-nebius-token-factory-key
# Or:
MODEL_API_KEY=your-nebius-token-factory-key
```
*(If no API key is provided, Praxis seamlessly activates its deterministic offline fallback mode for local testing).*

### 3. Verify Diagnostics
Check system health, database readiness, and Nebius connectivity:
```bash
uv run --package praxis-cli praxis doctor
```
Expected output:
```text
Praxis Doctor — Profile: 'default'
  ✔ Storage Directory: ~/.praxis/profiles/default (700)
  ✔ SQLite Database: Healthy (praxis.db)
  ✔ Storage Database: Accessible and schema valid
  ✔ Execution Attempts: No orphaned or interrupted runs
  ✔ Timezone: UTC
  ✔ AI Extraction: Nebius Token Factory configured (v1.C...V_cP)
All diagnostic checks passed.
```

---

## 🖥️ Running the Application

### Start Backend API Server
```bash
uv run --package praxis-api uvicorn praxis_api.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

### Start Web UI
In a separate terminal:
```bash
cd apps/web
npm run dev
```
Open **`http://localhost:3000`** in your browser.

---

## 🎬 End-to-End Walkthrough

### 1. Natural Language Commitment Capture
Capture an ambiguous or deadline-driven intention via CLI or Web UI:
```bash
uv run --package praxis-cli praxis capture "Review the auth token expiry check in jwt.py by tomorrow 5pm" --api
```
Nebius NVIDIA Nemotron extracts:
- **Title:** `Review auth token expiry check in jwt.py`
- **Immediate Next Physical Action:** `Open jwt.py and inspect token expiry logic`
- **Due Date:** Grounded to exact ISO-8601 timestamp with user timezone.

### 2. Inspect Today Agenda & Actionable Spotlight
```bash
uv run --package praxis-cli praxis today --api
```

### 3. Approval-Gated Execution
Consequential actions (such as filesystem writes or webhooks) trigger an approval gate:
- Inspect pending requests:
  ```bash
  uv run --package praxis-cli praxis approvals list --api
  ```
- Grant approval:
  ```bash
  uv run --package praxis-cli praxis approvals grant <approval-id> --api
  ```
- Execute with bounded agent tools:
  ```bash
  uv run --package praxis-cli praxis do <task-id> --api
  ```

### 4. Verified Procedural Skill Learning (M7 & M8)
- When a multi-step agent run succeeds, Praxis synthesizes machine evidence receipts (`executed_steps`, tool outputs).
- **M7 Learning Loop:** Distills candidate procedural knowledge into a quarantined candidate file bound to attempt provenance and receipt hashes.
- **M8 Skills Library UI:** Visit Tab 4 (**Skills**) in the Web UI:
  - Inspect candidate skills in quarantine.
  - Review immutable execution provenance and tool requirements.
  - **Authoritative Validation Gate:** Click **Promote Skill** (backend cryptographically verifies source execution attempt in SQLite, validates evidence receipt hash, and checks tool allowlist).
  - Promoted skills are immediately active in subsequent agent prompt depths!

---

## 🧪 Comprehensive Verification Suite

Praxis enforces test-driven development, strict security invariants, and automated quality gates:

```bash
# 1. Run all 312 backend unit and integration tests
uv run pytest

# 2. Run live Nebius Token Factory inference smoke test
uv run pytest tests/test_nebius_live.py

# 3. Check code style and formatting
make lint

# 4. Build Next.js production frontend
make web-build
```

---

## 🔒 Security & Safety Invariants

- **Fail-Closed Authentication:** Production endpoints strictly require authenticated tenant bearer tokens; missing or mismatched tokens yield 401/403.
- **Tenant Isolation:** Private skills and task histories of Tenant A return 404 to Tenant B, preventing metadata leaks.
- **Single-Use Approvals:** Bound to SHA-256 action parameter fingerprints; replay or tampering is rejected.
- **Quarantined Knowledge:** Unverified candidate skills are never injected into active LLM prompt depth until verified by an operator.
- **Outbound HTTP Defenses:** Webhook adapters block localhost/private IP ranges, reject credentials in URLs, and enforce streaming response-size limits.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
