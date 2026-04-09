#!/usr/bin/env python3
"""CLI compatibility shim for producer-driven runtime roundtrips."""

from jimbo_runtime_ops import (
    build_runtime_cli_command,
    run_roundtrip,
    run_subprocess,
)


def main(argv=None):
    from jimbo_runtime_tool import main as runtime_tool_main
    return runtime_tool_main(["roundtrip", *(argv or [])])


if __name__ == "__main__":
    raise SystemExit(main())
