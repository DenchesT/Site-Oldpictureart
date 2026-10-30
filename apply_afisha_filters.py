# -*- coding: utf-8 -*-
"""Nine non-destructive filters for Old Picture Art's generated exhibition page.

Run in the repository root: python apply_afisha_filters.py [--check]
No Git actions, external dependencies, or network access.
"""
import argparse
import ast
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
SOURCE = ROOT / 'sitebuild' / 'afisha.py'
CSS = ROOT / 'docs' / 'style.css'
TEST = ROOT / 'tests' / 'test_afisha.py'
BROWSER_TEST = ROOT / 'tests' / 'test_afisha.js'


def replace_one(s, old, new, label):
    if new in s:
        return s
    n = s.count(old)
    if n != 1:
        raise ValueError(f'{label}: ожидался один участок, найдено {n}. Версия кода отличается; файлы не изменены.')
    return s.replace(old, new, 1)


def update_source(s):
    # Do not change split(): it powers the small current-only sidebar, summaries and schema.org.
    s = replace_one(s,
        '''    if coords:
        attrs += f' data-lat="{coords[0]:.5f}" data-lon="{coords[1]:.5f}"' + (" data-approx" if coords[2] else "")''',
        '''    # Use text already present in afisha.json; a separately populated artists list
    # takes precedence, while the free-text field can find names in the title/note.
    search = " ".join(str(x) for x in (
        item.get("title", ""), item.get("title_orig", ""), item.get("venue", ""),
        item.get("city", ""), item.get("country", ""), item.get("museum", ""),
        item.get("note", ""), " ".join(str(x) for x in (item.get("artists") or []))))
    attrs += f' data-search="{h(search.casefold())}"'
    attrs += f' data-artists="{h(" ".join(str(x) for x in (item.get("artists") or [])).casefold())}"'
    if coords:
        attrs += f' data-lat="{coords[0]:.5f}" data-lon="{coords[1]:.5f}"' + (" data-approx" if coords[2] else "")''',
        'searchable exhibition metadata')
    s = replace_one(s,
        '''        + (f'<p class="afisha-orig">{h(orig)}</p>' if orig and orig != item["title"] else "")''',
        '''        + '<button type="button" class="afisha-favorite" aria-pressed="false" aria-label="Добавить в избранные выставки" title="Добавить в избранные выставки">☆</button>'
        + (f'<p class="afisha-orig">{h(orig)}</p>' if orig and orig != item["title"] else "")''',
        'favorites button')
    # Keep old split() contract while rendering all dated records for new archive and future filters.
    s = replace_one(s,
        '''    live = running + soon
    n_ru =''',
        '''    # The main page now includes ended events (archive) and distant future
    # events. Structured data, map and sidebar still use the existing live set.
    archive = sorted((it for it in items if _iso(it["end"]) < today),
                     key=lambda x: (x["end"], x["start"]), reverse=True)
    future = sorted((it for it in items if _iso(it["start"]) > today and
                     _iso(it["end"]) >= today), key=lambda x: (x["start"], x["end"]))
    all_items = running + future + archive
    live = running + soon
    n_ru =''', 'archival display list')
    s = replace_one(s,
        '''    countries = sorted({it["country"] for it in live if region(it) == "world"},
                       key=lambda c: (-sum(1 for it in live if it["country"] == c), c))
    used_tags = {t for it in live for t in it.get("tags") or []}''',
        '''    countries = sorted({it["country"] for it in all_items if region(it) == "world"},
                       key=lambda c: (-sum(1 for it in all_items if it["country"] == c), c))
    used_tags = {t for it in all_items for t in it.get("tags") or []}
    venues = sorted({it["venue"] for it in all_items}, key=str.casefold)
    archive_years = sorted({it["end"][:4] for it in all_items}, reverse=True)''',
        'all status dropdown options')
    s = replace_one(s,
        '''    epoch_select = _options([(k, label) for k, label in EPOCHS if k in used_tags], "Все эпохи")''',
        '''    epoch_select = _options([(k, label) for k, label in EPOCHS if k in used_tags], "Все эпохи")
    venue_select = _options([(v, v) for v in venues], "Все музеи")
    archive_year_select = _options([(y, y) for y in archive_years], "Все годы")''',
        'museum/archive year dropdowns')
    s = replace_one(s,
        '''      <label class="afisha-select"><span>Эпоха</span><select id="afisha-epoch">{epoch_select}</select></label>
      {near_btn}''',
        '''      <label class="afisha-select"><span>Эпоха</span><select id="afisha-epoch">{epoch_select}</select></label>
      <label class="afisha-select"><span>Музей</span><select id="afisha-venue">{venue_select}</select></label>
      <label class="afisha-select"><span>Закрытие</span><select id="afisha-closing"><option value="all">Любая дата</option><option value="7">В ближайшие 7 дней</option><option value="30">В ближайшие 30 дней</option><option value="90">В ближайшие 90 дней</option></select></label>
      <label class="afisha-select"><span>Открытие</span><select id="afisha-opening"><option value="all">Любая дата</option><option value="7">В ближайшие 7 дней</option><option value="30">В ближайшие 30 дней</option><option value="90">В ближайшие 90 дней</option></select></label>
      <label class="afisha-select" id="afisha-archive-year-box" hidden><span>Год архива</span><select id="afisha-archive-year">{archive_year_select}</select></label>
      <label class="afisha-select"><span>Сортировка</span><select id="afisha-sort"><option value="default">По дате события</option><option value="start">По открытию</option><option value="end">По закрытию</option><option value="title">По названию</option><option value="venue">По музею</option></select></label>
      <label class="afisha-select afisha-search-label"><span>Поиск по названию</span><input id="afisha-query" type="search" placeholder="Выставка, музей, город…" autocomplete="off"></label>
      <label class="afisha-select afisha-search-label"><span>Художник</span><input id="afisha-artist" type="search" placeholder="Имя или фамилия…" autocomplete="off"></label>
      <label class="afisha-fav-only"><input id="afisha-only-favorites" type="checkbox"> Только избранные</label>
      <button type="button" class="afisha-reset" id="afisha-reset">Сбросить фильтры</button>
      {near_btn}''',
        'new filter controls')
    s = replace_one(s,
        '''  <p class="afisha-near-note" id="afisha-near" role="status" hidden></p>''',
        '''  <div class="view-switch afisha-status-switch" role="group" aria-label="Статус выставки">
    <button type="button" data-status="current" aria-pressed="true">Сейчас и скоро</button>
    <button type="button" data-status="all" aria-pressed="false">Все периоды</button>
    <button type="button" data-status="running" aria-pressed="false">Идут сейчас</button>
    <button type="button" data-status="soon" aria-pressed="false">Скоро откроются</button>
    <button type="button" data-status="archive" aria-pressed="false">Архив</button>
  </div>
  <p class="afisha-near-note" id="afisha-near" role="status" hidden></p>''',
        'status switch')
    s = replace_one(s,
        '''<ul class="afisha-list" id="afisha-soon">{''.join(row(it) for it in soon)}</ul>
</section>''',
        '''<ul class="afisha-list" id="afisha-soon">{''.join(row(it) for it in future)}</ul>
</section>
<section class="afisha-section" id="afisha-archive-box" aria-labelledby="afisha-archive-title">
<h2 class="museum-section" id="afisha-archive-title">Архив выставок</h2>
<ul class="afisha-list" id="afisha-archive">{''.join(row(it) for it in archive)}</ul>
</section>''',
        'archive section')
    s = replace_one(s,
        '''<p class="no-results" id="afisha-empty" hidden>Под эти условия сейчас ничего не идёт — попробуйте другую эпоху или город.</p>''',
        '''<p class="no-results" id="afisha-empty" hidden>Выставок по выбранным условиям не найдено. Измените или сбросьте фильтры.</p>''',
        'clear empty-state text')
    s = replace_one(s,
        '''        log.info(f"Афиша: закончились больше {STALE_DAYS} дней назад — {len(stale)}, их можно убрать "
                 f"из {AFISHA_FILE}: " + "; ".join(f"«{it['title']}»" for it in stale[:6])''',
        '''        log.info(f"Афиша: в архиве завершившиеся больше {STALE_DAYS} дней назад — {len(stale)}; "
                 f"оставьте их в {AFISHA_FILE}: " + "; ".join(f"«{it['title']}»" for it in stale[:6])''',
        'retain archived exhibitions')
    s = replace_one(s,
        '''что идёт сегодня и что скоро откроется. Закончившиеся исчезают сами.''',
        '''что идёт сегодня, скоро откроется и уже завершилось. Прошедшие выставки доступны в архиве.''',
        'new archive description')
    # Event status classification is handled in the visitor's timezone, not fixed at build time.
    s = replace_one(s,
        '''    if (!end || today > end) return 'ended';''',
        '''    if (!end || today > end) {
      if (when && end) when.textContent = 'завершилась ' + human(end, false);
      return 'ended';
    }''',
        'ended status label')
    s = replace_one(s,
        '''  var lists = {running: document.getElementById('afisha-running'), soon: document.getElementById('afisha-soon')};
  var items = Array.prototype.slice.call(page.querySelectorAll('.afisha-item')).filter(function (li) {
    var st = mark(li, __SOON__);
    li.setAttribute('data-phase', st);
    if (st === 'ended' || st === 'later') { li.remove(); return false; }
    lists[st].appendChild(li);
    return true;
  });''',
        '''  var lists = {running: document.getElementById('afisha-running'),
               soon: document.getElementById('afisha-soon'),
               archive: document.getElementById('afisha-archive')};
  var items = Array.prototype.slice.call(page.querySelectorAll('.afisha-item')).map(function (li) {
    // The page has an archive and future section: do not delete old records.
    var phase = mark(li, 365000), st = phase === 'ended' ? 'archive' : 'soon';
    if (phase === 'running') st = 'running';
    li.setAttribute('data-phase', st);
    lists[st].appendChild(li);
    return li;
  });''',
        'keep old and future records in DOM')
    s = replace_one(s,
        '''  function defaultOrder() { order(lists.running, 'data-end'); order(lists.soon, 'data-start'); }''',
        '''  function defaultOrder() {
    order(lists.running, 'data-end'); order(lists.soon, 'data-start');
    order(lists.archive, 'data-end');
    // Archive default: most recently closed first.
    Array.prototype.slice.call(lists.archive.children).reverse().forEach(function (li) {
      lists.archive.appendChild(li);
    });
  }
  function applySort() {
    if (state.near && state.sort === 'default') {
      Object.keys(lists).forEach(function (k) { order(lists[k], 'data-dist', true); });
      return;
    }
    if (state.sort === 'default') { defaultOrder(); return; }
    var key = state.sort === 'title' ? 'data-title-sort' :
      state.sort === 'venue' ? 'data-venue-sort' : 'data-' + state.sort;
    Object.keys(lists).forEach(function (k) { order(lists[k], key); });
  }''',
        'sort archive and other groups')
    s = replace_one(s,
        '''      if (numeric) return (+x) - (+y);
      return x < y ? -1 : x > y ? 1 : 0;''',
        '''      if (numeric) return (+x) - (+y);
      if (key === 'data-title-sort' || key === 'data-venue-sort')
        return (x || '').localeCompare(y || '', 'ru');
      return x < y ? -1 : x > y ? 1 : 0;''',
        'locale-aware Russian title and museum sorting')
    s = replace_one(s,
        '''  var sel = {area: document.getElementById('afisha-area'), country: document.getElementById('afisha-country'),
             epoch: document.getElementById('afisha-epoch')};
  var box = {area: document.getElementById('afisha-area-box'), country: document.getElementById('afisha-country-box')};
  var state = {reg: 'russia', area: 'all', country: 'all', epoch: 'all', near: null};''',
        '''  var sel = {area: document.getElementById('afisha-area'), country: document.getElementById('afisha-country'),
             epoch: document.getElementById('afisha-epoch'), venue: document.getElementById('afisha-venue'),
             archiveYear: document.getElementById('afisha-archive-year')};
  var box = {area: document.getElementById('afisha-area-box'), country: document.getElementById('afisha-country-box')};
  var statusBtns = Array.prototype.slice.call(document.querySelectorAll('.afisha-status-switch button'));
  var q = document.getElementById('afisha-query'), artist = document.getElementById('afisha-artist');
  var closing = document.getElementById('afisha-closing'), opening = document.getElementById('afisha-opening');
  var sorter = document.getElementById('afisha-sort'), favoritesOnly = document.getElementById('afisha-only-favorites');
  var state = {reg: 'russia', area: 'all', country: 'all', epoch: 'all', venue: 'all',
               archiveYear: 'all', status: 'current', closing: 'all', opening: 'all', sort: 'default',
               query: '', artist: '', favoritesOnly: false, near: null};
  var favorites = {};
  try { favorites = JSON.parse(localStorage.getItem('afishaFavorites') || '{}') || {}; } catch (e) {}
  if (!favorites || typeof favorites !== 'object' || Array.isArray(favorites)) favorites = {};
  items.forEach(function (li) {
    li.setAttribute('data-title-sort', (li.querySelector('.afisha-title') || {}).textContent.trim().toLocaleLowerCase('ru'));
    li.setAttribute('data-venue-sort', (li.querySelector('.afisha-place') || {}).textContent.trim().toLocaleLowerCase('ru'));
  });
  function norm(s) { return String(s || '').toLocaleLowerCase('ru').replace(/ё/g, 'е').trim(); }
  function favoriteId(li) { return li.id; }
  function paintFavorite(li) {
    var b = li.querySelector('.afisha-favorite');
    if (!b) return;
    var liked = !!favorites[favoriteId(li)];
    b.setAttribute('aria-pressed', liked ? 'true' : 'false');
    b.textContent = liked ? '★' : '☆';
    b.title = liked ? 'Убрать из избранных выставок' : 'Добавить в избранные выставки';
    b.setAttribute('aria-label', b.title);
  }
  items.forEach(function (li) {
    paintFavorite(li);
    var b = li.querySelector('.afisha-favorite');
    if (!b) return;
    b.addEventListener('click', function () {
      if (favorites[favoriteId(li)]) delete favorites[favoriteId(li)];
      else favorites[favoriteId(li)] = true;
      try { localStorage.setItem('afishaFavorites', JSON.stringify(favorites)); } catch (e) {}
      paintFavorite(li);
      show();
    });
  });''',
        'extended UI state and favorites')
    s = replace_one(s,
        '''    if (skip !== 'epoch' && s.epoch !== 'all' && tags(li).indexOf(' ' + s.epoch + ' ') < 0) return false;
    return true;''',
        '''    if (skip !== 'epoch' && s.epoch !== 'all' && tags(li).indexOf(' ' + s.epoch + ' ') < 0) return false;
    if (skip !== 'venue' && s.venue !== 'all' && li.querySelector('.afisha-place').textContent.split(' · ')[0] !== s.venue) return false;
    if (skip !== 'archiveYear' && s.archiveYear !== 'all' &&
        li.getAttribute('data-phase') === 'archive' && li.getAttribute('data-end').slice(0, 4) !== s.archiveYear) return false;
    var phase = li.getAttribute('data-phase');
    if (s.status === 'current' && (phase === 'archive' ||
        (phase === 'soon' && (day(li.getAttribute('data-start')) - today) / 864e5 > __SOON__))) return false;
    if (s.status !== 'all' && s.status !== 'current' && phase !== s.status) return false;
    if (s.closing !== 'all' && phase !== 'running') return false;
    if (s.closing !== 'all' && (day(li.getAttribute('data-end')) - today) / 864e5 > +s.closing) return false;
    if (s.opening !== 'all' && phase !== 'soon') return false;
    if (s.opening !== 'all' && (day(li.getAttribute('data-start')) - today) / 864e5 > +s.opening) return false;
    if (s.query && norm(li.getAttribute('data-search')).indexOf(norm(s.query)) < 0) return false;
    if (s.artist && norm(li.getAttribute('data-artists') + ' ' +
      li.querySelector('.afisha-title').textContent + ' ' +
      ((li.querySelector('.afisha-note') || {}).textContent || '')).indexOf(norm(s.artist)) < 0) return false;
    if (s.favoritesOnly && !favorites[favoriteId(li)]) return false;
    return true;''',
        'nine filters conditions')
    s = replace_one(s,
        '''        var s2 = {reg: state.reg, area: state.area, country: state.country, epoch: state.epoch};''',
        '''        var s2 = Object.assign({}, state);''',
        'recount with updated state')
    s = replace_one(s,
        '''      if (c) c.textContent = items.filter(function (li) { return li.getAttribute('data-region') === r; }).length;''',
        '''      if (c) c.textContent = items.filter(function (li) {
        return fits(li, Object.assign({}, state, {reg: r, area: 'all', country: 'all'}));
      }).length;''',
        'region counts for active period')
    s = replace_one(s,
        '''    var shown = {running: 0, soon: 0};''',
        '''    var shown = {running: 0, soon: 0, archive: 0};''',
        'three visible groups')
    s = replace_one(s,
        '''    document.getElementById('afisha-soon-box').hidden = !shown.soon;
    document.getElementById('afisha-empty').hidden = !!(shown.running || shown.soon);''',
        '''    document.getElementById('afisha-soon-box').hidden = !shown.soon;
    document.getElementById('afisha-archive-box').hidden = !shown.archive;
    document.getElementById('afisha-empty').hidden = !!(shown.running || shown.soon || shown.archive);
    document.getElementById('afisha-archive-year-box').hidden = state.status !== 'archive';
    statusBtns.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-status') === state.status)); });
    applySort();''',
        'archive visibility and status')
    s = replace_one(s,
        '''    Object.keys(sel).forEach(function (k) { if (sel[k]) sel[k].value = state[k]; });
    recount();''',
        '''    Object.keys(sel).forEach(function (k) { if (sel[k]) sel[k].value = state[k]; });
    closing.value = state.closing; opening.value = state.opening; sorter.value = state.sort;
    q.value = state.query; artist.value = state.artist; favoritesOnly.checked = state.favoritesOnly;
    recount();''',
        'sync new controls')
    s = replace_one(s,
        '''      localStorage.setItem('afishaEpoch', state.epoch);''',
        '''      localStorage.setItem('afishaEpoch', state.epoch);
      localStorage.setItem('afishaFilters', JSON.stringify({status: state.status, venue: state.venue,
        archiveYear: state.archiveYear, closing: state.closing, opening: state.opening,
        sort: state.sort, favoritesOnly: state.favoritesOnly}));''',
        'persist new filters')
    s = replace_one(s,
        '''  Object.keys(sel).forEach(function (k) {
    if (sel[k]) sel[k].addEventListener('change', function () { state[k] = sel[k].value; show(); });
  });''',
        '''  Object.keys(sel).forEach(function (k) {
    if (sel[k]) sel[k].addEventListener('change', function () { state[k] = sel[k].value; show(); });
  });
  statusBtns.forEach(function (b) {
    b.addEventListener('click', function () {
      state.status = b.getAttribute('data-status');
      if (state.status !== 'archive') state.archiveYear = 'all';
      if (state.status === 'archive') state.closing = state.opening = 'all';
      if (state.status === 'running') state.opening = 'all';
      if (state.status === 'soon') state.closing = 'all';
      show();
    });
  });
  [closing, opening, sorter].forEach(function (el) {
    el.addEventListener('change', function () {
      state[el === closing ? 'closing' : el === opening ? 'opening' : 'sort'] = el.value;
      if (el === closing && el.value !== 'all') { state.opening = 'all'; state.status = 'running'; }
      if (el === opening && el.value !== 'all') { state.closing = 'all'; state.status = 'soon'; }
      show();
    });
  });
  var searchTimer;
  [q, artist].forEach(function (el) {
    el.addEventListener('input', function () {
      clearTimeout(searchTimer);
      var key = el === q ? 'query' : 'artist', val = el.value;
      searchTimer = setTimeout(function () { state[key] = val; show(); }, 130);
    });
  });
  favoritesOnly.addEventListener('change', function () { state.favoritesOnly = favoritesOnly.checked; show(); });
  document.getElementById('afisha-reset').addEventListener('click', function () {
    state.area = state.country = state.epoch = state.venue = state.archiveYear = 'all';
    state.closing = state.opening = 'all'; state.sort = 'default';
    state.status = 'current'; state.query = state.artist = ''; state.favoritesOnly = false;
    show();
  });''',
        'new filter listeners')
    # Do not let nearest map automatically select an already ended exhibition.
    s = replace_one(s,
        '''        if (li.hasAttribute('data-lat') && (!best || +li.getAttribute('data-dist') < +best.getAttribute('data-dist'))) best = li;''',
        '''        if (li.getAttribute('data-phase') !== 'archive' && li.hasAttribute('data-lat') &&
            (!best || +li.getAttribute('data-dist') < +best.getAttribute('data-dist'))) best = li;''',
        'exclude archive from nearest')
    s = replace_one(s,
        '''        state.reg = best.getAttribute('data-region');
        state.area = state.country = 'all';''',
        '''        state.reg = best.getAttribute('data-region');
        state.area = state.country = state.archiveYear = 'all';
        state.status = 'current'; state.closing = state.opening = 'all';''',
        'nearby navigation opens live exhibition filters')
    s = replace_one(s,
        '''    state.reg = target.getAttribute('data-region');
  } else {''',
        '''    state.reg = target.getAttribute('data-region');
    state.status = target.getAttribute('data-phase');
  } else {''',
        'open deep link with correct status')
    s = replace_one(s,
        '''      state.epoch = localStorage.getItem('afishaEpoch') || 'all';
    } catch (e) {}''',
        '''      state.epoch = localStorage.getItem('afishaEpoch') || 'all';
      var savedFilters = JSON.parse(localStorage.getItem('afishaFilters') || '{}');
      ['status', 'venue', 'archiveYear', 'closing', 'opening', 'sort', 'favoritesOnly'].forEach(function (k) {
        if (Object.prototype.hasOwnProperty.call(savedFilters, k)) state[k] = savedFilters[k];
      });
    } catch (e) {}''',
        'restore persisted filters')
    s = replace_one(s,
        '''  if (state.reg !== 'world') state.reg = 'russia';''',
        '''  if (state.reg !== 'world') state.reg = 'russia';
  if (['current','all','running','soon','archive'].indexOf(state.status) < 0) state.status = 'current';
  if (['all','7','30','90'].indexOf(state.closing) < 0) state.closing = 'all';
  if (['all','7','30','90'].indexOf(state.opening) < 0) state.opening = 'all';
  if (['default','start','end','title','venue'].indexOf(state.sort) < 0) state.sort = 'default';''',
        'stored value validation')
    s = replace_one(s,
        '''    if (el.hidden) { state.reg = el.getAttribute('data-region'); state.area = state.country = state.epoch = 'all'; show(); }''',
        '''    if (el.hidden) { state.reg = el.getAttribute('data-region'); state.area = state.country = state.epoch = 'all';
      state.status = el.getAttribute('data-phase'); state.archiveYear = state.venue = 'all';
      state.closing = state.opening = 'all'; state.query = state.artist = ''; state.favoritesOnly = false;
      show(); }''',
        'deep link filter reset')
    s = replace_one(s,
        '''    visited = match_visits(live_items, visits)''',
        '''    visited = match_visits(items, visits)  # include historical visits in archive''',
        'attach historical visits to archive')
    s = replace_one(s,
        '''page.querySelectorAll('.afisha-item[data-lat]')''',
        '''page.querySelectorAll('.afisha-item[data-lat]:not([data-phase="archive"])')''',
        'archive is not placed on live map')
    # Stable source generation: no changes to JSON metadata or previous schema.
    ast.parse(s)
    return s


