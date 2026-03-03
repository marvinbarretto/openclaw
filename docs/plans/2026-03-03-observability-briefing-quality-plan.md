# Observability & Briefing Quality — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add LangFuse observability to the full Jimbo pipeline, upgrade briefing model to Sonnet 4.6, add Kimi K2 as daily driver, and update model-swap infrastructure.

**Architecture:** Worker instrumentation via `call_model()` wrapper in base_worker.py (stdlib urllib, fire-and-forget POST to LangFuse ingestion API). Conductor traced via OpenRouter Broadcast (zero code). Model tiers updated in both swap scripts and VPS cron.

**Tech Stack:** Python 3.11 stdlib (urllib, json, base64, uuid), Bash (model-swap scripts), LangFuse REST API, OpenRouter Broadcast.

---

## Task 1: Add LangFuse tracing to `base_worker.py`

**Files:**
- Modify: `workspace/workers/base_worker.py:1-119`
- Test: `workspace/tests/test_base_worker.py`

**Step 1: Write the failing test for `trace_to_langfuse`**

Add to `workspace/tests/test_base_worker.py`:

```python
class TestLangfuseTracing(unittest.TestCase):
    @patch("workers.base_worker.urllib.request.urlopen")
    def test_trace_to_langfuse_posts_batch(self, mock_urlopen):
        """LangFuse tracing POSTs a batch with trace-create and generation-create."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"successes":[],"errors":[]}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-test"
        os.environ["LANGFUSE_SECRET_KEY"] = "sk-test"
        os.environ["LANGFUSE_HOST"] = "https://cloud.langfuse.com"

        from workers.base_worker import trace_to_langfuse
        trace_to_langfuse(
            trace_name="email-triage",
            run_id="run_abc123",
            model="gemini-2.5-flash",
            prompt="test prompt",
            response="test response",
            input_tokens=100,
            output_tokens=50,
            duration_ms=1234,
        )

        # Verify it called urlopen
        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/api/public/ingestion", req.full_url)

        # Verify auth header is Basic
        auth = req.get_header("Authorization")
        self.assertTrue(auth.startswith("Basic "))

        # Verify batch contains trace-create and generation-create
        body = json.loads(req.data)
        types = [e["type"] for e in body["batch"]]
        self.assertIn("trace-create", types)
        self.assertIn("generation-create", types)

        os.environ.pop("LANGFUSE_PUBLIC_KEY")
        os.environ.pop("LANGFUSE_SECRET_KEY")
        os.environ.pop("LANGFUSE_HOST")

    def test_trace_to_langfuse_noop_without_env(self):
        """LangFuse tracing does nothing if env vars are missing."""
        os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
        os.environ.pop("LANGFUSE_SECRET_KEY", None)

        from workers.base_worker import trace_to_langfuse
        # Should not raise
        trace_to_langfuse(
            trace_name="test",
            run_id="run_123",
            model="test",
            prompt="test",
            response="test",
            input_tokens=0,
            output_tokens=0,
            duration_ms=0,
        )
```

**Step 2: Run test to verify it fails**

