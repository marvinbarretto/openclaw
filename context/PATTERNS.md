# Patterns

How Marvin's notes actually work. Learned through review sessions with Claude Code.

This is a living document — when understanding changes, update the relevant section. Never append contradictory entries; rewrite the old understanding instead.

*Last updated: 2026-02-23*

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

## Bare URL notes

- Many notes are just a URL with no body text — especially Twitter/X links.
- The URL IS the note. Without fetching it, the note is unclassifiable.
- During manual review, fetch the URL content (oEmbed for tweets, page title for others) before presenting.
- During automated classification (`process-inbox.py`), bare URLs should be fetched before sending to the LLM. If the URL is dead, archive. If alive, classify based on the fetched content.

## Research tasks vs bookmarks

- Some single-name notes (e.g. "Paul Rosolie", "James Baldwin", "Scott Adams") are not passive bookmarks — they're active mini research tasks: "spend 10-20 mins learning about this person/topic."
- Distinguish from media notes: "Dopesic" = watch this show (type: media). "Paul Rosolie" = research this person (type: task, tag: to-research).
- If the name is a public figure or topic rather than a specific piece of media, lean towards type: task with a `to-research` tag.

## Compound notes

- Some notes serve two purposes at once — e.g. "HK eye" = trip planning (travel) motivated by a health need (health).
- Tag with both dimensions rather than forcing a single type. Use the primary purpose as the type and the secondary as a tag (e.g. type: travel, tags: health, hong-kong, eyes).

## Recurring nudges / habit triggers

- Google Keep had "recurring notes" which Google migrated into Tasks. These are not real tasks — they're periodic self-prompts like "exercise this week?", "any walks?", "try cooking X again".
- Recipes with ratings (e.g. "Beef Massaman 10/10", "Jambalaya 9/10") are also recurring Keep notes — nudges to cook a dish again. These stay in Keep as reference; archive from the vault.
- These should be archived as stale. The nudge pattern belongs in `context/PRIORITIES.md` under "Recurring Nudges", not in the vault.
- Recognise them by: question format ("any bargains?", "weather good for?"), weekly planning language, or recipe names with ratings.

## Agent self-awareness gaps

- Jimbo doesn't reliably check his own filesystem before claiming he hasn't built something.
- Skills teach him *how* to do things, but don't make him *aware* of what he's already done.
- Fix: SOUL.md needs explicit "Your Creations" sections listing what exists and where, with instructions to check before answering.
- Session continuity: OpenClaw sessions are long-lived (heartbeat keeps them alive, compaction compresses context). Deleting the session file + restarting is the only reliable way to force a fresh start.
- After updating SOUL.md, always delete session + restart so the old context doesn't override the new instructions.

## Duplicate/related notes

- Marvin sometimes creates multiple notes about the same thing (e.g. "Dopesic" and "Dopesic painkiller").
- These should get the same tags and type. Don't archive one as a duplicate — both may have slightly different context.
