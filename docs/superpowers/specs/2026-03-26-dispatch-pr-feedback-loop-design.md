# Dispatch PR Feedback Loop — Full Implementation Design

**Date:** 2026-03-26
**Status:** Approved design — ready for implementation
**Depends on:** jimbo-api (dispatch service, vault service), M2 dispatch worker, GitHub webhooks, Cloudflare R2
**Builds on:** 2026-03-26-dispatch-pr-model.md (design decision), 2026-03-25-autonomous-dispatch-design.md (original spec)

## Overview

Complete the dispatch PR model by implementing: GitHub webhook feedback loop, centralised template output contract, subtask rollup with notification, R2 evidence pipeline, and rejection-reason capture for retry prompts. After this work, every dispatch task — regardless of agent type — follows one lifecycle: branch → work → evidence → PR → review → vault update.

## 1. GitHub Webhook → jimbo-api Feedback Loop

### Webhook Route

New route: `POST /webhooks/github` (outside `/api/*` — GitHub uses its own HMAC auth, not X-API-Key)

- Sits **outside** the `X-API-Key` middleware (GitHub signs via `X-Hub-Signature-256`)
- Validates HMAC-SHA256 signature using `GITHUB_WEBHOOK_SECRET` env var
- Accepts `pull_request` events only, ignores all other event types
- Responds 200 immediately, processes asynchronously if needed

### PR → Task Matching

Two-step lookup:

1. **Primary:** Match incoming `pull_request.html_url` against `dispatch_queue.pr_url`
2. **Fallback:** Extract task_id from head branch name (`dispatch/{task_id}`) and match against `dispatch_queue.task_id`

If neither matches, log and ignore — it's a non-dispatch PR.

### Event Mapping

| GitHub action | `dispatch_queue` update | `vault_notes` update |
|---|---|---|
| `opened` | Store `pr_url` if not set, `pr_state: open` | No change |
| `closed` + `merged=true` | `pr_state: merged` | `status: done`, `dispatch_status: done`, `completed_at: now` |
| `closed` + `merged=false` | `pr_state: rejected`, fetch + store `rejection_reason` | `status: active`, `dispatch_status: needs_grooming` |
| `reopened` | `pr_state: open` | `status: active`, `dispatch_status: running` |

### Rejection Reason Capture

On `closed + not merged`:

1. Call GitHub API: `GET /repos/{owner}/{repo}/issues/{number}/comments` (issue-level comments, not review diff comments — we want the top-level closing comment, not inline code review notes)
2. Take the most recent comment body as `rejection_reason`
3. If no comments, `rejection_reason` remains null

No special comment format required — just close with a comment explaining why.

### Schema Additions

Add to `dispatch_queue` table:

```sql
ALTER TABLE dispatch_queue ADD COLUMN pr_url TEXT;
ALTER TABLE dispatch_queue ADD COLUMN pr_state TEXT;
ALTER TABLE dispatch_queue ADD COLUMN rejection_reason TEXT;
```

Wrapped in try/catch for idempotent migration (existing pattern in db/index.ts).

### Webhook Configuration

Per-repo webhooks on:
- `localshout-next` (coder tasks)
- `hub` (researcher + drafter tasks)
- Future dispatch target repos as needed

Settings per webhook:
- URL: `https://167.99.206.214/webhooks/github`
- Content type: `application/json`
- Secret: value of `GITHUB_WEBHOOK_SECRET`
- Events: Pull requests only

### New Env Vars

On VPS (jimbo-api):
- `GITHUB_WEBHOOK_SECRET` — shared secret for webhook signature validation
- `GITHUB_TOKEN` — PAT for fetching PR comments on rejection (can reuse existing token if scoped appropriately)

## 2. Centralised Template Output Contract

### Problem

Currently only `coder.md` mandates push + PR. Adding the same rules to every new template is error-prone and creates drift.

### Solution

Split templates into two layers:

**Shared output contract** — `workspace/dispatch/templates/_output-contract.md`:
- Branch naming: `dispatch/{task_id}`
- Commit conventions (conventional commits)
- Push + `gh pr create` using pr-format.md structure
- Result JSON schema (required fields: `status`, `summary`, `pr_url`, `branch`)
- Screenshot/video rules (when applicable)
- R2 upload rules (when applicable)
- Blocked state handling: `{ status: 'blocked', blockers[] }`

**Agent-specific templates** — `workspace/dispatch/templates/{type}.md`:
- Only describe HOW to do the work (what to read, what to produce, quality criteria)
- Reference the output contract: "Follow the output contract in _output-contract.md for branching, PR, and evidence."

### Template Rendering

The dispatch worker assembles the full prompt as:

```
{agent_type template contents}

---

{_output-contract.md contents}
```

