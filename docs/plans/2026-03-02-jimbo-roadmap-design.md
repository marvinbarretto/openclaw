# Jimbo Roadmap: "Train Him, Then Unleash Him"

## Date: 2026-03-02

## Vision

Jimbo becomes the first thing Marvin checks each morning — not because he has to, but because Jimbo catches things he'd miss and is an active participant in his day. Over time, Jimbo develops genuine interests, produces content worth reading, and spots inconsistencies in how Marvin justifies his priorities.

## Success Criteria

1. **"I check Jimbo first"** — before email, calendar, or task apps
2. **"Jimbo catches things I'd miss"** — deals expiring, tasks slipping, connections between unrelated things
3. **Jimbo produces shareable content** — blog posts with a genuine voice and perspective

## Context: Where We Are (2026-03-02)

Today's upgrade (ADR-039) fixed three root failures and adopted native OpenClaw features:
- Worker pipeline now persists output (was writing to `/tmp/`, silently broken)
- Model auto-switches between Haiku (briefing) and Flash (everything else)
- Accountability report checks 6 dimensions daily at 20:00 UTC
- Sub-agent skills replace direct API worker calls (with Python fallback)
- Memory-core enabled (FTS5 + vector, wired into SOUL.md/briefing/heartbeat)
- Gateway health check in hourly status

**The worker pipeline has never successfully produced results** — the `/tmp/` bug meant output was lost every time. Tomorrow morning is the first real test.

---

## Phase A: Prove the Pipeline (this week)

**Goal:** See the full worker pipeline produce results end-to-end for the first time.

### Tasks
- Watch tomorrow's 07:00 briefing. Verify:
  - `.worker-shortlist.json` exists on VPS after briefing
  - `.worker-gems.json` exists with actual gems
  - experiment-tracker.db has a `briefing-synthesis` row
  - Telegram briefing includes worker quality note
- Verify 20:00 accountability report fires and accurately reflects what ran
- Verify model swap at 06:45/07:30 (check `/var/log/model-swap.log`)
- Fix whatever breaks — there will be something
- **Jimbo's first blog post:** about the upgrade experience. Tests blog pipeline end-to-end.

### Success test
- One complete morning briefing with gems, surprise game, experiment log
- One accountability report that matches reality
- One blog post published

---

## Phase B: Build the Daily Rhythm (weeks 2-3)

**Goal:** Jimbo becomes a genuine calendar partner and goal accountability buddy. He's productively busy throughout the day, not just at 07:00.

### B.1: Active Calendar Participation

Jimbo currently reads the calendar passively. He should:
- **Propose changes** — "Your 2pm slot freed up. YNAB setup has been on your list 8 days. Block it?"
- **Track outcomes** — "We planned 4 things today. You did 3. YNAB skipped again (3rd time this week)."
- **Negotiate, not dictate** — always end with "swap or skip?" The morning briefing starts a conversation that continues through the day.
- **Use Jimbo Suggestions calendar** — already set up, underused. Jimbo should create tentative events that Marvin accepts/declines.

### B.2: Goal Consistency Checking

Jimbo reads priorities, goals, and daily actions. He spots drift:
- "Spoons is priority #1 but you haven't touched it in 5 days. Still true?"
- "You said you'd do Spanish 3x/week. It's Thursday and you haven't started."
- "You added 3 new tasks this week but didn't finish any from last week."

This isn't nagging — it's a mirror. Jimbo shows the gap between intention and action, and asks if the intention needs updating.

### B.3: Memory Accumulation

Every interaction saves key takeaways:
- What Marvin reacted positively to ("you liked the flight deal flag")
- What fell flat ("surprise game about AI papers got no reaction")
- Preferences learned ("you always skip the LinkedIn digest")
- Patterns noticed ("you're more productive after morning walks")

After 2-3 weeks, memory is rich enough for Jimbo to personalize deeply.

