"""Offline regression tests for apply_log_fixes and the Telethon compatibility shim.

Run from the project root: python tests/test_log_fixes.py
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import apply_log_fixes as fix


class UpdateTests(unittest.TestCase):
    def test_afisha_links_targeted_only(self):
        records = {"exhibitions": [
            {"title": t, "url": old, "other": "оставить"}
            for t, (old, new) in fix.EXHIBITION_LINKS.items()
        ] + [{"title": "Русский Париж. 1814–1914", "url":
                   "https://www.domrz.ru/exhibition/70568_russkiy_parizh_1814_1914/"}]}
        original = json.dumps(records, ensure_ascii=False, indent=2)
        updated = fix.update_afisha(original)
        got = json.loads(updated)["exhibitions"]
        for t, (_, new) in fix.EXHIBITION_LINKS.items():
            self.assertEqual(next(it for it in got if it["title"] == t)["url"], new)
        self.assertEqual(got[-1]["url"], records["exhibitions"][-1]["url"])
        self.assertEqual(updated, fix.update_afisha(updated))

    def test_afisha_refuses_unknown_url(self):
        data = {"exhibitions": [{"title": t, "url": "https://different.example"}
                                 for t in fix.EXHIBITION_LINKS]}
        with self.assertRaises(ValueError):
            fix.update_afisha(json.dumps(data, ensure_ascii=False))

    def test_map_override_and_idempotence(self):
        payload = '{\n  "Частная коллекция": {"skip": true},\n' \
                  '  "Частная коллекция, Монте-Карло": {"skip": true}\n}\n'
        result = fix.update_overrides(payload)
        self.assertTrue(json.loads(result)[fix.MUSEUM]["skip"])
        self.assertEqual(result, fix.update_overrides(result))

    def test_preexisting_museum_override_not_overwritten(self):
        data = {fix.MUSEUM: {"address": "user-defined"},
                "Частная коллекция, Монте-Карло": {"skip": True}}
        with self.assertRaises(ValueError):
            fix.update_overrides(json.dumps(data, ensure_ascii=False))

    def test_place_code_replaces_both_warning_paths(self):
        initial = '''def foo():
    try:
        import generate_map as gm
        doubts = gm.map_warnings(museum_names(all_posts, visits),
                                 gm.load_cache(), gm.load_overrides(quiet=True))
    except Exception:
        pass
    try:
        bare = [n for n in museum_names(all_posts, visits) if not museum_info(n, directory)["address"]]
    except Exception:
        pass
'''
        edited = fix.update_places(initial)
        self.assertIn('not (overrides.get(n) or {}).get("skip")', edited)
        self.assertEqual(edited, fix.update_places(edited))

    def test_telegram_code_hides_phone_and_installs_compat(self):
        initial = '''def foo():
    import TelethonFakeTLS
    TELETHON_AVAILABLE = True
    logger.info(f"Аккаунт: {PHONE}")
'''
        edited = fix.update_telegram(initial)
        self.assertNotIn('Аккаунт: {PHONE}', edited)
        self.assertIn('patch_faketls_wait_closed()', edited)
        self.assertEqual(edited, fix.update_telegram(edited))

    def test_ci_includes_new_tests(self):
        original = '''      - name: Все проверки сайта
        run: node tests/run.js'''
        updated = fix.update_workflow(original)
        self.assertIn('python tests/test_log_fixes.py', updated)
        self.assertEqual(updated, fix.update_workflow(updated))

    def test_full_update_dry_run_apply_and_reapply(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'sitebuild').mkdir()
            (root / 'tests').mkdir()
            (root / '.github/workflows').mkdir(parents=True)
            (root / 'build_site.py').write_text('# stub', encoding='utf-8')
            (root / 'afisha.json').write_text(json.dumps({'exhibitions': [
                {'title': title, 'url': old}
                for title, (old, _) in fix.EXHIBITION_LINKS.items()
            ]}, ensure_ascii=False, indent=2), encoding='utf-8')
            (root / 'museum_overrides.json').write_text(
                '{\n  "Частная коллекция, Монте-Карло": {"skip": true}\n}\n', encoding='utf-8')
            (root / 'sitebuild/places.py').write_text('''def f():
    try:
        import generate_map as gm
        doubts = gm.map_warnings(museum_names(all_posts, visits),
                                 gm.load_cache(), gm.load_overrides(quiet=True))
    except Exception:
        pass
    try:
        bare = [n for n in museum_names(all_posts, visits) if not museum_info(n, directory)["address"]]
    except Exception:
        pass
''', encoding='utf-8')
            (root / 'sitebuild/telegram.py').write_text('''try:
    import TelethonFakeTLS
    TELETHON_AVAILABLE = True
except ImportError:
    pass
def require_credentials():
    logger.info(f"Аккаунт: {PHONE}")
''', encoding='utf-8')
            (root / '.github/workflows/tests.yml').write_text('''      - name: Все проверки сайта
        run: node tests/run.js
''', encoding='utf-8')
            (root / 'sitebuild/telethon_compat.py').write_text('# shim', encoding='utf-8')
            (root / 'tests/test_log_fixes.py').write_text('# tests', encoding='utf-8')
            self.assertEqual(fix.main(['--dry-run'], root=root), 0)
            self.assertNotIn(fix.MUSEUM, json.loads((root / 'museum_overrides.json').read_text()))
            self.assertEqual(fix.main([], root=root), 0)
            self.assertTrue(json.loads((root / 'museum_overrides.json').read_text())[fix.MUSEUM]['skip'])
            self.assertTrue((root / 'afisha.json.bak').is_file())
            self.assertEqual(fix.main([], root=root), 0)

    def test_failed_plan_does_not_edit_any_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'sitebuild').mkdir()
            (root / 'build_site.py').write_text('# stub', encoding='utf-8')
            (root / 'afisha.json').write_text('{bad', encoding='utf-8')
            before = (root / 'afisha.json').read_bytes()
            with self.assertRaises(json.JSONDecodeError):
                fix.plan(root)
            self.assertEqual((root / 'afisha.json').read_bytes(), before)


class WriterTests(unittest.TestCase):
    def test_legacy_writer_gets_wait_closed(self):
        path = ROOT / 'sitebuild' / 'telethon_compat.py'
        spec = importlib.util.spec_from_file_location('test_opa_compat', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fake_package_names = ['TelethonFakeTLS', 'TelethonFakeTLS.FakeTLS',
                              'TelethonFakeTLS.FakeTLS.TLSInOut']
        saved = {name: sys.modules.get(name) for name in fake_package_names}
        try:
            for name in fake_package_names:
                sys.modules[name] = types.ModuleType(name)
            class FakeTLSStreamWriter:
                def __init__(self, upstream):
                    self.upstream = upstream
            sys.modules[fake_package_names[-1]].FakeTLSStreamWriter = FakeTLSStreamWriter
            self.assertTrue(module.patch_faketls_wait_closed())
            self.assertFalse(module.patch_faketls_wait_closed())
            class Upstream:
                was_closed = False
                async def wait_closed(self):
                    self.was_closed = True
            up = Upstream()
            asyncio.run(FakeTLSStreamWriter(up).wait_closed())
            self.assertTrue(up.was_closed)
            # Older upstream writer without wait_closed still exits cleanly.
            asyncio.run(FakeTLSStreamWriter(object()).wait_closed())
        finally:
            for name, original in saved.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original


if __name__ == '__main__':
    unittest.main(verbosity=2)
