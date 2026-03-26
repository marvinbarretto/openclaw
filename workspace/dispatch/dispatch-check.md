Check the dispatch queue for approved tasks and execute them.

## Step 1: Check for work

Run this curl command to check for an approved task:

```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/next"
```

If this returns a 404 or empty response, there are no approved tasks. Do nothing — output nothing, complete silently.

## Step 2: If a task is found

The response is JSON with `task_id`, `agent_type`, and `id` (dispatch queue ID).

1. Mark it as started:
```bash
curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" "$JIMBO_API_URL/api/dispatch/start" -d '{"id": DISPATCH_ID}'
```

2. Get the vault task details:
```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes/TASK_ID"
```

3. Read the prompt template from `~/development/openclaw/workspace/dispatch/templates/{agent_type}.md`

4. Fill in the template variables: `{title}`, `{definition_of_done}`, `{task_id}`, `{dispatch_repo}`, `{output_path}`

5. Dispatch a subagent with the rendered prompt. The subagent does the actual work (research, coding, drafting).

6. When the subagent completes, post the result:
```bash
curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" "$JIMBO_API_URL/api/dispatch/complete" -d '{"id": DISPATCH_ID, "result_summary": "SUMMARY"}'
```

If the subagent fails or gets blocked, report failure:
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
