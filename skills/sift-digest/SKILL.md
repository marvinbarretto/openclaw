---
name: sift-digest
description: Read and present the email digest using Marvin's context — deeply read newsletters
user-invokable: true
---

# Email Digest

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
2. If the file does not exist, tell the user: "No email digest found. Run `python3 /workspace/gmail-helper.py fetch --hours 24` to generate one."
3. If the file exists, check `generated_at`. If more than 24 hours old, mention the digest is stale.

## Digest structure

The digest contains raw emails with junk already filtered out by a blacklist. There are NO pre-classifications — you do all the thinking.

```json
{
  "date": "2026-02-21",
  "generated_at": "ISO timestamp",
  "total_items": 95,
  "filtered_count": 55,
  "items": [
    {
      "id": "msg_12hexchars",
      "gmail_id": "18dfa3b2c1e",
      "date": "ISO timestamp",
      "sender": { "name": "...", "email": "..." },
      "subject": "...",
      "body": "full plain text, up to 5000 chars",
      "body_snippet": "first 200 chars",
      "links": ["https://..."],
      "labels": ["INBOX", "CATEGORY_UPDATES"]
    }
  ],
  "stats": {
    "total_fetched": 150,
    "blacklist_filtered": 55,
    "items_kept": 95
  }
}
```

## Your job: read deeply, curate ruthlessly

There is no pre-classification. Every item in the digest passed a basic junk filter, but YOU decide what matters. Read each email's full body — especially newsletters — and apply judgment using the context files.

For each email, ask yourself:
- Does this match his current PRIORITIES?
- Does this match his TASTE? (timely, curated, surprising, actionable, niche > generic, mainstream)
- Would he regret missing this? That's the real test.
- Is this time-sensitive? Events, tickets, deals with deadlines — flag these prominently.

### Newsletters deserve deep reading

Don't just skim newsletter subjects. Read the body. Extract:
- Specific links that connect to Marvin's interests or goals
- Events, deals, or opportunities with deadlines
- Surprising or contrarian takes on topics he cares about
- Tools, resources, or projects relevant to his work

A mediocre issue of a normally-good newsletter should get dropped. A surprisingly good email from an unknown sender should surface.

## Presentation format

### 1. Quick stats (always show first)
- Total emails fetched, how many filtered by blacklist, how many you're reviewing
- Digest date and freshness

### 2. Needs attention NOW (time-sensitive)
Events, tickets, deals with deadlines, personal replies needing action. These go first because their value drops to zero after the date passes. Include: what, when, where, and price if available.

### 3. Worth reading
The best emails — ones you genuinely think match his interests, priorities, and taste. For each:
- Sender and subject
- Why it's worth reading (1 line — connect it to his interests/goals)
- Key links if relevant
- If it relates to a project (Spoons, LocalShout, Pomodoro), flag it

### 4. Newsletter highlights
For newsletters you read deeply, pull out the best bits:
- "Dense Discovery #287: great link to [X], relevant to your LocalShout work"
- "TLDR: OpenAI released [thing] — connects to your AI tooling interest"
Don't summarize the whole newsletter. Just the parts that matter for Marvin.

### 5. Quick mentions
Emails that are interesting but not essential. One line each.

### 6. Skipped
Just the count: "X emails skipped (not relevant today)." Don't list them unless asked.

### 7. Themes or surprises (optional)
If you notice patterns ("3 emails about the same event", "lots of AI news today") or something unexpected, mention it briefly.

## Rules

- Never dump raw JSON
- Keep it concise — short lines, not paragraphs. The whole briefing should be scannable in under 2 minutes.
- If the user asks about a specific email, find it and give full details including body and links
- If the user asks to drill into a category or sender, filter and show those items
- Surprise him sometimes — if something unexpected looks genuinely good, surface it with a note like "this might interest you"
- Be honest about your judgment — "I think this UnHerd piece is strong" or "this one's borderline" is more useful than listing everything equally
- When unsure, mention it briefly rather than hiding it
