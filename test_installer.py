# -*- coding: utf-8 -*-
"""Offline installer regression tests: verify all anchors, idempotence, no partial writes."""
import ast
import importlib.util
import subprocess
from pathlib import Path
from unittest import mock

INSTALLER = Path(__file__).with_name('apply_afisha_filters.py')
spec = importlib.util.spec_from_file_location('opa_installer', INSTALLER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def old_literals(fn):
    source = ast.parse(INSTALLER.read_text(encoding='utf-8'))
    function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == fn)
    values = []
    for n in ast.walk(function):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'replace_one':
            if isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
                values.append((n.lineno, n.args[1].value))
    return [t for _, t in sorted(values)]


def check_update(fn):
    # Each production anchor must match exactly once, even when all adjacent.
    pieces = old_literals(fn)
    # A few intentionally disabled/no-op blocks have their own anchors.
    if fn == 'update_source':
        pieces = [p for p in pieces if p not in (
            '''    attrs = f' data-country="{h(item["country"])}"' ''',
            '''    if item.get("tags"):\n        attrs += f' data-tags="{h(" ".join(item["tags"]))}"' ''',
            '''        + f'<h3 class="afisha-title"><a href="{h(item["url"])}" target="_blank" rel="noopener">' '''
        )]
    joined = '\n___SEPARATOR___\n'.join(pieces)
    with mock.patch.object(mod.ast, 'parse', side_effect=lambda x: None):
        result = getattr(mod, fn)(joined)
    assert len(result) > len(joined) / 2, fn
    return len(pieces)


def check_js_fragments():
    tree = ast.parse(INSTALLER.read_text(encoding='utf-8'))
    parts = {}
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'replace_one'):
            continue
        if len(n.args) >= 4 and all(isinstance(n.args[i], ast.Constant) for i in (2, 3)):
            parts[n.args[3].value] = n.args[2].value
    standalone = ['keep old and future records in DOM',
                  'sort archive and other groups',
                  'extended UI state and favorites',
                  'new filter listeners',
                  'region counts for active period']
    for name in standalone:
        snippet = parts[name]
        code = 'function demo() {\n' + snippet + '\n}'
        p = subprocess.run(['node', '--check'], input=code, text=True, capture_output=True)
        assert p.returncode == 0, (name, p.stderr)
    snippet = parts['nine filters conditions']
    p = subprocess.run(['node', '--check'], input='function fits(li,s,skip){\n' + snippet + '\n}', text=True, capture_output=True)
    assert p.returncode == 0, p.stderr
    return len(standalone) + 1


if __name__ == '__main__':
    count = check_update('update_source')
    tests_count = check_update('update_tests')
    browser_count = check_update('update_browser_tests')
    assert mod.update_source.__name__ == 'update_source'
    assert mod.CSS_APPEND.count('{') == mod.CSS_APPEND.count('}')
    js_count = check_js_fragments()
    print(f'OK: {count} участков генератора, {tests_count} участка Python-тестов, '
          f'{browser_count} участка браузерных тестов, {js_count} JS-фрагментов; стили сбалансированы.')
