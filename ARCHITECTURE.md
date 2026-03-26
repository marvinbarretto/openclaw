# Jimbo: How It All Works

**Last updated:** March 24, 2026

Jimbo is a personal AI assistant that lives on a small server in London. He connects to Telegram, reads your email, knows your calendar, tracks your tasks, and is slowly learning to be genuinely useful. This document explains how everything fits together and where we're heading.

---

## The Big Picture

Imagine you have three types of worker:

1. **The Postman** — delivers messages on a schedule, doesn't need to think about what's inside
2. **The Friend** — knows you, remembers your conversations, has opinions, makes you laugh
3. **The Genius** — brilliant but expensive to hire, so you save them for the really interesting work

Jimbo's architecture uses all three. The trick is knowing which worker to send for which job.

### The Postman (Python scripts)

These are small, fast programs that check data and send you Telegram messages. They don't use AI at all — they just look at numbers and make simple decisions.

- **"Is this email urgent?"** — checks a score that's already been calculated. If the score is high and the deadline is soon, it pings you. If not, silence.
- **"What's on my calendar?"** — reads your calendar, sorts events into "definitely happening" and "might be interesting", formats a clean summary.
- **"How's my task list?"** — checks how many tasks you have, whether anything got done this week, and suggests what to focus on today.
- **"Morning status"** — a 5-line snapshot of your day: calendar shape, email highlights, task focus, system health, one editorial line.

These run for free. No AI tokens, no API costs. They're like a well-organised inbox filter — mechanical but reliable.

### The Friend (Jimbo on OpenClaw)

