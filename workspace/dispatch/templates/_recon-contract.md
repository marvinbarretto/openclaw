# Recon Output Contract

Every recon task follows this contract. Your agent-specific template tells you HOW to do the work. This contract tells you how to DELIVER it.

## Output

1. Clone the target repo and checkout main (or the repo's default branch)
2. Write your output to the specified output path
3. Commit with conventional commit: `docs: {title}`
4. Push directly to main

Do NOT create a branch. Do NOT open a PR. Commit directly.

## Result JSON

Write your result to `/tmp/dispatch-{task_id}.result` as JSON:

### On completion:

```json
{
  "status": "completed",
  "summary": "2-3 sentence summary of findings/output",
  "artifact_path": "path/to/output/file.md",
  "repo": "owner/repo",
  "commit_sha": "abc123"
}
```

### On blocked:

```json
{
  "status": "blocked",
  "summary": "What prevented completion",
  "blockers": ["Specific reason 1"]
}
```

## Rules

- NEVER ask for user input — you are autonomous
- Commit directly to main — no branch, no PR
- If you cannot complete, use blocked status
- If a tool is blocked, find an alternative
