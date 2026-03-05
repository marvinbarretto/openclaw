# Briefing Pipeline Redesign

*2026-03-05 — Move orchestration from LLM prompts to cron, add local Opus analysis layer*

## Problem

The current pipeline asks Jimbo (an LLM) to orchestrate workers, read files, compose output, log results, and monitor itself — all in a single session guided by 400+ lines of skill prompts. He reliably does 4-5 of 15 tasks. Workers never run. Logging never fires. Calendar entries get fabricated. The monitoring chain reports false negatives all day.

The root cause isn't the model — it's the architecture. Orchestration should be code, not prompts.

## Design

### Principles

1. **Code orchestrates, LLMs think.** Python runs workers, fetches data, logs results. LLMs do editorial judgment and creative synthesis.
2. **Each LLM interaction does ONE thing.** Flash triages. Haiku deep-reads. Opus plans the day. Jimbo delivers the message.
3. **Graceful degradation.** Every component can be absent. Mac asleep? Jimbo composes himself. Workers failed? Jimbo reports the failure and works with partial data. Calendar API down? Jimbo says so.
4. **Twice daily.** Morning (strategy) at 07:00. Afternoon (rescue) at 15:00.

### Pipeline Architecture

#### Morning (briefing delivered at 07:00 UTC)

```
06:15  briefing-prep.py morning          [VPS cron]
       |-- gmail-helper.py fetch --hours 14
       |-- email_triage.py               (Flash, ~$0.01)
       |-- newsletter_reader.py          (Haiku, ~$0.03)
       |-- calendar-helper.py list-events --days 1
       |-- vault task selection           (grep + frontmatter parse)
       |-- assemble briefing-input.json
       |-- log to experiment-tracker
       |-- send pipeline status to Telegram

06:45  model-swap (only if no Opus analysis expected)

06:50  opus-briefing.sh                  [Mac launchd, if awake]
       |-- pull briefing-input.json from VPS
       |-- claude -p with morning prompt  (Opus via Max plan, free)
       |-- validate output JSON
       |-- push briefing-analysis.json to VPS

07:00  OpenClaw triggers Jimbo           [VPS]
       |-- IF briefing-analysis.json exists and fresh:
       |     read it, compose in Jimbo's voice, deliver
       |-- ELSE:
       |     read briefing-input.json, self-compose (Sonnet)
       |-- log to experiment-tracker + activity-log
```

#### Afternoon (briefing at ~15:00 UTC)

```
14:15  briefing-prep.py afternoon        [VPS cron]
       |-- gmail-helper.py fetch --hours 8
       |-- email_triage.py + newsletter_reader.py
       |-- calendar-helper.py list-events --days 1
       |-- NO vault rescore (use morning data)
       |-- assemble briefing-input.json (afternoon session)

14:45  model-swap (only if no Opus)

14:50  opus-briefing.sh                  [Mac launchd, if awake]
       |-- same flow, afternoon prompt (rescue framing)

15:00  Jimbo afternoon briefing
       |-- same branch logic
       |-- afternoon tone: what's left, what changed, what to let go
```

### Model Hierarchy

| Role | Model | Cost | Job |
|------|-------|------|-----|
| Email triage | Gemini Flash | ~$0.01/run | Score and filter emails |
| Newsletter reader | Claude Haiku 4.5 | ~$0.03/run | Extract gems from shortlisted emails |
| Thinking (Option C) | Claude Opus 4.6 (Max plan) | Free | Day plan, editorial judgment, cross-referencing |
| Delivery (Opus ran) | Haiku / Kimi / free model | ~$0.01 | Format Opus analysis into Jimbo's voice |
| Delivery (no Opus) | Claude Sonnet 4.6 | ~$0.15 | Self-compose from briefing-input.json |

When Opus has run, the delivery model doesn't need to think — just format and deliver. No model swap needed. When Opus hasn't run, swap to Sonnet for the briefing window (existing behaviour).

### Data Formats

#### `briefing-input.json` — assembled by briefing-prep.py

