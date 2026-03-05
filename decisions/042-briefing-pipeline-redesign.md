# ADR-042: Briefing Pipeline Redesign

## Status

Accepted

## Context

The briefing pipeline asked Jimbo (an LLM) to orchestrate workers, fetch data, compose output, log results, and monitor itself — all in a single session guided by 400+ lines of skill prompts across sift-digest (239 lines) and daily-briefing (167 lines). In practice, Jimbo reliably performed 4-5 of 15 required tasks. Workers never ran. Experiment-tracker logging never fired. Calendar entries were fabricated. The monitoring chain reported false negatives ("morning: missing") all day because the logging step was never reached.

Review sessions on 2026-03-04 and 2026-03-05 confirmed the root cause: orchestration should be code, not LLM prompts. Each prompt improvement (adding examples, context files, logging steps) made the prompt longer and reliable execution less likely.

Separately, Marvin has a Claude Max plan (Opus 4.6 access) and a MacBook capable of running scheduled jobs. Opus is dramatically better at editorial judgment and creative synthesis — the hardest part of briefing composition — but isn't available via API.

## Decision

Move orchestration from LLM prompts to a cron-driven Python script (`briefing-prep.py`), add an optional local Opus analysis layer via `claude -p` on the Mac, and slim Jimbo's skill to ~60 lines with one job: compose and deliver.

### Architecture

**VPS cron (always on, reliable):**
- `briefing-prep.py morning` at 06:15 UTC — runs email fetch, triage worker (Flash), reader worker (Haiku), calendar fetch, vault task selection. Assembles `briefing-input.json`. Logs to experiment-tracker. Sends Telegram status.
- `briefing-prep.py afternoon` at 14:15 UTC — same pipeline, shorter email window, no vault rescore.

**Mac launchd (powerful, intermittent):**
- `opus-briefing.sh morning` at 06:50 UTC — pulls `briefing-input.json` from VPS, runs `claude -p` (Opus via Max plan), pushes `briefing-analysis.json` back.
- Same for afternoon at 14:50 UTC.
- Exits silently on any failure. Graceful absence.

**Jimbo (VPS, 07:00 / 15:00):**
- Reads `briefing-input.json` (always present if pipeline ran).
- IF `briefing-analysis.json` exists and is fresh: Opus-assisted mode (deliver pre-computed analysis in Jimbo's voice).
- ELSE: self-compose mode (build day plan from raw data, same as before but with clean structured input).
- Logs to experiment-tracker and activity-log (2 commands).

### Model hierarchy

| Role | Model | Cost |
|------|-------|------|
| Email triage | Gemini Flash | ~$0.01/run |
| Newsletter reader | Claude Haiku 4.5 | ~$0.03/run |
| Thinking (when Mac available) | Claude Opus 4.6 (Max plan) | Free |
| Delivery (Opus ran) | Haiku / Kimi / free | ~$0.01 |
| Delivery (no Opus) | Claude Sonnet 4.6 | ~$0.15 |

### Retired components

- `sift-digest/SKILL.md` — replaced by `briefing-prep.py`
- Hourly `email-fetch-cron.py` — fetch now inside briefing-prep
- Hourly `alert-check.py status` — replaced by per-pipeline Telegram alert
- LLM-driven sub-agent spawning — replaced by Python subprocess calls

## Consequences

**What becomes easier:**
- Workers always run (Python cron, not LLM prompt compliance)
- Monitoring always works (briefing-prep logs its own runs, no dependency on Jimbo reaching Step 5)
- Jimbo's skill is 60 lines instead of 400+ — less can go wrong
- Opus-quality analysis at zero marginal cost when Mac is available
- Calendar data is structured JSON — no fabrication possible
- Pipeline failures are visible immediately (Telegram alert per step)

**What becomes harder:**
- Two machines involved (VPS + Mac) when Opus layer is active
- Mac must be awake at scheduled times for Opus benefit (mitigated by graceful fallback)
- Triage worker calibration is now visible (0 of 93 shortlisted in first live test — was hidden before because workers never ran)
- Calendar helper returns events from wrong date range — needs separate fix

**Trade-offs:**
- More moving parts (cron + launchd + Jimbo) but each part is simpler and more reliable
- Daily OpenRouter cost may decrease (cheaper delivery model when Opus handles thinking)
- Email fetch reduced from hourly to twice-daily — acceptable since it's tied to briefing delivery
