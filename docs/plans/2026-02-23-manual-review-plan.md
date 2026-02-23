# /manual-review Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Claude Code custom command that lets Marvin interactively review needs-context vault notes.

**Architecture:** A single markdown prompt file at `.claude/commands/manual-review.md` that instructs Claude Code how to run a review session. No scripts, no infrastructure — just a well-crafted prompt.

**Tech Stack:** Claude Code custom commands (markdown + $ARGUMENTS)

---

### Task 1: Create the .claude/commands directory

**Files:**
- Create: `.claude/commands/` (directory)

**Step 1: Create directory**

```bash
mkdir -p .claude/commands
```

**Step 2: Commit**

```bash
git add .claude/commands/.gitkeep 2>/dev/null; git commit --allow-empty -m "chore: create .claude/commands directory"
```

---

### Task 2: Write the manual-review command

**Files:**
- Create: `.claude/commands/manual-review.md`
- Reference: `context/PATTERNS.md` (for project tags and classification patterns)
- Reference: `scripts/process-inbox.py` (for type taxonomy and frontmatter schema)
- Reference: `data/vault/needs-context/*.md` (example note format)

**Step 1: Write the command file**

The command file needs these sections:

1. **Frontmatter** — description and argument hint
2. **Setup instructions** — what to read before starting (PATTERNS.md, count of files)
3. **Presentation format** — how to show the batch table
4. **Note-by-note review** — how to present each note and handle responses
5. **Action definitions** — direct/context/archive/skip with exact frontmatter changes
6. **Type taxonomy** — the full list so Claude doesn't have to look it up
7. **File operations** — how to update frontmatter and move files
8. **Session summary** — what to print at the end

Key details the prompt must encode:
- `$ARGUMENTS` is the batch size, default 10
- Read files from `data/vault/needs-context/`, sorted by `created` date ascending (oldest first)
- Parse YAML frontmatter using the same format as process-inbox.py
- Type taxonomy: bookmark, recipe, media, travel, idea, reference, event, task, checklist, person, finance, health, quote, journal, political
- Stale reasons: stale, dead-url, completed, duplicate, past-event, empty
- Project tags from PATTERNS.md: project:localshout, project:film-planner, project:spoons, project:openclaw
- For "direct": set status=active, type, tags, processed=today's date, move to `data/vault/notes/`
- For "context": prepend text to body, add review_context field to frontmatter, leave in needs-context/
- For "archive": set status=archived, stale_reason, processed=today's date, move to `data/vault/archive/`
- When user gives a full answer, just do it. When vague, ask follow-ups with multiple choice.
- At end: print summary counts, mention any pattern observations

**Step 2: Verify command is discoverable**

Run Claude Code and check that `/manual-review` appears in the command list.

**Step 3: Commit**

```bash
git add .claude/commands/manual-review.md
git commit -m "feat: add /manual-review command for vault note triage"
```

---

### Task 3: Smoke test with a dry run

**Step 1: Run the command**

```
/manual-review 3
```

**Step 2: Verify behaviour**

- Does it read 3 files from needs-context/?
- Does it present a table?
- Does it walk through notes and ask for decisions?
- Does it handle direct/context/archive responses correctly?
- Does it update frontmatter with correct field names?
- Does it move files to the right directories?
- Does it print a summary?

**Step 3: Fix any issues found**

Edit `.claude/commands/manual-review.md` as needed.

**Step 4: Commit any fixes**

```bash
git add .claude/commands/manual-review.md
git commit -m "fix: refine manual-review command after smoke test"
```

---

### Task 4: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add manual-review to Key Files section**

Add entry for `.claude/commands/manual-review.md` explaining what it does.

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add manual-review command to CLAUDE.md"
```
