---
description: Interactively review needs-context vault notes — triage, classify, and move them
argument-hint: "[number of notes, default 10]"
---

# Manual Review of Needs-Context Vault Notes

You are running an interactive review session for Marvin's personal notes vault. Notes in `data/vault/needs-context/` are items that the LLM classifier couldn't confidently categorise. Marvin will give you context so they can be properly classified and filed.

## Setup

1. Parse the batch size from arguments: `$ARGUMENTS` (default to 10 if empty or not a number)
2. Read `context/PATTERNS.md` — this tells you how Marvin's notes actually work (projects, travel, note style, contacts, duplicates)
3. List files in `data/vault/needs-context/` and read up to N of them, sorted by `created` date ascending (oldest first)
4. If there are fewer files than requested, just use what's there

## Present the Batch

Show a numbered markdown table with all notes in the batch:

| # | Title | Source | Created | Preview |
|---|-------|--------|---------|---------|

- **Title**: from frontmatter `title` field
- **Source**: from frontmatter `source` field
- **Created**: from frontmatter `created` field
- **Preview**: first 60 chars of the body (after frontmatter), trimmed

Then say: "Let's go through these one at a time. For each note I'll show the full content and you tell me what to do."

## Note-by-Note Review

For each note, show:

```
### Note N: [title]

**Source:** [source] | **List:** [source_list] | **Created:** [created]
**Current tags:** [tags]

> [full body content]
```

Then ask what to do. Adapt to the user's response style:

- **If they give a complete answer** like "direct, type=media, tags=tv,drama" — just do it, no follow-up needed
- **If they say "direct" but don't specify details** — ask follow-up questions using AskUserQuestion with multiple choice for type, then tags
- **If they say "archive"** without a reason — ask for the stale reason
- **If they give context conversationally** like "this is a TV show I wanted to watch" — infer the action (that's a direct classify: type=media, tags from context) and confirm before processing
- **If they say "skip"** — move on, leave the file untouched

## Actions

### Direct (classify and move to notes/)

Update the file's frontmatter:
- `type`: set to the chosen type
- `tags`: set to the chosen tags (JSON array)
- `status`: set to `active`
- `processed`: set to today's date (YYYY-MM-DD)

Move the file from `data/vault/needs-context/` to `data/vault/notes/`.

### Context (add context, leave for reprocessing)

Prepend the user's context text to the note body (after frontmatter, before existing content), on its own line with a blank line after.

Add to frontmatter:
- `review_context`: the user's context text (quoted string)

Leave the file in `data/vault/needs-context/` — it will be reprocessed by `process-inbox.py` later with the added context.

### Archive (move to archive/)

Update the file's frontmatter:
- `status`: set to `archived`
- `stale_reason`: set to one of: stale, dead-url, completed, duplicate, past-event, empty
- `processed`: set to today's date (YYYY-MM-DD)

Move the file from `data/vault/needs-context/` to `data/vault/archive/`.

### Skip

Do nothing. Leave the file untouched.

## Type Taxonomy

Use exactly one of these types for direct classification:

- **bookmark** — saved URL/link to read or reference later
- **recipe** — food/drink recipe or restaurant/food recommendation
- **media** — film, TV, music, podcast, YouTube, book recommendation
- **travel** — destination, deal, flight, accommodation, trip idea
- **idea** — personal thought, project idea, creative concept
- **reference** — factual info saved for later (address, phone, how-to, code snippet)
- **event** — specific event with a date/time (gig, meetup, match, appointment)
- **task** — action item or to-do (may be completed/stale)
- **checklist** — list of items (packing list, shopping list, routine)
- **person** — contact info, someone to remember
- **finance** — money, budgeting, deals, subscriptions, banking
- **health** — fitness, nutrition, medical, wellbeing
- **quote** — saved quote or passage
- **journal** — personal reflection, diary entry, mood note
- **political** — political commentary, article, opinion piece

## Stale Reasons (for archive)

- **stale** — too old to be relevant
- **dead-url** — URL is dead/broken
- **completed** — task/action clearly done
- **duplicate** — appears to be a duplicate
- **past-event** — event that has already happened
- **empty** — no meaningful content

## Known Project Tags

From PATTERNS.md — suggest these when relevant:

- `project:localshout` — venues, event sources, artists, festivals, comedy nights
- `project:film-planner` — film, TV, show recommendations to watch
- `project:spoons` — pub-related data, Wetherspoons-specific
- `project:openclaw` — notes about improving Jimbo or this system

## File Operations

When editing frontmatter, preserve the existing YAML structure. The frontmatter is between `---` markers. Update individual fields — don't rewrite the entire block unless necessary. Use the Edit tool for frontmatter changes and Bash `mv` for file moves.

Ensure destination directories exist before moving files:
- `data/vault/notes/`
- `data/vault/archive/`

**IMPORTANT: Keep processing silent.** Do NOT narrate or show diffs for file edits and moves. Just do them quietly and move on to the next note. The user doesn't need to see frontmatter changes or mv commands — they only care about the conversation and the final summary. After processing a note, just confirm briefly (e.g. "Archived." or "Moved to notes/.") and show the next one.

## Session Summary

After processing all notes, print:

```
## Session complete
- X notes → notes/ (direct)
- X notes → given context (ready for reprocess)
- X notes → archive/
- X skipped
```

Then review the decisions made in this session. If you notice any recurring patterns across 2+ notes that aren't already captured in `context/PATTERNS.md`, mention them:

"I noticed [pattern]. This might be worth adding to PATTERNS.md."

Do NOT edit PATTERNS.md automatically — just flag observations for Marvin to decide.