Concatenation at render time. No include/import system needed — the worker reads both files and joins them.

### Adding New Agent Types

To add a new agent type:
1. Create `workspace/dispatch/templates/{new-type}.md` — describe the work method only
2. Add the type to `AGENT_TYPE_CONFIG` in jimbo-api with model/timeout/fallback
3. Done — output contract, PR format, evidence pipeline all inherited

## 3. Researcher & Drafter Template Updates

### Researcher Template

Rewrite to follow the new structure:

- **Work method:** Search web, compare sources, cite URLs, synthesise findings
- **Output location:** `docs/research/{topic-slug}.md` in the hub repo
- **Target repo:** `hub` (default), overridable via `dispatch_repo`
- PR, branching, evidence all handled by output contract

### Drafter Template

Rewrite to follow the new structure:

- **Work method:** Research topic, match Marvin's voice (opinionated, direct, funny), write content
- **Output location:** `docs/drafts/{topic-slug}.md` (hub) or `src/content/posts/{slug}.md` (site)
- **Target repo:** `hub` (default) or `site`, set via `dispatch_repo`
- PR, branching, evidence all handled by output contract

### Hub Repo Initialisation

One-time setup in `hub` repo:

- Create `docs/research/.gitkeep`
- Create `docs/drafts/.gitkeep`
- Create `docs/lists/.gitkeep`
- Update `hub/CLAUDE.md` to explain:
  - Hub receives non-code dispatch outputs
  - `docs/research/` — research outputs, comparisons, analysis
  - `docs/drafts/` — content drafts, blog posts, documentation
  - `docs/lists/` — curated URL lists, tool comparisons, reference material
  - All work arrives as PRs from `dispatch/{task_id}` branches

## 4. Subtask Rollup

### Trigger

When the webhook handler updates a vault task to `status: done` (PR merged), it checks if the task has a `parent_id`.

### Rollup Logic

New vault service method: `checkSubtaskRollup(parentId: string)`

```
1. Query all vault_notes where parent_id = parentId
2. Query the parent note itself
3. Return { allDone: boolean, children: NoteWithStatus[], parent: Note }
```

If `allDone === true`:
- Send Telegram notification (see format below)
- Do NOT auto-close the parent — Marvin reviews first

If not all done:
- Silent, no action

### Telegram Notification

```
✅ All subtasks complete for: {parent_title}

• {child_1_title} — PR merged ✓
• {child_2_title} — PR merged ✓
• {child_3_title} — PR merged ✓

Ready to close the parent? Mark done in vault or reply here.
```

### API Support

New endpoint: `GET /api/vault/notes/:id/children`

Returns the note's children with their statuses, dispatch info, and PR URLs. Powers:
- Site UI (vault dashboard) — show parent with children, "ready to close" badge
- Telegram — Jimbo can check children status on command

### Parent Management Surfaces

**Telegram:** Jimbo recognises "close {task_id}" or similar commands during conversation. Uses existing vault update API.

**Site UI:** Parent tasks with all children done show a visual indicator in the vault view at `/app/jimbo/vault`. One-click close action.

Both use `PATCH /api/vault/notes/:id` with `{ status: 'done' }` — no new endpoint needed for the close action.

## 5. R2 Screenshot & Video Evidence Pipeline

### R2 Setup

