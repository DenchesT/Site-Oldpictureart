# -*- coding: utf-8 -*-
"""Old Picture Art: afisha redesign without changing palette; clean home navigation.

Designed for the Oct 31, 2026 GitHub generator and the preceding mobile-favorites
update. No git/push, no data changes. Every replacement is validated in memory
before writing. Existing changes are backed up before applying.
"""
from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MARKER = 'OPA AFISHA UI 2026-10-31'
FILES = ('sitebuild/afisha.py', 'sitebuild/posts.py', 'docs/style.css', 'opa-ui.js', 'tests/test_afisha.py', 'tests/test_afisha.js')


def once(source: str, old: str, new: str, label: str) -> str:
    n = source.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: ожидалось одно совпадение, найдено {n}. Ничего не записано.')
    return source.replace(old, new, 1)


def patch_afisha(source: str) -> str:
    if MARKER in source:
        return source
    source = once(source, '<h1>Выставки сейчас</h1>', '<h1>Выставки</h1>', 'Заголовок афиши')
    source = once(source,
        'Крупные выставки искусства до 1940 года — от старых мастеров до модерна и авангарда — в музеях России и мира: что идёт сегодня, скоро откроется и уже завершилось. Прошедшие выставки доступны в архиве.',
        'Актуальные и предстоящие выставки в музеях России и мира. Завершившиеся события сохраняются в архиве.',
        'Описание афиши')
    start = source.index('  <div class="visit-bar afisha-bar">', source.index('def render_afisha_page('))
    end = source.index('  <p class="afisha-near-note"', start)
    old = source[start:end]
    panel = '''  <div class="afisha-top-line">
    <div class="view-switch afisha-switch" role="group" aria-label="География выставок">
      <button type="button" data-region="russia" aria-pressed="true">Россия <span class="visit-count">{n_ru}</span></button>
      <button type="button" data-region="world" aria-pressed="false">Мир <span class="visit-count">{n_world}</span></button>
    </div>
  </div>
  <div class="view-switch afisha-status-switch" role="group" aria-label="Статус выставок">
    <button type="button" data-status="current" aria-pressed="true">Сейчас и скоро</button>
    <button type="button" data-status="running" aria-pressed="false">Идут</button>
    <button type="button" data-status="soon" aria-pressed="false">Скоро</button>
    <button type="button" data-status="archive" aria-pressed="false">Архив</button>
    <button type="button" data-status="favorites" aria-pressed="false">★ Избранное <span id="afisha-fav-total"></span></button>
    <button type="button" data-status="all" aria-pressed="false">Все периоды</button>
  </div>
  <div class="afisha-filter-panel">
    <label class="afisha-select afisha-search-label opa-afisha-unified-search">
      <span>Поиск выставок</span>
      <input id="afisha-query" type="search" placeholder="Выставка, художник, музей, город…" autocomplete="off">
    </label>
    <button type="button" id="afisha-mobile-filter-toggle" class="opa-afisha-mobile-toggle" aria-expanded="false" aria-controls="afisha-primary-filters afisha-filter-actions">Фильтры</button>
    <div class="afisha-primary-filters" id="afisha-primary-filters">
      <label class="afisha-select" id="afisha-area-box"><span>Город</span><select id="afisha-area">{area_select}</select></label>
      <label class="afisha-select" id="afisha-country-box" hidden><span>Страна</span><select id="afisha-country">{country_select}</select></label>
      <label class="afisha-select"><span>Музей</span><select id="afisha-venue">{venue_select}</select></label>
      <label class="afisha-select"><span>Эпоха</span><select id="afisha-epoch">{epoch_select}</select></label>
    </div>
    <div class="afisha-filter-actions" id="afisha-filter-actions">
      <details class="opa-afisha-more" id="afisha-more-filters">
        <summary>Дополнительные фильтры</summary>
        <div class="afisha-secondary-filters">
          <label class="afisha-select" id="afisha-closing-box"><span>Когда закрывается</span><select id="afisha-closing"><option value="all">Любая дата</option><option value="7">В ближайшие 7 дней</option><option value="30">В ближайшие 30 дней</option><option value="90">В ближайшие 90 дней</option></select></label>
          <label class="afisha-select" id="afisha-opening-box"><span>Когда открывается</span><select id="afisha-opening"><option value="all">Любая дата</option><option value="7">В ближайшие 7 дней</option><option value="30">В ближайшие 30 дней</option><option value="90">В ближайшие 90 дней</option></select></label>
          <label class="afisha-select" id="afisha-archive-year-box" hidden><span>Год архива</span><select id="afisha-archive-year">{archive_year_select}</select></label>
          {near_btn}
        </div>
      </details>
      <button type="button" class="afisha-reset" id="afisha-reset">Очистить фильтры</button>
    </div>
    <!-- Legacy controls remain hidden to preserve saved-filter compatibility. -->
    <input id="afisha-artist" type="hidden" value="">
    <input id="afisha-only-favorites" type="checkbox" hidden>
  </div>
'''
    source = once(source, old, panel, 'Сетка фильтров и переключатели статусов')
    source = once(source, '<main id="afisha" class="afisha">', '''<main id="afisha" class="afisha">
<div class="opa-afisha-results-bar">
  <div class="opa-afisha-results-summary">
    <span id="afisha-results-count" class="results-count" role="status" aria-live="polite"></span>
    <div id="afisha-active-filters" class="active-filter-chips" aria-label="Активные условия"></div>
    <button type="button" id="afisha-reset-inline" class="opa-reset-inline" hidden>Сбросить фильтры</button>
  </div>
  <label class="afisha-select opa-afisha-sort"><span>Сортировка</span><select id="afisha-sort"><option value="default">По дате события</option><option value="start">По открытию</option><option value="end">По закрытию</option><option value="title">По названию</option><option value="venue">По музею</option></select></label>
</div>''', 'Счётчик и сортировка над выставками')
    source = once(source, '<ul class="afisha-week-list" id="afisha-week-list"></ul>', '''<ul class="afisha-week-list" id="afisha-week-list"></ul>
<button type="button" id="afisha-week-more" class="opa-afisha-week-more" hidden>Показать остальные</button>''', 'Раскрытие срочных выставок')
    # The JS below is a normal string constant, not an f-string.
    source = once(source,
        "    if (s.status !== 'all' && s.status !== 'current' && phase !== s.status) return false;",
        "    if (s.status !== 'all' && s.status !== 'current' && s.status !== 'favorites' && phase !== s.status) return false;\n    if (s.status === 'favorites' && !favorites[favoriteId(li)]) return false;",
        'Отбор по избранным выставкам')
    source = once(source,
        "    rows.forEach(function (li) {\n      var a = li.querySelector('.afisha-title a'), r = document.createElement('li');",
        "    rows.forEach(function (li, index) {\n      var a = li.querySelector('.afisha-title a'), r = document.createElement('li');\n      r.hidden = index >= 3;",
        'Три ближайшие к закрытию')
    source = once(source,
        "    week.hidden = !rows.length;\n  }\n  function show() {",
        '''    week.hidden = !rows.length;
    var more = document.getElementById('afisha-week-more');
    if (more) {
      more.hidden = rows.length <= 3;
      more.textContent = 'Показать остальные (' + (rows.length - 3) + ')';
    }
  }
  var weekMore = document.getElementById('afisha-week-more');
  if (weekMore) weekMore.addEventListener('click', function () {
    Array.prototype.forEach.call(weekList.children, function (li) { li.hidden = false; });
    weekMore.hidden = true;
  });
  function show() {''', 'Кнопка раскрытия срочных выставок')
    source = once(source,
        "    document.getElementById('afisha-archive-year-box').hidden = state.status !== 'archive';",
        '''    document.getElementById('afisha-archive-year-box').hidden = state.status !== 'archive';
    document.getElementById('afisha-closing-box').hidden = (state.status === 'soon' || state.status === 'archive' || state.status === 'favorites');
    document.getElementById('afisha-opening-box').hidden = (state.status === 'running' || state.status === 'archive' || state.status === 'favorites');''',
        'Контекстные фильтры по статусу')
    source = once(source,
        "    closing.value = state.closing; opening.value = state.opening; sorter.value = state.sort;\n    q.value = state.query; artist.value = state.artist; favoritesOnly.checked = state.favoritesOnly;\n    recount();",
        '''    closing.value = state.closing; opening.value = state.opening; sorter.value = state.sort;
    q.value = state.query; artist.value = state.artist; favoritesOnly.checked = state.favoritesOnly;
    updateAfishaSummary(shown);
    recount();''', 'Счётчик и активные условия')
    source = once(source,
        "  function show() {\n    var shown = {running: 0, soon: 0, archive: 0};",
        '''  // Count, active filters and quick removal above the exhibition list.
  function updateAfishaSummary(shown) {
    var n = shown.running + shown.soon + shown.archive;
    var suffix = n % 100 >= 11 && n % 100 <= 14 ? 'выставок' : n % 10 === 1 ? 'выставка' : n % 10 >= 2 && n % 10 <= 4 ? 'выставки' : 'выставок';
    document.getElementById('afisha-results-count').textContent = 'Найдено ' + n + ' ' + suffix;
    var favTotal = document.getElementById('afisha-fav-total');
    if (favTotal) {
      var count = items.filter(function (li) { return favorites[favoriteId(li)]; }).length;
      favTotal.textContent = count ? '(' + count + ')' : '';
    }
    var chips = document.getElementById('afisha-active-filters');
    chips.replaceChildren();
    function chip(text, clear) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'opa-chip'; b.textContent = text + ' ×';
      b.title = 'Снять условие ' + text;
      b.addEventListener('click', clear); chips.appendChild(b);
    }
    if (state.reg === 'world') chip('Мир', function () { state.reg = 'russia'; show(); });
    var statusLabels = {running:'Идут', soon:'Скоро', archive:'Архив', favorites:'Избранное', all:'Все периоды'};
    if (statusLabels[state.status]) chip(statusLabels[state.status], function () { state.status = 'current'; state.favoritesOnly = false; state.archiveYear = 'all'; show(); });
    ['area','country','epoch','venue','archiveYear'].forEach(function (k) {
      if (state[k] === 'all' || !sel[k]) return;
      var option = Array.prototype.find.call(sel[k].options, function (o) { return o.value === state[k]; });
      var label = option ? option.getAttribute('data-label') || option.textContent : state[k];
      chip(label, function () { state[k] = 'all'; show(); });
    });
    if (state.closing !== 'all') chip('Закрытие: ' + state.closing + ' дн.', function () { state.closing = 'all'; show(); });
    if (state.opening !== 'all') chip('Открытие: ' + state.opening + ' дн.', function () { state.opening = 'all'; show(); });
    if (state.query) chip('Поиск: ' + state.query.slice(0, 30), function () { state.query = ''; show(); });
    var reset = document.getElementById('afisha-reset-inline');
    reset.hidden = chips.childElementCount === 0;
    var filterToggle = document.getElementById('afisha-mobile-filter-toggle');
    if (filterToggle) filterToggle.textContent = 'Фильтры' + (chips.childElementCount ? ' (' + chips.childElementCount + ')' : '');
  }
  document.getElementById('afisha-reset-inline').addEventListener('click', function () {
    document.getElementById('afisha-reset').click();
  });
  var mobileFilterToggle = document.getElementById('afisha-mobile-filter-toggle');
  if (mobileFilterToggle) mobileFilterToggle.addEventListener('click', function () {
    var panel = document.querySelector('.afisha-filter-panel');
    var expanded = panel.classList.toggle('expanded');
    this.setAttribute('aria-expanded', String(expanded));
  });
  function show() {
    var shown = {running: 0, soon: 0, archive: 0};''',
        'Снятие отдельных фильтров')
    source = once(source,
        "      state.status = b.getAttribute('data-status');\n      if (state.status !== 'archive') state.archiveYear = 'all';",
        "      state.status = b.getAttribute('data-status');\n      state.favoritesOnly = false;\n      if (state.status === 'favorites') { state.closing = state.opening = 'all'; state.archiveYear = 'all'; }\n      if (state.status !== 'archive') state.archiveYear = 'all';",
        'Переключатель избранного')
    source = once(source,
        "    state.favoritesOnly = true;\n    state.status = 'all';",
        "    state.favoritesOnly = false;\n    state.status = 'favorites';",
        'Ссылка на избранные из главного меню')
    source = once(source,
        "['current','all','running','soon','archive'].indexOf(state.status)",
        "['current','all','running','soon','archive','favorites'].indexOf(state.status)",
        'Сохранённый статус «Избранное»')
    source = once(source,
        '    # The main page now includes ended events (archive) and distant future',
        '    # ' + MARKER + '\n    # The main page now includes ended events (archive) and distant future',
        'Маркер версии UI')
    return source


