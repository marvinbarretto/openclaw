---
description: Triage ambiguous vault tasks from VPS — discuss each item with Marvin and update the vault
argument-hint: "[count] [pending|backlog|all]"
---

# Tasks Triage Session

You are running a collaborative triage session for vault tasks that need Marvin's input. These are cryptic Google Tasks jottings that the classifier couldn't confidently categorise.

## Setup

1. Parse arguments from `$ARGUMENTS`:
   - First argument: batch size (default 10)
   - Second argument: source — `pending` (today's sweep, default), `backlog` (older needs-context items), or `all` (both)

2. Read context files for making informed guesses:
   - `context/PRIORITIES.md` — what matters this week
   - `context/INTERESTS.md` — what Marvin cares about
   - `context/GOALS.md` — longer-term ambitions

3. Pull data from VPS depending on source:

   **For `pending` (default):**
   ```bash
   ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) cat /workspace/tasks-triage-pending.json'
   ```
   If the file doesn't exist or `needs_triage` is 0, say "No pending tasks from today's sweep." and fall through to backlog if source is `all`.

   **For `backlog`:**
   ```bash
   ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) ls /workspace/vault/needs-context/'
   ```
   Then read files up to the batch size.

## Session Flow

Start with a summary:

> **{count} tasks to triage** — {source description}. Let's go through them.

Then present each item **one at a time**.

### Per Item

1. Read the full file from VPS:
   ```bash
   ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) cat /workspace/vault/needs-context/{filename}'
   ```

2. If the note contains URLs, try to enrich them with WebFetch to understand what they point to. A bare URL IS the note — without fetching it, the note is unreviewable.

3. Present to Marvin with your best guess:

   > **{N}/{total}: "{raw_title}"**
   >
   > Full content: {body content}
   >
   > My read: I think this is a **{suggested_type}** — {your interpretation of what it means, referencing priorities/interests/goals if relevant}. Confidence: {confidence}/10.
   >
   > What's the story?

4. **Wait for Marvin's response.** Do not proceed until he replies.

5. Based on his response, take action:

   **If Marvin clarifies the meaning (most common):**
   Build updated markdown with corrected frontmatter (type, tags, title, status: active, confidence: 10) and write it to vault/notes/:
   ```bash
   ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) sh -c "cat > /workspace/vault/notes/{filename}" << '"'"'ENDOFFILE'"'"'
   {updated markdown content}
   ENDOFFILE'
   ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) rm /workspace/vault/needs-context/{filename}'
   ```
   Confirm: "Filed as **{type}**: \"{cleaned_title}\", tags: {tags}."

   **If Marvin says "archive", "done", "delete", or "not needed":**
   Write to vault/archive/ with status: archived and stale_reason:
   ```bash
   ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) sh -c "cat > /workspace/vault/archive/{filename}" << '"'"'ENDOFFILE'"'"'
   {updated markdown content}
   ENDOFFILE'
   ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) rm /workspace/vault/needs-context/{filename}'
   ```
   Confirm: "Archived ({reason})."

   **If Marvin says "skip" or "later":**
   Leave the file where it is. Say: "Leaving it for now."

   **If Marvin gives a conversational answer** like "oh that's a TV show I wanted to watch":
   Infer the classification (type: media, tags: [tv]) and confirm before writing. Don't ask unnecessary follow-ups if the meaning is clear.

6. Move to the next item.

## After All Items

Summarise:

> Done — **{N} filed** as notes, **{M} archived**, **{K} skipped**.

Clean up the pending file if we triaged all pending items:
```bash
ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) rm -f /workspace/tasks-triage-pending.json'
```

## Reference: Type Taxonomy

bookmark, recipe, media, travel, idea, reference, event, task, checklist, person, finance, health, quote, journal, political

## Reference: Stale Reasons

stale, dead-url, completed, duplicate, past-event, empty, not-needed

## Reference: Project Tags

project:localshout, project:film-planner, project:spoons, project:openclaw, project:pomodoro

## Rules

- One item at a time. Always wait for Marvin's response.
- Be opinionated — use context files to make educated guesses. "I think this is about your DisplayLink monitor issue" is better than "I'm not sure what this is."
- Keep it conversational. This should feel like sorting through a drawer together, not filling in forms.
- If Marvin gives a one-word answer, that's enough. Don't over-ask.
- Enrich bare URLs before presenting — the URL content is often the whole point of the note.
- If a note clearly relates to a current priority or project, say so.
