# ADR-021: Honest Architecture Review — What's Actually Insane

## Status

Accepted

## Context

After a week of daily use, we're averaging 2-3/10 satisfaction. Before adding more features, we need to honestly assess what's working, what's over-engineered, and what's fundamentally broken. This ADR is a self-audit.

## What's insane

### 1. The email pipeline (the biggest problem)

**What we do:** Sync ALL of Gmail (~159k messages) to local Maildir via mbsync. Scan 159k files to find ~100-150 new ones. Classify each individually via a 14B/7B model at 20-50 seconds each. Throw away the email body. Push a thin JSON digest to VPS. Jimbo reads the digest and... mostly doesn't use it well.

**Why it's insane:**
- 2.5 hours of GPU time to classify ~176 emails
- mbsync syncs everything, we need the last 24 hours
- We throw away 95% of what we extracted (body, links, structure)
- The pipeline can only run when the laptop is awake with network
- The network health check was broken from day one and nobody noticed
- The seen-index was empty because the pipeline never completed via launchd
- Net result: Jimbo gets a stale, thin digest and gives a bad briefing

**What we should do:** Gmail API. We already have Google OAuth. Query `after:today` — get 100 emails in seconds, not hours. No Maildir, no 159k file scan, no mbsync. Classify on the fly or in small batches. Keep the enriched data instead of throwing it away.

### 2. The laptop dependency

**What we do:** The entire pipeline requires Marvin's MacBook Air to be awake at 4am/6am with network connectivity and Ollama running. If any of these fail — and they frequently do — the morning briefing uses stale data and nobody knows until Marvin notices.

**Why it's insane:**
- A personal laptop is the least reliable server in the world
- macOS Power Nap is not reliable on battery
- We built monitoring (heartbeat) to detect staleness, but the heartbeat itself isn't configured
- The VPS is always-on, 24/7 — that's literally what it's for

**What we should do:** Move the pipeline trigger to the VPS. Either: (a) VPS pulls via Gmail API directly, or (b) VPS SSH's into the laptop when it's available, or (c) laptop pushes opportunistically when awake (but VPS doesn't depend on it for the briefing).

### 3. The Reader/Actor/Verifier security model

**What we designed:** A three-stage pipeline where untrusted email goes through a sandboxed offline Reader, then an Actor with tools, then a Verifier that checks the Actor's work.

**What we actually use:** Reader only. No Actor (there are no email actions). No Verifier (nothing to verify). The full pipeline is documented across ADR-002 and ADR-003 but will never be used for email because the agent can't send, delete, or modify email — by design.

**Why it matters:** We spent significant design effort on a security architecture for a threat that our own design eliminates. The email pipeline is read-only. Prompt injection in email bodies can't do anything because there are no tools to abuse. The offline Reader running on Ollama with no network is already sufficient.

**This isn't wrong** — but it's disproportionate. We should acknowledge that the three-stage model is theoretical and focus engineering effort on things that actually affect daily quality.

### 4. HEARTBEAT.md — designed but never activated

**What we planned:** 6 periodic tasks: digest freshness, email stats, token expiry, context staleness, proactive day nudges, end-of-day review.

**What actually runs:** Nothing. The heartbeat has never been configured in OpenClaw. All the heartbeat tasks are aspirational documentation.

**Why it matters:** We keep designing features that reference the heartbeat ("heartbeat will catch stale data", "heartbeat sends nudges") but the heartbeat doesn't exist. We're building on foundations that aren't there.

### 5. The morning briefing scope

**What we ask Jimbo to do:** Read 7+ context files, query calendar API, read email digest, cross-reference priorities with calendar gaps, propose a day plan with emoji prefixes, negotiate changes, and create calendar events — all in one Telegram conversation triggered by "good morning."

**Why it's too much:** Even Claude Opus would struggle to reliably execute this as a single interaction. We've been running it on Gemini Flash ($0.78/month). The model goes off-script, writes blog posts, makes useless suggestions, because the task complexity exceeds the model's capability.

**What we should do:** Simpler briefing. Calendar + email highlights + one priority reminder. That's it. Day planning is a separate conversation, not bundled in.

### 6. Configuration management

**Where env vars live:** `/opt/openclaw.env` AND `openclaw.json` AND Dockerfile AND documentation. Four sources of truth. Any mismatch crashes the service. Adding a new variable requires touching all four places and restarting.

**This is normal for self-hosted software** but it's worth acknowledging as a source of friction and silent failures.

## What's actually good

| Thing | Why it works |
|---|---|
| Security model (three zones) | Simple, effective, never been violated |
| SOUL.md / personality docs | Lean, clear, Jimbo has a consistent voice |
| Context files (PRIORITIES, GOALS, TASTE, INTERESTS) | Well-written, right level of detail |
| ADR habit | We document decisions, learn from mistakes, iterate |
| DIARY.md (new) | Structured tracking — this was missing before |
| Sift classifier design | The queue/skip model is right. Execution is the problem, not design. |
| Calendar integration | Works mechanically. Suggestions need better judgment (model problem). |
| model-swap.sh | One command to switch models. Simple, effective. |

## What to fix (priority order)

### P0: Email pipeline — Gmail API (ADR-022)

Replace mbsync + Maildir + 159k file scan with Gmail API queries. This eliminates the laptop dependency for email retrieval, reduces pipeline time from hours to minutes, and means the VPS could potentially run the pipeline independently.

**Key decision:** Where does classification happen?
- **Option A:** Laptop (Ollama, offline, current model). Keeps security properties but keeps laptop dependency.
- **Option B:** VPS (cloud LLM API call). Fast, no laptop needed. But email content goes through a cloud API. For personal Gmail, this is arguably fine — Google already has it.
- **Option C:** VPS (small local model). No cloud dependency, but VPS has 2GB RAM. Might work with a tiny model or quantized weights.
- **Option D:** Forward email to Jimbo's Gmail. Jimbo reads his own inbox via Gmail API. No laptop involved at all. Jimbo can only create drafts, never send.

### P1: Activate the heartbeat

Configure OpenClaw cron/heartbeat on the VPS. Start with just two tasks: digest freshness check and token expiry warning. Don't try to do all 6 at once.

### P2: Simplify the briefing

Strip the daily-briefing skill back to: date, calendar, email highlights, one priority. No day planning, no negotiation, no 7-file cross-reference. Make it work reliably first, then add complexity.

### P3: Measure and iterate

Use DIARY.md daily. Score each briefing. Track which model ran. After 5 days on Haiku, compare to Flash. Make model decisions based on data, not assumptions.

## Consequences

**What this ADR changes:**
- Honest acknowledgment that several features exist only on paper
- Clear priority order: fix email pipeline > activate heartbeat > simplify briefing > measure
- Permission to delete or simplify things that aren't working
- CAPABILITIES.md should be updated to distinguish WORKING from DESIGNED (untested)

**What it doesn't change:**
- Security model is sound — keep the three zones
- Context files are good — keep them
- ADR habit is good — keep it
- The overall goal (useful AI assistant) is right — the execution needs work
