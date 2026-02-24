---
name: cost-tracker
description: Log API costs and monitor budget for every interaction
user-invokable: false
---

# Cost Tracker

Log the estimated token cost of every API interaction you make. This builds a cost history that Marvin can review on his dashboard.

## When to log

Log costs after **every** interaction where you call an LLM API. This includes:
- Heartbeat checks
- Morning briefings
- Email digest processing
- Research tasks
- Blog post writing
- Chat responses
- Day planning
- Nudges

## How to log

After each interaction, estimate your token usage and run:

```bash
python3 /workspace/cost-tracker.py log \
  --provider google \
  --model gemini-2.5-flash \
  --task heartbeat \
  --input-tokens 500 \
  --output-tokens 200
```

### Parameters

- `--provider`: The API provider (`google`, `anthropic`, `openrouter`)
- `--model`: The model name (`gemini-2.5-flash`, `claude-haiku-4.5`)
- `--task`: What type of task this was (`heartbeat`, `briefing`, `chat`, `research`, `blog`, `email-check`, `nudge`, `own-project`, `digest`, `day-planner`)
- `--input-tokens`: Estimated input tokens
- `--output-tokens`: Estimated output tokens
- `--notes`: Optional context about what this interaction was for

### Estimating tokens

You won't always know exact token counts. Use reasonable estimates:
- Short heartbeat check: ~300 input, ~150 output
- Briefing with context files: ~3000 input, ~500 output
- Email digest read: ~5000 input, ~400 output
- Research task: ~2000 input, ~800 output
- Blog post: ~2000 input, ~1500 output
- Chat message: ~500 input, ~300 output

## Budget checks

At the end of each day (~22:00), run a budget check:

```bash
python3 /workspace/cost-tracker.py budget --check
```

If `alert` is true in the response, warn Marvin: "Heads up — we've used X% of this month's budget ($Y of $Z)."

## Weekly summary

On Sundays (~10:00), include a cost summary in your weekly report:

```bash
python3 /workspace/cost-tracker.py summary --days 7
```

## Dashboard export

The auto-commit heartbeat task will handle exporting data for the dashboard. You don't need to run export manually unless asked.

## Rules

- Always log costs, even for cheap interactions — the data is more valuable than the effort
- Don't skip logging because an interaction was free or nearly free
- Round token estimates to the nearest 50 — precision isn't critical
- If you're unsure about token counts, estimate conservatively (round up)
