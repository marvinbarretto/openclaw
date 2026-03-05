---
name: daily-briefing
description: Compose and deliver the morning or afternoon briefing from pre-computed pipeline data
user-invokable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or it's a scheduled briefing session, compose a briefing from the pre-computed pipeline data.

## Step 1: Read inputs

Run in the sandbox:

1. `cat /workspace/briefing-input.json`
2. `cat /workspace/briefing-analysis.json 2>/dev/null || echo 'null'`
3. `cat /workspace/SOUL.md`

If `briefing-input.json` is missing or older than 4 hours, say: "Pipeline hasn't run yet today. Ask me to check email if you want a manual scan."

If `briefing-analysis.json` exists and is less than 2 hours old, you are in **Opus-assisted mode** — the hard thinking is done. Your job is to deliver it in your voice.

If `briefing-analysis.json` is missing or stale, you are in **self-compose mode** — build the day plan yourself from the raw data.

## Step 2: Compose the briefing

### HARD RULES (both modes)

- **Calendar contains ONLY events from briefing-input.json.** Do not add, infer, or fabricate any events. If there are 4 events, show 4 events. If there are 0 events, say "nothing on the calendar today."
- **Email highlights come from the gems array.** Do not re-triage the digest yourself.
- **Report pipeline failures honestly.** If `pipeline.triage.status` is `"failed"`, say so: "Email triage didn't run today — highlights may be incomplete."

### Opus-assisted mode

Use the `briefing-analysis.json` data:
- Present the `day_plan` entries as time-blocked suggestions with the reasoning
- Present `email_highlights` with the editorial commentary
- If `surprise` is not null, present it
- Use `editorial_voice` to set your tone
- Rewrite everything in your own voice (SOUL.md personality) — don't just dump the JSON

### Self-compose mode

Build from `briefing-input.json`:
- **Calendar:** List events chronologically. Flag anything in the next 2 hours.
- **Day plan:** Identify free gaps between events. Cross-reference gems and vault_tasks. Suggest 3-5 activities with reasoning.
- **Email highlights:** Pick the top 3-5 gems by confidence. Explain WHY each matters.
- **Vault tasks:** Surface the top 2-3 from `vault_tasks` array. Weave into the day plan.
- **Surprise game (afternoon only):** Pick the best `surprise_candidate: true` gem, or make your own connection.

### Both modes

- **Morning:** Full day plan. End with "Anything you'd swap or skip?"
- **Afternoon:** Rescue framing. What's left today? What changed since morning? What to let go of?
- If `triage_pending > 0` and morning: "I picked up **{triage_pending} tasks** that need your input. When's good for a 15-min triage?"
- Keep it scannable — under 1 minute to read.

## Step 3: Log (MANDATORY)

After delivering the briefing, always run both:

```bash
python3 /workspace/experiment-tracker.py log \
    --task briefing-synthesis \
    --model <your-model> \
    --input-tokens <est> --output-tokens <est> \
    --session <morning|afternoon> \
    --conductor-rating <1-10> \
    --conductor-reasoning '{"mode": "<opus-assisted|self-compose>", "gems_used": <N>, "calendar_events": <N>}'

python3 /workspace/activity-log.py log \
    --task briefing \
    --description "<Morning|Afternoon> briefing: <brief summary>" \
    --outcome "<success|partial>" \
    --rationale "mode=<opus-assisted|self-compose>, calendar=<N events>, email=<N gems>, vault=<N tasks>" \
    --model <your-model>
```
