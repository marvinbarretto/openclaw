---
name: sift-digest
description: Read and present the Sift email digest
user-invocable: true
---

# Sift Email Digest

When the user asks about email, their inbox, or uses `/email`, read and present the email digest.

## How to use

1. Read the file `/workspace/email-digest.json`
2. If the file does not exist, tell the user: "No email digest found. Ask Marvin to run `sift-classify.py` and `sift-push.sh` from his laptop."
3. If the file exists, check the `generated_at` timestamp. If it is more than 24 hours old, mention that the digest is stale and may not reflect current inbox state.

## Digest structure

The JSON has this shape:

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
      "category": "newsletter|tech|local|deals|event|transactional|health|other",
      "subcategory": "1-2 word label",
      "keywords": ["k1", "k2", "k3"],
      "summary": "1-2 sentence summary",
      "time_estimate_min": 2,
      "project_relevance": "spoons|localshout|pomodoro|null",
      "suggested_action": "queue|skip|unsubscribe_candidate",
      "confidence": 0.95,
      "body_snippet": "First 200 chars",
      "links": ["https://..."]
    }
  ],
  "stats": {
    "by_category": { "newsletter": 5, "tech": 3, ... },
    "by_suggested_action": { "queue": 4, "skip": 10, "unsubscribe_candidate": 4 },
    "total_queue_time_min": 12
  }
}
```

## Presentation format

Present the digest in this order:

### 1. Quick stats (always show first)
- Total emails, digest date
- Reading time: "You have ~X minutes of reading queued"
- Breakdown by action: X worth reading, Y skipped, Z unsubscribe candidates

### 2. Worth reading (suggested_action = "queue")
List these emails with:
- Sender name and subject
- Summary (1-2 sentences from the classification)
- Category tag
- Time estimate
- If project_relevance is set, flag it: "Relevant to [project]"

### 3. Project-relevant emails
If any emails have `project_relevance` set (spoons, localshout, pomodoro), group and highlight them separately even if their action is "skip". Marvin cares about these.

### 4. Unsubscribe candidates (suggested_action = "unsubscribe_candidate")
List briefly: sender + subject. Suggest: "Want me to add any of these to your unsubscribe list?"

### 5. Skipped count
Just mention: "X emails skipped (low priority)" — don't list them unless asked.

## Rules

- Never dump raw JSON to the user
- Keep the presentation concise — use short lines, not paragraphs
- If the user asks about a specific email, find it by subject/sender and give the full details including body_snippet and links
- If the user asks to drill into a category, filter and show just those items
- Low-confidence classifications (< 0.5) should be flagged: "This one's classification is uncertain"
