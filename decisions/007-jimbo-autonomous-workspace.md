# ADR-007: Jimbo's Autonomous Workspace

## Status

Accepted

## Context

Jimbo is currently chat-only. The Docker sandbox has no Python, no Node, no write access to the workspace, and no ability to create or deploy anything. This makes Jimbo a conversationalist, not an agent.

To prototype the email digest system (and future projects), Jimbo needs to:
1. Write and run code
2. Persist output (files, scripts, data)
3. Show results to Marvin (deploy something visible)

The challenge: do this without compromising the security model we've carefully built.

## Decision

### 1. Jimbo gets his own GitHub account

- **Account:** `marvinbarretto-labs` (marvinbarretto.labs@gmail.com)
- **GitHub:** https://github.com/marvinbarretto-labs
- Jimbo's repos live here, completely separate from Marvin's personal account
- Fine-grained token scoped to Jimbo's own repos only (read + write)
- If the token leaks or the model gets hijacked, blast radius = Jimbo's disposable repos. Zero impact on Marvin's projects.

### 2. Jimbo gets a workspace repo: `jimbo-workspace`

A single repo where Jimbo builds, experiments, and ships prototypes.

**What lives in it:**

```
jimbo-workspace/
├── projects/
│   ├── email-digest/          # Digest reader, queue tracker, feedback system
│   │   ├── reader.py          # Reads email-digest.json, generates conversational output
│   │   ├── queue.py           # Time-budget tracking
│   │   ├── feedback.py        # Learning loop (sender/topic reputation)
│   │   ├── wildcard.py        # Daily wildcard generator + scoring
│   │   └── data/              # Runtime JSON files (queue, feedback, scores)
│   └── dashboard/             # Static HTML dashboard (deployable to GitHub Pages)
│       └── index.html         # Digest stats, queue status, wildcard scores
├── scripts/                   # Utility scripts
├── docs/                      # Jimbo's own notes and documentation
└── README.md
```

**Where it lives:**
- GitHub: under Jimbo's own account
- VPS: cloned into the sandbox workspace (e.g. `/workspace/jimbo-workspace/`)
- Jimbo can read, write, commit, and push from inside the sandbox

### 3. Install Python and Node in the sandbox

The sandbox (`bookworm-slim`) needs runtimes to actually run code. Rather than burning GitHub Actions minutes, install them directly.

**Approach:** Add a setup script or extend the Docker image.

```bash
# Option A: Install at container startup via config
# Option B: Build a custom sandbox image with runtimes pre-installed
# Option C: Mount host-installed runtimes (like we did with homebrew/gh)
```

Recommended: **Option C** — install Python3 and Node via homebrew on the host, mount into sandbox read-only. Same pattern as `gh`. No custom Docker image needed, no container rebuild.

### 4. Deployment: GitHub Pages for static output

- GitHub Pages is free, static-only, no secrets, no server
- Jimbo pushes to a `gh-pages` branch or `/docs` folder
- Output visible at `https://jimbo-agent.github.io/jimbo-workspace/`
- Perfect for: dashboards, reports, digest summaries, experiment output

### 5. What about a backend?

**What we'd miss without one:**
- No scheduled tasks (e.g. "run digest at 8am") — but OpenClaw's heartbeat/cron can trigger this
- No API endpoints — but Jimbo doesn't need to serve APIs, it talks via Telegram
- No database — but JSON files in the repo are fine for a prototype
- No server-side rendering — but static HTML generated from data works

**What we can mock:**
- "Backend" logic runs as Python scripts inside the sandbox, triggered by Jimbo or by heartbeat
- Data persistence = JSON files committed to the repo
- "Deployment" = push to GitHub Pages

**When we'd need a real backend:**
- If we want Jimbo to serve a web app with auth or real-time features
- If data grows beyond what JSON files can handle
- Cross that bridge later — prototype first with files + static pages

### 6. Model safety

Since the blast radius is genuinely zero (Jimbo's own disposable repo, no access to real projects), this workspace is **safe for cheap models**. The worst case: Jimbo writes bad code to its own repo. We delete it and start over.

This means we can:
- Use cheap/free models for coding experiments in jimbo-workspace
- Reserve Claude Sonnet for reading Marvin's real repos (ADR-006 still applies)
- Save money while Jimbo prototypes

## Implementation steps

1. Create Jimbo's GitHub account
2. Create `jimbo-workspace` repo under that account
3. Generate fine-grained token (read+write on jimbo-workspace only)
4. Install Python3 + Node in sandbox (via homebrew mount pattern)
5. Grant sandbox write access to a workspace subdirectory
6. Configure `gh` with Jimbo's token
7. Clone `jimbo-workspace` into sandbox
8. Test: can Jimbo write a file, commit, push, and deploy to Pages?

## Consequences

- **Good:** Jimbo becomes a real agent that can build and ship things
- **Good:** Zero blast radius — completely isolated from Marvin's repos and accounts
- **Good:** Safe for cheap models — disposable repo means low-stakes experimentation
- **Good:** No GitHub Actions cost — runtimes run locally in sandbox
- **Good:** GitHub Pages deployment is free and contained (static only)
- **Trade-off:** Need to maintain a second GitHub account (Jimbo's)
- **Trade-off:** Sandbox gets heavier (Python + Node installed) — more attack surface, but contained
- **Trade-off:** JSON-file "database" won't scale — fine for prototyping, revisit if needed
- **Risk:** Jimbo's GitHub account could be used for social engineering (e.g. opening PRs on public repos). Mitigation: token scoped only to jimbo-workspace, no other repo access.
