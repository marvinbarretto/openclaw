# ADR-008: Plugin & Skill Adoption Policy

## Status

Accepted

## Context

OpenClaw's ecosystem has grown rapidly (3,286+ skills on ClawHub, 37 bundled extensions). However, the ClawHavoc incident (Feb 2026) revealed serious supply-chain risks: 341 malicious skills distributing Atomic Stealer (AMOS), 7%+ of skills with credential-leaking flaws per Snyk audit. Skills and plugins run in-process with the Gateway — a malicious one has full access to Jimbo's runtime.

We need a policy for:
1. Which official/bundled plugins to enable
2. Whether and how to adopt community skills
3. How to build and deploy our own custom skills

## Decision

### Tier 1: Custom skills (build our own) — APPROVED

We build skills as `SKILL.md` files in `<workspace>/skills/`. These are prompt-only (no executable code), carry zero supply-chain risk, and have the highest loading precedence.

**Current custom skills:**
- `sift-digest` — reads and presents email-digest.json via `/email`
- `daily-briefing` — morning overview via `/briefing`

**Deployment:** `scripts/skills-push.sh` rsyncs from this repo to VPS workspace. Changes take effect on next Jimbo session (no restart needed).

### Tier 2: Bundled plugins — EVALUATE INDIVIDUALLY

Bundled plugins ship with OpenClaw and are maintained by the core team. They require explicit enablement. Evaluation:

#### Memory Core (memory-core) — RECOMMENDED

- **What:** SQLite + FTS5 hybrid search (BM25 + vector), OpenAI batch embedding indexing
- **Slot:** `plugins.slots.memory = "memory-core"`
- **Why enable:** Gives Jimbo automatic `memory_recall` and `memory_store` tools. Currently we rely on workspace markdown files (MEMORY.md, USER.md) which require manual curation. Memory Core adds automatic conversation recall — it *complements* workspace files, doesn't replace them.
- **Trade-off:** Requires an embedding model. If using OpenAI embeddings, that's an additional API call cost. Need to check if it works with OpenRouter/local models.
- **Workspace files still needed:** SOUL.md, IDENTITY.md, USER.md, AGENTS.md are curated identity files. Memory Core handles *recall of past conversations*, not identity.
- **Action:** Enable after confirming embedding model compatibility with our provider setup. Start with memory-core (simpler, more mature than LanceDB).

#### Memory LanceDB (memory-lancedb) — NOT YET

- **What:** LanceDB vector store alternative
- **Known bug:** `openclaw status` reports memory as unavailable because the status scanner only probes memory-core (GitHub #7273)
- **Action:** Skip for now. memory-core is simpler and better supported. Revisit if we need more advanced vector search.

#### Session Memory Hook — RECOMMENDED

- **What:** Bundled hook that auto-saves session context to a memory file when you run `/new`, generating a dated file with an LLM-generated slug
- **Risk:** Low — it only writes to workspace memory directory
- **Action:** Enable. This automates what Jimbo's memory/*.md logs are doing manually.

#### Command Logger Hook — RECOMMENDED

- **What:** Logs all command events to a JSONL audit file
- **Risk:** Low — write-only, useful for debugging and security review
- **Action:** Enable. Gives us an audit trail of Jimbo's actions.

#### Lobster (workflow automation) — DEFER

- **What:** Typed workflow automation with approval gates
- **Risk:** Medium — more complex, runs actions
- **Action:** Defer until we have a concrete workflow use case.

#### LLM-Task (structured tasks) — DEFER

- **What:** JSON-only structured task execution
- **Action:** Defer. Our current needs don't require structured task pipelines.

#### Auth plugins (Google, Qwen, Copilot Proxy) — NOT NEEDED

- **What:** OAuth bridges for various AI providers
- **Action:** Not needed. We use OpenRouter and direct Anthropic API keys.

### Tier 3: Community/ClawHub skills — STRICT POLICY

**Default: DO NOT INSTALL.** The ClawHub ecosystem is not mature enough for trusted use.

If a community skill looks genuinely useful, the following process is required:

1. **Source review:** Read the full source code before installing. Skills are small — this is feasible.
2. **VirusTotal check:** Check the skill's VirusTotal report on ClawHub.
3. **Local install only:** Use `openclaw plugins install -l ./path` (symlink mode) so we control the code.
4. **Model restriction:** Test on cheap/free model tier first (limited blast radius per ADR-004).
5. **No postinstall:** Never install skills that need lifecycle scripts.
6. **No unofficial registries:** Only use clawhub.ai. Ignore knockoff sites (openclaw-hub.org, claw-hub.net, etc.).

**Red flags — never install:**
- Skills named "self-improving", "capability-evolver", or similar
- Skills requesting network access beyond their stated purpose
- Skills with high downloads but few/no stars (bot-inflated)
- Skills from unknown authors with no other published work

## Consequences

### Easier
- Clear decision framework for any new plugin/skill request
- Custom skills give Jimbo structured capabilities with zero supply-chain risk
- Memory Core will reduce manual memory file maintenance
- Audit trail via Command Logger hook

### Harder
- We miss out on potentially useful community skills
- Memory Core needs embedding model setup (small config effort)
- Custom skills need manual deployment via rsync (but this is a feature, not a bug — we control exactly what runs)
