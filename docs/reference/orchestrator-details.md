# Orchestrator Technical Notes

## Problem Observed (2026-02-24)

Jimbo's morning briefing on Gemini Flash gave category-level summaries of 200 emails instead of deep reading. Example output: "Mix of eBay MacBook search hits, theatre tickets, job alerts" — no specific articles, links, prices, or buried gems cited. Flash can fit 200 emails in context but attention quality degrades at that volume.

## Architecture Decisions

- Workers call model APIs directly from sandbox (not through OpenClaw) — ANTHROPIC_API_KEY and GOOGLE_AI_API_KEY configured in openclaw.json sandbox.docker.env and passed into container
- Workers return structured JSON; Jimbo (conductor) turns it into prose
- Every run logged to experiment-tracker.db with config hash for before/after comparison
- Conductor rates worker output automatically; Marvin can rate via Telegram ("that was a 7") or site UI

## Email Pipeline Change

Before: Jimbo reads all 200 emails in one pass (Flash, ~1M chars)
After: email_triage.py (Flash) → shortlist of 30 → newsletter_reader.py (Haiku) → gems → Jimbo synthesises

## Games as Quality Metrics

- Surprise Game: Jimbo surfaces non-obvious gem from digest, Marvin judges. Score tracks reading depth over time.
- Future games: Prediction Game, Taste Test, Context Challenge (not committed, ideas only)
- Games stored in experiment-tracker.db (games + game_rounds tables)

## Conductor's Log → Blog Pipeline

Jimbo logs promoted/dropped/surprises/self_critique for every briefing. Weekly skill reviews 7 days of logs, writes a blog post from real decisions. Authenticity from actual reasoning, not fabrication.

## Open Questions

- Should conductor model differ between briefing (Sonnet) and chat (Haiku)? OpenClaw's single-model limitation means model-swap needed.
- ~~How to handle worker failures gracefully — fallback model or skip?~~ **Resolved:** fallback model is built into base_worker.py.
- Should the experiment tracker API be a separate Hono service or extend the triage API?

## Deployment Notes

- **Deployed:** 2026-02-25
- SSH multiplexing needed for workspace-push.sh — VPS rate-limits after ~5 concurrent connections. Use `ControlMaster` in SSH config.
- Container env vars (ANTHROPIC_API_KEY, GOOGLE_AI_API_KEY) added to openclaw.json `sandbox.docker.env`
- Container must be recreated after env changes: stop old container, then restart openclaw service (it spawns a new one)

## Files on VPS

```
/workspace/workers/
  base_worker.py         — base class with fallback model, structured JSON output, experiment logging
  email_triage.py        — Gemini Flash worker: scores/filters 200 emails → shortlist of ~30
  newsletter_reader.py   — Haiku worker: deep-reads shortlisted newsletters, extracts gems + links

/workspace/tasks/
  task_registry.py       — task definitions, worker routing, config

/workspace/tests/
  test_workers.py        — unit tests for worker scripts
```
