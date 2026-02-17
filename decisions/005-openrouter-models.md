# ADR-005: OpenRouter Model Selection

## Status

Accepted

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

### Current: Free tier for experimentation

**Primary model:** `stepfun/step-3.5-flash:free`
- Best free option for agent use (reasoning + tool support + 256K context)
- Zero cost while we experiment and build trust in the system

### Upgrade path

1. **Free** → `stepfun/step-3.5-flash:free` (now)
2. **Cheap** → `google/gemini-2.5-flash-lite` or `mistralai/devstral-2512` (when we add OpenRouter credits)
3. **Coding tasks** → `qwen/qwen3-coder-next` (same Qwen family as local models)
4. **Premium** → Anthropic Claude via direct API key (already configured)

### Model switching

Currently requires editing `openclaw.json` and restarting:
```bash
# On VPS:
# Edit /home/openclaw/.openclaw/openclaw.json → agents.defaults.model.primary
# Then: systemctl restart openclaw
```

**TODO:** Write a helper script for quick model swaps:
```bash
# Desired UX:
model-swap free          # stepfun/step-3.5-flash:free
model-swap cheap         # google/gemini-2.5-flash-lite
model-swap coding        # qwen/qwen3-coder-next
model-swap premium       # anthropic/claude-sonnet-4-5
```

## Consequences

- Zero cost for experimentation phase
- Free models may have lower quality — monitor and switch if needed
- Model switching is manual (restart required) — helper script will improve this
- OpenRouter single API key gives access to all models — no need for separate accounts
