# ADR-029: Orchestrator-Conductor Pattern — Multi-Model Task Routing

## Status

Accepted

## Context

Jimbo runs on a single model (Gemini 2.5 Flash, ~$0.78/month) for all tasks. After observing daily briefings, the email digest output is category-level summarisation ("eBay hits, theatre tickets, job alerts") rather than deep reading. With 200 emails x 5000 chars each in a single context window, Flash skims rather than reads — it grabs obvious subject-line information and misses buried gems in newsletter bodies.

ADR-020 identified this problem and proposed per-skill model routing, but stalled at Phase 1 ("just switch to Haiku for everything"). The real issue is architectural: different tasks need different models, and even within email reading, newsletters deserve deeper attention than receipts.

Additionally, there's no way to measure whether model changes actually improve output quality. We swap models based on vibes, not data.

### What we observed

- Briefing output lists categories, not specific articles or links
- No evidence of newsletter body reading (no cited articles, no extracted links)
- Time-sensitive items (events, deals) mentioned generically without prices or dates
- Flash is fine for simple tasks (heartbeat checks, casual chat) but fails at multi-file reasoning

### The established pattern

**Orchestrator-worker** (also called model cascading or conductor pattern) is widely used in production AI systems. A capable model handles judgment and synthesis while delegating bulk/structured work to cheaper models. This is how Anthropic, OpenAI, and most serious AI products route internally.

## Decision

Implement Jimbo as a **conductor** running on a capable model (Haiku 4.5 initially, Sonnet as budget allows), delegating subtasks to **worker scripts** that call cheaper model APIs directly from the sandbox.

### Key components

1. **Task Registry** — JSON config files defining every repeatable task, its model, evaluation criteria, and batch parameters. Changing any config field changes a hash, enabling before/after comparison.

2. **Experiment Tracker** — New SQLite-backed script (`experiment-tracker.py`). Logs every worker run: task ID, model, tokens, cost, duration, quality scores (automated + user-provided), config hash. Supports comparison queries across models and time periods.

3. **Worker Scripts** — Python scripts in `workspace/workers/` that call model APIs directly (not through OpenClaw). Each worker reads structured input, calls a model, returns structured JSON, logs the run. Workers are stateless and replayable.

4. **Conductor's Log** — Jimbo logs reasoning for every briefing: what he promoted, dropped, why, what surprised him, and self-critique of worker performance. This feeds both optimisation and blog content.

5. **Games Framework** — Persistent games (starting with the Surprise Game) that serve as quality metrics. Jimbo tries to surface a non-obvious gem; Marvin judges it. Scores tracked over time = direct measurement of reading depth.

6. **UI + API** — Dashboard on the personal site (`/app/jimbo/orchestrator/`) for monitoring runs, comparing models, rating output, editing task configs, and viewing game scores. VPS API extends the existing Hono pattern.

### Morning briefing flow (the primary use case)

```
06:00  gmail-helper.py fetches emails → email-digest.json
07:00  Jimbo (conductor, Haiku) wakes up
       ├── Calls email_triage.py (Flash) → shortlist of ~30 from 200
       ├── Calls newsletter_reader.py (Haiku) → extracted gems from shortlist
       ├── Reads calendar, recommendations, heartbeat himself
       └── Synthesises everything → Telegram briefing + conductor's log
```

### Cost estimate

| Component | Model | Est. monthly |
|-----------|-------|-------------|
| Email triage (daily) | Gemini Flash | ~$0.50 |
| Newsletter deep read (daily) | Claude Haiku 4.5 | ~$1.50 |
| Conductor (briefing + chat) | Claude Haiku 4.5 | ~$3-5 |
| Heartbeat (4x daily) | Gemini Flash | ~$0.20 |
| Experiments (ad-hoc) | Various | ~$2-5 |
| **Total** | | **~$7-12/month** |

Well within the $15-25/month budget, with room for experiments and conductor model upgrades.

### Implementation phases

- **Phase 1:** Foundation — experiment tracker, base worker, email triage + newsletter reader workers, updated sift-digest skill
- **Phase 2:** Conductor intelligence — reasoning log, self-critique, surprise game, Telegram rating
- **Phase 3:** UI + API — dashboard pages, run browser, comparison views, game scoreboard
- **Phase 4:** Blog + games — blog generation from conductor logs, additional games

## Consequences

**What becomes easier:**
- Deep reading of newsletters — dedicated worker with appropriate model
- Measuring quality — every run logged with automated + human scores
- Experimenting with models — change one field, compare results
- Continuous improvement — data-driven decisions instead of vibes
- Blog content — conductor's reasoning trail provides authentic material
- Playful interaction — games create structured feedback loops

**What becomes harder:**
- More moving parts — workers, tracker, registry, API
- Debugging — failures could be in worker, conductor, or API layer
- Skill updates — sift-digest and daily-briefing skills need rewriting to delegate
- Onboarding — understanding the system requires knowing the conductor pattern

**What changes:**
- Jimbo's role shifts from "model that reads everything" to "conductor that delegates and synthesises"
- Cost increases from ~$0.78/month to ~$7-12/month (quality-justified)
- The experiment tracker becomes the single source of truth for "is this working?"

**Risks:**
- Worker API calls from sandbox need env vars (already available: ANTHROPIC_API_KEY, GOOGLE_AI_API_KEY)
- OpenClaw's single-model limitation means conductor model = chat model; can't have Sonnet for briefings and Flash for casual chat without model-swap
- Over-engineering risk — Phase 1 should deliver value before building the full UI

## Related

- **Supersedes:** ADR-020 Phase 2 (static routing table)
- **Extends:** ADR-028 (cost tracking + activity logging)
- **Design doc:** `docs/plans/2026-02-24-orchestrator-design.md`
- **New files:** `workspace/experiment-tracker.py`, `workspace/workers/`, `workspace/tasks/`
