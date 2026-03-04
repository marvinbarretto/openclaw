# Briefing Quality Audit

*2026-03-03 — Full pipeline review*

## Executive Summary

The briefing pipeline has solid bones — three-stage architecture, good context files, honest SOUL.md — but suffers from **prompt bloat**, **context starvation at the triage stage**, **no examples of good output**, and **competing instructions that dilute focus**. The conductor (Sonnet) receives a 380+ line skill payload across two skills, making it nearly impossible to follow every instruction well. The workers are cleaner but the triage worker is blind to priorities and goals, which is the single biggest quality issue.

---

## Issues Found

### CRITICAL — Directly causes bad briefings

#### C1: Triage worker has no priorities or goals
- **File:** `workspace/tasks/email-triage.json` line 19
- **What:** `context_files: ["INTERESTS.md", "TASTE.md"]` — missing PRIORITIES.md and GOALS.md
- **Impact:** The first-pass filter that decides what Jimbo even SEES cannot answer "is this relevant to what matters this week?" It can match topics (interests) and quality (taste), but not urgency or current focus. An email about YNAB tools won't rank higher than a generic tech newsletter, even though "get finances in order" is an active priority.
- **Root cause:** Prompt design — likely kept lean to save Flash tokens, but the cost of missing a priority match far exceeds a few extra input tokens.

#### C2: No examples of good output anywhere in the pipeline
- **Files:** All prompts in `email_triage.py`, `newsletter_reader.py`, `sift-digest/SKILL.md`, `daily-briefing/SKILL.md`
- **What:** Every prompt describes the desired output format but never shows a concrete example of a *good* result. Models perform dramatically better with even one good example.
- **Impact:** The model has to guess what "explain WHY it matters" looks like vs just listing a subject line. It will default to the lazier pattern every time without a reference point.

#### C3: Conductor prompt is 380+ lines across two skills
- **Files:** `sift-digest/SKILL.md` (213 lines), `daily-briefing/SKILL.md` (167 lines)
- **What:** The conductor must simultaneously:
  1. Orchestrate workers (spawn sub-agents, handle fallbacks)
  2. Review worker output quality
  3. Rate workers
  4. Log to experiment tracker
  5. Log to recommendations store
  6. Play the surprise game
  7. Present the briefing in a specific 8-section format
  8. Propose a day plan from calendar + vault + email
  9. Check context freshness
  10. Log to cost tracker and activity log
  11. Check OpenRouter balance
  12. Announce tasks triage
- **Impact:** With 12+ competing directives, the model will reliably do 4-5 of them well and the rest poorly. The most likely casualties: day plan quality, email "WHY" explanations, vault task surfacing — exactly the things that make a briefing good.

#### C4: Two skills with overlapping presentation instructions
- **Files:** `sift-digest/SKILL.md` sections 1-8, `daily-briefing/SKILL.md` sections 1-11
- **What:** Both skills define how to present email highlights, but with different section numbering and slightly different priorities. sift-digest has 8 presentation sections. daily-briefing has 11 sections (including cost, OpenRouter, heartbeat, context freshness). The model sees both and must reconcile them.
- **Impact:** Contradictory or duplicated instructions cause the model to either merge them poorly or pick one and ignore the other. Neither outcome is good.

---

### HIGH — Significantly degrades quality

#### H1: PRIORITIES.md is stale (2026-02-19, 12 days old)
- **File:** `context/PRIORITIES.md` line 5
- **What:** "This Week" section references tasks from mid-February. "Get Sift email pipeline producing useful daily digests" is arguably done. "Chase Synaptics/Daniel" may be resolved. The priorities don't reflect what actually matters on March 3.
- **Impact:** Even when the model reads priorities correctly, it's applying two-week-old context. The "match current priorities" logic becomes noise.

