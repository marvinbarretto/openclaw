# Preferences

How to use my context files to make decisions about what's worth my attention. This is the glue between my interests, priorities, taste, and goals.

## Context Files

Read these to understand me:
- **INTERESTS.md** — what I care about (changes slowly)
- **PRIORITIES.md** — what matters right now (changes weekly)
- **TASTE.md** — what "good" looks like and what bores me
- **GOALS.md** — longer-term ambitions (changes monthly)

## Location context
Marvin is in Watford, UK. Central London is ~1 hour by train. Don't describe London venues as 'nearby' or 'on your doorstep' — they're accessible but require planning."


## How to Decide What's Worth Surfacing

Don't use hard rules. Use judgment. Every email should be evaluated on its own merit, considering:

1. **Is someone talking TO me?** Personal replies, direct messages, conversations I'm part of — these always matter. Never skip a human writing to me specifically.

2. **Is it time-sensitive?** Events, limited tickets, expiring deals, deadlines. The value of this information drops to zero after the date passes. Surface these early and prominently.

3. **Does it match my current priorities?** Check PRIORITIES.md. If I'm chasing a Synaptics fix, emails from Daniel matter. If LocalShout isn't live, Sentry alerts don't.

4. **Is this specific issue actually good?** A normally-great newsletter can have a dull issue. A normally-boring sender can have a gem. Judge the content, not just the source. Read TASTE.md for what "good" means to me.

5. **Would I regret missing this?** The real test. A fabric night selling out — yes. A Starbucks matcha promo — no. An UnHerd piece on a topic I follow — probably yes. A generic BBC roundup — probably no.

6. **Does it connect to my goals?** Check GOALS.md. Product Hunt connects to "build and ship products". YNAB connects to "get financially organised". A Bandsintown alert connects to "stay culturally active".

## What I DON'T Want

- A firehose of everything that might be relevant
- The same senders surfaced every day regardless of content quality
- Marketing dressed up as content
- Information I can't act on

## Feedback Loop

After each batch, I'll review what was surfaced and what was missed. This feedback refines everyone's understanding over time. The goal is that each week's briefing is better than the last — not because of stricter rules, but because of better judgment.

## For the Classifier (Ollama)

The classifier makes the first pass. It should:
- Lean towards surfacing events and personal replies (these are the most commonly missed)
- Use INTERESTS.md and PRIORITIES.md as context for what's relevant
- Not try to apply taste — that's Jimbo's job. The classifier sorts, Jimbo curates.

## For Jimbo

You present the final briefing. You should:
- Read all context files before preparing a briefing
- Apply TASTE.md when deciding what to highlight vs mention vs skip
- Adjust your judgment based on feedback from previous batches
- Surprise me sometimes — if something unexpected looks genuinely good, surface it
- Tell me when you're uncertain — "this might interest you" is fine
