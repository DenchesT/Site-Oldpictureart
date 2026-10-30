# -*- coding: utf-8 -*-
"""Old Picture Art: mobile menu, search label and account-synced exhibition favorites.

Compatible with Site-Oldpictureart main at d287a40 (2026-10-31).
Transactional: builds/validates all edits before writing; no Git operations.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys

MARKER = 'OPA MOBILE & EXHIBITION FAVORITES 2026-10-31'
FILES = ('site_common.py', 'sitebuild/afisha.py', 'sitebuild/posts.py', 'opa-ui.js', 'docs/opa-ui.js', 'docs/style.css')


def once(text: str, old: str, new: str, title: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{title}: ожидалось ровно одно совпадение, найдено {n}. Проект не изменён.')
    return text.replace(old, new, 1)


SHARED_FAVORITES_JS = r'''// OPA MOBILE & EXHIBITION FAVORITES 2026-10-31: cloud keys are independent
// from painting IDs, but reuse the already deployed YDB likes table/API.
function readAfishaFavorites() {
  try {
    var v = JSON.parse(localStorage.getItem('afishaFavorites') || '{}');
    return v && typeof v === 'object' && !Array.isArray(v) ? v : {};
  } catch (e) { return {}; }
}
function writeAfishaFavorites(v) {
  try { localStorage.setItem('afishaFavorites', JSON.stringify(v)); } catch (e) {}
}
function readAfishaFavoritePending() {
  try {
    var v = JSON.parse(localStorage.getItem('afishaFavoritesPending') || '{}');
    return v && typeof v === 'object' && !Array.isArray(v) ? v : {};
  } catch (e) { return {}; }
}
function writeAfishaFavoritePending(v) {
  try {
    if (Object.keys(v).length) localStorage.setItem('afishaFavoritesPending', JSON.stringify(v));
    else localStorage.removeItem('afishaFavoritesPending');
  } catch (e) {}
}
function announceAfishaFavorites() {
  window.dispatchEvent(new Event('opa:afisha-favorites'));
}
function afishaAccountKey() {
  var s = getSession();
  if (!s || !s.token) return '';
  try {
    var raw = s.token.split('.')[0].replace(/-/g, '+').replace(/_/g, '/');
    var data = JSON.parse(atob(raw));
    return typeof data.u === 'string' ? data.u : '';
  } catch (e) { return ''; }
}
var _afishaFavQueue = Promise.resolve(), _afishaFavChanges = 0;
function syncAfishaFavorites() {
  if (!CLOUD.on || !getSession() || !window.OPA_AFISHA_CATALOG) return Promise.resolve(false);
  // Serialize updates so two rapid star clicks cannot reorder requests.
  var job = _afishaFavQueue.catch(function () { return false; }).then(function () {
    if (!getSession()) return false;
    var who = afishaAccountKey();
    if (!who) return false;
    var catalog = window.OPA_AFISHA_CATALOG;
    var version = _afishaFavChanges;
    var saved = readAfishaFavorites(), pending = readAfishaFavoritePending();
    var former = '';
    try { former = localStorage.getItem('afishaFavoritesAccount') || ''; } catch (e) {}
    // Do not silently upload one signed-in user's favorites to a different account.
    if (former && former !== who) {
      saved = {}; pending = {};
      writeAfishaFavorites(saved); writeAfishaFavoritePending(pending);
      announceAfishaFavorites();
    }
    var merging = former !== who;
    var up = [], down = [];
    Object.keys(catalog).forEach(function (id) {
      var cloudId = catalog[id].key;
      if (!cloudId) return;
      if (Object.prototype.hasOwnProperty.call(pending, id)) {
        (pending[id] ? up : down).push(cloudId);
      } else if (merging && saved[id]) {
        up.push(cloudId);
      }
    });
    return Promise.all(down.map(function (key) { return cloudCall('unlike', {post_id: key}); }))
      .then(function () { return cloudCall('sync', {likes: up}); })
      .then(function (answer) {
        var remote = new Set(answer.likes || []), refreshed = {};
        Object.keys(catalog).forEach(function (id) {
          if (remote.has(catalog[id].key)) refreshed[id] = true;
        });
        try { localStorage.setItem('afishaFavoritesAccount', who); } catch (e) {}
        // A click during the request remains pending for the next queued sync.
        if (_afishaFavChanges === version) {
          writeAfishaFavorites(refreshed);
          writeAfishaFavoritePending({});
          announceAfishaFavorites();
        }
        return true;
      }).catch(function (e) {
        console.warn('Избранные выставки: синхронизация недоступна:', e.message);
        return false; // keep pending changes on network failures
      });
  });
  _afishaFavQueue = job;
  return job;
}
function setAfishaFavorite(id, liked) {
  var catalog = window.OPA_AFISHA_CATALOG || {};
  if (!Object.prototype.hasOwnProperty.call(catalog, id)) return;
  var saved = readAfishaFavorites(), pending = readAfishaFavoritePending();
  if (liked) saved[id] = true; else delete saved[id];
  pending[id] = !!liked;
  _afishaFavChanges++;
  writeAfishaFavorites(saved);
  writeAfishaFavoritePending(pending);
  announceAfishaFavorites();
  if (CLOUD.on && getSession()) syncAfishaFavorites();
}
'''


def patch_common(s: str) -> str:
    if MARKER in s:
        return s
    s = once(s,
        '// Пропуск от функции: {token, name, provider, exp}. Сам токен подписан',
        SHARED_FAVORITES_JS + '\n// Пропуск от функции: {token, name, provider, exp}. Сам токен подписан',
        'Общая синхронизация выставок')
    s = once(s,
        '(j.likes || []).forEach(function (id) { merged[id] = true; });',
        '(j.likes || []).forEach(function (id) { if (String(id).indexOf(\'exh_\') !== 0) merged[id] = true; });',
        'Разделение картин и выставок в облаке')
    s = once(s, 'Чтобы отмеченные картины были и на телефоне, и на компьютере.',
             'Чтобы избранные картины и выставки были доступны на телефоне и компьютере.',
             'Текст авторизации')
    s = once(s, 'Отмеченные картины видны на всех ваших устройствах.',
             'Избранные картины и выставки видны на всех ваших устройствах.',
             'Текст профиля')
    return s


def patch_afisha(s: str) -> str:
    if MARKER in s:
        return s
    s = once(s, 'import json\nimport logging\n', 'import json\nimport hashlib\nimport logging\n', 'Хеш выставки')
    s = once(s, '    BASE_URL, latin_slug, museum_page, AFISHA_FILE, has_afisha, MAP_LAYERS_JS,\n',
             '    BASE_URL, latin_slug, museum_page, AFISHA_FILE, has_afisha, MAP_LAYERS_JS, AUTH_JS,\n',
             'Авторизация на афише')
    helper = '''# OPA MOBILE & EXHIBITION FAVORITES 2026-10-31
# Stable, namespaced 36-character ID: accepted by existing cloud/auth/index.py.
# Never use an exhibition anchor directly as a cloud ID (it can be >40 chars).
def _afisha_favorite_key(item_id):
    return "exh_" + hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:32]


def _afisha_favorites_script(items):
    catalog = {
        it["id"]: {"key": _afisha_favorite_key(it["id"]), "title": it["title"],
                   "venue": it["venue"], "city": it["city"], "end": it["end"]}
        for it in items
    }
    # Safe even when a museum sends a title containing HTML or </script>.
    payload = json.dumps(catalog, ensure_ascii=True).replace("<", "\\\\u003c").replace(">", "\\\\u003e")
    return '<script>window.OPA_AFISHA_CATALOG=' + payload + ';</script>'


'''
    s = once(s, 'def afisha_id(item):\n', helper+'def afisha_id(item):\n', 'Каталог избранных выставок')
    # The original favorite ID remains the HTML anchor; mapping to YDB lives in the catalog.
    s = once(s, '  var favorites = {};\n  try { favorites = JSON.parse(localStorage.getItem(\'afishaFavorites\') || \'{}\') || {}; } catch (e) {}\n  if (!favorites || typeof favorites !== \'object\' || Array.isArray(favorites)) favorites = {};',
             '  var favorites = readAfishaFavorites();', 'Чтение избранного через общий модуль')
    old = '''  items.forEach(function (li) {
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
  });'''
    new = '''  items.forEach(function (li) {
    paintFavorite(li);
    var b = li.querySelector('.afisha-favorite');
    if (!b) return;
    b.addEventListener('click', function () {
      setAfishaFavorite(favoriteId(li), !favorites[favoriteId(li)]);
    });
  });
  window.addEventListener('opa:afisha-favorites', function () {
    favorites = readAfishaFavorites();
    items.forEach(paintFavorite);
    show();
  });'''
    s=once(s,old,new,'Сохранение звёздочек')
    # Favorites link on home turns on "all periods" so archived starred events stay reachable.
    needle="  if (state.reg !== 'world') state.reg = 'russia';"
    replacement="""  if (new URLSearchParams(location.search).get('favorites') === '1') {
    state.favoritesOnly = true;
    state.status = 'all';
    state.area = state.country = state.epoch = state.venue = state.archiveYear = 'all';
    state.closing = state.opening = 'all';
    state.query = state.artist = '';
  }
  if (state.reg !== 'world') state.reg = 'russia';"""
    s=once(s,needle,replacement,'Ссылка на избранные выставки')
    s=once(s,'  show();\n  function highlight(el) {',
           '  show();\n  syncAfishaFavorites();\n  function highlight(el) {', 'Синхронизация после открытия афиши')
    s=once(s, "  {theme_button('theme-toggle-inline')}\n</div>\n{scroll_top_button()}",
             "  {theme_button('theme-toggle-inline')}\n  <button type=\"button\" id=\"auth-btn\" class=\"topbar-btn\" aria-label=\"Войти\">Войти</button>\n</div>\n{scroll_top_button()}",
             'Кнопка авторизации в афише')
    s=once(s, '{SCROLL_TOP_JS}\n{COMMON_JS}\n{AFISHA_JS}\n{map_js}',
             '{SCROLL_TOP_JS}\n{COMMON_JS}\n{_afisha_favorites_script(all_items)}\n{AUTH_JS}\n{AFISHA_JS}\n{map_js}',
             'Облачные функции на странице афиши')
    return s


def patch_posts(s: str) -> str:
    if MARKER in s:
        return s
    s=once(s,'from .afisha import AFISHA_JS, afisha_block, load_afisha',
           'from .afisha import AFISHA_JS, afisha_block, load_afisha, _afisha_favorites_script',
           'Каталог избранного на главной')
    s=once(s, '    # Афиша — крупные выставки в России и в мире (sitebuild/afisha.py):',
           '    # OPA MOBILE & EXHIBITION FAVORITES 2026-10-31\n    # Афиша — крупные выставки в России и в мире (sitebuild/afisha.py):',
           'Маркер версии генератора')
    s=once(s,'    afisha_html = afisha_block(load_afisha()[0])',
           '    afisha_items = load_afisha()[0]\n    afisha_html = afisha_block(afisha_items)',
           'Данные афиши для избранного')
    s=once(s,'Поиск по названию, автору и музею · клавиша /',
           'Поиск по названию, художнику или музею', 'Подпись поля поиска')
    old='''    fav_html = ('<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon icon-fav" '
                'aria-expanded="false" onclick="toggleSection(this)">Избранное '
                '<span id="fav-count" class="count"></span></button>'
                f'<div class="sidebar-content collapsed"><ul id="fav-list">{empty_fav}</ul></div></div>')'''
    new='''    fav_html = ('<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon icon-fav" '
                'aria-expanded="false" onclick="toggleSection(this)">Избранное '
                '<span id="fav-count" class="count"></span></button>'
                '<div class="sidebar-content collapsed"><div class="opa-favorites-groups">'
                '<p class="opa-fav-subhead">Картины</p>'
                f'<ul id="fav-list">{empty_fav}</ul>'
                '<p class="opa-fav-subhead">Выставки <a class="opa-fav-all" '
                'href="afisha.html?favorites=1">Смотреть в афише</a></p>'
                '<ul id="fav-afisha-list"><li class="fav-empty">Отметьте ☆ в афише</li></ul>'
                '</div></div></div>')'''
    s=once(s,old,new,'Единая вкладка избранного')
    s=once(s, '''    if (favCount) favCount.textContent = likedIds.length ? '(' + likedIds.length + ')' : '';''',
           '''    const afishaLikes = readAfishaFavorites();
    const events = window.OPA_AFISHA_CATALOG || {{}};
    const exhibitCount = Object.keys(afishaLikes).filter(id => afishaLikes[id] && events[id]).length;
    const total = likedIds.length + exhibitCount;
    if (favCount) favCount.textContent = total ? '(' + total + ')' : '';''',
           'Счётчик картин и выставок')
    s=once(s,'// Аккордеон сайдбара: класс open нужен',
           '''function updateAfishaFavList() {{
    const list = document.getElementById('fav-afisha-list');
    if (!list) return;
    const favorites = readAfishaFavorites();
    const catalog = window.OPA_AFISHA_CATALOG || {{}};
    const ids = Object.keys(favorites).filter(id => favorites[id] && catalog[id]);
    ids.sort((a, b) => (catalog[a].end || '').localeCompare(catalog[b].end || '') * -1);
    list.replaceChildren();
    if (!ids.length) {{
        const li = document.createElement('li');
        li.className = 'fav-empty';
        li.textContent = 'Отметьте ☆ на странице афиши';
        list.appendChild(li);
        return;
    }}
    ids.forEach(function (id) {{
        const item = catalog[id], li = document.createElement('li'), a = document.createElement('a');
        a.href = 'afisha.html?favorites=1#' + encodeURIComponent(id);
        a.textContent = item.title;
        a.title = item.venue + (item.city ? ', ' + item.city : '');
        li.appendChild(a);
        const p = document.createElement('span');
        p.className = 'opa-fav-place';
        p.textContent = item.venue + (item.city ? ' · ' + item.city : '');
        li.appendChild(p);
        list.appendChild(li);
    }});
}}
window.addEventListener('opa:afisha-favorites', function () {{
    updateAfishaFavList();
    updateFavList();
}});
window.addEventListener('storage', function (e) {{
    if (e.key === 'afishaFavorites' || e.key === 'likes') {{ updateAfishaFavList(); updateFavList(); }}
}});

// Аккордеон сайдбара: класс open нужен''', 'Выставки в избранном на главной')
    s=once(s, '''    updateFavList();

    // Исходный порядок''',
           '''    updateFavList();
    updateAfishaFavList();

    // Исходный порядок''',
           'Первый вывод избранных выставок')
    s=once(s, '{CLOUD_JS}\n<script>\n// Вошедшему в аккаунт',
           '{CLOUD_JS}\n{_afisha_favorites_script(afisha_items)}\n<script>\n// Вошедшему в аккаунт',
           'Каталог избранного для облака на главной')
    s=once(s, 'cloudSync().then(function (changed) {{ if (changed) updateFavList(); }});',
           '''cloudSync().then(function (changed) {{ if (changed) updateFavList(); }});
syncAfishaFavorites().then(function (changed) {{
  if (changed) {{ updateAfishaFavList(); updateFavList(); }}
}});''',
           'Облачная синхронизация избранных выставок на главной')
    return s


MOBILE_LAYOUT_JS = '''    // OPA MOBILE & EXHIBITION FAVORITES 2026-10-31
    // Keep only the Menu control over artwork on phones. Sort/view/count
    // remain available INSIDE the same menu (no duplicate controls).
    var toolbar = document.querySelector('.index-page .results-bar');
    if (sidebar && toolbar) {
      var chipsForMobile = document.getElementById('opa-active-filters');
      var main = toolbar.parentNode;
      var barAnchor = document.createComment('OPA toolbar original position');
      main.insertBefore(barAnchor, toolbar);
      var chipsAnchor = document.createComment('OPA chips original position');
      if (chipsForMobile && chipsForMobile.parentNode)
        chipsForMobile.parentNode.insertBefore(chipsAnchor, chipsForMobile);
      var mobileControls = document.createElement('div');
      mobileControls.className = 'opa-mobile-controls';
      var searchBlock = sidebar.querySelector('.sidebar-search');
      if (searchBlock) searchBlock.insertAdjacentElement('afterend', mobileControls);
      else sidebar.prepend(mobileControls);
      var media = window.matchMedia('(max-width: 900px)');
      function placeControls() {
        if (media.matches) {
          mobileControls.appendChild(toolbar);
          if (chipsForMobile) mobileControls.appendChild(chipsForMobile);
        } else {
          if (barAnchor.parentNode) barAnchor.parentNode.insertBefore(toolbar, barAnchor);
          if (chipsForMobile && chipsAnchor.parentNode)
            chipsAnchor.parentNode.insertBefore(chipsForMobile, chipsAnchor);
        }
      }
      placeControls();
      if (media.addEventListener) media.addEventListener('change', placeControls);
      else if (media.addListener) media.addListener(placeControls);
    }
'''


def patch_ui(s: str) -> str:
    if MARKER in s:
        return s
    return once(s, '    // Clearer action names for assistive technology, without changing toolbar structure.',
                MOBILE_LAYOUT_JS+'    // Clearer action names for assistive technology, without changing toolbar structure.',
                'Мобильное меню вместо панели сортировки')


MOBILE_CSS = '''
/* OPA MOBILE & EXHIBITION FAVORITES 2026-10-31
   Existing palette and typography stay unchanged. */
.opa-favorites-groups { min-width: 0; }
.opa-fav-subhead {
  font: 600 var(--fs-xs) var(--ff-data); color: var(--text-2);
  margin: .7rem 0 .3rem; border-bottom: 1px solid var(--rule-soft);
  display: flex; align-items: baseline; gap: .5rem; justify-content: space-between;
}
.sidebar a.opa-fav-all {
  display: inline; font: 400 .68rem var(--ff-data); text-transform: none;
  padding: 0; border: 0; color: var(--link); text-decoration: underline;
}
#fav-afisha-list li { margin: .4rem 0; }
#fav-afisha-list li > a { display: block; padding: 1px var(--s2); }
.opa-fav-place {
  display: block; padding: 0 var(--s2); font: var(--fs-xs) var(--ff-data);
  line-height: 1.4; color: var(--muted); overflow-wrap: anywhere;
}
.opa-mobile-controls { display: none; }
@media (max-width: 900px) {
  /* All catalog controls live in the off-canvas menu. No sticky block over art. */
  .index-page .opa-mobile-controls { display: block; border-bottom: 1px solid var(--border); margin: .25rem 0 .65rem; padding: .25rem 0 .65rem; }
  .index-page .opa-mobile-controls .results-bar {
    display: flex; position: static; top: auto; z-index: auto; background: transparent;
    box-shadow: none; padding: .3rem 0; margin: 0; border-bottom: 0;
    min-height: 0; gap: .45rem; width: 100%;
  }
  .index-page .opa-mobile-controls .bar-controls { width: 100%; gap: .5rem; align-items: center; }
  .index-page .opa-mobile-controls .bar-label { display: block; width: 100%; }
  .index-page .opa-mobile-controls .sort-select { flex: 1 1 100%; width: 100%; max-width: none; min-height: 38px; }
  .index-page .opa-mobile-controls .view-switch { width: 100%; }
  .index-page .opa-mobile-controls .view-switch button { flex: 1 1 0; padding: .45rem .2rem; font-size: .67rem; white-space: normal; }
  .index-page .opa-mobile-controls .active-filter-chips { padding: .3rem 0 0; }
  .index-page #cards { scroll-margin-top: 3.5rem; }
  .index-page .grid.list .card-no { white-space: nowrap; }
  /* Keep the catalog number on one line, not № on a line by itself. */
  .index-page .grid.list .card-no { font-size: .66rem; letter-spacing: 0; }
  .index-page .grid.list .card-no::before { content: '№'; }
  /* Extra breathing room around row separators after navigating Back. */
  .index-page .grid.list .card { padding: var(--s4) var(--s2) var(--s5); row-gap: var(--s3); }
  .index-page .grid.list .card-facts { padding-bottom: .4rem; }
  /* The restored keyboard focus outline surrounds the card, not its text. */
  .index-page .card:focus-within { outline: none; }
  .index-page .card-link:focus-visible::after { inset: -4px; outline-offset: 0; border-radius: 2px; }
}
'''


def patch_css(s: str) -> str:
    if MARKER in s:
        return s
    return s.rstrip() + '\n' + MOBILE_CSS


PATCHES = {
    'site_common.py': patch_common,
    'sitebuild/afisha.py': patch_afisha,
    'sitebuild/posts.py': patch_posts,
    'opa-ui.js': patch_ui,
    'docs/style.css': patch_css,
}


def extract_inline_js(source: str, begin: str, end: str) -> str:
    start = source.index(begin) + len(begin)
    stop = source.index(end, start)
    return source[start:stop]


def validate(patches: dict[str, str]) -> None:
    for name in ('site_common.py','sitebuild/afisha.py','sitebuild/posts.py'):
        ast.parse(patches[name], filename=name)
    # Validate pure JS modules and the new inline common JS with Node when installed.
    node = shutil.which('node')
    if node:
        js = [patches['opa-ui.js']]
        common = patches['site_common.py']
        js.append(extract_inline_js(common, 'CLOUD_JS = """<script>\n', '</script>"""'))
        afisha = patches['sitebuild/afisha.py']
        js.append(extract_inline_js(afisha, 'AFISHA_JS = """<script>\n', '</script>"""'))
        for index, code in enumerate(js):
            proc = subprocess.run([node, '--check'], input=code, text=True, capture_output=True)
            if proc.returncode:
                raise RuntimeError(f'Ошибка JS блока {index}: {proc.stderr}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    opt = parser.add_mutually_exclusive_group()
    opt.add_argument('--check', action='store_true', help='Проверить совместимость, ничего не менять')
    opt.add_argument('--apply', action='store_true', help='Применить с резервной копией')
    args = parser.parse_args()
    root = args.root.resolve()
    texts = {}
    for filename in FILES:
        path = root / filename
        if not path.is_file():
            raise RuntimeError(f'Не найден {filename}; запустите из корня проекта')
        texts[filename] = path.read_text(encoding='utf-8')
    already = [name for name in FILES if MARKER in texts[name]]
    if already and len(already) != len(FILES):
        raise RuntimeError('Пакет установлен частично: ' + ', '.join(already) + '. Ничего не изменено.')
    if len(already) == len(FILES):
        print('Все изменения уже установлены. Повторно применять не нужно.')
        return 0
    planned = {name: PATCHES[name](texts[name]) for name in FILES if name != 'docs/opa-ui.js'}
    # The public JS copy was older than the repository-root source. Publish the same version.
    planned['docs/opa-ui.js'] = planned['opa-ui.js']
    validate(planned)
    print(f'OK: {len(planned)} файлов совместимы, Python и JS синтаксис проверен.')
    if not args.apply:
        print('Режим проверки. Файлы проекта не изменены. Для применения: --apply')
        return 0
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = root.parent / ('OldPictureArt_backup_mobile_favorites_' + stamp)
    if backup.exists():
        raise RuntimeError('Папка резервной копии существует: ' + str(backup))
    # All anchors validated; backup before the first write.
    for name in FILES:
        dst = backup / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, dst)
    modified = []
    try:
        for name in FILES:
            (root / name).write_text(planned[name], encoding='utf-8', newline='\n')
            modified.append(name)
    except Exception:
        for name in modified:
            shutil.copy2(backup / name, root / name)
        raise
    print('Установлено. Резервная копия:', backup)
    for name in modified:
        print('  ', name)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, SyntaxError) as error:
        print('Ошибка:', error, file=sys.stderr)
        sys.exit(1)
