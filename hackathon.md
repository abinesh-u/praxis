# HACKATHON.md — Praxis

**Project:** Praxis — Personal AI Execution System
**Hackathon:** Nebius Global AI Hackathon 2026
**Target Track:** Personal AI Track
**Repository:** https://github.com/abinesh-u/praxis
**License:** MIT License (visible and detectable at root)
**Sponsor:** Nebius B.V. (Schiphol, Netherlands)
**Administrator:** Devpost, Inc.

---

## 1. Official Dates and Timing

- **Submission Period:** Wednesday, August 26, 2026 (9:00 am Pacific Time) – Friday, October 30, 2026 (10:00 am Pacific Time / 10:30 pm IST).
- **Judging Period:** Wednesday, December 9, 2026 (9:00 am Pacific Time) – Wednesday, December 23, 2026 (12:00 pm Pacific Time).
- **Winners Announced:** On or around Monday, January 25, 2027 (12:00 pm Pacific Time).

---

## 2. Eligibility & Track Requirements

### Eligibility
- Open to individuals, teams, and organizations worldwide (including India).
- Entrant represents and warrants that the submission is original work and solely owned.
- Free, unrestricted testing access must be maintained for judges throughout the Judging Period (until December 23, 2026).

### Target Track: Personal AI Track
> *"Build an always-on, private assistant that works for you while keeping your data under your control. Give it persistent memory, reusable skills, access to the tools and information you choose, and the ability to carry out tasks across your daily workflows. Use at least one NVIDIA open source model, and use tools such as NVIDIA NemoClaw, OpenShell, Hermes Agent, and Nebius Serverless to bring personal AI to assemble, secure, and run your own personal AI system."*

### Praxis Track Alignment Matrix:
| Hackathon Requirement | Praxis Architecture Implementation |
| :--- | :--- |
| **Private assistant / Data control** | Local-first architecture, SQLite persistence, strict tenant isolation, no telemetry leak |
| **Persistent memory** | Durable SQLite tables for commitments, tasks, dependencies, execution attempts, and audit logs |
| **Reusable skills** | M7 verified procedural skill learning + M8 quarantined Skills Library & operator promotion gate |
| **Access to tools you choose** | Allowlisted filesystem and webhook tools; single-use cryptographically bound approvals |
| **Carry out daily tasks** | Closed-loop execution engine (Capture → Ground → Prioritize → Approve → Execute → Verify) |
| **NVIDIA open source model** | `nvidia/Nemotron-3_5-Lightning` served via **Nebius Token Factory** |

---

## 3. Mandatory Platform & Model Requirements

- **Nebius Token Factory Runtime Inference:**
  - Runtime inference calls to `https://api.tokenfactory.nebius.com/v1`.
  - Primary foundation model: `nvidia/Nemotron-3_5-Lightning`.
  - Registered fallback profiles: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` and `nvidia/nemotron-3-super-120b-a12b`.
- **Verified Live Test:**
  - Dedicated smoke test in `tests/test_nebius_live.py` executes against real Nebius endpoints.
- **Deterministic Offline Fallback:**
  - When running in local development without API keys, Praxis gracefully falls back to deterministic heuristic parsing without crashing.

---

## 4. Official Submission Checklist

All Devpost requirements must be satisfied before the deadline:

- [x] **Public Code Repository:** Hosted on GitHub at `https://github.com/abinesh-u/praxis`.
- [x] **Open Source License:** MIT License file visible in root (`LICENSE`) and detectable in GitHub About section.
- [x] **README Instructions:** `README.md` includes setup, environment configuration (`.env.example`), verification commands, and architecture overview.
- [x] **English Language:** All documentation, code comments, and demonstration materials are in English.
- [x] **New Creation Explanation:** Project was newly created during the official Submission Period (August 26, 2026 – October 30, 2026).
- [x] **NVIDIA / Nebius Documentation:** Prominently highlights the role of Nebius Token Factory and NVIDIA Nemotron in task decomposition and agent loop orchestration.
- [x] **Demonstration Video:**
  - Length strictly **under three (3) minutes** (< 3:00).
  - Uploaded to YouTube and made publicly visible.
  - Shows the project functioning on the intended device (CLI + Web UI).
  - Free from copyrighted music or third-party trademarks.
  - Follows storyboard in `docs/DEMO_VIDEO_SCRIPT.md`.
- [x] **Nebius & NVIDIA Platform Feedback:** Comprehensive feedback submitted covering Token Factory ergonomics, latency, and feature requests (`docs/DEVPOST_SUBMISSION.md`).
- [x] **Testing Access:** Clear instructions provided for judges to test locally with zero configuration barriers (`scripts/demo_walkthrough.py --seed`).

---

## 5. Judging Criteria (Stage Two - 4 Equally Weighted Pillars)

1. **Technological Implementation (25%):**
   - High-throughput integration with Nebius Token Factory using NVIDIA Nemotron 3.5 Lightning.
   - Robust Python FastAPI modular monolith + Next.js 15 Darkroom UI.
   - Comprehensive test suite (312 automated tests passing in ~4.5s).
2. **Design (25%):**
   - Coherent, complete product experience designed specifically to reduce executive overhead and task initiation friction.
   - Keyboard-driven darkroom interface (`1`: Today, `2`: Queue, `3`: Approvals, `4`: Skills Library).
3. **Potential Impact (25%):**
   - Directly addresses the pervasive problem of task initiation paralysis and prospective memory decay.
   - Shifts the paradigm from passive task management to active, verified execution.
4. **Quality of the Idea (25%):**
   - Non-obvious closed-loop architecture: bounded autonomy, evidence-based completion, and quarantined procedural skill learning.
   - Human agency preserved via single-use cryptographic authorization tokens.

---

## 6. Official Prizes Targeted

- **Personal AI Track Winner:** NVIDIA Jetson Orin Nano
- **Overall Awards:** Grand Prize ($20,000 USD), 2nd Place ($10,000 USD), 3rd Place ($6,000 USD)
- **Bonus Award:** Most Valuable Feedback ($100 USD + NVIDIA swag pack)
