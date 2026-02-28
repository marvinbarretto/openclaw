#!/usr/bin/env python3
"""Export Jimbo status data from the openclaw repo.

Parses ADRs, CAPABILITIES.md, and static architecture info into
workspace/jimbo-status.json for the personal site dashboard.

Usage: python3 scripts/export-status.py
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECISIONS_DIR = os.path.join(REPO_ROOT, "decisions")
CAPABILITIES_FILE = os.path.join(REPO_ROOT, "CAPABILITIES.md")
OUTPUT_FILE = os.path.join(REPO_ROOT, "workspace", "jimbo-status.json")

# Static architecture info — update manually when things change
ARCHITECTURE = {
    "model": "anthropic/claude-haiku-4.5",
    "worker_model": "google/gemini-2.5-flash",
    "heartbeat": "1h",
    "vps": "DigitalOcean $12/mo, London",
    "openclaw_version": "v2026.2.12",
    "sandbox": "Docker (Python 3.11, Node 18)",
}


def parse_decisions():
    """Parse all ADR files from decisions/ directory."""
    decisions = []
    for fname in sorted(os.listdir(DECISIONS_DIR)):
        if fname == "_template.md" or not fname.endswith(".md"):
            continue

        # Extract number from filename (e.g. 001-sandbox-architecture.md → 1)
        match = re.match(r"(\d+)-", fname)
        if not match:
            continue
        number = int(match.group(1))

        filepath = os.path.join(DECISIONS_DIR, fname)
        with open(filepath, "r") as f:
            content = f.read()

        # Extract title from first heading: # ADR-NNN: Title
        title_match = re.search(r"^#\s+ADR-\d+:\s*(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else fname

        # Extract status from line after ## Status
        status_match = re.search(
            r"^##\s+Status\s*\n+([^\n#]+)", content, re.MULTILINE
        )
        status = status_match.group(1).strip() if status_match else "Unknown"

        decisions.append(
            {"number": number, "title": title, "status": status, "file": fname}
        )

    return decisions


def parse_capabilities():
    """Parse capability tables and token expiry from CAPABILITIES.md."""
    with open(CAPABILITIES_FILE, "r") as f:
        content = f.read()

    capabilities = []
    tokens = []
    current_section = None

    for line in content.split("\n"):
        # Track section headings
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            section_name = heading_match.group(1).strip()
            if section_name == "Token Expiry":
                current_section = "__tokens__"
            else:
                current_section = section_name
                capabilities.append({"category": section_name, "items": []})
            continue

        # Skip non-table lines and header separators
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| ---"):
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 2:
            continue

        # Skip table headers
        if cells[0] in ("Capability", "Model", "Server", "Boundary", "Token"):
            continue

        if current_section == "__tokens__":
            if len(cells) >= 3:
                tokens.append(
                    {"name": cells[0], "expires": cells[1], "purpose": cells[2]}
                )
        elif capabilities:
            status = cells[1] if len(cells) > 1 else ""
            notes = cells[2] if len(cells) > 2 else ""
            capabilities[-1]["items"].append(
                {"name": cells[0], "status": status, "notes": notes}
            )

    return capabilities, tokens


def main():
    decisions = parse_decisions()
    capabilities, tokens = parse_capabilities()

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decisions": decisions,
        "capabilities": capabilities,
        "tokens": tokens,
        "architecture": ARCHITECTURE,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Exported {len(decisions)} ADRs, {len(capabilities)} capability sections, {len(tokens)} tokens")
    print(f"Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
