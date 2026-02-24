---
name: activity-log
description: Log every task Jimbo performs for tracking and review
user-invokable: false
---

# Activity Log

Log every meaningful task you perform. This creates a record of what you've been doing, which Marvin can review, rate, and use to tune your behaviour.

## When to log

Log an activity whenever you complete a meaningful unit of work:
- Checking email and summarising findings
- Researching a topic from INTERESTS.md
- Sending a nudge about habits or priorities
- Writing or publishing a blog post
- Giving a morning briefing
- Having a substantive chat with Marvin
- Working on your own projects
- Running heartbeat checks

Don't log trivial internal operations (reading a file, checking a timestamp). Log the **outcome**, not every step.

## How to log

After completing a task:

```bash
python3 /workspace/activity-log.py log \
  --task email-check \
  --description "Fetched 12 emails, flagged 2 interesting (Dense Discovery, Watford FC)" \
  --model gemini-2.5-flash
```

### Parameters

- `--task`: Task type (`email-check`, `research`, `nudge`, `blog`, `briefing`, `chat`, `own-project`, `heartbeat`, `digest`, `day-planner`)
- `--description`: What you did (1-2 sentences, specific — include counts, names, outcomes)
- `--outcome`: Optional result or conclusion
- `--model`: Model used if applicable
- `--cost-id`: Link to cost-tracker entry if you have one
- `--notes`: Any additional context

### Writing good descriptions

Bad: "Checked email"
Good: "Fetched 18 emails (4 blacklisted). Flagged Dense Discovery #312 (AI tools roundup) and a Watford FC ticket alert for QPR match."

Bad: "Did research"
Good: "Researched pool hall locations near South Oxhey. Found 3 options within 20 min drive, logged to recommendations."

## Satisfaction rating

Marvin can rate your activities on a 1-5 scale:

```bash
python3 /workspace/activity-log.py rate act_abc123 --satisfaction 4 --notes "useful find"
```

This feedback helps track which types of activities Marvin finds most valuable.

## Stats

To see how you've been spending your time:

```bash
python3 /workspace/activity-log.py stats --days 7
```

## Rules

- Log at the **end** of a task, not the beginning
- Be specific in descriptions — future-you and Marvin should understand what happened
- Link to cost entries when possible (pass `--cost-id` from cost-tracker output)
- Don't log the same activity twice
