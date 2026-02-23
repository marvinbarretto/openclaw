---
description: Interactively review needs-context vault notes — triage, classify, and move them
argument-hint: "[count] [oldest|newest|random]"
---

# Manual Review of Needs-Context Vault Notes

You are running an interactive review session for Marvin's personal notes vault. Notes in `data/vault/needs-context/` are items that the LLM classifier couldn't confidently categorise. Marvin will give you context so they can be properly classified and filed.

## Setup

1. Parse arguments from `$ARGUMENTS`:
   - First argument: batch size (default 5)
   - Second argument: sort order — `oldest` (default), `newest`, or `random`
   - Examples: `10 newest`, `5`, `20 random`, empty = `10 oldest`
2. Read `context/PATTERNS.md` — this tells you how Marvin's notes actually work
3. List files in `data/vault/needs-context/`, read up to N of them in the chosen sort order
4. If there are fewer files than requested, just use what's there

## Present the Batch

Show a numbered markdown table with all notes in the batch:

| # | Title | Source | Created | Preview |
|---|-------|--------|---------|---------|

- **Title**: from frontmatter `title` field
- **Source**: from frontmatter `source` field
- **Created**: from frontmatter `created` field, formatted as `YYYY-MM-DD (Xd ago)` — e.g. `2025-09-14 (527d ago)`
- **Preview**: first 60 chars of the body (after frontmatter), trimmed

After the table, wait for the user's response. They will typically give feedback for multiple notes at once.

## URL Enrichment

Before presenting a note, check if its body contains URLs. If so, try to enrich them:

**Twitter/X URLs** (x.com or twitter.com): Use WebFetch to call the oEmbed API:
```
https://publish.twitter.com/oembed?url=<tweet_url>
```
This returns the tweet text and author. Show it inline with the note.

**Other URLs**: Use WebFetch to fetch the page and extract a title/summary. If the fetch fails, just show the raw URL — don't block the review.

This enrichment is critical for notes that are just a bare URL — the URL IS the note, and without fetching it the note is unreviewable.

## Note-by-Note Review

For each note, show:

```
### Note N: [title]

**Source:** [source] | **List:** [source_list] | **Created:** [created]
**Current tags:** [tags]

> [full body content]

🔗 [Enriched URL content if available — tweet text, page title, summary]
```

Then ask what to do. Adapt to the user's response style:

- **If they give a complete answer** like "direct, type=media, tags=tv,drama" — just do it, no follow-up needed
- **If they say "direct" but don't specify details** — ask follow-up questions using AskUserQuestion with multiple choice for type, then tags
- **If they say "archive"** without a reason — ask for the stale reason
- **If they give context conversationally** like "this is a TV show I wanted to watch" — infer the action (that's a direct classify: type=media, tags from context) and confirm before processing
- **If they say "skip"** — move on, leave the file untouched
- **If they say "all — archive, stale"** or similar — apply the same action to all remaining notes in the batch

## Actions

### Direct (classify and move to notes/)

Update frontmatter: set `type`, `tags` (JSON array), `status` to `active`, `processed` to today (YYYY-MM-DD). Move file to `data/vault/notes/`.

### Context (add context, leave for reprocessing)

Prepend context text to note body (after frontmatter). Add `review_context` to frontmatter. Leave in `data/vault/needs-context/`.

### Archive (move to archive/)

Update frontmatter: set `status` to `archived`, `stale_reason`, `processed` to today (YYYY-MM-DD). Move file to `data/vault/archive/`.

### Skip

Do nothing.

## File Operations — Use review_helper.py

**CRITICAL: Do NOT use the Edit tool for frontmatter changes.** Edit shows diffs to the user which clutters the review session. Use `scripts/review_helper.py` via Bash instead — it's tested and silent.

**Direct or Archive (move + update frontmatter):**
```bash
python3 scripts/review_helper.py move <filepath> <dest_dir> '<json_updates>'
```

Example:
```bash
python3 scripts/review_helper.py move "data/vault/needs-context/dopesic--note_85ded1a.md" "data/vault/notes" '{"type": "media", "tags": ["tv", "drama"], "status": "active", "processed": "2026-02-23"}'
```

**Context (add context, no move):**
```bash
python3 scripts/review_helper.py context <filepath> '<context_text>'
```

Example:
```bash
python3 scripts/review_helper.py context "data/vault/needs-context/beer--note_b3fdc76.md" "This is about cheap beer prices in China, travel note"
```

For **direct**: dest_dir is `data/vault/notes`, updates must include type, tags, status=active, processed=today.
For **archive**: dest_dir is `data/vault/archive`, updates must include status=archived, stale_reason, processed=today.

## Reference: Type Taxonomy

bookmark, recipe, media, travel, idea, reference, event, task, checklist, person, finance, health, quote, journal, political

## Reference: Stale Reasons

stale, dead-url, completed, duplicate, past-event, empty

## Reference: Project Tags

project:localshout (venues, events, artists), project:film-planner (film/TV/shows), project:spoons (pub data), project:openclaw (Jimbo improvements)

## Session Summary

After processing all notes, print:

```
## Session complete
- X notes → notes/ (direct)
- X notes → given context (ready for reprocess)
- X notes → archive/
- X skipped
```

If you notice recurring patterns across 2+ notes not already in PATTERNS.md, mention them. Do NOT edit PATTERNS.md automatically.
