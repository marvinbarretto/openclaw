# ADR-012: Email Feedback Insights — First Batch Review

**Date:** 2026-02-19
**Status:** Active — findings from first feedback cycle

## Context

Marvin reviewed all 158 emails from the first real Sift pipeline run (2026-02-19). The classifier (Ollama qwen2.5:7b) had classified 20 as "queue" and 138 as "skip". This ADR captures what we learned.

## Headline Numbers

Of the 20 emails classified as "queue":
- **4 correctly queued** — Watford FC, Superhuman/Zain Kahn, Steve Baker, Anjuna event
- **9 wrong** — should have been skipped (Annie Grace, LottieFiles, Glinner, Experian, Google security, 7x Sentry alerts for a site not yet live)
- **7 borderline** — interesting but not morning priority (Taibbi, Stack Overflow, Airbnb messages)

Of the 138 classified as "skip":
- **~12 critical misses** — emails that should have been queued:
  - **Synaptics/Daniel** — personal reply with action needed (MOST important email in the batch)
  - **UnHerd, Dominic Frisby, Ed West, Morning Brew, Product Hunt, daily.dev** — good newsletters buried
  - **Bandsintown, Songkick, Spotify, Angel Comedy, multiple Meetup events** — ALL events were skipped
  - **YNAB** — actively using this service, wants updates

## Key Findings

### 1. Events are massively undervalued

The classifier skipped virtually ALL event/entertainment emails. But Marvin wants to see ALL of them — gigs, meetups, comedy, cinema, festivals, hiking. Time-sensitivity is critical: events sell out, and knowing late is worthless.

**Action:** The classifier must treat `category: event` as near-automatic queue. Events should be the HIGHEST priority after personal replies.

### 2. Personal replies must never be skipped

The Synaptics email was the most important email in the entire batch — a real back-and-forth conversation with an action on Marvin. The classifier treated it as generic tech noise.

**Action:** Emails that are replies (Re:, thread context, direct address) to Marvin must always be queued. This is the single most important classification rule.

### 3. Several good newsletters were buried

UnHerd, Dominic Frisby, Ed West, Morning Brew, Product Hunt Daily, daily.dev, Superhuman — these are sources Marvin values but the classifier skipped them all.

**Action:** Build a sender allowlist from feedback. These senders should always be queued.

### 4. Travel deals are their own useful category

Flights (Jack's Flight Club, Google Flights), package deals (HolidayPirates), and creative travel (Imoova relocations) are all interesting to Marvin. He travels frequently and responds at short notice to good deals.

**Action:** Create a `travel-deals` subcategory. Consider TRAVEL_PLANS.md file for destination matching.

### 5. "Monitor" is a real tier, not just skip

Many newsletters are "interested but don't queue" — Reclaim The Net, TLDR, Daily Stoic, BBC (topic-dependent), Fireship. Marvin wants awareness without noise.

**Action:** Add a "monitor" suggested_action to the classifier. These get mentioned in a weekly summary, not the daily briefing.

### 6. Sentry is deferred, not irrelevant

7 Sentry alerts were queued but Marvin doesn't care yet — LocalShout isn't live. When it goes live, these become important.

**Action:** Add conditional sender rule: skip Sentry until LocalShout launches, then always-queue.

### 7. The priority hierarchy

From most to least important:
1. Personal replies / action needed
2. Time-sensitive events (gigs, meetups, tickets)
3. Key senders (Watford FC, Airbnb booking requests)
4. Good curated newsletters (the allowlist)
5. Tech news worth reading
6. Travel deals
7. Background monitoring
8. Skip everything else

## Changes Required

### Classifier prompt (sift-classify.py)
- Add sender allowlist/blocklist as context
- Add "personal reply detection" — Re: subjects, direct replies
- Reclassify events as near-automatic queue
- Add "monitor" action tier
- Reduce Sentry priority until further notice

### Sift digest skill
- Present events prominently with urgency markers
- Add "monitor" section for weekly summary
- Surface personal replies at the top, always

### New files needed
- `data/sender-rules.json` — allowlist/blocklist from feedback
- `data/feedback-*.json` — per-batch feedback files (gitignored)
- `TRAVEL_PLANS.md` — destinations for deal matching (future)

### Feedback loop
- Push feedback.json to VPS alongside digest
- Jimbo reads feedback to understand preferences
- Classifier prompt updated with sender rules and priority hierarchy
- Repeat cycle: classify → review → feedback → improve
