# VPS Operations Gotchas

## After Reboot

- **Sandbox doesn't auto-start.** After `reboot`, run: `docker start $(docker ps -a -q --filter name=openclaw-sbx)`
- OpenClaw service restarts automatically via systemd. Sandbox container does not.

## SSH & Access

- **`ssh jimbo` only works from Marvin's laptop** (SSH alias in `~/.ssh/config`). On the VPS itself, run commands directly.
- SSH connection multiplexing is configured (`ControlMaster auto`) for reliability with rsync.

## API Keys & Environment

- **`grep API_KEY /opt/openclaw.env`** picks up `ANTHROPIC_API_KEY` first, not `JIMBO_API_KEY`. Always use `grep JIMBO_API_KEY` specifically.
- The jimbo-api service uses env var `API_KEY`. Sandbox scripts use `JIMBO_API_KEY`. Same value, different names.

## Sandbox Networking

- **Sandbox API URL is `https://167.99.206.214`** (routed through Caddy), not `localhost:3100` or Docker bridge `172.17.0.1`.
- The sandbox can't reach the host via Docker bridge on this VPS — always use the public IP through Caddy.
- `JIMBO_API_URL` in `/opt/openclaw.env` is set to `https://167.99.206.214` for this reason.

## System Maintenance

- **Kernel upgrade warnings** are cosmetic — safe to ignore or reboot at convenience. Reboot takes ~60s.
- **sqlite3 CLI** not installed by default on Ubuntu — `apt install sqlite3` if needed for manual DB queries.
- VPS rate-limits SSH after ~5 rapid connections — always batch with rsync, never per-file scp.
