---
name: blog-publisher
description: How to write, structure, and publish blog posts to GitHub Pages
user-invokable: false
---

# Blog Publisher

Reference this skill when creating or updating blog posts.

## Blog location

- Blog index: `/blog/index.html`
- Posts: `/blog/posts/YYYY-MM-DD-kebab-case-slug.html`
- Deployed via: `git add . && git commit && git push` to `gh-pages` branch
- Live at: `https://marvinbarretto-labs.github.io/jimbo-workspace/blog/`

## Creating a new post

### 1. Write the HTML

Use this template structure (refer to `web-style-guide` skill for design tokens and standards):

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{Post Title} | Jimbo's Blog</title>
  <style>
    /* Include design tokens from web-style-guide */
    /* Include page-specific styles */
  </style>
</head>
<body>
  <div class="container">
    <header>
      <a href="/jimbo-workspace/blog/" class="back-link">← Back to Blog</a>
      <h1>{Post Title}</h1>
      <div class="meta">
        <time datetime="YYYY-MM-DD">{Day} {DD} {Month} {YYYY}</time>
      </div>
      <div class="tags">
        <a href="/jimbo-workspace/blog/?tag=foo" class="tag">#foo</a>
      </div>
    </header>
    <main class="content">
      <!-- Your content here -->
    </main>
    <footer>
      <p>Built with plain HTML • © 2026 Jimbo</p>
    </footer>
  </div>
</body>
</html>
```

### 2. Update the blog index

Add a new `<article>` card to `/blog/index.html` at the top of the posts list (newest first):

```html
<article>
  <h2><a href="/jimbo-workspace/blog/posts/YYYY-MM-DD-slug.html">{Title}</a></h2>
  <time datetime="YYYY-MM-DD">{Human date}</time>
  <p>{Short excerpt — 1-2 sentences}</p>
  <div class="tags">
    <a href="/jimbo-workspace/blog/?tag=foo" class="tag">#foo</a>
  </div>
</article>
```

### 3. Update the RSS feed

If `/blog/feed.xml` exists, add a new `<item>` at the top of the feed. See the `rss-feed` skill.

### 4. Commit and push

```bash
git add blog/posts/YYYY-MM-DD-slug.html blog/index.html blog/feed.xml
git commit -m "New post: {title}"
git push
```

## Writing guidelines

- Write in first person — you're Jimbo, writing your own blog
- Be genuine about what you learned, built, or found interesting
- Include code snippets when relevant (use `<pre><code>`)
- Link to sources and references
- Keep posts focused — one topic per post
- Tag posts with relevant categories (2-4 tags)
- Mention Marvin's projects when relevant (Spoons, LocalShout, Pomodoro)

## Post naming

Pattern: `YYYY-MM-DD-kebab-case-slug.html`

Good: `2026-02-19-email-digest-first-look.html`
Bad: `new_post.html`, `blog3.html`, `2026-02-19.html`

## Diary vs blog

- **Diary** (`JIMBO_DIARY.md`): internal notes, quick thoughts, daily log. Not published.
- **Blog**: polished content meant for readers. Published to GitHub Pages.

If something starts as a diary entry and turns out interesting, turn it into a blog post.
