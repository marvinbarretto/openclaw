# Proactive Actions — Design Document

## Date: 2026-03-11

## Problem

Jimbo's infrastructure is heavily read-and-report. The email pipeline (Flash triage → Haiku read → briefing) is shallow — emails are skimmed, links aren't followed, and nothing is acted on. Marvin still does all the work. The briefing tells him what exists; it doesn't do anything about it.

## Vision

Every email becomes a mini-project. A free local model reads every sentence, follows every link, and produces a rich structured dossier. Smarter models on the VPS consume these dossiers and make decisions — creating calendar holds, drafting emails, surfacing opportunities. Actions happen throughout the day, not just at briefing time.

## Architecture Overview

```
RALPH (local Mac, free)           JIMBO-API (VPS)              DECISION MAKER (VPS, Flash)
──────────────────────           ───────────────              ──────────────────────────
Fetch email via Gmail API
Read body → extract facts
Follow links → Playwright
Summarise pages → extract facts
Score extraction confidence
Detect duplicate URLs
Group by thread ID
POST deep report ──────────────→ Store in SQLite
                                  GET /api/emails/reports ←──── Read enriched reports
                                                                GET /api/context
                                                                Judge relevance
                                                                Create action requests
                                  Store action requests ←────── POST /api/actions
                                         │
                                         ├── AUTONOMOUS → action-executor.py → calendar-helper.py / etc
                                         └── APPROVAL  → Telegram message → Marvin taps → executor
```

## Ralph Evolution

Ralph evolves from "overnight coding assistant" to "local background agent that does thorough work with free models."

### Job-Type Architecture

```
ralph start                        # run all enabled job types
ralph start --job email            # just email deep reading
ralph start --job code             # just GitHub issues (future)
ralph start --job code --repo X    # single repo
```

Each job type defines: queue source, worker logic, model requirements, output format.

```toml
[jobs.email]
enabled = true
model = "qwen2.5:7b"

[jobs.code]
enabled = false
model = "qwen2.5-coder:14b"
```

### What Stays from Current Ralph

- Queue → Worker → Reporter pattern
- Ollama preflight + auto-start
- Lock file, config.toml, run logging, dry-run
- Stdlib Python (except Playwright)

### What Goes

- aider dependency (retained for code job, not loaded for email)
- Hard coupling to GitHub issues as only job type

### What's New

- Gmail API client (ported from workspace/gmail-helper.py)
- Playwright link follower
- Structured output schema per email
- jimbo-api client (POST deep reports)
- Local state tracking (processed gmail IDs)
- Extraction confidence scoring per link
- URL deduplication across emails
- Thread grouping via Gmail thread ID

## Email Deep Reader Pipeline

Per-email:

```
1. FETCH      Gmail API → raw email (respects sender/subject blacklist)
2. READ       Ollama reads full body → extracts structured facts
3. FOLLOW     Playwright visits every link → snapshots + content extraction
4. ANALYSE    Ollama reads each page's content → summarises, extracts entities
5. COMPILE    Assembles full email report (body analysis + all link analyses)
6. PUSH       POST to jimbo-api /api/emails/reports
```

### Deep Report Schema

```json
{
  "gmail_id": "abc123",
  "thread_id": "thread_xyz",
  "processed_at": "2026-03-11T09:15:00Z",
  "from": "newsletter@example.com",
  "subject": "March events in Watford",
  "body_analysis": {
    "summary": "...",
    "entities": ["Watford Palace Theatre", "March 22"],
    "events": [{ "what": "...", "when": "...", "where": "...", "cost": "..." }],
    "deadlines": [{ "what": "...", "by": "..." }],
    "key_asks": ["RSVP by March 15"],
    "content_type": "newsletter"
  },
  "links": [
    {
      "url": "https://example.com/event",
      "link_text": "Book now",
      "page_title": "Spring Comedy Night — Watford Palace Theatre",
      "page_summary": "Stand-up comedy night, 4 acts, March 22, £15",
      "entities": ["Watford Palace Theatre", "March 22", "£15"],
      "events": [{ "what": "...", "when": "...", "where": "...", "cost": "£15" }],
      "fetch_method": "playwright",
      "fetch_status": "ok",
      "extraction_confidence": "high",
      "seen_in_emails": 1
    }
  ],
  "thread_position": 1,
  "thread_total": 3,
  "model": "qwen2.5:7b",
  "processing_time_seconds": 45
}
```

