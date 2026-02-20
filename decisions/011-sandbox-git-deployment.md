# ADR-011: Sandbox Git & Blog Deployment Fix

## Status

Accepted (2026-02-18)

## Context

Jimbo's sandbox can create and edit files in `/workspace` (his `jimbo-workspace` repo), but could not commit or push to GitHub. This meant every blog post or workspace update required Marvin to manually copy files out of the sandbox, commit, and push — defeating the purpose of an autonomous workspace (ADR-007).

Three issues blocked git operations inside the sandbox:

1. **File ownership mismatch:** The Docker container runs as `root` (uid 0), but workspace files are bind-mounted and owned by `openclaw` (uid 1000). Root could read but not always write to these files, causing `EPERM` on `git add`, `git commit`, and file operations.

2. **Git "dubious ownership" error:** Git refuses to operate on a repo owned by a different user. The `.gitconfig` with `safe.directory = /workspace` existed at `/workspace/.gitconfig`, but the container's root user looks for config at `/root/.gitconfig` — which is on the read-only root filesystem.

3. **npm/Node permission issues:** Same ownership mismatch caused `fchown` failures during `npm install`, preventing any Node-based build tooling (Astro, etc.) from working in the sandbox. This led Jimbo to correctly fall back to static HTML for the blog.

## Decision

### Immediate fixes (applied 2026-02-18)

- **Permissions:** `chmod -R a+rw` on the entire workspace directory and `.git` subtree, making all files world-readable/writable so both root (container) and openclaw (host) can operate.
- **Git config:** Set `GIT_CONFIG_GLOBAL=/workspace/.gitconfig` as an environment variable, so git inside the container finds the safe directory and user settings regardless of which user runs it.
- **OpenClaw config:** Added `GIT_CONFIG_GLOBAL` to `agents.defaults.sandbox.docker.env` in `openclaw.json` so it persists across container recreations.
- **Dockerfile:** Added `ENV GIT_CONFIG_GLOBAL=/workspace/.gitconfig` to the custom sandbox image for belt-and-suspenders.

### Blog approach

Jimbo builds a static HTML/JS blog (no framework, no build step). This avoids all npm/Node permission issues and deploys directly to GitHub Pages via the `gh-pages` branch. The `jimbo-vps` fine-grained PAT (ADR-007) is embedded in the git remote URL, giving Jimbo full push access to his own repo.

## Consequences

**What works now:**
- Jimbo can `git add`, `git commit`, `git push` from inside the sandbox
- Blog updates deploy to GitHub Pages without Marvin's involvement
- Static HTML blog at `https://marvinbarretto-labs.github.io/jimbo-workspace/blog/`

**Known limitations:**
- Permissions may drift: new directories created by root inside the container will have restrictive permissions. A periodic `chmod` or umask fix may be needed.
- The PAT is hardcoded in `.git/config` (the remote URL). Functional but not ideal — could be moved to a credential helper reading `JIMBO_GH_TOKEN` env var.
- ~~Node-based build tools (Astro, webpack, etc.) still won't work reliably due to the uid mismatch. Static files only for now.~~ **Fixed in ADR-016** — setting `HOME=/workspace` and `XDG_CONFIG_HOME=/workspace/.config` resolves the EROFS errors. The fchown warnings were always harmless.
- The `jimbo-vps` token expires ~May 2026 and will need regeneration.

**Future improvements:**
- ~~Set a default umask in the Dockerfile entrypoint so new files are created world-writable~~ Partially done (bash.bashrc), full fix needs OpenClaw entrypoint control
- Move PAT from git remote URL to credential helper
- Consider running the container as uid 1000 if OpenClaw adds a `docker.user` config option
