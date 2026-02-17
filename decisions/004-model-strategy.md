# ADR-004: Local + Cloud Model Strategy

## Status

Accepted

## Context

24GB MacBook Air (Apple Silicon) can run 7B–14B models locally via Ollama. The VPS (2GB RAM, no GPU) cannot run local models — it uses cloud APIs only. Goal: run the bulk of inference locally for free, reserve paid APIs for always-on VPS tasks and complex work.

## Decision

### Three tiers

| Tier | Where | Models | Cost | Use for |
|---|---|---|---|---|
| **Local** | MacBook Air (Ollama) | Qwen 2.5 7B, Qwen 2.5 Coder 14B | Free | Email triage, bulk summarization, sandbox coding, prototyping |
| **Cheap cloud** | VPS (always-on) | Gemini Flash, Claude Haiku | ~$5-10/mo | Telegram bot, async tasks, Reader duties when laptop is off |
| **Premium cloud** | Either | Claude Sonnet/Opus | Pay-per-use | Complex coding, nuanced analysis — human-triggered only |

### Ollama on MacBook Air

```bash
brew install ollama
ollama pull qwen2.5:7b            # Reader — classification, triage (~8GB)
ollama pull qwen2.5-coder:14b     # Actor — coding tasks (~10GB)
```

- Don't run both simultaneously — swap as needed
- 24GB budget: ~4-6GB for macOS, leaves plenty for one model at a time

### Cost control

- **Hard cap: £25/month** on all cloud LLM spend combined
- Set budget alerts at £15 (warning) and £25 (hard stop) on Claude/Gemini dashboards
- VPS uses Gemini Flash by default (~$0.075/1M input tokens)
- Premium cloud is manual-only — agent never auto-escalates to expensive models
- Email triage uses local Ollama only — zero cloud cost for the highest-volume task

### Email-specific: fully offline inference

The email Reader model runs with **no network access** (see ADR-002):
- Local Ollama on laptop (preferred) or VPS with swap
- No LLM API calls — email content never leaves the machine
- This eliminates the data exfiltration risk where email bodies are sent to cloud LLM providers as prompt context

## Consequences

- 90%+ of inference is free (local)
- Email triage (the high-volume task) costs nothing and is fully offline
- Cloud spend is capped at £25/mo — predictable budget
- Local models are slower (~10-30 tok/s) but fine for async batch work
- Need to manage two environments (Ollama + cloud APIs)