This is the actual Jimbo you talk to on Telegram. He runs on [OpenClaw](https://openclaw.ai), an open-source platform for personal AI agents. He has:

- **Personality** — defined in a file called SOUL.md that describes who he is, how he talks, what he cares about
- **Memory** — he remembers your conversations, your preferences, your projects
- **Tools** — he can check your email, look at your calendar, search your task vault, even draft blog posts
- **A heartbeat** — every 30 minutes he wakes up and checks if there's something worth telling you about (a free gap in your calendar + an overdue task = "Hey, you're free until 3pm, want to tackle that Spoons PR?")

The key insight: Jimbo is expensive per interaction (the platform loads a lot of context to make him smart), so we only use him for things that genuinely benefit from his personality and judgment. Checking if an email score is above 9? That's arithmetic. Connecting a newsletter about AI architecture to your actual project goals and delivering it with editorial flair? That's Jimbo.

### The Genius (Opus)

Claude Opus is one of the most capable AI models available. We have free access through a Max plan subscription, running on a dedicated Mac. Opus handles the creative work that cheaper models struggle with:

- **The Surprise Game** — cross-references today's email gems with your task vault, priorities, and interests to find one genuinely non-obvious connection. Not "both mention AI" (boring) but "this comedy newsletter and that vault task about gamification illuminate the same idea from completely different angles" (delightful).
- **Weekly accountability** — looks at patterns across an entire week. What kept coming up? What got ignored? What's the honest assessment?
- **Blog drafting** — reads the interesting signals from your week and drafts posts with actual voice and opinion.
- **Deep analysis** — when you want a thorough briefing that actually thinks, not just formats.

Opus is an enhancement. If the Mac is asleep, everything else still works. The morning alerts still arrive. Jimbo still chats. Tasks still get tracked. Opus just makes the creative parts better when it's available.

---

## The Data Pipeline

Before any of the above can work, raw data needs to be fetched and processed. This happens automatically overnight and throughout the day:

```
Gmail API ──→ gmail-helper.py ──→ email-digest.json
                                      │
                              email_triage.py (Flash AI, cheap)
                                      │
                              newsletter_reader.py (Haiku AI, cheap)
                                      │
                              Scored insights stored in jimbo-api
                                      │
Google Calendar ──→ calendar-helper.py ──→ Events with tags
                                              │
Google Tasks ──→ tasks-helper.py ──→ Vault inbox
                                        │
                              prioritise-tasks.py (Flash AI)
                                        │
                              Scored tasks in jimbo-api
```

The pipeline uses small, cheap AI models (Google's Flash, Anthropic's Haiku) to do the heavy lifting: scoring emails for relevance, extracting gems from newsletters, prioritising tasks. This costs about 2-5 pence per day.

By the time The Postman scripts run, all the thinking has already been done. They just read the results and format messages.

---

## The Vault: Where Everything Connects

The vault is a collection of ~1,600 notes, tasks, bookmarks, ideas, and references. Think of it as a second brain — everything Marvin has ever captured ends up here, tagged and scored.

The vault is where the magic happens. When Jimbo spots an email about a flight deal to Buenos Aires, he can check: "Does Marvin have a travel goal? A Spanish language priority? A budget constraint?" All of that context lives in the vault and the priorities/interests/goals stored in jimbo-api.

Right now the vault is mostly a reading list. The vision is for it to become a **shared task system** — Jimbo creates tasks from signals he spots, Marvin accepts or delegates them, progress is tracked, and completed items stop being mentioned. No more nagging about the same Airbnb booking ten times.

---

## What Makes This Interesting

### 1. Zero-cost daily intelligence

The Postman scripts mean you wake up to a structured morning: calendar summary, urgent emails flagged, task focus suggested, system health confirmed — all without spending a single AI token. This is the baseline that never breaks.

### 2. Personality where it matters

Jimbo doesn't waste his personality on "your gym class is at 6:30." He saves it for "You've been tracking that Buenos Aires flight for two weeks and it just dropped below your threshold. The Spanish practice you've been skipping would pair nicely with actually going." That's where conversational AI adds value — connecting dots and delivering with voice.

### 3. Creative intelligence on tap

With Opus available for free, the surprise game can be genuinely good. Imagine: Opus reads 50 email newsletters, your entire task vault, your goals and interests, and finds the ONE connection you'd never have made. A philosophy debate event + the fact you're playing piano that evening + an AI ethics article = "Tonight you'll be making music AND arguing about creativity. Here's an article that bridges both."

### 4. The task loop (coming soon)

The real endgame isn't better alerts — it's a working task system:

- Jimbo reads an email about a concert pre-sale → creates a task with a deadline
- You tell Jimbo "I'll handle the Airbnb thing" → task assigned to you, Jimbo stops mentioning it
- You say "done" → task closed, velocity tracked
- Weekly review shows: "7 tasks completed, 3 new, you've been ignoring the YNAB setup for 2 weeks"

This turns Jimbo from a news feed into a collaborator.

---

## Future Direction: Thinking Bigger

Everything below builds on the same tiered architecture. The question for each idea is: does it need The Postman, The Friend, or The Genius? That determines cost and complexity.

---

### Phase 1: The Task Loop (next to build, ~$0/month extra)

This is the highest-leverage thing we can build. Right now Jimbo surfaces information but doesn't track what happens to it. The task loop closes that gap:

**How it works:**
- Jimbo spots a concert pre-sale in your email → creates a task with a deadline automatically
- You tell Jimbo "I'll handle the Airbnb thing" → task assigned to you, Jimbo stops mentioning it
- You say "done" → task closed, velocity tracked, no more nagging
- Vault status script reports: "7 completed this week, 3 new, YNAB setup ignored for 14 days"

**Why it matters:** This turns Jimbo from a news feed into a collaborator. Every other feature gets better once tasks are tracked — the morning summary shows progress, the accountability report has real data, nudges become relevant instead of repetitive.

**Cost:** Zero. The task loop lives in jimbo-api (already running) and Python scripts (already free). Jimbo's conversational handling of "I'll do this" / "done" uses his existing heartbeat — no extra turns.

---

### Phase 2: Voice Channel via Twilio (~$2-5/month)

OpenClaw has a native voice-call plugin supporting Twilio. This isn't just "phone alerts" — it's a full voice interface.

**What becomes possible:**
- **Critical escalation:** Telegram alert → 30 minutes unacknowledged → Jimbo calls your phone. "Hey, your API credits expire today and I haven't heard back. Want me to handle it?"
- **Verbal briefing:** Call Jimbo on your walk to the gym. "What's my day look like?" He reads the morning summary out loud, you respond verbally to adjust.
- **Quick capture:** "Jimbo, remind me to book the Buenos Aires flight when it drops below 800 pounds." Task created from a phone call while your hands are full.
- **Inbound conversations:** Jimbo answers calls with TTS (text-to-speech) via OpenAI or ElevenLabs. He sounds like a person, not a robot.

**Cost breakdown:**
| Item | Cost |
|------|------|
| Twilio phone number (US) | $1.15/month |
| Outbound calls (per minute) | $0.014/min |
| Inbound calls (per minute) | $0.0085/min |
| TTS (OpenAI) | ~$0.015/1000 characters |
| Estimated monthly (light use) | $2-5/month |

**The interesting bit:** Voice is the ultimate "hands-free" interface. Cooking dinner? Ask Jimbo what recipe from your vault matches the ingredients you have. Driving? Get the afternoon briefing read aloud. This is where a personal AI agent stops feeling like an app and starts feeling like an actual assistant.

---

### Phase 3: Autonomous Sub-Agents (~$5-20/month extra)

This is where it gets genuinely exciting. Instead of Jimbo doing everything himself, he delegates to specialist workers.

**The concept:** Jimbo spots a signal → decides it needs action → spawns a sub-agent with a focused task → sub-agent completes it → result posted back to Jimbo → Jimbo reports to you.

**Concrete examples:**

**Blog Drafter Agent**
Jimbo notices an interesting pattern across this week's email gems. He spawns an Opus job: "Draft a 500-word blog post connecting the AI regulation article, the Watford FC ownership debate, and Marvin's note about community governance." Opus writes the draft, posts it to the blog repo as a PR. Jimbo messages: "Drafted a post about governance patterns — want to review?" You approve or tweak, Jimbo merges and deploys.

Cost: Free if Opus is on Max plan. ~$0.15-0.30 per draft if using API Opus.

**Research Agent**
You ask Jimbo "Find me the best flights to Buenos Aires in April under £800." Jimbo spawns a research agent that checks flight APIs, compares options, and returns a structured summary. Or: "What are the reviews like for that restaurant near Union Chapel?" Agent searches, summarises, reports back.

Cost: Depends on model. Flash for simple searches (~$0.01), Opus for analysis (~$0.10-0.30).

**Code Review Agent**
Jimbo monitors your GitHub repos. When a PR comes in, he spawns a review agent that reads the diff, checks for obvious issues, and posts a comment. Not replacing human review — augmenting it. "The Sentry integration PR looks clean but the error handler doesn't cover the timeout case."

Cost: ~$0.05-0.15 per review depending on diff size and model.

**Event Scout Agent**
Weekly: Opus reads your interests, location, and calendar, then searches event platforms (Dice, Eventbrite, Meetup, ianVisits) for things you'd actually want to go to. Not generic recommendations — filtered through your actual taste profile. "Found 3 events this week: a philosophy debate at Conway Hall (matches your film club interest), a jazz jam at Southampton Arms (you go there for piano anyway), and a free coding meetup in Shoreditch (LocalShout networking)."

Cost: ~$0.10-0.30 per weekly run.

**Infrastructure cost for sub-agents:**
The current $12/month DigitalOcean droplet (1 vCPU, 2GB RAM) handles Jimbo fine, but sub-agents running concurrently would benefit from more resources:

| Setup | Spec | Cost | Good for |
|-------|------|------|----------|
| Current VPS | 1 vCPU, 2GB | $12/month | Jimbo + pipeline + 1-2 light agents |
| Upgraded VPS | 2 vCPU, 4GB | $24/month | Jimbo + pipeline + 3-4 concurrent agents |
| Second VPS (worker) | 2 vCPU, 4GB | $24/month | Dedicated agent worker pool |
| Dedicated Mac Mini | M-series, always-on | $0 (owned hardware) + electricity | Free Opus, heavy creative work |

The sweet spot is probably: keep the current VPS for Jimbo + pipeline, use the dedicated Mac for Opus jobs, and only upgrade/add a VPS if you're running enough concurrent agents to need it. Start with one agent (blog drafter), see how it performs, scale from there.

---

### Phase 4: Multi-Surface Jimbo (~$0-5/month extra)

Right now Jimbo lives on Telegram. OpenClaw supports 25+ chat platforms. The same brain, different interfaces:

- **Telegram** — personal: deals, events, hobbies, life admin, nudges
- **Slack** — work: project tasks, code reviews, deployment alerts, standup summaries
- **WhatsApp** — family/social: shared calendar, trip planning, recipe suggestions
- **Discord** — community: LocalShout updates, open-source project notifications
- **Email** — weekly digest: a beautiful HTML email summarising the week, sent to yourself or shared with others

Each channel gets its own personality filter. Telegram Jimbo is casual and opinionated. Slack Jimbo is professional and concise. WhatsApp Jimbo is warm and helpful. Same data, same vault, same task loop — different voice.

**Cost:** OpenClaw supports multiple channels natively. The only cost is the additional API keys and platform setup. Most are free.

---

### Phase 5: Learning and Patterns (~$0-10/month extra)

Every interaction generates data. Over months, genuine patterns emerge:

**Email intelligence:**
- Which newsletters consistently produce gems you act on? (Holiday Pirates: 40% booking rate. Fireship: 80% read rate. Marketing spam: 0%.)
- Auto-tune the blacklist and scoring based on actual engagement.

**Productivity patterns:**
- "You complete tasks 3x faster when tagged 'software' vs 'admin'."
- "Tuesday mornings are your most productive slot. Protect them."
- "Tasks older than 14 days have a 5% completion rate. Archive or do them."

**Taste refinement:**
- "You've booked 4 jazz events and 0 classical in 6 months. Adjusting recommendations."
- "Flight deals under £100 get booked 60% of the time. Over £200: never."
- "You read every article about AI agents but skip articles about crypto."

**How:** A monthly Opus job reads the activity log, email reports, task completion data, and produces an insights report. The insights feed back into scoring (email_triage.py weights, vault priority scores, nudge frequency). The system gets smarter over time, genuinely personalised in a way no generic AI assistant can match — because it's learning from YOUR data, YOUR actions, YOUR taste.

**Cost:** One Opus run per month on Max plan = free. Or ~$0.30-0.50 via API if Mac is unavailable.

---

### Phase 6: The Network Effect (speculative, ~$20-50/month)

What if Jimbo wasn't just for you?

**Jimbo as a platform:**
- Deploy Jimbo instances for friends, family, or clients. Each gets their own vault, preferences, and personality — but shares infrastructure.
- A "Jimbo for teams" — shared task vault, team calendar awareness, meeting prep, action item tracking.
- An open-source "Jimbo starter kit" — the scripts, skills, and API as a template anyone can deploy.

**Content from cross-referencing:**
- The surprise game produces genuinely novel connections. A curated daily "interesting connection" blog/newsletter could have an audience.
- Vault insights about productivity, reading patterns, and decision-making could become content. "What I learned from 6 months of AI-assisted email triage."

**Infrastructure at scale:**
| Setup | Cost | Supports |
|-------|------|----------|
| Single VPS + Mac | ~$14/month | 1 user (current) |
| Upgraded VPS + Mac | ~$26/month | 1 user with sub-agents |
| Multi-user VPS cluster | ~$50-100/month | 3-5 users with shared pipeline |
| Kubernetes on DigitalOcean | ~$100-200/month | 10+ users, auto-scaling |

This is speculative — but the architecture supports it. jimbo-api is already a multi-tenant-capable API. The Python scripts are stateless. OpenClaw supports multiple agents. The building blocks are there.

---

### What This Could Look Like in 6 Months

A realistic, funded-by-side-project version:

> You wake up. Your phone has 4 Telegram messages from overnight — not a wall of text, but labelled updates: [Email] urgent pre-sale expires at 10am, [Calendar] packed morning then free afternoon, [Vault] 3 tasks completed yesterday (nice streak), [Morning] "Good day for deep work — you've got 4 hours clear after gym."
>
> At 9:30, a surprise drops: Opus found that a philosophy podcast you bookmarked 3 months ago just released an episode about the exact AI governance topic coming up at tonight's meetup. Link included.
>
> You're cooking lunch and call Jimbo. "What should I make with the chicken and peppers in the fridge?" He searches your saved recipes, finds a match, reads the instructions while you cook.
>
> At 2pm, a Slack message: "LocalShout PR #47 looks good. One suggestion: the error handler doesn't cover timeouts. Want me to push a fix?" You say yes. Jimbo's code review agent creates a commit.
>
> At 8pm, the accountability report: "Solid day. 4 tasks done, 2 new from email. Blog draft ready for review. Flight to Buenos Aires dropped to £790 — below your threshold. Task created: book or dismiss by Friday."
>
> Monthly: "This month you completed 23 tasks (up from 15). You ignored YNAB for 30 days — archiving it. Tuesday mornings produced 60% of your deep work. Recommendation: block Tuesdays, move meetings to Thursday."

**Total cost of this vision: ~$30-40/month.** A dedicated VPS ($24), Twilio ($3), occasional API calls ($5-10), and a Mac you already own running Opus for free. That's less than a Netflix subscription for a genuinely personalised AI assistant that knows you, works for you, and gets smarter over time.

---

## The Architecture in One Sentence

**Python fetches and filters the world, jimbo-api stores the state, The Postman delivers the alerts, Jimbo brings the personality, and Opus brings the creativity — each doing what they're best at, nothing doing what they're not.**

---

## Current Status (March 2026)

| Component | Status | Cost |
|-----------|--------|------|
| Data pipeline (email, calendar, tasks) | Running | ~$0.03/day |
| jimbo-api (shared state, dashboard) | Running | $0 (self-hosted) |
| OpenClaw / Jimbo (conversation, nudges) | Running on Kimi K2 | $0 (free model) |
| Tier 1 Python alerts | Being built | $0 |
| Opus creative layer | Pending dedicated Mac | $0 (Max plan) |
| Voice calls (Twilio) | Pending phone number | ~$1/month |
| Task loop | Designed, not built | $0 |
| VPS hosting | DigitalOcean London | $12/month |

**Total monthly cost: ~$13-14/month** for a 24/7 personal AI assistant with email intelligence, calendar awareness, task management, and creative cross-referencing. Not bad.
