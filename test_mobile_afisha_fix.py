# -*- coding: utf-8 -*-
"""Самопроверка мобильного CSS и безопасного установщика. Запуск из корня проекта."""
import ast
import tempfile
import unittest
from pathlib import Path

import apply_mobile_afisha_fix as patch


class FixTests(unittest.TestCase):
    def test_css_media_only_and_complete_borders(self):
        s = Path(patch.__file__).with_name("afisha_mobile_ui.css").read_text(encoding="utf-8")
        # No third-party CSS parser required on the user's Windows machine.
        self.assertEqual(s.count("@media"), 1)
        self.assertEqual(s.count("{"), s.count("}"))
        self.assertIn("@media (max-width: 700px)", s)
        for phrase in ('.afisha-status-switch button + button', 'border: 1px solid var(--border)',
                       'gap: .45rem', 'grid-template-columns: repeat(2, minmax(0, 1fr))',
                       '.tag-topbar', '.afisha-filter-panel'):
            self.assertIn(phrase, s)
        self.assertNotIn('display: none !important', s)
        self.assertNotIn('Актуальные и предстоящие выставки', s)  # description stays in generator

    def sandbox(self, path):
        root = Path(path)
        (root / 'sitebuild').mkdir(exist_ok=True)
        (root / 'docs').mkdir(exist_ok=True)
        (root / patch.CSS_FILE).write_text('.afisha-status-switch{}\n.afisha-filter-panel{}\n.tag-topbar{}\n', encoding='utf-8')
        (root / patch.POSTS_FILE).write_text('before\n' + patch.OLD_HEADING + '\nafter\n', encoding='utf-8')
        (root / 'sitebuild/afisha.py').write_text('x = ' + repr(patch.DESCRIPTION), encoding='utf-8')
        return root

    def test_apply_and_reapply(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.sandbox(directory)
            changes = patch.prepare(root)
            self.assertEqual(len(changes), 2)
            self.assertEqual(len(patch.write_all(changes, root)), 2)
            self.assertIn(patch.NEW_HEADING, (root/patch.POSTS_FILE).read_text(encoding='utf-8'))
            css = (root/patch.CSS_FILE).read_text(encoding='utf-8')
            self.assertEqual(css.count(patch.CSS_START), 1)
            self.assertEqual(len(patch.write_all(patch.prepare(root), root)), 0)
            self.assertEqual((root/patch.CSS_FILE).read_text(encoding='utf-8'), css)
            self.assertEqual((root/'sitebuild/afisha.py').read_text(encoding='utf-8'), 'x = ' + repr(patch.DESCRIPTION))

    def test_unknown_version_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.sandbox(directory)
            posts = root/patch.POSTS_FILE
            posts.write_text('legacy navbar', encoding='utf-8')
            old_css = (root/patch.CSS_FILE).read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'Не найден блок'):
                patch.prepare(root)
            self.assertEqual(old_css, (root/patch.CSS_FILE).read_bytes())
            self.assertEqual(posts.read_text(encoding='utf-8'), 'legacy navbar')

    def test_new_css_no_duplicate_and_posts_python_syntax(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.sandbox(directory)
            patch.write_all(patch.prepare(root), root)
            # The demo file is a fragment, so inspect only the generated section.
            self.assertIn(patch.NEW_HEADING, (root / patch.POSTS_FILE).read_text(encoding='utf-8'))
            ast.parse(Path(patch.__file__).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
