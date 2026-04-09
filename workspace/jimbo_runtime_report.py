#!/usr/bin/env python3
"""CLI compatibility shim for operational runtime summary reports."""

from jimbo_runtime_ops import load_producer_payloads, run_report


def main(argv=None):
    from jimbo_runtime_tool import main as runtime_tool_main
    return runtime_tool_main(["report", *(argv or [])])


if __name__ == "__main__":
    raise SystemExit(main())
