# Design: /assess skill for Claude Code

## Date: 2026-03-07

## Problem

Marvin encounters links, tweets, tools, and ideas daily that need quick evaluation against his current goals and priorities. Currently this is ad-hoc — read the thing, discuss it, form an opinion. There's no consistent framework applied, and no structured verdict to anchor the conversation.

## Solution

A Claude Code skill (`/assess`) that evaluates URLs or pasted text against Marvin's context — live from the jimbo-api and local prose files — and produces a structured verdict followed by open discussion.

## Architecture

```
/assess <url or pasted text>
       |
       +-- WebFetch URL (if URL provided)
       +-- jimbo-api -> Priorities, Interests, Goals (live, structured)
       +-- Local repo -> TASTE.md, PREFERENCES.md (prose, judgment criteria)
       |
       +-- Structured verdict + open discussion
```

## Context sources

| Source | Data | Location | Freshness |
|--------|------|----------|-----------|
| jimbo-api | Priorities, Interests, Goals | `https://167.99.206.214/api/context/files/{slug}` | Live (edited via site UI) |
| Local repo | TASTE.md | `context/TASTE.md` | Stable (changes rarely) |
| Local repo | PREFERENCES.md | `context/PREFERENCES.md` | Stable (changes rarely) |
| Local fallback | CONTEXT-BACKUP.md | `context/CONTEXT-BACKUP.md` | Condensed backup, updated occasionally |

If the jimbo-api is unreachable, the skill warns and falls back to `CONTEXT-BACKUP.md`.

## Inputs

Two modes:

1. **URL** — skill calls WebFetch to retrieve content. If WebFetch fails (tweets, paywalled content), prompts Marvin to paste the text.
2. **Pasted text** — used directly.

Not for raw ideas or brainstorming — those are better served by a clean slate conversation.

## Output format

1. **Verdict** — one line: Skip / Bookmark / Worth exploring / Act now
2. **Relevance** — 2-3 sentences on what this is and why it matters (or doesn't) to Marvin right now
3. **Connections** — which goals, priorities, or interests it touches (by name)
4. **What you'd do with it** — concrete next step if any
5. **Blind spots** — what to verify, what the source might be wrong about, what's missing

Conversation continues naturally after the verdict.

## Housekeeping (part of implementation)

- Delete `context/GOALS.md`, `context/INTERESTS.md`, `context/PRIORITIES.md` from repo (jimbo-api is source of truth)
- Create `context/CONTEXT-BACKUP.md` — condensed fallback for when API is down
- Update `CLAUDE.md` references to reflect the new source-of-truth split
- Update `scripts/workspace-push.sh` if it references deleted files

## Skill location

Claude Code skill file. Not an OpenClaw/Jimbo skill (may add later if useful).

## API access

The skill needs to call jimbo-api. It will use the same key stored in the VPS (`JIMBO_API_KEY`). The skill should read the key from environment or prompt for it. The API is exposed via Caddy at the VPS public IP.

## Out of scope

- Jimbo OpenClaw skill (future, if /assess proves useful)
- Automatic logging of assessments (could add later)
- Batch assessment of multiple links
