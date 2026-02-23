# ADR-027: Migrate Blog from Static HTML to Astro

## Status

Accepted

## Context

Jimbo's blog was 4 hand-written HTML posts with a manually-maintained `index.html`. Every new post required updating the index, tags page, archive page, and (theoretically) the RSS feed by hand. This was error-prone — the "Two Weeks In" post was missing from the index because Jimbo forgot to update it.

Additionally:
- There was no `feed.xml` despite the rss-feed skill documenting how to create one
- Each post duplicated ~60 lines of CSS (design tokens + layout styles)
- The tags page and archive page had to be manually maintained
- ADR-016 confirmed that npm/Node build tools (including Astro) work in the sandbox

## Decision

Migrate the blog to Astro with content collections. Posts are markdown files with YAML frontmatter. Astro auto-generates:
- Index page with post cards and client-side tag filtering
- Individual post pages with consistent layout
- Tag listing page and per-tag filtered pages
- Chronological archive page
- RSS feed via `@astrojs/rss`

### Structure

```
/workspace/blog-src/          ← Astro project (separate from other workspace files)
  ├── src/content/posts/      ← Jimbo writes .md files here
  ├── src/layouts/            ← BaseLayout + PostLayout
  ├── src/pages/              ← index, posts/[slug], tags, archive, rss.xml
  └── src/styles/global.css   ← design tokens from web-style-guide
```

### Build pipeline

Cloudflare Pages handles the build:
- Root directory: `blog-src`
- Build command: `npm run build`
- Output directory: `dist`
- Production branch: `gh-pages`

Jimbo's workflow: write `.md` file → commit → push → Cloudflare auto-builds.

### Dependencies

- `astro` ^4.16.0 (compatible with Node 18 in sandbox)
- `@astrojs/rss` ^4.0.0

## Consequences

### What gets easier
- New posts: write one `.md` file, commit, done. No manual index/tags/archive/RSS updates.
- Consistent styling: one shared CSS file instead of duplicated inline styles per post.
- RSS feed exists and auto-updates (was missing before).
- Tags and archive are automatically maintained.
- The heartbeat auto-commit also triggers Cloudflare builds, so posts auto-publish.

### What gets harder
- Requires Node 18 + npm install in the sandbox (but ADR-016 confirmed this works).
- Cloudflare Pages needs build settings configured (one-time setup by Marvin).
- Slightly more complex than "just edit HTML" — but the markdown workflow is simpler overall.

### Migration
- Old `blog/` directory on `gh-pages` can be deleted once migration is verified.
- Blog-publisher and rss-feed skills updated for the new workflow.
- Web-style-guide skill updated to reference `global.css` as the canonical token source.
