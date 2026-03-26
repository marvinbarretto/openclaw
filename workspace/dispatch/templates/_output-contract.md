# Dispatch Output Contract

Every dispatch task, regardless of agent type, MUST follow this contract. Your agent-specific template tells you HOW to do the work. This contract tells you how to DELIVER it.

## Branching

- Branch name: `dispatch/{task_id}`
- Branch from `main` (or the repo's default branch)
- Use conventional commits: `type: description` — lowercase, imperative, ~70 chars

## Push and Open a PR — THIS IS MANDATORY

After completing your work:

1. `git push origin dispatch/{task_id}`
2. Open a PR using `gh pr create` following this format:

### PR Title
Use the task title or `type: [Scope] description`

### PR Body

## Summary
One paragraph: what you changed and why.

## Changes
- `path/to/file.ext` — what changed and why
- `path/to/other.ext` — what changed and why

## Definition of Done Checklist
For each criterion in the acceptance criteria:
- [x] Criterion — evidence (test output, screenshot URL, manual verification)

## Screenshots
Before: {R2_URL or "N/A — no visual changes"}
After: {R2_URL or "N/A — no visual changes"}
Video: {R2_URL or "N/A — no interactive changes"}

## Testing
What you ran and the results.

---
Dispatched by Jimbo · Task #{seq} · Agent: {agent_type}

## Visual Evidence (when applicable)

If your changes affect UI:

1. Checkout `main`, start dev server, capture screenshots of affected pages using Playwright
2. Checkout your feature branch, start dev server, capture the same pages
3. For interactive changes (keyboard, hover, animation): use Playwright `recordVideo` to capture a `.webm`
4. Upload to R2:
   - `curl -X PUT "https://${R2_DISPATCH_PUBLIC_URL}/{task_id}/before.png" --upload-file before.png`
   - Same for `after.png` and `demo.webm`
5. Embed the public URLs in the PR body under Screenshots

If your changes are NOT visual (backend, research, drafts): write "N/A — no visual changes" in the Screenshots section.

**Fallback:** If R2 upload fails, commit screenshots to `.dispatch/screenshots/` on the branch and note the fallback in the PR body.

## Result JSON

Write your result to `/tmp/dispatch-{task_id}.result` as JSON:

### On completion (PR opened successfully):
```json
{
  "status": "completed",
  "summary": "One-line description of what was done",
  "pr_url": "https://github.com/owner/repo/pull/N",
  "branch": "dispatch/{task_id}",
  "files_changed": ["path/to/file.ext"],
  "screenshots": {
    "before": "https://r2-url/before.png",
    "after": "https://r2-url/after.png",
    "video": "https://r2-url/demo.webm"
  }
}
```

`pr_url` is REQUIRED for completed status. If you cannot open a PR, use the blocked status instead.

### On blocked (cannot complete):
```json
{
  "status": "blocked",
  "summary": "What prevented completion",
  "branch": "dispatch/{task_id}",
  "blockers": ["Specific reason 1", "Specific reason 2"],
  "files_changed": ["any files touched before blocking"]
}
```

## Rules

- NEVER ask for user input — you are autonomous
- If a tool is blocked, find an alternative
- If you cannot complete the work, use the blocked status — do not leave work half-done without reporting
- One task at a time, one branch, one PR
