# Networking & DNS

## Domain

- TBD — could use a subdomain of an existing domain (e.g. `claw.example.com`)

## Cloudflare Setup

- [ ] Add domain/subdomain to Cloudflare
- [ ] Point A record to VPS IP
- [ ] Enable proxy (orange cloud) for HTTPS termination
- [ ] Set SSL mode to **Full (Strict)**

## Firewall Ports

| Port | Service | Notes |
|---|---|---|
| 22 | SSH | Restrict to known IPs if possible |
| 443 | HTTPS | Cloudflare proxy only |
| 80 | HTTP | Redirect to 443 |

## Telegram Webhook

- Telegram sends updates to `https://your-domain/webhook`
- Must be HTTPS with a valid cert (Cloudflare handles this)
- Set webhook via Bot API: `setWebhook(url=...)`

## Current State (2026-02-16)

- Domain: not configured yet — using IP directly (`167.99.206.214`)
- Caddy handles TLS automatically via LetsEncrypt (even on bare IP)
- Dashboard accessible at `https://167.99.206.214`
- Telegram uses polling (not webhooks), so no inbound port needed for Telegram
- Cloudflare DNS setup deferred — not needed for the 30-day experiment

## Notes

- Marvin is an existing Cloudflare customer, so DNS setup is available if needed later
- The 1-Click image includes Caddy, which handles TLS without Cloudflare
- For a 30-day disposable experiment, bare IP + Caddy is fine
