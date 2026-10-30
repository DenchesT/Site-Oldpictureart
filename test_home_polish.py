# -*- coding: utf-8 -*-
"""Offline regression checks for the OPA main-page patcher (no network)."""
import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import apply_home_polish as installer

HERE = Path(__file__).resolve().parent


class MainPagePolishTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'sitebuild').mkdir()
        (self.root / 'docs').mkdir()
        shutil.copy2(HERE / 'fixtures/posts_sample.py', self.root / 'sitebuild/posts.py')
        (self.root / 'docs/style.css').write_text('.grid.list .card {}\n.results-bar {}\n.sidebar {}\n', encoding='utf-8')
        (self.root / 'opa-ui.js').write_text('''(function () {
function setup() {
  var sidebar = document.getElementById('sidebar');
  if (sidebar) {
    function update() {}
      sidebar.addEventListener('click',function(){setTimeout(update,0);});
  }
    // Clearer action names for assistive technology, without changing toolbar structure.
}
setup();
})();''', encoding='utf-8')
        (self.root / 'apply_ui_12.py').write_text('import shutil,sys,ast\n', encoding='utf-8')
        (self.root / 'test_installer.py').write_text('import tempfile\n', encoding='utf-8')
        (self.root / 'sitebuild/visits.py').write_text('''def score():
    try:
        from functools import lru_cache
        import math
    except ImportError:
        return 0
    return math.pi
''', encoding='utf-8')

    def test_check_is_read_only(self):
        before = {x: x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        planned = installer.prepare(self.root)
        self.assertEqual(len(planned), 6)
        self.assertEqual(before, {x: x.read_bytes() for x in self.root.rglob('*') if x.is_file()})

    def test_apply_produces_six_valid_files_and_is_idempotent(self):
        planned = installer.prepare(self.root)
        installer.apply(planned)
        self.assertFalse(installer.prepare(self.root))
        for path in planned:
            self.assertTrue(path.with_name(path.name + '.before-home-polish.bak').exists())
        py = (self.root / 'sitebuild/posts.py').read_text(encoding='utf-8')
        ast.parse(py)
        for s in ('opa-now-collapsible', 'opa-sidebar-heading', 'opa-search-clear',
                  'opa-reset-inline', 'opa-card-title-link', "opa:filters-changed",
                  'По году картины: поздние', "'Найдено '"):
            with self.subTest(marker=s):
                self.assertIn(s, py)
        self.assertIn('min-width: 901px', (self.root / 'docs/style.css').read_text(encoding='utf-8'))
        for path in ('apply_ui_12.py', 'test_installer.py', 'sitebuild/visits.py'):
            self.assertNotIn('import tempfile', (self.root / path).read_text()) if path == 'test_installer.py' else None
            ast.parse((self.root / path).read_text(encoding='utf-8'))

    def test_js_syntax_from_generator_and_ui(self):
        patched = installer.patch_generator((self.root / 'sitebuild/posts.py').read_text(encoding='utf-8'))
        js = patched.split('<script>', 1)[1].split('</script>', 1)[0]
        # Source f-strings escape literal JS braces by doubling them.
        js = js.replace('{{', '{').replace('}}', '}')
        self.assertIn('const clearSearch', js)
        self.assertIn("document.dispatchEvent(new CustomEvent('opa:filters-changed'))", js)
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'home.js'
            script.write_text(js, encoding='utf-8')
            r = subprocess.run(['node', '--check', str(script)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            script.write_text(installer.patch_ui_js((self.root / 'opa-ui.js').read_text(encoding='utf-8')), encoding='utf-8')
            r = subprocess.run(['node', '--check', str(script)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_mismatch_does_not_write(self):
        path = self.root / 'sitebuild/posts.py'
        path.write_text('def something_else(): pass\n', encoding='utf-8')
        old = {x: x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        with self.assertRaises(RuntimeError):
            installer.prepare(self.root)
        self.assertEqual(old, {x: x.read_bytes() for x in self.root.rglob('*') if x.is_file()})

    def test_io_error_restores_original_sources(self):
        planned = installer.prepare(self.root)
        old = {p: p.read_bytes() for p in planned}
        actual_replace = installer.os.replace
        count = [0]

        def fail_third(a, b):
            count[0] += 1
            if count[0] == 3:
                raise OSError('simulated disk error')
            return actual_replace(a, b)

        with patch.object(installer.os, 'replace', side_effect=fail_third):
            with self.assertRaises(OSError):
                installer.apply(planned)
        self.assertEqual(old, {p: p.read_bytes() for p in planned})

    def test_no_secrets_or_git_calls(self):
        source = (HERE / 'apply_home_polish.py').read_text(encoding='utf-8')
        self.assertNotIn('git push', source)
        self.assertNotIn('git reset', source)
        self.assertNotIn("'.env'", source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
