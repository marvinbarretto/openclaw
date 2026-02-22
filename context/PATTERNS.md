# Patterns

How Marvin's notes actually work. Learned through review sessions with Claude Code.

This is a living document — when understanding changes, update the relevant section. Never append contradictory entries; rewrite the old understanding instead.

*Last updated: 2026-02-22*

## Projects as destinations

Marvin's notes often serve a hidden purpose — feeding into a specific project. Tag these with `project:<name>`.

- **project:localshout** — venues, event sources, artists, festivals, comedy nights. Anything that could populate LocalShout's event/venue database. Examples: "100 Club", "Bristol Comedy Festival".
- **project:film-planner** — film, TV, show recommendations to watch. Marvin has a separate app (marvinbarretto.github.io/film-planner) for tracking these. Examples: "Dopesic", "The Offer".
- **project:spoons** — pub-related data, Wetherspoons-specific notes.
- **project:openclaw** — notes about improving Jimbo or this system.

## Travel notes

- Tag by country/city. Marvin revisits places and wants to recall prices, tips, phrases, recommendations.
- Short notes like "45 yen beer china 10:1" = recording local prices for future reference or a blog post.
- Travel knowledge should be richly tagged: country, city, topic (e.g. `china`, `beijing`, `beer`, `prices`).
- Marvin travels to China periodically — Chinese notes have ongoing value.

## Note style

- Notes are often a single word or short phrase — a mental bookmark, not a description.
- "Dopesic" means "watch this show". "100 Club" means "this venue matters".
- The LLM should make its best educated guess rather than sending to needs-context.
- Only use needs-context for genuinely opaque notes where even a guess would be random (e.g. "108", bare numbers with no context).

## Contacts

- Phone numbers with names (e.g. "+15616322662 Isabel") are temporary — usually "call this person" or "add to address book".
- If the note is old (> 3 months), archive it. The action is stale.

## Duplicate/related notes

- Marvin sometimes creates multiple notes about the same thing (e.g. "Dopesic" and "Dopesic painkiller").
- These should get the same tags and type. Don't archive one as a duplicate — both may have slightly different context.
