---
name: sift-digest
description: RETIRED — email orchestration now handled by briefing-prep.py cron job
user-invokable: true
---

# Email Digest (Retired)

This skill has been replaced by the cron-driven `briefing-prep.py` pipeline.

If you've been asked to check email or run the digest:
1. Check if `/workspace/briefing-input.json` exists — if so, the pipeline already ran
2. If it doesn't exist or is stale, run: `python3 /workspace/briefing-prep.py morning` (or afternoon)
3. Then follow the `daily-briefing` skill to compose and deliver

Do NOT attempt to spawn sub-agents or run workers directly. The pipeline handles this.