#### H2: GOALS.md opens with raw emotional text
- **File:** `context/GOALS.md` lines 1-3
- **What:** Three shouted lines ("MEET SOMEONE, START A FAMILY" etc.) before the structured content. This was likely a brain dump that was never cleaned up.
- **Impact:** The model will either treat this as the highest-priority signal (it's first, it's capitalised) or be confused by the tonal shift. Neither is useful for email triage or briefing composition. These are real goals but they don't help the model make email decisions.

#### H3: Worker output paths hardcoded to `/workspace/.worker-*`
- **File:** `sift-digest/SKILL.md` lines 38, 48
- **What:** The skill tells the conductor to read from `/workspace/.worker-shortlist.json` and `/workspace/.worker-gems.json`. These files must persist between Docker exec calls.
- **Impact:** Already fixed per memory notes, but the dot-prefix means these files are hidden from casual `ls` inspection. More importantly, if the conductor runs the Python fallback but reads the sub-agent path (or vice versa), it gets stale data from a previous run.

#### H4: Triage prompt says "be ruthless" but provides no calibration
- **File:** `workspace/workers/email_triage.py` lines 56-76
- **What:** "Be ruthlessly selective" and "would Marvin regret missing this?" are good instructions but there's no example of what passes vs fails. The model has to calibrate "ruthless" on its own.
- **Impact:** Different model versions or even different runs will have wildly different thresholds. Some days you get 5 items, some days 40.

#### H5: Newsletter reader prompt lacks prioritisation hierarchy
- **File:** `workspace/workers/newsletter_reader.py` lines 53-57
- **What:** The "look for" list is unordered: articles, events, deals, surprises, links. Time-sensitive items should be extracted first, but the prompt doesn't say so. The confidence scoring (0.0-1.0) is well-designed but there's no guidance on how priorities should influence it.
- **Impact:** A time-sensitive event buried in paragraph 8 of a newsletter may get the same treatment as a generic article link.

#### H6: daily-briefing "Before you start" runs 9 commands sequentially
- **File:** `daily-briefing/SKILL.md` lines 22-33
- **What:** 9 sandbox commands must run before any output. Several are redundant with what sift-digest already does (reading context, checking digest). Command 3 is a one-liner Python snippet that's fragile (inline json parsing).
- **Impact:** If any command fails (common with sandbox), the model may skip the rest. The sequential nature means a slow calendar API call delays everything. Redundant context reads waste tokens.

#### H7: "Before you start" in sift-digest reads context files, daily-briefing also reads them
- **Files:** `sift-digest/SKILL.md` lines 13-19, `daily-briefing/SKILL.md` lines 27-30
- **What:** Both skills instruct the conductor to read the same 5 context files. In a single briefing session, the model reads PRIORITIES.md, INTERESTS.md, etc. twice.
- **Impact:** Token waste and potential for confusion if the two reads return different content (e.g., context API returns different data than file read).

---

### MEDIUM — Causes inconsistency or missed opportunities

#### M1: No "what bad looks like" in any prompt
- **What:** Prompts describe what to do but never show anti-patterns. "Don't just list subject lines" is in daily-briefing but not in the worker prompts. The workers don't know what a bad gem looks like.
- **Impact:** The model doesn't know what to avoid. Negative examples are as valuable as positive ones for calibration.

#### M2: Surprise game instructions are split across files
- **Files:** `sift-digest/SKILL.md` lines 106-123, `daily-briefing/SKILL.md` (not mentioned)
- **What:** The surprise game is defined in sift-digest but daily-briefing doesn't reference it. The conductor has to remember to play it from the sift-digest instructions while following daily-briefing's presentation format.
- **Impact:** The game is frequently skipped or done poorly because it's in the "other" skill.

#### M3: PREFERENCES.md still references Ollama classifier
- **File:** `context/PREFERENCES.md` lines 41-46
- **What:** "For the Classifier (Ollama)" section describes a pipeline that no longer exists. The current pipeline uses Gemini Flash.
- **Impact:** If the model reads this, it might think there's a separate Ollama classifier stage and adjust its behaviour accordingly. Minor confusion risk.

