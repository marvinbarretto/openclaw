# Dispatch Output Model: Everything Produces a PR

**Date:** 2026-03-26
**Status:** Design decision — captures evolution from original dispatch spec (2026-03-25)
**Depends on:** jimbo-api (vault, dispatch queue), M2 home station, GitHub repos
**Supersedes:** Agent type–specific output contracts from the original dispatch spec

## Context

The first dispatch test (localshout-next #193, 2026-03-26) revealed a gap: the coder agent implemented the change and committed, but didn't push or open a PR. The result was a local branch on M2 with no reviewable artifact and no approval/rejection flow.

This led to a broader design conversation: if coder tasks produce PRs, what do researcher and drafter tasks produce? How does Marvin approve or reject non-code work?

## Decision

**Every dispatch task, regardless of agent type, produces a Pull Request as its deliverable.**

The PR is the universal delivery mechanism, approval surface, and audit trail. The agent type determines *how* the agent works (template, timeout, tools), but the output contract is the same: branch → commit → push → PR → review.

## Rationale

### Why PRs for everything

1. **Forcing function for quality.** An agent that knows its output will be reviewed as a PR naturally structures its work better than one dumping text into a vault field.
2. **Rich feedback.** Research produces markdown files with chapters, comparisons, URLs. Drafts produce content files. These are better reviewed in GitHub's diff UI than in a Telegram message.
3. **Approval/rejection is built in.** Merge = approve. Close = reject. GitHub provides the workflow for free — comments, suggestions, re-requests.
4. **Audit trail.** Every dispatch task has a permanent, linkable record. PR history shows what was attempted, what was changed, and why it was accepted or rejected.
5. **One workflow.** No need to maintain separate approval flows for different agent types. Everything goes through the same pipeline.

### Agent type → repo mapping

| Agent type | Target repo | Output location | Example |
|-----------|-------------|----------------|---------|
| Coder | The relevant project repo (e.g. localshout-next) | Source code changes | Fix bottom nav keyboard hide |
| Researcher | hub | `docs/research/{topic}.md` | Compare YNAB vs Actual Budget |
| Drafter | site or hub (depending on content type) | `src/content/` or `docs/drafts/` | Draft blog post on AI governance |

### Hub as the non-code repo

The `hub` repo serves as the catch-all for non-code dispatch artifacts. To prevent it becoming a junk drawer:

- `docs/research/` — research outputs, comparisons, analysis
- `docs/drafts/` — content drafts, blog posts, documentation
- `docs/lists/` — curated URL lists, tool comparisons, reference material
- Branch naming: `dispatch/{task_id}` (same convention as code repos)

Hub grooming (keeping the folder structure clean, archiving old research) is itself automatable — a meta-task for the dispatch system.

## Critical Design Requirements

### 1. Feedback loop: PR state → vault state

When a PR is merged or closed, the vault task that spawned it must reflect the outcome:

| PR state | Vault update |
|----------|-------------|
| Merged | `status: done`, `completed_at: now` |
| Closed (rejected) | `status: active` or `needs_grooming`, rejection reason captured |
| Closed (superseded) | `status: deferred` with note |

**Implementation options:**
- GitHub webhook → jimbo-api endpoint that updates vault
- Orchestrator polls PR state on each cron cycle
- Manual (Marvin updates vault after review) — acceptable for v1

Without this, merged PRs accumulate alongside stale vault tasks. This is the single most important integration to build after the basic PR flow works.

### 2. Rejection reasons as training data

When Marvin closes a PR, the closing comment should capture *why*:
- "Approach was wrong — should have used X instead of Y"
- "Scope creep — changed files outside the task"
- "Quality insufficient — no tests, no evidence of DoD"

These reasons feed back into the next attempt:
- The dispatch prompt for retry includes: "Previous attempt was rejected because: {reason}"
- Over time, rejection patterns inform template improvements

### 3. Subtask rollup

When a parent task is broken into subtasks:
- Each subtask gets its own vault note with `parent_id`
- Each subtask produces its own PR
- When all subtasks are `done`, the parent should surface as "ready to close"
- This requires rollup logic: query children, check all done, notify

The `parent_id` column exists. The rollup logic does not. This is a vault service enhancement.

### 4. PR format standardisation

All dispatch PRs follow the format defined in `workspace/dispatch/templates/pr-format.md`:
- Summary, changes, DoD checklist with evidence
- Before/after screenshots for visual changes (stored in R2)
- Testing section
- Agent attribution line

This ensures every PR is self-contained — a reviewer can understand the full change without context-switching to the vault or the issue.

### 5. Screenshot and video evidence

For visual changes, agents capture before/after screenshots using Playwright:
1. Checkout `main`, dev server, screenshot affected page
2. Checkout feature branch, dev server, screenshot same page
3. Upload to R2 at `dispatch/{task_id}/before.png`, `after.png`
4. For interactive changes (keyboard, hover, animation): record video → `dispatch/{task_id}/demo.webm`
5. Reference URLs in PR body

This provides visual evidence that the Definition of Done was met, without requiring Marvin to run the code locally.

## What This Changes from the Original Dispatch Spec

| Original (2026-03-25) | Updated (2026-03-26) |
|----------------------|---------------------|
| Coder outputs PR, researcher outputs summary, drafter outputs file | All agent types output a PR |
| Result stored in dispatch_queue.result_summary | Result is the PR itself; dispatch_queue links to pr_url |
| No feedback loop from review to vault | PR merge/close updates vault task state |
| Rejection = batch rejected at proposal time | Two rejection points: batch proposal (pre-execution) and PR review (post-execution) |
| No visual evidence of completion | Playwright screenshots/video stored in R2 |
| hub repo not part of dispatch | hub is the target repo for non-code tasks |

## Open Questions

1. **GitHub webhook vs polling for PR state sync.** Webhook is cleaner but requires endpoint + secret management. Polling is simpler but adds latency (up to 5 min with current cron). Start with polling, upgrade if the delay is annoying.

2. **R2 credentials on M2.** The agent needs R2 access to upload screenshots. Either provision env vars on M2 or have the orchestrator upload from the result files after collection.

3. **Hub repo initialisation.** Hub needs the folder structure (`docs/research/`, `docs/drafts/`, etc.) and a CLAUDE.md explaining its purpose so agents landing there understand the context.

4. **Subtask creation UX.** Breaking a parent task into subtasks during grooming — is this done in Telegram, the dashboard, or terminal? The vault API supports it (`parent_id`), but the grooming workflow needs to feel natural.

5. **When does "everything is a PR" break down?** Probably for very short outputs (a single URL, a yes/no answer). These might be better as vault body updates than full PRs. Watch for this pattern and adapt.

## Implementation Priorities

1. **Template strictness** ✅ Done — coder.md updated to mandate push + PR
2. **PR format doc** ✅ Done — pr-format.md created
3. **Feedback loop (PR → vault)** — Next priority. Start with orchestrator polling.
4. **Rejection capture** — Extend dispatch complete/fail to store rejection reasons
5. **Subtask rollup** — Vault service: "all children done → surface parent"
6. **R2 screenshot pipeline** — Provision credentials on M2, test with next dispatch
7. **Hub initialisation** — Folder structure, CLAUDE.md, first non-code task test
