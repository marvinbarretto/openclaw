# ADR-045: Knowledge Accumulation Loop

## Status

Accepted

## Context

While evaluating [CashClaw](https://github.com/moltlaunch/cashclaw) — an open-source autonomous work agent — we identified a pattern missing from the autonomous mind spec (2026-03-17). CashClaw's core self-improvement mechanism is a knowledge accumulation loop:

1. **Do work** → execute tasks, get results
2. **Produce knowledge entries** → structured insights from each run stored in `knowledge.json`
3. **Search knowledge** → BM25 + temporal decay retrieval, top N hits injected into future task prompts
4. **Get better** → each subsequent task benefits from accumulated operational memory

The autonomous mind spec has eight modular workers (vault-reader, vault-connector, vault-roulette, etc.) but each run is stateless. vault-reader enriches a bookmark, vault-connector finds matches, vault-roulette surfaces a note — but none of them remember *patterns* across runs. There's no mechanism for Jimbo to learn things like:

- "Finance bookmarks tend to connect to the SIPP task"
- "Travel deals cluster on Tuesdays from Skyscanner"
- "Composted idea posts draft better than single-source"
- "Watford match prep benefits from WML newsletter gems"

This is the difference between a tool that does tasks and an agent that gets better at them.

### What we learned from CashClaw's source

**search.ts (BM25 + temporal decay):**
- MiniSearch library with fuzzy matching (`fuzzy: 0.2`) and prefix search
- 30-day half-life temporal decay: `score * e^(-λ * age)` where `λ = ln(2) / halfLifeMs`
- Two data types indexed together (knowledge + feedback entries)
- Incremental index updates with dirty flag — only rebuilds when entries are trimmed
- Top 5 results injected into system prompts automatically

**study.ts (self-learning sessions):**
- Three rotating topics: feedback analysis, specialty research, task simulation
- Round-robin selection (least-covered topic goes next)
- Each session produces a structured knowledge entry
- Sessions run only when idle (no active tasks) — configurable interval (default 30 min)

**loop/index.ts (agent loop):**
- Clean separation: system prompt builder + task context builder + tool registry + LLM provider
- Multi-turn: loop until LLM stops calling tools or max turns reached
- All side effects through tools — the loop itself is provider-agnostic and task-source-agnostic
- Provider adapters use raw `fetch()`, zero SDK dependencies

**heartbeat.ts (orchestration):**
- WebSocket + REST polling dual mode with exponential backoff
- Study sessions only when idle, skipped if urgent tasks exist
- Task deduplication, expiry (7 days), concurrent task limits
- Event-driven architecture with typed listeners

### What's portable vs what's not

**Portable (adopt):**
- Knowledge accumulation pattern (insights.json + structured entries)
- BM25-lite scoring with temporal decay (implementable in stdlib Python)
- "Study when idle" scheduling (maps to heartbeat rotation)
- Insight injection into future prompts (vault-connector can search insights)

**Not portable (different constraints):**
- MiniSearch library (we're stdlib-only Python, no pip)
- Multi-turn tool-use agent loop (our workers are script-based, not long-running processes)
- WebSocket real-time events (our heartbeat is model-driven via HEARTBEAT.md)
- Client rating feedback loop (no external clients — Marvin is the only user)

## Decision

### 1. Add an insights store (`insights.json`)

New file: `/workspace/insights.json` (on VPS, alongside knowledge.json pattern from CashClaw).

```json
{
  "entries": [
    {
      "id": "ins_a1b2c3d4",
      "source_module": "vault-reader",
      "source_run": "run_e5f6g7h8",
      "timestamp": 1710700000,
      "type": "connection",
      "text": "Agent architecture bookmarks consistently connect to LocalShout priority — 3 of last 5 enriched bookmarks had AI/agent themes matching active project work",
      "tags": ["ai", "agents", "localshout", "architecture"],
      "confidence": 0.8
    }
  ],
  "max_entries": 100
}
```

Entry types: `connection` (cross-reference found), `pattern` (recurring observation), `suggestion` (actionable recommendation), `reflection` (meta-observation about Jimbo's own work).

Managed by a new `insights_store.py` utility (stdlib, atomic writes, FIFO trim at 100 entries). All workers import it; it's not a worker itself.

### 2. Add BM25-lite scoring to vault-connector

Replace raw grep hit counting with term-frequency scoring:

```
score = Σ(tf(term, doc) * idf(term, corpus)) * decay(note_type, age)
```

Where:
- `tf` = term frequency in note content + title + tags
- `idf` = inverse document frequency across vault (rarer terms score higher)
- `decay` = configurable per note type:
  - `bookmark`: no decay (reference material stays relevant)
  - `idea`: gentle decay (90-day half-life — ideas age but slowly)
  - `task`: moderate decay (30-day half-life — stale tasks less relevant)
  - `recipe/travel/event`: steep decay (14-day half-life — time-sensitive)

Implementation: pure Python stdlib. Build term index on each run (vault is <500 notes, this is fast). No persistent index needed yet.

vault-connector also searches `insights.json` alongside vault notes. Insight hits are tagged as `source: "insight"` in results so the caller knows they came from operational memory, not vault content.

### 3. Insight production in every background module

Each module gains an optional insight production step after its main work:

**vault-reader:** After enriching a bookmark, if the themes/connections match a pattern seen in previous enrichments (check insights.json), produce a `pattern` insight. E.g., "3 of the last 5 AI bookmarks connected to LocalShout — this is a genuine interest cluster, not noise."

**vault-connector:** After finding matches, if the match quality is high (3+ keyword hits), produce a `connection` insight. E.g., "Fed rate articles consistently match SIPP timing task — this connection is reliable."

**vault-roulette:** After surfacing a note, if it connects to today's email/calendar, produce a `connection` insight. E.g., "Dormant recipe notes tend to resurface near weekend meal planning — timing correlation."

**blog-drafter:** After drafting, produce a `reflection` insight about the source material quality. E.g., "Composted ideas (2+ notes) produce more coherent drafts than single-source."

Insight production is gated: only write an insight if it's genuinely novel (check existing insights for duplicates by tag overlap). Don't produce insights on every run — only when there's a pattern worth remembering. This prevents the store from filling with noise.

### 4. Insight injection into briefings and blog drafts

**daily-briefing skill** (section 5, "Jimbo's finds"): In addition to checking activity-log for recent background work, search `insights.json` for insights produced since the last briefing. Surface the most interesting 1-2. This gives Jimbo a "here's what I've been learning" section.

**blog-drafter** (`weekly-digest` and `honest-opinion` modes): Pull from insights.json instead of just raw vault/activity data. Accumulated insights are richer material for blog posts than individual data points.

### 5. insights_store.py utility

```
Location:    /workspace/insights_store.py
Interface:   CLI (for workers) + importable module
Commands:
  python3 insights_store.py add --module vault-reader --type connection --text "..." --tags ai,agents --confidence 0.8
  python3 insights_store.py search --query "finance bookmarks" --limit 5
  python3 insights_store.py stats
  python3 insights_store.py prune --max 100
```

Search uses the same BM25-lite scoring as vault-connector (shared function). Temporal decay: 60-day half-life for all insight types (insights are operational memory, they decay uniformly).

Atomic writes (write-to-temp-then-rename). FIFO pruning: when entries exceed max, drop the oldest lowest-confidence entries first.

## Consequences

### What becomes easier

- **Jimbo gets smarter over time.** Each background run contributes to a growing operational memory. After a week of heartbeats (~30+ runs), vault-connector's results improve because it has context about which connections are reliable.
- **Blog material writes itself.** Weekly digests can pull from rich insights instead of raw activity logs. "Here's what I noticed this week" is more interesting than "here's what I did."
- **Briefings gain depth.** "Today's email about Fed rates connects to your SIPP task — and I've noticed this connection 4 times in the last 2 weeks" is more valuable than a one-off match.
- **Pattern detection is automatic.** Over time, insights reveal what Marvin actually pays attention to vs. what he says he cares about — input for the attention-audit module.

### What becomes harder

- **insights.json management.** Needs pruning, deduplication, and quality gating. Without discipline, the store fills with noise. The confidence score and duplicate check help but aren't foolproof.
- **Token cost.** Each insight production step is an additional Flash call (small — keyword extraction + pattern check). At ~100 tokens per insight check, this adds ~2-3K tokens/day to background work. Well within free tier.
- **Debugging.** When Jimbo surfaces a questionable connection, tracing it back through the insight chain is harder than tracing a direct grep match. The `source_module` and `source_run` fields help.

### What stays unchanged

- Module contract (BaseWorker subclass, CLI args, stdout JSON, atomic writes)
- Security model (Reader/Actor split for untrusted content still applies)
- Existing workers (email_triage.py, newsletter_reader.py unchanged)
- Deployment (workspace-push.sh already syncs workers/ and workspace/)
- Cron schedule (no new cron entries needed — insights are produced during existing runs)

### Implementation order

1. `insights_store.py` — the utility (standalone, testable)
2. BM25-lite scoring function — shared between vault-connector and insights search
3. vault-connector update — add BM25-lite scoring + insights.json search
4. vault-reader update — add insight production after enrichment
5. vault-roulette update — add insight production after surfacing
6. HEARTBEAT.md update — mention insights in the background research rotation instructions
7. blog-drafter — pull from insights store in weekly-digest mode

Each step is independently deployable. The insights store can exist before any module writes to it.
