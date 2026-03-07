#!/usr/bin/env python3
"""Tests for briefing-prep.py pipeline orchestrator."""

import importlib.util
import json
import os
import subprocess
import sys

# Load briefing-prep.py (hyphenated filename can't be imported normally)
_module_path = os.path.join(os.path.dirname(__file__), "..", "briefing-prep.py")
_spec = importlib.util.spec_from_file_location("briefing_prep", _module_path)
briefing_prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(briefing_prep)

select_vault_tasks = briefing_prep.select_vault_tasks
run_step = briefing_prep.run_step


# --- CLI acceptance tests ---

def test_briefing_prep_cli_accepts_morning():
    """briefing-prep.py accepts 'morning' subcommand without crashing."""
    result = subprocess.run(
        [sys.executable, "workspace/briefing-prep.py", "morning", "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_briefing_prep_cli_accepts_afternoon():
    result = subprocess.run(
        [sys.executable, "workspace/briefing-prep.py", "afternoon", "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_briefing_prep_cli_rejects_unknown():
    result = subprocess.run(
        [sys.executable, "workspace/briefing-prep.py", "midnight"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


# --- Vault task selection tests ---

def test_select_vault_tasks_picks_high_priority(tmp_path):
    """Vault task selector returns tasks with priority >= 7, sorted descending."""
    (tmp_path / "high.md").write_text(
        '---\ntype: task\nstatus: active\npriority: 9\ntitle: "High"\n---\n'
    )
    (tmp_path / "medium.md").write_text(
        '---\ntype: task\nstatus: active\npriority: 5\ntitle: "Medium"\n---\n'
    )
    (tmp_path / "also_high.md").write_text(
        '---\ntype: task\nstatus: active\npriority: 8\ntitle: "Also High"\n---\n'
    )

    tasks, status = select_vault_tasks(vault_dir=str(tmp_path))
    assert status["status"] == "ok"
    assert len(tasks) == 2
    assert tasks[0]["priority"] == 9
    assert tasks[1]["priority"] == 8


def test_select_vault_tasks_skips_non_tasks(tmp_path):
    """Vault task selector ignores non-task types and inactive items."""
    (tmp_path / "bookmark.md").write_text(
        '---\ntype: bookmark\nstatus: active\npriority: 10\ntitle: "Link"\n---\n'
    )
    (tmp_path / "done.md").write_text(
        '---\ntype: task\nstatus: done\npriority: 9\ntitle: "Done"\n---\n'
    )

    tasks, status = select_vault_tasks(vault_dir=str(tmp_path))
    assert len(tasks) == 0


def test_select_vault_tasks_missing_dir():
    """Vault task selector handles missing directory gracefully."""
    tasks, status = select_vault_tasks(vault_dir="/nonexistent/path")
    assert tasks == []
    assert status["status"] == "failed"


def test_select_vault_tasks_respects_limit(tmp_path):
    """Vault task selector respects the limit parameter."""
    for i in range(10):
        (tmp_path / f"task_{i}.md").write_text(
            f'---\ntype: task\nstatus: active\npriority: {10 - i}\ntitle: "Task {i}"\n---\n'
        )

    tasks, status = select_vault_tasks(limit=3, vault_dir=str(tmp_path))
    assert len(tasks) == 3
    assert tasks[0]["priority"] == 10
    assert tasks[2]["priority"] == 8


# --- run_step tests ---

def test_run_step_captures_success():
    """run_step returns ok status on success."""
    ok, status = run_step("test-ok", [sys.executable, "-c", "print('hello')"])
    assert ok is True
    assert status["status"] == "ok"


def test_run_step_captures_failure():
    """run_step returns failure status when command exits non-zero."""
    ok, status = run_step("test-fail", [sys.executable, "-c", "import sys; sys.exit(1)"])
    assert ok is False
    assert status["status"] == "failed"


def test_run_step_captures_timeout():
    """run_step returns timeout status when command exceeds timeout."""
    ok, status = run_step(
        "test-timeout",
        [sys.executable, "-c", "import time; time.sleep(10)"],
        timeout=1,
    )
    assert ok is False
    assert status["status"] == "timeout"


# --- Activity logging tests ---

def test_pipeline_calls_activity_log(tmp_path, monkeypatch):
    """briefing-prep.py must log to activity-log.py after a pipeline run."""
    assert hasattr(briefing_prep, "log_to_activity"), \
        "briefing-prep.py must have a log_to_activity function"

    import inspect
    sig = inspect.signature(briefing_prep.log_to_activity)
    params = list(sig.parameters.keys())
    assert "session" in params, "log_to_activity must accept 'session'"
    assert "pipeline_status" in params, "log_to_activity must accept 'pipeline_status'"
