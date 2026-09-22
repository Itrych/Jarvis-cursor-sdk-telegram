from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from jarvis.files import (
    ProjectPathError,
    format_tree,
    resolve_inside,
    zip_target,
)


class FilesTests(unittest.TestCase):
    def test_resolve_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "ok.txt").write_text("x", encoding="utf-8")
            with self.assertRaises(ProjectPathError):
                resolve_inside(root, "../secret")
            with self.assertRaises(ProjectPathError):
                resolve_inside(root, "C:/Windows")
            self.assertEqual(resolve_inside(root, "ok.txt").name, "ok.txt")
            self.assertEqual(resolve_inside(root, "."), root.resolve())

    def test_format_tree_and_zip_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "readme.md").write_text("hi", encoding="utf-8")
            nested = root / "src"
            nested.mkdir()
            (nested / "app.py").write_text("print(1)\n", encoding="utf-8")
            (nested / ".hidden").write_text("nope", encoding="utf-8")
            (root / "venv").mkdir()
            (root / "venv" / "x.py").write_text("skip", encoding="utf-8")

            tree, top_level, truncated = format_tree(root)
            self.assertFalse(truncated)
            self.assertIn("readme.md", tree)
            self.assertIn("src/", tree)
            self.assertIn("app.py", tree)
            self.assertNotIn("venv", tree)
            self.assertNotIn(".hidden", tree)
            self.assertEqual(set(top_level), {"readme.md", "src/"})

            sub_tree, sub_top, _ = format_tree(root, nested)
            self.assertEqual(sub_top, ["src/app.py"])
            self.assertIn("app.py", sub_tree)

            zip_path = root / "out.zip"
            zip_target(root, nested, zip_path)
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
            self.assertEqual(names, ["src/app.py"])
            self.assertNotIn(".hidden", " ".join(names))

            whole = root / "all.zip"
            zip_target(root, root, whole)
            with zipfile.ZipFile(whole) as archive:
                names = set(archive.namelist())
            self.assertTrue(any(name.endswith("readme.md") for name in names))
            self.assertFalse(any("venv" in name for name in names))


if __name__ == "__main__":
    unittest.main()
