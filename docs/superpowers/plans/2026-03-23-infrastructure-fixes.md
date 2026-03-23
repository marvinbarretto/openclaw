# Infrastructure Fixes — Session Plan

> **For a fresh context window.** This plan addresses all open issues from HISTORY.md as of session 13 (2026-03-23). Start by reading this file and the referenced sources.

**Goal:** Move Jimbo from "degraded" to "healthy" by fixing broken tools, stale data, and pipeline bugs.

**Reference files:**
- `docs/reviews/HISTORY.md` — full issue history and patterns
- `CLAUDE.md` — project architecture and conventions
- `CAPABILITIES.md` — token expiry dates, current model

---

## Priority 1: Investigate and fix (high impact, likely fixable)

### 1.1 vault_reader.py 401 Unauthorized
**Status:** BROKEN — 5 consecutive days, most-called tool, 0 successes
**Impact:** Jimbo can't read vault notes during heartbeat mode

**Investigation steps:**
1. Find vault_reader.py on VPS: `find /home/openclaw -name "vault_reader.py" 2>/dev/null`
2. Read the script — what API does it call? What auth does it use?
3. Check if it's calling jimbo-api (needs `X-API-Key` header) or something else
4. Try running it manually in the sandbox with env vars to reproduce the 401
5. Check the jimbo-api logs: `journalctl -u jimbo-api --since "1 hour ago" | grep 401`
6. Fix the auth issue and test

**Likely cause:** Missing or wrong API key, or calling a route that requires auth but not sending the header.

### 1.2 vault_roulette always returns no_candidates
**Status:** BROKEN — every call returns empty, 12+ failures
**Impact:** No random vault discovery during heartbeat

**Investigation steps:**
1. Find vault_roulette.py on VPS
2. Read the script — what's the "dormancy" threshold? (HISTORY.md suggests 30 days)
3. Check the vault data: `curl -sk -H "X-API-Key: $API_KEY" "$BASE/api/vault/notes?status=active&limit=5"` — do notes have `last_surfaced` dates?
4. The threshold may be too restrictive — if all notes were scored/surfaced recently, none qualify as "dormant"
5. Adjust threshold or logic

**Likely cause:** 30-day dormancy threshold too strict, or `last_surfaced` field populated on all notes.

### 1.3 Email insight fields null
**Status:** BUG — 3 consecutive sessions. Scores present (5-10) but category/action/reason/insight all null.
**Impact:** Briefing has no structured email metadata to work with

**Investigation steps:**
1. Find `email_decision.py` (or equivalent) in the workspace — this is the worker that produces insights
2. Read the code — what model does it call? What prompt produces the fields?
3. Check recent experiment-tracker entries for `email-decision`: `curl -sk -H "X-API-Key: $API_KEY" "$BASE/api/experiments?task_id=email-decision&limit=5"`
4. The scoring may run in a separate pass from the content extraction — one works, one doesn't
5. Check if it's a prompt issue (model returns scores but skips other fields) or a parsing issue

**Likely cause:** The email_decision worker produces a score but the content fields are either not requested in the prompt or not parsed from the response.

### 1.4 Briefing auto-delivery broken
**Status:** BROKEN — 2 consecutive mornings, Marvin had to prompt manually
**Impact:** Defeats the purpose of a scheduled briefing

**Investigation steps:**
1. Check the OpenClaw cron config: `cat /home/openclaw/.openclaw/openclaw.json | python3 -m json.tool | grep -A5 cron`
2. Check model swap cron in root crontab: `crontab -l | grep -i model`
3. Check if model swap is even happening — is Sonnet available at 07:00?
4. Check openclaw logs around 07:00: `journalctl -u openclaw --since "2026-03-23 06:45" --until "2026-03-23 07:15"`
5. Session 12 was a rate limit. Session 13 — what happened? No log entry?
6. Check if the briefing cron trigger is still configured and firing

**Likely cause:** Model swap cron disabled (CLAUDE.md says "DISABLED since 2026-03-08"), so the briefing model may not be available, or the cron trigger itself is misconfigured.

---

## Priority 2: Skill/prompt fixes (medium impact, quick fixes)

### 2.1 No surprise section (regression)
**Status:** Missing from 3 consecutive sessions (was present in sessions 8-10)
**Impact:** Loss of the most-valued briefing feature

**Fix:** Check `skills/daily-briefing/SKILL.md` — the surprise section instruction exists (Step 2, item 3). The model is skipping it. This may be a model quality issue (Kimi K2 vs Sonnet) or the skill text is too far down in the prompt. Consider:
- Moving surprise higher in the section order
- Making it more prominent ("REQUIRED: always include a surprise")
- Testing with different models