### Extraction Confidence Levels

Per link, Ralph scores its own extraction quality (not relevance):

- **high** — full article content extracted, structured data found
- **medium** — partial content, some JS-rendered elements missing
- **low** — mostly empty page, 403/paywall, or heavy SPA that Playwright couldn't fully render

This tells Flash which link summaries to trust and which might need a second look.

### Deduplication

Ralph tracks URLs across emails. When the same URL appears in multiple emails:
- Process it once, reference the existing report in subsequent emails
- Track `seen_in_emails` count — a link appearing in 4 newsletters is a relevance signal
- Dedup key: normalised URL (strip tracking params like utm_*)

### Thread Grouping

Gmail API provides `threadId`. Ralph groups emails by thread so Flash sees:
- The full conversation context, not isolated messages
- `thread_position` and `thread_total` so Flash knows if it's reading the latest or catching up

### Operational Model

Ralph runs when the Mac is available. Not a daemon — a batch worker:
- Open laptop → Ralph chews through accumulated email
- Close laptop → Ralph stops gracefully, resumes next time
- State: local SQLite of processed `gmail_id`s (never re-processes)

### "Ralph Didn't Run" Alert

The VPS knows when the last deep report was posted. If 24h+ passes with no new reports and unprocessed email is accumulating, a Telegram nudge: "Ralph hasn't checked in since yesterday, N unprocessed emails waiting."

## Tiered Autonomy Model

### Tier Definitions (as code)

```python
AUTONOMOUS = [
    "calendar.create_hold",
    "calendar.create_reminder",
    "calendar.block_focus_time",
    "recommendation.save",
    "vault.create_task",
]

APPROVAL_REQUIRED = [
    "email.send_reply",
    "email.send_rsvp",
    "email.send_outreach",
    "calendar.decline_invite",
    "recommendation.flag_deal",
]

NEVER_AUTONOMOUS = [
    "email.contact_personal",
    "financial.purchase",
    "calendar.modify_existing",
    "calendar.invite_others",
]
```

These are literal data in the codebase, not logic buried in conditionals.

### Action Request Schema

```json
{
  "id": "act_a1b2c3",
  "source_email_id": "gmail_abc123",
  "action_type": "calendar.create_hold",
  "tier": "autonomous",
  "summary": "Comedy night at Watford Palace, March 22, £15",
  "payload": {
    "summary": "Comedy Night — Watford Palace Theatre",
    "start": "2026-03-22T19:30:00Z",
    "end": "2026-03-22T22:00:00Z",
    "description": "4 acts, £15. From TimeOut newsletter."
  },
  "reasoning": "Time-sensitive local event matching interests: comedy, Watford area",
  "status": "pending"
}
```

### Action Flow

```
AUTONOMOUS:
  Flash creates action request → jimbo-api stores it →
  action-executor.py runs immediately →
  Result logged → Included in next briefing

APPROVAL_REQUIRED:
  Flash creates action request → jimbo-api stores it →
  Telegram: "Draft RSVP to Comedy Night. Approve / Edit / Skip" →
  Marvin taps → action-executor.py runs →
  Result logged

NEVER_AUTONOMOUS:
  Surfaced in briefing only → No action request created
```

### Feedback Loop

Every approve/edit/skip decision is stored. Over time this builds a calibration signal:
- Flash proposed 10 calendar holds this week, 8 skipped → too aggressive
- All RSVP drafts approved → tone/format is right
- Surfaced in dashboard, eventually fed back into Flash's decision prompt

## New jimbo-api Endpoints

