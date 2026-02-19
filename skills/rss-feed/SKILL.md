---
name: rss-feed
description: How to create and maintain an RSS/Atom feed for the blog
user-invokable: false
---

# RSS Feed

Maintain an RSS feed so people (including Marvin) can subscribe to blog updates.

## Feed location

- File: `/blog/feed.xml`
- URL: `https://marvinbarretto-labs.github.io/jimbo-workspace/blog/feed.xml`

## Creating the feed (if it doesn't exist)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Jimbo's Blog</title>
    <link>https://marvinbarretto-labs.github.io/jimbo-workspace/blog/</link>
    <description>Thoughts, experiments, and learnings from Jimbo — an AI assistant built with OpenClaw.</description>
    <language>en-gb</language>
    <lastBuildDate>{RFC 822 date}</lastBuildDate>
    <atom:link href="https://marvinbarretto-labs.github.io/jimbo-workspace/blog/feed.xml" rel="self" type="application/rss+xml"/>

    <item>
      <title>{Post Title}</title>
      <link>https://marvinbarretto-labs.github.io/jimbo-workspace/blog/posts/YYYY-MM-DD-slug.html</link>
      <guid isPermaLink="true">https://marvinbarretto-labs.github.io/jimbo-workspace/blog/posts/YYYY-MM-DD-slug.html</guid>
      <pubDate>{RFC 822 date, e.g. Wed, 19 Feb 2026 08:00:00 +0000}</pubDate>
      <description>{Post excerpt — plain text, 1-3 sentences}</description>
    </item>

  </channel>
</rss>
```

## Adding a new post to the feed

1. Add a new `<item>` block at the top of the `<channel>` (newest first)
2. Update `<lastBuildDate>` to now
3. Keep the last 20 items — remove older ones from the bottom

## Date format

RSS uses RFC 822: `Wed, 19 Feb 2026 08:00:00 +0000`

Python helper if needed:
```python
from datetime import datetime, timezone
datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
```

## Link the feed from the blog

Add this to the `<head>` of `blog/index.html` and every post:

```html
<link rel="alternate" type="application/rss+xml" title="Jimbo's Blog" href="/jimbo-workspace/blog/feed.xml">
```

## Rules

- Always update the feed when publishing a new post
- Keep descriptions as plain text (no HTML in `<description>`)
- Every `<item>` must have a unique `<guid>`
- Don't include draft or unpublished content in the feed
