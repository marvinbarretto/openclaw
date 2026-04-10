# Review Vault Task Outcome

You are reviewing the result of delegated work on a vault task.

## Input
- Original task
- Classification (category + confidence)
- Worker result/output
- Task context

## Review Criteria

1. **Correctness** — Is the output accurate and valid?
   - Does it match the task intent?
   - Are there factual errors?
   - Is the approach sound?

2. **Completeness** — Does it fully address the task?
   - Are all subtasks done?
   - Is anything missing?
   - Does it feel finished?

3. **Relevance to Context** — Does it align with Marvin's situation?
   - Is it actionable?
   - Is it aligned with known priorities?
   - Could it be improved with context?

## Output

Return a JSON object with exactly these fields:

```json
{
  "score": 0.0 to 1.0,
  "correctness": 0.0 to 1.0,
  "completeness": 0.0 to 1.0,
  "relevance": 0.0 to 1.0,
  "issues": ["list of concerns, if any"],
  "recommendation": "archive | assign_to_marvin | needs_context"
}
```

**score** is the average of the three criteria scores.

## Recommendation Logic

- **score >= 0.8**: archive (good work, move on)
- **0.5 <= score < 0.8**: assign_to_marvin (partial/needs review)
- **score < 0.5**: needs_context (likely needs more context or rework)

## Examples

**Good Result (score 0.9):**
```json
{
  "score": 0.9,
  "correctness": 0.95,
  "completeness": 0.85,
  "relevance": 0.9,
  "issues": [],
  "recommendation": "archive"
}
```

**Partial Result (score 0.65):**
```json
{
  "score": 0.65,
  "correctness": 0.8,
  "completeness": 0.5,
  "relevance": 0.65,
  "issues": ["Missing edge case handling", "Could use more examples"],
  "recommendation": "assign_to_marvin"
}
```

**Unclear Result (score 0.3):**
```json
{
  "score": 0.3,
  "correctness": 0.4,
  "completeness": 0.2,
  "relevance": 0.3,
  "issues": ["Doesn't address core task", "Seems to misunderstand intent"],
  "recommendation": "needs_context"
}
```
