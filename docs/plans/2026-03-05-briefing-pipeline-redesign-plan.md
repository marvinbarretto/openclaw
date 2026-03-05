# Briefing Pipeline Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move briefing orchestration from LLM prompts to cron-driven Python, add optional local Opus analysis layer, slim Jimbo's skill to ~60 lines.

**Architecture:** `briefing-prep.py` (VPS cron) runs workers sequentially, assembles `briefing-input.json`. Optional `opus-briefing.sh` (Mac launchd) runs Opus analysis via `claude -p`. Jimbo reads pre-computed JSON and composes the briefing — one job, one input.

**Tech Stack:** Python 3.11 stdlib only (VPS sandbox), Bash + claude CLI (Mac), OpenClaw skill (SKILL.md)

**Design doc:** `docs/plans/2026-03-05-briefing-pipeline-redesign-design.md`

---

## Phase 1: Core Pipeline (`briefing-prep.py`)

The foundation. Works standalone without the Opus layer.

### Task 1: Create `briefing-prep.py` skeleton with CLI

**Files:**
- Create: `workspace/briefing-prep.py`
- Test: `workspace/tests/test_briefing_prep.py`

**Step 1: Write the failing test**

```python
# workspace/tests/test_briefing_prep.py
import json
import subprocess
import sys

def test_briefing_prep_cli_accepts_morning():
    """briefing-prep.py accepts 'morning' subcommand without crashing."""
    result = subprocess.run(
        [sys.executable, "workspace/briefing-prep.py", "morning", "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode == 0

def test_briefing_prep_cli_accepts_afternoon():
    result = subprocess.run(
        [sys.executable, "workspace/briefing-prep.py", "afternoon", "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode == 0

def test_briefing_prep_cli_rejects_unknown():
    result = subprocess.run(
        [sys.executable, "workspace/briefing-prep.py", "midnight"],
        capture_output=True, text=True
    )
    assert result.returncode != 0
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest workspace/tests/test_briefing_prep.py -v`
Expected: FAIL — file doesn't exist

**Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""
Briefing pipeline orchestrator.

Runs workers, fetches calendar, selects vault tasks, assembles briefing-input.json.
Replaces LLM-driven orchestration from sift-digest skill.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 briefing-prep.py morning              # full morning pipeline
    python3 briefing-prep.py afternoon            # lighter afternoon pipeline
    python3 briefing-prep.py morning --dry-run    # assemble without running workers
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import time

_script_dir = os.path.dirname(os.path.abspath(__file__))
ALERT_SCRIPT = os.path.join(_script_dir, "alert.py")
TRACKER_SCRIPT = os.path.join(_script_dir, "experiment-tracker.py")
OUTPUT_PATH = os.path.join(_script_dir, "briefing-input.json")


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def alert(message):
    """Send Telegram alert. Non-blocking."""
    try:
        subprocess.run([sys.executable, ALERT_SCRIPT, message], timeout=10)
    except Exception:
        pass


def log_to_tracker(session, pipeline_status, duration_ms):
    """Log pipeline run to experiment-tracker."""
    status_summary = ", ".join(
        f"{k}={v['status']}" for k, v in pipeline_status.items()
    )
    try:
        subprocess.run([
            sys.executable, TRACKER_SCRIPT, "log",
            "--task", "briefing-prep",
            "--model", "pipeline",
            "--input-tokens", "0",
            "--output-tokens", "0",
            "--session", session,
            "--output-summary", status_summary,
            "--duration", str(duration_ms),
        ], timeout=10)
    except Exception as e:
        sys.stderr.write(f"Tracker log failed: {e}\n")


def run_step(name, cmd, env=None, timeout=120):
    """Run a pipeline step. Returns (ok, result_dict)."""
    merged_env = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, env=merged_env,
        )
        if result.returncode != 0:
            error = result.stderr.strip()[:200]
            alert(f"❌ {name} failed: {error}")
            return False, {"status": "failed", "error": error}
        return True, {"status": "ok"}
    except subprocess.TimeoutExpired:
        alert(f"❌ {name} timed out after {timeout}s")
        return False, {"status": "timeout"}
    except Exception as e:
        alert(f"❌ {name} error: {e}")
        return False, {"status": "error", "error": str(e)}


