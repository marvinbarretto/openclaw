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

2. Read ALL context files — both for making informed guesses and to track what needs updating:
   - `context/PRIORITIES.md` — what matters this week (note the "Last updated" date)
   - `context/INTERESTS.md` — what Marvin cares about
   - `context/GOALS.md` — longer-term ambitions
   - `context/TASTE.md` — what "good" looks like
   - `context/PREFERENCES.md` — how context files combine
   - `context/PATTERNS.md` — classification patterns from previous sessions

   As you read these, note anything that feels stale or incomplete. The triage conversation will reveal whether these files are accurate.

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

### Session summary

Summarise what happened:

> Done — **{N} filed** as notes, **{M} archived**, **{K} skipped**.

Clean up the pending file if we triaged all pending items:
```bash
ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) rm -f /workspace/tasks-triage-pending.json'
```

### Context file updates

During the triage, Marvin's explanations reveal what he actually cares about right now. Review the conversation and check whether any context files need updating.

**PRIORITIES.md** — Did any items reveal a new active focus or a completed/stale priority? Did Marvin say something like "oh I'm not doing that anymore" or "actually that's my main thing right now"? If so, propose specific edits.

**GOALS.md** — Did any items reveal a new ambition or a shifted goal? "That's about wanting to move abroad" might mean GOALS.md needs a new section.

**INTERESTS.md** — Did items reveal interests not currently listed? A "dating" task suggests a life area that INTERESTS.md doesn't cover. A "BuzzFeed work" item might reveal a career interest.

**PATTERNS.md** — Did you see recurring classification patterns across 2+ items that would help future automated classification? (e.g., "bare task titles with no context are usually ideas, not tasks")

For each proposed update:
1. Show the exact change as a before/after diff
2. Explain why the triage conversation supports this change
3. Ask Marvin to approve before writing

**Be bold with proposals.** If Marvin archived 3 items related to a priority that's clearly done, propose removing it from PRIORITIES.md. If a conversation revealed a whole area of life not in the context files, propose adding it. The context files should reflect reality, and triage sessions are where reality surfaces.

After approved edits, push updated context files to VPS:
```bash
./scripts/workspace-push.sh
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
