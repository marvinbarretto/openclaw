# ADR-013: Sandbox Path & Permission Guardrails

## Status

Accepted (2026-02-19)

## Context

Jimbo was spiralling when hitting permission errors or path confusion inside the Docker sandbox. A typical failure pattern:

1. Jimbo tries to write a file, gets EPERM (root creating files in openclaw-owned workspace)
2. Tries a different path guess (`/home/openclaw/.openclaw/workspace/` instead of `/workspace`)
3. Tries `chown` (fails — sandbox restriction)
4. Deletes the file and recreates it
5. Accidentally deletes a directory of blog posts
6. Tries to recover, gets more permission errors, spirals further

Root causes:
- **Permission drift:** ADR-011 applied `chmod -R a+rw` once, but new files/dirs created by root (uid 0) got restrictive permissions, breaking subsequent operations.
- **No environment documentation:** Jimbo had no persistent rules about paths or permission recovery. Skills used relative paths (`/blog/index.html`) that he misinterpreted.
- **No recovery procedure:** When errors occurred, Jimbo had no "first aid" steps and resorted to increasingly destructive workarounds.

## Decision

### 1. Umask fix in Dockerfile

Added `umask 0000` to `/etc/bash.bashrc` and `ENV UMASK=0000` in the custom sandbox image. New files and directories created by root are now world-readable/writable by default, preventing permission drift.

### 2. Explicit paths in skills

Updated `blog-publisher` skill to use absolute `/workspace/` paths instead of relative paths. Added a "if you hit permission errors" section with the correct fix (chmod, never rm).

### 3. TOOLS.md sandbox environment rules

Added a "Sandbox Environment" section to Jimbo's TOOLS.md (read every session) with:
- Hard path rules: `/workspace` is the only path, period
- Permission fix procedure: `chmod`, never `chown`, never delete-and-recreate
- Recovery rules: check git history, don't spiral, tell Marvin if stuck after one retry

## Consequences

**Easier:**
- Permission errors should rarely occur (umask fix prevents drift)
- When they do occur, Jimbo has a documented fix procedure
- Jimbo won't guess paths — `/workspace` is explicitly stated as the only option
- The "stop and think" rule should prevent destructive spiralling

**Harder:**
- `umask 0000` means all files in the workspace are world-writable — acceptable since the sandbox is single-user and isolated
- Rules in TOOLS.md depend on the LLM actually following them — may need reinforcement in SOUL.md if the model ignores TOOLS.md
- Requires Docker image rebuild when changing the umask approach
