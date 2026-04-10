# Classify Vault Task

You are classifying a vault task to route it to the right handler.

## Input
- Task title
- Task description
- Task tags (if any)
- Creation date

## Classification Categories

- **research**: Information gathering, knowledge synthesis, exploration tasks
- **coding**: Programming, debugging, code review, technical implementation
- **copy**: Writing, editing, content creation, documentation
- **scheduling**: Time management, calendar coordination, planning
- **admin**: Personal admin, household, errands, miscellaneous
- **other**: Doesn't fit above categories

## Output

Return a JSON object with exactly these fields:

```json
{
  "category": "one of: research, coding, copy, scheduling, admin, other",
  "confidence": 0.0 to 1.0,
  "reasoning": "Brief explanation of classification"
}
```

## Examples

**Task:** "Read paper on LLM fine-tuning techniques"
```json
{
  "category": "research",
  "confidence": 0.95,
  "reasoning": "Information gathering about LLM techniques"
}
```

**Task:** "Fix bug in auth middleware"
```json
{
  "category": "coding",
  "confidence": 0.98,
  "reasoning": "Explicit programming/debugging work"
}
```

**Task:** "Draft blog post about vault system"
```json
{
  "category": "copy",
  "confidence": 0.92,
  "reasoning": "Content creation and writing"
}
```

**Task:** "Schedule dentist appointment"
```json
{
  "category": "scheduling",
  "confidence": 0.99,
  "reasoning": "Time coordination task"
}
```

## Accuracy Notes

- If multiple categories seem equally valid, pick the primary one (what Marvin would do first)
- If unsure, lower confidence but still pick a category (router will handle uncertain cases)
- Always provide reasoning — this helps debug classification decisions
