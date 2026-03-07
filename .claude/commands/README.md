# Claude Code Custom Skills

Quick reference for all custom `/slash` commands in this project.

| Skill | What it does | Example |
|-------|-------------|---------|
| `/assess` | Evaluate a URL or pasted text against your goals, priorities, interests, and taste | `/assess https://example.com/article` |
| `/review-briefing` | Review Jimbo's briefing quality — pull pipeline data, discuss what worked | `/review-briefing 2026-03-07` |
| `/manual-review` | Interactively triage vault notes (inbox or needs-context) | `/manual-review 10 inbox oldest` |
| `/triage-tasks` | Triage ambiguous vault tasks from VPS via discussion | `/triage-tasks 5 pending` |

## Context sources

- `/assess` reads from jimbo-api (Priorities, Interests, Goals) + local TASTE.md and PREFERENCES.md
- `/review-briefing` SSHes to VPS to pull pipeline data
- `/manual-review` and `/triage-tasks` SSH to VPS to read/update vault files

## Adding new skills

Drop a `.md` file in `.claude/commands/` with YAML frontmatter:

```yaml
---
description: One-line description shown in skill list
argument-hint: "<what to pass>"
---
```

Skills appear immediately — no restart needed.
