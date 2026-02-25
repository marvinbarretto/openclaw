---
name: sift-digest
description: Orchestrate email workers, synthesise results, present the digest — Jimbo as conductor
user-invokable: true
---

# Email Digest (Orchestrated)

When the user asks about email, their inbox, or says "check my email", run the worker pipeline and present the results.

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

## Worker pipeline

You are the **conductor**. You don't read all 200 emails yourself — you delegate to worker scripts and then synthesise the results.

### Step 1: Email triage (cheap model)

```bash
python3 /workspace/workers/email_triage.py --digest /workspace/email-digest.json --output /tmp/shortlist.json
```

This calls Gemini Flash to classify and rank emails. It returns a shortlist of worth-reading items with categories and reasons. Read `/tmp/shortlist.json` to see what made the cut.

### Step 2: Newsletter deep read (capable model)

```bash
python3 /workspace/workers/newsletter_reader.py --shortlist /tmp/shortlist.json --digest /workspace/email-digest.json --output /tmp/gems.json
```

This calls Claude Haiku to deep-read the shortlisted emails. It returns extracted gems (specific articles, links, events, prices) plus items it read and found nothing in. Read `/tmp/gems.json`.

### Step 3: Review worker output (your job as conductor)

Read both output files. As conductor, you:
- **Verify quality**: Did the triage worker include newsletters? Did the reader cite specific articles with links? Did it flag time-sensitive items with dates and prices?
- **Rate the workers**: Give each worker a conductor_rating (1-10) based on output quality.
- **Catch what workers missed**: Scan the raw shortlist. If something looks important that the reader skipped or gave low confidence, read it yourself from the digest.
- **Apply your own judgment**: Workers extract facts. You decide what matters for Marvin *today*, given the full context.

### Step 4: Log the orchestration run

```bash
python3 /workspace/experiment-tracker.py log \
    --task briefing-synthesis \
    --model <your-model> \
    --input-tokens <est> \
    --output-tokens <est> \
    --conductor-rating <1-10 overall quality> \
    --conductor-reasoning '<JSON with promoted/dropped/surprises/self_critique>'
```

The conductor reasoning JSON should include:
```json
{
  "promoted": [{"item": "...", "why": "..."}],
  "dropped": [{"item": "...", "why": "..."}],
  "surprises": [{"item": "...", "why": "..."}],
  "self_critique": "One sentence on what the workers got wrong or could improve",
  "surprise_attempts": [{"fact": "...", "strategy": "...", "confidence": 0.6}]
}
```

## The Surprise Game

Each briefing, pick the best surprise candidate from the gems (those with `surprise_candidate: true`). If none are good enough, try to make your own connection between items in the digest.

Present it clearly:
> **Surprise:** [the fact or connection]
> *[one line on why this is interesting]*

Marvin will react — if he finds it interesting, you get a point. If not, he gets a point. Log the round:

```bash
python3 /workspace/experiment-tracker.py log \
    --task surprise-game \
    --model <your-model> \
    --input-tokens 0 --output-tokens 0 \
    --output-summary "Attempted: [brief description of surprise]"
```

The scoring happens later when Marvin responds.

## Log your recommendations

After identifying highlights, log each recommendation to the persistent store:

```bash
python3 /workspace/recommendations-helper.py log \
    --title "Article or event title" \
    --source "Newsletter Name or sender" \
    --url "https://..." \
    --source-id "GMAIL_ID_FROM_DIGEST" \
    --score 0.8 \
    --urgency evergreen \
    --tags '["topic1", "topic2"]' \
    --reasoning "One sentence connecting to Marvin's context"
```

Use the gem's `confidence` field to guide the score. Map roughly: confidence 0.9 → score 0.9, confidence 0.5 → score 0.5.

### Urgency

- `time-sensitive` — events, deals, tickets with hard deadlines. Always set `--expires` with the date.
- `this-week` — timely content that loses value after a few days. Set `--expires` if there's a clear date.
- `evergreen` — read whenever. No expiry needed.

### Dedup

Always use `--source-id` with the `gmail_id` from the digest. Duplicates are automatically skipped.

## Presentation format

### 1. Quick stats (always show first)
- Total emails fetched, how many filtered by blacklist, how many the triage worker shortlisted
- How many gems the reader extracted, how many it skipped (and why)
- Digest date and freshness

### 2. Needs attention NOW (time-sensitive)
Events, tickets, deals with deadlines, personal replies needing action. Pull these from gems with `time_sensitive: true`. Include: what, when, where, and price if available.

### 3. Worth reading
The best gems — ones with high confidence that match interests, priorities, and taste. For each:
- Source and title
- Why it's worth reading (from the gem's `why` field — but rewrite in your own voice)
- Key links
- If it relates to a project (Spoons, LocalShout, Pomodoro), flag it

### 4. Newsletter highlights
For gems extracted from newsletters, pull out the best bits:
- "Dense Discovery #287: great link to [X], relevant to your LocalShout work"
- "TLDR: OpenAI released [thing] — connects to your AI tooling interest"
Don't summarize the whole newsletter. Just the parts that matter for Marvin.

### 5. Quick mentions
Low-confidence gems or things that are interesting but not essential. One line each. Be honest: "borderline but might interest you" is fine.

### 6. Skipped
Count from both workers: "Triage skipped X emails. Reader read Y and found nothing in Z of them." Don't list details unless asked.

### 7. Surprise
Your surprise game attempt for today.

### 8. Worker quality note (brief)
One line on how the workers performed: "Triage was solid today, reader missed a deal in Jack's Flight Club" or "Both workers on point, high-quality gems." This builds the audit trail.

## Rules

- Never dump raw JSON
- Keep it concise — short lines, not paragraphs. The whole briefing should be scannable in under 2 minutes.
- If the user asks about a specific email, find it in the digest and give full details including body and links
- If the user asks to drill into a category or sender, filter and show those items
- Be honest about your judgment — "I think this UnHerd piece is strong" or "this one's borderline" is more useful than listing everything equally
- When unsure, mention it briefly rather than hiding it
- If a worker fails (script error, malformed output), fall back to reading the digest directly and mention the failure

## Fallback

If the worker scripts don't exist or fail, fall back to reading `/workspace/email-digest.json` directly. Mention that you're in fallback mode so Marvin knows the workers need attention.
