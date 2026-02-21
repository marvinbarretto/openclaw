# ADR-022: Gmail API Migration — Replacing the Maildir Pipeline

## Status

Proposed

## Context

The current email pipeline (mbsync → Maildir → scan 159k files → classify → push digest) takes 2.5 hours, depends on the laptop being awake, and the network check was broken from day one. We need a fundamentally better approach.

We already have Google OAuth set up for Calendar (ADR-018). Gmail API uses the same OAuth infrastructure.

## Options considered

| Option | Approach | Laptop needed? | Speed | Risk |
|---|---|---|---|---|
| A | Gmail API on laptop, classify via Ollama | Yes | ~60 min | Low (offline) |
| B | Gmail API on VPS, classify via cloud LLM | No | ~5 min | Email transits cloud API |
| C | Forward all email to Jimbo's Gmail | No | Near-real-time | Full inbox copy in second account |
| **D** | **Gmail API read-only on Marvin's account** | **No** | **~5 min** | **Read-only token on VPS** |

## Decision

**Option D: Gmail API read-only on Marvin's account.**

### How it works

1. VPS queries Gmail API: "messages from last 24 hours"
2. Gmail returns message data
3. VPS classifies each email in memory (via Haiku)
4. VPS writes digest JSON (summaries, 200-char snippets)
5. Raw email content is discarded — nothing persists

Jimbo looks through a window at the inbox. He doesn't make a copy.

### Why Option D

1. **No persistence** — emails are read, classified, discarded. If VPS is compromised, the emails aren't there. Only the refresh token (revocable in 30 seconds from Google security settings).
2. **Eliminates laptop dependency** — VPS runs independently, any time.
3. **Fast** — Gmail API query returns in seconds. Haiku classifies at ~1-2s per email. Total: ~5 minutes for 150 emails vs 2.5 hours today.
4. **Incremental risk** — VPS already has Calendar read, Telegram, GitHub access. Gmail read-only is the same risk class.
5. **Simplest to implement** — add one OAuth scope, write one fetch script.

### What the refresh token grants (and doesn't)

| Can do | Cannot do |
|---|---|
| Read email messages and metadata | Send email |
| Search/query the inbox | Delete email |
| List labels | Modify email (labels, read status, archive) |
| | Create drafts |
| | Access Drive, Contacts, or anything outside Gmail |

### If VPS is compromised

**Attacker gets:**
- Live read access to Gmail (until token is revoked)
- Current digest JSON (200-char snippets, no full bodies)

**Attacker does NOT get:**
- A stored copy of the inbox (nothing persists)
- Ability to send, delete, or modify email
- Historical email content beyond the current digest

**Revocation:** Google security settings → revoke app access → immediate cutoff. Same as revoking Calendar access today.

### Hard constraints

1. **Never send email.** No send scope. No send tools. No exceptions.
2. **Never delete or modify email.** Read-only scope only.
3. **Never persist raw email content.** Read, classify, discard. Only digest JSON stays.
4. **Body truncation and HTML stripping** still apply.

### What this supersedes

- ADR-002 Phase 1 (Maildir/mbsync approach) → replaced by Gmail API
- Laptop dependency for email → eliminated
- sift-cron.sh as primary pipeline → replaced by VPS-based pipeline
- Offline-only classification → relaxed to allow cloud LLM on VPS

### What this preserves

- ADR-002 core principle: no send/delete/modify capability
- Structured JSON classification output (same schema)
- Classification prompt and logic (reusable with any LLM backend)
- Local Ollama on laptop as manual fallback (sift-cron.sh still works)

## Implementation sketch

### 1. Add Gmail read-only scope to OAuth

Re-run calendar-auth.py (or new gmail-auth.py) with additional scope:
```
https://www.googleapis.com/auth/gmail.readonly
```

Generates a new refresh token covering both Calendar and Gmail.

### 2. New script: `gmail-fetch.py`

Runs on VPS. Uses Gmail API to:
- Query messages from last N hours
- Extract: sender, subject, date, body (plain text, truncated)
- Output: unclassified items in current digest schema

### 3. Classification via cloud LLM

Use same classification prompt, but call Haiku API instead of Ollama. Same JSON schema output. Same queue/skip logic.

### 4. VPS cron job

```
05:00  gmail-fetch.py → classify via Haiku → email-digest.json ready
07:00  Jimbo morning briefing (reads digest from local filesystem)
```

No laptop. No mbsync. No 159k file scan. ~5 minutes total.

### 5. Laptop pipeline becomes fallback

sift-cron.sh still works for manual runs or fully-offline classification. Backup, not primary.

## Future considerations (not in scope)

- **Draft replies:** Jimbo could draft suggested responses on his own Gmail account (marvinbarretto.labs@gmail.com), addressed to Marvin, not to original senders. Marvin reviews and forwards from his real account. Requires careful scoping to prevent accidental sends. Deferred until read-only pipeline is stable.
- **Near-real-time processing:** With Gmail API, could classify emails as they arrive instead of daily batch. Deferred until daily batch proves reliable.
- **Enriched digest:** Extract dates, action items, amounts, thread grouping during classification. Deferred until basic pipeline works.

## Consequences

**What becomes easier:**
- Pipeline: 5 minutes instead of 2.5 hours
- No laptop dependency — VPS handles everything
- Fresh digest every morning, reliably
- Can run multiple times per day
- Path to near-real-time processing

**What becomes harder:**
- One more OAuth scope to manage
- Email content transits cloud LLM API during classification
- Two classification paths to maintain (cloud primary + local fallback)

**Security model change:**
- ADR-002's "no Gmail credentials on VPS" relaxed to "read-only Gmail credentials on VPS"
- Same risk class as existing Calendar credentials
- Defence-in-depth: read-only scope + no send tools + no persistence + instant revocability

**Cost:**
- Gmail API: free (15,000 queries/day, we use ~200)
- Haiku classification: ~$0.01-0.05 per run
- Net saving: 2.5 hours of laptop GPU inference eliminated