#### M4: Context freshness check (section 8) is cargo cult
- **File:** `daily-briefing/SKILL.md` lines 107-113
- **What:** Instructs the model to check if PRIORITIES hasn't been updated in 10 days. Currently PRIORITIES is 12 days old. This check would fire every single day until updated, becoming noise.
- **Impact:** A nudge that fires every day stops being a nudge and becomes clutter.

#### M5: Heartbeat email check-ins overlap with hourly email fetch
- **File:** `workspace/HEARTBEAT.md` lines 29-31
- **What:** HEARTBEAT says "check email 3x/day at 09:00, 13:00, 17:00" but email is now fetched hourly by cron (`email-fetch-cron.py`). The heartbeat instruction is stale.
- **Impact:** Jimbo might try to fetch email during heartbeat checks when it's already fresh, wasting tokens on redundant work.

#### M6: Model tag instruction in SOUL.md assumes knowledge of model
- **File:** `workspace/SOUL.md` line 106
- **What:** "Tag your model: [Flash], [Haiku], [Sonnet], [Opus], [Free]" — but the model might not know which model it is, especially via OpenRouter routing.
- **Impact:** Minor — model usually knows, but via OpenRouter broadcast it might tag incorrectly.

#### M7: Batch size defaults may cause inconsistent triage
- **Files:** `email-triage.json` batch_size 50, `newsletter-deep-read.json` batch_size 15
- **What:** If there are 120 emails, triage runs 3 batches with independent ranking. Cross-batch re-ranking (line 115-116 in email_triage.py) only sorts by rank number, which is relative within each batch.
- **Impact:** Email #1 from batch 3 might be less relevant than email #5 from batch 1, but after re-ranking they're treated as equal (both rank 1 and 5 respectively). The sort is mechanical, not semantic.

---

### LOW — Minor issues or style concerns

#### L1: sift-digest "Log your recommendations" section is verbose
- **File:** `sift-digest/SKILL.md` lines 127-152
- **What:** 25 lines explaining how to log recommendations, including urgency taxonomy and dedup instructions. This is reference material, not briefing instructions.
- **Impact:** Takes attention budget away from the core briefing task.

#### L2: daily-briefing section numbering is confusing
- **What:** Sections go 1, 2, 3, 3.5, 4, 5, 6, 7, 8, 9, 10, 11. The "3.5" insertion suggests organic growth without restructuring.
- **Impact:** The model has to process an irregular numbering scheme, adding minor cognitive load.

#### L3: HEARTBEAT.md model references are stale
- **File:** `workspace/HEARTBEAT.md` lines 10-11
- **What:** References "Haiku" for briefing window and "Flash" outside. Actual config is Sonnet for briefing, Kimi K2 outside.
- **Impact:** If Jimbo reads HEARTBEAT during the briefing, it might think it's on Haiku when it's on Sonnet.

---

## Root Cause Analysis

| Category | Issues | Core Problem |
|----------|--------|-------------|
| **Context starvation** | C1, H1, M3 | Workers don't get the context they need; context that exists is stale |
| **Prompt bloat** | C3, C4, H6, H7, L1, L2 | Too many instructions competing for attention; duplicated across skills |
| **No examples** | C2, H4, M1 | Models calibrate from examples, not descriptions. Zero examples anywhere. |
| **Stale instructions** | M3, M4, M5, L3, H2 | Pipeline evolved but prompts/context files didn't keep up |
| **Architecture** | H3, M7 | Minor structural issues with file paths and batch ranking |

---

## Proposed Improvement Order

### Phase 1: Highest-impact, lowest-effort (do now)

1. **Add PRIORITIES.md and GOALS.md to triage worker context** — one line change in `email-triage.json`
2. **Add concrete examples** to triage prompt and reader prompt — 10-15 lines each showing good vs bad output
3. **Update PRIORITIES.md** — Marvin needs to refresh "This Week"
4. **Clean up GOALS.md** — move the raw emotional lines to a comment or restructure as proper goals
5. **Fix HEARTBEAT.md model references** — Sonnet not Haiku, Kimi not Flash

