#!/usr/bin/env python3
"""Long-lived process entrypoint for streamed Jimbo runtime requests."""

import argparse
import datetime
import json
import os
import sys

from jimbo_runtime_request_service import stream_runtime_requests
from jimbo_runtime_requests import iter_runtime_requests


def serve_request_stream(*, request_file, continue_on_error=True, output_stream=None):
    """Execute a newline-delimited runtime request stream and write responses."""
    output_stream = output_stream or sys.stdout
    started_at = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    responses = 0
    errors = 0

    for response in stream_runtime_requests(
        iter_runtime_requests(request_file=request_file),
        continue_on_error=continue_on_error,
    ):
        json.dump(response, output_stream, sort_keys=True)
        output_stream.write("\n")
        responses += 1
        if response.get("ok") is False:
            errors += 1

    return {
        "started_at": started_at,
        "completed_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        "request_file": request_file,
        "responses": responses,
        "errors": errors,
        "continue_on_error": bool(continue_on_error),
    }


def write_server_stats(stats, stats_file):
    """Persist machine-readable runtime server stats."""
    output_dir = os.path.dirname(os.path.abspath(stats_file))
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    with open(stats_file, "w") as f:
        json.dump(stats, f, sort_keys=True, indent=2)
        f.write(os.linesep)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--request-file",
        default="-",
        help="Path to a newline-delimited JSON request stream, or - for stdin",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first request error instead of emitting error responses",
    )
    parser.add_argument(
        "--stats-file",
        help="Optional path to write machine-readable server run stats",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        stats = serve_request_stream(
            request_file=args.request_file,
            continue_on_error=not args.fail_fast,
            output_stream=sys.stdout,
        )
        if args.stats_file:
            write_server_stats(stats, args.stats_file)
        return 0
    except Exception as exc:
        sys.stderr.write(f"[jimbo-runtime-server] {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
