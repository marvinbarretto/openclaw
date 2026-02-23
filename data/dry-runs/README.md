# Dry Run Log

Tracking the evolution of our automated note classifier. Each run tests a combination of model, prompt, and rules against the vault inbox.

**Goal:** Get automated classification accurate enough to process ~6,500 notes with minimal manual review.

**Method:** Dry-run batches, compare against manual ground truth, update PATTERNS.md and classifier prompt, repeat.

## The Problem

~13,000 scattered notes from Google Tasks and Google Keep, dumped into a vault inbox. Need to classify each as: active note (with type + tags), needs-context (ambiguous), or archive (stale/completed/dead).

Manual review at 5 notes/batch = ~1,300 sessions. Not feasible. Need an LLM to handle the bulk, with manual review for the ambiguous remainder.

## Runs

| # | Date | Model | Items | Notes | Needs-ctx | Archive | Errors | Time | Notes |
|---|------|-------|-------|-------|-----------|---------|--------|------|-------|
| 001 | 2026-02-23 | qwen2.5:7b | 50 | 46 | 1 | 2 | 1 | 680s (13.6s/ea) | Baseline. Way too confident — gave 8-9 confidence even when wrong. Only 1 needs-context vs ~15 expected. Missed project tags entirely. |
| 002 | 2026-02-23 | qwen2.5-coder:14b | 50 | 46 | 3 | 0 | 1 | 1079s (21.6s/ea) | Same prompt as 001. Slightly better uncertainty (3 needs-context). Got "The Odyssey" right as book. Still missed projects, completed tasks. Zero archives. |
| 003 | 2026-02-23 | qwen2.5:7b | 25 | 24 | 0 | 0 | 1 | 958s (38.3s/ea) | Improved prompt v2 made NO difference. 0 needs-context, 0 archive. Model ignores rules — bare tweets still "bookmark [travel]" at confidence 8. 7b can't absorb long system prompts. |
| 004 | 2026-02-23 | gemini-2.5-flash | 25 | 17 | 2 | 2 | 4 | 112s (4.5s/ea) | **Breakthrough.** Actually follows rules — bare tweets → needs-context, uses project tags, person tags, archives stale items. 4 errors from maxOutputTokens too low (fixed to 2048). First model to demonstrate real comprehension of the prompt. |
| 005 | 2026-02-23 | gemini-2.5-flash | 25 | 20 | 3 | 2 | 0 | 103s (4.1s/ea) | **Zero errors** after token fix. Bare tweets → needs-context (conf 1-3). Project tags used correctly. "Carl N Misty feeling" → needs-context (conf 4). Consistent with 004 quality. Ready for larger test. |
| 006 | 2026-02-23 | gemini-2.5-flash | 200 | 120 | 68 | 12 | 0 | 668s (3.3s/ea) | **200 items, 0 errors.** 34% needs-context is a healthy ratio. Bare tweets, opaque numbers, ambiguous shorts all correctly routed. Travel notes richly tagged (vietnam, hong-kong, china). Vietnamese/Chinese phrases identified. Project tags consistent. Dead URLs archived. |
| 007 | 2026-02-23 | gemini-2.5-flash | 100 | 69 | 25 | 6 | 0 | 319s (3.2s/ea) | **New features: age-based auto-archive rules, --skip-fetch flag, oEmbed for tweets, updated PATTERNS.md.** Skip-fetch used (no URL fetching). needs-context dropped from 34% → 25% — new rules help LLM on shopping lists and opaque items. Remaining needs-context almost all bare tweet URLs (oEmbed would resolve). BuzzFeed notes correctly kept as active. Project/person tags solid. 3 stale, 2 completed, 1 past-event archived correctly. |

## Ground Truth Review (from 006)

We manually reviewed ~20 borderline items from run 006 (confidence 6-8 or suspicious classifications). Results:

