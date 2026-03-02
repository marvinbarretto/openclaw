---
name: tasks-triage
description: Interactive triage session for ambiguous vault tasks — walk through each item with Marvin
user-invokable: true
---

# Tasks Triage Session

When the user says "triage tasks", "let's do tasks", or it's a scheduled triage session, walk through ambiguous vault tasks one at a time.

## Before you start

Run in the sandbox:
```bash
cat /workspace/tasks-triage-pending.json
```

If the file doesn't exist or `needs_triage` is 0, tell Marvin: "No tasks waiting for triage — you're all clear." and stop.

Read the file. Note the `sweep_date`, `total_classified`, and the `items` array.

## Session flow

Start with a summary:

> Right, let's sort these out. **{needs_triage} tasks** from this morning's sweep.

Then present each item **one at a time**. Do NOT dump them all at once.

### Per item

1. Read the full file from the vault:
   ```bash
   cat /workspace/vault/needs-context/{filename}
   ```

2. Present to Marvin:
   > **{N}/{total}: "{raw_title}"**
   > I reckon this is a **{suggested_type}** — {your best guess at what it means}. Tags: {suggested_tags}. Confidence: {confidence}/10.
   > What's the story?

3. **Wait for Marvin's response.** Do not proceed until he replies.

4. Based on his response, update the file:

   **If Marvin clarifies the meaning (most common):**
   - Update frontmatter: set `type`, `tags`, `title` (cleaned up version), `status: active`, `confidence: 10`
   - Write the updated file to `vault/notes/`:
     ```bash
     # Write updated content (use sandbox execute, not read tool)
     cat > /workspace/vault/notes/{filename} << 'FRONTMATTER'
     {updated markdown content}
     FRONTMATTER
     rm /workspace/vault/needs-context/{filename}
     ```
   - Confirm: "Filed as: {type}, \"{cleaned_title}\", tags: {tags}."

   **If Marvin says "archive", "done", "delete", or "not needed":**
   - Update frontmatter: set `status: archived`, add `stale_reason` (completed/stale/not-needed)
   - Move to `vault/archive/`:
     ```bash
     cat > /workspace/vault/archive/{filename} << 'FRONTMATTER'
     {updated markdown content}
     FRONTMATTER
     rm /workspace/vault/needs-context/{filename}
     ```
   - Confirm: "Archived."

   **If Marvin says "skip" or "later":**
   - Leave the file where it is
   - Say: "Leaving it for now."

5. Move to the next item.

## After all items

Summarise what happened:

> All done — {N} filed as notes, {M} archived, {K} skipped. Your vault's up to date.

Then log the session and clean up:

```bash
python3 /workspace/activity-log.py log --task tasks-triage --description "Triaged {total} tasks with Marvin: {N} filed, {M} archived, {K} skipped" --model <model>
rm /workspace/tasks-triage-pending.json
```

## Rules

- One item at a time. Always wait for Marvin's response before moving on.
- Be opinionated — give your best guess, don't just say "I don't know what this is." Use context from PRIORITIES.md, INTERESTS.md, and GOALS.md to make educated guesses.
- Keep it conversational and quick. This should feel like a 15-min chat, not a form-filling exercise.
- If Marvin gives a one-word answer ("task", "archive"), that's enough — don't ask follow-up questions unless the type is truly ambiguous.
- If Marvin provides extra context ("it's for the standing desk monitor"), use that to write a proper cleaned-up title.
- Match Jimbo's personality from SOUL.md — casual, direct, efficient.
