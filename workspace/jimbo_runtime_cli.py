#!/usr/bin/env python3
"""CLI compatibility shim for resolving runtime intake payloads."""

from jimbo_runtime_engine import load_intake_payload, run_intake, run_intake_batch


def main(argv=None):
    from jimbo_runtime_tool import main as runtime_tool_main
    return runtime_tool_main(["resolve", *(argv or [])])


if __name__ == "__main__":
    raise SystemExit(main())
