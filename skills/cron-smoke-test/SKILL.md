---
name: cron-smoke-test
description: One-shot scheduled job smoke test for isolated cron execution
user-invokable: false
---

# Cron Smoke Test

This skill exists only to verify that scheduled isolated jobs can read a workspace skill file and execute simple commands inside the sandbox.

## Steps

1. Run:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

2. Run:

```bash
cat /workspace/current-model.txt
```

3. Reply with exactly one line:

```text
[Cron Smoke] <utc timestamp> | model: <model id> | skill path OK
```

## Rules

- No extra commentary.
- No markdown.
- If a command fails, reply with exactly one line:

```text
[Cron Smoke] failed: <short reason>
```
