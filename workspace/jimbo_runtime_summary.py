#!/usr/bin/env python3
"""Summarize workflow decisions across one or more Jimbo intake payloads."""

import argparse
import json
import os
import sys

from jimbo_runtime_cli import load_intake_payload, run_intake_batch


def summarize_results(results):
    """Aggregate resolved runtime results into a control-plane summary."""
    if not isinstance(results, list):
        results = [results]

    summary = {
        "mode": "summary",
        "total": len(results),
        "workflows": {},
        "sources": {},
        "triggers": {},
        "route_decisions": {},
        "items": [],
    }

    for result in results:
        workflow = result.get("workflow") or "unknown"
        source = result.get("source") or "unknown"
        trigger = result.get("trigger") or "unknown"
        route_decision = result.get("route_decision") or "none"

        summary["workflows"][workflow] = summary["workflows"].get(workflow, 0) + 1
        summary["sources"][source] = summary["sources"].get(source, 0) + 1
        summary["triggers"][trigger] = summary["triggers"].get(trigger, 0) + 1
        summary["route_decisions"][route_decision] = summary["route_decisions"].get(route_decision, 0) + 1
        summary["items"].append({
            "task_id": result.get("task_id"),
            "title": result.get("title"),
            "workflow": workflow,
            "source": source,
            "trigger": trigger,
            "route_decision": route_decision,
        })

    return summary


def run_summary(payloads, *, runtime=None):
    """Resolve intake payloads and aggregate their workflow decisions."""
    results = run_intake_batch(payloads, runtime=runtime)
    return summarize_results(results)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-json", help="Raw normalized intake JSON")
    parser.add_argument("--intake-file", help="Path to a JSON file containing one or more intake payloads")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        payload = load_intake_payload(
            intake_json=args.intake_json,
            intake_file=args.intake_file,
        )
        summary = run_summary(payload)
    except Exception as exc:
        sys.stderr.write(f"[jimbo-summary] {exc}\n")
        return 1

    json.dump(summary, sys.stdout, sort_keys=True)
    sys.stdout.write(os.linesep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