### 2.2 No inline links in briefing
**Status:** Gem data has URLs but briefing says "link in the email"
**Impact:** Reduces actionability

**Fix:** Update `skills/daily-briefing/SKILL.md` Step 2, email highlights section. Add instruction: "Include URLs from the gems data directly. Say 'Check it out: [URL]' not 'link in the email'."

### 2.3 Message format (wall of text)
**Status:** Briefing sent as one long Telegram message
**Impact:** Poor mobile UX

**Fix:** The skill already says "Each section = one message" (Step 2, Telegram rules). The model isn't following it. This is harder to fix — may need platform-level message splitting, or stronger prompt emphasis. Check if OpenClaw supports sending multiple messages in sequence.

### 2.4 Email cherry-picking poor
**Status:** High-confidence gems missed (0.95 OpenClaw podcast missed in session 13)
**Impact:** Best content doesn't reach Marvin

**Fix:** The briefing skill says "use the `email_insights` array (sorted by relevance_score) and the `gems` array." The model may not be reading all gems. Add instruction: "Read ALL gems. Present the top 3-4 by confidence score. Never skip a gem with confidence >= 0.9."

---

## Priority 3: Infrastructure debt (lower urgency)

### 3.1 Opus layer broken/stale
**Status:** `claude -p` erroring since Mar 16 (7+ days stale)
**Fix:** Either fix opus-briefing.sh or formally retire the Opus layer. The system works without it — Sonnet self-composes fine when the skill is loaded. Consider whether the complexity is worth maintaining.

### 3.2 Blog git push broken
**Status:** Push fails: "no repository initialized at host workspace"
**Fix:** Check git config in the sandbox. The blog-src directory may need `git init` or the remote URL may be stale.

### 3.3 False success on rate limit
**Status:** Activity log records "briefing delivered: success" when model hits rate limit
**Fix:** The briefing skill's Step 3 (log delivery) runs unconditionally. It should only run after actual content was composed. This is a skill prompt fix — add: "Only log success if you actually delivered briefing content."

### 3.4 Duplicate messages
**Status:** Same items sent twice at same timestamp (session 11)
**Fix:** Investigate whether this is a tool double-fire bug in OpenClaw, or a model issue. Check activity logs for the duplicate entries.

### 3.5 Accountability surprise detection
**Status:** Reports "surprise game not played" when it was
**Fix:** Check `accountability-check.py` — how does it detect surprise sections? It may be searching for a specific keyword that doesn't match the model's output format.

### 3.6 Stale files throughout repo
**Status:** HEARTBEAT.md, skills/, TODO.md, CAPABILITIES.md all have incorrect claims
**Fix:** Audit each file against current reality. Remove retired skills, update HEARTBEAT.md to reflect current tools, update CAPABILITIES.md.

---

## Priority 4: Design gaps (future sessions)

These are architecture issues, not bugs. They need design work (brainstorming sessions), not quick fixes:

- **No task creation from signals** — Jimbo surfaces actionable items but doesn't create tasks
- **No conversational task handoff** — No "I'll take this" / "you do it" / "done" protocol
- **Nudge rate-limiting** — No awareness of whether an item was actioned
- **Vault tasks stale** — Same 5 priority-9 items every session
- **Calendar write not used** — Jimbo narrates but doesn't propose+create
- **No briefing rating mechanism** — experiment_tracker has user_rating but no UI
- **Surprise game definition** — needs a proper doc defining what delight means

These are tracked in HISTORY.md and the vault task system design spec.

---

## Suggested session flow

1. **vault_reader 401** — diagnose and fix (highest impact, feeds into heartbeat)
2. **vault_roulette** — diagnose threshold issue
3. **Email insight null fields** — diagnose email_decision worker
4. **Briefing auto-delivery** — check cron config and model swap
5. **Skill prompt fixes** — batch the 4 skill changes (surprise, links, format, cherry-picking)
6. **False success logging** — quick skill fix
7. **Stale files audit** — if time allows

Start with investigation commands for #1-4 in parallel, then fix in order of what's simplest.

---

## How to start the fresh session

Paste this to Claude Code:

```
Read docs/superpowers/plans/2026-03-23-infrastructure-fixes.md — this is our session plan.
Then read docs/reviews/HISTORY.md for context.
Start with Priority 1.1 (vault_reader 401) — investigate on the VPS.
```
