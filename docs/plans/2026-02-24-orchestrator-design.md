# Orchestrator Design — Jimbo as Conductor

**Date:** 2026-02-24
**Status:** Approved (design phase)
**Supersedes:** ADR-020 (multi-model routing, Phase 2)

## Problem

Jimbo processes ~200 emails daily on Gemini 2.5 Flash. The model fits them in context but doesn't truly deep-read — it summarises at the category level ("eBay MacBook hits, theatre tickets, job alerts") rather than extracting buried gems from newsletter bodies. The skill instructions are excellent but the model can't follow them at this volume.

More broadly: different tasks need different models, and even within a single task (email reading), different content types deserve different levels of attention. We need an architecture that matches model capability to task complexity, tracks everything, and continuously improves.

## Design Principles

- **Quality-maximising** within a $15-25/month budget
- **Everything is logged** — every worker run, every conductor decision, every user rating
- **Experimentation is built in** — change a model, change a prompt, compare results over time
- **Beautiful audit trail** — the data itself tells the story of what's working
- **Jimbo stays in character** — the orchestration makes him smarter, not robotic

## Architecture

```
Jimbo (Conductor — Haiku 4.5 or Sonnet)
  │
  │  Makes high-judgment decisions, synthesises worker outputs,
  │  composes final messages, logs reasoning, plays games
  │
  ├── email_triage.py (Flash)
  │     Bulk classify 200 emails → ranked shortlist of ~30
  │
  ├── newsletter_reader.py (Haiku)
  │     Deep read shortlisted newsletters, extract specific gems
  │
  ├── heartbeat_checker.py (Flash)
  │     Run system checks, return structured status
  │
  └── ... future workers (research, recommendations, vault triage)
```

Workers call model APIs directly from the sandbox (not through OpenClaw). Jimbo orchestrates by calling worker scripts and reading their structured JSON output.

## Component 1: Task Registry

Every repeatable task gets a definition file.

```
workspace/tasks/
  ├── registry.json
  ├── email-triage.json
  ├── newsletter-deep-read.json
  ├── briefing-synthesis.json
  ├── heartbeat.json
  └── chat.json
```

Task definition schema:

```json
{
  "task_id": "newsletter-deep-read",
  "description": "Deep read shortlisted newsletters, extract links/events/gems matching context",
  "default_model": "claude-haiku-4.5",
  "fallback_model": "gemini-2.5-flash",
  "evaluation": {
    "method": "conductor-review",
    "criteria": [
      "cited_specific_articles",
      "linked_to_context_files",
      "surfaced_surprises"
    ]
  },
  "budget_ceiling_per_run": 0.05,
  "batch_size": 15,
  "context_files": ["INTERESTS.md", "TASTE.md", "PRIORITIES.md"]
}
```

Changing any field (model, batch size, prompt strategy) changes the `config_hash`, enabling before/after comparison.

## Component 2: Experiment Tracker

SQLite-backed (`workspace/experiment-tracker.py` + `experiment-tracker.db`), same pattern as cost-tracker.py.

### Run schema

```sql
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    parent_run_id TEXT,          -- links worker runs to conductor run
    timestamp TEXT NOT NULL,
    model TEXT NOT NULL,
    config_hash TEXT NOT NULL,   -- fingerprint of task config at run time
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    duration_ms INTEGER,
    input_summary TEXT,
    output_summary TEXT,
    quality_scores TEXT,         -- JSON: per-criteria scores
    conductor_rating INTEGER,   -- Jimbo's assessment of worker output (1-10)
    user_rating INTEGER,        -- Marvin's rating (1-10), nullable
    user_notes TEXT,
    conductor_reasoning TEXT,    -- JSON: promoted/dropped/surprises/self_critique
    config_snapshot TEXT         -- JSON: full task config at run time
);
```

### CLI

```bash
python3 experiment-tracker.py log --task <id> --model <model> --input-tokens N --output-tokens N --quality '{...}'
python3 experiment-tracker.py runs --task <id> --last 10
python3 experiment-tracker.py compare --task <id> --days 14
python3 experiment-tracker.py compare --task <id> --models "claude-haiku-4.5,gemini-2.5-pro"
python3 experiment-tracker.py rate <run_id> --user-rating 8 --notes "good"
python3 experiment-tracker.py export --days 30 --format json
python3 experiment-tracker.py stats --days 7
```

