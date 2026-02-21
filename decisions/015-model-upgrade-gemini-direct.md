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

### Gemini thinking leak (known issue)

Gemini 2.5 Flash with `"reasoning": true` leaks its chain-of-thought into the response text. The thinking appears before the actual briefing in Telegram ("Okay, I have read all the context files... Let me check...").

**What we tried:**
- `"reasoning": false` in model config → thinking stops but briefing quality drops significantly (shallow, no curation depth)
- `"reasoning": true` + SOUL.md instruction "Never show your working" → reduces it slightly but Gemini still does it
- `agents.defaults.thinking: "off"` → not a valid config key in OpenClaw 2026.2.12, crashes the service

**Current state:** `reasoning: true` with SOUL.md instruction. Thinking leaks but briefing quality is good — proper event highlights, travel deals with prices, context-aware grouping, security alerts surfaced. The substance matters more than the cosmetics.

**To fix later:**
- Check if a future OpenClaw update adds thinking token filtering for the `google-generative-ai` provider
- Or try a model that separates thinking from output natively (Claude Haiku would do this correctly)
- The `--thinking` CLI flag exists per-session but there's no persistent config equivalent yet

### SOUL.md update

Added "Output Rules" section to SOUL.md on VPS telling Jimbo to never show his working. This helps generally even if it doesn't fully fix the Gemini thinking leak.

## Consequences

- Daily briefing cost rises from $0 to ~$0.78/month — trivial for usable quality
- Three providers now in use: Google AI (daily), OpenRouter (free/coding), Anthropic (claude/opus)
- Classifier prompt is much longer but gives the small model concrete rules instead of vague guidance
- The `/v1beta` baseUrl and full model object schema are critical gotchas — document for future reference
- **Gemini thinking leak:** reasoning tokens appear in Telegram output. Cosmetic issue — quality is good. Parked for now.
- Need to verify classifier improvement by running on same batch before/after (not yet done)
- Need to monitor Gemini briefing quality over next few days — fallback to Claude Haiku if needed

## Rate Limits (observed 2026-02-20)

Hit `429 RESOURCE_EXHAUSTED` errors — `GenerateContentPaidTierInputTokensPerModelPerMinute` quota exceeded (1M tokens/min). Saw 1.65M peak TPM, 39 RPD.

**Root cause:** The `GOOGLE_AI_API_KEY` was shared with another project ("Watford Events") under the same Google Cloud project. The other app's traffic consumed most of the per-minute token quota, leaving insufficient headroom for Jimbo.

**Lesson:** Always use a dedicated API key per project/application. Google AI rate limits are per-project, not per-key — but separate projects get separate quotas.

**TODO:**
- [ ] Create a dedicated Google Cloud project for OpenClaw/Jimbo
- [ ] Generate a new API key under that project
- [ ] Update `/opt/openclaw.env` on VPS with the new key
- [ ] Restart openclaw service
- [ ] Restrict the new key to VPS IP (167.99.206.214) via Google Cloud Console API key restrictions
