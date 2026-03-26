# Dispatch Flow Split — Commissions, Quests, and Recon

**Date:** 2026-03-26
**Status:** Design — awaiting review
**Depends on:** jimbo-api (dispatch service, vault service, webhooks), M2 dispatch worker, GitHub API, gh-issue skill
**Builds on:** 2026-03-25-autonomous-dispatch-design.md, 2026-03-26-dispatch-pr-feedback-loop-design.md

## Problem

The dispatch system has working machinery (queue, worker, templates, PR feedback loop, vault scoring) but no work flowing through it. Three disconnected systems each hold part of the picture:

1. **The vault** — 1,600+ scored tasks, but code tasks sit alongside life tasks. Vault notes are underspecified for agent dispatch (thin acceptance criteria, no file references, no scope boundaries).
2. **GitHub Issues + Project boards** — well-structured issues with labels (`ralph` for agents, `human` for Marvin), priorities, milestones, and acceptance criteria. Already a functioning commission tracker. But dispatch doesn't read from GitHub.
3. **The `gh-issue` skill** — creates rich issues with problem statements, expected behaviour, file references, scope, and agent-suitability assessments. But issues it creates have zero connection to dispatch or the vault.

The result: dispatch sits hungry with nothing to eat. The vault is cluttered with code tasks that belong on GitHub. Issues exist but can't trigger dispatch. The loop is open.

## Design Principles

1. **The vault is your world.** Personal tasks, ideas, research requests, life admin. Not a code backlog.
2. **GitHub is the codebase's world.** Issues, PRs, project boards. Code lives here.
3. **Dispatch bridges both** — pulls commissions from GitHub, pulls recon from the vault.
4. **No duplication.** A task lives in one place. No syncing vault tasks to issues or vice versa.
5. **Agent type determines HOW. Flow determines WHAT.** `agent_type` picks the template. `flow` picks the delivery contract.

## The Three Flows

### Commission

Work you hand off to agents. The artifact is code (or code-adjacent config, migrations, etc.).

- **Source:** GitHub Issues labeled `ralph` on target repos
- **Spec session:** ~1hr/day, you brain-dump via `gh-issue` skill, issues land on project board
- **Dispatch:** proposes batches from `ralph`-labeled issues matching readiness criteria
- **Agent types:** coder (primary), occasionally researcher (e.g. "find all uses of deprecated API X")
- **Delivery:** PR linked to issue
- **Review:** GitHub PR review
- **Completion:** PR merge closes issue automatically (via `closes #N` in PR body), webhook updates dispatch queue
- **Your role:** commissioner + reviewer

```
brain dump → gh-issue skill → GitHub Issue (ralph label)
  → dispatch proposes → Marvin approves
  → agent executes → PR (with "Closes #N")
  → Marvin reviews PR → merge
  → webhook: dispatch=done, issue closed, project board → Done
```

### Quest

Things only you can do. Physical errands, relationship tasks, creative decisions, emotional work, complex judgment calls.

- **Source:** Vault (scored by prioritise-tasks.py)
- **Not dispatched.** Surfaced in briefings, nudged by Jimbo, tracked in vault.
- **Agent support:** Jimbo can gather context, send reminders, prep materials — but can't complete the quest.
- **Delivery:** You do the thing. Mark done in vault.
- **Your role:** the protagonist

```
vault task (quest) → briefing surfaces it → you do it → vault done
```

### Recon

Intelligence-gathering that feeds decisions. Research, comparisons, landscape scans, option analysis.

- **Source:** Vault (flow=recon, scored by prioritise-tasks.py)
- **Dispatch:** proposes from vault, same as today
- **Agent types:** researcher, drafter
- **Delivery:** Artifact committed directly to target repo + Telegram notification with summary
- **Review:** You read it when you want. No PR gate.
- **Completion:** Agent completion marks vault task done. If output is garbage, you re-dispatch or discard.
- **Your role:** reader + decision-maker
- **Often spawns new work:** recon output may generate commissions (new issues) or inform quests

