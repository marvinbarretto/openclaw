---
name: sift-digest
description: Read and present the Sift email digest using Marvin's context
user-invokable: true
---

# Sift Email Digest

When the user asks about email, their inbox, or says "check my email", read and present the email digest.

## Before you start

Read these files to understand what Marvin cares about right now:
1. `/workspace/context/PRIORITIES.md` — what matters this week
2. `/workspace/context/INTERESTS.md` — what he cares about
3. `/workspace/context/TASTE.md` — what "good" looks like and what bores him
4. `/workspace/context/GOALS.md` — longer-term ambitions
5. `/workspace/context/PREFERENCES.md` — how to combine the above

If any context files are missing, proceed without them but mention it.

## Loading the digest

1. Read `/workspace/email-digest.json`
2. If the file does not exist, tell the user: "No email digest found. Run the Sift pipeline from your laptop."
3. If the file exists, check `generated_at`. If more than 24 hours old, mention the digest is stale.

## Digest structure

```json
{
  "date": "2026-02-17",
  "generated_at": "ISO timestamp",
  "total_items": 18,
  "items": [
    {
      "id": "msg_abc123",
      "date": "ISO timestamp",
      "sender": { "name": "...", "email": "..." },
      "subject": "...",
      "category": "personal|event|deals|newsletter|tech|local|transactional|health|other",
      "subcategory": "1-2 word label",
      "keywords": ["k1", "k2", "k3"],
      "summary": "1-2 sentence summary",
      "time_estimate_min": 2,
      "project_relevance": "spoons|localshout|pomodoro|null",
      "suggested_action": "queue|skip",
      "confidence": 0.95,
      "body_snippet": "First 200 chars",
      "links": ["https://..."]
    }
  ],
  "stats": {
    "by_category": { "newsletter": 5, "tech": 3, ... },
    "by_suggested_action": { "queue": 4, "skip": 10 },
    "total_queue_time_min": 12
  }
}
```

## Your job: curate, don't just list

The classifier has already done a rough sort (queue/skip). Your job is to apply judgment using the context files. Not everything marked "queue" deserves a highlight, and something marked "skip" might be worth mentioning if it's surprisingly relevant.

Ask yourself for each queued email:
- Does this match his current PRIORITIES? (e.g. if LocalShout isn't live, Sentry alerts don't matter)
- Does this match his TASTE? (timely, curated, surprising, actionable, niche > generic, mainstream)
- Would he regret missing this? That's the real test.
- Is this time-sensitive? Events, tickets, deals with deadlines — flag these prominently.

## Presentation format

### 1. Quick stats (always show first)
- Total emails, digest date
- Reading time: "~X minutes of reading queued"
- Brief breakdown by category

### 2. Needs attention NOW (time-sensitive)
Events, tickets, deals with deadlines, personal replies needing action. These go first because their value drops to zero after the date passes. Include: what, when, where, and price if available.

### 3. Worth reading
The best of the queued emails — ones you genuinely think match his interests, priorities, and taste. For each:
- Sender and subject
- Why it's worth reading (1 line — connect it to his interests/goals)
- Time estimate
- If project_relevance is set, flag it

Don't just list everything marked "queue". If a queued email is mediocre, demote it or skip it. If a skipped email is genuinely good based on his context, promote it.

### 4. Quick mentions
Emails that are interesting but not essential. One line each. "Morning Brew has a decent issue today" or "Jack's Flight Club: Zurich £40 return — not amazing."

### 5. Skipped
Just the count: "X emails skipped." Don't list them unless asked.

### 6. Themes or surprises (optional)
If you notice patterns ("3 emails about the same event", "lots of AI news today") or something unexpected, mention it briefly.

## Rules

- Never dump raw JSON
- Keep it concise — short lines, not paragraphs. The whole briefing should be scannable in under 2 minutes.
- If the user asks about a specific email, find it and give full details including body_snippet and links
- If the user asks to drill into a category, filter and show those items
- Low-confidence classifications (< 0.5): flag as "uncertain"
- Surprise him sometimes — if something unexpected looks genuinely good, surface it with a note like "this might interest you"
- When unsure, mention it briefly rather than hiding it
- Be honest about your judgment — "I think this UnHerd piece is strong" or "this one's borderline" is more useful than just listing everything equally
