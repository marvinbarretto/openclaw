---
name: blog-publisher
description: How to write and publish blog posts using Astro content collections
user-invokable: false
---

# Blog Publisher

Reference this skill when creating or updating blog posts.

## Blog location

- **Astro source:** `/workspace/blog-src/`
- **Posts directory:** `/workspace/blog-src/src/content/posts/`
- **Live at:** `https://jimbo.pages.dev/`
- **Build:** Cloudflare Pages runs `npm run build` automatically on push

### Workflow

1. Write a `.md` file in the posts directory
2. Commit and push — Cloudflare auto-builds and deploys
3. Index, tags, archive, and RSS feed are all auto-generated. No manual updates needed.

### If you hit permission errors
- Run `chmod -R a+rw /workspace/blog-src/` — do NOT delete and recreate files.
- Never use `chown` (it will fail in the sandbox).
- Never `rm -rf` directories containing posts — you'll lose content.

## Creating a new post

### 1. Write the markdown file

Create a new file at `/workspace/blog-src/src/content/posts/YYYY-MM-DD-kebab-case-slug.md` with this frontmatter:

```markdown
---
title: "Your Post Title"
date: YYYY-MM-DD
description: "A short excerpt — 1-2 sentences for index cards and RSS."
tags: [tag1, tag2, tag3]
---

Post content in markdown here...
```

### 2. Commit and push

```bash
cd /workspace
git add blog-src/src/content/posts/YYYY-MM-DD-slug.md
git commit -m "New post: title"
git push
```

That's it. Astro auto-generates:
- The post page at `/posts/YYYY-MM-DD-slug/`
- The index listing with excerpt and tags
- Tag pages for each tag used
- The archive page
- The RSS feed at `/rss.xml`

### Frontmatter fields

| Field | Required | Description |
|---|---|---|
| `title` | Yes | Post title (displayed as gradient heading) |
| `date` | Yes | Publication date (YYYY-MM-DD) |
| `description` | Yes | Short excerpt for cards and RSS (1-2 sentences) |
| `tags` | Yes | Array of tag strings (2-4 tags) |
| `draft` | No | Set to `true` to hide from listings and RSS |

## Writing guidelines

- Write in first person — you're Jimbo, writing your own blog
- Be genuine about what you learned, built, or found interesting
- Use markdown formatting: `##` headings, `**bold**`, `` `code` ``, `> blockquotes`
- Link to sources and references
- Keep posts focused — one topic per post
- Tag posts with relevant categories (2-4 tags)
- Mention Marvin's projects when relevant (Spoons, LocalShout, Pomodoro)

## Post naming

Pattern: `YYYY-MM-DD-kebab-case-slug.md`

Good: `2026-02-19-email-digest-first-look.md`
Bad: `new_post.md`, `blog3.md`, `2026-02-19.md`

## Diary vs blog

- **Diary** (`JIMBO_DIARY.md`): internal notes, quick thoughts, daily log. Not published.
- **Blog**: polished content meant for readers. Published via Astro to Cloudflare Pages.

If something starts as a diary entry and turns out interesting, turn it into a blog post.

## Design

The blog uses design tokens from the `web-style-guide` skill. Styles live in `/workspace/blog-src/src/styles/global.css` and Astro layouts in `/workspace/blog-src/src/layouts/`. Dark theme, purple accent gradient, system fonts.
