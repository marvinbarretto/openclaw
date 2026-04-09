"""Shared producer registry for Jimbo runtime intake emitters."""

import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def build_producer_commands():
    """Return the canonical runtime intake producer command registry."""
    return {
        "dispatch-proposal": [
            sys.executable,
            os.path.join(SCRIPT_DIR, "dispatch.py"),
            "--emit-intake",
        ],
        "dispatch-worker": [
            sys.executable,
            os.path.join(SCRIPT_DIR, "dispatch-worker.py"),
            "--emit-intake",
        ],
    }


PRODUCER_COMMANDS = build_producer_commands()


def get_producer_command(producer):
    """Return the subprocess command for a registered runtime producer."""
    if producer not in PRODUCER_COMMANDS:
        raise ValueError(f"Unknown producer: {producer}")
    return list(PRODUCER_COMMANDS[producer])