def patch_posts(source: str) -> str:
    if MARKER in source:
        return source
    if '    afisha_html = afisha_block(afisha_items)' in source:
        source = once(source, '    afisha_html = afisha_block(afisha_items)',
            '''    afisha_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-afisha no-arrow" '
                   'href="afisha.html">Выставки</a></div>')''', 'Ссылка вместо анонсов афиши')
    elif '    afisha_html = afisha_block(load_afisha()[0])' in source:
        source = once(source, '    afisha_html = afisha_block(load_afisha()[0])',
            '''    afisha_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-afisha no-arrow" '
                   'href="afisha.html">Выставки</a></div>')''', 'Ссылка вместо анонсов афиши')
    else:
        raise RuntimeError('Боковая афиша: текущий код отличается от ожидаемого')
    source = once(source, '{afisha_html}\n{fav_html}', '{fav_html}', 'Выставки отдельно от избранного')
    source = once(source, '<p class="opa-sidebar-heading">Выставки и подборки</p>',
                  '<p class="opa-sidebar-heading">Подборки</p>', 'Заголовок подборок')
    source = once(source, '{map_link_html}\n{visits_link_html}',
                  '{afisha_html}\n{map_link_html}\n{visits_link_html}', 'Вкладка выставок в разделах сайта')
    source = once(source,
        '{(\'<details class="opa-now-collapsible"><summary>Мои посещения · текущие выставки</summary>\' + now_block + \'</details>\') if now_block else \'\'}',
        '', 'Убираем дублирующий блок над главной галереей')
    # afisha_block is no longer used. Retain AFISHA_JS for other pages and
    # _afisha_favorites_script for the cloud favorites bridge when present.
    source = once(source, 'AFISHA_JS, afisha_block, load_afisha', 'AFISHA_JS, load_afisha',
                  'Неиспользуемый импорт блока анонсов')
    source = once(source, '    # Афиша — крупные выставки в России и в мире (sitebuild/afisha.py):',
        '    # ' + MARKER + '\n    # В меню одна ссылка на афишу, без анонсов в боковой колонке.\n    # Афиша — крупные выставки в России и в мире (sitebuild/afisha.py):',
        'Маркер версии меню')
    return source