```
vault task (recon) → dispatch proposes → Marvin approves
  → agent executes → artifact committed + Telegram notification
  → dispatch=done, vault=done
  → Marvin reads → maybe creates issues (commissions) or vault tasks (quests)
```

## Implementation

### 1. New field: `flow` on dispatch_queue

```sql
ALTER TABLE dispatch_queue ADD COLUMN flow TEXT NOT NULL DEFAULT 'commission';
```

Valid values: `'commission'` | `'recon'`

Quests are never dispatched, so they don't appear in the queue.

`flow` determines the delivery contract. `agent_type` determines the template. These are independent axes:

| flow | agent_type | delivery |
|------|-----------|----------|
| commission | coder | PR + issue link |
| commission | researcher | PR + issue link (rare, e.g. codebase audit) |
| recon | researcher | Artifact + notify |
| recon | drafter | Artifact + notify |

### 2. New field: `issue_number` and `issue_repo` on dispatch_queue

```sql
ALTER TABLE dispatch_queue ADD COLUMN issue_number INTEGER;
ALTER TABLE dispatch_queue ADD COLUMN issue_repo TEXT;
```

Populated for commissions. Null for recon. Used to:
- Include issue body in the agent prompt (richer context than vault acceptance_criteria)
- Add `Closes #N` to PR body (auto-close on merge)
- Track the full issue → dispatch → PR → close lifecycle

### 3. GitHub Issue source for commissions

New service method: `proposeFromGitHub(repos: string[], batchSize: number)`

```
1. For each repo, call GitHub API:
   GET /repos/{owner}/{repo}/issues?labels=ralph&state=open&sort=created&direction=asc
2. Filter out issues already in dispatch_queue (by issue_number + issue_repo)
3. Rank by priority labels (P0 > P1 > P2 > P3) and milestone
4. Take top N for the batch
5. Insert into dispatch_queue with:
   - task_source = 'github'
   - flow = 'commission'
   - task_id = '{repo}#{issue_number}' (composite key)
   - issue_number, issue_repo populated
   - agent_type inferred from labels (default: coder)
```

Priority label mapping (from existing project board conventions):
- `P0-blocks-launch` → highest
- `P1-before-launch` → high
- `P2: Soon` → medium
- No priority label → low

Agent type inference from labels:
- `infrastructure`, `bug`, default → coder
- `research` → researcher
- `ralph` without other type hints → coder

### 4. Commission prompt assembly

When the worker picks up a commission, instead of reading vault acceptance_criteria, it fetches the GitHub issue body:

```
1. GET /repos/{issue_repo}/issues/{issue_number}
2. Extract: title, body (contains Problem, Expected behaviour, Acceptance criteria, Context, Scope)
3. Assemble prompt: {agent template} + {issue body as context} + {rejection feedback if retry} + {output contract}
```

The issue body from `gh-issue` is already structured with exactly the context agents need. No transformation required.

### 5. Commission output contract update

The existing `_output-contract.md` stays as the commission contract. One addition to the PR body template:

```markdown
Closes {issue_repo}#{issue_number}
```

This line in the PR body triggers GitHub's auto-close behaviour. When the PR merges, the issue closes automatically. No webhook needed for issue closure — GitHub handles it natively.

### 6. Recon output contract (new file)

New file: `workspace/dispatch/templates/_recon-contract.md`

```markdown
# Recon Output Contract

Every recon task follows this contract. Your agent-specific template tells you HOW
to do the work. This contract tells you how to DELIVER it.

## Output

1. Clone the target repo and checkout main (or default branch)
2. Write your output to the specified output path
3. Commit with conventional commit: `docs: {title}`
4. Push directly to main

Do NOT create a branch. Do NOT open a PR. Commit directly.

## Result JSON

Write your result to `/tmp/dispatch-{task_id}.result` as JSON:

### On completion:
{
  "status": "completed",
  "summary": "2-3 sentence summary of findings/output",
  "artifact_path": "path/to/output/file.md",
  "repo": "owner/repo",
  "commit_sha": "abc123"
}

### On blocked:
{
  "status": "blocked",
  "summary": "What prevented completion",
  "blockers": ["Specific reason 1"]
}

## Rules

- NEVER ask for user input — you are autonomous
- Commit directly to main — no branch, no PR
- If you cannot complete, use blocked status
```

