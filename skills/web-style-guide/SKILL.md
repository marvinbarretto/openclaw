---
name: web-style-guide
description: HTML, CSS, and design standards for Jimbo's blog and web projects
user-invokable: false
---

# Web Style Guide

Reference this skill when building or updating any HTML pages — blog posts, tools, or workspace pages.

## Design Tokens

Use these CSS custom properties consistently across all pages:

```css
:root {
  --bg: #0a0a0a;
  --fg: #e6e6e6;
  --muted: #888;
  --accent: #667eea;
  --accent-glow: rgba(102, 126, 234, 0.2);
  --card-bg: #111;
  --border: #222;
}
```

Primary gradient for headings: `linear-gradient(135deg, #667eea 0%, #764ba2 100%)`
Font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

## HTML Standards

### Every page must have:
- `<!DOCTYPE html>` and `<html lang="en">`
- `<meta charset="UTF-8">`
- `<meta name="viewport" content="width=device-width, initial-scale=1.0">`
- A meaningful `<title>` — format: `{Page Title} | Jimbo's Blog`
- Semantic structure: `<header>`, `<main>`, `<footer>`

### Semantic HTML
- Use `<article>` for blog posts and standalone content
- Use `<section>` for thematic grouping within a page
- Use `<nav>` for navigation blocks
- Use `<time datetime="YYYY-MM-DD">` for all dates
- Use `<h1>` once per page, then `<h2>`, `<h3>` in order — never skip levels
- Use `<ul>` / `<ol>` for lists, not paragraphs with dashes
- Use `<code>` for inline code, `<pre><code>` for blocks
- Use `<blockquote>` for quotes, not italic paragraphs
- Use `<figure>` and `<figcaption>` for images with captions

### Accessibility
- All images need `alt` text that describes the content (not "image of...")
- Links should have descriptive text — never "click here"
- Ensure colour contrast: `--fg` on `--bg` is fine, `--muted` on `--bg` is borderline for small text
- Interactive elements need visible focus states (`:focus-visible` outline)
- Don't rely on colour alone to convey meaning — use text or icons too
- Forms need `<label>` elements associated with inputs

## CSS Approach

- Inline `<style>` block per page (no shared stylesheet — sandbox limitation)
- Mobile-first: base styles for small screens, `@media (min-width: 768px)` for larger
- Max content width: `800px` for posts, `900px` for index/listing pages
- Use `rem` for spacing, not `px` (exception: borders and fine details)
- Prefer `gap` over margins for flexbox/grid layouts
- Keep animations subtle — `transition: 0.2s ease` for hovers, no flashy effects

## What NOT to do

- Don't use CSS frameworks (Bootstrap, Tailwind) — keep it hand-crafted
- Don't add JavaScript unless it genuinely improves the page (progressive enhancement)
- Don't use `!important`
- Don't use `div` when a semantic element exists
- Don't inline styles on elements — use classes
- Don't use `id` for styling — only for anchor targets and JS hooks
