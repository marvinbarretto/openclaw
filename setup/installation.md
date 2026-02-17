# Installation

Actual steps taken on 2026-02-16. DigitalOcean 1-Click OpenClaw deploy.

## What we provisioned

- **Provider:** DigitalOcean
- **Plan:** $12/mo (2GB RAM, 1 vCPU, 50GB SSD)
- **Region:** LON1 (London)
- **Image:** OpenClaw 2.12 on Ubuntu 24.04
- **Droplet name:** `openclaw212onubuntu-s-1vcpu-2gb-lon1-01`
- **IP:** 167.99.206.214

## Pre-requisites

- [x] DigitalOcean account
- [x] SSH key on local machine (`~/.ssh/id_ed25519.pub`)
- [x] SSH key added to DigitalOcean during droplet creation

## How to connect

```bash
ssh jimbo
```

This uses the SSH config alias defined in `~/.ssh/config`:

```
Host jimbo
    HostName 167.99.206.214
    User root
    RequestTTY yes
```

`RequestTTY yes` bakes in the `-t` flag, so interactive TUI prompts and arrow keys work automatically. No need to type the IP or remember flags.

## What the 1-Click image gives you

Pre-installed and ready:
- OpenClaw 2026.2.12 at `/usr/bin/openclaw`
- Caddy reverse proxy (auto TLS via LetsEncrypt, works via IP — no domain needed)
- Containerized agent isolation (Docker)
- Gateway token auth
- Dashboard at `https://167.99.206.214`

## Setup steps (what we actually did)

1. **Created droplet** from DigitalOcean Marketplace → OpenClaw 1-Click
2. **SSH'd in:** `ssh -t root@167.99.206.214`
3. **Selected AI provider:** Anthropic (option 3 in the onboarding wizard)
4. **Entered Anthropic API key** (created a dedicated `openclaw-vps` key)
5. **Paired dashboard:**
   - Opened `https://167.99.206.214` in browser
   - Went to Overview panel → pasted gateway token → clicked Connect
   - Back in SSH, typed `continue`
6. **Enabled Telegram** (see below — needed manual fix)

## Telegram setup (needed manual intervention)

The TUI wizard cancelled before saving. Had to do it manually:

```bash
# 1. Set the bot token in env file
#    Edit /opt/openclaw.env — uncomment and set:
TELEGRAM_BOT_TOKEN=<your-bot-token>

# 2. Enable Telegram in the JSON config
#    In /home/openclaw/.openclaw/openclaw.json, set:
#    "telegram": { "enabled": true }

# 3. Run doctor fix
/opt/openclaw-cli.sh doctor --fix

# 4. Restart
systemctl restart openclaw

# 5. Verify Telegram is running
journalctl -u openclaw --no-pager -n 15 | grep telegram
# Should see: [telegram] [default] starting provider (@your_bot_name)

# 6. Message the bot on Telegram — it will give you a pairing code
# 7. Approve pairing:
/opt/openclaw-cli.sh pairing approve telegram <PAIRING_CODE>
```

## Key files on the VPS

| File | Purpose |
|---|---|
| `/opt/openclaw.env` | Environment variables (API keys, bot tokens) |
| `/home/openclaw/.openclaw/openclaw.json` | Main config — **service user** (plugins, channels, model, sandbox) |
| `/root/.openclaw/openclaw.json` | Config — **root user** (layered on top, used by `openclaw config set`) |
| `/tmp/openclaw/openclaw-2026-02-16.log` | Daily log file |

**Important:** OpenClaw uses **layered config**. `openclaw config set` (run as root) writes to `/root/.openclaw/openclaw.json`, but the service runs as the `openclaw` user and reads `/home/openclaw/.openclaw/openclaw.json`. Always edit the service user's config directly for reliability.

## Helper scripts

```bash
/opt/restart-openclaw.sh       # Restart with status check
/opt/status-openclaw.sh        # Show status and token
/opt/update-openclaw.sh        # Update to latest version
/opt/openclaw-cli.sh           # Run CLI commands
/opt/openclaw-tui.sh           # Launch interactive TUI
```

## Useful commands

```bash
# Check service status
systemctl status openclaw

# Tail logs live
journalctl -u openclaw -f

# Check channel status
/opt/openclaw-cli.sh channels status

# List configured channels
/opt/openclaw-cli.sh channels list

# Restart after config changes
systemctl restart openclaw
```

## Sandbox Architecture (Docker)

The agent runs inside a Docker container (`openclaw-sandbox:bookworm-slim`). The container is **minimal** — it has almost nothing installed by default.

### What's mounted into the sandbox

Configured via `agents.defaults.sandbox.docker.binds` in `openclaw.json`:

```
/home/openclaw/homebrew:/home/openclaw/homebrew:ro    # CLI tools (gh, etc)
/opt/openclaw:/opt/openclaw:ro                         # Env file (but NOT loaded as env vars)
/usr/lib/node_modules/openclaw/skills:...skills:ro     # Skill definitions
/etc/ssl/certs:/etc/ssl/certs:ro                       # CA certificates (for HTTPS)
```

### Environment variables inside sandbox

Configured via `agents.defaults.sandbox.docker.env` in `openclaw.json`:

```json
"env": {
  "GH_TOKEN": "github_pat_...",
  "JIMBO_GH_TOKEN": "github_pat_..."
}
```

| Var | Account | Scope | Access |
|---|---|---|---|
| `GH_TOKEN` | `marvinbarretto` | Spoons, LocalShout, Pomodoro | Read-only, 60-day expiry |
| `JIMBO_GH_TOKEN` | `marvinbarretto-labs` | `jimbo-workspace` | Read+write, 90-day expiry |

**Key gotcha:** Mounting `/opt/openclaw.env` as a file does NOT make its contents available as environment variables. You must explicitly set env vars in the `docker.env` config object.

### Runtimes in sandbox — custom Docker image

The default `bookworm-slim` image has no runtimes. We built a custom image with Python, Node, and git baked in.

**Why not homebrew mount?** Homebrew binaries compiled on the host (Ubuntu 24.04, glibc 2.39) won't run inside the container (Debian 12, glibc 2.36). glibc mismatch.

**Why not `setupCommand`?** The docs recommend it, but OpenClaw's sandbox drops ALL Linux capabilities (`CapDrop: ALL`) and sets `no-new-privileges`. `apt-get` needs `SETUID`/`SETGID` to switch to the `_apt` user, so it fails at runtime.

**Solution: bake packages into a custom image at build time** (no capability restrictions during `docker build`).

The Dockerfile is tracked in this repo at `sandbox/Dockerfile`. To deploy:

```bash
# Copy to VPS and build
scp sandbox/Dockerfile root@167.99.206.214:/tmp/Dockerfile.jimbo
ssh jimbo 'docker build -f /tmp/Dockerfile.jimbo -t openclaw-sandbox:bookworm-slim /tmp/'

# Recreate the sandbox container
ssh jimbo 'docker rm -f $(docker ps -aq --filter name=openclaw-sbx) && systemctl restart openclaw'
```

**Critical: do NOT add `USER openclaw`** to the Dockerfile. The `openclaw` user doesn't exist in the image — OpenClaw creates it at container runtime. Adding it causes: `unable to find user openclaw: no matching entries in passwd file`.

**Available in sandbox (2026-02-17):**
- Python 3.11.2
- Node v18.20.4 / npm 9.2.0
- TypeScript 5.x, ts-node (global)
- jq, curl, make
- git, ca-certificates
- npm (with cache redirected to `/workspace/.npm-cache` — see below)

**Note:** Homebrew Python 3.14 and Node 25 are also installed on the host for non-sandbox use. The sandbox uses the Debian apt versions instead (glibc compatible).

### Workspace write permissions

The sandbox has `ReadonlyRootfs=true` and drops ALL Linux capabilities (including `DAC_OVERRIDE`). The container runs as root (uid 0), but the workspace bind-mount is owned by `openclaw` (uid 1000) with `755` permissions. Without `DAC_OVERRIDE`, root **cannot** bypass file permissions — so shell commands can't write to `/workspace` even though `workspaceAccess: "rw"` is set in config.

**Fix (run once on the host):**

```bash
chmod -R o+w /home/openclaw/.openclaw/workspace
```

This allows any user (including root-without-capabilities) to write to the workspace. Without this fix:
- OpenClaw's Write tool works (it writes from the host side, outside the container)
- But all shell commands fail: `npm install`, `git commit`, `node` writing output files, `python` scripts — anything that creates or modifies files from inside the container

**npm cache fix:** The Dockerfile sets `npm_config_cache=/workspace/.npm-cache` because npm's default cache (`/root/.npm`) is on the read-only root filesystem. This redirects caching to the writable workspace mount.

**fchown warnings:** `npm install` produces `TAR_ENTRY_ERROR EPERM: operation not permitted, fchown` warnings. These are harmless — npm tries to set file ownership but `CHOWN` capability is dropped. Files still extract correctly, they just keep the current user's ownership.

### Container lifecycle

- Container spawns on first agent message, persists across conversations
- `openclaw sandbox recreate --all` doesn't work if containers aren't tracked — use `docker rm -f` directly
- After config changes: kill the container + restart the service for changes to take effect

```bash
# Nuclear option — force container recreation after config changes
docker rm -f $(docker ps -q --filter name=openclaw-sbx)
systemctl restart openclaw
# Container will respawn on next Telegram message
```