### Phase 2: Structural improvements (next session)

6. **Merge sift-digest and daily-briefing presentation sections** — one canonical format, referenced from one place
7. **Split conductor responsibilities** — orchestration (running workers, logging) separate from presentation (composing the briefing). The skill should have a clear "Phase 1: gather data" and "Phase 2: compose output" structure.
8. **Remove redundant context reads** — if sift-digest already loaded context, daily-briefing shouldn't reload it
9. **Fix PREFERENCES.md** — remove Ollama reference, update for current architecture

### Phase 3: Quality feedback loop (build the review ritual)

10. **Design daily review format** — structured rating card Marvin fills in after each briefing
11. **Build review UI on site dashboard** — form that captures ratings, saves to API
12. **Feed ratings back into prompts** — "yesterday's briefing scored 4/10 because..." becomes prompt context
13. **LangFuse trace review** — after tomorrow's briefing, review full traces to see where quality drops

---

## Daily Review Process Design

### The Ritual

After each morning briefing, Marvin rates it on his phone (via site dashboard). Takes 60 seconds.

### Review Card Fields

```
Date: 2026-03-04
Overall: 6/10

Did it include?
  [ ] Calendar + day plan
  [ ] Vault tasks woven into plan
  [ ] Email WHY explanations (not just subjects)
  [ ] Time-sensitive items first
  [ ] Surprise game

What was good:
  (free text, 1-2 lines)

What was bad:
  (free text, 1-2 lines)

Missed items:
  (things in email/calendar Jimbo should have caught)

Worker quality:
  Triage: ___/10
  Reader: ___/10
  Conductor: ___/10
```

### How ratings feed back

1. Ratings stored in jimbo-api (new endpoint: `/api/briefing-reviews`)
2. `briefing-review-helper.py` in sandbox reads last 7 days of ratings
3. sift-digest skill's "Before you start" section adds: "Read recent briefing reviews to understand what worked and what didn't"
4. Over time, a `context/PATTERNS.md`-style file accumulates learned patterns about briefing quality

### Implementation path

- **Phase 3a:** Manual — Marvin types ratings into Telegram, Jimbo logs them via activity-log
- **Phase 3b:** Site UI — review form at `/app/jimbo/briefing-review`, API endpoint, helper script
- **Phase 3c:** Automated — helper script fetches last 7 reviews, formats as prompt context, injected into sift-digest

---

## Concrete Prompt Improvements

### Fix C1: Add priorities + goals to triage worker

**Before** (`email-triage.json` line 19):
```json
"context_files": ["INTERESTS.md", "TASTE.md"]
```

**After:**
```json
"context_files": ["INTERESTS.md", "TASTE.md", "PRIORITIES.md", "GOALS.md"]
```

### Fix C2: Add examples to triage prompt

**Add after "Respond with ONLY the JSON object" in `email_triage.py`:**

```
# Examples of good vs bad triage

GOOD shortlist entry:
{
  "gmail_id": "abc123",
  "rank": 1,
  "category": "deal",
  "reason": "Buenos Aires flight £632 — Marvin tracks travel deals and this is genuinely cheap for BA",
  "time_sensitive": true,
  "deadline": "2026-03-10"
}

BAD shortlist entry (don't do this):
{
  "gmail_id": "def456",
  "rank": 3,
  "category": "newsletter",
  "reason": "Tech newsletter with some articles",
  "time_sensitive": false,
  "deadline": null
}
The bad example fails because the reason is vague — it doesn't say WHY this newsletter matters for Marvin specifically.

GOOD skip decision: Skip "Your Uber receipt" — transactional noise, no action needed.
GOOD skip decision: Skip "Sainsbury's Nectar points" — loyalty marketing, never relevant.
BAD skip decision: Skip "UnHerd Weekly" — this is a newsletter Marvin reads. Even if this week's issue is weak, it should make the shortlist for the reader to evaluate.
```

