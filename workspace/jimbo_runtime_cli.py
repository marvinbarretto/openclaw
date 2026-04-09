#!/usr/bin/env python3
"""CLI entrypoint for running normalized intake through the Jimbo runtime."""

import argparse
import json
import os
import sys

from jimbo_runtime import JimboIntakeEnvelope, get_default_runtime
from jimbo_runtime_contract import normalize_intake_payload


def load_intake_payload(*, intake_json=None, intake_file=None):
    """Load one normalized intake payload or a payload list."""
    if bool(intake_json) == bool(intake_file):
        raise ValueError("Provide exactly one of intake_json or intake_file")

    if intake_json:
        return json.loads(intake_json)

    with open(intake_file) as f:
        return json.load(f)


def run_intake(payload, *, live=False, runtime=None):
    """Resolve or execute one normalized intake payload through the runtime."""
    runtime = runtime or get_default_runtime()
    payload = normalize_intake_payload(payload, live=live)
    envelope = JimboIntakeEnvelope.from_mapping(payload)
    selection = runtime.resolve_workflow(envelope)

    result = {
        "workflow": selection.workflow.name,
        "task_id": selection.task.task_id,
        "title": selection.task.title,
        "source": envelope.source,
        "trigger": envelope.trigger,
        "live": bool(live),
    }

    if not live:
        result["mode"] = "resolved"
        return result

    intake_activity_id, route_activity_id = None, None
    runtime_result = runtime.begin(
        envelope,
        intake_reason=payload.get("intake_reason") or "Runtime intake received",
        route=payload["route"],
        route_reason=payload.get("route_reason"),
        delegate=payload.get("delegate"),
        changed=payload.get("changed"),
        metadata=payload.get("runtime_metadata") or payload.get("metadata"),
    )
    intake_activity_id = runtime_result.intake_activity_id
    route_activity_id = runtime_result.route_activity_id
    result["mode"] = "executed"
    result["intake_activity_id"] = intake_activity_id
    result["route_activity_id"] = route_activity_id
    return result


def run_intake_batch(payloads, *, live=False, runtime=None):
    """Resolve or execute one or more intake payloads through the runtime."""
    runtime = runtime or get_default_runtime()
    if isinstance(payloads, list):
        return [run_intake(payload, live=live, runtime=runtime) for payload in payloads]
    return run_intake(payloads, live=live, runtime=runtime)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-json", help="Raw normalized intake JSON")
    parser.add_argument("--intake-file", help="Path to a JSON file containing one intake payload")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute intake logging instead of dry-run workflow resolution",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        payload = load_intake_payload(
            intake_json=args.intake_json,
            intake_file=args.intake_file,
        )
        result = run_intake_batch(payload, live=args.live)
    except Exception as exc:
        sys.stderr.write(f"[jimbo-runtime] {exc}\n")
        return 1

    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write(os.linesep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
