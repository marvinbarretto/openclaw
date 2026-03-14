# ADR-044: Email Ingestion and Decision Pipeline

## Status

Accepted

## Context

Marvin's email contains high-value signals — local events, deals, newsletter gems, personal replies — buried in noise. The briefing pipeline (ADR-042) needs structured, scored email data to produce useful briefings, but the existing email flow had two problems:

1. **Extraction was shallow.** Gmail API gives subject, snippet, labels. The briefing triage worker (Flash) was classifying emails by metadata alone — it couldn't read linked pages, see event flyers, or extract structured data from newsletter bodies.

2. **No persistent scoring.** Each briefing run re-triaged emails from scratch. There was no record of which emails had been evaluated, what they contained, or how relevant they were. The email decision worker in the briefing pipeline was ephemeral.

Separately, Marvin has a Mac with Ollama (free local LLM inference) and Playwright (headless browser), but these can't run on the VPS (1 vCPU, 2GB RAM). The VPS has API access to Gemini Flash and internet connectivity. The right architecture uses each machine for what it's good at.

## Decision

Split email processing into three stages across two machines, with jimbo-api as the persistent store between them.

### Architecture

```
Mac (Ralph, launchd hourly)          VPS (cron every 30 min)
┌─────────────────────────┐          ┌──────────────────────────┐
│ Gmail API (read-only)   │          │ email_decision.py        │
│ → Ollama extraction     │          │ → GET undecided reports   │
│ → Playwright screenshots│          │ → Fetch context from API  │
│ → R2 upload (presigned) │          │ → Gemini Flash scoring    │
│ → POST report to API    │          │ → PATCH decision back     │
└─────────┬───────────────┘          └──────────┬───────────────┘
          │                                      │
          │         ┌──────────────┐             │
          └────────►│  jimbo-api   │◄────────────┘
                    │  (VPS:3100)  │
                    │              │──► Briefing pipeline reads
                    │  email_reports│     decided reports
                    │  table       │──► Dashboard shows status
                    └──────────────┘     /app/jimbo/emails
```

### Stage 1: Deep extraction (Ralph, local Mac)

**What:** Read Gmail, extract structured data from email bodies and linked pages.

**Why local:** Ollama runs free with no API costs. Playwright needs a real browser. Both need more RAM than the VPS has.

**How:**
- `lib/gmail.py` — OAuth read-only access, subject blacklist filtering
- `lib/ollama_extract.py` — Ollama (mistral/llama) extracts: summary, content_type, entities, events, deadlines, key_asks
- `lib/links.py` — Playwright follows links, extracts page content, takes screenshots of low-confidence pages
- Screenshots uploaded to R2 via presigned URLs from jimbo-api
- Structured report POSTed to `POST /api/emails/reports`

**Output per email:**
```json
{
  "gmail_id": "...",
  "subject": "...",
  "from_email": "...",
  "body_analysis": {
    "summary": "...",
    "content_type": "newsletter|event|personal|...",
    "entities": ["Watford Palace Theatre"],
    "events": [{"what": "Comedy Night", "when": "Friday 7:30pm"}],
    "deadlines": [],
    "key_asks": []
  },
  "links": [
    {
      "url": "...",
      "page_title": "...",
      "page_summary": "...",
      "entities": [],
      "events": [],
      "extraction_confidence": "high|medium|low",
      "screenshot_url": "https://r2.example.com/..."
    }
  ]
}
```

### Stage 2: Relevance scoring (Decision worker, VPS)

**What:** Score each undecided report against Marvin's current priorities, interests, and goals.

**Why VPS:** Needs jimbo-api access for context. Uses Gemini Flash (cheap, fast). Runs on cron — no human needed.

**How:**
- `workers/email_decision.py` — BaseWorker subclass
- Fetches undecided reports from `GET /api/emails/reports/undecided`
- Loads context via `context_slugs: [priorities, interests, goals]` from jimbo-api
- Multimodal: for low-confidence links with screenshots, sends images to Gemini Flash for visual analysis
- PATCHes decision back to `PATCH /api/emails/reports/:gmail_id/decide`

**Decision schema:**
```json
{
  "relevance_score": 8,
  "category": "event",
  "suggested_action": "surface-in-briefing",
  "reason": "Matches local events interest",
  "insight": "Comedy night at Watford Palace, Friday 7:30pm...",
  "connections": ["local events", "Watford"],
  "time_sensitive": true,
  "deadline": "2026-03-20"
}
```

### Stage 3: Consumption (briefing + dashboard)

- `briefing-prep.py` can query decided reports with `min_relevance` filter for the morning briefing
- Dashboard at `/app/jimbo/emails` shows pipeline health, scores, categories, expandable detail rows
- Future: email feedback loop (rate decisions, improve scoring)

### jimbo-api schema

`email_reports` table stores both the raw report (Stage 1) and the decision (Stage 2):

- Report fields: `gmail_id`, `subject`, `from_email`, `body_analysis` (JSON), `links` (JSON), `created_at`
- Decision fields: `relevance_score`, `category`, `suggested_action`, `reason`, `insight`, `connections` (JSON), `time_sensitive`, `deadline`, `decided_at`

Endpoints:
- `POST /api/emails/reports` — Ralph pushes a report
- `GET /api/emails/reports/undecided` — Decision worker fetches work
- `PATCH /api/emails/reports/:gmail_id/decide` — Decision worker writes back
- `GET /api/emails/reports` — Dashboard/briefing reads (supports `?min_relevance=N`)
- `GET /api/emails/stats` — Dashboard summary counts

### Model choices

| Stage | Model | Cost | Rationale |
|-------|-------|------|-----------|
| Extraction | Ollama (local) | Free | Slow but free. Extraction is mechanical, not creative. |
| Screenshots | Playwright | Free | Browser rendering, no LLM needed |
| Scoring | Gemini 2.5 Flash | ~$0.01/run | Cheap, fast, follows JSON schema well |
| Scoring fallback | OpenRouter Kimi K2 (free) | Free | Backup if Flash quota hit |

### Scheduling

- Ralph: launchd hourly on Mac (runs when Mac is awake)
- Decision worker: VPS cron every 30 minutes
- Reports accumulate if Mac is off; decision worker catches up when reports arrive

## Consequences

**What becomes easier:**
- Briefing has pre-scored, structured email data — no more re-triaging from scratch each morning
- Dashboard gives real-time visibility into what Ralph is reading and how it's being scored
- Each stage is independently testable and deployable
- Adding new data sources (RSS, calendar) follows the same pattern: extract → store → score

**What becomes harder:**
- Three repos involved (ralph, jimbo-api, openclaw) — coordinated changes needed for schema updates
- Ralph must be running for emails to flow — if Mac is off for days, backlog builds
- Presigned URL flow for screenshots adds complexity (ralph → jimbo-api → R2 → decision worker)

**Trade-offs:**
- Hourly extraction is slower than real-time, but emails aren't time-critical to the minute
- Local Ollama extraction quality is lower than Gemini/Claude, but it's free and the decision worker re-evaluates anyway
- Storing full reports in SQLite means the database grows (~1KB per email) — acceptable for personal scale

**Dependencies:**
- ADR-033 (Context API) — decision worker fetches context from jimbo-api
- ADR-042 (Briefing Pipeline) — briefing consumes decided reports
- R2 bucket for screenshot storage
- Caddy reverse proxy for jimbo-api HTTPS access from Docker container
