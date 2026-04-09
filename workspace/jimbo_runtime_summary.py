#!/usr/bin/env python3
"""CLI compatibility shim for summarizing runtime intake payloads."""

from jimbo_runtime_summary_core import (
    log_summary_activity,
    run_summary,
    summarize_results,
    write_summary_artifact,
)


def main(argv=None):
    from jimbo_runtime_tool import main as runtime_tool_main
    return runtime_tool_main(["summary", *(argv or [])])


if __name__ == "__main__":
    raise SystemExit(main())
