#!/usr/bin/env python3
"""Run a producer and generate an operational Jimbo runtime summary report."""

import argparse
import json
import sys

from jimbo_runtime_roundtrip import PRODUCER_COMMANDS, run_subprocess
from jimbo_runtime_summary import (
    log_summary_activity,
    run_summary,
    write_summary_artifact,
)


def load_producer_payloads(producer):
    """Run one producer in emit mode and parse its intake payloads."""
    if producer not in PRODUCER_COMMANDS:
        raise ValueError(f"Unknown producer: {producer}")
    return json.loads(run_subprocess(PRODUCER_COMMANDS[producer]))


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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--producer",
        choices=sorted(PRODUCER_COMMANDS),
        required=True,
        help="Which runtime intake producer to execute",
    )
    parser.add_argument("--output-file", help="Optional path to write the summary JSON artifact")
    parser.add_argument(
        "--log-activity",
        action="store_true",
        help="Record the generated summary via the orchestration activity API",
    )
    parser.add_argument(
        "--summary-id",
        help="Optional explicit activity task_id when using --log-activity",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        summary = run_report(
            args.producer,
            output_file=args.output_file,
            log_activity=args.log_activity,
            summary_id=args.summary_id,
        )
    except Exception as exc:
        sys.stderr.write(f"[jimbo-report] {exc}\n")
        return 1

    json.dump(summary, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
