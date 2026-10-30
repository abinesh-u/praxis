# Praxis — 3-Minute Video Demonstration Script

**Target Video Duration:** 2 minutes 50 seconds (Safely under the 3:00 Devpost limit)  
**Resolution:** 1080p (1920x1080) at 60fps  
**Setup:** Split screen or quick tab switching between Terminal (left/fullscreen) and Web Browser (right/fullscreen).  

---

## ⏱️ Timeline & Storyboard

| Timestamp | Visual / Screen Action | Spoken Narration (Voiceover) |
| :--- | :--- | :--- |
| **0:00 – 0:25** | **Title Slide / Web UI Hero**<br>Display Praxis Web UI in Editorial Darkroom theme (`http://localhost:3000`). Calm, focused interface. | *"Most people don't need another app to manage their tasks. They need help actually doing them. Todo lists become overwhelming cemeteries of good intentions, while generic chatbots offer conversational advice without durable state or real execution boundaries. This is Praxis — a personal AI execution system built for the Nebius Global AI Hackathon."* |
| **0:25 – 0:50** | **CLI Terminal Screen**<br>Run `praxis doctor`<br>Show green checkmarks and Nebius Token Factory online status. | *"Praxis runs across a unified dual interface: a local-first CLI and a calm web dashboard. Let's run `praxis doctor`. Notice our AI Engine is connected directly to Nebius Token Factory, serving NVIDIA's open-source Nemotron 3.5 Lightning model for high-speed, structured reasoning."* |
| **0:50 – 1:20** | **CLI Commitment Capture**<br>Run:<br>`praxis capture "Review the auth token expiry check in jwt.py by tomorrow 5pm" --api` | *"Let's capture a natural commitment. Rather than just saving raw text, Praxis invokes Nebius Token Factory. Nemotron decomposes our intention into a concrete physical next action: 'Open jwt.py and inspect token expiry logic', and grounds 'tomorrow 5pm' into an exact ISO-8601 timestamp with our timezone. No vague planning, just immediate clarity."* |
| **1:20 – 1:45** | **Switch to Web UI (Browser)**<br>Press `1` (Today view).<br>Show the Spotlight Card and Actionable task.<br>Press `2` (Queue). | *"Switching to our web interface, designed with an editorial darkroom aesthetic to eliminate cognitive overload. The Today view highlights our actionable spotlight. When we inspect the task, Praxis separates planning from execution. It never assumes an action succeeded merely because an AI said so."* |
| **1:45 – 2:15** | **Approvals & Bounded Execution**<br>Click on Task or switch to Tab `3` (Approvals).<br>Show pending approval for consequential actions.<br>Click **Grant Approval** or run CLI `praxis approvals grant`. | *"For sensitive operations — like modifying code or dispatching webhooks — Praxis enforces human agency through single-use approval tokens cryptographically bound to the exact action parameters. Once approved, our bounded agent loop executes the allowlisted tool and records verifiable machine evidence in SQLite."* |
| **2:15 – 2:40** | **M8 Skills Library & Validation Gate**<br>Press `4` (Skills Library).<br>Show **Candidate Skills** in Quarantine.<br>Click to inspect provenance, receipt hash, and tool requirements.<br>Click **Promote Skill**. | *"Here is our standout innovation: procedural skill learning. When multi-step agent runs succeed, Praxis distills the procedure into reusable procedural knowledge. In Milestone 7, candidates are strictly quarantined to prevent prompt injection. In Milestone 8, operators review candidates here. Clicking Promote triggers our authoritative backend validation gate — verifying attempt completion, receipt hashes, and tool security before activating the skill into active prompt depth."* |
| **2:40 – 2:55** | **Full Suite Test Terminal**<br>Show terminal running `uv run pytest` (312 tests passing) and `uv run pytest tests/test_nebius_live.py`. | *"Behind this calm interface is an uncompromising engineering core: 312 passing tests, fail-closed tenant isolation, and live verified Nebius inference. Praxis turns good intentions into verified execution."* |
| **2:55 – 3:00** | **Closing Card**<br>Display GitHub Repo: `github.com/abinesh-u/praxis`<br>Praxis — Personal AI Execution Partner. | *"Thank you. Try Praxis today on GitHub!"* |

---

## 🎬 Recording Checklist & Pro Tips
1. **Pre-flight Check:**
   - Run `python scripts/demo_walkthrough.py --check` before hitting record.
   - Ensure the FastAPI server is running on `http://localhost:8000`.
   - Ensure the Next.js frontend is running on `http://localhost:3000`.
2. **Audio Quality:**
   - Use a clear microphone with minimal background noise.
   - Speak in a calm, confident, steady cadence.
3. **Screen Setup:**
   - Browser zoom set to 110% or 125% for crystal clear visibility on mobile/laptop screens.
   - Terminal font size set to 16px or 18px with high contrast theme.
4. **Export Settings:**
   - 1080p MP4 (H.264), 30fps or 60fps.
   - Total length strictly <= 2 minutes 55 seconds.
