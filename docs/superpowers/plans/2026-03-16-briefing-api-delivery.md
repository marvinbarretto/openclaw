# Briefing API Delivery Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opus publishes briefing analysis to jimbo-api; Jimbo fetches via API and delivers section-by-section as a conversational agent.

**Architecture:** New briefing endpoint in jimbo-api (Hono/Node/SQLite). opus-briefing.sh POSTs instead of writing files. Daily briefing skill rewritten as step-by-step tool calls. Opus prompts updated to drop editorial_voice, add vault_tasks.

**Tech Stack:** TypeScript (jimbo-api), Bash (opus-briefing.sh), Markdown (OpenClaw skill, Opus prompts)

**Spec:** `docs/superpowers/specs/2026-03-16-briefing-api-delivery-design.md`

---

## Chunk 1: jimbo-api Briefing Endpoint

### Task 1: Add briefing_analyses table to schema

**Files:**
- Modify: `/Users/marvinbarretto/development/jimbo/jimbo-api/src/db/index.ts`

- [ ] **Step 1: Add CREATE TABLE to the SCHEMA constant**

Add after the last CREATE TABLE in the SCHEMA string:

```sql
CREATE TABLE IF NOT EXISTS briefing_analyses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session TEXT NOT NULL,
  model TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  analysis TEXT NOT NULL,
  user_rating INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_briefing_analyses_created ON briefing_analyses(created_at);
CREATE INDEX IF NOT EXISTS idx_briefing_analyses_session ON briefing_analyses(session);
```

- [ ] **Step 2: Verify DB initialises cleanly**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm run build`
Expected: No TypeScript errors

- [ ] **Step 3: Commit**

```bash
git add src/db/index.ts
git commit -m "feat: add briefing_analyses table to schema"
```

### Task 2: Create briefing types

**Files:**
- Create: `/Users/marvinbarretto/development/jimbo/jimbo-api/src/types/briefing.ts`

- [ ] **Step 1: Write the types file**

```typescript
export interface BriefingAnalysis {
  id: number;
  session: string;
  model: string;
  generated_at: string;
  analysis: BriefingAnalysisData;
  user_rating: number | null;
  created_at: string;
}

export interface BriefingAnalysisData {
  day_plan: DayPlanEntry[];
  email_highlights: EmailHighlight[];
  surprise: Surprise | null;
  vault_tasks: VaultTaskEntry[];
}

export interface DayPlanEntry {
  time: string;
  suggestion: string;
  source: string;
  reasoning: string;
}

export interface EmailHighlight {
  source: string;
  headline: string;
  editorial: string;
  links: string[];
}

export interface Surprise {
  fact: string;
  strategy: string;
}

export interface VaultTaskEntry {
  title: string;
  priority: number;
  actionability: string;
  note: string;
}

