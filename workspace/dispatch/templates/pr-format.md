# Pull Request Format — Dispatch Agents

Every coder dispatch task MUST produce a PR that follows this format exactly.

## PR Title

Use the GitHub issue title verbatim if one exists. Otherwise: `type: [Scope] description`

Examples:
- `fix: [Mobile] Hide bottom nav tabs when keyboard is active`
- `feat: [Admin] Add bulk operations to event list`

## PR Body

```markdown
## Summary

One paragraph: what changed and why.

## Changes

- Bullet list of files changed with one-line explanation each
- Group by concern (e.g. "Hook", "Component", "Styles")

## Definition of Done Checklist

Map each acceptance criterion to evidence:

- [x] Criterion from the issue → what satisfies it
- [x] Another criterion → how it was verified
- [ ] Criterion that could not be verified → explain why

## Screenshots

### Before
![before](url-to-r2-screenshot)

### After
![after](url-to-r2-screenshot)

If the change is not visual (e.g. backend dedup, refactor), replace screenshots with:
- Test output showing the fix
- Log output showing the improvement
- `N/A — non-visual change: [explain what changed]`

## Testing

- What tests were run (existing suite, manual verification)
- Any pre-existing failures noted (not introduced by this PR)

## Notes

- Anything the reviewer should know
- Edge cases considered
- Decisions made and why

---
Dispatched by [Jimbo](https://github.com/marvinbarretto/openclaw) · Task #{seq} · Agent: {agent_type}
```

## Screenshot Requirements

Agents with access to Playwright MUST capture before/after screenshots for visual changes:

1. **Before**: checkout `main`, start dev server, navigate to the affected page, screenshot
2. **After**: checkout the feature branch, start dev server, same page, screenshot
3. Upload both to R2 at `dispatch/{task_id}/before.png` and `dispatch/{task_id}/after.png`
4. Reference the R2 URLs in the PR body

If Playwright is not available or the change cannot be screenshotted, explain why in the Screenshots section.

## Video (stretch goal)

If the change involves interaction (hover, focus, animation, keyboard):

1. Use Playwright to record a short video of the interaction
2. Upload to R2 at `dispatch/{task_id}/demo.webm`
3. Link in the PR body

## What Makes a Good Dispatch PR

- **Self-contained**: a reviewer can understand the full change from the PR alone
- **Evidence-based**: screenshots, test output, or logs — not just "I did it"
- **Honest**: if something couldn't be verified, say so
- **Minimal**: only files related to the task, no drive-by fixes
