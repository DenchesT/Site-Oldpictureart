# -*- coding: utf-8 -*-
"""Smoke/regression checks for Old Picture Art afisha redesign.
Run after `python apply_afisha_ui.py --apply` and offline rebuild.
"""
import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# ZIP is unpacked into the site root, so ROOT is the current project.
checks = []


def check(name, success):
    checks.append((name, bool(success)))
    print(('OK  ' if success else 'FAIL ') + name)


for name in ('sitebuild/afisha.py', 'sitebuild/posts.py'):
    file = ROOT / name
    check(name + ': синтаксис Python', file.exists() and bool(ast.parse(file.read_text(encoding='utf-8'))))

af = (ROOT / 'sitebuild/afisha.py').read_text(encoding='utf-8')
posts = (ROOT / 'sitebuild/posts.py').read_text(encoding='utf-8')
css = (ROOT / 'docs/style.css').read_text(encoding='utf-8')
js = (ROOT / 'opa-ui.js').read_text(encoding='utf-8')
check('переключатели статусов и избранного', 'data-status="favorites"' in af and 'data-status="archive"' in af)
check('один видимый поиск', 'opa-afisha-unified-search' in af and '<input id="afisha-artist" type="hidden"' in af)
check('контекстные даты и архив', 'afisha-closing-box' in af and 'afisha-opening-box' in af and 'afisha-archive-year-box' in af)
check('группировка дополнительных фильтров', '<details class="opa-afisha-more"' in af)
check('избранное сохраняется в существующем механизме', 'setAfishaFavorite(' in af and "s.status === 'favorites'" in af)
check('короткий блок завершения', 'id="afisha-week-more"' in af and "r.hidden = index >= 3" in af)
check('количество результатов и сброс', 'afisha-results-count' in af and 'afisha-active-filters' in af and 'afisha-reset-inline' in af)
check('сортировка вынесена к результатам', 'opa-afisha-results-bar' in af and 'id="afisha-sort"' in af)
check('на главной вместо анонсов пункт «Выставки»', 'href="afisha.html">Выставки</a>' in posts and '{afisha_html}\n{map_link_html}' in posts and "{('<details class=\"opa-now-collapsible\"" not in posts)
check('на телефоне сортировка снова над картинами', 'position: static; top: auto; z-index: auto; display: flex' in css and 'mobileControls.appendChild(toolbar)' not in js)
check('исходные цвета и типографика не переопределены', 'var(--ff-data)' in css and 'var(--border)' in css)
if (ROOT / 'docs/afisha.html').exists():
    page = (ROOT / 'docs/afisha.html').read_text(encoding='utf-8')
    check('собранная афиша содержит новые элементы', all(f'id="{ident}"' in page for ident in ('afisha-fav-total', 'afisha-results-count', 'afisha-query', 'afisha-sort', 'afisha-week-more')))
if (ROOT / 'docs/index.html').exists():
    page = (ROOT / 'docs/index.html').read_text(encoding='utf-8')
    check('на собранной главной только ссылка на выставки', 'href="afisha.html">Выставки</a>' in page and 'id="afisha-block"' not in page)
try:
    import shutil
    if shutil.which('node'):
        import apply_afisha_ui as patch
        code = patch.extract_js(af)
        proc = subprocess.run(['node', '--check'], input=code, capture_output=True, text=True)
        check('весь JavaScript афиши: синтаксис', proc.returncode == 0)
except Exception as exc:
    check('весь JavaScript афиши: синтаксис', False)
    print(str(exc))
print(f'\nПроверок: {len(checks)}; ошибок: {sum(not ok for _, ok in checks)}')
raise SystemExit(1 if any(not ok for _, ok in checks) else 0)
