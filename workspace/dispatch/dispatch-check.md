Check the dispatch queue for approved tasks and execute them. Post status updates so the dashboard can show what's happening.

## Step 0: Post heartbeat

Every cycle, post a heartbeat so the dashboard knows the worker is alive:

```bash
curl -sf -X PUT -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" "$JIMBO_API_URL/api/settings/dispatch_worker" -d '{"value": "{\"status\": \"polling\", \"checked_at\": \"CURRENT_ISO_TIMESTAMP\", \"machine\": \"m2\"}"}'
```

Replace CURRENT_ISO_TIMESTAMP with the actual time.

## Step 1: Check for work

```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/next"
```

If this returns a 404 or empty response, there are no approved tasks. Do nothing — output nothing, complete silently.

## Step 2: If a task is found

The response is JSON with `task_id`, `agent_type`, and `id` (dispatch queue ID).

1. Post status update — task picked up:
```bash
curl -sf -X PUT -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" "$JIMBO_API_URL/api/settings/dispatch_worker" -d '{"value": "{\"status\": \"executing\", \"task_id\": \"TASK_ID\", \"agent_type\": \"AGENT_TYPE\", \"started_at\": \"CURRENT_ISO_TIMESTAMP\", \"machine\": \"m2\"}"}'
```

2. Mark it as started in the dispatch queue:
```bash
curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" "$JIMBO_API_URL/api/dispatch/start" -d '{"id": DISPATCH_ID}'
```

3. Get the vault task details:
```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes/TASK_ID"
```

4. Read the prompt template from `~/development/openclaw/workspace/dispatch/templates/{agent_type}.md`

5. Read the output contract from `~/development/openclaw/workspace/dispatch/templates/_output-contract.md`

6. Fill in the template variables: `{title}`, `{definition_of_done}`, `{task_id}`, `{dispatch_repo}`, `{output_path}`, `{seq}`, `{agent_type}`

7. **Check for previous rejections.** Query dispatch history for this task:
```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/queue?task_id=TASK_ID&status=rejected"
```
If results exist and the most recent has a `rejection_reason`, inject this block between the agent template and output contract:
```
---
PREVIOUS ATTEMPT FEEDBACK

This task was attempted before and the PR was rejected.
Reviewer feedback: {rejection_reason}

Learn from this feedback and adjust your approach accordingly.
---
```

8. Assemble the final prompt: `{agent template} + {rejection feedback if any} + {output contract}`

9. Dispatch a subagent with the rendered prompt. The subagent does the actual work.

10. When the subagent completes, read its result JSON from `/tmp/dispatch-{task_id}.result` and post:
```bash
curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" "$JIMBO_API_URL/api/dispatch/complete" -d '{"id": DISPATCH_ID, "result_summary": "SUMMARY", "pr_url": "PR_URL_FROM_RESULT"}'
```
Note: `pr_url` is now passed to the API so the webhook feedback loop can track the PR.

Then update worker status:
```bash
curl -sf -X PUT -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" "$JIMBO_API_URL/api/settings/dispatch_worker" -d '{"value": "{\"status\": \"completed\", \"task_id\": \"TASK_ID\", \"completed_at\": \"CURRENT_ISO_TIMESTAMP\", \"result_summary\": \"BRIEF_SUMMARY\", \"machine\": \"m2\"}"}'
```

If the subagent fails or gets blocked:
```bash
curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" "$JIMBO_API_URL/api/dispatch/fail" -d '{"id": DISPATCH_ID, "error_message": "REASON"}'
```

## Rules

- If no tasks, produce ZERO output. Silence means healthy.
- One task at a time. After completing a task, check again immediately before sleeping.
- Use the Agent tool to dispatch work to subagents — don't do the task yourself in the main loop.
- For coder tasks, the subagent should work in the repo specified by `dispatch_repo` (default: ~/development/localshout-next).
- For researcher tasks, the subagent should use WebSearch and WebFetch.
- For drafter tasks, the subagent should write to the specified output_path.
- ALWAYS post status updates — the dashboard depends on them.

## CRITICAL: Autonomous execution

This loop runs unattended. No human is watching. You MUST:

- NEVER ask for user input or confirmation. Make decisions autonomously.
- NEVER present multiple choice options and wait for a response.
- If a tool use requires permission, skip it and use an alternative approach.
- If you're unsure, pick the most reasonable option and proceed.
- If a subagent would need to ask for permission, instruct it to proceed without asking.
- When dispatching subagents, include this instruction in their prompt: "You are running autonomously with no human present. Never ask for confirmation. Make all decisions yourself. If a tool is blocked, use an alternative."
