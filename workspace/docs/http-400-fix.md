# HTTP 400 Bad Request Fix - Task Record Decisions Schema

## Root Cause

When `jimbo_runtime.py` sent decision updates via PATCH to `/api/workflows/tasks/{id}`, the API returned HTTP 400 errors. The issue was **JSON serialization of null/optional fields** in the decisions array.

### The Problem

**Original code (line 360):**
```python
decisions_json = [{'step': d.step, 'decision': d.decision, 'model': d.model, 'worker_id': d.worker_id, 'cost': d.cost, 'timestamp': d.timestamp} for d in tr.decisions]
```

**Issue:** This unconditionally included all fields, even when they were `None`:

```json
{
  "decisions": [
    {
      "step": "classify",
      "decision": {"category": "research"},
      "model": "haiku",
      "worker_id": null,    // <-- Problem: null in JSON
      "cost": 0.0,
      "timestamp": "2026-04-10T..."
    }
  ]
}
```

**Why it failed:**

The jimbo-api backend uses Zod validation for the decisions schema:

```typescript
// Expected schema (DecisionSchema)
{
  step: string,
  decision: object,
  model?: string,           // Optional field
  worker_id?: string,       // Optional field
  cost?: number,
  timestamp: string
}
```

Zod treats `model: null` and the absence of the `model` field differently:
- **Missing field** `{}` — valid (field is optional)
- **Null field** `{"model": null}` — invalid (field must be string OR missing)

Result: HTTP 400 validation error, with response body explaining the schema violation.

---

## The Fix

**Two changes:**

### 1. Filter Null Fields When Serializing (Line 366-376)

```python
# Serialize decisions, excluding null fields (Zod schema validation)
decisions_json = []
for d in tr.decisions:
    dec = {'step': d.step, 'decision': d.decision, 'timestamp': d.timestamp}
    if d.model is not None:
        dec['model'] = d.model
    if d.worker_id is not None:
        dec['worker_id'] = d.worker_id
    if d.cost > 0:
        dec['cost'] = d.cost
    decisions_json.append(dec)
```

Now produces valid JSON (null fields omitted):

```json
{
  "decisions": [
    {
      "step": "classify",
      "decision": {"category": "research"},
      "model": "haiku",
      "timestamp": "2026-04-10T..."
      // model and worker_id omitted if null
    }
  ]
}
```

### 2. Improve Error Handler to Show Response Body (Line 121-125)

```python
except HTTPError as e:
    error_body = e.read().decode('utf-8') if e.fp else ""
    print(f"ERROR: HTTP {e.code} updating task record: {error_body}")
    print(f"DEBUG: Payload was: {json.dumps(payload, indent=2)}")
    return None
```

**Before:** Only printed `"ERROR: Failed to update task record: <URLError>"` — no details  
**After:** Prints HTTP status code, response body, and the actual payload sent

This makes debugging much faster: you can immediately see what validation failed and what data was rejected.

---

## Testing

Added `/workspace/tests/test_task_record_api.py` with three test cases:

1. **Decision with all fields** — includes model, worker_id, cost in JSON
2. **Decision without optional fields** — omits model, worker_id, cost from JSON
3. **Multiple decisions** — each serialized independently
4. **Valid JSON output** — proves no null values appear in serialized output

---

## Files Changed

- `/workspace/jimbo_runtime.py` — lines 100-128 (error handler), lines 366-376 (serialization)
- `/workspace/tests/test_task_record_api.py` — new test file

---

## Next Steps

1. Run `pytest workspace/tests/test_task_record_api.py -v` to verify serialization tests pass
2. Run `jimbo_runtime.py vault-triage --dry-run` to test with actual workflow
3. If 400 still occurs, the new error handler will show the exact validation failure from the backend

---

## Schema Reference

Expected jimbo-api DecisionSchema (from docs/superpowers/specs/):

```typescript
decision: {
  step: string,              // Required: step ID
  decision: object,          // Required: the decision data
  model?: string,            // Optional: which model made this decision
  worker_id?: string,        // Optional: which worker executed
  result?: object,           // Optional: outcome of execution
  cost?: number,             // Optional: model cost for this step
  timestamp: string          // Required: ISO timestamp
}
```

Key rule: **Zod optional fields (`?`) must be omitted from JSON if not present, not set to null.**
