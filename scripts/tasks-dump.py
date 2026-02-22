#!/usr/bin/env python3
"""
Dump all Google Tasks to JSON for inspection.

Fetches every task list and every task within them.
Writes to data/tasks-dump.json.

Usage:
    export GOOGLE_CALENDAR_CLIENT_ID='...'
    export GOOGLE_CALENDAR_CLIENT_SECRET='...'
    export GOOGLE_CALENDAR_REFRESH_TOKEN='...'
    python3 scripts/tasks-dump.py
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TASKS_API = "https://tasks.googleapis.com/tasks/v1"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def get_env(name):
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: {name} not set", file=sys.stderr)
        sys.exit(1)
    return val


def refresh_access_token(client_id, client_secret, refresh_token):
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR: Token refresh failed ({e.code}): {body}", file=sys.stderr)
        sys.exit(1)

    return tokens["access_token"]


def api_get(access_token, path):
    url = f"{TASKS_API}/{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR: Tasks API ({e.code}): {body}", file=sys.stderr)
        sys.exit(1)


def fetch_all_tasks(access_token, tasklist_id):
    """Fetch all tasks from a list, handling pagination."""
    all_tasks = []
    page_token = None

    while True:
        path = f"lists/{urllib.parse.quote(tasklist_id)}/tasks?maxResults=100&showCompleted=true&showHidden=true"
        if page_token:
            path += f"&pageToken={page_token}"

        result = api_get(access_token, path)
        all_tasks.extend(result.get("items", []))

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return all_tasks


def main():
    client_id = get_env("GOOGLE_CALENDAR_CLIENT_ID")
    client_secret = get_env("GOOGLE_CALENDAR_CLIENT_SECRET")
    refresh_token = get_env("GOOGLE_CALENDAR_REFRESH_TOKEN")

    access_token = refresh_access_token(client_id, client_secret, refresh_token)

    # Fetch all task lists
    print("Fetching task lists...", file=sys.stderr)
    lists_result = api_get(access_token, "users/@me/lists")
    task_lists = lists_result.get("items", [])
    print(f"Found {len(task_lists)} list(s)", file=sys.stderr)

    # Fetch tasks from each list
    output = {
        "dumped_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "lists": [],
    }

    total_tasks = 0
    for tl in task_lists:
        list_id = tl["id"]
        list_title = tl.get("title", "(untitled)")
        print(f"  {list_title}...", file=sys.stderr, end=" ")

        tasks = fetch_all_tasks(access_token, list_id)
        print(f"{len(tasks)} tasks", file=sys.stderr)
        total_tasks += len(tasks)

        output["lists"].append({
            "id": list_id,
            "title": list_title,
            "updated": tl.get("updated", ""),
            "tasks": tasks,
        })

    output["total_tasks"] = total_tasks

    # Write output
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(repo_root, "data", "tasks-dump.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nTotal: {total_tasks} tasks across {len(task_lists)} lists", file=sys.stderr)
    print(f"Written to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
