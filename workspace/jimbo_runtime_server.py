#!/usr/bin/env python3
"""Long-lived process entrypoint for streamed Jimbo runtime requests."""

import argparse
import json
import sys

from jimbo_runtime_request_service import stream_runtime_requests
from jimbo_runtime_requests import iter_runtime_requests


def serve_request_stream(*, request_file, continue_on_error=True, output_stream=None):
    """Execute a newline-delimited runtime request stream and write responses."""
    output_stream = output_stream or sys.stdout
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
        "responses": responses,
        "errors": errors,
        "continue_on_error": bool(continue_on_error),
    }


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
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        serve_request_stream(
            request_file=args.request_file,
            continue_on_error=not args.fail_fast,
            output_stream=sys.stdout,
        )
        return 0
    except Exception as exc:
        sys.stderr.write(f"[jimbo-runtime-server] {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
