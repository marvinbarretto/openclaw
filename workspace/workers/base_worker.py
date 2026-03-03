"""
Base worker for Jimbo's orchestrator.

Provides shared infrastructure: API clients for Google AI and Anthropic,
experiment tracker logging, task config loading, retry with fallback.

Python 3.11 stdlib only. No pip dependencies.
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid

_workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_tasks_dir = os.path.join(_workspace_dir, "tasks")
_tracker_script = os.path.join(_workspace_dir, "experiment-tracker.py")


def load_task_config(task_id):
    """Load a task definition from the registry."""
    path = os.path.join(_tasks_dir, f"{task_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No task config: {path}")
    with open(path) as f:
        return json.load(f)


def load_context_file(filename):
    """Load a context file from /workspace/context/ (sandbox) or workspace/context/ (local)."""
    for base in ["/workspace/context", os.path.join(_workspace_dir, "context")]:
        path = os.path.join(base, filename)
        if os.path.exists(path):
            with open(path) as f:
                return f.read()
    return None


def call_google_ai(prompt, model="gemini-2.5-flash", api_key=None, system=None):
    """Call Google AI Generative Language API. Returns {text, input_tokens, output_tokens}."""
    api_key = api_key or os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_AI_API_KEY not set")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )

    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    body = {"contents": contents}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    text = result["candidates"][0]["content"]["parts"][0]["text"]
    usage = result.get("usageMetadata", {})

    return {
        "text": text,
        "input_tokens": usage.get("promptTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0),
    }


def call_anthropic(prompt, model="claude-haiku-4.5", api_key=None, system=None, max_tokens=4096):
    """Call Anthropic Messages API. Returns {text, input_tokens, output_tokens}."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers)

    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    text = result["content"][0]["text"]
    usage = result.get("usage", {})

    return {
        "text": text,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


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


class BaseWorker:
    """Base class for all orchestrator workers."""

    def __init__(self, task_id):
        self.task_id = task_id
        self.config = load_task_config(task_id)
        self.run_id = "run_" + uuid.uuid4().hex[:8]
        self.start_time = time.time()

    def get_model(self):
        return self.config["default_model"]

    def get_fallback_model(self):
        return self.config.get("fallback_model")

    def get_context(self):
        """Load all context files specified in the task config."""
        context = {}
        for filename in self.config.get("context_files", []):
            content = load_context_file(filename)
            if content:
                context[filename] = content
        return context

    def call(self, prompt, system=None, model=None):
        """Call the model API with automatic fallback."""
        model = model or self.get_model()
        try:
            return call_model(prompt, model=model, system=system)
        except Exception as e:
            fallback = self.get_fallback_model()
            if fallback and fallback != model:
                sys.stderr.write(
                    f"Primary model {model} failed ({e}), trying fallback {fallback}\n"
                )
                return call_model(prompt, model=fallback, system=system)
            raise

    def log_run(self, model=None, input_tokens=0, output_tokens=0,
                input_summary=None, output_summary=None, quality_scores=None,
                conductor_rating=None, conductor_reasoning=None):
        """Log this run to the experiment tracker."""
        duration = int((time.time() - self.start_time) * 1000)
        model = model or self.get_model()

        cmd = [
            sys.executable, _tracker_script, "log",
            "--task", self.task_id,
            "--model", model,
            "--input-tokens", str(input_tokens),
            "--output-tokens", str(output_tokens),
        ]
        if duration:
            cmd.extend(["--duration", str(duration)])
        if input_summary:
            cmd.extend(["--input-summary", input_summary])
        if output_summary:
            cmd.extend(["--output-summary", output_summary])
        if quality_scores:
            scores_str = json.dumps(quality_scores) if isinstance(quality_scores, dict) else quality_scores
            cmd.extend(["--quality", scores_str])
        if conductor_rating is not None:
            cmd.extend(["--conductor-rating", str(conductor_rating)])
        if conductor_reasoning:
            reasoning_str = json.dumps(conductor_reasoning) if isinstance(conductor_reasoning, dict) else conductor_reasoning
            cmd.extend(["--conductor-reasoning", reasoning_str])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            sys.stderr.write(f"Tracker log failed: {result.stderr}\n")
            return None

        return json.loads(result.stdout)

    def run(self, input_data):
        """Override in each worker. Returns structured output dict."""
        raise NotImplementedError("Subclasses must implement run()")
