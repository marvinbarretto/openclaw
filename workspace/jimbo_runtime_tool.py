#!/usr/bin/env python3
"""Top-level CLI for Jimbo runtime control-plane commands."""

import argparse
import json
import sys

from jimbo_runtime_engine import load_intake_payload, run_intake_batch
from jimbo_runtime_producers import PRODUCER_COMMANDS
from jimbo_runtime_ops import run_report, run_roundtrip
from jimbo_runtime_summary_core import (
    log_summary_activity,
    run_summary,
    write_summary_artifact,
)


def cmd_producers(_args):
    print(json.dumps(sorted(PRODUCER_COMMANDS)))
    return 0


def cmd_resolve(args):
    payload = load_intake_payload(
        intake_json=args.intake_json,
        intake_file=args.intake_file,
    )
    result = run_intake_batch(payload, live=args.live)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def cmd_summary(args):
    payload = load_intake_payload(
        intake_json=args.intake_json,
        intake_file=args.intake_file,
    )
    summary = run_summary(payload)
    if args.log_activity:
        summary["activity_id"] = log_summary_activity(summary, summary_id=args.summary_id)
    if args.output_file:
        write_summary_artifact(summary, args.output_file)
    json.dump(summary, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def cmd_roundtrip(args):
    output = run_roundtrip(
        args.producer,
        live=args.live,
        summary=args.summary,
    )
    sys.stdout.write(output)
    return 0


def cmd_report(args):
    summary = run_report(
        args.producer,
        output_file=args.output_file,
        log_activity=args.log_activity,
        summary_id=args.summary_id,
    )
    json.dump(summary, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    producers_parser = subparsers.add_parser("producers", help="List registered runtime intake producers")
    producers_parser.set_defaults(handler=cmd_producers)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve or execute runtime intake payloads")
    resolve_parser.add_argument("--intake-json", help="Raw normalized intake JSON")
    resolve_parser.add_argument("--intake-file", help="Path to a JSON file containing one or more intake payloads")
    resolve_parser.add_argument("--live", action="store_true", help="Execute intake logging instead of dry-run resolution")
    resolve_parser.set_defaults(handler=cmd_resolve)

    summary_parser = subparsers.add_parser("summary", help="Summarize runtime intake payloads")
    summary_parser.add_argument("--intake-json", help="Raw normalized intake JSON")
    summary_parser.add_argument("--intake-file", help="Path to a JSON file containing one or more intake payloads")
    summary_parser.add_argument("--output-file", help="Optional path to write the summary JSON artifact")
    summary_parser.add_argument("--log-activity", action="store_true", help="Record the summary via the orchestration activity API")
    summary_parser.add_argument("--summary-id", help="Optional explicit activity task_id when using --log-activity")
    summary_parser.set_defaults(handler=cmd_summary)

    roundtrip_parser = subparsers.add_parser("roundtrip", help="Run a producer and pass its output into runtime surfaces")
    roundtrip_parser.add_argument("--producer", choices=sorted(PRODUCER_COMMANDS), required=True)
    roundtrip_parser.add_argument("--live", action="store_true", help="Execute the runtime CLI in live mode")
    roundtrip_parser.add_argument("--summary", action="store_true", help="Send the producer payloads to the runtime summary command")
    roundtrip_parser.set_defaults(handler=cmd_roundtrip)

    report_parser = subparsers.add_parser("report", help="Run a producer and emit an operational summary report")
    report_parser.add_argument("--producer", choices=sorted(PRODUCER_COMMANDS), required=True)
    report_parser.add_argument("--output-file", help="Optional path to write the summary JSON artifact")
    report_parser.add_argument("--log-activity", action="store_true", help="Record the generated summary via the orchestration activity API")
    report_parser.add_argument("--summary-id", help="Optional explicit activity task_id when using --log-activity")
    report_parser.set_defaults(handler=cmd_report)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except Exception as exc:
        sys.stderr.write(f"[jimbo-runtime-tool] {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
