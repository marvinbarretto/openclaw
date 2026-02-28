# How to Switch Jimbo's Model

From laptop:

```bash
./scripts/model-swap.sh status   # see current model
```

## Tiers

| Command | Model | Cost |
|---------|-------|------|
| `./scripts/model-swap.sh free` | stepfun/step-3.5-flash:free | $0 |
| `./scripts/model-swap.sh cheap` | gemini-2.5-flash-lite | ~$0.24/mo |
| `./scripts/model-swap.sh daily` | gemini-2.5-flash | ~$0.78/mo |
| `./scripts/model-swap.sh coding` | qwen3-coder-next | ~$0.07/1M tokens |
| `./scripts/model-swap.sh haiku` | claude-haiku-4.5 (OpenRouter) | ~$2.49/mo |
| `./scripts/model-swap.sh claude` | claude-sonnet-4.5 (Anthropic) | premium |
| `./scripts/model-swap.sh opus` | claude-opus-4.5 (Anthropic) | max quality |

## When to switch

- **Low OpenRouter credits alert** → `daily` or `free` (these use Google AI / free tier, not OpenRouter)
- **Want quality briefings** → `haiku`
- **Just testing** → `free`

The script SSHs into the VPS, updates openclaw.json, and restarts the service. Takes ~5 seconds.