## Component 3: Worker Architecture

### base_worker.py

Shared infrastructure for all workers:

- Direct API calls to Google AI, Anthropic, OpenRouter
- Automatic token counting and cost estimation
- Experiment tracker logging (every run logged automatically)
- Structured JSON input/output
- Retry with fallback model on failure

### Worker contract

Every worker:
1. Reads input (JSON from stdin or file path)
2. Loads its task config from the registry
3. Calls a model API with a task-specific prompt
4. Returns structured JSON output
5. Logs the run to experiment-tracker.db

Workers are stateless. Same input + same config = comparable output.

### Morning briefing flow

```
06:00  gmail-helper.py fetches 200 emails → email-digest.json
07:00  Jimbo wakes (OpenClaw cron)
       │
       Step 1: python3 workers/email_triage.py --digest email-digest.json
               Model: Flash | Output: shortlist.json (top ~30, ranked, with reasons)
               Logged: run_triage_xxx
       │
       Step 2: python3 workers/newsletter_reader.py --shortlist shortlist.json
               Model: Haiku | Output: gems.json (articles, links, events, prices, deadlines)
               Logged: run_news_xxx
       │
       Step 3: Jimbo reads calendar, recommendations, heartbeat (himself, as conductor)
       │
       Step 4: Jimbo synthesises → Telegram briefing
               Logs: conductor reasoning, links to worker run_ids, overall quality assessment
```

## Component 4: Conductor's Log

Jimbo logs his reasoning for every briefing — what he promoted, dropped, why, and what surprised him.

```json
{
  "run_id": "run_brief_a1b2",
  "conductor_reasoning": {
    "promoted": [
      {
        "item": "Anjuna fabric night",
        "why": "Electronic music interest, time-sensitive, niche venue"
      }
    ],
    "dropped": [
      {
        "item": "Capgemini job alerts",
        "why": "Generic, not actively looking, repetitive"
      }
    ],
    "surprises": [
      {
        "item": "Error fare buried in Jack's Flight Club paragraph 6",
        "why": "£89 return Lisbon — almost missed by worker"
      }
    ],
    "self_critique": "Newsletter reader missed the Lisbon fare. Need better deal extraction.",
    "surprise_attempts": [
      {
        "fact": "The Neighbourhood's debut album was recorded in a garage in Newbury Park, CA — 20 minutes from where Groove Armada played their first gig",
        "strategy": "Connected two email items via music geography",
        "confidence": 0.6
      }
    ]
  }
}
```

### Blog pipeline

Conductor logs accumulate daily. A skill (or scheduled task) reviews 7 days of logs and writes a blog post. The reasoning trail means Jimbo writes from real decisions, not fabrication. Topics emerge naturally: "This week I learned I'm bad at spotting travel deals in newsletters" or "Three emails this week connected to the same emerging trend."

## Component 5: Games Framework

Persistent games between Jimbo and Marvin, tracked in the experiment system. Games serve dual purpose: fun interaction AND quality measurement.

### The Surprise Game

The original game. Jimbo tries to surface a fact, connection, or piece of knowledge from the daily digest that Marvin finds genuinely interesting.

**Rules:**
- Each briefing, Jimbo includes one "surprise" — a non-obvious connection, buried gem, or interesting fact extracted from the emails
- Marvin reacts: interesting → Jimbo gets a point. Not interesting → Marvin gets a point
- Score tracked persistently, visible on dashboard and in briefings

**Why it works as a quality metric:** A good surprise means the model genuinely read deeply, understood context, and made a creative connection. A bad surprise means it's pattern-matching or guessing. The score over time directly measures depth-of-reading quality.

### Games table

```sql
CREATE TABLE games (
    game_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created TEXT NOT NULL
);

CREATE TABLE game_rounds (
    round_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    run_id TEXT,                 -- links to experiment run that generated it
    timestamp TEXT NOT NULL,
    jimbo_play TEXT,             -- what Jimbo attempted (JSON)
    outcome TEXT,                -- 'jimbo_point' | 'marvin_point' | 'draw' | 'pending'
    jimbo_score INTEGER,        -- running total
    marvin_score INTEGER,       -- running total
    notes TEXT
);
```

