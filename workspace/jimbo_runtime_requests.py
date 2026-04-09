"""Machine-readable request contract for Jimbo runtime control-plane actions."""

import json
import sys


REQUEST_COMMANDS = {"emit", "resolve", "summary", "report"}


def load_runtime_request(*, request_json=None, request_file=None):
    """Load one runtime request object from JSON text, a file, or stdin."""
    if bool(request_json) == bool(request_file):
        raise ValueError("Provide exactly one of request_json or request_file")

    if request_json:
        return json.loads(request_json)

    if request_file == "-":
        return json.load(sys.stdin)

    with open(request_file) as f:
        return json.load(f)


def normalize_runtime_request(request):
    """Validate and normalize one runtime control-plane request."""
    if not isinstance(request, dict):
        raise ValueError("Runtime request must be a JSON object")

    command = request.get("command")
    if command not in REQUEST_COMMANDS:
        raise ValueError(f"Unsupported runtime request command: {command}")

    normalized = {"command": command}

    for field in (
        "producer",
        "intake_json",
        "intake_file",
        "live",
        "output_file",
        "log_activity",
        "summary_id",
    ):
        if field in request:
            normalized[field] = request[field]

    if command == "emit":
        if not normalized.get("producer"):
            raise ValueError("emit requests require producer")
        return normalized

    if command in {"resolve", "summary", "report"}:
        has_producer = bool(normalized.get("producer"))
        has_inline_payload = bool(normalized.get("intake_json"))
        has_file_payload = bool(normalized.get("intake_file"))
        source_count = sum([has_producer, has_inline_payload, has_file_payload])
        if command == "report":
            if not has_producer or source_count != 1:
                raise ValueError("report requests require exactly one producer source")
        elif source_count != 1:
            raise ValueError(f"{command} requests require exactly one payload source")

    if command == "resolve" and "live" in normalized:
        normalized["live"] = bool(normalized["live"])

    if command == "summary" and "live" in normalized:
        raise ValueError("summary requests do not support live execution")

    return normalized


def iter_runtime_requests(*, request_file):
    """Yield newline-delimited runtime request objects from a file or stdin."""
    if not request_file:
        raise ValueError("request_file is required")

    stream = sys.stdin if request_file == "-" else open(request_file)
    try:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)
    finally:
        if stream is not sys.stdin:
            stream.close()