```json
{
  "generated_at": "2026-03-05T06:45:00Z",
  "session": "morning",
  "pipeline": {
    "email_fetch": {"status": "ok", "count": 87},
    "triage": {"status": "ok", "shortlisted": 12, "skipped": 75},
    "reader": {"status": "ok", "gems": 5, "skipped": 7},
    "calendar": {"status": "ok", "events": 4},
    "vault": {"status": "ok", "tasks": 3}
  },
  "calendar": [
    {
      "summary": "Review Briefing",
      "start": "2026-03-05T10:00:00Z",
      "end": "2026-03-05T10:30:00Z",
      "location": null
    }
  ],
  "gems": [
    {
      "source": "Jack's Flight Club",
      "title": "Buenos Aires from £632 return",
      "why": "Direct match to travel goals",
      "confidence": 0.9,
      "links": ["https://example.com/deal"],
      "time_sensitive": true,
      "deadline": "2026-03-10",
      "price": "£632 return",
      "surprise_candidate": false
    }
  ],
  "shortlist_reasons": [
    {
      "gmail_id": "abc123",
      "category": "deal",
      "reason": "Buenos Aires flight — tracks travel deals",
      "time_sensitive": true
    }
  ],
  "vault_tasks": [
    {
      "file": "localshout-auth-flow.md",
      "title": "Review LocalShout auth flow",
      "priority": 9,
      "actionability": "clear",
      "tags": ["localshout", "dev"]
    }
  ],
  "context_summary": {
    "priorities_updated": "2026-03-04",
    "goals_updated": "2026-02-20",
    "top_priority": "LocalShout MVP",
    "active_priority_count": 4
  },
  "triage_pending": 3
}
```

Calendar is ONLY what the API returned. Gems come pre-scored from workers. Vault tasks are pre-selected. Pipeline status is explicit per-component.

#### `briefing-analysis.json` — produced by Opus on Mac

```json
{
  "generated_at": "2026-03-05T06:55:00Z",
  "session": "morning",
  "model": "claude-opus-4-6",
  "day_plan": [
    {
      "time": "09:00-10:00",
      "suggestion": "LocalShout auth flow review",
      "source": "vault",
      "reasoning": "Highest priority task, clear next step, fits before your 10:00 review"
    }
  ],
  "email_highlights": [
    {
      "source": "Watford Observer",
      "headline": "Ngakia exclusive interview",
      "editorial": "First interview since his move — read this before the Spurs match tonight.",
      "links": ["https://example.com/article"]
    }
  ],
  "surprise": {
    "fact": "Gresham College has a free talk tonight at 18:00 — 20 min walk from your salsa class at 19:00.",
    "strategy": "Cross-referenced events email with tonight's calendar gap"
  },
  "editorial_voice": "Busy day but structured. The big risk is the 14:00-15:00 block — back-to-back meetings. Don't let the morning run over."
}
```

Opus thinks, Jimbo talks. The `editorial_voice` gives Jimbo a tone cue. The `day_plan` has reasoning he can paraphrase. Jimbo writes the actual Telegram message.

### Jimbo's New Skill (~60 lines)

Replaces both sift-digest (239 lines) and daily-briefing (167 lines).

```
Phase 1: Check for inputs
  - Read /workspace/briefing-input.json — if missing, say "Pipeline didn't run" and stop
  - Read /workspace/briefing-analysis.json — note if present (< 2 hours old) or absent

Phase 2: Compose
  IF briefing-analysis.json exists and fresh:
    Use Opus day plan, email highlights, surprise, editorial voice
    Format into Telegram message in your voice (SOUL.md personality)

  ELSE (self-compose mode):
    Build day plan from calendar + gems + vault tasks in briefing-input.json
    Pick 3-5 email highlights from gems, explain WHY
    Play surprise game if afternoon session

  ALWAYS:
    Calendar section uses ONLY events from briefing-input.json — add nothing
    Morning: full day plan, end with "anything you'd swap or skip?"
    Afternoon: rescue — what's left, what changed, what to let go
    Report pipeline failures from the pipeline status block
    If triage_pending > 0 and morning: announce, offer to schedule

Phase 3: Log
  Log to experiment-tracker (one command)
  Log to activity-log (one command)
```

Critical rule: **"The calendar section contains ONLY events from briefing-input.json. Do not add, infer, or fabricate any events."**

`sift-digest/SKILL.md` is retired. Its worker orchestration job moves to `briefing-prep.py`.

### Opus Layer (Option C)

#### Mac-side script: `opus-briefing.sh`

```bash
#!/bin/bash
set -euo pipefail

SESSION="${1:-morning}"
INPUT=$(ssh jimbo 'cat /workspace/briefing-input.json' 2>/dev/null) || exit 0
[ -z "$INPUT" ] && exit 0

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ANALYSIS=$(echo "$INPUT" | claude -p "$(cat "$SCRIPT_DIR/opus-prompts/${SESSION}.md")")

# Validate JSON before pushing
echo "$ANALYSIS" | python3 -c "import sys,json; json.load(sys.stdin)" || exit 0

echo "$ANALYSIS" | ssh jimbo 'cat > /workspace/briefing-analysis.json'
```

