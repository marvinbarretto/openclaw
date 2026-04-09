#!/usr/bin/env python3
"""Run a Jimbo intake producer and pipe its payloads into the runtime CLI."""

import argparse
import os
import subprocess
import sys

from jimbo_runtime_producers import PRODUCER_COMMANDS, get_producer_command

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


def build_runtime_cli_command(*, live=False, summary=False):
    script_name = "jimbo_runtime_summary.py" if summary else "jimbo_runtime_cli.py"
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, script_name),
        "--intake-file",
        "-",
    ]
    if live and not summary:
        cmd.append("--live")
    return cmd


def run_roundtrip(producer, *, live=False, summary=False):
    """Emit intake payloads from a producer and pass them to the runtime CLI."""
    if live and summary:
        raise ValueError("summary mode does not support live execution")

    producer_output = run_subprocess(get_producer_command(producer))
    runtime_output = run_subprocess(
        build_runtime_cli_command(live=live, summary=summary),
        stdin_text=producer_output,
    )
    return runtime_output


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--producer",
        choices=sorted(PRODUCER_COMMANDS),
        required=True,
        help="Which runtime intake producer to execute",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute the runtime CLI in live mode",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Send the producer payloads to the runtime summary command",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        output = run_roundtrip(args.producer, live=args.live, summary=args.summary)
    except Exception as exc:
        sys.stderr.write(f"[jimbo-roundtrip] {exc}\n")
        return 1

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