CSS_APPEND = r'''
/* Afisha filters: same colors, fonts, spacing and control language as existing site. */
.afisha-status-switch { display: inline-flex; margin: 0 0 var(--s4); flex-wrap: wrap; }
.afisha-search-label input { background: var(--card-bg); color: var(--text); border: 1px solid var(--input-border); padding: .5rem .6rem; font: inherit; width: min(100%, 230px); min-height: 36px; }
.afisha-search-label input:focus-visible, .afisha-favorite:focus-visible, .afisha-reset:focus-visible { outline: 2px solid var(--active); outline-offset: 2px; }
.afisha-fav-only { display: inline-flex; align-items: center; gap: .45rem; font-family: var(--ff-data); font-size: var(--fs-xs); cursor: pointer; }
.afisha-fav-only input { accent-color: var(--active); width: 17px; height: 17px; }
.afisha-reset { border: 1px solid var(--border); background: var(--card-bg); color: var(--text); font: var(--fs-xs) var(--ff-data); padding: .5rem .7rem; cursor: pointer; }
.afisha-favorite { float: right; border: 1px solid var(--border); background: var(--card-bg); color: var(--link); border-radius: 2px; font-size: 1.2rem; min-width: 38px; min-height: 38px; margin-left: var(--s2); cursor: pointer; }
.afisha-favorite[aria-pressed="true"] { color: var(--active); background: var(--accent-soft); }
.afisha-status-switch [aria-pressed="true"] { font-weight: bold; }
@media (max-width: 620px) {
  .afisha-status-switch { width: 100%; }
  .afisha-status-switch button { flex: 1 1 43%; min-height: 42px; }
  .afisha-filters .afisha-select { min-width: 135px; }
  .afisha-search-label input { width: 100%; }
}
'''


