# -*- coding: utf-8 -*-
"""Личный арт-паспорт: статическая страница поверх существующего каталога.

Генератор использует только публичные метаданные. Личные данные пользователей
хранятся отдельно в YDB, через авторизованную облачную функцию.
"""
import logging
import os
from html import escape as h

from site_common import (AUTH_JS, BASE_URL, COMMON_JS, SCROLL_TOP_JS, TOAST_JS,
                         head_common, script_json, scroll_top_button,
                         site_footer, theme_button, museum_page)
from .afisha import load_afisha, _afisha_favorites_script
from .config import OUTPUT_DIR
from .places import museum_names
from .slugs import artist_slug
from .text import typo_ru

logger = logging.getLogger('build_site')


def passport_catalog(posts, visits):
    """Only public catalogue metadata, never authentication or visitor data."""
    works = []
    for p in posts or []:
        if not p.get('id') or not p.get('filename'):
            continue
        thumb = (p.get('thumbs') or p.get('images') or [''])[0]
        works.append({
            'id': str(p['id']),
            'title': str(p.get('title') or ''),
            'artist': str(p.get('artist') or ''),
            'museum': str(p.get('museum') or ''),
            'year': str(p.get('creation_year') or ''),
            'href': p['filename'],
            'thumb': thumb,
        })
    artists = sorted({p['artist'].strip() for p in (posts or []) if p.get('artist')})
    museums = museum_names(posts or [], visits or [])
    return {
        'works': works,
        'artists': [{'name': a, 'href': artist_slug(a)} for a in artists],
        'museums': [{'name': m, 'href': museum_page(m)} for m in museums],
    }


def render_passport_page(posts, visits, exhibitions=None):
    catalog = passport_catalog(posts, visits)
    events = exhibitions if exhibitions is not None else load_afisha()[0]
    head = head_common(
        title='Мой арт-паспорт — Old Picture Art',
        description='Личный арт-паспорт: любимые художники, коллекции картин, посещённые музеи и увиденные оригиналы.',
        canonical=f'{BASE_URL}/passport.html',
        extra='\n<meta name="robots" content="noindex, nofollow">',
    )
    # script_json escapes '<' to stop JSON from closing its <script>.
    payload = script_json(catalog, ensure_ascii=False)
    return f'''<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
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
      <p class="passport-intro">Ваши любимые художники, картины, посещённые музеи и оригиналы, которые вы видели вживую. Заполняется только вашими отметками.</p>
      <p class="passport-owner" id="passport-owner" aria-live="polite"></p>
    </div>
    <div class="passport-emblem" aria-hidden="true"><span>OPA</span><small>ART PASS</small></div>
  </header>
  <p class="passport-info" id="passport-save-info">Гостевой режим сохраняет данные в браузере. После входа личные отметки, коллекции, лайки картин и выставок синхронизируются с аккаунтом. Экспорт JSON остаётся резервной копией.</p>
  <section class="passport-stats" id="passport-stats" aria-label="Личная статистика" aria-live="polite"></section>
  <div class="passport-tabs" role="group" aria-label="Разделы арт-паспорта">
    <button type="button" data-tab="overview" aria-pressed="true">Обзор</button>
    <button type="button" data-tab="artists" aria-pressed="false">Художники</button>
    <button type="button" data-tab="museums" aria-pressed="false">Музеи</button>
    <button type="button" data-tab="originals" aria-pressed="false">Оригиналы</button>
    <button type="button" data-tab="collections" aria-pressed="false">Коллекции</button>
  </div>
  <section id="passport-panel" class="passport-panel" aria-live="polite"></section>
  <footer class="passport-tools">
    <p>Ваши отметки о посещении музеев не зависят от <a href="visits.html">дневника посещений автора сайта</a>. Просмотр страницы картины сам по себе не означает, что вы видели оригинал.</p>
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
