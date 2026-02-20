# ADR-005: OpenRouter Model Selection

## Status

Updated (2026-02-20) — upgrading from free tier to Gemini 2.5 Flash for daily use

## Context

OpenRouter provides access to hundreds of models via a single API key. We need to pick models for different tiers: free for experimentation, cheap for daily use, premium for complex tasks. The VPS currently uses one model at a time (set in `openclaw.json`, requires restart to switch).

## Research (2026-02-16)

### Free models (best for agents)

| Model ID | Name | Context | Strengths |
|---|---|---|---|
| `stepfun/step-3.5-flash:free` | Step 3.5 Flash | 256K | Reasoning model, tool support, large context |
| `openrouter/aurora-alpha` | Aurora Alpha | 128K | Built for coding assistants and agentic workflows |
| `arcee-ai/trinity-large-preview:free` | Trinity Large Preview | 131K | Complex toolchain support |
| `nvidia/nemotron-3-nano-30b-a3b:free` | Nemotron 3 Nano 30B | 256K | Large context, free |

### Cheap models (< $0.50/1M input tokens)

| Model ID | Price (in/out per 1M) | Context | Strengths |
|---|---|---|---|
| `mistralai/devstral-2512` | $0.05 / $0.22 | 262K | Agentic coding, multi-file orchestration |
| `qwen/qwen3-coder-next` | $0.07 / $0.30 | 262K | Coding + tool use, same family as local Ollama models |
| `xiaomi/mimo-v2-flash` | $0.09 / $0.29 | 262K | #1 open-source on SWE-bench |
| `google/gemini-2.5-flash-lite` | $0.10 / $0.40 | 1.05M | Proven, massive context, Google |
| `mistralai/mistral-small-creative` | $0.10 / $0.30 | 32K | Creative tasks, smaller context |

### Premium models (for complex work)

| Model ID | Price (in/out per 1M) | Context | Strengths |
|---|---|---|---|
| `google/gemini-2.5-flash` | $0.30 / $2.50 | 1.05M | Built-in thinking, strong reasoning |
| `anthropic/claude-sonnet-4-5` | $3.00 / $15.00 | 200K | Best coding quality (via Anthropic key directly) |

### Cost estimates at these prices

At $0.10/1M input tokens (Gemini Flash Lite), processing 1000 messages/day averaging 500 tokens each:
- Daily: 500K tokens = $0.05/day
- Monthly: ~$1.50/month
- At free tier: $0/month

## Decision

### Phase 1 (2026-02-16): Free tier for experimentation

**Primary model:** `stepfun/step-3.5-flash:free`
- Best free option for agent use (reasoning + tool support + 256K context)
- Zero cost while we experiment and build trust in the system

### Phase 2 (2026-02-20): Upgrade to Gemini 2.5 Flash for daily use

**Problem:** The free model (`stepfun/step-3.5-flash:free`) can't follow the sift-digest skill's multi-file context + curation instructions. Morning briefings listed Checkatrade marketing and Audible sales as highlights — no taste or judgment applied.

**Evaluation for daily briefing (~75K input + ~1.5K output tokens):**

| Model | $/briefing | $/month | Verdict |
|-------|-----------|---------|---------|
| `qwen/qwen3-235b-a22b-thinking:free` | $0.00 | $0.00 | Best free option but 20 req/day limit |
| `google/gemini-2.5-flash-lite` | ~$0.008 | ~$0.24 | Ultra-cheap, decent |
| `google/gemini-2.5-flash` | ~$0.026 | ~$0.78 | Built-in thinking, strong reasoning |
| `anthropic/claude-haiku-4.5` | ~$0.083 | ~$2.49 | Excellent instruction-following |
| `anthropic/claude-sonnet-4.5` | ~$0.248 | ~$7.44 | Overkill for daily briefing |

**New primary model:** `google/gemini-2.5-flash` (direct Google AI API)
- Built-in thinking/reasoning is exactly what the curation task needs
- ~$0.78/month is trivial cost for usable daily briefings
- 1M token context handles all context files + full digest easily
- Pricing is identical via OpenRouter vs direct Google AI ($0.30/$2.50 per 1M tokens)
- Using direct Google AI avoids needing OpenRouter credits — one fewer dependency
- Fallback: step up to `anthropic/claude-haiku-4.5` (~$2.49/month) if quality isn't good enough

**Setup:** Add `GOOGLE_AI_API_KEY` to `/opt/openclaw.env` and configure the `google` provider in `openclaw.json`. See ADR-015 for the full working config and gotchas (baseUrl, model object schema, etc.).

### Model tiers

| Tier | Model | Cost | Use case |
|------|-------|------|----------|
| `free` | `openrouter/stepfun/step-3.5-flash:free` | $0 | Testing, non-critical tasks |
| `cheap` | `google/gemini-2.5-flash-lite` | ~$0.24/mo | Light daily use (direct Google AI) |
| `daily` | `google/gemini-2.5-flash` | ~$0.78/mo | **Daily briefings (direct Google AI, recommended)** |
| `coding` | `openrouter/qwen/qwen3-coder-next` | ~$0.07/1M | Code tasks (via OpenRouter) |
| `haiku` | `openrouter/anthropic/claude-haiku-4.5` | ~$2.49/mo | Upgrade if Gemini isn't good enough |
| `claude` | `anthropic/claude-sonnet-4-5` | premium | Complex work (direct Anthropic) |
| `opus` | `anthropic/claude-opus-4-5` | max | When quality matters most (direct Anthropic) |

### Model switching

Helper script at `scripts/model-swap.sh`:
```bash
./scripts/model-swap.sh daily    # google/gemini-2.5-flash (recommended)
./scripts/model-swap.sh free     # stepfun/step-3.5-flash:free
./scripts/model-swap.sh haiku    # anthropic/claude-haiku-4.5
./scripts/model-swap.sh status   # show current model
```

## Consequences

- Daily briefing cost rises from $0 to ~$0.78/month — trivial for usable quality
- Gemini 2.5 Flash has built-in thinking which should handle the multi-file curation task well
- Using direct Google AI API — same pricing as OpenRouter, one fewer dependency
- Clear upgrade path to Claude Haiku if Gemini quality disappoints
- Model switching is now scriptable via `model-swap.sh`
- Three providers in use: Google AI (daily), OpenRouter (free/coding/haiku), Anthropic (claude/opus)