export const VALID_SESSIONS = ['morning', 'afternoon'] as const;
export type Session = typeof VALID_SESSIONS[number];
```

- [ ] **Step 2: Commit**

```bash
git add src/types/briefing.ts
git commit -m "feat: add briefing analysis types"
```

### Task 3: Create briefing service with tests (TDD)

**Files:**
- Create: `/Users/marvinbarretto/development/jimbo/jimbo-api/test/briefing.test.ts`
- Create: `/Users/marvinbarretto/development/jimbo/jimbo-api/src/services/briefing.ts`

- [ ] **Step 1: Write the test file**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const TEST_DB_DIR = './test/tmp-briefing';
const TEST_DB_PATH = path.join(TEST_DB_DIR, 'test.db');
process.env.CONTEXT_DB_PATH = TEST_DB_PATH;

const { getDb } = await import('../src/db/index.js');
const {
  createAnalysis,
  getLatestAnalysis,
  getAnalysisHistory,
  rateAnalysis,
} = await import('../src/services/briefing.js');

const VALID_INPUT = {
  session: 'morning' as const,
  model: 'claude-opus-4-6',
  generated_at: new Date().toISOString(),
  day_plan: [{ time: '09:00-10:00', suggestion: 'Work', source: 'calendar', reasoning: 'Free slot' }],
  email_highlights: [{ source: 'test', headline: 'Test', editorial: 'Test', links: [] }],
  surprise: { fact: 'A surprise', strategy: 'Found it' },
  vault_tasks: [{ title: 'Fix bug', priority: 10, actionability: 'clear', note: 'Important' }],
};

describe('briefing service', () => {
  beforeEach(() => {
    mkdirSync(TEST_DB_DIR, { recursive: true });
    const db = getDb();
    db.exec('DELETE FROM briefing_analyses');
  });

  describe('createAnalysis', () => {
    it('stores and returns analysis with id', () => {
      const result = createAnalysis(VALID_INPUT);
      expect(result.id).toBeGreaterThan(0);
      expect(result.session).toBe('morning');
      expect(result.model).toBe('claude-opus-4-6');
      expect(result.analysis.day_plan).toHaveLength(1);
      expect(result.analysis.email_highlights).toHaveLength(1);
      expect(result.analysis.surprise).not.toBeNull();
      expect(result.analysis.vault_tasks).toHaveLength(1);
    });

    it('stores with empty optional fields', () => {
      const result = createAnalysis({
        ...VALID_INPUT,
        email_highlights: undefined,
        surprise: undefined,
        vault_tasks: undefined,
      });
      expect(result.analysis.email_highlights).toEqual([]);
      expect(result.analysis.surprise).toBeNull();
      expect(result.analysis.vault_tasks).toEqual([]);
    });
  });

  describe('getLatestAnalysis', () => {
    it('returns null when no analyses exist', () => {
      expect(getLatestAnalysis()).toBeNull();
    });

    it('returns most recent analysis', () => {
      createAnalysis(VALID_INPUT);
      createAnalysis({ ...VALID_INPUT, model: 'second-run' });
      const latest = getLatestAnalysis();
      expect(latest!.model).toBe('second-run');
    });

    it('filters by session', () => {
      createAnalysis(VALID_INPUT);
      createAnalysis({ ...VALID_INPUT, session: 'afternoon' as const });
      const morning = getLatestAnalysis('morning');
      expect(morning!.session).toBe('morning');
    });

    it('returns null for stale analyses (>6 hours)', () => {
      const db = getDb();
      const staleTime = new Date(Date.now() - 7 * 60 * 60 * 1000).toISOString();
      db.prepare(
        `INSERT INTO briefing_analyses (session, model, generated_at, analysis) VALUES (?, ?, ?, ?)`
      ).run('morning', 'test', staleTime, JSON.stringify({ day_plan: [], email_highlights: [], surprise: null, vault_tasks: [] }));
      expect(getLatestAnalysis()).toBeNull();
    });
  });

  describe('getAnalysisHistory', () => {
    it('returns empty array when no analyses', () => {
      expect(getAnalysisHistory()).toEqual([]);
    });

    it('returns analyses in reverse chronological order', () => {
      createAnalysis(VALID_INPUT);
      createAnalysis({ ...VALID_INPUT, model: 'second' });
      const history = getAnalysisHistory(10);
      expect(history[0].model).toBe('second');
    });

    it('respects limit', () => {
      createAnalysis(VALID_INPUT);
      createAnalysis({ ...VALID_INPUT, model: 'second' });
      createAnalysis({ ...VALID_INPUT, model: 'third' });
      const history = getAnalysisHistory(2);
      expect(history).toHaveLength(2);
    });
  });

  describe('rateAnalysis', () => {
    it('sets user_rating on existing analysis', () => {
      const created = createAnalysis(VALID_INPUT);
      const rated = rateAnalysis(created.id, 8);
      expect(rated!.user_rating).toBe(8);
    });

    it('returns null for non-existent id', () => {
      expect(rateAnalysis(999, 5)).toBeNull();
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npx vitest run test/briefing.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Write the service**

```typescript
import { getDb } from '../db/index.js';
import type { BriefingAnalysis, BriefingAnalysisData, Session } from '../types/briefing.js';

interface CreateAnalysisInput {
  session: Session;
  model: string;
  generated_at: string;
  day_plan: BriefingAnalysisData['day_plan'];
  email_highlights?: BriefingAnalysisData['email_highlights'];
  surprise?: BriefingAnalysisData['surprise'];
  vault_tasks?: BriefingAnalysisData['vault_tasks'];
}

function mapRow(row: any): BriefingAnalysis {
  return {
    ...row,
    analysis: JSON.parse(row.analysis),
    user_rating: row.user_rating ?? null,
  };
}