def patch_ui(source: str) -> str:
    if MARKER in source:
        return source
    # Undo previous script that relocated sorting to the off-canvas menu.
    begin = '    // OPA MOBILE & EXHIBITION FAVORITES 2026-10-31\n    // Keep only the Menu control over artwork on phones.'
    end = '    // Clearer action names for assistive technology, without changing toolbar structure.'
    if begin in source:
        first = source.index(begin)
        last = source.index(end, first)
        source = source[:first] + '    // ' + MARKER + ': sorting stays above artwork on phones.\n' + source[last:]
    else:
        source = once(source, end,
            '    // ' + MARKER + ': sorting stays above artwork on phones.\n' + end,
            'Возврат мобильной сортировки')
    return source



def patch_py_tests(source: str) -> str:
    if 'OPA AFISHA UI TESTS 2026-10-31' in source:
        return source
    old = '''    ok("на главной афиша — в левой панели, под фильтрами",
       idx.find('id="sidebar"') < idx.find('id="afisha-block"') < idx.find('</aside>')
       and idx.find("'Техника'") < 0 and idx.find('icon-technique') < idx.find('id="afisha-block"'))
    ok("…и над галереей её больше нет", idx.find('id="afisha-block"') > idx.find('<div class="layout">'))'''
    new = '''    # OPA AFISHA UI TESTS 2026-10-31
    ok("на главной в разделе сайта — одна ссылка «Выставки»",
       idx.find('id="sidebar"') < idx.find('href="afisha.html">Выставки</a>') < idx.find('</aside>')
       and 'id="afisha-block"' not in idx)
    ok("на главной нет повторных анонсов над картинами",
       'opa-now-collapsible' not in idx)'''
    return once(source, old, new, 'Регрессии ссылки на афишу в Python-тестах')


