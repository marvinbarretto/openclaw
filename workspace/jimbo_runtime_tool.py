#!/usr/bin/env python3
"""Top-level CLI for Jimbo runtime control-plane commands."""

import argparse
import json
import sys

from jimbo_runtime_executor import (
    build_report_output,
    build_resolve_output,
    build_summary_output,
)
from jimbo_runtime_inbox_service import enqueue_producer_requests
from jimbo_runtime_request_service import execute_runtime_request
from jimbo_runtime_producers import PRODUCER_COMMANDS
from jimbo_runtime_requests import (
    load_runtime_request,
)
from jimbo_runtime_ops import (
    emit_producer_output,
)
from jimbo_runtime_server import serve_request_stream


def cmd_producers(_args):
    print(json.dumps(sorted(PRODUCER_COMMANDS)))
    return 0


def cmd_request(args):
    request = load_runtime_request(
        request_json=args.request_json,
        request_file=args.request_file,
    )
    response = execute_runtime_request(request)
    json.dump(response, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def cmd_enqueue(args):
    result = enqueue_producer_requests(args.producer, live=args.live)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def cmd_serve(args):
    serve_request_stream(
        request_file=args.request_file,
        continue_on_error=True,
        output_stream=sys.stdout,
    )
    return 0


def cmd_resolve(args):
    result = build_resolve_output(args)
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
    summary = build_report_output(args)
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

    serve_parser = subparsers.add_parser("serve", help="Execute newline-delimited runtime request objects")
    serve_parser.add_argument("--request-file", required=True, help="Path to a newline-delimited JSON request stream, or - for stdin")
    serve_parser.set_defaults(handler=cmd_serve)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve or execute runtime intake payloads")
    add_payload_source_args(resolve_parser)
    resolve_parser.add_argument("--live", action="store_true", help="Execute intake logging instead of dry-run resolution")
    resolve_parser.set_defaults(handler=cmd_resolve)

    emit_parser = subparsers.add_parser("emit", help="Emit raw normalized intake JSON from a registered producer")
    emit_parser.add_argument("--producer", choices=sorted(PRODUCER_COMMANDS), required=True)
    emit_parser.set_defaults(handler=cmd_emit)

    enqueue_parser = subparsers.add_parser("enqueue", help="Submit producer payloads into the runtime inbox")
    enqueue_parser.add_argument("--producer", choices=sorted(PRODUCER_COMMANDS), required=True)
    enqueue_parser.add_argument("--live", action="store_true", help="Queue live runtime execution requests")
    enqueue_parser.set_defaults(handler=cmd_enqueue)

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