export function createAnalysis(input: CreateAnalysisInput): BriefingAnalysis {
  const db = getDb();
  const analysis: BriefingAnalysisData = {
    day_plan: input.day_plan,
    email_highlights: input.email_highlights ?? [],
    surprise: input.surprise ?? null,
    vault_tasks: input.vault_tasks ?? [],
  };

  const result = db.prepare(
    `INSERT INTO briefing_analyses (session, model, generated_at, analysis)
     VALUES (?, ?, ?, ?)`
  ).run(input.session, input.model, input.generated_at, JSON.stringify(analysis));

  return mapRow(
    db.prepare('SELECT * FROM briefing_analyses WHERE id = ?').get(result.lastInsertRowid)
  );
}

export function getLatestAnalysis(session?: string): BriefingAnalysis | null {
  const db = getDb();
  const conditions = [`created_at >= datetime('now', '-6 hours')`];
  const values: any[] = [];

  if (session) {
    conditions.push('session = ?');
    values.push(session);
  }

  const where = conditions.join(' AND ');
  const row = db.prepare(
    `SELECT * FROM briefing_analyses WHERE ${where} ORDER BY created_at DESC LIMIT 1`
  ).get(...values) as any | undefined;

  return row ? mapRow(row) : null;
}

export function getAnalysisHistory(limit: number = 10): BriefingAnalysis[] {
  const db = getDb();
  const rows = db.prepare(
    `SELECT * FROM briefing_analyses ORDER BY created_at DESC LIMIT ?`
  ).all(limit) as any[];
  return rows.map(mapRow);
}