### 7. Worker prompt assembly branching

The dispatch worker checks `flow` to decide which contract to use:

```
if flow === 'commission':
  contract = read('_output-contract.md')        // PR contract
  context = fetch issue body from GitHub API     // rich context
else if flow === 'recon':
  contract = read('_recon-contract.md')          // direct commit contract
  context = vault task acceptance_criteria       // existing behaviour
```

Template selection still uses `agent_type` as today.

### 8. Recon completion: Telegram notification

When a recon task completes (worker receives result JSON), in addition to the existing `POST /dispatch/complete`, the worker sends a Telegram notification:

```
📄 Recon complete: {title}

{summary from result JSON}

📎 {repo}/{artifact_path}
```

This replaces the PR as the review surface. You see the summary in Telegram, open the file if you want the full output.

### 9. Vault changes: remove code tasks

Code tasks should be migrated out of the vault to GitHub Issues over time. No automated migration — they're different formats. Instead:

- Stop creating code-related vault tasks. Use `gh-issue` directly.
- Existing code vault tasks with `dispatch_status=ready` can be dispatched as-is (backwards compatible). As they complete, they leave the vault naturally.
- The vault scoring pipeline (`prioritise-tasks.py`) continues to score quest and recon tasks.

New vault field: `flow` — defaults to `quest`. Set to `recon` for research/draft tasks that should be dispatched.

### 10. proposeBatch changes

The existing `proposeBatch()` becomes the vault proposer (recon + legacy vault commissions).

New `proposeCommissions()` proposes from GitHub Issues.

The orchestrator calls both:

```
1. proposeCommissions(repos=['localshout-next'], batchSize=2)
2. proposeBatch(batchSize=1)  // vault recon tasks
3. Combine into one Telegram approval message
```

This keeps the single approval surface (one Telegram message per batch cycle) while pulling from both sources.

### 11. Briefing integration

Morning/afternoon briefings should pull from both worlds:

```
Commission status:
  → "3 PRs ready for review" (from dispatch_queue where flow=commission, pr_state=open)
  → "2 commissions in progress" (from dispatch_queue where flow=commission, status=running)
  → "5 ralph issues awaiting dispatch" (from GitHub API, ralph label, not in queue)

Quest priorities:
  → Top 3 vault tasks where flow=quest, scored by ai_priority (existing behaviour)

Recon:
  → "Recon on X landed overnight — {summary}" (from dispatch_queue where flow=recon, status=completed, completed recently)
```

## Lifecycle Diagrams

### Commission (full loop)

```
You brain-dump into gh-issue skill
  │
  ▼
GitHub Issue created (ralph label, on project board)
  │
  ▼
Orchestrator proposes commission batch → Telegram
  │
  ▼
You approve → dispatch_queue (flow=commission, task_source=github)
  │
  ▼
M2 worker picks up
  → Fetches issue body from GitHub API (rich context)
  → Loads coder template + PR output contract
  → Injects rejection feedback if retry
  → Spawns agent
  │
  ▼
Agent: branch dispatch/{repo}#{issue_number}
  → implements the work
  → PR with "Closes owner/repo#N"
  │
  ▼
You review PR
  ├── Merge → GitHub auto-closes issue
  │   → Webhook: dispatch pr_state=merged
  │   → Project board: issue moves to Done
  │
  └── Close with comment → Webhook: pr_state=rejected
      → rejection_reason captured
      → Issue stays open, available for re-dispatch
      → 24h cooldown, max 2 retries
```

### Recon (lightweight loop)

