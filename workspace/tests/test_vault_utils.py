import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.vault_utils import parse_frontmatter, extract_urls, html_to_text, update_frontmatter, write_vault_note_atomic


class TestParseFrontmatter(unittest.TestCase):
    def test_basic_frontmatter(self):
        content = "---\ntitle: Test Note\ntype: bookmark\nstatus: active\ntags: [\"ai\", \"agents\"]\n---\n\nBody text here."
        meta, body = parse_frontmatter(content)
        self.assertEqual(meta["title"], "Test Note")
        self.assertEqual(meta["type"], "bookmark")
        self.assertEqual(meta["status"], "active")
        self.assertIn("Body text here", body)

    def test_no_frontmatter(self):
        content = "Just a plain file."
        meta, body = parse_frontmatter(content)
        self.assertEqual(meta, {})
        self.assertEqual(body, "Just a plain file.")

    def test_frontmatter_with_quotes(self):
        content = '---\ntitle: "Quoted: title"\nconfidence: 9\n---\n\nBody.'
        meta, body = parse_frontmatter(content)
        self.assertEqual(meta["title"], "Quoted: title")
        self.assertEqual(meta["confidence"], "9")


class TestExtractUrls(unittest.TestCase):
    def test_links_section(self):
        content = "---\ntype: bookmark\n---\n\n## Links\n- https://example.com/article\n- https://other.com/page\n"
        urls = extract_urls(content)
        self.assertEqual(urls, ["https://example.com/article", "https://other.com/page"])

    def test_no_links(self):
        content = "---\ntype: task\n---\n\nJust a task."
        urls = extract_urls(content)
        self.assertEqual(urls, [])

    def test_inline_urls(self):
        content = "---\ntype: bookmark\n---\n\nCheck out https://example.com/inline for details."
        urls = extract_urls(content)
        self.assertEqual(urls, ["https://example.com/inline"])


class TestHtmlToText(unittest.TestCase):
    def test_basic_html(self):
        html = "<html><body><h1>Title</h1><p>Paragraph one.</p><p>Paragraph two.</p></body></html>"
        text = html_to_text(html)
        self.assertIn("Title", text)
        self.assertIn("Paragraph one", text)
        self.assertNotIn("<", text)

    def test_strips_script_and_style(self):
        html = "<html><head><style>body{color:red}</style></head><body><script>alert('hi')</script><p>Real content.</p></body></html>"
        text = html_to_text(html)
        self.assertIn("Real content", text)
        self.assertNotIn("alert", text)
        self.assertNotIn("color:red", text)

    def test_strips_nav_and_footer(self):
        html = "<nav>Menu items</nav><main><p>Article content.</p></main><footer>Copyright</footer>"
        text = html_to_text(html)
        self.assertIn("Article content", text)
        self.assertNotIn("Menu items", text)
        self.assertNotIn("Copyright", text)


class TestUpdateFrontmatter(unittest.TestCase):
    def test_adds_new_fields(self):
        content = "---\ntitle: Test\ntype: bookmark\n---\n\nBody."
        updated = update_frontmatter(content, {"enriched": "true", "enriched_at": "2026-03-17T12:00:00Z"})
        self.assertIn("enriched: true", updated)
        self.assertIn("enriched_at:", updated)
        self.assertIn("Body.", updated)

    def test_overwrites_existing_fields(self):
        content = "---\ntitle: Old\ntype: bookmark\n---\n\nBody."
        updated = update_frontmatter(content, {"title": "New Title"})
        self.assertIn("title: New Title", updated)
        self.assertNotIn("title: Old", updated)


if __name__ == "__main__":
    unittest.main()
