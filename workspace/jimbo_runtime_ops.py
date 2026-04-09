"""Operational helpers for producer-driven Jimbo runtime flows."""

import json
import os
import subprocess
import sys

from jimbo_runtime_producers import PRODUCER_COMMANDS, get_producer_command
from jimbo_runtime_summary_core import (
    log_summary_activity,
    run_summary,
    write_summary_artifact,
)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_subprocess(cmd, *, stdin_text=None):
    """Run one subprocess and return its stdout."""
    proc = subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"command failed: {' '.join(cmd)}")
    return proc.stdout


def emit_producer_output(producer):
    """Run one producer in emit mode and return its raw intake JSON."""
    return run_subprocess(get_producer_command(producer))


def build_runtime_cli_command(producer, *, live=False, summary=False):
    command = "summary" if summary else "resolve"
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "jimbo_runtime_tool.py"),
        command,
        "--producer",
        producer,
    ]
    if live and not summary:
        cmd.append("--live")
    return cmd


def run_roundtrip(producer, *, live=False, summary=False):
    """Emit intake payloads from a producer and pass them to the runtime CLI."""
    if live and summary:
        raise ValueError("summary mode does not support live execution")

    return run_subprocess(build_runtime_cli_command(producer, live=live, summary=summary))


def load_producer_payloads(producer):
    """Run one producer in emit mode and parse its intake payloads."""
    return json.loads(emit_producer_output(producer))


def run_report(producer, *, output_file=None, log_activity=False,
               summary_id=None, runtime=None, logger=None):
    """Generate a runtime summary report from a producer's emitted intake."""
    payloads = load_producer_payloads(producer)
    summary = run_summary(payloads, runtime=runtime)
    summary["producer"] = producer

    if log_activity:
        summary["activity_id"] = log_summary_activity(
            summary,
            summary_id=summary_id,
            logger=logger,
        )
    if output_file:
        write_summary_artifact(summary, output_file)
    return summary
