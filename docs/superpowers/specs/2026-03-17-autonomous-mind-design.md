# Jimbo's Autonomous Mind — Design Spec

**Date:** 2026-03-17
**Context:** Session 9. After fixing all infrastructure bugs (heartbeat, triage parsing, briefing API, stale refs), Jimbo is now alive between briefings. The next step: make him a reading, connecting, publishing agent — not just a briefing delivery bot.

## Problem

Jimbo has access to 115 vault notes (45 bookmarks, 33 tasks, 17 ideas), daily email with 46+ items, two calendars, context API with priorities/goals/interests, and a blog. Between briefings, he does nothing. The vault is a graveyard — notes saved once and forgotten. Bookmarks are just URLs nobody reads. Ideas sit dormant. There's no system for connecting email insights to vault material, enriching calendar events with context, detecting attention patterns, or publishing from saved material.

## Solution

Eight modular workers that Jimbo composes during heartbeats, briefings, and ad-hoc requests. Each module is standalone, swappable, and follows the same contract. Skills (daily-briefing, blog-publisher, HEARTBEAT.md) orchestrate them but don't contain the logic.

## Principles

- **Full autonomy.** Jimbo reads, connects, publishes, and nudges without asking. Safety mechanisms (Zone 1 sandbox, gmail.readonly, no external sends) are already in place.
- **One thing per heartbeat.** Don't try to do everything every 30 minutes. Pick ONE background task from the rotation. Over a day (30+ heartbeats), cover a lot of ground.
- **Modular everything.** Each behaviour is a worker + task config. Swap models, change thresholds, add new modules — all without touching orchestration logic.
- **Free tier first.** Flash on Google AI free tier for all background work. Sonnet only during briefing windows (already paid for). Opus only via Mac (free with Max plan).
- **Vault is the memory.** Everything Jimbo learns gets written back to the vault or activity log. No ephemeral insights.
- **Reader/Actor split for untrusted content.** Any module that ingests external web content (vault-reader, brave-search) must treat it as untrusted. LLM calls on external content use a Reader pattern: fixed-schema JSON output only, no tool access, no vault writes from the LLM response directly. The calling script validates and writes. (ADR-003)

## Module Contract

Every module follows this pattern:

```
Location:    /workspace/workers/<module-name>.py
Config:      /workspace/tasks/<module-name>.json
Base class:  BaseWorker (from workers/base_worker.py)
Input:       CLI args (argparse)
Output:      stdout JSON (structured result)
Stderr:      progress/debug logging
Side effects: vault note updates (atomic: write-to-temp-then-rename), activity-log entries, experiment-tracker entries, insight entries (ADR-045)
Dependencies: Python 3.11 stdlib only (no pip). LLM calls via BaseWorker.call(). Insight writes via insights_store.py.
Flags:       All modules that modify files support --dry-run
```

Same pattern as existing workers (email_triage.py, newsletter_reader.py). Subclass `BaseWorker` for: config loading, context fetching from jimbo-api, model fallback, experiment tracking, LangFuse tracing. Config controls model, thresholds, batch sizes. Scripts are stateless — all state lives in vault files, SQLite DBs, jimbo-api, or insights.json (ADR-045).

### Knowledge Accumulation (ADR-045)

Every background module can produce **insight entries** — structured observations about patterns, connections, and suggestions discovered during runs. Insights accumulate in `/workspace/insights.json` and are searched by vault-connector and briefing synthesis to improve future results. This is the self-improvement loop: do work → notice patterns → remember patterns → use patterns in future work.

Insight production is optional per run. Only write an insight when there's a genuine pattern worth remembering (3+ keyword hits, recurring connection, novel observation). The `insights_store.py` utility handles storage, search (BM25-lite + temporal decay), and pruning.

### File Write Safety

All vault note modifications use atomic writes:
1. Write to `<filepath>.tmp`
2. `os.replace("<filepath>.tmp", "<filepath>")` (atomic on POSIX)
3. Frontmatter parsing failures are logged and skipped, never crash the module

### Vault Size

Designed for <500 active notes. Current vault is 115 notes. If vault grows significantly (from the 13K Google Tasks/Keep backlog), vault-connector's grep-based search will need indexing. Cross that bridge when we get there.

## Modules

### 1. vault-reader

**Purpose:** Fetch a URL from a bookmark note, extract readable text, summarise via Flash, update the vault note with the summary and extracted connections.

