# ADR-015: Model Upgrade — Gemini 2.5 Flash via Direct Google AI API

## Status

Accepted

## Context

Two problems with Jimbo's email briefing quality:

1. **Classifier too permissive:** The local Ollama classifier (qwen2.5:7b) was queuing 138 out of 142 emails (~97% pass-through). Checkatrade marketing and Wetherspoons receipts were getting through. The ALWAYS SKIP list was too vague for a 7B model.

2. **VPS model too weak:** `stepfun/step-3.5-flash:free` couldn't follow the sift-digest skill's multi-file context + curation instructions. Morning briefings listed everything instead of curating.

## Decision

### Classifier changes (local Ollama)

- **Default model:** `qwen2.5:7b` → `qwen2.5-coder:14b` (already downloaded, 9GB)
- **Prompt rewrite:** Massively expanded the ALWAYS SKIP list with concrete brand names, email types, and sender patterns. Removed the "USE JUDGMENT" section for newsletters — all newsletters now queue by default. The classifier is a coarse filter; Jimbo does the thinking.
- **Target:** ~50% queue rate (down from ~97%)

### VPS model changes

- **Model:** `stepfun/step-3.5-flash:free` → `google/gemini-2.5-flash`
- **Provider:** Direct Google AI API (not via OpenRouter)
- **Cost:** ~$0.78/month for daily briefings (identical to OpenRouter pricing)
- **Why direct:** Already had a Gemini API key, avoids needing OpenRouter credits, one fewer dependency

### OpenClaw provider config (gotchas documented)

The `models.providers` schema in `openclaw.json` is strict. We hit three config validation errors before getting it right:

1. **`baseUrl` is required** — can't omit it. Must be `https://generativelanguage.googleapis.com/v1beta`
2. **`models` array is required** — can't omit it
3. **`models` entries must be objects** — not strings. Each needs: `id`, `name`, `reasoning`, `input`, `cost`, `contextWindow`, `maxTokens`
4. **`GOOGLE_AI_API_KEY` must be in `/opt/openclaw.env`** — the systemd service loads this via `EnvironmentFile=`. Adding the key after boot requires `systemctl daemon-reload && systemctl restart openclaw`
5. **The `/v1beta` path matters** — without it, API calls return 404. The baseUrl must include the API version.

Working config:
```json
"models": {
  "providers": {
    "google": {
      "baseUrl": "https://generativelanguage.googleapis.com/v1beta",
      "apiKey": "${GOOGLE_AI_API_KEY}",
      "api": "google-generative-ai",
      "models": [
        {
          "id": "gemini-2.5-flash",
          "name": "Gemini 2.5 Flash",
          "reasoning": true,
          "input": ["text", "image"],
          "cost": { "input": 0.3, "output": 2.5, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 1000000,
          "maxTokens": 8192
        }
      ]
    }
  }
}
```

### model-swap.sh updates

Added `daily` tier (google/gemini-2.5-flash) and `haiku` tier (anthropic/claude-haiku-4.5). Gemini tiers now use `google/` prefix (direct) instead of `openrouter/google/`.

## Consequences

- Daily briefing cost rises from $0 to ~$0.78/month — trivial for usable quality
- Three providers now in use: Google AI (daily), OpenRouter (free/coding), Anthropic (claude/opus)
- Classifier prompt is much longer but gives the small model concrete rules instead of vague guidance
- The `/v1beta` baseUrl and full model object schema are critical gotchas — document for future reference
- Need to verify classifier improvement by running on same batch before/after (not yet done)
- Need to monitor Gemini briefing quality over next few days — fallback to Claude Haiku if needed
