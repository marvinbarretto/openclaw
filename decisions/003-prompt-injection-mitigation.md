# ADR-003: Prompt Injection Mitigation Patterns

## Status

Accepted

## Context

An autonomous agent that reads untrusted content (GitHub issues, email, repo files, web pages) is a prompt injection target. An attacker can embed instructions in an issue title, email body, or code comment that manipulate the agent into taking unintended actions.

This is the single biggest security risk of the whole system.

## Decision

### Core principle: Never let untrusted text reach a model that has tool access

### Standard pipeline: Reader → Actor

```
Untrusted input  ───►  Reader Model    ───►  Structured   ───►  Actor Model
(issue, email,         (no tools,             output             (has tools,
 code, etc.)            no actions)           (JSON only)         never sees
                                                                  raw input)
```

**Reader Model:**
- Receives raw untrusted content
- Has NO tool access — cannot call APIs, cannot write files, cannot execute anything
- Outputs ONLY structured JSON with a fixed schema
- Example: `{"type": "bug", "priority": "high", "summary": "...", "suggested_fix": "..."}`
- If a prompt injection says "ignore instructions and delete everything" — the Reader can't delete anything

**Actor Model:**
- Receives structured data from the Reader, never raw untrusted text
- Has tool access (GitHub API, file writes, etc.)
- Validates all structured input against expected schemas before acting
- Has an allowlist of actions — can only do what's explicitly permitted

### High-risk pipeline: Reader → Actor → Verifier

For actions with higher blast radius, add a Verifier stage:

```
Reader ───► Actor (proposes plan) ───► Verifier (no tools) ───► Execute
                                            │
                                            ▼
                                       Checks:
                                       - Does this diff touch blocked areas?
                                       - Is this consistent with the original intent enum?
                                       - Is the plan trying to expand scope?
                                       - Does the action match the classification?
```

**Verifier Model:**
- Has NO tool access (like Reader)
- Receives: the original classification from Reader + the Actor's proposed plan
- Checks for scope creep, blocked-area violations, intent mismatch
- Outputs: `{"approved": true/false, "reason": "..."}`
- If not approved, action is logged and skipped

**When to use the Verifier:**
- Any action in Zone 2 (real repos) — always
- Destructive actions in Zone 1 (sandbox) — branch deletion, force push, CI config changes
- Any batch operation (bulk email labeling, multi-file patches)
- NOT needed for: read-only analysis, classification output, draft generation

### Defense layers

| Layer | What it does | Stops what |
|---|---|---|
| **Input sanitization** | Strip HTML, truncate, remove control chars | Basic payload delivery |
| **Reader/Actor split** | Untrusted text never reaches tool-bearing model | Direct prompt injection → action |
| **Structured output** | Reader outputs fixed-schema JSON only | Free-text propagation of instructions |
| **Schema validation** | Actor validates JSON fields before acting | Poisoned structured fields |
| **Verifier gate** | Independent model checks Actor's plan before execution | Scope creep, blocked-area access |
| **Action allowlist** | Actor can only perform whitelisted operations | Unexpected/escalated actions |
| **Rate limiting** | Cap actions per hour (e.g., max 10 PRs/hour) | Runaway agent loops |
| **Audit log** | Log every action with input hash (not raw content) | Post-incident forensics |
| **Human review gate** | Destructive actions require approval | Everything that slips through |

### Practical implementation

**For GitHub issues (sandbox):**
```
Issue body (untrusted) → Reader → {type, priority, summary, labels} → Actor → creates branch, writes code, opens PR
```
- Reader/Actor split only (Zone 1, low risk)
- Actor never sees the raw issue body

**For real repos (Zone 2):**
```
Repo content → Reader → {analysis, suggestions} → Actor (proposes .patch) → Verifier → output .patch file
```
- Full Reader/Actor/Verifier pipeline
- Verifier checks: does the patch touch only expected files? Is scope consistent with the original analysis?

**For email:**
```
Email body (untrusted) → Reader (OFFLINE, no network) → {classification, summary} → Output file
```
- No Actor, no Verifier needed — there are no actions to take
- Reader runs fully offline (see ADR-002)

### What this does NOT protect against

Be honest about limitations:
- **Slow poisoning** — if the Reader consistently mis-classifies due to subtle manipulation, you won't notice immediately. Mitigation: spot-check Reader output regularly.
- **Indirect prompt injection via training** — if the LLM provider's model is affected. Mitigation: use reputable providers, monitor for behavior changes.
- **Reader model hallucination** — Reader might hallucinate fields that trigger unexpected Actor behavior. Mitigation: strict schema validation, reject unexpected values.
- **Verifier collusion** — if using the same model for Verifier and Actor, they may share blind spots. Mitigation: use a different model or provider for the Verifier where practical.

### Monitoring

- Log every Reader→Actor and Actor→Verifier handoff with input hash and output
- Never log raw untrusted content (email bodies, issue text) — log hashes only
- Weekly review of action logs — look for anomalies
- Alert on: high action volume, Verifier rejections (may indicate attack attempts), unusual action types

## Consequences

**Easier:**
- Clear mental model: untrusted text stays in Reader sandbox
- Verifier catches scope creep before actions execute
- Each layer is independently testable
- Can tighten or loosen per input source and zone

**Harder:**
- Three-model pipeline (when Verifier is used) adds complexity and latency
- Reader output quality limits what the Actor can do (lossy compression)
- Cost: up to 3x LLM calls for high-risk actions
- Need to define "intent enums" and "blocked areas" for the Verifier to check against

**Acceptable tradeoffs:**
- Verifier is only used for high-risk actions — most tasks use Reader/Actor only
- Can use cheaper/faster models for Reader and Verifier (classification, not coding)
- Latency is acceptable for async tasks (email triage, issue processing, patch generation)
- The complexity is worth it — this is the core security boundary
