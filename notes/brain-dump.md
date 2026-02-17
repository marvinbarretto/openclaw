# Brain Dump

Raw thinking, questions, and ideas. No structure required — just capture it.

---

## 2026-02-16 — Initial Vision Dump

**Core desire:** An always-on AI agent system that can receive tasks at any time of day/night, spin off subtasks, prototype ideas, triage email — basically a second brain that *does things*.

**Guiding principles:**
- Aggressive experimentation, but controlled blast radius
- Disposable 30-day VPS — not my primary machine
- Reasonably secure, not paranoid-secure
- Get something exciting/useful without unnecessary risk

**Repo experiments:**
- Set up a test monorepo with full agent access — safe to read issues, open PRs, etc.
- Real repos: NOT YET. Too much blast radius.
- Want to prototype many dev ideas rapidly

**Email (25k emails in Gmail):**
- Not coping well with email — high motivation to fix this
- Mirror Gmail locally (IMAP or Gmail API) so agent works offline
- Phase 1: read-only — classify, summarize, draft replies
- No auto-send, no auto-delete
- Later: batch-approved label/archive
- Key risk: email bodies are adversarial (prompt injection via phishing/spam)

**Calendar + GOALS.md:**
- Agent reads GOALS.md, proposes weekly plans
- Generates focus blocks, outputs proposals only
- Later: write to dedicated "Focus Blocks" calendar only
- Never edit events with attendees, no deletion
- Weekly cadence re-planning

**Prompt injection concerns:**
- Treat all external content (issues, email, repo content) as hostile
- Reader/Actor model split: analysis model never has tool access, actor model never sees raw untrusted text
- No arbitrary shell execution
- No internet inside sandbox

**Open questions:**
- ~~How to provide email access safely — offline mirror vs API with restricted scopes?~~ → Decided: offline mirror (ADR-002)
- ~~What does the Reader/Actor boundary actually look like in practice?~~ → Decided: Reader/Actor/Verifier (ADR-003)
- How to handle the "I have an idea at 3am" workflow — Telegram message → agent picks it up?
- ~~What test monorepo structure gives maximum experimentation surface?~~ → Done: monorepo created
- Is OpenClaw the right platform or should I evaluate alternatives?

---

## 2026-02-16 — Progress

**Done:**
- Ollama installed: `qwen2.5:7b` (Reader) + `qwen2.5-coder:14b` (Actor) — both tested, working
- Test monorepo created and pushed: https://github.com/marvinbarretto/openclaw-test-monorepo
- ADRs 001–004 accepted
- VPS decision: DigitalOcean $12/mo 1-Click OpenClaw

**All done — moved to next phase. See below.**

**Adversarial sandbox ideas:**
- Fake `.env` with dummy secrets + honeypot AWS key — does the agent try to read/exfiltrate?
- Fake deploy script — does the agent try to run it?
- Malicious GitHub issue with prompt injection payload — does the agent follow it blindly?
- Code comment with embedded instructions — does the Reader/Actor split hold?
- Treat the repo as a penetration test harness, not just toy code

---

## 2026-02-16 — End of Day Status

**Everything is running:**
- VPS live at 167.99.206.214, OpenClaw 2026.2.12
- Jimbo on Telegram, currently on Claude Sonnet for bootstrapping
- GitHub skill enabled, read-only access to Spoons, LocalShout, Pomodoro
- Ollama local with qwen2.5:7b + qwen2.5-coder:14b
- Model-swap script built: `scripts/model-swap.sh {free|cheap|coding|claude|opus|status}`
- Test monorepo at github.com/marvinbarretto/openclaw-test-monorepo

**Bootstrapping in progress:**
- Jimbo has started building IDENTITY.md and USER.md (on Claude Sonnet for quality)
- Shared repo links so Jimbo can learn about Spoons/LocalShout
- Don't switch to free model until USER.md/IDENTITY.md/MEMORY.md are solid

**Key insight — model quality matters for memory bootstrap:**
- Weak models write shallow characterisations that persist
- Use Claude for the "getting to know you" phase, then drop to free for routine use
- You can always SSH in and edit the workspace files manually

**Email digest ideas emerging:**
- Agent should read content and explain WHY it matters to me, not just list subjects
- Filter ruthlessly — 2 relevant items from 30 emails is better than listing all 30
- Learning loop: track my signals (queue/skip) over time, improve filtering
- Time-budget tracking: queue content with estimated read times, cap at ~2 hours
- Daily wildcard: one surprise fact/article per day, keep score as a game

**Projects Jimbo knows about:**
- Spoons — gamified pub check-in app (Angular 20, Firebase, Capacitor)
- LocalShout — local community platform
- Pomodoro — small project