Run: `cd workspace && python3 -m pytest tests/test_base_worker.py::TestLangfuseTracing -v`
Expected: FAIL with `ImportError` or `AttributeError` (function doesn't exist yet)

**Step 3: Implement `trace_to_langfuse` function**

Add to `workspace/workers/base_worker.py` after the existing imports (line 17), add `import base64`. Then add the function after `call_model()` (after line 119):

```python
import base64


def trace_to_langfuse(trace_name, run_id, model, prompt, response,
                      input_tokens, output_tokens, duration_ms,
                      system=None, metadata=None):
    """POST trace + generation to LangFuse ingestion API. Fire-and-forget."""
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        return  # silently disabled

    trace_id = f"{trace_name}/{run_id}"
    gen_id = f"{trace_id}/gen_{uuid.uuid4().hex[:8]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    batch = {
        "batch": [
            {
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": now,
                "body": {
                    "id": trace_id,
                    "timestamp": now,
                    "name": trace_name,
                    "metadata": metadata or {},
                    "tags": ["jimbo-worker"],
                },
            },
            {
                "id": str(uuid.uuid4()),
                "type": "generation-create",
                "timestamp": now,
                "body": {
                    "traceId": trace_id,
                    "id": gen_id,
                    "name": f"{trace_name}-call",
                    "startTime": now,
                    "model": model,
                    "input": {"system": system, "prompt": prompt} if system else prompt,
                    "output": response,
                    "usage": {
                        "input": input_tokens,
                        "output": output_tokens,
                    },
                    "metadata": {"duration_ms": duration_ms},
                },
            },
        ],
    }

    credentials = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    url = f"{host}/api/public/ingestion"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {credentials}",
    }
    data = json.dumps(batch).encode()
    req = urllib.request.Request(url, data=data, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as e:
        sys.stderr.write(f"LangFuse trace failed (non-blocking): {e}\n")
```

**Step 4: Run test to verify it passes**

Run: `cd workspace && python3 -m pytest tests/test_base_worker.py::TestLangfuseTracing -v`
Expected: PASS (both tests)

**Step 5: Commit**

```bash
git add workspace/workers/base_worker.py workspace/tests/test_base_worker.py
git commit -m "feat: add LangFuse tracing function to base_worker"
```

---

## Task 2: Wire `call_model()` to trace every call

**Files:**
- Modify: `workspace/workers/base_worker.py:112-119`
- Test: `workspace/tests/test_base_worker.py`

**Step 1: Write the failing test**

Add to `workspace/tests/test_base_worker.py`:

```python
class TestCallModelTracing(unittest.TestCase):
    @patch("workers.base_worker.trace_to_langfuse")
    @patch("workers.base_worker.urllib.request.urlopen")
    def test_call_model_traces_to_langfuse(self, mock_urlopen, mock_trace):
        """call_model() calls trace_to_langfuse after getting a response."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        from workers.base_worker import call_model
        result = call_model("test prompt", model="gemini-2.5-flash", api_key="fake")

        self.assertEqual(result["text"], "ok")
        mock_trace.assert_called_once()
        call_args = mock_trace.call_args
        self.assertEqual(call_args.kwargs["model"], "gemini-2.5-flash")
        self.assertEqual(call_args.kwargs["prompt"], "test prompt")
        self.assertEqual(call_args.kwargs["response"], "ok")
```

**Step 2: Run test to verify it fails**

Run: `cd workspace && python3 -m pytest tests/test_base_worker.py::TestCallModelTracing -v`
Expected: FAIL (`trace_to_langfuse` not called)

**Step 3: Update `call_model()` to add tracing**

Replace `call_model()` in `workspace/workers/base_worker.py` (lines 112-119):

```python
def call_model(prompt, model, provider=None, api_key=None, system=None):
    """Route to the correct API based on model name or provider."""
    start = time.time()
    if provider == "google" or model.startswith("gemini"):
        result = call_google_ai(prompt, model=model, api_key=api_key, system=system)
    elif provider == "anthropic" or model.startswith("claude"):
        result = call_anthropic(prompt, model=model, api_key=api_key, system=system)
    else:
        raise ValueError(f"Unknown model/provider: {model}/{provider}")

    duration_ms = int((time.time() - start) * 1000)
    trace_to_langfuse(
        trace_name=f"worker/{model}",
        run_id=f"call_{uuid.uuid4().hex[:8]}",
        model=model,
        prompt=prompt,
        response=result["text"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        duration_ms=duration_ms,
        system=system,
    )
    return result
```

**Step 4: Run all tests to verify nothing broke**

Run: `cd workspace && python3 -m pytest tests/test_base_worker.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add workspace/workers/base_worker.py workspace/tests/test_base_worker.py
git commit -m "feat: wire call_model to trace every worker API call to LangFuse"
```

---

## Task 3: Update model-swap scripts with new tiers

**Files:**
- Modify: `scripts/model-swap-local.sh`
- Modify: `scripts/model-swap.sh`

**Step 1: Add `sonnet` and `kimi` tiers to `model-swap-local.sh`**

Update the case statement. Replace existing `claude` tier with `sonnet`, add `kimi`:

```bash
case "${1:-}" in
  free)    MODEL="openrouter/stepfun/step-3.5-flash:free" ;;
  cheap)   MODEL="google/gemini-2.5-flash-lite" ;;
  daily)   MODEL="google/gemini-2.5-flash" ;;
  coding)  MODEL="openrouter/qwen/qwen3-coder-next" ;;
  haiku)   MODEL="openrouter/anthropic/claude-haiku-4.5" ;;
  sonnet)  MODEL="openrouter/anthropic/claude-sonnet-4-6" ;;
  kimi)    MODEL="openrouter/moonshotai/kimi-k2" ;;
  opus)    MODEL="openrouter/anthropic/claude-opus-4-6" ;;
  status)
    echo "Current model:"
    grep primary "$CONFIG"
    exit 0
    ;;
  *)
    echo "Usage: $0 {free|cheap|daily|coding|haiku|sonnet|kimi|opus|status}"
    exit 1
    ;;
esac
```

**Step 2: Mirror changes in `model-swap.sh`**

Same case statement updates plus update the usage help text:

```bash
case "${1:-}" in
  free)    MODEL="openrouter/stepfun/step-3.5-flash:free" ;;
  cheap)   MODEL="google/gemini-2.5-flash-lite" ;;
  daily)   MODEL="google/gemini-2.5-flash" ;;
  coding)  MODEL="openrouter/qwen/qwen3-coder-next" ;;
  haiku)   MODEL="openrouter/anthropic/claude-haiku-4.5" ;;
  sonnet)  MODEL="openrouter/anthropic/claude-sonnet-4-6" ;;
  kimi)    MODEL="openrouter/moonshotai/kimi-k2" ;;
  opus)    MODEL="openrouter/anthropic/claude-opus-4-6" ;;
  status)
    echo "Current model:"
    ssh "$VPS" "grep primary $CONFIG"
    exit 0
    ;;
  *)
    echo "Usage: $0 {free|cheap|daily|coding|haiku|sonnet|kimi|opus|status}"
    echo ""
    echo "  free    stepfun/step-3.5-flash:free     \$0"
    echo "  cheap   google/gemini-2.5-flash-lite    ~\$0.24/month  (direct Google AI)"
    echo "  daily   google/gemini-2.5-flash         ~\$0.78/month  (direct Google AI)"
    echo "  coding  qwen/qwen3-coder-next           ~\$0.07/1M tokens"
    echo "  haiku   anthropic/claude-haiku-4.5      ~\$2.49/month"
    echo "  sonnet  claude-sonnet-4-6               ~\$4/month (briefing window)"
    echo "  kimi    moonshotai/kimi-k2              ~\$1/month (daily driver)"
    echo "  opus    claude-opus-4-6                 max quality"
    echo "  status  show current model"
    exit 1
    ;;
esac
```

**Step 3: Verify scripts parse**

Run: `bash -n scripts/model-swap-local.sh && echo "local OK" && bash -n scripts/model-swap.sh && echo "remote OK"`
Expected: `local OK` and `remote OK`

**Step 4: Commit**

```bash
git add scripts/model-swap-local.sh scripts/model-swap.sh
git commit -m "feat: add sonnet and kimi tiers, update opus to 4.6"
```

---

## Task 4: Update briefing-synthesis task config

**Files:**
- Modify: `workspace/tasks/briefing-synthesis.json`

**Step 1: Update default_model and budget**

Replace the full file contents:

```json
{
  "task_id": "briefing-synthesis",
  "description": "Conductor task — Jimbo synthesises worker outputs into the morning briefing",
  "default_model": "claude-sonnet-4-6",
  "fallback_model": "claude-haiku-4.5",
  "provider": "openclaw",
  "evaluation": {
    "method": "user-rating",
    "criteria": [
      "followed_presentation_format",
      "time_sensitive_items_first",
      "surprise_attempt_included",
      "concise_and_scannable"
    ]
  },
  "budget_ceiling_per_run": 0.25,
  "notes": "This task is performed by Jimbo himself (conductor), not a worker script. Logged for tracking. Upgraded from Haiku to Sonnet 4.6 (2026-03-03)."
}
```

**Step 2: Verify JSON parses**

Run: `python3 -c "import json; json.load(open('workspace/tasks/briefing-synthesis.json'))" && echo "OK"`
Expected: `OK`

**Step 3: Commit**

```bash
git add workspace/tasks/briefing-synthesis.json
git commit -m "feat: upgrade briefing conductor to Sonnet 4.6 with Haiku fallback"
```

---

## Task 5: Deploy to VPS

**Step 1: Push workspace files (includes base_worker.py + task config)**

Run: `./scripts/workspace-push.sh`

**Step 2: Push model-swap-local.sh to VPS**

Run: `rsync -avz scripts/model-swap-local.sh jimbo:/usr/local/bin/model-swap-local.sh`

**Step 3: Update VPS cron — briefing window to Sonnet, daily to Kimi**

SSH in and update root crontab. Change:
```
45 6 * * * /usr/local/bin/model-swap-local.sh haiku >> /var/log/model-swap.log 2>&1
30 7 * * * /usr/local/bin/model-swap-local.sh daily >> /var/log/model-swap.log 2>&1
```
To:
```
45 6 * * * /usr/local/bin/model-swap-local.sh sonnet >> /var/log/model-swap.log 2>&1
30 7 * * * /usr/local/bin/model-swap-local.sh kimi >> /var/log/model-swap.log 2>&1
```

**Step 4: Add LangFuse env vars to `/opt/openclaw.env`**

Add these three lines (values from your LangFuse account):
```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

**Step 5: Pass LangFuse env vars into sandbox**

Update the cron entries that run workers (email fetch, tasks sweep) to include `-e LANGFUSE_PUBLIC_KEY=$LANGFUSE_PUBLIC_KEY -e LANGFUSE_SECRET_KEY=$LANGFUSE_SECRET_KEY -e LANGFUSE_HOST=$LANGFUSE_HOST` in the `docker exec` calls. Or add them to the openclaw.json `sandbox.docker.env` section so they're always available.

**Step 6: Verify deployment**

Run:
```bash
ssh jimbo "python3 -c \"import py_compile; py_compile.compile('/home/openclaw/.openclaw/workspace/workers/base_worker.py', doraise=True)\" && echo 'base_worker OK'"
ssh jimbo "grep sonnet /usr/local/bin/model-swap-local.sh && echo 'model-swap OK'"
ssh jimbo "grep 'sonnet-4-6' /home/openclaw/.openclaw/workspace/tasks/briefing-synthesis.json && echo 'task config OK'"
```

**Step 7: Commit any remaining changes**

```bash
git add -A && git commit -m "chore: deployment updates for observability + model upgrade"
```

---

## Task 6: Configure OpenRouter Broadcast (manual, no code)

**Step 1: Create LangFuse account**

Go to langfuse.com, sign up (free Hobby tier). Create a project called "Jimbo".

**Step 2: Get API keys**

In LangFuse project settings: copy the Public Key and Secret Key.

**Step 3: Enable broadcast in OpenRouter**

Go to OpenRouter settings → Broadcast → LangFuse. Paste the keys and base URL (`https://cloud.langfuse.com`). Test the connection.

**Step 4: Send a test message to Jimbo**

Send Jimbo a message via Telegram. Check LangFuse dashboard — you should see the full trace with system prompt, skills, and response.

---

## Task 7: Update CLAUDE.md and memory

**Files:**
- Modify: `CLAUDE.md` — update cron schedule docs (sonnet at 06:45, kimi at 07:30)
- Modify: `CAPABILITIES.md` — update current model info

**Step 1: Update CLAUDE.md cron documentation**

Find the cron schedule section and update:
- `06:45` line: "switch to Sonnet for morning briefing window" (was Haiku)
- `07:30` line: "switch to Kimi K2 after briefing" (was Flash)
- Daily sequence text: update model names

**Step 2: Update model-swap tiers in CLAUDE.md**

Update the model-swap.sh reference: `./scripts/model-swap.sh {free|cheap|daily|coding|haiku|sonnet|kimi|opus|status}`

**Step 3: Commit**

```bash
git add CLAUDE.md CAPABILITIES.md
git commit -m "docs: update model lineup — Sonnet 4.6 briefing, Kimi K2 daily"
```

---

## Execution Order Summary

| # | Task | Type | Blocked By |
|---|------|------|------------|
| 1 | LangFuse tracing function | Code (base_worker.py) | — |
| 2 | Wire call_model to trace | Code (base_worker.py) | 1 |
| 3 | Model-swap script tiers | Script edit | — |
| 4 | Briefing task config | JSON edit | — |
| 5 | Deploy to VPS | Deploy | 1, 2, 3, 4 |
| 6 | OpenRouter Broadcast | Manual config | — |
| 7 | Update docs | Docs | 3 |

Tasks 1→2 are sequential. Tasks 3, 4, 6 can run in parallel with each other and with 1-2. Task 5 needs all code done. Task 7 can run anytime.

---

## VPS Manual Steps Checklist

- [ ] Create LangFuse account + project
- [ ] Enable OpenRouter Broadcast → LangFuse
- [ ] Add `LANGFUSE_*` env vars to `/opt/openclaw.env`
- [ ] Pass LangFuse env vars into sandbox (openclaw.json docker.env or cron)
- [ ] Update VPS cron: 06:45 → `sonnet`, 07:30 → `kimi`
- [ ] Verify model swap works: `model-swap-local.sh status`