```
POST   /api/emails/reports            # Ralph pushes deep reports
GET    /api/emails/reports            # Flash reads for decision-making
GET    /api/emails/reports/unprocessed # Reports not yet judged by Flash

POST   /api/actions                   # Flash creates action requests
GET    /api/actions?status=pending    # Executor reads pending
PATCH  /api/actions/:id               # Update status
POST   /api/actions/:id/approve       # Telegram approval callback
GET    /api/actions/stats             # Feedback loop data
```

## Briefing Pipeline Evolution

### Current (ADR-042)

```
06:15  briefing-prep.py runs workers sequentially
07:00  Jimbo delivers from briefing-input.json
```

### New

```
Continuous:  Ralph processes email → POST deep reports to jimbo-api
Periodic:    decision-maker.py (cron) → Flash judges → actions created/executed
Briefing:    Jimbo reads from jimbo-api — "here's what happened since last time"
```

### Retired Components

- `email_triage.py` worker — replaced by decision-maker.py reading deep reports
- `newsletter_reader.py` worker — replaced by Ralph's deep reading
- Email fetch step in `briefing-prep.py` — Ralph handles fetching

### Retained Components

- `briefing-prep.py` (simplified) — assembles briefing context from jimbo-api
- `calendar-helper.py` — used by action-executor.py
- Opus analysis layer (optional)
- Telegram alerting

## Security Changes

- **Gmail scope upgrade:** `gmail.readonly` → `gmail.readonly` + `gmail.send` (Phase 3 only)
- **ADR-002 amendment needed:** email send capability with approval gate
- **Ralph gets jimbo-api key:** for POSTing reports (no SSH access to VPS)
- **Reader/Actor split maintained:** Ralph reads, Flash decides, executor acts — untrusted email content never drives actions directly
- **Tiered autonomy as security boundary:** `NEVER_AUTONOMOUS` list is a hard block, not a suggestion

## Implementation Phases

### Phase 1 — Ralph Email Deep Reader

- Refactor Ralph into job-type architecture
- Port Gmail API fetch logic (with blacklist)
- Playwright link follower with confidence scoring
- Ollama fact extraction (no judgment, no relevance scoring)
- URL deduplication + thread grouping
- Local state tracking (processed IDs)
- POST deep reports to jimbo-api
- jimbo-api: `POST/GET /api/emails/reports` endpoints
- "Ralph didn't run" alert on VPS

**Deliverable:** `ralph start --job email` processes inbox, rich reports appear in jimbo-api.

### Phase 2 — Decision Maker + Action Layer

- `decision-maker.py` on VPS — Flash reads deep reports + context → action requests
- jimbo-api: `POST/GET/PATCH /api/actions` endpoints
- `action-executor.py` on VPS — executes autonomous actions via helpers
- Tiered autonomy config as literal data
- Telegram approval flow for medium-tier actions
- Feedback loop storage (approve/skip signals)

**Deliverable:** Calendar holds appear automatically. Telegram asks approval for email drafts.

### Phase 3 — Gmail Send

- Re-run `google-auth.py` with `gmail.send` scope
- Add `send` command to `gmail-helper.py`
- Wire email actions through executor
- ADR-002 amendment

**Deliverable:** Approve a Telegram message, email sends on your behalf.

### Phase 4 — Briefing Evolution

- Simplify `briefing-prep.py` to read from jimbo-api
- Briefing becomes activity summary, not processing trigger
- Retire `email_triage.py` and `newsletter_reader.py`
- Reassess briefing timing

### Phase 5 — Dashboard + Observability

- Deep reports viewer on site dashboard
- Action log (proposed / approved / executed / skipped)
- Ralph processing stats
- Feedback loop visualisation (calibration over time)

## Open Questions

- What Ollama model works best for fact extraction from email? Test qwen2.5:7b vs others.
- Should Ralph also process calendar invitations (not just email newsletters)?
- How often should decision-maker.py run? Every 30 min? Every hour? On-demand when Ralph posts?
- Dashboard priority: is Phase 5 important enough to interleave with earlier phases?