def update_tests(s):
    s = replace_one(s,
        '''    ok("закончившихся на странице нет", "Закрылась" not in page and "Откроется нескоро" not in page)''',
        '''    ok("прошедшие выставки и дальние анонсы доступны на странице", "Закрылась" in page and "Откроется нескоро" in page)
    ok("архив имеет отдельный список", 'id="afisha-archive"' in page and 'data-status="archive"' in page)
    ok("все девять фильтров подключены", all('id="afisha-' + k + '"' in page for k in (
        'closing', 'opening', 'venue', 'query', 'artist', 'archive-year', 'sort', 'only-favorites', 'reset')))''',
        'legacy test for archive')
    s = replace_one(s,
        '''    ok("в списке эпох — только те, что есть у идущих", '<select id="afisha-epoch"><option value="all" data-label="Все эпохи">Все эпохи</option></select>' in page)''',
        '''    ok("эпохи доступны для всех периодов", '<select id="afisha-epoch"><option value="all" data-label="Все эпохи">Все эпохи</option></select>' in page)''',
        'legacy epoch label')
    s = replace_one(s,
        '''    ok("давно закончившиеся — подсказка убрать", "Давно закрылась" in text and "Закрылась»" in text, text)''',
        '''    ok("давно закончившиеся — сохранены для архива", "Давно закрылась" in text and "оставьте их" in text, text)''',
        'legacy archive retention test')
    ast.parse(s)
    return s