export function rateAnalysis(id: number, rating: number): BriefingAnalysis | null {
  const db = getDb();
  const existing = db.prepare('SELECT * FROM briefing_analyses WHERE id = ?').get(id);
  if (!existing) return null;

  db.prepare('UPDATE briefing_analyses SET user_rating = ? WHERE id = ?').run(rating, id);
  return mapRow(db.prepare('SELECT * FROM briefing_analyses WHERE id = ?').get(id));
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npx vitest run test/briefing.test.ts`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/briefing.ts test/briefing.test.ts
git commit -m "feat: briefing analysis service with tests"
```

### Task 4: Create briefing routes

**Files:**
- Create: `/Users/marvinbarretto/development/jimbo/jimbo-api/src/routes/briefing.ts`
- Modify: `/Users/marvinbarretto/development/jimbo/jimbo-api/src/index.ts`

- [ ] **Step 1: Write the routes file**

```typescript
import { Hono } from 'hono';
import { VALID_SESSIONS } from '../types/briefing.js';
import {
  createAnalysis,
  getLatestAnalysis,
  getAnalysisHistory,
  rateAnalysis,
} from '../services/briefing.js';

const briefing = new Hono();

briefing.post('/analysis', async (c) => {
  const body = await c.req.json();

  if (!body.session || !VALID_SESSIONS.includes(body.session)) {
    return c.json({ error: 'session required (morning|afternoon)' }, 400);
  }
  if (!body.model) {
    return c.json({ error: 'model required' }, 400);
  }
  if (!body.generated_at) {
    return c.json({ error: 'generated_at required' }, 400);
  }
  if (!Array.isArray(body.day_plan) || body.day_plan.length === 0) {
    return c.json({ error: 'day_plan required (non-empty array)' }, 400);
  }

  const result = createAnalysis({
    session: body.session,
    model: body.model,
    generated_at: body.generated_at,
    day_plan: body.day_plan,
    email_highlights: body.email_highlights,
    surprise: body.surprise,
    vault_tasks: body.vault_tasks,
  });

  return c.json(result, 201);
});

briefing.get('/latest', (c) => {
  const session = c.req.query('session');
  if (session && !VALID_SESSIONS.includes(session as any)) {
    return c.json({ error: 'session must be morning or afternoon' }, 400);
  }

  const result = getLatestAnalysis(session || undefined);
  if (!result) {
    return c.json({ error: 'No fresh analysis available' }, 404);
  }

  return c.json(result);
});

briefing.get('/history', (c) => {
  const limit = Number(c.req.query('limit') || '10');
  if (isNaN(limit) || limit < 1) {
    return c.json({ error: 'limit must be a positive number' }, 400);
  }

  return c.json(getAnalysisHistory(limit));
});

briefing.put('/:id/rate', async (c) => {
  const id = Number(c.req.param('id'));
  if (isNaN(id)) return c.json({ error: 'Invalid id' }, 400);

  const body = await c.req.json<{ rating: number }>();
  if (!body.rating || !Number.isInteger(body.rating) || body.rating < 1 || body.rating > 10) {
    return c.json({ error: 'rating required (integer 1-10)' }, 400);
  }

  const result = rateAnalysis(id, body.rating);
  if (!result) return c.json({ error: 'Not found' }, 404);

  return c.json(result);
});

export default briefing;
```

- [ ] **Step 2: Register routes in index.ts**

Add import and route registration in `src/index.ts`:

```typescript
import briefing from './routes/briefing.js';
// ... after other app.route() calls:
app.route('/api/briefing', briefing);
```

- [ ] **Step 3: Build and verify**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm run build`
Expected: No errors

- [ ] **Step 4: Run all tests**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npx vitest run`
Expected: All tests PASS (existing + new)

- [ ] **Step 5: Commit**

```bash
git add src/routes/briefing.ts src/index.ts
git commit -m "feat: briefing API routes (POST analysis, GET latest, GET history, PUT rate)"
```

### Task 5: Deploy jimbo-api to VPS

**Files:**
- No file changes — deployment steps only

- [ ] **Step 1: Build**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm run build`

- [ ] **Step 2: Deploy to VPS**

```bash
rsync -av dist/ jimbo:/home/openclaw/jimbo-api/dist/
ssh jimbo 'cd /home/openclaw/jimbo-api && cp -r dist/* . && sudo systemctl restart jimbo-api'
```

- [ ] **Step 3: Add Caddy routes**

```bash
ssh jimbo 'sudo nano /etc/caddy/Caddyfile'
```

Add both routes (bare path + glob):
```
handle /api/briefing {
    reverse_proxy localhost:3100
}
handle /api/briefing/* {
    reverse_proxy localhost:3100
}
```

Then: `ssh jimbo 'sudo systemctl reload caddy'`

- [ ] **Step 4: Verify endpoints**

```bash
API_KEY="7e37e4ae1650b6ebc2a925b918924d80"

# Should return 404 (no data yet)
curl -sk -H "X-API-Key: $API_KEY" "https://167.99.206.214/api/briefing/latest"

# Should return 201
curl -sk -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"session":"morning","model":"test","generated_at":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","day_plan":[{"time":"09:00","suggestion":"test","source":"test","reasoning":"test"}]}' \
  "https://167.99.206.214/api/briefing/analysis"

# Should return the test analysis
curl -sk -H "X-API-Key: $API_KEY" "https://167.99.206.214/api/briefing/latest"

# Should return history
curl -sk -H "X-API-Key: $API_KEY" "https://167.99.206.214/api/briefing/history?limit=5"
```

- [ ] **Step 5: Commit deployment verification**

No code to commit — just verify the deploy succeeded.

---

## Chunk 2: opus-briefing.sh + Opus Prompts

### Task 6: Update opus-briefing.sh to POST to API

**Files:**
- Modify: `/Users/marvinbarretto/development/openclaw/scripts/opus-briefing.sh`

- [ ] **Step 1: Read the current script**

Read `scripts/opus-briefing.sh` to confirm current state.

- [ ] **Step 2: Rewrite the script**

Replace the full script with error logging and API POST:

```bash
#!/bin/bash
set -euo pipefail

# Opus briefing analysis — runs on Mac, pulls data from VPS, pushes analysis to jimbo-api.
# Logs errors to stderr (visible in launchd logs). Sends Telegram alert on failure.

SESSION="${1:-morning}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPT_DIR="$(dirname "$SCRIPT_DIR")/opus-prompts"

# Required env vars
: "${JIMBO_API_KEY:?JIMBO_API_KEY not set}"
API_URL="https://167.99.206.214/api"

send_alert() {
    local msg="$1"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d text="[opus-briefing] $msg" \
            -d parse_mode=HTML >/dev/null 2>&1 || true
    fi
}

if [ ! -f "$PROMPT_DIR/${SESSION}.md" ]; then
    echo "ERROR: Unknown session: $SESSION" >&2
    exit 1
fi

# Pull briefing-input.json from VPS
echo "Pulling briefing-input.json for $SESSION..." >&2
INPUT=$(ssh jimbo 'cat /home/openclaw/.openclaw/workspace/briefing-input.json' 2>/dev/null) || {
    echo "ERROR: Failed to pull briefing-input.json" >&2
    send_alert "Failed to pull briefing-input.json from VPS"
    exit 1
}
[ -z "$INPUT" ] && { echo "ERROR: briefing-input.json is empty" >&2; send_alert "briefing-input.json is empty"; exit 1; }

# Check it's for the right session
INPUT_SESSION=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session',''))" 2>/dev/null) || {
    echo "ERROR: Failed to parse session from input" >&2; exit 1
}
if [ "$INPUT_SESSION" != "$SESSION" ]; then
    echo "Input session ($INPUT_SESSION) doesn't match requested ($SESSION), skipping" >&2
    exit 0
fi

# Check it's fresh (less than 10 hours old)
IS_FRESH=$(echo "$INPUT" | python3 -c "
import sys, json, datetime
d = json.load(sys.stdin)
gen = datetime.datetime.fromisoformat(d['generated_at'])
if gen.tzinfo is None:
    gen = gen.replace(tzinfo=datetime.timezone.utc)
age = (datetime.datetime.now(datetime.timezone.utc) - gen).total_seconds()
print('yes' if age < 36000 else 'no')
" 2>/dev/null) || { echo "ERROR: Failed to check freshness" >&2; exit 1; }

if [ "$IS_FRESH" != "yes" ]; then
    echo "briefing-input.json is stale, skipping" >&2
    exit 0
fi

# Run Opus analysis
echo "Running Opus analysis for $SESSION..." >&2
PROMPT=$(cat "$PROMPT_DIR/${SESSION}.md")
ANALYSIS=$(echo "$INPUT" | claude -p "$PROMPT" 2>/dev/null) || {
    echo "ERROR: claude -p failed" >&2
    send_alert "Opus analysis failed (claude -p error) for $SESSION"
    exit 1
}

# Validate JSON
echo "$ANALYSIS" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'day_plan' in d" 2>/dev/null || {
    echo "ERROR: Opus output is not valid JSON or missing day_plan" >&2
    send_alert "Opus output validation failed for $SESSION"
    exit 1
}

# POST to jimbo-api
echo "Posting analysis to jimbo-api..." >&2
HTTP_CODE=$(echo "$ANALYSIS" | curl -sk -o /dev/null -w '%{http_code}' \
    -X POST \
    -H "X-API-Key: $JIMBO_API_KEY" \
    -H "Content-Type: application/json" \
    -d @- \
    "$API_URL/briefing/analysis") || {
    echo "ERROR: Failed to POST to jimbo-api" >&2
    send_alert "Failed to POST analysis to jimbo-api for $SESSION"
    exit 1
}

if [ "$HTTP_CODE" != "201" ]; then
    echo "ERROR: jimbo-api returned $HTTP_CODE" >&2
    send_alert "jimbo-api returned HTTP $HTTP_CODE for $SESSION analysis POST"
    exit 1
fi

echo "Opus analysis posted for $SESSION session (HTTP $HTTP_CODE)" >&2
```

- [ ] **Step 3: Test locally (dry run)**

```bash
# Verify script parses without errors
bash -n scripts/opus-briefing.sh

# Test with missing env var (should error)
unset JIMBO_API_KEY 2>/dev/null; bash scripts/opus-briefing.sh morning 2>&1 | head -1
# Expected: "JIMBO_API_KEY not set"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/opus-briefing.sh
git commit -m "feat: opus-briefing.sh posts to jimbo-api, adds error logging + alerts"
```

### Task 7: Update Opus prompts

**Files:**
- Modify: `/Users/marvinbarretto/development/openclaw/opus-prompts/morning.md`
- Modify: `/Users/marvinbarretto/development/openclaw/opus-prompts/afternoon.md`

- [ ] **Step 1: Update morning.md output schema**

In `opus-prompts/morning.md`, replace the output schema block (lines 22-49) with:

```json
{
  "generated_at": "ISO timestamp",
  "session": "morning",
  "model": "your model name",
  "day_plan": [
    {
      "time": "HH:MM-HH:MM",
      "suggestion": "what to do",
      "source": "calendar|vault|gems|priorities",
      "reasoning": "one sentence why this fits here"
    }
  ],
  "email_highlights": [
    {
      "source": "sender or newsletter name",
      "headline": "specific article, event, or deal title",
      "editorial": "one sentence connecting to Marvin's context — be specific and confident",
      "links": ["url1"]
    }
  ],
  "surprise": {
    "fact": "the surprising connection or find",
    "strategy": "how you found it"
  },
  "vault_tasks": [
    {
      "title": "task name from pipeline",
      "priority": 10,
      "actionability": "clear|vague|needs-breakdown",
      "note": "one sentence on why this matters today or how it connects"
    }
  ]
}
```

Also add to the Rules section:
```
- For vault_tasks, pass through the pipeline's selected tasks. Add a `note` explaining why each matters today — connect to calendar events, email content, or priorities where possible.
```

- [ ] **Step 2: Update afternoon.md**

In `opus-prompts/afternoon.md`, replace the output schema (lines 25-52) with the same schema as morning but with `"session": "afternoon"`.

Replace the rule on line 17:
```
Old: - editorial_voice should acknowledge the day so far, not just the remaining hours.
New: - For vault_tasks, pass through the pipeline's selected tasks. Add a `note` explaining why each matters in the remaining hours.
```

- [ ] **Step 4: Commit**

```bash
git add opus-prompts/morning.md opus-prompts/afternoon.md
git commit -m "feat: opus prompts drop editorial_voice, add vault_tasks schema"
```

### Task 8: Set Mac env vars for opus-briefing.sh

**Files:**
- Modify: `/Users/marvinbarretto/development/openclaw/scripts/com.marvin.opus-briefing.morning.plist`
- Modify: `/Users/marvinbarretto/development/openclaw/scripts/com.marvin.opus-briefing.afternoon.plist`

- [ ] **Step 1: Read current plist files**

Read both plist files to see the current EnvironmentVariables section.

- [ ] **Step 2: Add env vars to both plists**

Add to the `EnvironmentVariables` dict in each plist:
- `JIMBO_API_KEY` — value: `7e37e4ae1650b6ebc2a925b918924d80`
- `TELEGRAM_BOT_TOKEN` — value: read from VPS (`ssh jimbo 'grep TELEGRAM_BOT_TOKEN /opt/openclaw.env'`)
- `TELEGRAM_CHAT_ID` — value: read from VPS (`ssh jimbo 'grep TELEGRAM_CHAT_ID /opt/openclaw.env'`)

- [ ] **Step 3: Reload launchd agents**

```bash
launchctl unload ~/Library/LaunchAgents/com.marvin.opus-briefing.morning.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.marvin.opus-briefing.morning.plist
launchctl unload ~/Library/LaunchAgents/com.marvin.opus-briefing.afternoon.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.marvin.opus-briefing.afternoon.plist
```

- [ ] **Step 4: Commit**

```bash
git add scripts/com.marvin.opus-briefing.morning.plist scripts/com.marvin.opus-briefing.afternoon.plist
git commit -m "feat: add API key and Telegram env vars to launchd plists"
```

---

## Chunk 3: Daily Briefing Skill Rewrite

### Task 9: Rewrite the daily-briefing skill

**Files:**
- Modify: `/Users/marvinbarretto/development/openclaw/skills/daily-briefing/SKILL.md`

- [ ] **Step 1: Read the current skill**

Read `skills/daily-briefing/SKILL.md` to confirm current state.

- [ ] **Step 2: Replace with new step-by-step skill**

```markdown
---
name: daily-briefing
description: Deliver the morning or afternoon briefing from Opus analysis via jimbo-api
user-invokable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or it's a scheduled briefing session.

## Step 1: Fetch today's briefing

Run in the sandbox:

```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/briefing/latest"
```

- If the curl fails entirely (connection refused, timeout): say "jimbo-api is down. I can still check your calendar and email directly — want me to?"
- If it returns 404: say "Opus hasn't run yet today. I can check your calendar and top vault tasks if you'd like."
- If it returns data: parse the JSON and continue.

## Step 2: Deliver the briefing

Walk through the analysis **one section at a time**. Send each as a separate message. Use your own voice — be conversational, not robotic.

1. **Day plan** — present the time blocks with suggestions and reasoning. Flag anything in the next 2 hours.
2. **Email highlights** — present each pick with WHY it matters. Skip if the array is empty.
3. **Surprise** — present the connection/find. Skip if null.
4. **Vault tasks** — present priority tasks with Opus's notes on why they matter today. If `triage_pending > 0` in briefing-input.json, announce: "I picked up N tasks that need your input. When's good for a 15-min triage?"

After delivering, ask: "Anything you'd swap or skip?"

## Step 3: Log delivery

Run both in the sandbox:

```bash
curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  -d '{"task_type":"briefing","description":"<Morning|Afternoon> briefing delivered (opus-assisted)","outcome":"success"}' \
  "$JIMBO_API_URL/api/activity"

curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  -d '{"task":"briefing-synthesis","model":"<your-model>","input_tokens":0,"output_tokens":0,"config_hash":"opus-assisted","notes":"{\"mode\":\"opus-assisted\",\"session\":\"<morning|afternoon>\"}"}' \
  "$JIMBO_API_URL/api/experiments"
```

## Step 4: Stay available

You are now in conversation. Marvin may ask follow-ups. Use your sandbox tools:

- **"Tell me more about [email]"** → `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/emails/reports"` and find the relevant report
- **"Add that to my calendar"** → `python3 /workspace/calendar-helper.py create-event --summary "..." --start ... --end ...`
- **"Check conflicts at 3pm"** → `python3 /workspace/calendar-helper.py check-conflicts --start ... --end ...`
- **"What vault tasks are urgent?"** → `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes?status=active&sort=priority&limit=10"`
- **"Remind me at 3pm about X"** → `python3 /workspace/calendar-helper.py create-event --summary "Reminder: X" --start 2026-03-16T15:00:00 --end 2026-03-16T15:15:00`
```

- [ ] **Step 3: Commit**

```bash
git add skills/daily-briefing/SKILL.md
git commit -m "feat: rewrite daily-briefing skill as step-by-step API-driven agent"
```

### Task 10: Deploy skill to VPS

**Files:**
- No file changes — deployment only

- [ ] **Step 1: Push skill to VPS**

```bash
cd /Users/marvinbarretto/development/openclaw
./scripts/skills-push.sh
```

- [ ] **Step 2: Verify skill is on VPS**

```bash
ssh jimbo 'cat /home/openclaw/.openclaw/workspace/skills/daily-briefing/SKILL.md | head -5'
```
Expected: should show the new frontmatter

---

## Chunk 4: End-to-End Verification

### Task 11: Manual end-to-end test

- [ ] **Step 1: Post today's Opus analysis to the API manually**

Pull today's analysis that's already on VPS and POST it:

```bash
API_KEY="7e37e4ae1650b6ebc2a925b918924d80"
ssh jimbo 'cat /home/openclaw/.openclaw/workspace/briefing-analysis.json' | \
  curl -sk -X POST \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d @- \
    "https://167.99.206.214/api/briefing/analysis"
```

Expected: HTTP 201 with the stored analysis

- [ ] **Step 2: Verify GET latest works**

```bash
curl -sk -H "X-API-Key: $API_KEY" "https://167.99.206.214/api/briefing/latest" | python3 -m json.tool | head -20
```

Expected: returns today's analysis with id, session, analysis object

- [ ] **Step 3: Test opus-briefing.sh posts correctly**

Set env vars and run manually:

```bash
export JIMBO_API_KEY="7e37e4ae1650b6ebc2a925b918924d80"
# Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID if available
bash scripts/opus-briefing.sh morning
```

Expected: "Opus analysis posted for morning session (HTTP 201)" — or "stale/wrong session" if the input data is old.

- [ ] **Step 4: Message Jimbo on Telegram**

Send "briefing?" or "good morning" on Telegram. Verify Jimbo:
1. Fetches from the API (not from files)
2. Delivers section by section
3. Responds to follow-up questions

This is the live test. Note any issues for the next review session.

- [ ] **Step 5: Final commit — review entry + history update**

```bash
cd /Users/marvinbarretto/development/openclaw
git add docs/reviews/2026-03-16.md docs/reviews/HISTORY.md docs/superpowers/specs/2026-03-16-briefing-api-delivery-design.md
git commit -m "docs: session 7 review, briefing API delivery spec"
```