### Future games (examples, not committed)

- **Prediction Game:** Jimbo predicts what Marvin will find most interesting from tomorrow's digest. Scored next day.
- **Taste Test:** Jimbo recommends something outside Marvin's usual interests. Point if Marvin engages with it.
- **Context Challenge:** Jimbo connects two unrelated emails to one of Marvin's active projects. Marvin judges if the connection is real.

Games are defined in the task registry like any other task — they have evaluation criteria, they're logged, they're tracked.

## Component 6: UI + API

### VPS API (extend existing Hono server or new service)

```
GET  /api/orchestrator/tasks              — list task definitions
GET  /api/orchestrator/tasks/:id          — single task config
PUT  /api/orchestrator/tasks/:id          — update config (change model, batch size)
GET  /api/orchestrator/runs               — recent runs, paginated, filterable
GET  /api/orchestrator/runs/:id           — single run with full detail
POST /api/orchestrator/runs/:id/rate      — submit user rating
GET  /api/orchestrator/compare/:task      — model comparison for a task
GET  /api/orchestrator/stats              — cost/day, quality trends, model breakdown
GET  /api/orchestrator/games              — game list with scores
GET  /api/orchestrator/games/:id/rounds   — round history
POST /api/orchestrator/games/:id/score    — record round outcome
GET  /api/orchestrator/conductor-log      — recent conductor reasoning entries
```

### Site pages (`/app/jimbo/orchestrator/`)

| Page | Shows |
|------|-------|
| Overview | Today's runs, cost, quality trend, active experiments, Jimbo's self-critique |
| Tasks | Registry browser, edit configs, see per-task stats |
| Runs | Run history with quality scores, filter by task/model, rate runs |
| Compare | Side-by-side model comparison per task (charts, averages) |
| Games | Scoreboard, round history, play pending rounds |
| Conductor's Log | Jimbo's reasoning feed — promoted/dropped/surprises, blog-ready |

### Alternative inputs

- **Telegram:** "that briefing was a 7" → rates today's briefing run. "jimbo point" / "my point" → scores the surprise game round.
- **CLI:** `experiment-tracker.py rate <run_id> --user-rating 8` for terminal workflow.

## Cost Estimate

| Component | Model | Est. monthly cost |
|-----------|-------|-------------------|
| Email triage (daily) | Gemini Flash | ~$0.50 |
| Newsletter deep read (daily) | Claude Haiku 4.5 | ~$1.50 |
| Conductor (briefing + chat) | Claude Haiku 4.5 | ~$3-5 |
| Heartbeat (4x daily) | Gemini Flash | ~$0.20 |
| Experiments (ad-hoc model tests) | Various | ~$2-5 |
| **Total** | | **~$7-12/month** |

Well within $15-25 budget, with room for upgrading conductor to Sonnet or running more experiments.

## Implementation Phases

### Phase 1: Foundation
- experiment-tracker.py (SQLite script, CLI)
- base_worker.py (API calling, logging)
- Task registry (JSON files)
- email_triage.py worker (Flash)
- newsletter_reader.py worker (Haiku)
- Update sift-digest skill to use workers

### Phase 2: Conductor Intelligence
- Conductor's log (reasoning capture)
- Self-critique and quality scoring
- Surprise game implementation
- Telegram rating integration ("that was a 7")

### Phase 3: UI + API
- VPS API endpoints (extend Hono pattern)
- Site dashboard pages (Astro + React islands)
- Run browser, comparison views, game scoreboard
- Task config editing from UI

### Phase 4: Blog + Games
- Blog generation from conductor logs
- Additional games (prediction, taste test, context challenge)
- Dashboard refinements based on usage

## Relationship to Existing Systems

| Existing | Relationship |
|----------|-------------|
| cost-tracker.py | Experiment tracker captures cost per run; cost-tracker continues for overall budget |
| activity-log.py | Conductor logs replace activity logging for orchestrated tasks; activity-log continues for non-orchestrated work |
| model-swap.sh | Still useful for switching Jimbo's own model; workers choose models independently |
| ADR-020 | This design fulfils Phase 2 and goes beyond it |
| sift-digest skill | Updated to delegate to workers instead of reading all emails directly |
| daily-briefing skill | Updated to orchestrate the full worker pipeline |
