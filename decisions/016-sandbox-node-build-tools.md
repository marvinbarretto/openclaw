# ADR-016: Sandbox Node Build Tools Fix

## Status

Accepted (2026-02-20)

## Context

npm and Node build tools (Astro, webpack, Angular CLI, React) were listed as BROKEN in the sandbox since ADR-011 (2026-02-18). The root cause was documented as "uid mismatch causes fchown errors" but the actual blockers were more nuanced:

**Three separate issues were conflated:**

1. **fchown warnings** — npm tries to `chown` extracted packages but the `CHOWN` capability is dropped. These warnings are **harmless** — packages install correctly, they just keep root's ownership.

2. **EROFS (read-only filesystem)** — Tools try to write config/cache to `$HOME` (defaulting to `/root/`), which is on the read-only root filesystem. Astro's telemetry writes to `~/.config/astro`, npm's cache to `~/.npm`, etc. These are **fatal** — the tool crashes.

3. **umask 0022** — The `umask 0000` fix from ADR-013 was added to `/etc/bash.bashrc`, which only applies to interactive bash shells. The actual container process (`sleep infinity`) and `docker exec` commands inherit the default `0022` umask, so new files are created `644`/`755` — writable by root but not by the host's openclaw user (uid 1000).

**What we discovered:** Issue 1 is harmless. Issue 2 is the real blocker, and the fix is trivial — redirect `HOME` to `/workspace`. Issue 3 is a latent bug that causes permission drift over time.

## Decision

### Environment variable redirects

Set `HOME=/workspace` and `XDG_CONFIG_HOME=/workspace/.config` in both:

1. **Dockerfile** (`ENV` directives) — baked into the image
2. **openclaw.json** (`agents.defaults.sandbox.docker.env`) — persists across image rebuilds

This redirects all "write to home directory" operations to the writable `/workspace` mount. Every tool that respects `$HOME` or `$XDG_CONFIG_HOME` now works — including npm, Astro, webpack, and any XDG-compliant tool.

### Suppress fchown warnings

Set `npm_config_unsafe_perm=true` in the Dockerfile. This tells npm not to attempt ownership changes, eliminating the `TAR_ENTRY_ERROR EPERM: operation not permitted, fchown` warnings entirely.

### What we did NOT change

- **umask:** The `bash.bashrc` approach from ADR-013 is still in place. It's imperfect (doesn't apply to non-interactive processes) but the one-time `chmod -R a+rw` plus this partial fix is sufficient. A proper fix would require an entrypoint script, but OpenClaw controls the container entrypoint.
- **Container user:** Still runs as root (uid 0). OpenClaw doesn't support `docker.user` config yet.
- **Capability drops:** Still drops ALL capabilities. We work within this constraint.

## Testing Results

All tested on the VPS with the new Docker image (2026-02-20):

| Tool | Command | Result |
|------|---------|--------|
| npm install | `npm install lodash` | Clean install, no warnings |
| npm install (large) | `npm install webpack webpack-cli` | Installs 119 packages, no fchown warnings |
| Astro build | `cd blog-src && npm run build` | 11 pages built in ~6s |
| webpack build | `npx webpack --mode production` | Compiled successfully |
| npm init | `npm init -y` | Creates package.json cleanly |

## Consequences

**What works now:**
- `npm install` — clean, no warnings
- Astro — full build pipeline (dev server untested, but build works)
- webpack — bundling works
- Any Node tool that writes config to `$HOME` or `$XDG_CONFIG_HOME`
- TypeScript compilation (was already working via global ts-node)

**Known limitations:**
- `npm run dev` (dev servers) may not work if they try to bind ports — sandbox networking is `bridge` but port forwarding isn't configured
- Angular CLI's `ng new` scaffolding should work but hasn't been tested yet
- React's create-react-app is deprecated; Vite-based setups (`npm create vite`) should work since Vite respects HOME
- The umask issue (new files created as 644/755) still exists for non-interactive processes. Periodic `chmod -R a+rw /workspace` may still be needed
- Node 18 is the sandbox version (from Debian bookworm repos). Some newer frameworks may want Node 20+

**What this unblocks:**
- Jimbo can scaffold, build, and deploy Node projects in the sandbox
- Blog can migrate from static HTML to Astro if desired
- Jimbo can help with Angular/React/Vite project scaffolding and builds