If anything fails (Mac offline, SSH down, claude errors, bad JSON), the script exits and the VPS fallback handles it.

#### Mac-side launchd: `com.marvin.opus-briefing.plist`

Two scheduled runs: 06:50 UTC (morning) and 14:50 UTC (afternoon).

#### Opus prompts

Two files: `opus-prompts/morning.md` (~40 lines) and `opus-prompts/afternoon.md` (~30 lines).

**Morning:** "Analyse today's data. Build a day plan around real calendar events and free gaps. Cross-reference email gems with vault tasks and priorities. Find surprising connections. One editorial sentence on the day's shape and main risk."

**Afternoon:** "This is the rescue check-in. What calendar events remain? What's new since morning? What's realistically achievable? What should Marvin let go of? Be honest about energy."

Both prompts include the JSON schema for `briefing-analysis.json` and the rule: calendar events are fixed facts, do not fabricate.

### Alerting and Monitoring

#### Drop
- Hourly email digest freshness checks
- "Morning: missing" detection via experiment-tracker (was broken)
- Gateway and model checks from sandbox
- All alerts before 07:00 UTC

#### Replace with

**Per-pipeline status (twice daily, after each briefing):**
```
07:05  ✅ Morning: 87 emails → 12 shortlisted → 5 gems |
       calendar: 4 events | vault: 3 tasks | opus: yes | $0.08
```

Sent by `briefing-prep.py` after the pipeline completes. One message, everything you need.

**Immediate failure alerts:**
```
06:35  ❌ email_triage worker failed: Flash API timeout.
       Briefing will proceed without triage.
```

Sent by `briefing-prep.py` as each step runs. Real-time visibility.

**Accountability check (20:00, unchanged):**
Reads from `briefing-prep.py`'s experiment-tracker logs instead of Jimbo's. More reliable source.

### Cron Schedule (new)

```
# 06:15 — morning briefing pipeline
15 6 * * * briefing-prep.py morning

# 06:45 — model swap to Sonnet (only needed when no Opus)
45 6 * * * model-swap-local.sh sonnet

# 07:30 — model swap back to Kimi
30 7 * * * model-swap-local.sh kimi

# 14:15 — afternoon briefing pipeline
15 14 * * * briefing-prep.py afternoon

# 14:45 — model swap to Sonnet (only needed when no Opus)
45 14 * * * model-swap-local.sh sonnet

# 15:30 — model swap back to Kimi
30 15 * * * model-swap-local.sh kimi

# 20:00 — daily accountability report
0 20 * * * accountability-check.py
```

Drops: hourly email fetch, hourly status check, 04:30 vault scoring (moves into morning prep), 05:00 tasks sweep (keeps its own cron or moves into prep).

### What Gets Retired

| Current | Replacement |
|---------|-------------|
| `sift-digest/SKILL.md` (239 lines) | `briefing-prep.py` (cron) |
| `daily-briefing/SKILL.md` (167 lines) | New skill (~60 lines) |
| Hourly `email-fetch-cron.py` | Fetch inside `briefing-prep.py` |
| Hourly `alert-check.py status` | Per-pipeline status from `briefing-prep.py` |
| Model swap logic | Conditional on Opus presence |

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Mac asleep | No Opus analysis | Jimbo self-composes with Sonnet (same as today) |
| `claude -p` rate limited | No Opus analysis | Same fallback |
| Flash API down | No email triage | briefing-prep reports failure, Jimbo works with raw digest |
| Haiku API down | No gems | briefing-prep reports, Jimbo has shortlist but no deep reads |
| Calendar API down | No calendar events | briefing-prep reports, Jimbo says "calendar unavailable" |
| VPS down | No briefing | Nothing we can do — same as today |
| briefing-prep.py crashes | No briefing-input.json | Jimbo says "pipeline didn't run", immediate Telegram alert |

Every failure is visible and reported. No silent degradation.

### Migration Path

Build in layers:
1. **Phase 1:** `briefing-prep.py` + new slimmed skill. Test with Jimbo self-composing (Option A only).
2. **Phase 2:** `opus-briefing.sh` + launchd + prompts. Test Opus analysis quality.
3. **Phase 3:** Model swap conditional on Opus presence. Drop hourly alerts.

Phase 1 is the foundation — it works standalone and is strictly better than today regardless of whether Phase 2 ever ships.
