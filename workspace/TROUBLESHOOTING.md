# TROUBLESHOOTING.md

**Read this before telling Marvin something doesn't work.**

If you hit an error or can't find something, check here first. Most problems have been solved before.

---

## "Directory doesn't exist" or "file not found"

**Vault notes:** The vault is at `/workspace/vault/notes/`. If `ls` fails, try:
```bash
ls /workspace/vault/notes/ | head -5
```
If that works, the directory exists — your previous command was wrong. If it genuinely doesn't exist, tell Marvin the vault hasn't been synced yet (he runs `workspace-push.sh` from his laptop).

**General rule:** Before reporting a missing file/directory, try `ls` on the exact path. Don't guess — verify.

---

## Searching the vault

The vault has ~1,600 markdown files. Never try to read them all at once.

**Search by content:**
```bash
grep -rli 'search_term' /workspace/vault/notes/
```

**Search by frontmatter field:**
```bash
grep -rli 'type: recipe' /workspace/vault/notes/
grep -rli 'type: task' /workspace/vault/notes/
```

**Search by tag or project (case-insensitive):**
```bash
grep -rli 'localshout\|LocalShout' /workspace/vault/notes/
```

**Read a specific note:**
```bash
cat /workspace/vault/notes/some-note--note_abc1234.md
```

**If grep returns nothing:** try broader terms, check spelling, try lowercase. The vault uses lowercase tags.

---

## Google API errors

**"Token refresh failed (400/401)":**
The refresh token is expired or missing a scope. Tell Marvin to re-run `google-auth.py` on his laptop. You can't fix this yourself.

**"gmail.readonly scope" or "tasks.readonly scope" error:**
Same — the token needs wider scopes. Marvin must re-auth.

---

## Sandbox environment

**You are inside a Docker container.** Your paths:
- `/workspace/` — your home, everything is here
- `/workspace/vault/notes/` — Marvin's classified notes
- `/workspace/email-digest.json` — today's email digest
- `/workspace/context/` — Marvin's context files

**Never use host paths** like `/home/openclaw/.openclaw/workspace/` — those don't work inside the sandbox.

---

## Script failures

**"Permission denied" when writing files:**
Workspace files are pushed from Marvin's laptop via rsync, which preserves his UID (501). The sandbox runs as root but the workspace directory may not be writable. This is a known issue — tell Marvin to run this from his laptop:
```bash
ssh jimbo "chmod -R a+rw /home/openclaw/.openclaw/workspace/"
```
You cannot fix this yourself from inside the sandbox.

**"Permission denied" when running scripts:**
```bash
chmod +x /workspace/script-name.py
```

**"No module named X":**
All scripts are stdlib only. If you see an import error, the script is broken — tell Marvin.

**Git "dubious ownership":**
```bash
chmod -R a+rw /workspace/.git/
```

---

## Before telling Marvin something doesn't work

1. **Try the exact command** — don't paraphrase errors, run the actual command
2. **Check this file** — the answer is probably here
3. **Check SOUL.md** — it has guidance on how to use your tools
4. **Try a simpler version** — if `grep -rli` fails, try `ls` first
5. **Only then** tell Marvin, and include the actual error message