```
You create vault task (flow=recon, agent_type=researcher)
  │
  ▼
prioritise-tasks.py scores it → dispatch_status=ready
  │
  ▼
Orchestrator proposes recon batch → Telegram
  │
  ▼
You approve → dispatch_queue (flow=recon, task_source=vault)
  │
  ▼
M2 worker picks up
  → Loads researcher/drafter template + recon contract
  → Spawns agent
  │
  ▼
Agent: commits artifact directly to main
  → Telegram notification with summary
  │
  ▼
Vault task → done
You read when ready → maybe spawns new issues or quests
```

### Quest (no dispatch)

```
Vault task (flow=quest) scored by prioritise-tasks.py
  │
  ▼
Briefing surfaces it: "Top quest: {title}"
  │
  ▼
You do the thing
  │
  ▼
You mark done in vault (or Jimbo marks on your instruction)
```

## Your Daily Rhythm

| Time | Activity | System |
|------|---------|--------|
| Morning briefing | See priorities across all three flows | Jimbo briefing |
| ~1hr spec session | Brain-dump code tasks via gh-issue | gh-issue skill → GitHub |
| Background | Dispatch executes commissions + recon | M2 worker, automatic |
| Periodic | Review commission PRs (merge/reject) | GitHub |
| Vault time | Work on quests, fire off recon requests | Vault + dispatch |
| Overnight | Recon artifacts land, ready for morning | M2 worker + Telegram |

## Migration Path

### Phase 1: Wire up GitHub as commission source
- Add `flow`, `issue_number`, `issue_repo` columns to dispatch_queue
- Implement `proposeFromGitHub()` in dispatch service
- Update worker to fetch issue body for commission prompts
- Add `Closes #N` to PR output contract
- Test with one `ralph` issue end-to-end

### Phase 2: Add recon contract
- Create `_recon-contract.md`
- Add flow field to vault_notes
- Update worker to branch on flow for contract selection
- Add Telegram notification for recon completion
- Test with one recon task end-to-end

### Phase 3: Briefing integration
- Update briefing to show commission/quest/recon status
- Pull open `ralph` issues count from GitHub API
- Show recent recon completions with summaries

### Phase 4: Vault cleanup (gradual, manual)
- Stop creating code vault tasks
- Existing code tasks in vault complete naturally through dispatch
- Vault becomes purely quests + recon + ideas

## Schema Summary

### dispatch_queue additions

```sql
ALTER TABLE dispatch_queue ADD COLUMN flow TEXT NOT NULL DEFAULT 'commission';
ALTER TABLE dispatch_queue ADD COLUMN issue_number INTEGER;
ALTER TABLE dispatch_queue ADD COLUMN issue_repo TEXT;
```

### vault_notes addition

```sql
ALTER TABLE vault_notes ADD COLUMN flow TEXT NOT NULL DEFAULT 'quest';
```

Valid values: `'quest'` | `'recon'`

(Commissions don't live in the vault — they live in GitHub.)

### New env vars

None required beyond existing `GITHUB_TOKEN` (already needed for PR feedback loop).

## Open Questions

| Question | Proposed Answer | Confidence |
|----------|----------------|------------|
| Should recon artifacts go to `hub` repo or a dedicated repo? | hub (already set up with docs/research/, docs/drafts/) | High |
| Should the orchestrator propose commissions and recon separately or in one batch? | One combined batch — simpler approval surface | Medium |
| What if a `ralph` issue has no acceptance criteria? | Skip it in proposal — DoR gate requires issue body to contain "Acceptance criteria" | High |
| Should recon completion update a GitHub project board? | No — recon lives in the vault, not GitHub | High |
| Should `gh-issue` auto-label issues as `ralph`? | It already assesses agent-suitability and adds the label — no change needed | High |
| Can a recon output auto-create commission issues? | Not in v1 — recon notifies you, you decide what to do with it | High |
| Direct commit to main for recon — is that safe? | Yes for docs/research/ and docs/drafts/ — no CI, no production impact | High |
