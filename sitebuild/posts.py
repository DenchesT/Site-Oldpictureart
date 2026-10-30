# -*- coding: utf-8 -*-
"""Страницы картин, подборки по тегам и главная страница.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
import re
import json
from collections import defaultdict
from html import escape as h
from site_common import (
    head_common, scroll_top_button, theme_button, site_footer, TELEGRAM_URL, TELEGRAM_NAME,
    hires_url, COMMON_JS, SCROLL_TOP_JS, LUPA_JS, TOAST_JS, SHARE_JS, AUTH_JS, CLOUD_JS,
    BASE_URL, has_visits, VISITS_FILE,
)
import logging
from .config import OUTPUT_DIR
from .text import load_json, lower_first, plural_ru, slugify, typo_ru
from .slugs import artist_slug, retire_pages, surname_key, tag_slug
from .links import clean_links, source_block, source_items
from .html import artwork_jsonld, download_name, page_title, site_og_image, telegram_post_link, tidy
from .images import size_attrs
from .places import museum_href
from .visits import NOW_ON_JS, now_on_block
from .afisha import AFISHA_JS, afisha_block, load_afisha

logger = logging.getLogger("build_site")

@tidy
def render_post_page(post, all_posts=None):
    artist, title = h(post["artist"]), h(post["title"])
    title_plain = post.get("title") or ""
    desc = post.get("description") or ""
    urls = post.get("urls") or ([post["url"]] if post.get("url") else [])
    cover_image = post['images'][0] if post.get('images') else ''
    post_id = str(post.get("id", ""))

    parts = []
    hl = post.get("hires", [])
    views = post.get("views") or []
    for i, src in enumerate(post["images"]):
        lh = hires_url(hl[i] if i < len(hl) else src)
        # Первая картина — главный элемент страницы (LCP): грузим её сразу,
        # остальные ленимся. Раньше lazy стоял на всех, включая первую.
        loading = 'fetchpriority="high" decoding="async"' if i == 0 else 'loading="lazy" decoding="async"'
        # Ссылка на оригинал остаётся настоящей: без JS она откроет файл, как
        # раньше, а со скриптом клик перехватывает лупа. data-* нужны ей для
        # подписи — лезть за ними в разметку страницы не приходится.
        # Год в подписи лупы повторялся: он и так стоит в конце названия
        # («…, 1832»), а на телефоне подпись и без того длинная.
        year = str(post.get("creation_year") or "")
        meta_bits = [x for x in (("" if year and year in title_plain else year),
                                 post.get("museum") or "") if x]
        # data-view — то, что грузит лупа: копия до 2000 пикселей. Ссылка
        # остаётся на оригинал: и без JS, и по Ctrl+клик, и кнопкой «скачать»
        # человек получает файл таким, каким он пришёл из канала. Адрес копии
        # не переписывается под HIRES_BASE_URL: в хранилище уезжают только
        # оригиналы, всё остальное остаётся рядом с сайтом.
        vw = views[i] if i < len(views) else ""
        parts.append(
            f'<a href="{h(lh)}" class="painting-link" target="_blank" rel="noopener" '
            + (f'data-view="{h(vw)}" ' if vw else '')
            + f'title="Рассмотреть" data-title="{artist} — {title}" data-meta="{h(", ".join(meta_bits))}" '
            f'data-download="{h(download_name(post, lh))}">'
            f'<img src="{h(src)}" alt="{artist} — {title}" class="painting"{size_attrs(src)} {loading}>'
            f'<span class="painting-hint" aria-hidden="true">'
            f'<span class="icon-lupa" aria-hidden="true"></span> Рассмотреть</span></a>'
        )
    img_html = "\n".join(parts)

    # Сведения о работе — отдельной таблицей в правой колонке: в каталоге
    # это главный справочный блок, а не строчка под заголовком.
    spec_rows = [
        ("Год", str(post.get("creation_year")) if post.get("creation_year") else ""),
        ("Материал", lower_first(post.get("material", ""))),
        ("Техника", ", ".join(post.get("techniques", []))),
        ("Размер", post.get("size", "")),
    ]
    spec_html = '<div class="spec-table">' + "".join(
        f'<div><span>{h(k)}</span><b>{h(v)}</b></div>' for k, v in spec_rows if v)
    if post.get("museum"):
        # Собрание — ссылка на страницу музея (там и карта), а у частных
        # собраний, у которых своей страницы нет, — на карточку на карте
        spec_html += (f'<div><span>Собрание</span><b><a href="{h(museum_href(post["museum"]))}">'
                      f'{h(typo_ru(post["museum"]))}</a></b></div>')
    spec_html += '</div>'

    tags_html = ""
    if post["tags"]:
        tags_html = '<div class="tags">' + " ".join(f'<a href="tag-{h(tag_slug(t))}.html" class="tag">#{h(t)}</a>' for t in post["tags"]) + "</div>"
    tags_block = f'<div class="aside-block"><h3>Теги</h3>{tags_html}</div>' if tags_html else ""

    desc_html = ""
    if desc:
        paras = "".join(f"<p>{h(typo_ru(p))}</p>" for p in desc.split("\n\n") if p.strip())
        desc_html = f'<section class="description">{paras}</section>'

    hist = post.get("history") or post.get("note") or ""
    if isinstance(hist, str): hist = [s.strip() for s in re.split(r"⸻|\n", hist) if s.strip()]
    hist_html = ""
    if hist:
        # В канале пункты пронумерованы руками: «1) Приобретена…». В <ul>
        # это давало точку и номер сразу — нумерует теперь сам список.
        numbered = all(re.match(r"\d+[).]\s", s) for s in hist)
        if numbered:
            hist = [re.sub(r"^\d+[).]\s+", "", s) for s in hist]
        its = "".join(f"<li>{h(typo_ru(s))}</li>" for s in hist)
        tag = "ol" if numbered else "ul"
        hist_html = f'<section class="history"><h3>Происхождение</h3><{tag}>{its}</{tag}></section>'

    # Источники: ссылки, спрятанные под словами поста (с их подписью), и
    # голые адреса из текста. Раньше были видны только вторые.
    src_block = source_block(source_items(clean_links(post.get("links")), urls))

    # Prev/Next навигация
    prev_link = ""
    next_link = ""
    if all_posts:
        sorted_posts = sorted(all_posts, key=lambda x: x["date"])
        current_idx = next((i for i, p in enumerate(sorted_posts) if p.get("id") == post.get("id")), -1)
        if current_idx > 0:
            prev_post = sorted_posts[current_idx - 1]
            prev_link = f'<a href="{h(prev_post["filename"])}" class="prev-post" title="{h(prev_post["artist"])} — {h(prev_post["title"])}"><span class="icon-prev"></span> Предыдущая</a>'
        if current_idx < len(sorted_posts) - 1 and current_idx != -1:
            next_post = sorted_posts[current_idx + 1]
            next_link = f'<a href="{h(next_post["filename"])}" class="next-post" title="{h(next_post["artist"])} — {h(next_post["title"])}">Следующая <span class="icon-next"></span></a>'
    post_nav = f'<nav class="post-nav">{prev_link}{next_link}</nav>' if (prev_link or next_link) else ""

    # Скачать работу. Это ссылка, а не кнопка: атрибут download отдаёт файл
    # напрямую, работает без JS и не мешает «сохранить как» из меню правой
    # кнопки. Файлы лежат на том же домене, иначе download браузер игнорирует.
    download_src = hires_url(hl[0] if hl else (post["images"][0] if post.get("images") else ""))
    download_btn = ""
    if download_src:
        download_btn = (f'<a href="{h(download_src)}" download="{h(download_name(post, download_src))}" '
                        f'class="topbar-btn" aria-label="Скачать картину" title="Скачать картину">'
                        f'<span class="icon-download" aria-hidden="true"></span></a>')

    # «Рядом в собрании»: после описания человек упирался в тупик, хотя
    # у того же художника и в том же музее есть что показать.
    similar_block = similar_html(post, all_posts) if all_posts else ""
    artist_link = (f'<a href="{h(artist_slug(post["artist"]))}">{artist}</a>'
                   if post.get("artist") else artist)

    page_desc = (desc[:200] if desc else f"{post.get('artist','')} — {post.get('title','')}. {post.get('museum','')}").strip()
    head = head_common(
        title=h(page_title(post)),
        description=page_desc,
        og_image=f"{BASE_URL}/{post.get('card') or cover_image}" if (post.get('card') or cover_image) else "",
        canonical=f"{BASE_URL}/{post.get('filename','')}",
        og_type="article",
        extra="\n" + artwork_jsonld(post),
    )

    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="post-page">
<a href="#main" class="skip-link">К содержанию</a>
<div class="post-topbar">
  <a href="./" class="topbar-back"><span class="icon-back" aria-hidden="true"></span> Галерея</a>
  <div class="post-topbar-right">
    <button type="button" onclick="goRandom()" class="topbar-btn" aria-label="Случайная картина" title="Случайная картина"><span class="icon-random" aria-hidden="true"></span></button>
    <button type="button" data-share-btn onclick="sharePage(this)" class="topbar-btn" aria-label="Поделиться" title="Поделиться" aria-haspopup="menu"><span class="icon-share" aria-hidden="true"></span></button>
    {download_btn}
    <button type="button" id="like-btn" data-post-id="{post_id}" onclick="toggleLike()" class="topbar-btn topbar-like" aria-pressed="false" aria-label="В избранное" title="В избранное"><span class="icon-heart" aria-hidden="true"></span><span class="like-count" id="like-count" hidden></span></button>
    <button type="button" class="topbar-btn" data-theme-toggle onclick="toggleTheme()" aria-label="Переключить тему" title="Светлая / тёмная тема"><span class="icon-theme-toggle" aria-hidden="true"></span></button>
    <button type="button" id="auth-btn" class="topbar-btn ym-hide-content" title="Войти"><span class="icon-login" aria-hidden="true"></span> Войти</button>
  </div>
</div>
{scroll_top_button()}
<article id="main" class="post-layout">
  <div class="post-main">
    <header class="post-head">
      <h1>{artist_link}</h1>
      <h2>{title}</h2>
    </header>
    {img_html}
    <div class="color-palette" id="color-palette"></div>
    {desc_html}
    {hist_html}
  </div>
  <aside class="post-aside">
    {spec_html}
    {src_block}
    {tags_block}
    <div class="aside-block">
      <h3>Запись</h3>
      <time>{h(post['date'])}</time><span class="views-count" id="views-count"></span>
      {telegram_post_link(post)}
    </div>
  </aside>
</article>
{similar_block}
{post_nav}
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{LUPA_JS}
{TOAST_JS}
{SHARE_JS}
<script src="vendor/color-thief/color-thief.umd.js" defer></script>
<script>
// ---------- Палитра цветов ----------
// Раньше палитра вешалась только на событие load: если картинка бралась из
// кэша, load уже прошёл и палитра не появлялась никогда. Теперь проверяем
// img.complete, а сам скрипт ждём через window load (color-thief стоит defer).
(function() {{
    function buildPalette() {{
        var img = document.querySelector('.painting');
        var container = document.getElementById('color-palette');
        if (!img || !container || !window.ColorThief) return;
        try {{
            var palette = new ColorThief().getPalette(img, 5);
            if (!palette) return;
            palette.forEach(function(color) {{
                var hex = '#' + color.map(function(c) {{ return c.toString(16).padStart(2, '0'); }}).join('');
                var swatch = document.createElement('button');
                swatch.type = 'button';
                swatch.className = 'palette-swatch';
                swatch.style.background = hex;
                swatch.title = hex + ' — скопировать';
                swatch.setAttribute('aria-label', 'Скопировать цвет ' + hex);
                swatch.addEventListener('click', function() {{
                    var self = this;
                    function flash() {{
                        self.classList.add('copied');
                        setTimeout(function() {{ self.classList.remove('copied'); }}, 700);
                    }}
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                        navigator.clipboard.writeText(hex).then(flash).catch(function() {{ flash(); }});
                    }} else {{ flash(); }}
                }});
                container.appendChild(swatch);
            }});
        }} catch (e) {{ /* картинка с другого домена или ещё не декодирована */ }}
    }}
    function start() {{
        var img = document.querySelector('.painting');
        if (!img) return;
        if (img.complete && img.naturalWidth) buildPalette();
        else img.addEventListener('load', buildPalette, {{once: true}});
    }}
    if (document.readyState === 'complete') start();
    else window.addEventListener('load', start);
}})();

// ---------- Случайная картина ----------
// Список страниц кладёт главная. Если человек пришёл сразу на карточку и
// списка нет — раньше кнопка молча не работала, теперь уводим на главную.
function goRandom() {{
    var p = [];
    try {{ p = JSON.parse(localStorage.getItem('allPosts') || '[]'); }} catch (e) {{}}
    if (p && p.length) location.href = p[Math.floor(Math.random() * p.length)];
    else location.href = './?random=1';
}}

// ---------- Счётчик просмотров (локальный) ----------
(function() {{
    try {{
        var key = window.location.pathname;
        var views = JSON.parse(localStorage.getItem('pageViews') || '{{}}');
        views[key] = (views[key] || 0) + 1;
        localStorage.setItem('pageViews', JSON.stringify(views));
        var el = document.getElementById('views-count');
        if (el) {{
            el.innerHTML = '<span class="icon-views" aria-hidden="true"></span> ';
            el.appendChild(document.createTextNode(views[key]));
            el.title = 'Вы открывали эту страницу ' + views[key] + ' раз(а)';
        }}
    }} catch (e) {{}}
}})();

// ---------- Локальное состояние лайка ----------
// Раньше «сердечко» подсвечивалось только после входа в аккаунт: без входа
// лайк ставился, но после перезагрузки кнопка снова была пустой.
(function() {{
    try {{
        var btn = document.getElementById('like-btn');
        if (!btn) return;
        var likes = JSON.parse(localStorage.getItem('likes') || '{{}}');
        var on = !!likes[btn.dataset.postId];
        btn.classList.toggle('liked', on);
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }} catch (e) {{}}
}})();

// ---------- Горячие клавиши ----------
document.addEventListener('keydown', function(e) {{
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target;
    // не мешаем набору текста в полях (форма входа)
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    var k = e.key;
    if (k === 'r' || k === 'к') goRandom();
    else if (k === 'h' || k === 'р') window.location.href = './';
    else if (k === 't' || k === 'е') toggleTheme();
    else if (k === 'Escape') {{
        var m = document.querySelector('.auth-modal-overlay');
        if (m) m.remove();
    }}
    else if (k === 'ArrowLeft') {{
        var p = document.querySelector('.prev-post');
        if (p) p.click();
    }}
    else if (k === 'ArrowRight') {{
        var n = document.querySelector('.next-post');
        if (n) n.click();
    }}
}});
</script>
{AUTH_JS}
</body></html>"""