### Fix C2: Add examples to newsletter reader prompt

**Add after "Respond with ONLY the JSON object" in `newsletter_reader.py`:**

```
# Examples of good vs bad gems

GOOD gem:
{
  "gmail_id": "abc123",
  "source": "Jack's Flight Club",
  "title": "Buenos Aires from £632 return",
  "why": "Direct match to travel goals — Marvin tracks error fares and this is genuinely below average for BA flights",
  "confidence": 0.9,
  "links": ["https://jacksflightclub.com/deals/buenos-aires"],
  "time_sensitive": true,
  "deadline": "2026-03-10",
  "price": "£632 return",
  "surprise_candidate": false
}

BAD gem (don't produce these):
{
  "gmail_id": "def456",
  "source": "TLDR",
  "title": "AI roundup",
  "why": "Marvin is interested in AI",
  "confidence": 0.5,
  "links": [],
  "time_sensitive": false,
  "deadline": null,
  "price": null,
  "surprise_candidate": false
}
The bad gem fails because: title is vague (which AI roundup?), why doesn't reference specific priorities or projects, no links extracted, confidence 0.5 is honest but the gem shouldn't exist if the match is this weak.

GOOD skip:
{
  "gmail_id": "ghi789",
  "source": "Morning Brew",
  "reason": "This issue focused on US banking regulation — no UK relevance, no connection to Marvin's projects or interests"
}
```

### Fix C3/C4: Restructure conductor skill (outline)

The merged skill should have two clear phases:

```
Phase 1: Gather (do silently, no output)
  1. Read context files (once)
  2. Run workers (triage → reader)
  3. Run calendar helper
  4. Read vault tasks
  5. Read briefing reviews from last 7 days
  6. Check tasks triage pending

Phase 2: Compose (produce output)
  Follow this EXACT structure:
  1. Date + greeting (2 lines)
  2. Schedule + day plan (calendar + vault + email, end with "swap or skip?")
  3. Email highlights with WHY (3-5 items max)
  4. Surprise game (1 item)
  5. Quick mentions (1 line each, only if genuinely borderline)

Phase 3: Housekeeping (do silently after output)
  1. Log to experiment tracker
  2. Log to activity log
  3. Log recommendations
  4. Log cost
```

The key insight: **Phase 2 is the only thing the user sees.** It should be under 25 lines of instructions. All the logging, tracking, and checking belongs in Phases 1 and 3 where it doesn't compete with composition quality.

### Fix H2: Clean up GOALS.md

**Before:**
```
MEET SOMEONE, START A FAMILY
RELEASE SOFTWARE WITH MY NAME ON AND FINALLY DO SOMETHING WITH MY SKILLS
LIVE SOMEWHERE I WANT TO LIVE, TRY SOMETHING NEW MAYBE? BEING HERE FEELS LIKE TREADING WATER
```

**Proposed:** Move these to a "## North Star" section at the bottom, or convert to structured goals:
```
## Life Goals (background — not for daily email decisions)
- Personal: meet someone, start a family
- Career: ship products with my name on them
- Location: explore living somewhere new
```

This preserves the intent but stops the model from treating raw emotional text as the primary signal.

---

## What to Review After Tomorrow's Briefing

With LangFuse traces available after the next briefing:

1. **Triage worker trace:** How many emails did it shortlist? Did the reasons reference priorities? How long did it take?
2. **Reader worker trace:** How specific were the gems? Did it extract actual article titles and links, or generic summaries?
3. **Conductor trace:** Which sections did it produce? Did it propose a day plan? Did it explain WHY for email highlights?
4. **Token usage:** How much of the context window is consumed by the two skill prompts vs actual email content?
5. **Failure points:** Did any stage fall back? What error messages appeared?

---

*Next step: Apply Phase 1 fixes (C1, C2, H1 prompt for Marvin, H2, L3), then review tomorrow's briefing with LangFuse traces.*