**Script:** `workers/vault_reader.py`

**Dependencies:** `base_worker.py`, `context-helper.py` (priorities/interests for connection matching), `activity-log.py`

**Commands:**
```bash
python3 workers/vault_reader.py read --file vault/notes/bookmark-agent-arch.md
python3 workers/vault_reader.py next          # oldest unread bookmark
python3 workers/vault_reader.py stats         # unread vs enriched counts
python3 workers/vault_reader.py next --dry-run
```

**Behaviour:**
1. Parse frontmatter from the vault note, extract URL
2. Fetch the URL via urllib (timeout=15s, user-agent, redirect following)
3. Strip HTML to readable text using `html.parser.HTMLParser` (stdlib, NOT regex). Strip script/style/nav tags. Extract text content only.
4. If text > 5000 chars, truncate to first 5000
5. **Reader call (untrusted content):** Call Flash with fixed-schema prompt: "Return JSON only: {summary, themes[], entities[], connections[]}". The LLM has no tool access and cannot write to vault — it just analyses.
6. Script validates the JSON response, then writes summary/themes/connections back into the vault note (atomic write)
7. Set `enriched: true` and `enriched_at: <timestamp>` in frontmatter
8. Log to activity-log and experiment-tracker

**Security:** External web content is untrusted. The Flash call uses a Reader pattern per ADR-003: fixed-schema JSON output, no tools, no direct file writes. The script itself validates and writes.

**Output JSON:**
```json
{
  "file": "bookmark-agent-arch.md",
  "url": "https://...",
  "status": "enriched|fetch_failed|already_enriched|no_url",
  "summary": "...",
  "themes": ["...", "..."],
  "connections": ["vault note X", "priority Y"]
}
```

**Config (tasks/vault-reader.json):**
```json
{
  "task_id": "vault-reader",
  "default_model": "gemini-2.5-flash",
  "max_content_chars": 5000,
  "context_slugs": ["priorities", "interests"],
  "skip_if_enriched": true
}
```

### 2. vault-connector

**Purpose:** Take input text (email insight, calendar event summary, free-form query) and find semantically related vault notes via keyword extraction + tag matching + grep.

**Script:** `workers/vault_connector.py`

**Dependencies:** `base_worker.py` (for Flash keyword extraction call), vault notes directory

**Commands:**
```bash
python3 workers/vault_connector.py match --query "Fed rate outlook and mortgage impact"
python3 workers/vault_connector.py match-email --gmail-id 19cf919de37e57bc  # reads from briefing-input.json
python3 workers/vault_connector.py match-event --summary "Watford vs Wrexham"
```

**Behaviour:**
1. Extract keywords from input text (Flash call: "Extract 5-10 keywords/entities from this text. Return JSON: {keywords[]}")
2. Search vault notes using: grep for keywords in filenames and content, tag matching against extracted entities, frontmatter type/project filtering
3. Rank results by: number of keyword hits, tag overlap, priority score (higher = more relevant), freshness (recently modified = more relevant)
4. Return top N matches with match reasons

**Output JSON:**
```json
{
  "query": "Fed rate outlook...",
  "matches": [
    {
      "file": "finance-sipp-timing.md",
      "title": "SIPP contribution timing",
      "type": "task",
      "priority": 8,
      "match_reasons": ["keyword: mortgage", "tag: finance", "priority >= 7"],
      "snippet": "First 50 chars of note content..."
    }
  ],
  "keywords_extracted": ["Fed", "rate", "mortgage", "markets"]
}
```

**Config (tasks/vault-connector.json):**
```json
{
  "task_id": "vault-connector",
  "default_model": "gemini-2.5-flash",
  "max_results": 5,
  "vault_dir": "/workspace/vault/notes",
  "min_keyword_hits": 1
}
```

### 3. vault-roulette

**Purpose:** Pick a random or decaying vault note and return it with context about why it's being surfaced.

**Script:** `workers/vault_roulette.py`

