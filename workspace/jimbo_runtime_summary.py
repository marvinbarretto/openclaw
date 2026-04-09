#!/usr/bin/env python3
"""Summarize workflow decisions across one or more Jimbo intake payloads."""

import argparse
import datetime
import json
import os
import sys

import orchestration_helper
from jimbo_runtime_cli import load_intake_payload, run_intake_batch


def summarize_results(results):
    """Aggregate resolved runtime results into a control-plane summary."""
    if not isinstance(results, list):
        results = [results]

    summary = {
        "mode": "summary",
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
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


def log_summary_activity(summary, *, summary_id=None, logger=None):
    """Record a runtime summary as an orchestration activity."""
    logger = logger or orchestration_helper.log_decision
    summary_id = summary_id or f"runtime-summary-{summary['generated_at']}"

    workflow_counts = summary.get("workflows") or {}
    workflow_label = ", ".join(
        f"{name}={count}" for name, count in sorted(workflow_counts.items())
    ) or "no workflows"
    title = f"{summary['total']} intake items ({workflow_label})"

    return logger(
        "report",
        summary_id,
        title=title,
        task_source="runtime-summary",
        reason="Aggregated runtime intake decisions",
        report={
            "status": "summarized",
            "summary": title,
        },
        changed={
            "total": summary["total"],
            "workflows": summary.get("workflows"),
            "sources": summary.get("sources"),
            "triggers": summary.get("triggers"),
            "route_decisions": summary.get("route_decisions"),
        },
        metadata={
            "summary": summary,
        },
    )


def write_summary_artifact(summary, output_file):
    """Write a machine-readable summary artifact to disk."""
    output_dir = os.path.dirname(os.path.abspath(output_file))
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(summary, f, sort_keys=True, indent=2)
        f.write(os.linesep)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-json", help="Raw normalized intake JSON")
    parser.add_argument("--intake-file", help="Path to a JSON file containing one or more intake payloads")
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
        payload = load_intake_payload(
            intake_json=args.intake_json,
            intake_file=args.intake_file,
        )
        summary = run_summary(payload)
        if args.output_file:
            write_summary_artifact(summary, args.output_file)
        if args.log_activity:
            summary["activity_id"] = log_summary_activity(
                summary,
                summary_id=args.summary_id,
            )
    except Exception as exc:
        sys.stderr.write(f"[jimbo-summary] {exc}\n")
        return 1

    json.dump(summary, sys.stdout, sort_keys=True)
    sys.stdout.write(os.linesep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
