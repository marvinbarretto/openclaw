# Patterns

How Marvin's notes actually work. Learned through review sessions with Claude Code.

This is a living document — when understanding changes, update the relevant section. Never append contradictory entries; rewrite the old understanding instead.

*Last updated: 2026-02-23*

## Projects as destinations

Marvin's notes often serve a hidden purpose — feeding into a specific project. Tag these with `project:<name>`.

- **project:localshout** — venues, event sources, artists, festivals, comedy nights. Anything that could populate LocalShout's event/venue database. Examples: "100 Club", "Bristol Comedy Festival", "Watford Film Club", "FANE what's on", "Bedford events". URLs to event listing sites (filmclub, fane.co.uk, dice) are LocalShout tasks, not bookmarks — they're sources to integrate.
- **project:film-planner** — film, TV, show recommendations to watch. Marvin has a separate app (marvinbarretto.github.io/film-planner) for tracking these. Examples: "Dopesic", "The Offer".
- **project:spoons** — pub-related data, Wetherspoons-specific notes. Also gamification ideas (badges, leaderboards, collecting).
- **project:openclaw** — notes about improving Jimbo or this system. Includes prompts like "interview me about this plan", notes about model orchestration, links to Obsidian/productivity tool approaches.

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
- Fresh session command: `ssh jimbo "rm /home/openclaw/.openclaw/agents/main/sessions/sessions.json && systemctl restart openclaw"`
- Check session state: `openclaw sessions --active 5` (shows recent sessions with token usage)

## VPS sandbox git operations (from host)

Running git on the VPS as root against the workspace requires two things:
- `GIT_CONFIG_GLOBAL=/home/openclaw/.openclaw/workspace/.gitconfig` — so git finds user identity and safe.directory
- The `.gitconfig` must include BOTH `safe.directory = /workspace` (container path) AND `safe.directory = /home/openclaw/.openclaw/workspace` (host path)
- Without both paths, git works inside the sandbox but fails when accessed from the host via SSH.

## Jimbo's git hygiene

- Jimbo will `git add .` and commit everything in the workspace if not guided — OAuth tokens, Homebrew caches, node_modules, etc.
- **Always have a `.gitignore`** in the workspace. Added one covering: `*.token.json`, `*access-token*`, `.cache/`, `.npm-cache/`, `.config/`, `node_modules/`, `memory/`.
- GitHub push protection will block pushes containing secrets. Fix: rewrite history (reset to clean state, re-commit), don't just "allow" the secret.
- Permissions drift: files created by root in the container get restrictive permissions (644). Periodic `chmod -R a+rw` on blog/posts/ needed.
- The blog post directory (`blog/posts/`) was owned by `root:root` while the rest of `blog/` was `openclaw:openclaw` — this caused sandbox read tool failures even though exec worked.

## Completed tasks

- Many notes are tasks that have already been done. The LLM has no way to know this without being told.
- Look for signals: notes that describe actions Marvin is already doing (e.g. "help me work through my backlog" when the vault pipeline exists), or notes that match completed work in the repo.
- Archive with stale_reason "completed", not "stale".

## People as tasks

- Notes with just a person's name (e.g. "Kat!", "Feather table", "Ring Alvin") are usually tasks to contact that person, not passive person records.
- They often carry hidden context: "Kat" = ask her to test LocalShout. "Feather table" = ask about his table + suggest pool.
- Tag with `person:<name>` and the relevant project/context if known.
- If the contact action is old (> 3 months), archive as stale unless there's ongoing relationship value.

## Sequential/related notes

- Some notes only make sense in sequence. "Clean notes off old computer" followed by "Get them off, wipe" — the second refers to the first.
- When processing, look at adjacent notes (by creation date) for context that might clarify an otherwise opaque note.

## Conversation starters for Jimbo

- Some notes are prompts designed to start a conversation with Jimbo: "interview me relentlessly about this plan", "help me work through my backlog", "be bold with reading and coding in the sandbox".
- If the conversation has already happened, archive as completed. If not yet done, classify as task with `project:openclaw`.

## "Shape Up" is not fitness

- "Shape Up" by Basecamp is a product development methodology book, not a fitness book. The LLM consistently misclassifies this as health/fitness.
- More generally: short titles that sound like one domain often belong to another. When uncertain, lean towards needs-context rather than guessing.

## Duplicate/related notes

- Marvin sometimes creates multiple notes about the same thing (e.g. "Dopesic" and "Dopesic painkiller").
- These should get the same tags and type. Don't archive one as a duplicate — both may have slightly different context.

## BuzzFeed notes

- Marvin still does some work for BuzzFeed — BuzzFeed notes are NOT automatically stale.
- Internal tool references (Atlassian/Jira tickets, internal URLs like `bf-island-ui.dev.buzzfeed.io`) may be active work items. Don't archive without context.
- BuzzFeed article URLs (buzzfeed.com/author/article) may be bookmarks worth keeping.
- Only archive BuzzFeed notes if they're clearly outdated based on other signals (very old date, completed task language, etc.) — not just because they mention BuzzFeed.

## Single-item shopping/packing lists

- Notes like "milk, fill", "tissues", "shower and hand gel" are often completed shopping errands or packing checklists.
- If old (> 1 month), archive as completed — the purchase was almost certainly made.
- Don't classify as "task" — these aren't ongoing tasks, they're one-shot reminders.

## Person nicknames

- Some notes use nicknames or first names that map to specific people: "Silver" = Adam Silver (a friend), "Surath" = a specific person (not a place).
- When a name appears with an action ("Surath goes Sunday", "Silver lunch"), it's a social plan or task, not a person record.
- If old (> 3 months), archive as stale — the social event has passed.

## Credentials and secrets in notes

- Some notes contain API keys, AWS credentials, or passwords dumped from Google Keep.
- These should be archived immediately. Flag to Marvin to rotate the credentials if still active.
- Never include credential values in classification output or logs.

## Opaque numbers and codes

- Bare numbers like "12", "1520", "108" with no context are almost always unrecoverable.
- If old (> 1 month), archive as stale. Don't send to needs-context — manual review won't help either.
- Exception: numbers that look like prices ("45 yen"), dates ("17 v 22" = match score), or phone numbers.
