"""Shared utilities for vault workers. Frontmatter parsing, URL extraction, HTML stripping."""

import os
import re
from html.parser import HTMLParser


def parse_frontmatter(content):
    """Parse YAML frontmatter from a vault note. Returns (meta_dict, body_string).

    Simple parser — handles key: value pairs, quoted values, and arrays.
    Does not use yaml lib (stdlib only).
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    frontmatter = content[3:end]
    body = content[end + 3:].strip()

    meta = {}
    for line in frontmatter.strip().split("\n"):
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        # Strip surrounding quotes
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        meta[key.strip()] = val

    return meta, body


def extract_urls(content):
    """Extract URLs from a vault note. Checks ## Links section first, then inline URLs."""
    urls = []
    url_pattern = re.compile(r'https?://[^\s<>"\')\]]+')

    # Check for ## Links section
    links_match = re.search(r'^## Links\s*\n(.*?)(?=\n##|\Z)', content, re.MULTILINE | re.DOTALL)
    if links_match:
        links_section = links_match.group(1)
        urls = url_pattern.findall(links_section)
    else:
        # Fall back to any URLs in body (after frontmatter)
        _, body = parse_frontmatter(content)
        urls = url_pattern.findall(body)

    return urls


class _HTMLTextExtractor(HTMLParser):
    """Extract readable text from HTML, stripping tags."""

    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript", "svg", "iframe"}

    def __init__(self):
        super().__init__()
        self._pieces = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._pieces.append(text)

    def get_text(self):
        return "\n".join(self._pieces)


def html_to_text(html_content):
    """Convert HTML to readable text using stdlib HTMLParser.

    Strips script, style, nav, header, footer, noscript, svg, iframe tags.
    """
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html_content)
    except Exception:
        # Malformed HTML — return raw with tags stripped via regex fallback
        return re.sub(r'<[^>]+>', ' ', html_content).strip()
    return extractor.get_text()


def write_vault_note_atomic(filepath, content):
    """Write content to a vault note file atomically (write-to-temp-then-rename)."""
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w") as f:
        f.write(content)
    os.replace(tmp_path, filepath)


def update_frontmatter(content, updates):
    """Update frontmatter fields in a vault note. Returns new content string.

    Adds new fields and overwrites existing ones. Preserves body and field order.
    """
    meta, body = parse_frontmatter(content)
    meta.update(updates)

    # Rebuild frontmatter
    lines = ["---"]
    for key, val in meta.items():
        # Keep arrays and quoted strings as-is if they look like JSON
        if isinstance(val, str) and (val.startswith("[") or val.startswith("{")):
            lines.append(f"{key}: {val}")
        elif isinstance(val, str) and ":" in val:
            lines.append(f'{key}: "{val}"')
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")

    if body:
        lines.append("")
        lines.append(body)

    return "\n".join(lines)