- Bucket: `dispatch-evidence` on existing Cloudflare account
- Public access enabled (same pattern as localshout-next's `localshout-images` bucket)
- Public URL: `https://{R2_DISPATCH_PUBLIC_URL}/{path}`

### M2 Env Vars

```
R2_DISPATCH_ACCOUNT_ID=...
R2_DISPATCH_ACCESS_KEY_ID=...
R2_DISPATCH_SECRET_ACCESS_KEY=...
R2_DISPATCH_BUCKET_NAME=dispatch-evidence
R2_DISPATCH_PUBLIC_URL=https://dispatch-evidence.{domain}
```

### Agent Capture Flow (defined in output contract)

For tasks with visual changes:

1. Checkout `main`, start dev server
2. Playwright `page.screenshot()` on affected pages → `before.png`
3. Checkout feature branch, start dev server
4. Same pages → `after.png`
5. For interactive changes: `browserContext.newPage()` with `recordVideo: { dir: '/tmp/dispatch-{task_id}/' }` → `demo.webm`
6. Upload to R2 via S3-compatible API: `{task_id}/before.png`, `{task_id}/after.png`, `{task_id}/demo.webm`
7. Embed public URLs in PR body

### When to Capture

- Coder tasks touching UI → screenshots mandatory, video if interactive (keyboard, hover, animation)
- Coder tasks that are backend-only → skip, note "N/A — no visual changes" in PR
- Researcher/drafter → skip (markdown output, no visual)

The output contract makes this conditional: "If your changes affect UI, capture evidence. If not, skip and note why."

### Fallback

If R2 upload fails (missing creds, network error):
- Commit screenshots to `.dispatch/screenshots/` on the branch
- Note the fallback in the PR body: "Screenshots committed to branch (R2 upload failed)"
- PR is not blocked

## 6. Rejection Feedback in Retry Prompts

### Flow

When a rejected task is re-groomed and re-dispatched:

1. Dispatch worker picks up the task from the queue
2. Before rendering the prompt, queries dispatch history: `GET /api/dispatch/queue?task_id={task_id}&status=rejected`
3. If previous rejections exist, injects into the prompt:

```
---
PREVIOUS ATTEMPT FEEDBACK

This task was attempted before and the PR was rejected.
Reviewer feedback: {rejection_reason}

Learn from this feedback and adjust your approach accordingly.
---
```

4. This block is inserted between the agent template and the output contract

### API Support

The existing `GET /api/dispatch/queue?task_id=X&status=rejected` endpoint already returns history filtered by task_id and status. The `rejection_reason` field (new column) will be included in the response. No new endpoint needed.

## 7. Complete Task Lifecycle

```
Vault task (status: active, dispatch_status: ready)
  │
  ▼
VPS Orchestrator proposes batch → Telegram notification
  │
  ▼
Marvin approves (Telegram or API)
  │
  ▼
M2 Worker picks up task
  → Loads agent template + output contract
  → Injects rejection feedback if retry
  → Spawns Claude Code agent
  │
  ▼
Agent executes:
  1. Clone repo, branch dispatch/{task_id}
  2. Do the work (code / research / draft)
  3. Playwright evidence (if visual)
  4. Upload to R2 (if visual)
  5. Commit, push, gh pr create
  6. Write result JSON with pr_url
  │
  ▼
M2 Worker collects result → POST /dispatch/complete
  → jimbo-api stores pr_url on dispatch_queue
  │
  ▼
GitHub webhook (PR opened) → jimbo-api
  → Matches PR → task, stores pr_state: open
  │
  ▼
Marvin reviews PR
  ├── Merge → webhook → pr_state: merged
  │   → vault: done
  │   → Subtask rollup check → Telegram if all siblings done
  │
  ├── Close with comment → webhook → pr_state: rejected
  │   → Fetch rejection_reason from last comment
  │   → vault: active, needs_grooming
  │   → Rejection reason available for next dispatch attempt
  │
  └── Request changes → no webhook action, PR stays open
```

## Implementation Summary

### jimbo-api changes
- Schema: 3 new columns on `dispatch_queue` (`pr_url`, `pr_state`, `rejection_reason`)
- New route: `POST /webhooks/github` (outside `/api/*` — GitHub uses its own HMAC auth, not X-API-Key) with HMAC validation
- New route: `GET /api/vault/notes/:id/children`
- New service method: `checkSubtaskRollup(parentId)`
- Extend `completeTask()`: store `pr_url` from result
- Telegram notification helper for rollup messages

### openclaw changes
- New file: `workspace/dispatch/templates/_output-contract.md`
- Rewrite: `workspace/dispatch/templates/researcher.md` (add PR flow, reference output contract)
- Rewrite: `workspace/dispatch/templates/drafter.md` (add PR flow, reference output contract)
- Refactor: `workspace/dispatch/templates/coder.md` (extract shared rules to output contract)

### hub repo changes
- Create: `docs/research/.gitkeep`, `docs/drafts/.gitkeep`, `docs/lists/.gitkeep`
- Update: `CLAUDE.md` with dispatch context

### Cloudflare changes
- Create: `dispatch-evidence` R2 bucket with public access
- Generate: API credentials scoped to this bucket

### GitHub changes
- Configure: webhook on `localshout-next` (PR events → jimbo-api)
- Configure: webhook on `hub` (PR events → jimbo-api)

### M2 changes
- Env vars: R2 dispatch credentials

### VPS changes
- Env vars: `GITHUB_WEBHOOK_SECRET`, `GITHUB_TOKEN` (if not already available)

## Open Questions (Resolved)

| Question | Resolution |
|---|---|
| Webhook vs polling | Webhook (instant feedback, cleaner) |
| PR → task matching | pr_url primary, branch name fallback |
| Per-repo vs org webhook | Per-repo (user account, not org) |
| Subtask auto-close | No — Telegram notification, manual close |
| R2 vs commit screenshots | R2 primary, commit as fallback |
| Rejection comment format | No format required — grab last comment on close |
| Video support | Yes — Playwright recordVideo, upload .webm to R2 |
