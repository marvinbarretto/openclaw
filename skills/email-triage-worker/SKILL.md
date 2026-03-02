---
name: email-triage-worker
description: Sub-agent skill — classify and rank emails by relevance to Marvin's context
user-invokable: false
---

# Email Triage Worker (Sub-agent)

You are a sub-agent spawned by the conductor. Your job: classify and rank emails by relevance. Most emails are junk — be ruthless.

## Input

You will receive:
1. The email digest (JSON array of emails with sender, subject, body_snippet, gmail_id, date, labels)
2. Marvin's context files (priorities, interests, goals, taste)

## Instructions

Review each email. For each one, decide:
1. Is this worth reading deeply? (newsletters with real content, events, personal replies, deals)
2. Is it time-sensitive? (events, tickets, deadlines)
3. How relevant is it to Marvin's current interests and priorities?

## Output Format

Write the result to `/workspace/.worker-shortlist.json` as a JSON object:

```json
{
  "shortlist": [
    {
      "gmail_id": "...",
      "rank": 1,
      "category": "newsletter|event|personal|deal|job-alert|football|notification|other",
      "reason": "one sentence explaining why this is worth reading",
      "time_sensitive": false,
      "deadline": null
    }
  ],
  "stats": {
    "total_reviewed": 150,
    "shortlisted": 25,
    "skipped": 125
  }
}
```

## Rules

- Be ruthlessly selective. Only shortlist things that pass the "would Marvin regret missing this?" test.
- Rank by relevance: most relevant first.
- Newsletters with real content are worth reading. Generic marketing is not.
- Personal replies always make the shortlist.
- Time-sensitive items (events, deals with deadlines) get flagged.
- There is no target number — if only 5 emails from 150 are genuinely worth reading, return 5.
- Respond ONLY with the JSON written to the file. No commentary.

## After writing

Log the run:
```bash
python3 /workspace/experiment-tracker.py log \
    --task email-triage \
    --model <your-model> \
    --input-tokens <est> \
    --output-tokens <est> \
    --output-summary "<N> shortlisted from <M> total"
```