### Lessons learned the hard way

1. **No CA certs by default** — `bookworm-slim` doesn't include `/etc/ssl/certs/`. Any HTTPS call (including `gh` to GitHub API) fails with TLS errors. Fix: bind-mount host certs, or bake `ca-certificates` into custom image.
2. **`openclaw config set` writes to root's config** — not the service user's. Always edit `/home/openclaw/.openclaw/openclaw.json` directly.
3. **Stale containers** — Config changes don't affect running containers. Must `docker rm -f` and recreate. Always check `docker ps -a` (not just `docker ps`) for "Created" but not running containers.
4. **`gh` needs both the binary AND the token** — binary via homebrew mount, token via `docker.env`.
5. **glibc mismatch** — Host (Ubuntu 24.04) has glibc 2.39, container (Debian 12) has 2.36. Homebrew binaries compiled on the host won't run in the container. Use apt packages baked into a custom image instead.
6. **`setupCommand` doesn't work with apt** — sandbox drops ALL capabilities and sets `no-new-privileges`. `apt-get` needs `SETUID`/`SETGID`. Even setting `user: '0:0'` and `readOnlyRoot: false` doesn't help. Only solution: install at image build time.
7. **Never add `USER openclaw` to Dockerfile** — OpenClaw creates this user at container runtime. Adding it to the Dockerfile causes a fatal startup error.
8. **systemd PATH order matters** — `/etc/systemd/system/openclaw.service` had homebrew before `/usr/bin` in PATH. Installing Node via homebrew made OpenClaw use Node 25 instead of its bundled Node 22, crashing Telegram. Fix: move homebrew to end of PATH.
9. **`openclaw logs --follow` uses root config** — which doesn't have the gateway token. Use `journalctl -u openclaw -f` instead for service logs.
10. **Shell can't write to `/workspace`** — `ReadonlyRootfs=true` + `CapDrop: ALL` means root in the container can't override `755` permissions on the workspace (owned by uid 1000). The Write tool works (host-side), but shell commands fail. Fix: `chmod -R o+w /home/openclaw/.openclaw/workspace` on the host.
11. **npm install fails with EROFS** — npm's cache defaults to `/root/.npm` which is on the read-only root filesystem. Fix: set `npm_config_cache=/workspace/.npm-cache` in the Dockerfile (already done in `sandbox/Dockerfile`).

## Troubleshooting

- **SSH arrow keys don't work in TUI:** Use `ssh -t` (allocates proper TTY)
- **SSH disconnects while idle:** Timeout — just reconnect, droplet is still running
- **Telegram "configured, not enabled":** Edit `openclaw.json`, set `"enabled": true`, restart
- **TUI wizard cancels mid-setup:** Set values directly in `/opt/openclaw.env` and `/home/openclaw/.openclaw/openclaw.json`
- **API billing error:** Check provider dashboard balance. Consider switching to OpenRouter for cheaper models.
- **Agent can't reach GitHub (TLS error):** Mount CA certs into sandbox — add `/etc/ssl/certs:/etc/ssl/certs:ro` to `docker.binds`
- **Agent says GH_TOKEN is empty:** Set it in `docker.env` config, kill container, restart service
- **`openclaw config set` didn't work:** It wrote to `/root/.openclaw/openclaw.json` — edit `/home/openclaw/.openclaw/openclaw.json` instead
- **`setupCommand` fails with apt-get:** Sandbox drops all capabilities. Use a custom Docker image instead (see Runtimes section above)
- **Container won't start — "unable to find user openclaw":** You added `USER openclaw` to a custom Dockerfile. Remove it — OpenClaw creates the user at runtime
- **Stale container after image rebuild:** Run `docker ps -a` — look for "Created" containers. `docker rm -f` them before restarting
- **OpenClaw crashes after installing Node via homebrew:** Homebrew Node (v25) replaced system Node (v22) in PATH. Check `/etc/systemd/system/openclaw.service` PATH order — `/usr/bin` must come before homebrew
- **`openclaw logs --follow` says "unauthorized":** It reads root's config. Use `journalctl -u openclaw -f` instead
- **Shell commands can't write to `/workspace`:** Workspace is owned by uid 1000 with 755 perms, container runs as root (uid 0) with all capabilities dropped. Run `chmod -R o+w /home/openclaw/.openclaw/workspace` on the host.
- **`npm install` fails with EROFS (read-only file system):** npm cache is at `/root/.npm` on the read-only rootfs. Ensure `npm_config_cache=/workspace/.npm-cache` is set in the Dockerfile.
- **`npm install` shows TAR_ENTRY_ERROR fchown warnings:** Harmless — `CHOWN` capability is dropped. Files still install correctly.
