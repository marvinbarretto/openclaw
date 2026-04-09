"""Shared execution core for Jimbo runtime control-plane requests."""

from types import SimpleNamespace

from jimbo_runtime_engine import load_intake_payload, run_intake_batch
from jimbo_runtime_ops import load_producer_payloads
from jimbo_runtime_requests import normalize_runtime_request
from jimbo_runtime_summary_core import (
    log_summary_activity,
    run_summary,
    write_summary_artifact,
)


def build_request_namespace(request):
    """Normalize one runtime request and expose it as a simple namespace."""
    request = normalize_runtime_request(request)
    return SimpleNamespace(
        producer=request.get("producer"),
        intake_json=request.get("intake_json"),
        intake_file=request.get("intake_file"),
        live=bool(request.get("live")),
        output_file=request.get("output_file"),
        log_activity=bool(request.get("log_activity")),
        summary_id=request.get("summary_id"),
    ), request["command"]


def load_command_payload(args):
    """Load runtime payloads from either a producer or explicit intake input."""
    if args.producer:
        return load_producer_payloads(args.producer)
    return load_intake_payload(
        intake_json=args.intake_json,
        intake_file=args.intake_file,
    )


def build_emit_output(args):
    """Return parsed emitted intake payloads for one producer."""
    return load_producer_payloads(args.producer)


def build_resolve_output(args):
    """Resolve or execute runtime intake payloads."""
    payload = load_command_payload(args)
    return run_intake_batch(payload, live=args.live)


def build_summary_output(args, *, include_producer=False):
    """Build a summary result and optionally persist related side effects."""
    payload = load_command_payload(args)
    summary = run_summary(payload)
    if include_producer and args.producer:
        summary["producer"] = args.producer
    if args.log_activity:
        summary["activity_id"] = log_summary_activity(summary, summary_id=args.summary_id)
    if args.output_file:
        write_summary_artifact(summary, args.output_file)
    return summary


def build_report_output(args):
    """Build the report surface output."""
    return build_summary_output(args, include_producer=True)


def run_runtime_request(request):
    """Execute one normalized runtime request and return a structured response."""
    delegated_args, command = build_request_namespace(request)
    if command == "emit":
        result = build_emit_output(delegated_args)
    elif command == "resolve":
        result = build_resolve_output(delegated_args)
    elif command == "summary":
        result = build_summary_output(delegated_args)
    elif command == "report":
        result = build_report_output(delegated_args)
    else:
        raise ValueError(f"Unsupported runtime request command: {command}")
    return {
        "command": command,
        "result": result,
    }