def patch_js_tests(source: str) -> str:
    if 'OPA AFISHA UI TESTS 2026-10-31' in source:
        return source
    start = source.index('  const blk = await page.evaluate(() => {')
    end = source.index("  ok('главная без ошибок скрипта'", start)
    new = '''  // OPA AFISHA UI TESTS 2026-10-31
  const nav = await page.evaluate(() => ({
    link: !!document.querySelector('#sidebar a[href="afisha.html"]'),
    oldPreview: !!document.getElementById('afisha-block'),
    upperPreview: !!document.querySelector('.opa-now-collapsible')
  }));
  ok('на главной только ссылка «Выставки»', nav.link && !nav.oldPreview && !nav.upperPreview, JSON.stringify(nav));
'''
    source = once(source, source[start:end], new, 'Браузерные проверки бокового меню')
    source = once(source, '''  ok('всё закончилось — списка нет, ссылка на афишу осталась',
     await page.$eval('#afisha-block', b => b.querySelector('.afisha-side').hidden && !!b.querySelector('a[href="afisha.html"]')).catch(() => false));''',
    '''  ok('ссылка «Выставки» не зависит от сроков завершения',
     await page.$eval('#sidebar a[href="afisha.html"]', a => a.textContent.trim() === 'Выставки').catch(() => false));''',
    'Браузерный тест постоянной ссылки')
    source = once(source, "await page.check('#afisha-only-favorites');",
        "await page.click('.afisha-status-switch [data-status=\"favorites\"]');",
        'Проверка избранного через вкладку')
    source = once(source, "await page.uncheck('#afisha-only-favorites');",
        "await page.click('.afisha-status-switch [data-status=\"current\"]');",
        'Выход из вкладки избранного')
    # Filter controls are intentionally collapsed until requested, unlike the old flat grid.
    for expr in ("selectOption('#afisha-archive-year'", "selectOption('#afisha-closing'",
                 "selectOption('#afisha-opening'", "click('#afisha-near-btn'"):
        source = source.replace('await page.' + expr,
            "await page.locator('#afisha-more-filters').evaluate(d => d.open = true);\n    await page.".replace('\\n', '\n') + expr)
    return source