**Dependencies:** vault notes directory, `briefing-input.json` (for recent email insights), `calendar-helper.py` (for today's events), `context-helper.py` (for priorities)

**Commands:**
```bash
python3 workers/vault_roulette.py spin                    # random pick
python3 workers/vault_roulette.py spin --decaying --days 30  # dormant notes only
python3 workers/vault_roulette.py spin --type idea        # specific type
```

**Behaviour:**
1. Scan vault notes, parse frontmatter
2. If `--decaying`: filter to notes where `enriched_at` or file mtime is older than threshold
3. Weight selection: older notes weighted higher (decay = more likely to surface), higher priority weighted higher, types weighted by config (ideas > bookmarks > tasks for serendipity)
4. Pick one note
5. Generate a one-line "why now" reason: check today's calendar (via `calendar-helper.py list-events --days 1`), recent email insights (from `briefing-input.json`), and priorities (via `context-helper.py`) for any connection. If no connection: "No reason — just thought you should see this again."

**Output JSON:**
```json
{
  "file": "idea-gamify-habits.md",
  "title": "Gamifying habit tracking",
  "type": "idea",
  "days_since_touched": 42,
  "reason": "You saved this 6 weeks ago. Today's Songkick email about Romare + your interest in reward systems might connect.",
  "content_preview": "First 200 chars..."
}
```

**Config (tasks/vault-roulette.json):**
```json
{
  "task_id": "vault-roulette",
  "default_model": "gemini-2.5-flash",
  "decay_threshold_days": 30,
  "type_weights": {"idea": 3, "bookmark": 2, "task": 1, "recipe": 2, "travel": 2},
  "exclude_types": ["journal"]
}
```

### 4. vault-tagger

**Purpose:** Analyse tag co-occurrence across vault notes. Detect emerging clusters — interests you're circling without consciously noticing.

**Script:** `workers/vault_tagger.py`

**Dependencies:** `base_worker.py` (for Flash analysis call), vault notes directory, `context-helper.py` (for interests comparison)

**Commands:**
```bash
python3 workers/vault_tagger.py analyse     # full tag analysis + cluster detection
python3 workers/vault_tagger.py clusters    # just show current clusters (no LLM call)
```

**Note:** Attention drift analysis (comparing tags vs priorities) lives in `attention-audit.py`, not here. vault-tagger focuses on tag patterns; attention-audit focuses on priority alignment.

**Behaviour (analyse):**
1. Scan all vault notes, extract tags from frontmatter
2. Build co-occurrence matrix: which tags appear together
3. Identify clusters: groups of 3+ tags that frequently co-occur
4. Compare clusters to context API interests — flag any cluster NOT represented in interests
5. Call Flash: "These tag clusters emerged from the vault. Which represent genuine emerging interests vs noise? Return JSON: {clusters[], emerging[]}"

**Behaviour (clusters):**
1. Same as steps 1-3 of analyse, but skip LLM call. Pure data.

**Output JSON (analyse):**
```json
{
  "total_notes": 115,
  "total_unique_tags": 34,
  "clusters": [
    {"tags": ["travel", "spain", "food"], "count": 8, "in_interests": false},
    {"tags": ["ai", "agents", "architecture"], "count": 12, "in_interests": true}
  ],
  "emerging": ["travel+spain+food — not in interests, 8 notes across 3 weeks"]
}
```

**Config (tasks/vault-tagger.json):**
```json
{
  "task_id": "vault-tagger",
  "default_model": "gemini-2.5-flash",
  "min_cluster_size": 3,
  "min_co_occurrence": 2,
  "context_slugs": ["interests"]
}
```

### 5. event-enricher

**Purpose:** Take a calendar event and search vault + email insights for relevant context. Used before briefings and as standalone pre-event briefs.

**Script:** `workers/event_enricher.py`

**Dependencies:** `base_worker.py`, `workers/vault_connector.py` (for vault search), `briefing-input.json` (for email insights), `calendar-helper.py` (for past events)

**Commands:**
```bash
python3 workers/event_enricher.py enrich --summary "Watford vs Wrexham" --start "2026-03-17T19:45:00"
python3 workers/event_enricher.py upcoming --hours 6   # enrich all events in next 6 hours
```

**Behaviour:**
1. Extract key entities from event summary (Flash call: "Extract entities from this event title. Return JSON: {entities[]}")
2. Search vault via vault-connector subprocess for related notes
3. Search recent email insights from `briefing-input.json` (on disk, not API) for related content
4. Search calendar via `calendar-helper.py list-events --days 7` for related past events
5. Compile a context brief

**Output JSON:**
```json
{
  "event": "Watford vs Wrexham",
  "start": "2026-03-17T19:45:00",
  "vault_context": [{"file": "...", "relevance": "..."}],
  "email_context": [{"subject": "WML: Kieffer Moore NONO", "insight": "..."}],
  "history": "Last match: Watford 2-1 Wrexham (from calendar Dec 14)",
  "brief": "Moore likely out per WML threads. You saved a tactical analysis of Wrexham's 3-5-2."
}
```

**Config (tasks/event-enricher.json):**
```json
{
  "task_id": "event-enricher",
  "default_model": "gemini-2.5-flash",
  "max_vault_matches": 3,
  "history_days": 90
}
```

### 6. attention-audit

**Purpose:** Compare what's in priorities/goals vs what you're actually saving, acting on, and ignoring. The honest mirror.

**Script:** `workers/attention_audit.py`

**Dependencies:** `base_worker.py`, `context-helper.py` (priorities/goals), vault notes directory (for mtime analysis), `activity-log.py` (for action history), `calendar-helper.py` (for suggestion tracking), `vault-tagger.py clusters` output (for emerging themes)

**Commands:**
```bash
python3 workers/attention_audit.py weekly    # full weekly audit
python3 workers/attention_audit.py check     # quick alignment check (no LLM)
```

**Behaviour (weekly):**
1. Load priorities/goals from context API (via `context-helper.py`)
2. Load vault saves from last 7 days (by file mtime)
3. Load activity log entries from last 7 days (via `activity-log.py stats --days 7`)
4. Load vault-tagger cluster data (from last `analyse` run output if available)
5. Score alignment: for each priority, how much vault/email/calendar/activity is connected to it?
6. Detect drift: high-priority items with low activity, themes getting attention without being priorities
7. Call Flash: "Given these patterns, write a candid 5-line assessment. Not what they did — what it reveals."

**Behaviour (check):**
Pure data — steps 1-6 without the LLM call. Returns raw alignment scores.

**Output JSON:**
```json
{
  "period": "2026-03-10 to 2026-03-17",
  "priorities_alignment": [
    {"priority": "LocalShout", "score": 0.7, "evidence": "3 vault saves, 5 email engagements, 1 work block"},
    {"priority": "Personal finance", "score": 0.1, "evidence": "0 saves, 1 email, YNAB skipped 3 times"}
  ],
  "drift": [
    {"theme": "travel deals", "vault_saves": 6, "not_in_priorities": true}
  ],
  "honest_assessment": "You're executing on LocalShout but avoiding finance...",
  "suggestion": "Either promote travel to a real priority or schedule one 30-min YNAB session."
}
```

**Config (tasks/attention-audit.json):**
```json
{
  "task_id": "attention-audit",
  "default_model": "gemini-2.5-flash",
  "period_days": 7,
  "context_slugs": ["priorities", "goals"]
}
```

### 7. blog-drafter

**Purpose:** Take a topic, vault notes bundle, or creative prompt and write a blog draft. Saves to blog-src ready for publish. Does NOT publish — that's the blog-publisher skill's job.

**Script:** `workers/blog_drafter.py`

**Dependencies:** `base_worker.py`, `workers/vault_connector.py` (for related notes), `workers/attention_audit.py` (for honest-opinion mode), `activity-log.py`

**Commands:**
```bash
python3 workers/blog_drafter.py draft --source vault/notes/idea-gamify-habits.md
python3 workers/blog_drafter.py draft --topic "What I learned from 9 sessions of broken infrastructure"
python3 workers/blog_drafter.py compost --files vault/notes/idea-a.md vault/notes/idea-b.md
python3 workers/blog_drafter.py weekly-digest
python3 workers/blog_drafter.py honest-opinion
python3 workers/blog_drafter.py draft --source vault/notes/idea-x.md --dry-run
```

**Behaviour (draft):**
1. Read source material (vault note, topic, or composted notes)
2. If vault note: also run vault-connector subprocess to find related notes for context
3. Call Flash: "Write a 3-5 paragraph blog post in Jimbo's voice (opinionated, concise, not corporate). Source: [material]. Related context: [connections]. Have a clear take, not just a summary."
4. Generate frontmatter (title, date, tags, description)
5. Write to `/workspace/blog-src/src/content/posts/YYYY-MM-DD-<slug>.md`
6. Log to activity-log

**Behaviour (weekly-digest):**
1. Gather: vault saves this week (by mtime), email highlights from `briefing-input.json`, activity log entries, vault-tagger clusters
2. Call Flash: "Write a weekly digest. What Marvin saved, acted on, and ignored. Any patterns. Under 500 words, conversational."

**Behaviour (honest-opinion):**
1. Run `attention-audit.py check` subprocess
2. Call Flash: "Write a candid blog post about what this week's patterns reveal. Honest but not cruel. Jimbo's opinion column."

**Output JSON:**
```json
{
  "file": "2026-03-17-broken-infrastructure.md",
  "title": "Nine Sessions of Broken Infrastructure",
  "word_count": 380,
  "tags": ["openclaw", "infrastructure", "debugging"],
  "status": "drafted"
}
```

**Config (tasks/blog-drafter.json):**
```json
{
  "task_id": "blog-drafter",
  "default_model": "gemini-2.5-flash",
  "max_word_count": 500,
  "blog_dir": "/workspace/blog-src/src/content/posts",
  "context_slugs": ["priorities", "interests"]
}
```

### 8. brave-search (optional, requires API key)

**Purpose:** Search the web for a query. Used by vault-reader when a URL fetch fails, by event-enricher for external context, and by blog-drafter for research.

**Script:** `workers/brave_search.py`

**Dependencies:** `base_worker.py`, env var `BRAVE_SEARCH_API_KEY`

**Commands:**
```bash
python3 workers/brave_search.py search --query "Wrexham AFC 3-5-2 formation analysis"
python3 workers/brave_search.py summarise --url "https://..."
```

**Behaviour:**
1. Call Brave Search API with query (stdlib urllib, no pip)
2. Return top N results with title, URL, snippet
3. For summarise: fetch URL, strip HTML via `html.parser.HTMLParser`, return readable text

**Security:** Search results and fetched URLs are untrusted external content. Reader pattern applies — fixed-schema JSON output from any LLM calls on this content.

**Config (tasks/brave-search.json):**
```json
{
  "task_id": "brave-search",
  "api_key_env": "BRAVE_SEARCH_API_KEY",
  "max_results": 5,
  "free_tier_monthly_limit": 2000
}
```

**Deployment note:** If implemented, add `BRAVE_SEARCH_API_KEY` to `/opt/openclaw.env` and to the Docker sandbox env var injection in root crontab and openclaw.json sandbox config.

## Orchestration

### HEARTBEAT.md — Background Research Rotation

The heartbeat fires every 30 minutes during active hours (07:00-01:00). Each heartbeat, pick ONE random module from the rotation, run it, and send a Telegram nudge if the result is interesting. This is the primary engine — no separate cron orchestrator.

Add to HEARTBEAT.md:

```markdown
## Background research (one random module per heartbeat)

Each heartbeat, pick ONE at random from this list. Don't repeat the same module two heartbeats in a row — use memory to track what you did last.

1. **Read a bookmark**: `python3 /workspace/workers/vault_reader.py next` — fetch and summarise the oldest unread bookmark. If it connects to something in today's email or your priorities, tell Marvin via Telegram. Example: "Just read your bookmark about agent architectures. Key themes: multi-agent coordination, tool use. Connects to your LocalShout priority."

2. **Vault roulette**: `python3 /workspace/workers/vault_roulette.py spin --decaying` — surface a note dormant 30+ days. If it connects to today's email or calendar, share it. If not, note it in memory — it might connect later. Example: "Dormant note resurface: 'Gamifying habit tracking' (42 days). Songkick email about Romare + your interest in reward systems might connect."

3. **Email × vault collision**: Pick an email insight from today's briefing-input.json. Run `python3 /workspace/workers/vault_connector.py match --query "<insight text>"`. If 2+ keyword hits, send the connection. Example: "Today's Seeking Alpha article about Fed rates connects to your SIPP timing task (priority 8) and your mortgage calculator bookmark."

4. **Event enrichment**: Run `python3 /workspace/workers/event_enricher.py upcoming --hours 6`. If context found for an upcoming event, send a pre-event brief. Example: "Watford vs Wrexham at 19:45 — Moore likely out per WML, you saved a Wrexham 3-5-2 tactical analysis."

5. **Blog draft**: If you haven't drafted a blog post today, pick material: a freshly enriched bookmark, an interesting collision, or run `python3 /workspace/workers/blog_drafter.py compost` on 2 random ideas. Draft the post, then use the blog-publisher skill to publish it.

**Rules:**
- Skip silently if the module finds nothing interesting. Don't send "nothing to report."
- Log every run to activity-log, even silent ones.
- You have conversation context the modules don't — if a result connects to something Marvin mentioned earlier today, say so.
- If you notice a pattern across multiple runs, synthesise it into an insight.
```

**Fallback:** If after a few days the model isn't following the rotation (activity log still empty, no Telegram nudges), we build a `background-tick.py` cron script that runs the same rotation mechanically. But try the heartbeat-native approach first — the model has conversation context, memory, and the ability to follow up, which a cron script doesn't.

### daily-briefing skill — Additions

Add after vault tasks section:

```markdown
5. **Jimbo's finds** — Check memory and activity-log for recent background research results. If vault-reader enriched bookmarks since the last briefing, mention the most interesting one with its connections. If vault-connector found email×vault collisions, present the strongest match. If vault-tagger detected a new cluster, mention it. Keep this to 2-3 finds max — quality over quantity.
```

### blog-publisher skill — Additions

The blog-publisher skill stays as-is for the publish mechanics (git commit, push, Cloudflare build). blog-drafter handles content creation. The skill just needs a note:

```markdown
## Content sources

Blog posts can come from several places:
- **Ad-hoc**: You decide to write about something
- **Vault-to-blog**: `python3 /workspace/workers/blog_drafter.py draft --source <vault-note>`
- **Idea composting**: `python3 /workspace/workers/blog_drafter.py compost --files <note1> <note2>`
- **Weekly digest**: `python3 /workspace/workers/blog_drafter.py weekly-digest`
- **Honest opinion**: `python3 /workspace/workers/blog_drafter.py honest-opinion`

Use blog-drafter to generate content, then follow the publish steps below.
```

### Cron Jobs

Add to VPS root crontab:

```bash
# Daily 04:00 UTC — tag gravity analysis (before task scoring at 04:30)
0 4 * * * docker exec ... python3 /workspace/workers/vault_tagger.py analyse >> /var/log/vault-tagger.log 2>&1

# Sunday 09:00 UTC — weekly attention audit + digest blog post
0 9 * * 0 docker exec ... python3 /workspace/workers/attention_audit.py weekly >> /var/log/attention-audit.log 2>&1
0 9 * * 0 docker exec ... python3 /workspace/workers/blog_drafter.py weekly-digest >> /var/log/blog-drafter.log 2>&1
```

Background research runs via heartbeat (every 30 min, model-driven), not cron. Only vault-tagger (daily batch analysis) and attention-audit + weekly-digest (Sunday reflection) need dedicated cron entries because they're scheduled at specific times independent of heartbeat.

### Deployment

`workspace-push.sh` already syncs the `workers/` directory. New modules in `/workspace/workers/` will be deployed automatically. New task configs in `/workspace/tasks/` are also synced. No deployment script changes needed.

## Implementation Order

Build in this order — each module is independently useful:

1. **vault-reader** — highest impact. Turns 45 dead bookmarks into rich, connected notes. Unblocks everything else.
2. **vault-connector** — the linking engine. Used by event-enricher, email×vault collisions, and blog-drafter.
3. **vault-roulette** — simplest module. Adds serendipity immediately.
4. **HEARTBEAT.md update** — add the background research rotation. Once modules 1-3 are deployed, Jimbo starts using them every 30 min.
5. **event-enricher** — uses vault-connector. Makes calendar events contextual.
6. **blog-drafter** — uses vault-connector. Turns vault material into published posts.
7. **vault-tagger** — batch analysis, runs daily. Detects patterns.
8. **attention-audit** — weekly reflection. Consumes vault-tagger output.
9. **brave-search** — optional enhancement. Adds web search to vault-reader and event-enricher.

Each module can be built, deployed, and tested independently. HEARTBEAT.md rotation grows as modules ship. If the model doesn't follow the rotation after a few days, fall back to a `background-tick.py` cron script.

## What Stays Unchanged

- briefing-prep.py (data collection pipeline)
- email_triage.py, newsletter_reader.py, email_decision.py (email pipeline)
- calendar-helper.py, context-helper.py (existing tools)
- jimbo-api (all existing endpoints)
- OpenClaw cron jobs (morning/afternoon briefing)
- SOUL.md (personality)
- Security model (Zone 1 sandbox, readonly email, no external sends)

## Success Criteria

- Jimbo reads at least 3 bookmarks per day (measurable via enriched_at counts)
- At least 1 email×vault collision surfaced per briefing
- 2-3 blog posts per week published autonomously
- Activity log no longer empty — background research logged
- Weekly attention audit running and producing honest assessments