def card_html(p, cat_no=None, cat_width=3, show_artist=True, show_museum=True):
    """Карточка работы в описи. Одна на все списки — главную, теги,
    страницы художников: раньше разметка была скопирована и разъезжалась.

    show_artist=False — для страницы художника: там его имя стоит в
    заголовке и повторять его в каждой строке незачем, поэтому главной
    строкой карточки становится название работы. show_museum=False — для
    страницы музея: там собрание в заголовке, и в каждой строке оно лишнее."""
    cat_no = cat_no or {}
    cv = ""
    if p.get("thumbs"): cv = p["thumbs"][0]
    elif p.get("images"): cv = p["images"][0]
    cv = h(cv)
    museum_name = h(typo_ru(p.get('museum', '')))
    artist_name = h(p["artist"])
    title_name = h(p["title"])
    # Экранированные кавычки внутри f-строки требуют Python 3.12+,
    # на 3.11 это была синтаксическая ошибка. Собираем строку заранее.
    museum_html = (f'<div class="card-museum"><a href="{h(museum_href(p.get("museum", "")))}"'
                   f' title="Все картины этого собрания">{museum_name}</a></div>') if museum_name and show_museum else ''
    no = cat_no.get(p.get("filename"))
    no_html = f'<span class="card-no">{no:0{cat_width}d}</span>' if no else '<span class="card-no"></span>'
    facts = [("Год", str(p.get("creation_year")) if p.get("creation_year") else ""),
             ("Материал", lower_first(p.get("material", ""))),
             ("Техника", ", ".join(p.get("techniques", []))),
             ("Размер", p.get("size", ""))]
    facts_html = "".join(f'<div><span>{h(k)}</span><b>{h(v)}</b></div>' for k, v in facts if v)
    head_line = artist_name if show_artist else title_name
    sub_line = f'<div class="card-title">{title_name}</div>' if show_artist else ''
    return (
        f'<article class="card">{no_html}'
        f'<a class="card-img" href="{h(p["filename"])}" aria-label="Открыть картину: {artist_name} — {title_name}"><img src="{cv}" alt="{artist_name} — {title_name}"{size_attrs(cv)} loading="lazy" decoding="async"></a>'
        f'<div class="card-body">'
        f'<div class="card-artist"><a class="card-link" href="{h(p["filename"])}">{head_line}</a></div>'
        f'{sub_line}{museum_html}</div>'
        f'<div class="card-facts">{facts_html}</div></article>'
    )