def update_browser_tests(s):
    s = replace_one(s,
        "all: [...document.querySelectorAll('.afisha-item')].map(row),",
        "all: vis('.afisha-item').map(row),",
        'consider visible cards in default status')
    s = replace_one(s,
        "  ok('ничего закончившегося', st.all.every(r => r.end >= DAY), st.all.filter(r => r.end < DAY).map(r => r.title).join(', '));",
        "  ok('архив скрыт по умолчанию', st.all.every(r => r.end >= DAY), st.all.filter(r => r.end < DAY).map(r => r.title).join(', '));",
        'archive default visibility')
    s = replace_one(s,
        "  if (closed) ok(`закрылась к ${LATER} — пропала («${closed.title}»)`, !st.all.some(r => r.title === closed.title));",
        "  if (closed) ok(`закрылась к ${LATER} — переехала в архив («${closed.title}»)`, !st.all.some(r => r.title === closed.title) && await page.evaluate(t => [...document.querySelectorAll('#afisha-archive .afisha-item')].some(li => li.querySelector('.afisha-title a').textContent === t), closed.title));",
        'closed exhibition remains in archive')
    s = replace_one(s,
        "  ok('всё закончилось — «пусто», разделов нет', empty && !st.runningBox && !st.soonBox && st.all.length === 0);",
        "  ok('всё закончилось — текущая афиша пуста, архив остаётся', empty && !st.runningBox && !st.soonBox && st.all.length === 0 && await page.$eval('#afisha-archive', e => e.children.length > 0));",
        'archived pages retained')
    s = replace_one(s,
        '''  // Города России — выпадающий список.''',
        '''  // Дополнительные фильтры: используем реальные записи и подставленную дату.
  const archivedRu = data.filter(x => x.country === 'Россия' && x.end < DAY).length;
  await page.click('.afisha-status-switch [data-status="archive"]');
  const archiveCount = await page.$$eval('#afisha-archive .afisha-item:not([hidden])', xs => xs.length);
  ok('архив по России показывает завершившиеся выставки', archiveCount === archivedRu,
     `${archiveCount} из ${archivedRu}`);
  if (archiveCount) {
    const archiveYears = [...new Set(data.filter(x => x.country === 'Россия' && x.end < DAY).map(x => x.end.slice(0, 4)))];
    const year = archiveYears[0];
    await page.selectOption('#afisha-archive-year', year);
    const years = await page.$$eval('#afisha-archive .afisha-item:not([hidden])', xs => xs.map(x => x.dataset.end.slice(0, 4)));
    ok('год архива оставляет только выставки выбранного года', years.length > 0 && years.every(y => y === year), years.join(', '));
    await page.selectOption('#afisha-archive-year', 'all');
  }
  await page.click('.afisha-status-switch [data-status="current"]');

  const first = await page.$eval('#afisha-running .afisha-item:not([hidden])', li => ({
    id: li.id, title: li.querySelector('.afisha-title a').textContent.trim(),
    venue: li.querySelector('.afisha-place').textContent.split(' · ')[0]
  }));
  await page.fill('#afisha-query', first.title.slice(0, Math.min(6, first.title.length)));
  await page.waitForTimeout(200);
  const queryHit = await page.$eval('#' + first.id, li => !li.hidden);
  ok('поиск находит выставку по названию', queryHit);
  await page.fill('#afisha-query', '');
  await page.waitForTimeout(200);
  await page.selectOption('#afisha-venue', first.venue);
  const venues = await page.$$eval('.afisha-item:not([hidden])', xs => xs.map(x => x.querySelector('.afisha-place').textContent.split(' · ')[0]));
  ok('музей ограничивает список одним местом', venues.length > 0 && venues.every(v => v === first.venue));
  await page.selectOption('#afisha-venue', 'all');

  await page.click('#' + first.id + ' .afisha-favorite');
  await page.check('#afisha-only-favorites');
  const liked = await page.$$eval('.afisha-item:not([hidden])', xs => xs.map(x => x.id));
  ok('избранное оставляет отмеченную выставку', liked.length === 1 && liked[0] === first.id, liked.join(', '));
  await page.reload();
  await page.waitForTimeout(200);
  ok('избранное сохраняется после перезагрузки', await page.$eval('#' + first.id + ' .afisha-favorite', b => b.getAttribute('aria-pressed') === 'true'));
  await page.uncheck('#afisha-only-favorites');
  await page.click('#' + first.id + ' .afisha-favorite');

  await page.selectOption('#afisha-closing', '30');
  const closings = await page.$$eval('.afisha-item:not([hidden])', xs => xs.map(x => x.dataset.end));
  ok('закрытие за 30 дней показывает только действующие выставки', closings.every(d => d >= DAY && d <= plusDays(DAY, 30)));
  await page.selectOption('#afisha-closing', 'all');
  await page.selectOption('#afisha-opening', '90');
  const openings = await page.$$eval('.afisha-item:not([hidden])', xs => xs.map(x => x.dataset.start));
  ok('открытие за 90 дней показывает только будущие выставки', openings.every(d => d > DAY && d <= plusDays(DAY, 90)));
  await page.click('#afisha-reset');
  await page.selectOption('#afisha-sort', 'title');
  const titles = await page.$$eval('#afisha-running .afisha-item:not([hidden])', xs => xs.map(x => x.querySelector('.afisha-title a').textContent.trim()));
  ok('сортировка по названию', titles.every((t, i) => i === 0 || titles[i - 1].localeCompare(t, 'ru') <= 0));
  await page.click('#afisha-reset');

  // Города России — выпадающий список.''',
        'browser regressions for all new UI controls')
    return s