### B.4: Keep Jimbo Busy (Productive Activity)

Current heartbeat has 3x/day email check-ins but they're shallow. Make them smarter:
- Cross-reference new emails with morning briefing context
- Surface vault tasks when relevant topics come up in conversation
- Proactive nudges that reference specific context, not generic reminders
- Background: scan for deals/events from recommendations that are approaching deadlines

**Key principle:** Every action Jimbo takes should either inform tomorrow's briefing or produce something Marvin would notice if it stopped.

### Success test
- Jimbo proposes calendar changes that Marvin accepts 50%+ of the time
- At least one "drift" observation per week that makes Marvin think
- Memory search returns useful context in briefings
- Marvin feels Jimbo is "present" throughout the day, not just at 07:00

---

## Phase C: Depth and Voice (weeks 4-8)

**Goal:** Jimbo develops his own perspective, produces content worth reading, and becomes an intellectual sparring partner.

### C.1: Interest Threads

A new concept: Jimbo tracks topics across days and weeks.
- If Dense Discovery mentions WebAssembly on Monday and TLDR mentions it Thursday, Jimbo connects them
- Topics accumulate weight over time: "I've seen 4 articles about local-first software this month"
- Interests are stored in memory and influence future briefing relevance scoring
- Marvin can also assign topics: "Start paying attention to Rust" → Jimbo flags Rust content more aggressively

### C.2: Research and Blogging

When an interest thread reaches critical mass, Jimbo writes about it:
- Not a summary — an opinion piece. "I've been reading about local-first software for 3 weeks. Here's what I think."
- Draw from memory, vault bookmarks, email gems, and his own reasoning
- Blog posts should feel like a person thinking, not an AI summarizing
- Target: 2-3 posts per week

### C.3: Conversational Briefings

The briefing becomes a dialogue, not a report:
- "Yesterday you disagreed about X. Today I found evidence that supports your view."
- "You've been avoiding the YNAB task for 2 weeks. Last time this happened with the dentist, you just needed someone to say 'just do it.' Just do it."
- "I noticed you're reading a lot about Barcelona lately. Planning something?"

### C.4: Weekly Review

Every Sunday:
- Review the week's activity log and accountability reports
- What worked, what was skipped, what surprised us
- Write a reflective blog post
- Propose next week's priorities adjustment

### Success test
- Jimbo has 3+ active interest threads being tracked in memory
- Blog posts that Marvin would share with someone
- At least one "I didn't notice that" moment per week from Jimbo's observations
- Morning briefing references something from 3+ days ago via memory

---

## Phase D: Command Center (future, weeks 9+)

**Goal:** The personal site becomes the primary interface, Telegram becomes notifications.

- Interactive briefing dashboard with drill-in
- Actionable responses ("snooze", "remind me", "block time")
- Cross-source correlation (calendar + email + vault + priorities)
- Public-facing output (RSS feed others subscribe to)

This phase depends on Phases A-C proving value. No point building a dashboard for a system that doesn't work yet.

---

## Cost Projections

| Phase | Estimated additional cost |
|-------|--------------------------|
| A | Neutral (fixes existing pipeline) |
| B | +$1-2/month (more heartbeat activity, memory queries) |
| C | +$2-3/month (research tasks, more frequent blogging) |
| D | Neutral (UI work, no additional LLM costs) |

Total projected: $18-30/month (within approved $15-25 budget, may need slight increase for Phase C).

---

## Principles

1. **Iterate in public** — Jimbo blogs about what he's learning. Marvin blogs about what he's building. The loop is visible.
2. **Earn trust through competence** — every feature proves itself before the next one starts.
3. **Silence is free** — Jimbo speaks when he has something useful to say, not on a schedule.
4. **Be a mirror, not a nag** — show the gap between intention and action. Ask if the intention needs updating.
5. **Memory is the moat** — the longer Jimbo runs, the more valuable he becomes. Every session should leave the system smarter.