CSS = '''

/* OPA AFISHA UI 2026-10-31: preserve existing Old Picture Art colors and fonts. */
.afisha-page .artist-head { padding-bottom: var(--s3); margin-bottom: var(--s4); }
.afisha-page .afisha-lede { max-width: 75ch; line-height: 1.45; margin-bottom: var(--s3); }
.afisha-top-line { display: flex; align-items: center; gap: var(--s3); margin-bottom: var(--s3); }
.afisha-page .afisha-status-switch { display: flex; width: fit-content; max-width: 100%; margin-bottom: var(--s4); flex-wrap: wrap; }
.afisha-page .afisha-status-switch button { white-space: nowrap; }
.afisha-filter-panel { border: 1px solid var(--border); background: var(--card-bg); padding: var(--s4); display: grid; gap: var(--s3); margin-bottom: var(--s3); }
.opa-afisha-unified-search { display: flex; max-width: none; }
.opa-afisha-unified-search input { width: 100%; max-width: none; min-height: 42px; font-family: var(--ff-data); font-size: var(--fs-sm); }
.afisha-primary-filters, .afisha-secondary-filters { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--s3); align-items: end; }
.afisha-primary-filters .afisha-select, .afisha-secondary-filters .afisha-select { min-width: 0; width: 100%; }
.afisha-primary-filters select, .afisha-secondary-filters select { width: 100%; min-width: 0; max-width: 100%; min-height: 39px; }
.afisha-filter-actions { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--s4); flex-wrap: wrap; }
.opa-afisha-more { min-width: min(100%, 20rem); flex: 1 1 20rem; }
.opa-afisha-more > summary { cursor: pointer; list-style-position: inside; color: var(--link); font: var(--fs-xs) var(--ff-data); padding: .55rem 0; }
.opa-afisha-more > summary:hover { text-decoration: underline; }
.opa-afisha-more .afisha-secondary-filters { padding: var(--s3) 0; }
.afisha-filter-panel .afisha-reset { align-self: start; margin-top: .25rem; }
.opa-afisha-mobile-toggle { display: none; }
.opa-afisha-results-bar { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--s4); flex-wrap: wrap; padding: var(--s2) 0 var(--s4); margin-bottom: var(--s4); border-bottom: 1px solid var(--border); }
.opa-afisha-results-summary { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--s2); flex: 1 1 20rem; }
.opa-afisha-results-summary .active-filter-chips { margin: 0; }
.opa-afisha-sort { flex: 0 1 14rem; }
.opa-afisha-sort select { width: 100%; min-width: 0; }
.opa-afisha-results-summary .opa-reset-inline { display: inline-block; }
.opa-afisha-results-summary .opa-reset-inline[hidden] { display: none; }
.opa-afisha-week-more { margin-top: .5rem; background: none; border: 0; padding: .3rem 0; font: var(--fs-xs) var(--ff-data); color: var(--link); cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.opa-afisha-week-more[hidden] { display: none; }
@media (max-width: 900px) {
  .index-page .results-bar { position: static; top: auto; z-index: auto; display: flex; background: var(--bg); box-shadow: none; }
  .index-page .bar-controls { display: flex; }
  .index-page .opa-mobile-controls { display: none; }
  .index-page #cards { scroll-margin-top: 3.5rem; }
}
@media (max-width: 700px) {
  .afisha-primary-filters, .afisha-secondary-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .afisha-filter-panel { padding: var(--s3); }
  .opa-afisha-mobile-toggle { display: block; width: 100%; padding: var(--s2) var(--s3); border: 1px solid var(--border); background: var(--card-bg); color: var(--link); font: var(--fs-xs) var(--ff-data); text-align: center; cursor: pointer; min-height: 42px; }
  .afisha-filter-panel:not(.expanded) .afisha-primary-filters, .afisha-filter-panel:not(.expanded) .afisha-filter-actions { display: none; }
  .afisha-page .afisha-status-switch { width: 100%; }
  .afisha-page .afisha-status-switch button { flex: 1 1 auto; }
  .opa-afisha-sort { flex: 1 1 100%; }
  .opa-afisha-results-summary { flex-basis: 100%; }
}
@media (max-width: 420px) {
  .afisha-primary-filters, .afisha-secondary-filters { grid-template-columns: 1fr; }
}
'''