def run_pipeline(session, dry_run=False):
    """Run the full briefing prep pipeline."""
    start = time.time()
    pipeline_status = {}
    calendar = []
    gems = []
    shortlist_reasons = []
    vault_tasks = []
    triage_pending = 0

    # --- Step 1: Email fetch ---
    fetch_hours = 14 if session == "morning" else 8
    if not dry_run:
        ok, status = run_step("email-fetch", [
            sys.executable, os.path.join(_script_dir, "gmail-helper.py"),
            "fetch", "--hours", str(fetch_hours),
        ])
        pipeline_status["email_fetch"] = status
        if ok:
            try:
                with open(os.path.join(_script_dir, "email-digest.json")) as f:
                    digest = json.load(f)
                pipeline_status["email_fetch"]["count"] = len(digest.get("items", []))
            except (json.JSONDecodeError, OSError):
                pipeline_status["email_fetch"]["count"] = 0
    else:
        pipeline_status["email_fetch"] = {"status": "skipped (dry-run)"}

    # --- Step 2: Email triage ---
    shortlist_path = os.path.join(_script_dir, ".worker-shortlist.json")
    digest_path = os.path.join(_script_dir, "email-digest.json")
    if not dry_run and pipeline_status.get("email_fetch", {}).get("status") == "ok":
        ok, status = run_step("email-triage", [
            sys.executable, os.path.join(_script_dir, "workers", "email_triage.py"),
            "--digest", digest_path,
            "--output", shortlist_path,
        ], timeout=180)
        pipeline_status["triage"] = status
        if ok:
            try:
                with open(shortlist_path) as f:
                    shortlist_data = json.load(f)
                stats = shortlist_data.get("stats", {})
                pipeline_status["triage"]["shortlisted"] = stats.get("shortlisted", 0)
                pipeline_status["triage"]["skipped"] = stats.get("skipped", 0)
                shortlist_reasons = shortlist_data.get("shortlist", [])
            except (json.JSONDecodeError, OSError):
                pass
    else:
        pipeline_status["triage"] = {"status": "skipped"}

    # --- Step 3: Newsletter deep read ---
    gems_path = os.path.join(_script_dir, ".worker-gems.json")
    if not dry_run and os.path.exists(shortlist_path):
        ok, status = run_step("newsletter-reader", [
            sys.executable, os.path.join(_script_dir, "workers", "newsletter_reader.py"),
            "--shortlist", shortlist_path,
            "--digest", digest_path,
            "--output", gems_path,
        ], timeout=300)
        pipeline_status["reader"] = status
        if ok:
            try:
                with open(gems_path) as f:
                    gems_data = json.load(f)
                gems = gems_data.get("gems", [])
                stats = gems_data.get("stats", {})
                pipeline_status["reader"]["gems"] = stats.get("gems_extracted", 0)
                pipeline_status["reader"]["skipped"] = stats.get("skipped_count", 0)
            except (json.JSONDecodeError, OSError):
                pass
    else:
        pipeline_status["reader"] = {"status": "skipped"}

    # --- Step 4: Calendar ---
    if not dry_run:
        result = subprocess.run(
            [sys.executable, os.path.join(_script_dir, "calendar-helper.py"),
             "list-events", "--days", "1"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            try:
                calendar = json.loads(result.stdout)
                if isinstance(calendar, dict):
                    calendar = calendar.get("events", calendar.get("items", []))
                pipeline_status["calendar"] = {"status": "ok", "events": len(calendar)}
            except json.JSONDecodeError:
                pipeline_status["calendar"] = {"status": "failed", "error": "invalid JSON"}
        else:
            pipeline_status["calendar"] = {"status": "failed", "error": result.stderr.strip()[:200]}
    else:
        pipeline_status["calendar"] = {"status": "skipped (dry-run)"}

    # --- Step 5: Vault tasks (morning only) ---
    if session == "morning" and not dry_run:
        vault_tasks, vault_status = select_vault_tasks()
        pipeline_status["vault"] = vault_status
    else:
        pipeline_status["vault"] = {"status": "skipped"}

    # --- Step 6: Triage pending ---
    if session == "morning":
        try:
            triage_path = os.path.join(_script_dir, "tasks-triage-pending.json")
            if os.path.exists(triage_path):
                with open(triage_path) as f:
                    triage_data = json.load(f)
                triage_pending = triage_data.get("needs_triage", 0)
        except (json.JSONDecodeError, OSError):
            pass

    # --- Step 7: Context summary ---
    context_summary = build_context_summary()

    # --- Assemble output ---
    output = {
        "generated_at": now_utc().isoformat(),
        "session": session,
        "pipeline": pipeline_status,
        "calendar": calendar,
        "gems": gems,
        "shortlist_reasons": shortlist_reasons,
        "vault_tasks": vault_tasks,
        "context_summary": context_summary,
        "triage_pending": triage_pending,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    duration_ms = int((time.time() - start) * 1000)

    # --- Log and alert ---
    log_to_tracker(session, pipeline_status, duration_ms)
    send_status_alert(session, pipeline_status, duration_ms)

    return output


def select_vault_tasks(limit=5):
    """Select top vault tasks by priority score. Returns (tasks_list, status_dict)."""
    vault_dir = os.path.join("/workspace", "vault", "notes")
    if not os.path.exists(vault_dir):
        return [], {"status": "failed", "error": "vault dir not found"}

    tasks = []
    for filename in os.listdir(vault_dir):
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(vault_dir, filename)
        try:
            with open(filepath) as f:
                content = f.read(2000)  # frontmatter is always near the top
        except OSError:
            continue

        # Parse YAML frontmatter (simple — no yaml lib in stdlib)
        if not content.startswith("---"):
            continue
        end = content.find("---", 3)
        if end == -1:
            continue
        frontmatter = content[3:end]

        meta = {}
        for line in frontmatter.strip().split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                meta[key.strip()] = val.strip().strip('"').strip("'")

        if meta.get("type") != "task" or meta.get("status") != "active":
            continue

        try:
            priority = int(meta.get("priority", "0"))
        except ValueError:
            priority = 0

        if priority < 7:
            continue

        tasks.append({
            "file": filename,
            "title": meta.get("title", filename),
            "priority": priority,
            "actionability": meta.get("actionability", "unknown"),
            "tags": meta.get("tags", "[]"),
        })

    tasks.sort(key=lambda t: t["priority"], reverse=True)
    tasks = tasks[:limit]

    return tasks, {"status": "ok", "tasks": len(tasks)}


def build_context_summary():
    """Build a context summary from context files."""
    summary = {}
    context_dir = os.path.join("/workspace", "context")

    for name, key in [("PRIORITIES.md", "priorities_updated"), ("GOALS.md", "goals_updated")]:
        path = os.path.join(context_dir, name)
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            summary[key] = datetime.datetime.fromtimestamp(
                mtime, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d")

    # Read top priority from PRIORITIES.md
    priorities_path = os.path.join(context_dir, "PRIORITIES.md")
    if os.path.exists(priorities_path):
        try:
            with open(priorities_path) as f:
                content = f.read(500)
            # Look for first bullet point after "This Week" or similar header
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    summary["top_priority"] = line.lstrip("-* ").strip()
                    break
        except OSError:
            pass

    return summary


def send_status_alert(session, pipeline_status, duration_ms):
    """Send a one-line status summary to Telegram."""
    parts = []

    # Email stats
    fetch = pipeline_status.get("email_fetch", {})
    triage = pipeline_status.get("triage", {})
    reader = pipeline_status.get("reader", {})
    if fetch.get("status") == "ok":
        count = fetch.get("count", "?")
        shortlisted = triage.get("shortlisted", "?")
        gem_count = reader.get("gems", "?")
        parts.append(f"{count} emails → {shortlisted} shortlisted → {gem_count} gems")
    else:
        parts.append(f"email: {fetch.get('status', 'unknown')}")

    # Calendar
    cal = pipeline_status.get("calendar", {})
    if cal.get("status") == "ok":
        parts.append(f"calendar: {cal.get('events', 0)} events")
    else:
        parts.append(f"calendar: {cal.get('status', 'unknown')}")

    # Vault
    vault = pipeline_status.get("vault", {})
    if vault.get("status") == "ok":
        parts.append(f"vault: {vault.get('tasks', 0)} tasks")

    # Check for Opus analysis
    analysis_path = os.path.join(_script_dir, "briefing-analysis.json")
    opus = "no"
    if os.path.exists(analysis_path):
        try:
            mtime = os.path.getmtime(analysis_path)
            age_hours = (time.time() - mtime) / 3600
            if age_hours < 2:
                opus = "yes"
        except OSError:
            pass
    parts.append(f"opus: {opus}")

    # Duration
    parts.append(f"{duration_ms // 1000}s")

    label = "Morning" if session == "morning" else "Afternoon"
    any_failed = any(
        v.get("status") in ("failed", "timeout", "error")
        for v in pipeline_status.values()
    )
    icon = "❌" if any_failed else "✅"

    alert(f"{icon} {label} pipeline: {' | '.join(parts)}")


def main():
    parser = argparse.ArgumentParser(description="Briefing pipeline orchestrator")
    parser.add_argument("session", choices=["morning", "afternoon"])
    parser.add_argument("--dry-run", action="store_true", help="Assemble without running workers")
    args = parser.parse_args()

    output = run_pipeline(args.session, dry_run=args.dry_run)
    print(json.dumps({"status": "ok", "path": OUTPUT_PATH}, indent=2))


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest workspace/tests/test_briefing_prep.py -v`
Expected: PASS (dry-run doesn't call any external services)

**Step 5: Commit**

```bash
git add workspace/briefing-prep.py workspace/tests/test_briefing_prep.py
git commit -m "feat: add briefing-prep.py pipeline orchestrator"
```

---

### Task 2: Test pipeline steps with mocked workers

**Files:**
- Modify: `workspace/tests/test_briefing_prep.py`

**Step 1: Write tests for `select_vault_tasks` and `build_context_summary`**

```python
import os
import tempfile

def test_select_vault_tasks_picks_high_priority(tmp_path):
    """Vault task selector returns tasks with priority >= 7, sorted descending."""
    # Create a mock vault dir with 3 files
    (tmp_path / "high.md").write_text('---\ntype: task\nstatus: active\npriority: 9\ntitle: "High"\n---\n')
    (tmp_path / "medium.md").write_text('---\ntype: task\nstatus: active\npriority: 5\ntitle: "Medium"\n---\n')
    (tmp_path / "also_high.md").write_text('---\ntype: task\nstatus: active\npriority: 8\ntitle: "Also High"\n---\n')

    # Patch vault_dir in the function (or call with overrideable path)
    # For now, test the frontmatter parsing logic directly
    from workspace.briefing_prep import select_vault_tasks
    tasks, status = select_vault_tasks(vault_dir=str(tmp_path))
    assert status["status"] == "ok"
    assert len(tasks) == 2
    assert tasks[0]["priority"] == 9
    assert tasks[1]["priority"] == 8

def test_select_vault_tasks_skips_non_tasks(tmp_path):
    """Vault task selector ignores non-task types and inactive items."""
    (tmp_path / "bookmark.md").write_text('---\ntype: bookmark\nstatus: active\npriority: 10\ntitle: "Link"\n---\n')
    (tmp_path / "done.md").write_text('---\ntype: task\nstatus: done\npriority: 9\ntitle: "Done"\n---\n')

    from workspace.briefing_prep import select_vault_tasks
    tasks, status = select_vault_tasks(vault_dir=str(tmp_path))
    assert len(tasks) == 0
```

Note: To make `select_vault_tasks` testable, add an optional `vault_dir` parameter (default `/workspace/vault/notes`). Update the function signature in briefing-prep.py:

```python
def select_vault_tasks(limit=5, vault_dir=None):
    vault_dir = vault_dir or os.path.join("/workspace", "vault", "notes")
```

**Step 2: Run tests**

Run: `python3 -m pytest workspace/tests/test_briefing_prep.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add workspace/briefing-prep.py workspace/tests/test_briefing_prep.py
git commit -m "test: add vault task selection tests for briefing-prep"
```

---

### Task 3: Test `run_step` and `send_status_alert`

**Files:**
- Modify: `workspace/tests/test_briefing_prep.py`

**Step 1: Write tests for `run_step` error handling**

```python
def test_run_step_captures_failure():
    """run_step returns failure status when command exits non-zero."""
    from workspace.briefing_prep import run_step
    ok, status = run_step("test-fail", [sys.executable, "-c", "import sys; sys.exit(1)"])
    assert ok is False
    assert status["status"] == "failed"

def test_run_step_captures_timeout():
    """run_step returns timeout status when command exceeds timeout."""
    from workspace.briefing_prep import run_step
    ok, status = run_step("test-timeout", [sys.executable, "-c", "import time; time.sleep(10)"], timeout=1)
    assert ok is False
    assert status["status"] == "timeout"

def test_run_step_captures_success():
    """run_step returns ok status on success."""
    from workspace.briefing_prep import run_step
    ok, status = run_step("test-ok", [sys.executable, "-c", "print('hello')"])
    assert ok is True
    assert status["status"] == "ok"
```

**Step 2: Run tests**

Run: `python3 -m pytest workspace/tests/test_briefing_prep.py -v`
Expected: PASS (note: `run_step` calls `alert()` on failure — alert.py will silently skip without env vars)

**Step 3: Commit**

```bash
git add workspace/tests/test_briefing_prep.py
git commit -m "test: add run_step error handling tests"
```

---

### Task 4: Deploy `briefing-prep.py` to VPS and test

**Files:**
- Modify: `scripts/workspace-push.sh` (add briefing-prep.py to rsync if not already covered)

**Step 1: Push to VPS**

```bash
./scripts/workspace-push.sh
```

**Step 2: Test dry-run on VPS**

```bash
ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/briefing-prep.py morning --dry-run'
```

Expected: JSON output with all pipeline steps showing `"status": "skipped (dry-run)"`, and `briefing-input.json` written.

**Step 3: Test live morning run on VPS**

```bash
ssh jimbo 'export $(grep -v "^#" /opt/openclaw.env | xargs) && docker exec \
  -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e GOOGLE_CALENDAR_CLIENT_ID=$GOOGLE_CALENDAR_CLIENT_ID \
  -e GOOGLE_CALENDAR_CLIENT_SECRET=$GOOGLE_CALENDAR_CLIENT_SECRET \
  -e GOOGLE_CALENDAR_REFRESH_TOKEN=$GOOGLE_CALENDAR_REFRESH_TOKEN \
  -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
  -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/briefing-prep.py morning'
```

Expected: Pipeline runs all steps, writes `briefing-input.json`, sends Telegram status. Check:
- Was a Telegram status message received?
- Does `briefing-input.json` have populated calendar, gems, and vault_tasks arrays?
- Did the experiment-tracker get a `briefing-prep` row?

**Step 4: Verify `briefing-input.json` content**

```bash
ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) python3 -c "
import json
d = json.load(open(\"/workspace/briefing-input.json\"))
print(\"Session:\", d[\"session\"])
print(\"Pipeline:\")
for k, v in d[\"pipeline\"].items():
    print(f\"  {k}: {v}\")
print(f\"Calendar events: {len(d[\"calendar\"])}\"  )
print(f\"Gems: {len(d[\"gems\"])}\")
print(f\"Vault tasks: {len(d[\"vault_tasks\"])}\")
print(f\"Triage pending: {d[\"triage_pending\"]}\")
"'
```

**Step 5: Commit any fixes discovered during VPS testing**

```bash
git add workspace/briefing-prep.py
git commit -m "fix: briefing-prep adjustments from live VPS testing"
```

---

## Phase 2: New Jimbo Skill

### Task 5: Write the new `daily-briefing/SKILL.md`

**Files:**
- Modify: `skills/daily-briefing/SKILL.md` (full rewrite)

**Step 1: Write the new skill**

```markdown
---
name: daily-briefing
description: Compose and deliver the morning or afternoon briefing from pre-computed pipeline data
user-invokable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or it's a scheduled briefing session, compose a briefing from the pre-computed pipeline data.

## Step 1: Read inputs

Run in the sandbox:

1. `cat /workspace/briefing-input.json`
2. `cat /workspace/briefing-analysis.json 2>/dev/null || echo 'null'`
3. `cat /workspace/SOUL.md`

If `briefing-input.json` is missing or older than 4 hours, say: "Pipeline hasn't run yet today. Ask me to check email if you want a manual scan."

If `briefing-analysis.json` exists and is less than 2 hours old, you are in **Opus-assisted mode** — the hard thinking is done. Your job is to deliver it in your voice.

If `briefing-analysis.json` is missing or stale, you are in **self-compose mode** — build the day plan yourself from the raw data.

## Step 2: Compose the briefing

### HARD RULES (both modes)

- **Calendar contains ONLY events from briefing-input.json.** Do not add, infer, or fabricate any events. If there are 4 events, show 4 events. If there are 0 events, say "nothing on the calendar today."
- **Email highlights come from the gems array.** Do not re-triage the digest yourself.
- **Report pipeline failures honestly.** If `pipeline.triage.status` is `"failed"`, say so: "Email triage didn't run today — highlights may be incomplete."

### Opus-assisted mode

Use the `briefing-analysis.json` data:
- Present the `day_plan` entries as time-blocked suggestions with the reasoning
- Present `email_highlights` with the editorial commentary
- If `surprise` is not null, present it
- Use `editorial_voice` to set your tone
- Rewrite everything in your own voice (SOUL.md personality) — don't just dump the JSON

### Self-compose mode

Build from `briefing-input.json`:
- **Calendar:** List events chronologically. Flag anything in the next 2 hours.
- **Day plan:** Identify free gaps between events. Cross-reference gems and vault_tasks. Suggest 3-5 activities with reasoning.
- **Email highlights:** Pick the top 3-5 gems by confidence. Explain WHY each matters.
- **Vault tasks:** Surface the top 2-3 from `vault_tasks` array. Weave into the day plan.
- **Surprise game (afternoon only):** Pick the best `surprise_candidate: true` gem, or make your own connection.

### Both modes

- **Morning:** Full day plan. End with "Anything you'd swap or skip?"
- **Afternoon:** Rescue framing. What's left today? What changed since morning? What to let go of?
- If `triage_pending > 0` and morning: "I picked up **{triage_pending} tasks** that need your input. When's good for a 15-min triage?"
- Keep it scannable — under 1 minute to read.

## Step 3: Log (MANDATORY)

After delivering the briefing, always run both:

```bash
python3 /workspace/experiment-tracker.py log \
    --task briefing-synthesis \
    --model <your-model> \
    --input-tokens <est> --output-tokens <est> \
    --session <morning|afternoon> \
    --conductor-rating <1-10> \
    --conductor-reasoning '{"mode": "<opus-assisted|self-compose>", "gems_used": <N>, "calendar_events": <N>}'

python3 /workspace/activity-log.py log \
    --task briefing \
    --description "<Morning|Afternoon> briefing: <brief summary>" \
    --outcome "<success|partial>" \
    --rationale "mode=<opus-assisted|self-compose>, calendar=<N events>, email=<N gems>, vault=<N tasks>" \
    --model <your-model>
```
```

**Step 2: Deploy to VPS**

```bash
./scripts/skills-push.sh
```

**Step 3: Commit**

```bash
git add skills/daily-briefing/SKILL.md
git commit -m "feat: rewrite daily-briefing skill for pipeline architecture"
```

---

### Task 6: Retire `sift-digest/SKILL.md`

**Files:**
- Modify: `skills/sift-digest/SKILL.md` (replace with redirect)

**Step 1: Replace with a redirect skill**

```markdown
---
name: sift-digest
description: RETIRED — email orchestration now handled by briefing-prep.py cron job
user-invokable: true
---

# Email Digest (Retired)

This skill has been replaced by the cron-driven `briefing-prep.py` pipeline.

If you've been asked to check email or run the digest:
1. Check if `/workspace/briefing-input.json` exists — if so, the pipeline already ran
2. If it doesn't exist or is stale, run: `python3 /workspace/briefing-prep.py morning` (or afternoon)
3. Then follow the `daily-briefing` skill to compose and deliver

Do NOT attempt to spawn sub-agents or run workers directly. The pipeline handles this.
```

**Step 2: Deploy**

```bash
./scripts/skills-push.sh
```

**Step 3: Commit**

```bash
git add skills/sift-digest/SKILL.md
git commit -m "refactor: retire sift-digest skill, redirect to pipeline"
```

---

## Phase 3: Opus Layer (Option C)

### Task 7: Create Opus prompts

**Files:**
- Create: `opus-prompts/morning.md`
- Create: `opus-prompts/afternoon.md`

**Step 1: Write morning prompt**

```markdown
You are analysing today's briefing data for Marvin Barretto. Your job is creative synthesis — connect dots between calendar, email, tasks, and priorities that a simpler model would miss.

You will receive a JSON object (briefing-input.json). Respond with ONLY a valid JSON object matching the schema below.

## Rules

- Calendar events are FIXED FACTS from the Google Calendar API. Do not add, infer, or fabricate events.
- Build the day plan around real calendar events and real free gaps. A "free gap" is 30+ minutes between events.
- For email highlights, explain WHY each gem matters to Marvin specifically. Reference his priorities, interests, or goals.
- Look for cross-references: an email event that fits a calendar gap, a gem that connects to a vault task, a deal that matches a goal. These connections are your unique value.
- The surprise should be a genuine non-obvious connection. If you can't find one, set it to null. A weak surprise is worse than none.
- editorial_voice: one sentence capturing the day's shape, main risk, or key opportunity.
- If any pipeline step failed (check the `pipeline` object), note it in editorial_voice.

## Context

Marvin is based in Watford/South Oxhey, UK. He works on LocalShout (Next.js community platform) as his main project. He cares about: football (Watford FC, Arsenal), travel deals, live music and comedy, dating, fitness, Spanish language, AI/tech, and his personal finances. Check the `context_summary` for his current top priority.

## Output Schema

```json
{
  "generated_at": "ISO timestamp",
  "session": "morning or afternoon",
  "model": "your model name",
  "day_plan": [
    {
      "time": "HH:MM-HH:MM",
      "suggestion": "what to do",
      "source": "calendar|vault|gems|priorities",
      "reasoning": "one sentence why this fits here"
    }
  ],
  "email_highlights": [
    {
      "source": "sender or newsletter name",
      "headline": "specific article, event, or deal title",
      "editorial": "one sentence connecting to Marvin's context — be specific and confident",
      "links": ["url1", "url2"]
    }
  ],
  "surprise": {
    "fact": "the surprising connection or find",
    "strategy": "how you found it"
  },
  "editorial_voice": "one sentence on the day's shape"
}
```

Respond with ONLY the JSON object. No markdown fences, no explanation.
```

**Step 2: Write afternoon prompt**

```markdown
You are analysing the afternoon briefing data for Marvin Barretto. This is the rescue check-in — his morning plan may have gone off-track.

You will receive a JSON object (briefing-input.json) with `"session": "afternoon"`. Respond with ONLY a valid JSON object.

## Focus

- What calendar events remain today? Flag anything in the next 2 hours.
- Any new emails since morning that need attention? Prioritise time-sensitive items.
- What's realistically achievable in the remaining hours?
- What should Marvin let go of? Be honest — if the evening is packed, say "protect your energy."
- If there's a surprise candidate in the gems, present it. Afternoons are for the surprise game.

## Rules

- Calendar events are FIXED FACTS. Do not fabricate.
- Be honest about what's achievable. Don't suggest cramming 4 tasks into 2 hours.
- editorial_voice should acknowledge the day so far, not just the remaining hours.

## Context

Same as morning prompt — Marvin is in Watford/South Oxhey, UK. LocalShout is the main project. See `context_summary` for current priorities.

## Output Schema

Same as morning:

```json
{
  "generated_at": "ISO timestamp",
  "session": "afternoon",
  "model": "your model name",
  "day_plan": [{"time": "HH:MM-HH:MM", "suggestion": "...", "source": "...", "reasoning": "..."}],
  "email_highlights": [{"source": "...", "headline": "...", "editorial": "...", "links": ["..."]}],
  "surprise": {"fact": "...", "strategy": "..."} or null,
  "editorial_voice": "one sentence"
}
```

Respond with ONLY the JSON object. No markdown fences, no explanation.
```

**Step 3: Commit**

```bash
git add opus-prompts/morning.md opus-prompts/afternoon.md
git commit -m "feat: add Opus analysis prompts for morning and afternoon briefings"
```

---

### Task 8: Create `opus-briefing.sh` script

**Files:**
- Create: `scripts/opus-briefing.sh`

**Step 1: Write the script**

```bash
#!/bin/bash
set -euo pipefail

# Opus briefing analysis — runs on Mac, pulls data from VPS, pushes analysis back.
# Exits silently on any failure — VPS fallback handles it.

SESSION="${1:-morning}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPT_DIR="$(dirname "$SCRIPT_DIR")/opus-prompts"

if [ ! -f "$PROMPT_DIR/${SESSION}.md" ]; then
    echo "Unknown session: $SESSION" >&2
    exit 1
fi

# Pull briefing-input.json from VPS
INPUT=$(ssh jimbo 'cat /workspace/briefing-input.json' 2>/dev/null) || exit 0
[ -z "$INPUT" ] && exit 0

# Check it's for the right session
INPUT_SESSION=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session',''))" 2>/dev/null) || exit 0
if [ "$INPUT_SESSION" != "$SESSION" ]; then
    echo "Input session ($INPUT_SESSION) doesn't match requested ($SESSION), skipping" >&2
    exit 0
fi

# Check it's fresh (less than 2 hours old)
IS_FRESH=$(echo "$INPUT" | python3 -c "
import sys, json, datetime
d = json.load(sys.stdin)
gen = datetime.datetime.fromisoformat(d['generated_at'])
if gen.tzinfo is None:
    gen = gen.replace(tzinfo=datetime.timezone.utc)
age = (datetime.datetime.now(datetime.timezone.utc) - gen).total_seconds()
print('yes' if age < 7200 else 'no')
" 2>/dev/null) || exit 0

if [ "$IS_FRESH" != "yes" ]; then
    echo "briefing-input.json is stale, skipping" >&2
    exit 0
fi

# Run Opus analysis
PROMPT=$(cat "$PROMPT_DIR/${SESSION}.md")
ANALYSIS=$(echo "$INPUT" | claude -p "$PROMPT" 2>/dev/null) || exit 0

# Validate JSON before pushing
echo "$ANALYSIS" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'day_plan' in d" 2>/dev/null || exit 0

# Push to VPS
echo "$ANALYSIS" | ssh jimbo 'cat > /workspace/briefing-analysis.json' 2>/dev/null || exit 0

echo "Opus analysis pushed for $SESSION session"
```

**Step 2: Make executable and test locally**

```bash
chmod +x scripts/opus-briefing.sh
```

Test requires `briefing-input.json` on VPS (from Task 4). Run:

```bash
./scripts/opus-briefing.sh morning
```

Expected: Pulls input from VPS, runs Opus, pushes analysis back. Verify:

```bash
ssh jimbo 'cat /workspace/briefing-analysis.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d, indent=2))"'
```

**Step 3: Commit**

```bash
git add scripts/opus-briefing.sh
git commit -m "feat: add opus-briefing.sh for Mac-side Opus analysis"
```

---

### Task 9: Create launchd plist for Mac scheduling

**Files:**
- Create: `scripts/com.marvin.opus-briefing.morning.plist`
- Create: `scripts/com.marvin.opus-briefing.afternoon.plist`

**Step 1: Write morning plist**

Note: launchd uses local time. 06:50 UTC = 06:50 GMT / 07:50 BST. Adjust for current timezone. Using UTC-equivalent for consistency — Marvin should adjust `Hour` and `Minute` for BST when clocks change.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.marvin.opus-briefing.morning</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/marvinbarretto/development/openclaw/scripts/opus-briefing.sh</string>
        <string>morning</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>50</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/opus-briefing-morning.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/opus-briefing-morning.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>/Users/marvinbarretto</string>
    </dict>
</dict>
</plist>
```

**Step 2: Write afternoon plist** (same structure, different time and label)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.marvin.opus-briefing.afternoon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/marvinbarretto/development/openclaw/scripts/opus-briefing.sh</string>
        <string>afternoon</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>15</integer>
        <key>Minute</key>
        <integer>50</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/opus-briefing-afternoon.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/opus-briefing-afternoon.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>/Users/marvinbarretto</string>
    </dict>
</dict>
</plist>
```

**Step 3: Install plists** (do NOT run until Phase 1 is tested and stable)

```bash
cp scripts/com.marvin.opus-briefing.morning.plist ~/Library/LaunchAgents/
cp scripts/com.marvin.opus-briefing.afternoon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.marvin.opus-briefing.morning.plist
launchctl load ~/Library/LaunchAgents/com.marvin.opus-briefing.afternoon.plist
```

**Step 4: Commit**

```bash
git add scripts/com.marvin.opus-briefing.morning.plist scripts/com.marvin.opus-briefing.afternoon.plist
git commit -m "feat: add launchd plists for Opus briefing analysis"
```

---

## Phase 4: VPS Cron and Cleanup

### Task 10: Update VPS cron schedule

**Step 1: SSH to VPS and update root crontab**

```bash
ssh jimbo
sudo crontab -e
```

Replace the existing email/briefing crons with:

```
# 04:30 — vault task scoring (Gemini Flash) — keep as-is
30 4 * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/prioritise-tasks.py \
  >> /var/log/task-scoring.log 2>&1

# 05:00 — Google Tasks sweep — keep as-is
0 5 * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e GOOGLE_CALENDAR_CLIENT_ID=$GOOGLE_CALENDAR_CLIENT_ID \
              -e GOOGLE_CALENDAR_CLIENT_SECRET=$GOOGLE_CALENDAR_CLIENT_SECRET \
              -e GOOGLE_CALENDAR_REFRESH_TOKEN=$GOOGLE_CALENDAR_REFRESH_TOKEN \
              -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
              -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
              -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
  $(docker ps -q --filter name=openclaw-sbx) \
  sh -c 'python3 /workspace/tasks-helper.py pipeline || \
         python3 /workspace/alert.py "05:00 tasks sweep FAILED"' \
  >> /var/log/tasks-sweep.log 2>&1

# 06:15 — MORNING BRIEFING PIPELINE (NEW)
15 6 * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
              -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
              -e GOOGLE_CALENDAR_CLIENT_ID=$GOOGLE_CALENDAR_CLIENT_ID \
              -e GOOGLE_CALENDAR_CLIENT_SECRET=$GOOGLE_CALENDAR_CLIENT_SECRET \
              -e GOOGLE_CALENDAR_REFRESH_TOKEN=$GOOGLE_CALENDAR_REFRESH_TOKEN \
              -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
              -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
              -e LANGFUSE_PUBLIC_KEY=$LANGFUSE_PUBLIC_KEY \
              -e LANGFUSE_SECRET_KEY=$LANGFUSE_SECRET_KEY \
              -e LANGFUSE_HOST=$LANGFUSE_HOST \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/briefing-prep.py morning \
  >> /var/log/briefing-prep.log 2>&1

# 06:45 — model swap to Sonnet for briefing window
45 6 * * * /usr/local/bin/model-swap-local.sh sonnet >> /var/log/model-swap.log 2>&1

# 07:30 — model swap back to Kimi
30 7 * * * /usr/local/bin/model-swap-local.sh kimi >> /var/log/model-swap.log 2>&1

# 14:15 — AFTERNOON BRIEFING PIPELINE (NEW)
15 14 * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
              -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
              -e GOOGLE_CALENDAR_CLIENT_ID=$GOOGLE_CALENDAR_CLIENT_ID \
              -e GOOGLE_CALENDAR_CLIENT_SECRET=$GOOGLE_CALENDAR_CLIENT_SECRET \
              -e GOOGLE_CALENDAR_REFRESH_TOKEN=$GOOGLE_CALENDAR_REFRESH_TOKEN \
              -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
              -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
              -e LANGFUSE_PUBLIC_KEY=$LANGFUSE_PUBLIC_KEY \
              -e LANGFUSE_SECRET_KEY=$LANGFUSE_SECRET_KEY \
              -e LANGFUSE_HOST=$LANGFUSE_HOST \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/briefing-prep.py afternoon \
  >> /var/log/briefing-prep.log 2>&1

# 14:45 — model swap to Sonnet for afternoon briefing
45 14 * * * /usr/local/bin/model-swap-local.sh sonnet >> /var/log/model-swap.log 2>&1

# 15:30 — model swap back to Kimi
30 15 * * * /usr/local/bin/model-swap-local.sh kimi >> /var/log/model-swap.log 2>&1

# 20:00 — daily accountability report — keep as-is
0 20 * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
              -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/accountability-check.py \
  >> /var/log/accountability.log 2>&1
```

**Removed:**
- Hourly email fetch (`email-fetch-cron.py`)
- Hourly status check (`alert-check.py status`)

**Step 2: Verify cron is saved**

```bash
sudo crontab -l | grep briefing-prep
```

Expected: Both 06:15 and 14:15 entries visible.

---

### Task 11: Write ADR for the architecture shift

**Files:**
- Create: `decisions/042-briefing-pipeline-redesign.md`

**Step 1: Write the ADR**

Follow the template in `decisions/_template.md`. Key content:

- **Status:** Accepted
- **Context:** 400+ line skill prompts, workers never run, calendar fabrication, broken monitoring
- **Decision:** Move orchestration to `briefing-prep.py` (cron), add optional Opus analysis layer via Mac `claude -p`, slim Jimbo's skill to ~60 lines
- **Consequences:** More reliable pipeline, Opus-quality thinking at zero cost, graceful degradation, simpler monitoring. Adds Mac as optional dependency.

**Step 2: Commit**

```bash
git add decisions/042-briefing-pipeline-redesign.md
git commit -m "docs: ADR-042 briefing pipeline redesign"
```

---

### Task 12: Update CLAUDE.md and memory

**Files:**
- Modify: `CLAUDE.md` (update pipeline section, cron schedule, key files)
- Modify: Memory files

**Step 1: Update CLAUDE.md**

Key changes:
- Add `briefing-prep.py` to key files section
- Update cron schedule to reflect new timing
- Add `opus-prompts/` to repo structure
- Add `scripts/opus-briefing.sh` to key files
- Note retirement of hourly email fetch and hourly status checks
- Update "Email Pipeline" section to reference new architecture

**Step 2: Update memory**

Update MEMORY.md to reflect:
- New pipeline architecture (briefing-prep.py + Opus layer)
- Retired components (hourly fetch, hourly alerts, sift-digest)
- ADR-042

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for pipeline redesign"
```

---

## Execution Order and Dependencies

```
Phase 1 (foundation — do first, test thoroughly):
  Task 1 → Task 2 → Task 3 → Task 4

Phase 2 (skill — do after Phase 1 is verified on VPS):
  Task 5 → Task 6

Phase 3 (Opus layer — do after Phase 2, independent of VPS):
  Task 7 → Task 8 → Task 9

Phase 4 (cron and cleanup — do last):
  Task 10 → Task 11 → Task 12
```

**Review checkpoints:**
- After Task 4: Verify `briefing-input.json` is populated correctly on VPS
- After Task 6: Trigger a briefing and verify Jimbo reads from `briefing-input.json`
- After Task 8: Verify Opus analysis JSON is valid and pushed to VPS
- After Task 10: Wait for next morning briefing cycle and verify end-to-end
