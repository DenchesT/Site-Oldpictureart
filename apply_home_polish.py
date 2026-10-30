# -*- coding: utf-8 -*-
"""Conservative, idempotent main-page UX patch for Old Picture Art.

Edits only the known generator, the existing progressive-enhancement JS,
its CSS and three harmless lint imports. No network, no git, no private files.
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import shutil
import tempfile

ROOT_MARKER = 'opa-now-collapsible'
CSS_BEGIN = '/* OPA MAIN PAGE POLISH 12 — START */'
CSS_END = '/* OPA MAIN PAGE POLISH 12 — END */'
JS_MARKER = '// OPA MAIN PAGE POLISH: visit details visibility and live chips'


def replace_once(source: str, old: str, new: str, what: str) -> str:
    n = source.count(old)
    if n != 1:
        raise RuntimeError(f'{what}: ожидалось одно совпадение, найдено {n}. Ничего не изменено.')
    return source.replace(old, new, 1)


def patch_generator(src: str) -> str:
    if ROOT_MARKER in src:
        expected = ('opa-card-title-link', 'opa-search-clear', 'opa-reset-inline',
                    'opa-sidebar-heading', "opa:filters-changed", 'Найдено ')
        missing = [marker for marker in expected if marker not in src]
        if missing:
            raise RuntimeError('Главная частично изменена; нет элементов: ' + ', '.join(missing))
        return src
    s = src
    s = replace_once(
        s,
        '    <span class="card-no">{cat_no[id(p)]:0{cat_width}d}</span>',
        '    <span class="card-no" title="Номер работы в каталоге">{cat_no[id(p)]:0{cat_width}d}</span>',
        'Каталожный номер')
    s = replace_once(
        s,
        '        <div class="card-title">{title_name}</div>',
        '        <div class="card-title"><a class="opa-card-title-link" href="{h(p[\'filename\'])}" aria-label="Открыть картину: {artist_name} — {title_name}">{title_name}</a></div>',
        'Ссылка с названия картины')
    s = replace_once(
        s,
        '    def section(icon, label, content):',
        '    now_block = now_on_block(visits if visits is not None else load_json(VISITS_FILE, []), all_posts)\n\n'
        '    def section(icon, label, content):',
        'Расчёт блока текущих посещений')
    s = replace_once(
        s,
        '{now_on_block(visits if visits is not None else load_json(VISITS_FILE, []), all_posts)}',
        "{('<details class=\"opa-now-collapsible\"><summary>Мои посещения · текущие выставки</summary>' + now_block + '</details>') if now_block else ''}",
        'Сворачиваемый блок посещений вместо длинного дублирования')
    s = replace_once(
        s,
        '  <label class="visually-hidden" for="search">Поиск по галерее</label>\n'
        '  <input type="search" class="search-box" placeholder="Поиск по художнику, картине, музею…" id="search" autocomplete="off">',
        '  <label class="opa-search-label" for="search">Поиск картин</label>\n'
        '  <div class="opa-search-wrap">\n'
        '    <input type="search" class="search-box" placeholder="Художник, название, музей…" id="search" autocomplete="off" aria-describedby="opa-search-help">\n'
        '    <button type="button" class="opa-search-clear" id="opa-clear-search" title="Очистить поиск" aria-label="Очистить поиск" hidden>×</button>\n'
        '  </div>\n'
        '  <p class="opa-search-help" id="opa-search-help">Поиск по названию, автору и музею · клавиша /</p>',
        'Поиск по картинам с очисткой')
    s = replace_once(
        s,
        '<button type="button" id="reset-filter" class="filter-reset">Сбросить все фильтры</button>\n'
        "{section('icon-archive', 'Архив', arh)}",
        '<button type="button" id="reset-filter" class="filter-reset">Сбросить все фильтры</button>\n'
        '<p class="opa-sidebar-heading">Фильтры картин</p>\n'
        "{section('icon-archive', 'Архив', arh)}",
        'Заголовок группы фильтров')
    s = replace_once(
        s,
        "{section('icon-technique', 'Техника', th)}\n{afisha_html}",
        "{section('icon-technique', 'Техника', th)}\n"
        '<p class="opa-sidebar-heading">Выставки и подборки</p>\n{afisha_html}',
        'Группа выставок и подборок')
    s = replace_once(
        s,
        '{popular_html}\n{theme_html}\n{map_link_html}',
        '{popular_html}\n<p class="opa-sidebar-heading">Разделы сайта</p>\n{map_link_html}',
        'Граница навигации')
    s = replace_once(
        s,
        '{timeline_link_html}\n</aside><main class="main-content">',
        '{timeline_link_html}\n{theme_html}\n</aside><main class="main-content">',
        'Настройка темы после разделов')
    s = replace_once(
        s,
        '  <span id="results-count" class="results-count" role="status" aria-live="polite"></span>',
        '  <div class="opa-results-meta">\n'
        '    <span id="results-count" class="results-count" role="status" aria-live="polite"></span>\n'
        '    <button type="button" id="opa-reset-inline" class="opa-reset-inline" onclick="resetAllFilters()" hidden>Сбросить фильтры</button>\n'
        '  </div>',
        'Счётчик и сброс над списком')
    s = replace_once(s, '<span class="bar-label" id="sort-label">Порядок</span>',
                     '<span class="bar-label" id="sort-label">Сортировка</span>', 'Имя сортировки')
    s = replace_once(s, '<label class="visually-hidden" for="sort">Порядок записей</label>',
                     '<label class="visually-hidden" for="sort">Сортировка картин</label>', 'Подпись сортировки')
    for old, new in (
        ('<option value="new">Сначала новые</option>', '<option value="new">Недавно добавленные</option>'),
        ('<option value="cyear">По году создания</option>', '<option value="cyear">По году картины: ранние</option>'),
        ('<option value="cyear-desc">По году создания, новые сверху</option>', '<option value="cyear-desc">По году картины: поздние</option>'),
    ):
        s = replace_once(s, old, new, 'Название сортировки')
    s = replace_once(
        s,
        "    if (searchBox) searchBox.value = '';\n    document.querySelectorAll('.filter-link.active')",
        "    if (searchBox) searchBox.value = '';\n"
        "    const searchClear = document.getElementById('opa-clear-search');\n"
        "    if (searchClear) searchClear.hidden = true;\n"
        "    document.querySelectorAll('.filter-link.active')",
        'Очистка поиска при сбросе')
    s = replace_once(
        s,
        "    if (counter) counter.textContent = hasActive ? (visible + ' ' + plural(visible, 'картина', 'картины', 'картин')) : '';",
        "    if (counter) counter.textContent = 'Найдено ' + visible + ' ' + plural(visible, 'картина', 'картины', 'картин');\n"
        "    const resetInline = document.getElementById('opa-reset-inline');\n"
        "    if (resetInline) resetInline.hidden = !hasActive;",
        'Счётчик найденных картин')
    s = replace_once(
        s,
        "    if (empty) empty.hidden = visible !== 0;\n}}\n\nfunction plural(",
        "    if (empty) empty.hidden = visible !== 0;\n"
        "    document.dispatchEvent(new CustomEvent('opa:filters-changed'));\n"
        "}}\n\nfunction plural(",
        'Обновление фильтров и их ярлыков')
    s = replace_once(
        s,
        "    const searchBox = document.getElementById('search');\n    if (searchBox) {{\n        let t = null;",
        "    const searchBox = document.getElementById('search');\n"
        "    const clearSearch = document.getElementById('opa-clear-search');\n"
        "    if (searchBox) {{\n"
        "        if (clearSearch) {{\n"
        "            clearSearch.hidden = !searchBox.value.trim();\n"
        "            clearSearch.addEventListener('click', function () {{\n"
        "                searchBox.value = '';\n"
        "                searchBox.dispatchEvent(new Event('input', {{bubbles: true}}));\n"
        "                searchBox.focus();\n"
        "            }});\n"
        "        }}\n"
        "        let t = null;",
        'Кнопка очистки строки поиска')
    s = replace_once(
        s,
        '            const v = e.target.value.toLowerCase().trim();\n            clearTimeout(t);',
        "            const v = e.target.value.toLowerCase().trim();\n"
        "            if (clearSearch) clearSearch.hidden = !e.target.value.trim();\n"
        '            clearTimeout(t);',
        'Состояние кнопки очистки поиска')
    ast.parse(s, filename='sitebuild/posts.py')
    return s


def patch_ui_js(s: str) -> str:
    if JS_MARKER in s:
        if "document.addEventListener('opa:filters-changed', update);" not in s or 'nowWrap.hidden = nowBox.hidden' not in s:
            raise RuntimeError('opa-ui.js содержит неполное обновление')
        return s
    old = "      sidebar.addEventListener('click',function(){setTimeout(update,0);});"
    new = (f'      {JS_MARKER}\n'
           "      document.addEventListener('opa:filters-changed', update);\n"
           "      sidebar.addEventListener('click',function(){setTimeout(update,0);});")
    s = replace_once(s, old, new, 'Обновление ярлыков активных фильтров')
    s = replace_once(
        s,
        "    // Clearer action names for assistive technology, without changing toolbar structure.",
        "    // The full visits list remains in the DOM for dates/accessibility; avoid an empty teaser.\n"
        "    var nowBox = document.getElementById('now-on');\n"
        "    var nowWrap = document.querySelector('.opa-now-collapsible');\n"
        "    if (nowWrap && nowBox) nowWrap.hidden = nowBox.hidden;\n"
        "    // Clearer action names for assistive technology, without changing toolbar structure.",
        'Прячем пустой блок посещений')
    return s


CSS = r'''/* OPA MAIN PAGE POLISH 12 — START */
/* All overrides stay within the existing palette and only affect the homepage. */
.index-page header { padding: 1.1rem 0 .85rem; margin-bottom: .85rem; gap: .85rem; }
.index-page h1 { font-size: clamp(2.1rem, 3.25vw, 2.55rem); }
.index-page .site-lede { margin-top: .45rem; line-height: 1.4; max-width: 77ch; }
.index-page .subtitle { margin-top: .35rem; }
.index-page .random-btn { padding: .5rem .9rem; }
/* Visits are available on demand; the detailed exhibition list remains in the sidebar. */
.opa-now-collapsible { margin: 0 0 .85rem; border: 1px solid var(--border); background: var(--card-bg); }
.opa-now-collapsible[hidden] { display: none !important; }
.opa-now-collapsible > summary { list-style-position: inside; padding: .45rem .8rem; cursor: pointer; color: var(--link); font: var(--fs-xs) var(--ff-data); letter-spacing: .04em; }
.opa-now-collapsible > summary:hover, .opa-now-collapsible > summary:focus-visible { background: var(--panel); }
.opa-now-collapsible > .now-on { margin: 0; border: 0; border-top: 1px solid var(--rule-soft); }
/* One document scrollbar on desktop; the search field stays available in the sidebar. */
@media (min-width: 901px) {
  .index-page .sidebar { position: static; max-height: none; height: auto; overflow: visible; }
  .index-page .sidebar-search { position: sticky; top: 0; z-index: 12; background: var(--sidebar-bg); padding-top: .5rem; }
}
.opa-sidebar-heading { margin: .8rem 0 .3rem; padding: .35rem 0 .25rem; border-bottom: 1px solid var(--border); color: var(--text-2); font: 600 var(--fs-xs) var(--ff-data); letter-spacing: .06em; text-transform: uppercase; }
.index-page .sidebar .opa-search-label { display: block; margin-bottom: .3rem; color: var(--text-2); font: var(--fs-xs) var(--ff-data); }
.opa-search-wrap { position: relative; }
.index-page .search-box { width: 100%; padding-right: 2.2rem; background: var(--card-bg); border-color: var(--input-border); }
.opa-search-clear { position: absolute; right: 2px; top: 2px; bottom: 2px; min-width: 2rem; border: 0; background: transparent; color: var(--text-2); font-size: 1.3rem; line-height: 1; cursor: pointer; }
.opa-search-clear:hover { background: var(--panel); }
.opa-search-clear[hidden] { display: none !important; }
.index-page .search-box::-webkit-search-cancel-button { display: none; }
.opa-search-help { color: var(--muted); font: .67rem var(--ff-data); line-height: 1.45; margin: .3rem 0 0; }
/* Persistent count, reset action, and a compact floating sort/view toolbar. */
.index-page .results-bar { position: sticky; top: 0; z-index: 40; background: var(--bg); padding: .7rem .25rem; border-bottom: 1px solid var(--border); min-height: 3.3rem; margin-bottom: .65rem; box-shadow: 0 3px 9px -9px var(--shadow-strong); }
.opa-results-meta { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
.index-page .results-count { color: var(--text-2); font-weight: 500; }
.opa-reset-inline { border: 0; background: transparent; color: var(--link); font: var(--fs-xs) var(--ff-data); padding: .15rem; text-decoration: underline; text-underline-offset: 2px; cursor: pointer; }
.opa-reset-inline[hidden] { display: none !important; }
.index-page #cards { scroll-margin-top: 4.8rem; }
/* Original paintings are shown at natural aspect ratios, only a little larger. */
@media (min-width: 1001px) {
  .index-page .grid.list .card { grid-template-columns: 3.4rem 156px minmax(0, 1fr) minmax(0, 15rem); gap: 1.1rem; }
  .index-page .grid.list .card-img img { max-height: 158px; }
}
.index-page .card-img { position: relative; z-index: 1; }
.index-page .grid.list .card-img { border-radius: 2px; }
.index-page .card-img img { transition: box-shadow .15s, border-color .15s; }
.index-page .card-img:hover img, .index-page .card-img:focus-visible img { border-color: var(--active); box-shadow: 0 4px 15px -5px var(--shadow-strong); }
.index-page .card:focus-within { outline: 1px solid var(--active); outline-offset: -1px; }
.index-page .opa-card-title-link { position: relative; z-index: 1; text-decoration: none; color: inherit; }
.index-page .opa-card-title-link:hover, .index-page .opa-card-title-link:focus-visible { text-decoration: underline; text-underline-offset: 3px; color: var(--link); }
.index-page .grid.list .card-facts { font-size: .75rem; color: var(--text-2); }
.index-page .grid.list .card-facts div { padding: 3px 0; }
.index-page .grid.list .card-facts b { font-weight: 600; }
.index-page .grid.list .card-no::before { content: '№ '; }
@media (min-width: 621px) and (max-width: 1000px) {
  .index-page .grid.list .card { grid-template-columns: 3rem 120px minmax(0,1fr); }
  .index-page .grid.list .card-img img { max-height: 125px; }
}
@media (max-width: 900px) {
  .index-page .sidebar { position: fixed; max-height: none; overflow-y: auto; }
  .index-page .sidebar-search { position: static; }
  .index-page .results-bar { top: 3rem; }
}
@media (max-width: 620px) {
  .index-page .results-bar { align-items: flex-start; gap: .4rem; }
  .index-page .results-bar .bar-controls { gap: .45rem; }
  .index-page #cards { scroll-margin-top: 7rem; }
  .index-page .grid.list .card { grid-template-columns: 2.4rem 92px minmax(0,1fr); }
  .index-page .grid.list .card-img img { max-height: 100px; }
}
@media (max-width: 380px) {
  .index-page .grid.list .card { grid-template-columns: 2rem 70px minmax(0,1fr); }
  .index-page .grid.list .card-img img { max-height: 88px; }
}
/* OPA MAIN PAGE POLISH 12 — END */
'''


def patch_css(src: str) -> str:
    if CSS_BEGIN in src and CSS_END in src:
        return src
    if CSS_BEGIN in src or CSS_END in src:
        raise RuntimeError('Маркеры CSS повреждены; отказываюсь от частичного изменения')
    if '.grid.list .card' not in src or '.results-bar' not in src or '.sidebar' not in src:
        raise RuntimeError('CSS изменился слишком сильно; нужно проверить версию')
    return src.rstrip() + '\n\n' + CSS


def patch_lint(src: str, path: str) -> str:
    replacements = {
        'apply_ui_12.py': ('import shutil,sys,ast', 'import shutil,sys'),
        'test_installer.py': ('import tempfile\n', ''),
        'sitebuild/visits.py': ('        from functools import lru_cache\n', ''),
    }
    old, new = replacements[path]
    if old not in src:
        return src
    if src.count(old) != 1:
        raise RuntimeError(f'{path}: найдено несколько вхождений неиспользуемого импорта')
    result = src.replace(old, new, 1)
    ast.parse(result, filename=path)
    return result


def prepare(root: Path) -> dict[Path, str]:
    files = {
        'sitebuild/posts.py': patch_generator,
        'docs/style.css': patch_css,
        'opa-ui.js': patch_ui_js,
    }
    for name in ('apply_ui_12.py', 'test_installer.py', 'sitebuild/visits.py'):
        files[name] = lambda text, n=name: patch_lint(text, n)
    planned = {}
    for name, transform in files.items():
        path = root / name
        if not path.is_file():
            raise RuntimeError(f'Нет файла {name}; требуются исходники Old Picture Art')
        old = path.read_text(encoding='utf-8')
        new = transform(old)
        if old != new:
            planned[path] = new
    return planned


def apply(planned: dict[Path, str]) -> None:
    # All edits have already been checked before the first file is touched.
    # On an I/O error restore the source files from the in-memory snapshot.
    originals = {path: path.read_bytes() for path in planned}
    installed = []
    try:
        for path, content in planned.items():
            backup = path.with_name(path.name + '.before-home-polish.bak')
            if not backup.exists():
                shutil.copy2(path, backup)
            fd, tmp = tempfile.mkstemp(prefix='.opa-home-', dir=path.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
                    out.write(content)
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            installed.append(path)
    except Exception:
        for path in installed:
            path.write_bytes(originals[path])
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description='12 доработок главной страницы Old Picture Art')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='Только проверить, не записывать файлы')
    group.add_argument('--apply', action='store_true', help='Внести изменения с резервными копиями')
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='Корень проекта')
    args = parser.parse_args()
    root = args.root.resolve()
    planned = prepare(root)
    if not planned:
        print('Уже установлено: новых изменений не требуется.')
        return 0
    print(f'Найдено файлов для обновления: {len(planned)}')
    for path in planned:
        print(' -', path.relative_to(root))
    if args.check:
        print('Проверка пройдена; файлы не изменены.')
    else:
        apply(planned)
        print('Изменения применены. Оригиналы сохранены как *.before-home-polish.bak')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
