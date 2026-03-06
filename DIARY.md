# Jimbo Daily Diary

Tracking daily satisfaction, issues, wins, and lessons. Score is Marvin's subjective rating of Jimbo's usefulness that day.

## Key

- **Score:** 1-10 (1 = useless, 5 = meh, 10 = indispensable)
- **Model:** LLM model Jimbo was running that day
- **Pipeline:** Did the email digest arrive fresh? (Y/N/stale)
- **Briefing:** Did the morning briefing happen and was it useful? (Y/N/partial)

## Log

| Date | Score | Model | Pipeline | Briefing | Notes |
|---|---|---|---|---|---|
| 2026-02-19 | 3 | gemini-2.5-flash | Y | partial | First real briefing attempt. Sift pipeline working but digest quality mixed. Feedback mechanism added. |
| 2026-02-20 | 3 | gemini-2.5-flash | Y | partial | Pipeline ran at 04:22. Jimbo gave briefing but went off-script trying to publish a blog post. Astro build failed (Node version). Calendar event created but not useful. Day planner deployed. |
| 2026-02-21 | 2 | gemini-2.5-flash | N | N | Pipeline failed — network check bug (IMAP ≠ HTTPS). Fixed URL. Also: pipeline has **never worked via launchd** — every successful run was manual or lucky. Switching to Haiku (ADR-020). Gmail API migration started (ADR-022): dropped LLM classification entirely, gmail-helper.py runs in sandbox, blacklist-only filtering, Jimbo reads raw emails deeply. |
| 2026-02-25 | — | — | — | — | Night before first orchestrated briefing. Wrote down hopes: specific articles cited by name, links worth clicking, buried deals surfaced, stats up top, honest skips, a genuine surprise. Worried about: Python 3.11 vs 3.14 syntax, API key interpolation, malformed Flash JSON, Haiku over-extracting, silent fallback. The real test: does Marvin learn something he wouldn't have found scrolling Gmail himself? |

## Patterns

| Pattern | First seen | Status | Fix |
|---|---|---|---|
| Sift pipeline network check broken | 2026-02-21 | FIXED | `curl https://imap.gmail.com` always times out (IMAP ≠ HTTPS). Changed to `https://www.google.com`. Pipeline had never worked via launchd — every "successful" cron run was actually manual. Whole pipeline now replaced by Gmail API (ADR-022). |
| Gemini goes off-script | 2026-02-20 | OPEN | Writes blog posts, meta-commentary instead of following skill instructions. Consider Haiku. |
| Calendar suggestions not useful | 2026-02-21 | OPEN | Suggested fixing own tooling. Needs better judgment about what Marvin would actually want. |
| Briefing too ambitious | 2026-02-20 | OPEN | 7+ context files to cross-reference is too much for Flash. Simplify or upgrade model. Led to orchestrator-conductor redesign (ADR-029): split work across Flash triage + Haiku reader + conductor synthesis. |
| Silent fallback risk | 2026-02-25 | OPEN | If workers fail, Jimbo falls back to reading raw digest without reporting why. Need mandatory failure reporting + experiment-tracker logging even on fallback. |
| Heartbeat not running | 2026-02-19 | OPEN | Designed but never configured in OpenClaw. Blocks proactive nudges. |

## Model History

| Date | Model | Cost/month | Verdict |
|---|---|---|---|
| 2026-02-17 | stepfun/step-3.5-flash:free | $0 | Can't follow instructions at all (ADR-005) |
| 2026-02-18+ | google/gemini-2.5-flash | ~$0.78 | Follows some instructions. Goes off-script. Struggles with complex multi-file context. |
| 2026-02-21 | anthropic/claude-haiku-4.5 | ~$2.49 | Switching to daily driver. ADR-020: right model for right job. |
