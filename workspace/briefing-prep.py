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
ACTIVITY_LOG_SCRIPT = os.path.join(_script_dir, "activity-log.py")
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


def log_to_activity(session, pipeline_status):
    """Log pipeline completion to activity-log."""
    fetch = pipeline_status.get("email_fetch", {})
    reader = pipeline_status.get("reader", {})
    cal = pipeline_status.get("calendar", {})
    vault = pipeline_status.get("vault", {})

    email_count = fetch.get("count", 0)
    gem_count = reader.get("gems", 0)
    event_count = cal.get("events", 0)
    task_count = vault.get("tasks", 0)

    label = "Morning" if session == "morning" else "Afternoon"
    any_failed = any(
        v.get("status") in ("failed", "timeout", "error")
        for v in pipeline_status.values()
    )
    outcome = "partial" if any_failed else "success"

    try:
        subprocess.run([
            sys.executable, ACTIVITY_LOG_SCRIPT, "log",
            "--task", "briefing",
            "--description", f"{label} pipeline: {email_count} emails, {gem_count} gems, {event_count} events, {task_count} vault tasks",
            "--outcome", outcome,
            "--rationale", f"session={session}, pipeline-driven (ADR-042)",
        ], timeout=10)
    except Exception as e:
        sys.stderr.write(f"Activity log failed: {e}\n")


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
            alert(f"briefing-prep: {name} failed: {error}")
            return False, {"status": "failed", "error": error}
        return True, {"status": "ok"}
    except subprocess.TimeoutExpired:
        alert(f"briefing-prep: {name} timed out after {timeout}s")
        return False, {"status": "timeout"}
    except Exception as e:
        alert(f"briefing-prep: {name} error: {e}")
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
             "list-events", "--days", "1", "--primary-only"],
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
    log_to_activity(session, pipeline_status)
    send_status_alert(session, pipeline_status, duration_ms)

    return output


def select_vault_tasks(limit=5, vault_dir=None):
    """Select top vault tasks by priority score. Returns (tasks_list, status_dict)."""
    vault_dir = vault_dir or os.path.join("/workspace", "vault", "notes")
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
        parts.append(f"{count} emails -> {shortlisted} shortlisted -> {gem_count} gems")
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
    icon = "FAIL" if any_failed else "OK"

    alert(f"[{icon}] {label} pipeline: {' | '.join(parts)}")


def main():
    parser = argparse.ArgumentParser(description="Briefing pipeline orchestrator")
    parser.add_argument("session", choices=["morning", "afternoon"])
    parser.add_argument("--dry-run", action="store_true", help="Assemble without running workers")
    args = parser.parse_args()

    output = run_pipeline(args.session, dry_run=args.dry_run)
    print(json.dumps({"status": "ok", "path": OUTPUT_PATH}, indent=2))


if __name__ == "__main__":
    main()
