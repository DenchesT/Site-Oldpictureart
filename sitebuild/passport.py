# -*- coding: utf-8 -*-
"""Personal art passport: static public catalog only; private records in YDB."""
import logging
import os

from site_common import (AUTH_JS, BASE_URL, COMMON_JS, SCROLL_TOP_JS, TOAST_JS,
                         head_common, script_json, scroll_top_button, MAP_LAYERS_JS,
                         site_footer, theme_button, museum_page)
from .afisha import load_afisha, _afisha_favorites_script, _afisha_favorite_key
from .config import OUTPUT_DIR
from .places import museum_names, museum_directory, museum_info, LEAFLET_CSS, LEAFLET_JS
from .slugs import artist_slug
from .passport_ids import get_passport_id, registry_aliases, save_passport_registry

logger = logging.getLogger('build_site')


def passport_catalog(posts, visits):
    """Public metadata only: never access visitor tokens, visits or notes."""
    works = []
    for p in posts or []:
        if not p.get('id') or not p.get('filename'):
            continue
        thumb = (p.get('thumbs') or p.get('images') or [''])[0]
        works.append({
            'id': str(p['id']), 'title': str(p.get('title') or ''),
            'artist': str(p.get('artist') or ''),
            'museum': str(p.get('museum') or ''),
            'year': str(p.get('creation_year') or ''),
            'href': p['filename'], 'thumb': thumb,
        })
    artists = sorted({p['artist'].strip() for p in (posts or []) if p.get('artist')})
    names = museum_names(posts or [], visits or [])
    directory = museum_directory()
    catalog = {
        'works': works,
        'artists': [{'id': get_passport_id('artists', a), 'name': a, 'href': artist_slug(a)}
                    for a in artists],
        'museums': []
    }
    for m in names:
        info = museum_info(m, directory)
        catalog['museums'].append({
            'id': get_passport_id('museums', m), 'name': m,
            'href': museum_page(m), 'city': info.get('city') or '',
            'country': info.get('country') or '', 'address': info.get('address') or '',
            'lat': info.get('lat'), 'lon': info.get('lon'),
            'approx': bool(info.get('approx')),
        })
    catalog['aliases'] = registry_aliases()
    save_passport_registry()
    return catalog


def render_passport_page(posts, visits, exhibitions=None):
    catalog = passport_catalog(posts, visits)
    events = exhibitions if exhibitions is not None else load_afisha()[0]
    catalog['exhibitions'] = [{
        'id': str(it['id']), 'key': _afisha_favorite_key(it['id']),
        'title': str(it.get('title') or ''), 'venue': str(it.get('venue') or ''),
        'city': str(it.get('city') or ''), 'start': str(it.get('start') or ''),
        'end': str(it.get('end') or ''),
    } for it in events if it.get('id')]
    head = head_common(
        title='Мой арт-паспорт — Old Picture Art',
        description='Личный арт-паспорт: музейный дневник, увиденные оригиналы и коллекции.',
        canonical=f'{BASE_URL}/passport.html',
        extra='\n<meta name="robots" content="noindex, nofollow">',
    )
    payload = script_json(catalog, ensure_ascii=False)
    tabs = [('overview','Обзор'), ('visits','Дневник'), ('artists','Художники'),
            ('museums','Музеи'), ('originals','Оригиналы'), ('collections','Коллекции'),
            ('exhibitions','Выставки'), ('map','Карта'), ('timeline','Хронология'),
            ('stats','Статистика')]
    nav = ''.join('<button type="button" data-tab="'+key+'" aria-pressed="'+
                  ('true' if key=='overview' else 'false')+'">'+label+'</button>'
                  for key,label in tabs)
    return f'''<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
{LEAFLET_CSS}
<link rel="stylesheet" href="passport.css">
</head><body class="tag-page passport-page">
<a href="#passport-main" class="skip-link">К паспорту</a>
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> Галерея</a>
  <a href="afisha.html" class="back">Афиша</a>
  {theme_button('theme-toggle-inline')}
  <button type="button" id="auth-btn" class="topbar-btn ym-hide-content" title="Войти">Войти</button>
</div>
{scroll_top_button()}
<main id="passport-main" class="passport-main">
  <header class="passport-header">
    <div>
      <p class="eyebrow">Личная коллекция впечатлений</p>
      <h1>Мой арт-паспорт</h1>
      <p class="passport-intro">Любимые произведения, посещения музеев, увиденные оригиналы и коллекции — ваша личная история искусства.</p>
      <p class="passport-owner" id="passport-owner" aria-live="polite"></p>
    </div>
    <div class="passport-emblem" aria-hidden="true"><span>OPA</span><small>ART PASS</small></div>
  </header>
  <div class="passport-info passport-syncbar" id="passport-save-info" role="status" aria-live="polite">
    <span id="passport-sync-text">Загрузка статуса синхронизации…</span>
    <button type="button" id="passport-sync-button">Синхронизировать</button>
  </div>
  <section class="passport-stats" id="passport-stats" aria-label="Личная статистика"></section>
  <nav class="passport-tabs" aria-label="Разделы арт-паспорта">{nav}</nav>
  <section id="passport-panel" class="passport-panel" aria-live="polite"></section>
  <footer class="passport-tools">
    <p>Дневник ваших посещений не связан с <a href="visits.html">дневником автора сайта</a>. Просмотр карточки картины не засчитывается как встреча с оригиналом.</p>
    <div class="passport-tool-buttons">
      <button type="button" id="passport-export">Экспорт JSON</button>
      <label class="passport-import">Импорт JSON <input type="file" id="passport-import" accept="application/json,.json"></label>
    </div>
    <p class="passport-feedback" id="passport-feedback" role="status"></p>
  </footer>
</main>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{TOAST_JS}
{LEAFLET_JS}
<script src="vendor/leaflet.markercluster/leaflet.markercluster.js"></script>
<script src="map-config.js"></script>
<script>{MAP_LAYERS_JS}</script>
<script>window.OPA_PASSPORT_DATA={payload};</script>
{_afisha_favorites_script(events)}
{AUTH_JS}
<script src="passport-actions.js" defer></script>
<script src="passport.js" defer></script>
</body></html>'''


def generate_passport(posts, visits=None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    target = os.path.join(OUTPUT_DIR, 'passport.html')
    with open(target, 'w', encoding='utf-8', newline='\n') as f:
        f.write(render_passport_page(posts, visits or []))
    logger.info('Арт-паспорт: %s', target)
    return target


__all__ = ['passport_catalog', 'render_passport_page', 'generate_passport']