def patch_css(source: str) -> str:
    return source if MARKER in source else source.rstrip() + '\n\n' + CSS


PATCHES = {
    'sitebuild/afisha.py': patch_afisha,
    'sitebuild/posts.py': patch_posts,
    'docs/style.css': patch_css,
    'opa-ui.js': patch_ui,
    'tests/test_afisha.py': patch_py_tests,
    'tests/test_afisha.js': patch_js_tests,
}


def extract_js(source: str) -> str:
    return source.split('\nAFISHA_JS = """<script>\n', 1)[1].split('</script>"""', 1)[0].replace('__SOON__', '92')


def validate(modified: dict[str, str]) -> None:
    ast.parse(modified['sitebuild/afisha.py'], filename='sitebuild/afisha.py')
    ast.parse(modified['sitebuild/posts.py'], filename='sitebuild/posts.py')
    ast.parse(modified['tests/test_afisha.py'], filename='tests/test_afisha.py')
    for key in ('afisha-status-switch', 'afisha-fav-total', 'afisha-active-filters', 'afisha-week-more', 'afisha-query'):
        assert key in modified['sitebuild/afisha.py'], key
    node = shutil.which('node')
    if node:
        for name, js in (('afisha', extract_js(modified['sitebuild/afisha.py'])), ('opa-ui', modified['opa-ui.js']), ('test_afisha', modified['tests/test_afisha.js'])):
            result = subprocess.run([node, '--check'], input=js, text=True, capture_output=True)
            if result.returncode:
                raise RuntimeError(f'Ошибка JavaScript ({name}): {result.stderr}')


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--root', type=Path, default=Path.cwd(), help='Корневая папка проекта')
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Только проверить, ничего не менять')
    mode.add_argument('--apply', action='store_true', help='Применить изменения с резервными копиями')
    args = cli.parse_args()
    root = args.root.resolve()
    data = {}
    for name in FILES:
        p = root / name
        if not p.is_file():
            raise RuntimeError(f'Не найден файл проекта: {p}')
        old = p.read_text(encoding='utf-8')
        data[name] = (old, PATCHES[name](old))
    if (root / 'docs/opa-ui.js').exists():
        name = 'docs/opa-ui.js'
        old = (root / name).read_text(encoding='utf-8')
        # Built copy may be older than the source; only undo the previous mobile relocation.
        new = patch_ui(old) if '    // Clearer action names for assistive technology, without changing toolbar structure.' in old else old
        data[name] = old, new
    validate({name: pair[1] for name, pair in data.items()})
    edits = [k for k, (old, new) in data.items() if old != new]
    print('Совместимость и синтаксис: OK')
    print('Файлы для изменения:', ', '.join(edits) if edits else 'ничего: уже установлено')
    if not args.apply:
        print('Файлы НЕ изменены. Для установки: python apply_afisha_ui.py --apply')
        return 0
    if not edits:
        return 0
    backup = root / f'_backup_afisha_ui_{datetime.now():%Y%m%d_%H%M%S}'
    for name in edits:
        to = backup / name
        to.parent.mkdir(parents=True, exist_ok=True)
        to.write_text(data[name][0], encoding='utf-8')
    changed = []
    try:
        for name in edits:
            (root / name).write_text(data[name][1], encoding='utf-8', newline='\n')
            changed.append(name)
    except Exception:
        for name in changed:
            (root / name).write_text(data[name][0], encoding='utf-8', newline='\n')
        raise
    print('Установлено. Резервные копии:', backup)
    print('Теперь запустите: python rebuild_pages.py --offline')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'ОШИБКА: {exc}', file=sys.stderr)
        sys.exit(1)
