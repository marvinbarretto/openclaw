# ADR-002: Safe Gmail Triage System

## Status

Accepted

## Context

25,000 emails in Gmail. Not coping. Want an agent to classify, summarize, and draft replies — but email content is adversarial (spam, phishing, prompt injection via email body). Need a system that's useful without giving the agent the ability to send email, delete email, or be manipulated by email content.

## Decision

### Phase 1: Offline mirror, read-only, no credentials on VPS

```
┌──────────────┐     one-time sync      ┌──────────────────┐
│   Gmail      │ ──────────────────────► │  Local machine   │
│   (IMAP)     │    (your laptop)        │  Maildir export  │
└──────────────┘                         └────────┬─────────┘
                                                  │ scp/rsync
                                         ┌────────▼─────────┐
                                         │     VPS          │
                                         │  /data/email/    │
                                         │  (read-only fs)  │
                                         └────────┬─────────┘
                                                  │
                                         ┌────────▼─────────┐
                                         │  Reader (LOCAL)   │
                                         │  Ollama, no net   │
                                         │  - Classify       │
                                         │  - Summarize      │
                                         │  - Draft replies  │
                                         └────────┬─────────┘
                                                  │
                                         ┌────────▼─────────┐
                                         │  Output files    │
                                         │  /data/output/   │
                                         │  - triage.json   │
                                         │  - summaries.md  │
                                         │  - drafts/       │
                                         └──────────────────┘
```

**How it works:**
1. On your laptop, sync Gmail to Maildir using `mbsync` (isync) or Gmail API export
2. `rsync` the Maildir to VPS (one-time or periodic batch)
3. Mount email directory as **read-only** inside the agent container
4. Agent classifies every email: `action_required | reference | bulk | spam`
5. Agent writes summaries and draft replies to output directory
6. You review output on your laptop/phone — approve, edit, or discard
7. **No Gmail credentials on the VPS.** Agent cannot send, delete, or modify email.

**Why offline mirror, not Gmail API on VPS:**
- Zero risk of auto-send/auto-delete even if agent is compromised
- No OAuth tokens to steal
- Prompt injection in email body can't trigger Gmail actions because there are no Gmail actions available
- You control what email batches the agent sees

### Processing order: recent first

Do NOT process 25k emails in one go:

1. **First batch:** Last 90 days (~recent actionable mail)
2. **Second batch:** Last 12 months (catch anything missed)
3. **Third batch:** Older archive (bulk, low priority)

This gets you value fast — the 90-day batch likely contains everything you're actually stressed about.

### Phase 2: Batch-approved actions (later, after trust builds)

- Agent outputs proposed label/archive actions as a JSON batch file
- You review the batch on your laptop
- A separate script (on your laptop, not VPS) applies approved actions via Gmail API
- Still no Gmail write credentials on VPS

### Log hygiene

**Critical — if VPS is compromised, logs must not expose your inbox:**

- [ ] **Never log full email bodies** — log only: message ID, sender, subject line hash, classification result
- [ ] **Store drafts in structured format** — separate file per draft, not embedded in logs
- [ ] **Log rotation** — auto-delete processing logs after 30 days
- [ ] **No email content in error messages** — sanitize before logging

Log format:
```json
{"msg_id": "abc123", "from_hash": "sha256:...", "classification": "action_required", "confidence": 0.92, "timestamp": "2026-02-16T10:30:00Z"}
```

### Data exfiltration risk

Even with an offline mirror, if the agent has outbound network AND access to an LLM API, it could theoretically leak email content through LLM API calls (the email body becomes part of the prompt sent to the provider).

**Mitigation: Run email Reader model fully offline.**

- Email classification container runs local Ollama model (Qwen 2.5 7B)
- **No outbound internet** for the email-processing container — not even to LLM APIs
- Model weights are pre-loaded, inference is local
- This is the strongest guarantee: email content never leaves the machine

```
Email container network policy:
  outbound: NONE
  inbound: read-only mount of /data/email/
  model: local Ollama (pre-loaded, no download needed)
  output: write to /data/output/ only
```

If running on VPS (not laptop), this means the Ollama model must be installed on the VPS too — but only for the email Reader. The VPS can handle a 7B model if we give it swap (it'll be slow, but email triage is batch/async anyway). Alternatively, run email triage exclusively on the laptop.

### Prompt injection mitigation for email

Email is the single most dangerous input source — attackers literally craft email to manipulate recipients (humans or AI).

Mitigations:
1. **Fully offline Reader** — no network, no tools, no actions available
2. **Strip HTML** — process plain text only, strip all HTML/links before agent sees it
3. **Truncate** — cap email body at ~2000 tokens
4. **Structured output only** — Reader outputs JSON classification, not free text
5. **No email-to-action pipeline** — even if Reader is fully compromised, there are no tools to abuse and no network to exfiltrate through

### Email sync tooling

**Option A: `mbsync` (isync)** — battle-tested IMAP sync to Maildir
```bash
# On your laptop
brew install isync
# Configure ~/.mbsyncrc with Gmail IMAP
mbsync -a
# Then rsync to VPS
rsync -avz ~/Maildir/ vps:/data/email/
```

**Option B: Gmail API export** — more control, can filter by date/label
```python
# Export specific labels/date ranges
# Outputs .eml files or structured JSON
# Runs on your laptop, outputs to local dir
```

Recommendation: Start with Option A (`mbsync`), it's simpler. Use date filtering to grab the 90-day batch first.

## Consequences

**Easier:**
- Safe to experiment — agent literally cannot send email
- No OAuth tokens at risk
- Email content never leaves the machine (offline Reader)
- If VPS compromised, logs don't expose inbox content
- Recent-first processing gets value fast

**Harder:**
- Not real-time — you batch-sync periodically
- Extra step to apply triage decisions back to Gmail
- Offline Reader on VPS is slow (CPU-only 7B model) — consider running on laptop instead
- Need to set up `mbsync` on your laptop (one-time)

**Acceptable tradeoffs:**
- Real-time isn't needed — batch triage every few hours is fine
- The extra review step IS the security model — that's the point
- Slow inference is fine for batch email triage — it's not interactive
