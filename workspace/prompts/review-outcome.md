# Review Dispatch Recommendation

You are reviewing a triage pipeline's dispatch recommendation for a vault task.

## Input
- Original task (title + description)
- Classification (category + confidence)
- Dispatch recommendation (agent/marvin/archive + reasoning)

## Review Criteria

1. **Correctness** — Is the dispatch path right?
   - Would an agent actually be able to do this?
   - Does this genuinely need Marvin, or could an agent handle it?
   - If archiving, is the task really stale/done/duplicate?

2. **Completeness** — Is the recommendation well-reasoned?
   - Does the reason make sense?
   - Is the effort estimate reasonable?
   - Is the agent_type appropriate for the category?

3. **Relevance** — Does this align with Marvin's priorities?
   - Is this task worth doing at all?
   - Is the urgency right?
   - Would Marvin agree with this routing?

## Output

Return a JSON object with exactly these fields:

```json
{
  "score": 0.0 to 1.0,
  "correctness": 0.0 to 1.0,
  "completeness": 0.0 to 1.0,
  "relevance": 0.0 to 1.0,
  "issues": ["list of concerns, if any"],
  "recommendation": "archive | assign_to_marvin | dispatch_to_agent"
}
```

**score** is the average of the three criteria scores.

## Recommendation Logic

- **score >= 0.8**: Accept the dispatch recommendation as-is
- **0.5 <= score < 0.8**: Flag for Marvin to review the recommendation
- **score < 0.5**: Recommendation is wrong — needs human review

## Examples

**Good recommendation (score 0.9):**
```json
{
  "score": 0.9,
  "correctness": 0.95,
  "completeness": 0.85,
  "relevance": 0.9,
  "issues": [],
  "recommendation": "dispatch_to_agent"
}
```

**Questionable recommendation (score 0.6):**
```json
{
  "score": 0.6,
  "correctness": 0.7,
  "completeness": 0.6,
  "relevance": 0.5,
  "issues": ["Task requires account access that agents can't have"],
  "recommendation": "assign_to_marvin"
}
```
