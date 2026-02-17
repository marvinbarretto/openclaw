# VPS Comparison

## Requirements

- Run OpenClaw + Telegram bot 24/7
- Enough RAM for LLM API calls and skill execution
- Low latency to Telegram servers (EU or US)
- Disposable 30-day experiment

## Options

| Provider | Plan | Price/mo | RAM | vCPUs | Storage | Location | OpenClaw support |
|---|---|---|---|---|---|---|---|
| **DigitalOcean** | Basic | $12 | 2 GB | 1 | 50 GB SSD | US/EU/SGP | 1-Click deploy, hardened image, official tutorial |
| **DigitalOcean** | Recommended | $24 | 4 GB | 2 | 80 GB SSD | US/EU/SGP | Same 1-Click, more headroom |
| **Hostinger** | KVM 1 | $8.99 | 4 GB | 2 | 50 GB NVMe | US/EU/Asia | Manual setup |
| **Hetzner** | CX22 | ~$4.60 | 4 GB | 2 | 40 GB | EU only | Manual setup |

## DigitalOcean 1-Click Advantages

What you get out of the box that you'd have to set up manually elsewhere:

- **Caddy reverse proxy** — auto-provisions LetsEncrypt TLS certs, works via IP (no domain needed)
- **Containerized agent isolation** — agents run in isolated Docker containers, can't read host API keys
- **Gateway token auth** — auto-generated, restricts access to authorized users
- **Non-root execution** — limits blast radius
- **Pairing mechanism** — built-in Telegram pairing (`openclaw pairing approve telegram <CODE>`)
- **Onboarding wizard** — `openclaw onboard --install-daemon` handles API keys, channels, daemon setup
- **Tailscale integration** — secure dashboard access without exposing ports
- **Update script** — one-command updates

## Decision

**DigitalOcean $12/mo plan** (with 2GB swap added)

Rationale:
- 1-Click deploy saves hours of manual hardening that we'd have to do on Hostinger
- Agent containerization IS the sandbox architecture — it's built in
- Official OpenClaw tutorial and community support
- $3 more than Hostinger but security hardening is done for you
- $12 plan is now officially supported (as of Feb 2026)
- Per-second billing — only pay for what you use in the 30-day experiment
- Can upgrade to $24 plan if 2GB feels tight (likely won't need to with API-only inference)
