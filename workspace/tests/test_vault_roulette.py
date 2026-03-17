import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.vault_roulette import VaultRoulette


class TestVaultRoulette(unittest.TestCase):
    def _make_note(self, tmpdir, filename, title, note_type="idea", tags="[]", age_days=0):
        content = f"---\ntitle: {title}\ntype: {note_type}\nstatus: active\ntags: {tags}\n---\n\nContent for {title}.\n"
        path = os.path.join(tmpdir, filename)
        with open(path, "w") as f:
            f.write(content)
        if age_days > 0:
            mtime = time.time() - (age_days * 86400)
            os.utime(path, (mtime, mtime))
        return path

    def test_spin_returns_a_note(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "idea1.md", "Cool idea", "idea")
            self._make_note(tmpdir, "idea2.md", "Another idea", "idea")

            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin()
            self.assertIn(result["file"], ["idea1.md", "idea2.md"])
            self.assertEqual(result["type"], "idea")

    def test_spin_decaying_filters_by_age(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "old.md", "Old idea", "idea", age_days=45)
            self._make_note(tmpdir, "new.md", "Fresh idea", "idea", age_days=2)

            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin(decaying=True, decay_days=30)
            self.assertEqual(result["file"], "old.md")

    def test_spin_excludes_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "journal.md", "My journal", "journal")
            self._make_note(tmpdir, "idea.md", "An idea", "idea")

            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin()
            self.assertEqual(result["file"], "idea.md")

    def test_spin_empty_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin()
            self.assertEqual(result["status"], "no_candidates")

    def test_spin_type_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "recipe.md", "Tagine", "recipe")
            self._make_note(tmpdir, "idea.md", "AI thing", "idea")

            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin(note_type="recipe")
            self.assertEqual(result["file"], "recipe.md")


if __name__ == "__main__":
    unittest.main()