- **4 → notes/** (correctly classified but needed tag fixes — e.g. missing `project:localshout`, missing `china` tag)
- **3 → archive/completed** (single-item shopping lists: "silver lunch", "shower and hand gel", "tissues")
- **15 → archive/stale** (opaque numbers, old social plans, old work tickets, expired codes)
- **1 → archive/stale + security flag** (AWS credentials in a note — keys need rotation)

**Key findings from this review:**
1. Gemini correctly identified most items but sometimes missed project tags (e.g. "Surath email" should have `project:localshout`)
2. Single-item shopping/packing lists are almost always completed — archive as completed, not classify as task
3. Opaque numbers ("12", "1520") are unrecoverable after a few weeks — archive, don't send to needs-context
4. Person nicknames carry hidden context ("Silver" = Adam Silver) — the LLM can't know this without being told
5. BuzzFeed notes are NOT automatically stale — Marvin still does work for BuzzFeed. Archive only with clear staleness signals.
6. Credentials sometimes end up in notes via Google Keep — archive immediately and flag for rotation

## Ground Truth (from 001/002)

We manually reviewed all 50 items from runs 001/002. The correct breakdown was:

- **22 → notes/** (active, classified)
- **4 → needs-context/** (bare tweet URLs)
- **18 → archive/** (stale)
- **6 → archive/** (completed)

**Total: 22 active, 4 needs-context, 24 archive.**

Both models got this badly wrong — classifying ~46/50 as active notes.

### Key failure modes (both models)

1. **No project awareness** — didn't tag localshout/spoons/openclaw even with context files loaded
2. **Overconfident** — confidence 8-9 on opaque 2-word notes
3. **Can't detect "completed"** — no concept of task lifecycle
4. **Bare tweet URLs** — guessed "travel" instead of admitting uncertainty
5. **Domain confusion** — "Shape Up" (Basecamp book) → health/fitness, "The Odyssey" (7b) → travel/greece
6. **People = passive records** — "Kat!", "Ring Alvin" should be contact tasks
7. **Missed sequential context** — "Get them off, wipe" relates to previous note "Clean notes off old computer"

### What we changed for run 003

1. Added `context/PATTERNS.md` to the context files (previously missing)
2. Added confidence scoring — confidence <= 5 forces needs-context
3. Added 8 new classification rules:
   - Event listing URLs → project:localshout tasks
   - Person names → contact tasks with person:<name> tag
   - AI conversation prompts → project:openclaw
   - "Shape Up" = Basecamp book
   - Bare tweet URLs without content → must go to needs-context
   - Recurring nudges → archive as stale
   - Opaque notes > 3 months → needs-context
4. Expanded project descriptions in PATTERNS.md with concrete examples

## Prompt Evolution

### v1 (runs 001-002)
- Context: INTERESTS, PRIORITIES, TASTE, GOALS
- Rules: 9 classification rules
- No confidence scoring
- "Use needs-context sparingly"

### v2 (run 003+)
- Context: INTERESTS, PRIORITIES, TASTE, GOALS, **PATTERNS**
- Rules: 18 classification rules (9 new)
- Confidence scoring (1-10), <= 5 forces needs-context
- "It is better to flag something for manual review than to guess wrong"
- Specific rules for tweets, people, projects, domain ambiguity

## Architecture

```
Manual review sessions (Claude Code /manual-review)
        │
        ├──→ Process notes (move/archive/classify)
        ├──→ Update PATTERNS.md (learned rules)
        └──→ Update process-inbox.py prompt (classification rules)
                │
                ├──→ Dry run (test against inbox)
                ├──→ Compare to ground truth
                └──→ Iterate prompt ──→ next dry run
```

The feedback loop: each manual review session improves the automated classifier, which reduces the number of items needing manual review.

## Models Tested

| Model | Size | Speed | Quality | Notes |
|-------|------|-------|---------|-------|
| qwen2.5:7b | 4.7GB | 13.6s/item | Low | Fast but overconfident. Guesses rather than admitting uncertainty. |
| qwen2.5-coder:14b | 9.0GB | 21.6s/item | Slightly better | Better at knowing what it doesn't know (3 vs 1 needs-context). Still misses projects. |
| Gemini 2.5 Flash | API | 4.5s/item | **Best so far** | Follows complex rules, uses project/person tags, handles uncertainty correctly. 8x faster than 7b. ~$0.01/50 items. Thinking tokens eat into output — needs higher maxOutputTokens. |
| Claude Haiku 4.5 | API | ~1s/item | Untested with new prompt | Original model in process-inbox.py. Fast but costs money. |

## Key Learning: Small Models Can't Follow Complex Prompts

Run 003 proved that qwen2.5:7b simply ignores additional rules in the system prompt. Adding 9 new rules, PATTERNS.md, and confidence scoring had zero measurable effect — same overconfident behaviour, same wrong answers.

**The constraint isn't the prompt, it's the model.** A 7b model doesn't have the capacity to hold a long system prompt (5 context files + 18 rules + taxonomy + examples) in working memory and actually reason about each rule. It pattern-matches on the note content and outputs plausible-looking JSON with high confidence.

**Implication:** For complex classification with many rules and context, we need a model that can actually follow instructions — either a larger local model (14b helped slightly) or an API model (Gemini, Haiku). The local models are better suited for simpler, more constrained tasks.

## Future Directions

- **Few-shot examples** — include ground truth examples in the prompt
- **Fine-tuning** — use labelled review data as training examples for a custom LoRA
- **oEmbed pre-fetch** — fetch tweet content before sending to LLM (currently only done in manual review)
- **Two-pass approach** — LLM handles clear cases, routes ambiguous to manual review queue
- **Obsidian integration** — use the vault directly in Obsidian as a UI layer
