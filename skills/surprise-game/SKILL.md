---
name: surprise-game
description: Find one genuinely surprising connection across email gems, vault tasks, and interests
user-invokable: false
---

# Surprise Game

You are running as an isolated cron job. Your job: find ONE genuinely surprising, non-obvious connection across Jimbo's data sources. This is where you get to show off your personality and creativity.

## What makes a GOOD surprise

- An email gem that connects to a vault task in a way Marvin wouldn't have noticed
- A calendar event that pairs with a newsletter insight for unexpected reasons
- A travel deal that aligns with a hobby goal or upcoming event
- Two completely unrelated sources that illuminate each other

## What makes a BAD surprise (never do these)

- "Both mention AI" or "both are about technology" — too generic
- Forced connections with no genuine insight
- Things Marvin would obviously already know
- Restating what the email/gem already says

## Steps

### 1. Gather sources

Today's gems:
```bash
cat /workspace/briefing-input.json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(json.dumps(g)) for g in d.get('gems',[])]"
```

Vault tasks:
```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/tasks?sort=priority&limit=20"
```

Context:
```bash
python3 /workspace/context-helper.py priorities
python3 /workspace/context-helper.py interests
```

### 2. Find the connection

Cross-reference gems with vault tasks, priorities, and interests. Look for:
- Shared themes across unrelated sources
- Timing coincidences (event + newsletter + task aligning)
- Contrasting perspectives on the same topic from different worlds
- Hidden relevance (something that looks unrelated but connects to a goal)

### 3. Present it

Start with a label, then use your editorial voice. Be enthusiastic but genuine. Structure:

> **[Surprise]**
> **[Catchy one-liner]**
> [The connection — what links these things]
> [Why it matters to Marvin specifically]
> [Link(s) if available]

### 4. Output discipline

**If nothing genuinely surprises you today: produce ZERO output.** A forced surprise is worse than none. Skip days are fine — quality over quantity.

### 5. Log

```bash
python3 /workspace/activity-log.py log --type surprise-game --description "[brief connection]" --outcome "delivered"
```

Use "skipped — nothing genuine" as outcome if you stayed silent.
