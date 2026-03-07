---
description: Assess a URL or pasted text against Marvin's current goals, priorities, interests, and taste
argument-hint: "<url or pasted text>"
---

# Assess

Evaluate the content provided in `$ARGUMENTS` against Marvin's current context. Produce a structured verdict, then open the floor for discussion.

## Phase 1: Load Context

Load all context sources. Do these in parallel where possible.

**From jimbo-api (live, structured):**

Use the Bash tool to run these three curl commands. The API key is in env var `JIMBO_API_KEY`. If that's not set, ask Marvin for it.

```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" https://167.99.206.214/api/context/files/priorities
curl -s -H "X-API-Key: $JIMBO_API_KEY" https://167.99.206.214/api/context/files/interests
curl -s -H "X-API-Key: $JIMBO_API_KEY" https://167.99.206.214/api/context/files/goals
```

If any of these fail (network error, auth error, empty response), warn Marvin and fall back to reading `context/CONTEXT-BACKUP.md` instead. Don't silently skip — always say when you're using the fallback.

**From local repo (prose, judgment criteria):**

Read these two files:
- `context/TASTE.md` — defines what "good" looks like, what's boring, how Marvin consumes content
- `context/PREFERENCES.md` — how to combine context for decisions, what to surface, what to skip

These are the most important files for making judgment calls. TASTE.md especially — it defines the quality bar.

## Phase 2: Load Content

Look at `$ARGUMENTS`:

- **If it starts with http:// or https://:** Use WebFetch to retrieve the content. If WebFetch fails (JavaScript-rendered pages like tweets, paywalled sites), tell Marvin it couldn't be fetched and ask him to paste the content. Then wait for his response before continuing.
- **Otherwise:** Treat the arguments as the content to evaluate directly.

## Phase 3: Evaluate

Read all the loaded context carefully. Then evaluate the content against it.

Think about:
- Does this connect to any active priorities or goals? Which ones specifically?
- Does it match Marvin's interests? Is it in a domain he cares about?
- Does it pass the TASTE.md quality bar? Is it timely, curated, surprising, actionable, concise, niche, personally relevant?
- Would Marvin regret missing this? (The key test from PREFERENCES.md)
- Is there a concrete next step, or is this just "interesting"?
- What's the source not telling you? What would you need to verify?

## Phase 4: Deliver Verdict

Present your assessment using this structure. Keep it natural — this is a framework, not a rigid template. Adapt the length to match the complexity of what you're assessing.

**Verdict:** One line. Use one of: Skip / Bookmark / Worth exploring / Act now
Include a brief reason in the same line (e.g. "Bookmark — interesting tool but your bottleneck is elsewhere right now")

**Relevance:** 2-3 sentences. What is this, and why does it matter (or not) to Marvin specifically? Be direct. Don't hedge everything.

**Connections:** Name the specific goals, priorities, or interests this touches. Use the actual names from the API data (e.g. "OpenClaw/Jimbo [active]", "Keep Learning", "AI and agents"). If it doesn't connect to anything, say so — that's informative too.

**What you'd do with it:** A concrete next step if there is one. "Read the README and evaluate MCP server mode for Jimbo" is good. "Keep an eye on this space" is vague and useless. If there's genuinely nothing to do, say "Nothing right now" rather than inventing busywork.

**Blind spots:** What should Marvin be sceptical about? What claims need verifying? What's the source's incentive? What context is missing? This section is about intellectual honesty, not negativity.

## Phase 5: Invite Discussion

After the verdict, add a brief conversational hook. Something like "Happy to dig into any of this" or a specific question that might help Marvin think about it further. Don't be formulaic — make it natural.

Then let the conversation flow. Marvin will push back, ask follow-ups, or move on. The verdict is a starting point, not the final word.