def plan():
    if not SOURCE.is_file() or not CSS.is_file() or not TEST.is_file() or not BROWSER_TEST.is_file():
        raise FileNotFoundError('Запустите скрипт из корня Site-Oldpictureart (рядом с afisha.json).')
    original = {SOURCE: SOURCE.read_text(encoding='utf-8'),
                CSS: CSS.read_text(encoding='utf-8'),
                TEST: TEST.read_text(encoding='utf-8'),
                BROWSER_TEST: BROWSER_TEST.read_text(encoding='utf-8')}
    new = dict(original)
    if 'id="afisha-archive"' not in original[SOURCE]:
        new[SOURCE] = update_source(original[SOURCE])
    if '/* Afisha filters: same colors' not in original[CSS]:
        new[CSS] = original[CSS].rstrip() + '\n' + CSS_APPEND
    if 'прошедшие выставки и дальние анонсы доступны на странице' not in original[TEST]:
        new[TEST] = update_tests(original[TEST])
    if 'архив скрыт по умолчанию' not in original[BROWSER_TEST]:
        new[BROWSER_TEST] = update_browser_tests(original[BROWSER_TEST])
    return original, new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='проверить совместимость без изменений')
    args = parser.parse_args()
    old, new = plan()     # fully validate before writing even one file
    changes = [p for p in new if new[p] != old[p]]
    if not changes:
        print('Изменения уже установлены.'); return
    for p in changes:
        print(('Проверено: ' if args.check else 'Изменяю: ') + str(p.relative_to(ROOT)))
    if args.check:
        print('Проверка совместимости прошла. Файлы не менялись.'); return
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    for p in changes:
        backup = p.with_name(p.name + '.bak-' + stamp)
        backup.write_text(old[p], encoding='utf-8')
        p.write_text(new[p], encoding='utf-8', newline='\n')
    print('Готово. Резервные копии сохранены рядом с изменёнными файлами.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError, SyntaxError) as exc:
        raise SystemExit(f'Не применено: {exc}')
