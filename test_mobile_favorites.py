# -*- coding: utf-8 -*-
"""Offline regressions for the mobile / exhibition-favorites patch.

Run after installing: python test_mobile_favorites.py
"""
from pathlib import Path
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile

from apply_mobile_favorites import FILES, MARKER, SHARED_FAVORITES_JS, patch_css, patch_ui

ROOT = Path(__file__).resolve().parent


def check(label, flag):
    if not flag:
        raise AssertionError(label)
    print('OK  ', label)


def main():
    project = Path.cwd()
    if (project / 'sitebuild/posts.py').is_file():
        texts = {name: (project / name).read_text(encoding='utf-8') for name in FILES}
        check('6 installed files and markers', len(texts) == 6 and all(MARKER in s for s in texts.values()))
        check('published JavaScript matches source', texts['docs/opa-ui.js'] == texts['opa-ui.js'])
        for name in ('site_common.py', 'sitebuild/posts.py', 'sitebuild/afisha.py'):
            ast.parse(texts[name], filename=name)
        check('Python generators compile', True)
        check('main search has no hotkey hint',
              'Поиск по названию, художнику или музею' in texts['sitebuild/posts.py'] and
              '· клавиша /' not in texts['sitebuild/posts.py'])
        check('mobile controls moved inside menu',
              'mobileControls.appendChild(toolbar)' in texts['opa-ui.js'] and
              "sidebar.querySelector('.sidebar-search')" in texts['opa-ui.js'])
        check('mobile gallery has space around restored focus',
              'index-page .card-link:focus-visible::after' in texts['docs/style.css'] and
              'padding: var(--s4) var(--s2) var(--s5)' in texts['docs/style.css'])
        check('two groups in favorites sidebar',
              'fav-afisha-list' in texts['sitebuild/posts.py'] and
              'opa-fav-subhead' in texts['sitebuild/posts.py'])
        check('afisha login, cloud sync and catalog included in generated markup',
              '_afisha_favorites_script(all_items)' in texts['sitebuild/afisha.py'] and
              '{AUTH_JS}' in texts['sitebuild/afisha.py'])
        check('gallery cloud-sync does not mix exhibition IDs with painting IDs',
              'indexOf(\'exh_\') !== 0' in texts['site_common.py'])
        # Validate stable cloud ids and HTML script injection safety.
        tree = ast.parse(texts['sitebuild/afisha.py'])
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and
                 n.name in ('_afisha_favorite_key', '_afisha_favorites_script')]
        check('stable cloud-ID functions exist', len(funcs) == 2)
        env = {'json': json, 'hashlib': hashlib}
        exec(compile(ast.Module(body=funcs, type_ignores=[]), '<afisha-helpers>', 'exec'), env)
        key = env['_afisha_favorite_key']('a-mone-moskva')
        check('cloud ID fits existing YDB input validation', len(key) <= 40 and bool(re.fullmatch('[0-9A-Za-z_-]+', key)))
        payload = env['_afisha_favorites_script']([{'id': 'a-test', 'title': '</script><img onerror=x>',
            'venue': 'Музей', 'city': 'Москва', 'end': '2026-11-30'}])
        check('untrusted exhibition titles cannot escape JSON script', payload.lower().count('</script>') == 1)
        check('styles are idempotent', patch_css(texts['docs/style.css']) == texts['docs/style.css'])
        check('JS is idempotent', patch_ui(texts['opa-ui.js']) == texts['opa-ui.js'])
    else:
        check('installer can be imported', len(FILES) == 6)
        check('mobile CSS has focus spacing', 'inset: -4px' in patch_css(''))
    node = shutil.which('node')
    if node:
        js_test = ROOT / 'test_mobile_cloud.js'
        if not js_test.exists():
            print('SKIP JS cloud scenarios: no test_mobile_cloud.js')
        else:
            p = subprocess.run([node, str(js_test)], cwd=project if (project / 'sitebuild').exists() else ROOT,
                               text=True, capture_output=True)
            if p.returncode:
                raise AssertionError('Cloud JS tests failed:\n' + p.stdout + p.stderr)
            print(p.stdout.strip())
    else:
        print('SKIP JS cloud scenarios: Node.js unavailable')
    print('ALL TESTS PASSED')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('FAIL:', e, file=sys.stderr)
        raise
