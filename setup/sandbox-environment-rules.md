# Sandbox Environment Rules

These rules should be added to TOOLS.md on the VPS workspace so Jimbo reads them every session.

Push with:
```bash
ssh jimbo "cat >> /home/openclaw/.openclaw/workspace/TOOLS.md" < setup/sandbox-environment-rules-content.md
```

Or tell Jimbo directly: "Add these rules to your TOOLS.md"

---

## Content to add to TOOLS.md

```markdown
## Sandbox Environment

### Paths — MEMORISE THESE
- Your working directory is `/workspace`. ALWAYS use this path.
- `/workspace` is the ONLY writable location. The root filesystem is read-only.
- Blog files: `/workspace/blog/` and `/workspace/blog/posts/`
- Never use `/home/openclaw/.openclaw/workspace/` — that's the host path, not yours.
- Never guess paths. If a file isn't under `/workspace/`, it doesn't exist for you.

### Permissions
- The container runs as root (uid 0) but workspace files are owned by openclaw (uid 1000).
- If you get "permission denied" or EPERM on a file: `chmod a+rw <file>`
- If you get it on a directory: `chmod -R a+rw <directory>/`
- NEVER use `chown` — it fails in the sandbox.
- NEVER delete and recreate files to work around permissions. Just chmod first, then write.
- If git fails with "dubious ownership": `chmod -R a+rw /workspace/.git/`

### When things go wrong — STOP AND THINK
- If a command fails, diagnose the error BEFORE trying alternatives.
- Do NOT try 3-4 different path guesses. The path is /workspace. Period.
- Do NOT rm -rf directories containing content you created. You'll lose work.
- If you accidentally delete something, recover from git: `git log --oneline` then `git checkout HEAD -- <path>`
- If you're stuck after one retry, tell Marvin what the error is instead of spiralling.
```