@tidy
def render_tag_page(tag, posts, cat_no=None, cat_width=3):
    """cat_no — сквозные каталожные номера всего собрания: на странице тега
    номер должен остаться тем же, что и на главной, иначе он ничего не значит."""
    newest = sorted(posts, key=lambda x: x["date"], reverse=True)
    cards = [card_html(p, cat_no, cat_width) for p in newest]
    # Превью ссылки — карточка самой свежей работы подборки (1200×630, как
    # у страницы работы); без неё ссылка на тег в мессенджере была голым текстом.
    cover = next((p.get("card") or p["images"][0] for p in newest if p.get("card") or p.get("images")), "")
    head = head_common(
        title=f"#{h(tag)} — Old Picture Art",
        description=f"Картины по тегу #{tag} — подборка из {len(posts)} работ в галерее Old Picture Art.",
        canonical=f"{BASE_URL}/tag-{tag_slug(tag)}.html",
        og_image=f"{BASE_URL}/{cover}" if cover else "",
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<h1>#{h(tag)} <span class="tag-count">({len(posts)})</span></h1>
<div class="grid list">{''.join(cards)}</div>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
</body></html>"""

@tidy
def render_index(all_posts, visits=None):
    MONTHS = {"01":"Январь","02":"Февраль","03":"Март","04":"Апрель","05":"Май","06":"Июнь","07":"Июль","08":"Август","09":"Сентябрь","10":"Октябрь","11":"Ноябрь","12":"Декабрь"}
    ps = sorted(all_posts, key=lambda x: x["date"], reverse=True)
    
    authors = sorted({p["artist"] for p in ps if p.get("artist")}, key=surname_key)
    museums = sorted({p.get("museum","") for p in ps if p.get("museum")})
    ms, ts = set(), set()
    for p in ps:
        if p.get("material"): ms.add(p["material"])
        for t in p.get("techniques",[]):
            if t and len(t)>2: ts.add(t)
    materials, techniques = sorted(ms), sorted(ts)
    
    archive = defaultdict(set)
    archive_count = defaultdict(int)
    for p in ps:
        if p.get("date") and "-" in p["date"]:
            y, m, _ = p["date"].split("-")
            archive[y].add(m)
            archive_count[y] += 1
    ars = {y: sorted(list(m), reverse=True) for y, m in sorted(archive.items(), reverse=True)}
    
    creation_years = []
    for p in ps:
        cy = p.get("creation_year")
        if cy: creation_years.append(cy)
    decades = {}
    for y in creation_years:
        d_start = y // 10 * 10
        d_label = f"{d_start}–{d_start+9}"
        decades[d_label] = decades.get(d_label, 0) + 1
    decades_sorted = sorted(decades.keys())
    
    year_range = f"{min(creation_years)}–{max(creation_years)}" if creation_years else ""
    
    # Каталожный номер закреплён за работой навсегда: он показывает место
    # в хронологии собрания, а не позицию в текущей сортировке.
    chrono = sorted(ps, key=lambda x: (x.get("creation_year") or 9999, x.get("date", "")))
    cat_no = {id(x): i for i, x in enumerate(chrono, 1)}
    cat_width = max(3, len(str(len(ps))))

    cards = []
    for p in ps:
        cv = ""
        if p.get("thumbs"): cv = p["thumbs"][0]
        elif p.get("images"): cv = p["images"][0]
        cv = h(cv)
        y, m = "", ""
        if p.get("date") and "-" in p["date"]: y, m, _ = p["date"].split("-")
        decade_attr = ""
        creation_year = p.get("creation_year")
        if creation_year:
            d_start = creation_year // 10 * 10
            decade_attr = f'data-decade="{d_start}–{d_start+9}"'
        artist_name = h(p['artist'])
        title_name = h(p['title'])
        museum_name = h(typo_ru(p.get('museum', '')))

        # Дата публикации
        pub_date = p.get('date', '')[:10] if p.get('date') else ''

        # data-search собирает всё, по чему ищем: раньше поиск шёл по
        # видимому тексту карточки, а названия картины в нём нет — искать
        # по названию было невозможно.
        search_blob = " ".join(filter(None, [
            p.get('artist', ''), p.get('title', ''), p.get('museum', ''),
            p.get('material', ''), " ".join(p.get('techniques', [])),
            " ".join(p.get('tags', [])), pub_date,
        ])).lower()

        # Сведения о работе: в описи это столбец таблицы, в плитках —
        # строчка через точку. Разметка одна, раскладку задаёт CSS.
        facts = [("Год", str(creation_year) if creation_year else ""),
                 ("Материал", lower_first(p.get('material', ''))),
                 ("Техника", ", ".join(p.get('techniques', []))),
                 ("Размер", p.get('size', ''))]
        facts_html = "".join(
            f'<div><span>{h(k)}</span><b>{h(v)}</b></div>' for k, v in facts if v)

        # Карточка — <article>, а не <a>: внутри должна быть вторая ссылка,
        # на музей, а ссылку в ссылку вкладывать нельзя. Вся карточка всё
        # равно кликабельна — за счёт растянутой на неё .card-link.
        museum_slug = slugify(p.get('museum', ''))
        museum_html = (f'<div class="card-museum"><a href="{h(museum_href(p.get("museum", "")))}"'
                       f' title="Все картины этого собрания">{museum_name}</a></div>') if museum_name else ''

        cards.append(f"""<article class="card" data-artist="{h(p['artist'].lower())}" data-title="{h(p['title'].lower())}" data-year="{y}" data-month="{m}" data-cyear="{creation_year or ''}" data-museum="{h(museum_slug)}" data-material="{h(slugify(p.get('material','')))}" data-techniques="{h(' '.join(slugify(t) for t in p.get('techniques',[])))}" data-search="{h(search_blob)}" data-no="{cat_no[id(p)]}" {decade_attr}>
    <span class="card-no" title="Номер работы в каталоге">{cat_no[id(p)]:0{cat_width}d}</span>
    <a class="card-img" href="{h(p['filename'])}" aria-label="Открыть картину: {artist_name} — {title_name}"><img src="{cv}" alt="{artist_name} — {title_name}"{size_attrs(cv)} loading="lazy" decoding="async"></a>
    <div class="card-body">
        <div class="card-artist"><a class="card-link" href="{h(p['filename'])}">{artist_name}</a></div>
        <div class="card-title"><a class="opa-card-title-link" href="{h(p['filename'])}" aria-label="Открыть картину: {artist_name} — {title_name}">{title_name}</a></div>
        {museum_html}
        <div class="card-date">{pub_date}</div>
    </div>
    <div class="card-facts">{facts_html}</div>
    </article>""")
    
    artist_count = defaultdict(int)
    museum_count = defaultdict(int)
    material_count = defaultdict(int)
    technique_count = defaultdict(int)
    for p in ps:
        if p.get("artist"): artist_count[p["artist"]] += 1
        if p.get("museum"): museum_count[p["museum"]] += 1
        if p.get("material"): material_count[p["material"]] += 1
        for t in p.get("techniques",[]):
            if t and len(t)>2: technique_count[t] += 1
    
    ah = "".join(f'<li><a href="#" class="filter-link" data-type="artist" data-val="{h(a.lower())}">{h(a)} <span class="count">({artist_count[a]})</span></a></li>' for a in authors)
    mh = "".join(f'<li><a href="#" class="filter-link" data-type="museum" data-val="{h(slugify(m))}">{h(typo_ru(m))} <span class="count">({museum_count[m]})</span></a></li>' for m in museums if m)
    # Материал в базе записан с заглавной («Холст»), техника — со строчной
    # («масло»). В списке фильтров они стоят рядом, поэтому приводим
    # к одному виду: со строчной, как принято в описании работы.
    mth = "".join(f'<li><a href="#" class="filter-link" data-type="material" data-val="{h(slugify(m))}">{h(lower_first(m))} <span class="count">({material_count[m]})</span></a></li>' for m in materials)
    th = "".join(f'<li><a href="#" class="filter-link" data-type="technique" data-val="{h(slugify(t))}">{h(t)} <span class="count">({technique_count[t]})</span></a></li>' for t in techniques)
    # Годы: строка на десятилетие, полоса показывает, сколько работ. Раньше
    # это были столбики гистограммы шириной в восемнадцать пикселей — пальцем
    # в такой не попасть, а на сенсорных экранах читают чаще, чем мышью.
    # Строки устроены как соседние разделы сайдбара и как страница статистики,
    # так что это не новый элемент, а тот же самый. Поля «от / до» под списком
    # задают точный диапазон, подпись словами говорит, что сейчас выбрано.
    hist_max = max(decades.values()) if decades else 1
    bars = []
    for d in decades_sorted:
        start = int(d.split("–")[0])
        n = decades.get(d, 0)
        pct = round(n / hist_max * 100)
        word = plural_ru(n, "работа", "работы", "работ")
        bars.append(
            f'<li><button type="button" class="dec-row" data-decade="{start}" style="--w:{pct}%" '
            f'aria-pressed="false" title="{h(d)} — {n} {word}" aria-label="{h(d)}, {n} {word}">'
            f'<span class="dec-year">{start}-е</span>'
            f'<span class="dec-track"><span class="dec-fill"></span></span>'
            f'<span class="dec-n">{n}</span></button></li>'
        )
    decade_starts = [int(d.split("–")[0]) for d in decades_sorted]
    opts_from = "".join(f'<option value="{v}">{v}</option>' for v in decade_starts)
    opts_to = "".join(f'<option value="{v + 9}">{v + 9}</option>' for v in decade_starts)
    dech = f'''<div class="year-filter">
      <ul class="dec-list" id="year-hist">{''.join(bars)}</ul>
      <div class="year-range">
        <label class="visually-hidden" for="year-from">Год от</label>
        <select id="year-from" class="year-select"><option value="">любой</option>{opts_from}</select>
        <span class="year-dash">—</span>
        <label class="visually-hidden" for="year-to">Год до</label>
        <select id="year-to" class="year-select"><option value="">любой</option>{opts_to}</select>
      </div>
      <p class="year-caption" id="year-caption" role="status" aria-live="polite"></p>
    </div>'''
    
    arh = ""
    for y, ms_list in ars.items():
        arh += f'<li><a href="#" class="filter-link" data-type="year" data-val="{y}"><b>{y} год</b> <span class="count">({archive_count[y]})</span></a><ul class="month-list">'
        for mn in ms_list: arh += f'<li><a href="#" class="filter-link" data-type="month" data-year="{y}" data-val="{mn}">{MONTHS.get(mn,mn)}</a></li>'
        arh += '</ul></li>'
    
    af = json.dumps([p["filename"] for p in ps])
    post_map_data = {
        str(p.get("id", "")): {"file": p["filename"], "title": p.get("title", f"Картина #{p.get('id', '')}"),
                               "artist": p.get("artist", ""),
                               "thumb": (p.get("thumbs") or p.get("images") or [""])[0]}
        for p in ps if p.get("id")
    }
    pm_js = json.dumps(post_map_data, ensure_ascii=False)
    
    # Разделы сайдбара. Заголовки-«аккордеоны» теперь настоящие <button>:
    # раньше это были <div onclick>, недоступные с клавиатуры и для скринридеров.
    empty_fav = ('<li class="fav-empty">Нажмите <span class="icon-heart" aria-hidden="true"></span>'
                 ' на странице картины</li>')
    fav_html = ('<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon icon-fav" '
                'aria-expanded="false" onclick="toggleSection(this)">Избранное '
                '<span id="fav-count" class="count"></span></button>'
                f'<div class="sidebar-content collapsed"><ul id="fav-list">{empty_fav}</ul></div></div>')
    # «Популярное у посетителей» — рядом с «Избранным»: то же по сути,
    # только отметки чужие. Раздел появляется, когда список пришёл из
    # облака; пока отмеченных картин мало, в сайдбаре ничего не висит.
    # Свёрнут, как и «Избранное»: список длинный и заслонял бы остальное меню.
    popular_html = ('<div class="sidebar-section" id="popular" hidden>'
                    '<button type="button" class="sidebar-title sidebar-icon icon-popular" '
                    'aria-expanded="false" onclick="toggleSection(this)">Популярное '
                    '<span id="popular-count" class="count"></span></button>'
                    '<div class="sidebar-content collapsed"><ul id="popular-list"></ul></div></div>')
    theme_html = ('<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon icon-theme no-arrow" '
                  'data-theme-toggle aria-pressed="false" onclick="toggleTheme()">Тема</button></div>')
    quiz_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-quiz no-arrow" '
                      'href="quiz.html">Квиз</a></div>')
    timeline_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-timeline no-arrow" '
                          'href="timeline.html">Хронология</a></div>')
    map_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-map no-arrow" '
                     'href="museums.html">Карта собраний</a></div>')
    # Посещения появляются в меню только когда в канале нашлись
    # посты #выставка или #галерея — пустой раздел никому не нужен.
    visits_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-visits no-arrow" '
                        'href="visits.html">Посещения</a></div>') if has_visits() else ''
    # Афиша — крупные выставки в России и в мире (sitebuild/afisha.py):
    # раздел в панели под фильтрами — ссылка и ближайшие к закрытию.
    afisha_html = afisha_block(load_afisha()[0])
    index_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-artists no-arrow" '
                       'href="ukazatel.html">Указатель</a></div>')
    stats_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-decades no-arrow" '
                       'href="stats.html">Статистика</a></div>')
    # Канал — источник всего собрания, поэтому он в том же ряду, что карта
    # и указатель, а не мелкой строкой где-то внизу.
    tg_link_html = (f'<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-tg no-arrow" '
                    f'href="{TELEGRAM_URL}" target="_blank" rel="noopener">Канал</a></div>')
    
    head = head_common(
        title="Old Picture Art — Галерея",
        og_image=site_og_image(all_posts),
        description=(f"Галерея из {len(ps)} картин: {len(authors)} художников, {len(museums)} музеев. "
                     "Поиск по художникам, музеям, технике и десятилетиям."),
        canonical=f"{BASE_URL}/",
    )

    now_block = now_on_block(visits if visits is not None else load_json(VISITS_FILE, []), all_posts)

    def section(icon, label, content):
        return (f'<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon {icon}" '
                f'aria-expanded="false" onclick="toggleSection(this)">{label}</button>'
                f'<div class="sidebar-content collapsed"><ul>{content}</ul></div></div>')

    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="index-page">
<a href="#cards" class="skip-link">К галерее</a>
<button type="button" class="menu-toggle" id="menu-toggle" onclick="toggleMenu()" aria-expanded="false" aria-controls="sidebar"><span class="icon-menu" aria-hidden="true"></span> Меню</button>
<div class="overlay" id="overlay" onclick="toggleMenu()" aria-hidden="true" hidden></div>
{scroll_top_button()}
<header>
<div class="head-text">
<h1><span class="icon-logo" aria-hidden="true"></span> Old Picture Art</h1>
<p class="site-lede">Собрание живописи из музеев мира. У каждой работы указаны автор, год, материал, размер и место, где она сейчас, а любую картину можно скачать в высоком разрешении. Пополняется из телеграм-канала <a href="{TELEGRAM_URL}" target="_blank" rel="noopener">{TELEGRAM_NAME}</a>.</p>
<div class="subtitle">{len(ps)} {plural_ru(len(ps), 'картина', 'картины', 'картин')} · {len(authors)} {plural_ru(len(authors), 'художник', 'художника', 'художников')} · {len(museums)} {plural_ru(len(museums), 'музей', 'музея', 'музеев')} · {year_range}</div>
</div>
<button type="button" class="random-btn" onclick="goRandom()"><span class="icon-random-white" aria-hidden="true"></span> Случайная картина</button></header>
{('<details class="opa-now-collapsible"><summary>Мои посещения · текущие выставки</summary>' + now_block + '</details>') if now_block else ''}
<div class="layout"><aside class="sidebar" id="sidebar" aria-label="Фильтры">
<div class="sidebar-section sidebar-search">
  <label class="opa-search-label" for="search">Поиск картин</label>
  <div class="opa-search-wrap">
    <input type="search" class="search-box" placeholder="Художник, название, музей…" id="search" autocomplete="off" aria-describedby="opa-search-help">
    <button type="button" class="opa-search-clear" id="opa-clear-search" title="Очистить поиск" aria-label="Очистить поиск" hidden>×</button>
  </div>
  <p class="opa-search-help" id="opa-search-help">Поиск по названию, автору и музею · клавиша /</p>
</div>
<button type="button" id="reset-filter" class="filter-reset">Сбросить все фильтры</button>
<p class="opa-sidebar-heading">Фильтры картин</p>
{section('icon-archive', 'Архив', arh)}
<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon icon-decades" aria-expanded="false" onclick="toggleSection(this)">Годы</button><div class="sidebar-content collapsed">{dech}</div></div>
{section('icon-artists', 'Художники', ah)}
{section('icon-museums', 'Музеи', mh)}
{section('icon-material', 'Материал', mth)}
{section('icon-technique', 'Техника', th)}
<p class="opa-sidebar-heading">Выставки и подборки</p>
{afisha_html}
{fav_html}
{popular_html}
<p class="opa-sidebar-heading">Разделы сайта</p>
{map_link_html}
{visits_link_html}
{index_link_html}
{stats_link_html}
{tg_link_html}
{quiz_link_html}
{timeline_link_html}
{theme_html}
</aside><main class="main-content">
<div class="results-bar">
  <div class="opa-results-meta">
    <span id="results-count" class="results-count" role="status" aria-live="polite"></span>
    <button type="button" id="opa-reset-inline" class="opa-reset-inline" onclick="resetAllFilters()" hidden>Сбросить фильтры</button>
  </div>
  <div class="bar-controls">
  <span class="bar-label" id="sort-label">Сортировка</span>
  <label class="visually-hidden" for="sort">Сортировка картин</label>
  <select id="sort" class="sort-select" aria-labelledby="sort-label">
    <option value="new">Недавно добавленные</option>
    <option value="cyear">По году картины: ранние</option>
    <option value="cyear-desc">По году картины: поздние</option>
    <option value="artist">По художнику</option>
    <option value="title">По названию</option>
  </select>
  <div class="view-switch" role="group" aria-label="Вид списка">
    <button type="button" id="view-list" aria-pressed="true" onclick="setView('list')">Подробный список</button>
    <button type="button" id="view-grid" aria-pressed="false" onclick="setView('grid')">Карточки</button>
  </div>
  </div>
</div>
<div class="active-filter-chips" id="opa-active-filters" aria-label="Выбранные фильтры" hidden></div>
<div class="grid list" id="cards">{''.join(cards)}</div>
<p class="no-results" id="no-results" hidden>Ничего не найдено. Попробуйте изменить запрос или <button type="button" class="linklike" onclick="resetAllFilters()">сбросить фильтры</button>.</p>
</main></div>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{NOW_ON_JS}
{AFISHA_JS}
<script>
const ALL_POSTS = {af};
const POSTS_DATA = {pm_js};

try {{ localStorage.setItem('allPosts', JSON.stringify(ALL_POSTS)); }} catch (e) {{}}

function goRandom() {{
    if (ALL_POSTS.length) location.href = ALL_POSTS[Math.floor(Math.random() * ALL_POSTS.length)];
}}

// Переход с карточки: «случайная картина» без сохранённого списка ведёт сюда
if (location.search.indexOf('random=1') !== -1 && ALL_POSTS.length) {{
    location.replace(ALL_POSTS[Math.floor(Math.random() * ALL_POSTS.length)]);
}}

// Опись или плитки. Выбор запоминается: разметка одна, меняется только
// класс контейнера, поэтому фильтры и поиск продолжают работать как были.
function setView(mode) {{
    const grid = document.getElementById('cards');
    if (!grid) return;
    grid.classList.toggle('list', mode === 'list');
    const l = document.getElementById('view-list'), g = document.getElementById('view-grid');
    if (l) l.setAttribute('aria-pressed', mode === 'list' ? 'true' : 'false');
    if (g) g.setAttribute('aria-pressed', mode === 'grid' ? 'true' : 'false');
    try {{ localStorage.setItem('cardView', mode); }} catch (e) {{}}
}}

(function () {{
    let saved = null;
    try {{ saved = localStorage.getItem('cardView'); }} catch (e) {{}}
    if (saved === 'grid') document.addEventListener('DOMContentLoaded', function () {{ setView('grid'); }});
}})();

function updateFavList() {{
    let likes = {{}};
    try {{ likes = JSON.parse(localStorage.getItem('likes') || '{{}}'); }} catch (e) {{}}
    const favList = document.getElementById('fav-list');
    const favCount = document.getElementById('fav-count');
    if (!favList) return;
    const likedIds = Object.keys(likes).filter(id => likes[id]);
    if (favCount) favCount.textContent = likedIds.length ? '(' + likedIds.length + ')' : '';
    favList.textContent = '';
    if (!likedIds.length) {{
        const li = document.createElement('li');
        li.className = 'fav-empty';
        li.innerHTML = 'Нажмите <span class="icon-heart" aria-hidden="true"></span> на странице картины';
        favList.appendChild(li);
        return;
    }}
    likedIds.forEach(id => {{
        const info = POSTS_DATA[id];
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = info ? info.file : '#';
        a.title = info ? info.title : ('Картина #' + id);
        // textContent, а не innerHTML: названия картин приходят из данных
        a.innerHTML = '<span class="icon-painting-small" aria-hidden="true"></span> ';
        a.appendChild(document.createTextNode(info ? info.title : ('Картина #' + id)));
        li.appendChild(a);
        favList.appendChild(li);
    }});
}}

// Аккордеон сайдбара: класс open нужен, чтобы стрелка ▾ поворачивалась —
// раньше он не ставился нигде и стрелка всегда смотрела вниз.
function toggleSection(el) {{
    const content = el.nextElementSibling;
    if (!content) return;
    const willOpen = content.classList.contains('collapsed');
    content.classList.toggle('collapsed', !willOpen);
    el.classList.toggle('open', willOpen);
    el.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
}}

function toggleMenu(force) {{
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');
    const btn = document.getElementById('menu-toggle');
    if (!sidebar) return;
    const open = typeof force === 'boolean' ? force : !sidebar.classList.contains('open');
    sidebar.classList.toggle('open', open);
    if (overlay) {{ overlay.classList.toggle('visible', open); overlay.hidden = !open; }}
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}}

function isMobile() {{ return window.matchMedia('(max-width: 900px)').matches; }}

let activeFilters = {{ search: '', type: null, val: null, year: null, from: null, to: null }};

function resetAllFilters() {{
    activeFilters = {{ search: '', type: null, val: null, year: null, from: null, to: null }};
    const searchBox = document.getElementById('search');
    if (searchBox) searchBox.value = '';
    const searchClear = document.getElementById('opa-clear-search');
    if (searchClear) searchClear.hidden = true;
    document.querySelectorAll('.filter-link.active').forEach(l => {{
        l.classList.remove('active');
        l.removeAttribute('aria-current');
    }});
    const f = document.getElementById('year-from'), t = document.getElementById('year-to');
    if (f) f.value = ''; if (t) t.value = '';
    syncHistogram();
    applyFilters();
}}

// Подсветка столбиков и подпись под гистограммой. Выбор показан не только
// цветом: под столбиками стоит строка словами.
function syncHistogram() {{
    const from = activeFilters.from, to = activeFilters.to;
    document.querySelectorAll('.dec-row').forEach(b => {{
        const d = +b.dataset.decade;
        const on = (from === null && to === null) ||
                   ((from === null || d + 9 >= from) && (to === null || d <= to));
        b.classList.toggle('dim', !(from === null && to === null) && !on);
        b.setAttribute('aria-pressed', (from !== null || to !== null) && on ? 'true' : 'false');
    }});
    const cap = document.getElementById('year-caption');
    if (!cap) return;
    if (from === null && to === null) cap.textContent = 'Все годы';
    else if (from !== null && to !== null) cap.textContent = from + '—' + to;
    else if (from !== null) cap.textContent = 'с ' + from;
    else cap.textContent = 'по ' + to;
}}

function setYearRange(from, to) {{
    activeFilters.from = from;
    activeFilters.to = to;
    const f = document.getElementById('year-from'), t = document.getElementById('year-to');
    if (f) f.value = from === null ? '' : String(from);
    if (t) t.value = to === null ? '' : String(to);
    syncHistogram();
    applyFilters();
}}

// Порядок записей. Каталожные номера при этом не пересчитываются:
// номер закреплён за работой и показывает её место в хронологии собрания.
function sortCards(mode) {{
    const grid = document.getElementById('cards');
    if (!grid) return;
    const cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
    const byText = (a, b, key) => (a.dataset[key] || '').localeCompare(b.dataset[key] || '', 'ru');
    const year = el => parseInt(el.dataset.cyear, 10) || 0;
    cards.sort((a, b) => {{
        if (mode === 'cyear') return year(a) - year(b) || byText(a, b, 'artist');
        if (mode === 'cyear-desc') return year(b) - year(a) || byText(a, b, 'artist');
        if (mode === 'artist') return byText(a, b, 'artist') || year(a) - year(b);
        if (mode === 'title') return byText(a, b, 'title');
        return (+b.dataset.no) - (+a.dataset.no) === 0 ? 0 : 0;  // «сначала новые» — исходный порядок
    }});
    if (mode === 'new') {{
        cards.sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));
    }}
    const frag = document.createDocumentFragment();
    cards.forEach(c => frag.appendChild(c));
    grid.appendChild(frag);
    try {{ localStorage.setItem('cardSort', mode); }} catch (e) {{}}
}}

let ORDER = [];

function applyFilters() {{
    const cards = document.querySelectorAll('.card');
    let visible = 0;
    cards.forEach(card => {{
        let show = true;
        if (activeFilters.search) {{
            const blob = card.dataset.search || card.textContent.toLowerCase();
            if (blob.indexOf(activeFilters.search) === -1) show = false;
        }}
        if (show && (activeFilters.from !== null || activeFilters.to !== null)) {{
            const cy = parseInt(card.dataset.cyear, 10);
            if (!cy) show = false;
            else if (activeFilters.from !== null && cy < activeFilters.from) show = false;
            else if (activeFilters.to !== null && cy > activeFilters.to) show = false;
        }}
        if (show && activeFilters.type) {{
            const t = activeFilters.type, v = activeFilters.val;
            if (t === 'artist') show = card.dataset.artist === v;
            else if (t === 'museum') show = card.dataset.museum === v;
            else if (t === 'material') show = card.dataset.material === v;
            else if (t === 'technique') show = (card.dataset.techniques || '').split(' ').indexOf(v) !== -1;
            else if (t === 'decade') show = card.dataset.decade === v;
            else if (t === 'year') show = card.dataset.year === v;
            else if (t === 'month') show = card.dataset.year === activeFilters.year && card.dataset.month === v;
        }}
        card.hidden = !show;
        if (show) visible++;
    }});

    const hasActive = !!(activeFilters.search || activeFilters.type ||
                         activeFilters.from !== null || activeFilters.to !== null);
    const resetBtn = document.getElementById('reset-filter');
    if (resetBtn) resetBtn.classList.toggle('visible', hasActive);

    const counter = document.getElementById('results-count');
    if (counter) counter.textContent = 'Найдено ' + visible + ' ' + plural(visible, 'картина', 'картины', 'картин');
    const resetInline = document.getElementById('opa-reset-inline');
    if (resetInline) resetInline.hidden = !hasActive;

    const empty = document.getElementById('no-results');
    if (empty) empty.hidden = visible !== 0;
    document.dispatchEvent(new CustomEvent('opa:filters-changed'));
}}

function plural(n, one, few, many) {{
    const n10 = n % 10, n100 = n % 100;
    if (n10 === 1 && n100 !== 11) return one;
    if (n10 >= 2 && n10 <= 4 && (n100 < 10 || n100 >= 20)) return few;
    return many;
}}

document.addEventListener('DOMContentLoaded', function() {{
    updateFavList();

    // Исходный порядок запоминаем один раз — к нему возвращает «сначала новые»
    ORDER = Array.prototype.slice.call(document.querySelectorAll('#cards .card'));

    const sortSel = document.getElementById('sort');
    if (sortSel) {{
        let savedSort = null;
        try {{ savedSort = localStorage.getItem('cardSort'); }} catch (e) {{}}
        if (savedSort && [...sortSel.options].some(o => o.value === savedSort)) {{
            sortSel.value = savedSort;
            sortCards(savedSort);
        }}
        sortSel.addEventListener('change', function () {{ sortCards(this.value); }});
    }}

    // Клик по строке — это десятилетие целиком
    document.querySelectorAll('.dec-row').forEach(bar => {{
        bar.addEventListener('click', function () {{
            const d = +this.dataset.decade;
            if (activeFilters.from === d && activeFilters.to === d + 9) setYearRange(null, null);
            else setYearRange(d, d + 9);
        }});
    }});

    const yf = document.getElementById('year-from'), yt = document.getElementById('year-to');
    [yf, yt].forEach(el => {{
        if (!el) return;
        el.addEventListener('change', function () {{
            let from = yf && yf.value ? +yf.value : null;
            let to = yt && yt.value ? +yt.value : null;
            if (from !== null && to !== null && from > to) {{ const x = from; from = to; to = x; }}
            setYearRange(from, to);
        }});
    }});
    syncHistogram();

    const searchBox = document.getElementById('search');
    const clearSearch = document.getElementById('opa-clear-search');
    if (searchBox) {{
        if (clearSearch) {{
            clearSearch.hidden = !searchBox.value.trim();
            clearSearch.addEventListener('click', function () {{
                searchBox.value = '';
                searchBox.dispatchEvent(new Event('input', {{bubbles: true}}));
                searchBox.focus();
            }});
        }}
        let t = null;
        searchBox.addEventListener('input', function(e) {{
            const v = e.target.value.toLowerCase().trim();
            if (clearSearch) clearSearch.hidden = !e.target.value.trim();
            clearTimeout(t);
            // debounce: 195 карточек пересчитывать на каждую букву незачем
            t = setTimeout(function() {{ activeFilters.search = v; applyFilters(); }}, 120);
        }});
    }}

    document.querySelectorAll('.filter-link').forEach(link => {{
        link.addEventListener('click', function(e) {{
            e.preventDefault();
            const same = this.classList.contains('active');
            document.querySelectorAll('.filter-link.active').forEach(l => {{
                l.classList.remove('active');
                l.removeAttribute('aria-current');
            }});
            if (same) {{
                // повторный клик по тому же фильтру — снимаем его
                activeFilters.type = activeFilters.val = activeFilters.year = null;
            }} else {{
                this.classList.add('active');
                this.setAttribute('aria-current', 'true');
                activeFilters.type = this.dataset.type;
                activeFilters.val = this.dataset.val;
                activeFilters.year = this.dataset.year || null;
            }}
            applyFilters();
            // на телефоне меню перекрывает результат — закрываем его
            if (isMobile()) toggleMenu(false);
            document.getElementById('cards').scrollIntoView({{block: 'start', behavior: 'auto'}});
        }});
    }});

    // Из указателя сюда ведут ссылки вида index.html#mat-холст. Без разбора
    // якоря такой переход просто открывал главную без всякого фильтра.
    function applyHashFilter() {{
        const raw = (location.hash || '').replace(/^#/, '');
        const cut = raw.indexOf('-');
        if (cut < 1) return;
        const kind = {{mat: 'material', tech: 'technique', artist: 'artist', museum: 'museum'}}[raw.slice(0, cut)];
        if (!kind) return;
        let val = raw.slice(cut + 1);
        try {{ val = decodeURIComponent(val); }} catch (e) {{}}
        const link = [...document.querySelectorAll('.filter-link')]
            .find(l => l.dataset.type === kind && l.dataset.val === val);
        if (!link) return;
        const section = link.closest('.sidebar-section');
        const body = section && section.querySelector('.sidebar-content');
        if (body && body.classList.contains('collapsed')) section.querySelector('.sidebar-title').click();
        link.click();
    }}
    applyHashFilter();
    window.addEventListener('hashchange', applyHashFilter);

    const resetBtn = document.getElementById('reset-filter');
    if (resetBtn) resetBtn.addEventListener('click', function(e) {{ e.preventDefault(); resetAllFilters(); }});

    document.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') {{
            if (document.getElementById('sidebar').classList.contains('open')) toggleMenu(false);
            else if (document.activeElement === searchBox && searchBox.value) resetAllFilters();
        }}
        if (e.key === '/' && document.activeElement !== searchBox) {{
            e.preventDefault();
            if (isMobile()) toggleMenu(true);
            if (searchBox) searchBox.focus();
        }}
    }});

    applyFilters();
}});
</script>
{CLOUD_JS}
<script>
// Вошедшему в аккаунт — отметки из облака в список «Избранное».
cloudSync().then(function (changed) {{ if (changed) updateFavList(); }});

// «Популярное у посетителей»: самые отмечаемые картины. Функция отдаёт
// только номера картин и числа — кто отмечал, в ответе нет. Блок
// появляется, когда отмеченных картин набралось хотя бы три: полка из
// одной картины выглядела бы случайной.
if (CLOUD.on) cloudCall('top', {{limit: 6}}).then(function (j) {{
  var items = (j.top || []).filter(function (x) {{ return POSTS_DATA[x[0]]; }});
  if (items.length < 3) return;
  var list = document.getElementById('popular-list');
  items.forEach(function (x) {{
    var info = POSTS_DATA[x[0]], n = x[1];
    var li = document.createElement('li');
    var a = document.createElement('a');
    a.href = info.file;
    a.className = 'popular-link';
    a.title = info.artist ? info.artist + ' — ' + info.title : info.title;
    if (info.thumb) {{
      var img = document.createElement('img');
      img.src = info.thumb; img.alt = ''; img.loading = 'lazy'; img.decoding = 'async';
      img.width = 34; img.height = 34;
      a.appendChild(img);
    }}
    var name = document.createElement('span');
    name.className = 'popular-name';
    name.textContent = info.title;
    a.appendChild(name);
    var cnt = document.createElement('span');
    cnt.className = 'popular-count count';
    cnt.innerHTML = '<span class="icon-heart" aria-hidden="true"></span> ';
    cnt.appendChild(document.createTextNode(n));
    var hidden = document.createElement('span');
    hidden.className = 'visually-hidden';
    hidden.textContent = ' — добавили в избранное';
    cnt.appendChild(hidden);
    a.appendChild(cnt);
    li.appendChild(a);
    list.appendChild(li);
  }});
  document.getElementById('popular-count').textContent = '(' + items.length + ')';
  document.getElementById('popular').hidden = false;
}}).catch(function () {{}});
</script><script src="opa-ui.js" defer></script>
</body></html>"""


def similar_works(post, all_posts, limit=6):
    """Похожие работы: сначала тот же художник, затем то же собрание,
    затем то же десятилетие. Считается при сборке, на странице ничего
    не ищется — поэтому блок ничего не стоит посетителю.
    """
    me = post.get("filename")
    picked, seen = [], {me}

    def take(candidates, why):
        for p in candidates:
            if len(picked) >= limit:
                return
            fn = p.get("filename")
            if not fn or fn in seen:
                continue
            seen.add(fn)
            picked.append((p, why))

    by_date = sorted(all_posts, key=lambda x: x.get("date", ""), reverse=True)

    artist = (post.get("artist") or "").strip()
    if artist:
        take([p for p in by_date if (p.get("artist") or "").strip() == artist], "того же художника")

    museum = (post.get("museum") or "").strip()
    if museum and not museum.lower().startswith("частная"):
        take([p for p in by_date if (p.get("museum") or "").strip() == museum], "из того же собрания")

    year = post.get("creation_year")
    if year:
        lo = (int(year) // 10) * 10
        take([p for p in by_date
              if p.get("creation_year") and lo <= int(p["creation_year"]) < lo + 10],
             f"{lo}-х годов")

    return picked


def similar_html(post, all_posts):
    """Блок «Рядом в собрании» в конце страницы картины."""
    items = similar_works(post, all_posts)
    if not items:
        return ""
    cards = []
    for p, why in items:
        cv = ""
        if p.get("thumbs"):
            cv = p["thumbs"][0]
        elif p.get("images"):
            cv = p["images"][0]
        # Когда работа попала в подборку «за десятилетие», год уже назван
        # в самой причине — второй раз его писать незачем.
        year = "" if why.endswith("-х годов") else str(p.get("creation_year") or "")
        cards.append(
            f'<a class="near-card" href="{h(p["filename"])}">'
            f'<span class="near-img"><img src="{h(cv)}" alt="{h(p["artist"])} — {h(p["title"])}"{size_attrs(cv)} '
            f'loading="lazy" decoding="async"></span>'
            f'<span class="near-body">'
            f'<span class="near-artist">{h(p["artist"])}</span>'
            f'<span class="near-title">{h(p["title"])}</span>'
            f'<span class="near-why">{h(why)}{" · " + year if year else ""}</span>'
            f'</span></a>'
        )
    return ('<section class="near"><h3>Рядом в собрании</h3>'
            '<div class="near-grid">' + "".join(cards) + '</div></section>')


def generate_tag_pages(all_posts):
    logger.info("Генерация страниц тегов...")
    tp = defaultdict(list)
    for p in all_posts:
        for t in p.get("tags",[]): tp[t].append(p)
    chrono = sorted(all_posts, key=lambda x: (x.get("creation_year") or 9999, x.get("date", "")))
    cat_no = {x["filename"]: i for i, x in enumerate(chrono, 1)}
    cat_width = max(3, len(str(len(all_posts))))
    c = 0
    for tag, posts in tp.items():
        with open(os.path.join(OUTPUT_DIR, f"tag-{tag_slug(tag)}.html"), "w", encoding="utf-8") as f:
            f.write(render_tag_page(tag, posts, cat_no, cat_width))
        c += 1

    # Страницы тегов, которых в собрании больше нет, надо убирать.
    # Исправили опечатку в посте — и tag-freidrich.html остаётся лежать
    # навсегда: на него никто не ссылается, в карте сайта его нет, но
    # поисковик, раз его увидев, будет ходить по нему годами и показывать
    # людям пустой раздел.
    live = {f"tag-{tag_slug(t)}.html" for t in tp}
    legacy = {f"tag-{t}.html": f"tag-{tag_slug(t)}.html" for t in tp}
    moved, removed = retire_pages("tag-", live, legacy)
    if moved:
        logger.info(f"Прежних адресов тегов оставлено перенаправлениями: {moved}")
    if removed:
        logger.info(f"Убрано страниц исчезнувших тегов: {removed}")

    logger.info(f"Сгенерировано {c} страниц тегов")
    return tp

__all__ = [
    'render_post_page',
    'card_html',
    'render_tag_page',
    'render_index',
    'similar_works',
    'similar_html',
    'generate_tag_pages',
]
