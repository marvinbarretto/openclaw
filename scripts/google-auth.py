#!/usr/bin/env python3
"""
One-time OAuth flow for Google APIs (Calendar + Gmail read-only).

Runs on the laptop. Opens a browser for Google consent, captures the auth code
via a localhost callback, exchanges it for a refresh token, and saves credentials
to data/.google-tokens.json.

Replaces calendar-auth.py with broader scopes. The resulting refresh token
works for both Calendar and Gmail API access.

Usage:
    python3 scripts/google-auth.py --client-id CLIENT_ID --client-secret CLIENT_SECRET

Prerequisites:
    1. Google Cloud project with Calendar API AND Gmail API enabled
    2. OAuth 2.0 Client ID (type: Desktop app)
    3. App published (unverified OK) so refresh tokens don't expire after 7 days
"""

import argparse
import http.server
import json
import os
import sys
import urllib.parse
import urllib.request
import webbrowser

CALLBACK_PORT = 8090
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}"
SCOPES = "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/tasks.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def main():
    parser = argparse.ArgumentParser(description="Google API OAuth flow (Calendar + Gmail)")
    parser.add_argument("--client-id", required=True, help="OAuth 2.0 Client ID")
    parser.add_argument("--client-secret", required=True, help="OAuth 2.0 Client Secret")
    args = parser.parse_args()

    # Build consent URL
    params = urllib.parse.urlencode({
        "client_id": args.client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    })
    consent_url = f"{AUTH_URL}?{params}"

    # State to capture the auth code from the callback
    auth_result = {"code": None, "error": None}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            if "error" in params:
                auth_result["error"] = params["error"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Auth failed</h1><p>You can close this tab.</p>")
            elif "code" in params:
                auth_result["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Auth successful!</h1><p>You can close this tab.</p>")
            else:
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Unexpected request</h1>")

        def log_message(self, format, *args):
            pass  # suppress server logs

    # Start callback server
    server = http.server.HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    print(f"Opening browser for Google consent...")
    print(f"Scopes: Calendar (read/write) + Gmail (read-only) + Tasks (read-only)")
    print(f"(If the browser doesn't open, visit: {consent_url})")
    webbrowser.open(consent_url)

    # Wait for the callback
    print(f"Waiting for callback on localhost:{CALLBACK_PORT}...")
    server.handle_request()
    server.server_close()

    if auth_result["error"]:
        print(f"\nERROR: Auth failed: {auth_result['error']}", file=sys.stderr)
        sys.exit(1)

    if not auth_result["code"]:
        print("\nERROR: No auth code received.", file=sys.stderr)
        sys.exit(1)

    # Exchange auth code for tokens
    print("Exchanging auth code for tokens...")
    token_data = urllib.parse.urlencode({
        "code": auth_result["code"],
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=token_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\nERROR: Token exchange failed ({e.code}): {body}", file=sys.stderr)
        sys.exit(1)

    if "refresh_token" not in tokens:
        print("\nERROR: No refresh token in response. Did you set prompt=consent?", file=sys.stderr)
        print(f"Response: {json.dumps(tokens, indent=2)}", file=sys.stderr)
        sys.exit(1)

    # Save tokens
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(repo_root, "data", ".google-tokens.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    credentials = {
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "refresh_token": tokens["refresh_token"],
    }

    with open(output_path, "w") as f:
        json.dump(credentials, f, indent=2)
    os.chmod(output_path, 0o600)

    print(f"\nSaved credentials to {output_path}")
    print()
    print("=== Next steps ===")
    print()
    print("1. Test locally:")
    print(f"   export GOOGLE_CALENDAR_CLIENT_ID='{args.client_id}'")
    print(f"   export GOOGLE_CALENDAR_CLIENT_SECRET='{args.client_secret}'")
    print(f"   export GOOGLE_CALENDAR_REFRESH_TOKEN='{tokens['refresh_token']}'")
    print("   python3 workspace/calendar-helper.py list-calendars")
    print("   python3 workspace/gmail-helper.py fetch --hours 24")
    print()
    print("2. Deploy to VPS:")
    print("   Update GOOGLE_CALENDAR_REFRESH_TOKEN in /opt/openclaw.env")
    print("   (Same token works for both Calendar and Gmail)")
    print()
    print("NOTE: This replaces calendar-auth.py. The new token has both")
    print("Calendar and Gmail scopes. You only need one refresh token.")
    print()


if __name__ == "__main__":
    main()
