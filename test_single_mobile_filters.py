#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Регрессионные проверки исправления мобильной афиши.

Запуск: python test_single_mobile_filters.py
Работает без pytest, сети и браузера. Если установлен Playwright для Python,
дополнительно проверяет интерфейс в Chromium (на компьютере разработчика).
"""

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from apply_single_mobile_filters import (
    AFISHA, CSS, CSS_PATCH, JS_ANCHOR, JS_PATCH, JS_MARKER, CSS_MARKER,
    prepare, write_all,
)

DESCRIPTION = "Актуальные и предстоящие выставки в музеях России и мира. Завершившиеся события сохраняются в архиве."

JS_FIXTURE = '''  var mobileFilterToggle = document.getElementById('afisha-mobile-filter-toggle');
  if (mobileFilterToggle) mobileFilterToggle.addEventListener('click', function () {
    var panel = document.querySelector('.afisha-filter-panel');
    var expanded = panel.classList.toggle('expanded');
    this.setAttribute('aria-expanded', String(expanded));
  });
  function show() {}'''
BASE_CSS = '''
.afisha-page .afisha-status-switch { display: flex; }
.afisha-filter-panel { background: white; padding: 10px; }
.opa-afisha-mobile-toggle { display: none; }
.afisha-primary-filters, .afisha-filter-actions { display: block; }
@media screen and (max-width: 700px) {
  .opa-afisha-mobile-toggle { display: block; }
  .afisha-filter-panel:not(.expanded) .afisha-primary-filters,
  .afisha-filter-panel:not(.expanded) .afisha-filter-actions { display: none; }
}
'''


def fixture_py():
    return (
        'AFISHA_JS = """\n(function(){\n' + JS_FIXTURE + '\n})();\n"""\n'
        "PAGE = '''<div id=\"afisha-more-filters\"></div><button id=\"afisha-mobile-filter-toggle\"></button>"
        "<input id=\"afisha-query\"><select id=\"afisha-sort\"></select><p>"
        + DESCRIPTION + "</p>'''\n"
    )


def make_root(d):
    root = Path(d)
    (root / 'sitebuild').mkdir(exist_ok=True)
    (root / 'docs').mkdir(exist_ok=True)
    (root / AFISHA).write_text(fixture_py(), encoding='utf-8')
    (root / CSS).write_text(BASE_CSS, encoding='utf-8')
    return root


class PatcherTests(unittest.TestCase):
    def test_initial_preparation_no_write(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_root(d)
            before_py = (root / AFISHA).read_bytes()
            before_css = (root / CSS).read_bytes()
            changes = prepare(root)
            self.assertNotEqual(changes[root / AFISHA][0], changes[root / AFISHA][1])
            self.assertNotEqual(changes[root / CSS][0], changes[root / CSS][1])
            self.assertIn(JS_MARKER, changes[root / AFISHA][1])
            self.assertIn(CSS_MARKER, changes[root / CSS][1])
            ast.parse(changes[root / AFISHA][1])
            self.assertEqual(before_py, (root / AFISHA).read_bytes())
            self.assertEqual(before_css, (root / CSS).read_bytes())

    def test_apply_backup_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_root(d)
            changes = prepare(root)
            backups = write_all(changes)
            self.assertEqual(len(backups), 2)
            for p in backups:
                self.assertTrue(p.is_file())
            updated = prepare(root)
            self.assertTrue(all(before == after for before, after in updated.values()))
            self.assertEqual(write_all(updated), [])

    def test_mismatched_version_stops_without_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_root(d)
            src = (root / AFISHA)
            src.write_text(src.read_text('utf-8').replace(JS_ANCHOR, 'different code'), encoding='utf-8')
            before_css = (root / CSS).read_bytes()
            with self.assertRaises(RuntimeError):
                prepare(root)
            self.assertEqual(before_css, (root / CSS).read_bytes())

    def test_css_scoped_mobile_only(self):
        self.assertIn('@media screen and (max-width: 700px)', CSS_PATCH)
        self.assertIn('.afisha-page #afisha-more-filters > summary', CSS_PATCH)
        self.assertIn('.afisha-filter-panel.expanded #afisha-filter-actions', CSS_PATCH)
        self.assertNotIn('description', CSS_PATCH)

    def test_js_syntax_if_node_available(self):
        if not shutil.which('node'):
            self.skipTest('Node.js отсутствует')
        src = '(function(){\n' + JS_FIXTURE.replace('  function show() {}', '') + JS_PATCH + '  function show() {}\n})();'
        result = subprocess.run(['node', '--check'], text=True, input=src, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


def browser_check():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Browser: пропущено (Python Playwright не установлен)')
        return
    import os
    chromium_path = '/usr/bin/chromium' if os.path.exists('/usr/bin/chromium') else None
    browser_html = f'''<!doctype html><html lang="ru"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>{BASE_CSS}\n{CSS_PATCH}</style><body class="afisha-page">
<div class="afisha-status-switch"><button>Сейчас и скоро</button><button>Идут</button><button>Скоро</button><button>Архив</button></div>
<div class="afisha-filter-panel">
<label>Поиск<input id="afisha-query"></label>
<button id="afisha-mobile-filter-toggle" type="button" aria-expanded="false" aria-controls="afisha-primary-filters afisha-filter-actions">Фильтры</button>
<div id="afisha-primary-filters" class="afisha-primary-filters"><label>Город<select id="afisha-area"><option>Москва</option></select></label><label>Музей<select id="afisha-venue"><option>Все музеи</option></select></label></div>
<div id="afisha-filter-actions" class="afisha-filter-actions">
<details id="afisha-more-filters" class="opa-afisha-more"><summary>Дополнительные фильтры</summary>
<div class="afisha-secondary-filters"><label id="afisha-closing-box">Закрытие <select id="afisha-closing"><option>30 дней</option></select></label>
<label id="afisha-opening-box">Открытие <select id="afisha-opening"><option>90 дней</option></select></label>
<label id="afisha-archive-year-box">Архив <select id="afisha-archive-year"><option>2026</option></select></label></div>
</details><button id="afisha-reset">Сброс</button></div></div>
<label>Сортировка<select id="afisha-sort"><option>По дате</option></select></label>
<script>(function(){{\n{JS_FIXTURE.replace('  function show() {}','')}\n{JS_PATCH}\nfunction show(){{}}\n}})();</script></body></html>'''
    with sync_playwright() as p:
        kwargs = {'headless': True}
        if chromium_path:
            kwargs.update({'executable_path': chromium_path, 'args': ['--no-sandbox']})
        try:
            browser = p.chromium.launch(**kwargs)
        except Exception as e:
            print('Browser: пропущено (Chromium не доступен):', str(e)[:120])
            return
        try:
            page = browser.new_page(viewport={'width': 390, 'height': 844})
            page.set_content(browser_html)
            assert page.locator('#afisha-more-filters').get_attribute('open') is not None
            assert not page.locator('#afisha-more-filters summary').is_visible(), 'Summary visible on mobile'
            assert not page.locator('#afisha-closing').is_visible(), 'Hidden outer accordion leaked controls'
            page.locator('#afisha-mobile-filter-toggle').click()
            assert page.locator('#afisha-closing').is_visible(), 'Secondary controls should open with outer accordion'
            assert page.locator('#afisha-venue').is_visible(), 'Primary controls should open with outer accordion'
            assert not page.locator('#afisha-more-filters summary').is_visible()
            assert page.locator('#afisha-mobile-filter-toggle').get_attribute('aria-expanded') == 'true'
            assert page.locator('#afisha-sort').is_visible()
            assert page.locator('.afisha-status-switch').is_visible()
            page.locator('#afisha-mobile-filter-toggle').click()
            assert not page.locator('#afisha-closing').is_visible()
            # Desktop: original details accordion is still available.
            page.set_viewport_size({'width': 1050, 'height': 860})
            page.wait_for_function("!document.getElementById('afisha-more-filters').open")
            assert page.locator('#afisha-more-filters summary').is_visible()
            page.locator('#afisha-more-filters summary').click()
            assert page.locator('#afisha-closing').is_visible()
            page.set_viewport_size({'width': 390, 'height': 844})
            page.wait_for_function("document.getElementById('afisha-more-filters').hasAttribute('data-opa-mobile-detail')")
            assert not page.locator('#afisha-more-filters summary').is_visible()
            page.set_viewport_size({'width': 1050, 'height': 860})
            page.wait_for_function("!document.getElementById('afisha-more-filters').hasAttribute('data-opa-mobile-detail')")
            assert page.locator('#afisha-more-filters').get_attribute('open') is not None, 'Desktop open state lost'
            page.close()
            print('Browser OK: мобильный единый фильтр, скрытие, десктоп, изменение ширины.')
        finally:
            browser.close()


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PatcherTests)
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    if not outcome.wasSuccessful():
        raise SystemExit(1)
    browser_check()
