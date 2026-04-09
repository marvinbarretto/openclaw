#!/usr/bin/env python3
"""Top-level CLI for Jimbo runtime control-plane commands."""

import argparse
import json
import sys

from jimbo_runtime_engine import load_intake_payload, run_intake_batch
from jimbo_runtime_producers import PRODUCER_COMMANDS
from jimbo_runtime_requests import load_runtime_request, normalize_runtime_request
from jimbo_runtime_ops import (
    emit_producer_output,
    load_producer_payloads,
)
from jimbo_runtime_summary_core import (
    log_summary_activity,
    run_summary,
    write_summary_artifact,
)


def cmd_producers(_args):
    print(json.dumps(sorted(PRODUCER_COMMANDS)))
    return 0


def build_request_namespace(request):
    request = normalize_runtime_request(request)
    return argparse.Namespace(
        producer=request.get("producer"),
        intake_json=request.get("intake_json"),
        intake_file=request.get("intake_file"),
        live=bool(request.get("live")),
        output_file=request.get("output_file"),
        log_activity=bool(request.get("log_activity")),
        summary_id=request.get("summary_id"),
    ), request["command"]


def cmd_request(args):
    request = load_runtime_request(
        request_json=args.request_json,
        request_file=args.request_file,
    )
    delegated_args, command = build_request_namespace(request)
    if command == "emit":
        return cmd_emit(delegated_args)
    if command == "resolve":
        return cmd_resolve(delegated_args)
    if command == "summary":
        return cmd_summary(delegated_args)
    if command == "report":
        return cmd_report(delegated_args)
    raise ValueError(f"Unsupported runtime request command: {command}")


def load_command_payload(args):
    if args.producer:
        return load_producer_payloads(args.producer)
    return load_intake_payload(
        intake_json=args.intake_json,
        intake_file=args.intake_file,
    )


def cmd_resolve(args):
    payload = load_command_payload(args)
    result = run_intake_batch(payload, live=args.live)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def cmd_emit(args):
    sys.stdout.write(emit_producer_output(args.producer))
    return 0


def cmd_summary(args):
    summary = build_summary_output(args)
    json.dump(summary, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def build_summary_output(args, *, include_producer=False):
    payload = load_command_payload(args)
    summary = run_summary(payload)
    if include_producer and args.producer:
        summary["producer"] = args.producer
    if args.log_activity:
        summary["activity_id"] = log_summary_activity(summary, summary_id=args.summary_id)
    if args.output_file:
        write_summary_artifact(summary, args.output_file)
    return summary


def cmd_roundtrip(args):
    if args.live and args.summary:
        raise ValueError("summary mode does not support live execution")
    if args.summary:
        return cmd_summary(argparse.Namespace(
            producer=args.producer,
            intake_json=None,
            intake_file=None,
            output_file=None,
            log_activity=False,
            summary_id=None,
        ))
    return cmd_resolve(argparse.Namespace(
        producer=args.producer,
        intake_json=None,
        intake_file=None,
        live=args.live,
    ))


def cmd_report(args):
    summary = build_summary_output(args, include_producer=True)
    json.dump(summary, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def add_payload_source_args(parser):
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--producer", choices=sorted(PRODUCER_COMMANDS), help="Registered runtime intake producer")
    source_group.add_argument("--intake-json", help="Raw normalized intake JSON")
    source_group.add_argument("--intake-file", help="Path to a JSON file containing one or more intake payloads")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    producers_parser = subparsers.add_parser("producers", help="List registered runtime intake producers")
    producers_parser.set_defaults(handler=cmd_producers)

    request_parser = subparsers.add_parser("request", help="Execute one machine-readable runtime control-plane request")
    request_source = request_parser.add_mutually_exclusive_group(required=True)
    request_source.add_argument("--request-json", help="Raw runtime request JSON")
    request_source.add_argument("--request-file", help="Path to a JSON file containing one runtime request object")
    request_parser.set_defaults(handler=cmd_request)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve or execute runtime intake payloads")
    add_payload_source_args(resolve_parser)
    resolve_parser.add_argument("--live", action="store_true", help="Execute intake logging instead of dry-run resolution")
    resolve_parser.set_defaults(handler=cmd_resolve)

    emit_parser = subparsers.add_parser("emit", help="Emit raw normalized intake JSON from a registered producer")
    emit_parser.add_argument("--producer", choices=sorted(PRODUCER_COMMANDS), required=True)
    emit_parser.set_defaults(handler=cmd_emit)

    summary_parser = subparsers.add_parser("summary", help="Summarize runtime intake payloads")
    add_payload_source_args(summary_parser)
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
