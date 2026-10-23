# -*- coding: utf-8 -*-
"""Страницы музеев и вызов карты собраний.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
import re
import sys
import subprocess
import urllib.parse
from urllib.parse import quote
from collections import defaultdict
from html import escape as h
from site_common import (
    head_common, scroll_top_button, theme_button, site_footer, COMMON_JS, SCROLL_TOP_JS,
    BASE_URL, visit_organizers, museum_page, MAP_LAYERS_JS,
)
import logging
from .config import OUTPUT_DIR
from .text import plural_ru, slugify, typo_ru
from .slugs import artist_slug, retire_pages, surname_key
from .html import catalogue_numbers, jsonld_script, tidy, year_span
from .places import (
    LEAFLET_CSS, LEAFLET_JS, been_phrase_ru, museum_directory, museum_info, place_jsonld,
    prepare_museums, visit_map_names, visit_museum_names,
)
from .visits import RUN_STATUS_JS, visit_card, visit_sort_key
from .posts import card_html
from .afisha import MUSEUM_AFISHA_JS, load_afisha, museum_afisha_block

logger = logging.getLogger("build_site")

@tidy
def render_museum_page(name, works, been, info, all_posts, cat_no, cat_width, neighbours=(None, None),
                       away=(), afisha=()):
    """Страница одного собрания: картины, походы, адрес, сайт, карта.

    afisha — записи афиши с полем museum = name: блок «Сейчас в афише».
    """
    shown = typo_ru(name)          # имя для показа; name — ключ справочника и адрес страницы
    works = sorted(works, key=lambda x: (x.get("creation_year") or 9999, x.get("date", "")))
    been = sorted(been, key=visit_sort_key, reverse=True)
    cards = [card_html(p, cat_no, cat_width, show_museum=False) for p in works]
    artists = sorted({p["artist"].strip() for p in works if p.get("artist")}, key=surname_key)
    span = year_span(works)
    where = ", ".join(x for x in (info.get("city"), info.get("country")) if x)

    # Шапка — два блока, у каждого своя подпись, чтобы ни одна строка не
    # читалась двояко. Раньше «Сайт — museefabre.fr» стояло прямо над
    # «Работ на сайте — 3», и выходило «на сайте музея три работы?»;
    # «Художников — 2» не говорило, каких, а «Годы» — годы чего.
    #
    # «Адрес и сайт» — сам музей: адрес одной строкой (город и страна
    # в нём же, без отдельной строки «Где»), официальный сайт.
    address = (info.get("address") or "").strip()
    country = (info.get("country") or "").strip()
    about = []
    if address:
        if country and country.lower() not in address.lower():
            address += f", {country}"
        about.append(("Адрес", h(address)))
    elif where:
        about.append(("Где", h(where)))
    if info.get("site"):
        host = re.sub(r"^www\.", "", urllib.parse.urlsplit(info["site"]).netloc)
        about.append(("Официальный сайт",
                      f'<a href="{h(info["site"])}" target="_blank" rel="noopener">{h(host)} ↗</a>'))

    # «На этом сайте» — что из музея есть здесь: работы, чьи, каких лет,
    # и сколько раз я там был. Имена художников — ссылками, отдельного
    # списка внизу страницы больше нет.
    here = []
    if works:
        here.append(("Работ", str(len(works))))
    if artists:
        # Каждое имя — своей строкой: через запятую длинные имена рвались
        # посередине («Жан Дезире / Гюстав Курбе»).
        names = "".join(f'<a class="museum-artist" href="{h(artist_slug(a))}">{h(a)}</a>'
                        for a in artists)
        here.append(("Художник" if len(artists) == 1 else "Художники", names))
    if span:
        here.append(("Годы создания" if "—" in span else "Год создания", h(span)))
    if been:
        here.append(("Побывал", "однажды" if len(been) == 1
                     else f"{len(been)} {plural_ru(len(been), 'раз', 'раза', 'раз')}"))

    def table(rows):
        return ('<div class="spec-table artist-facts">'
                + "".join(f'<div><span>{h(k)}</span><b>{v}</b></div>' for k, v in rows) + '</div>')

    card_link = f"museums.html#museum-{h(slugify(name))}"
    has_map = info.get("lat") is not None and info.get("lon") is not None
    if has_map:
        lat, lon = info["lat"], info["lon"]
        ya = f"https://yandex.ru/maps/?pt={lon:.6f},{lat:.6f}&z=16&l=map"
        map_block = (
            '<div class="museum-map"><h2 class="museum-caption">На карте</h2>'
            f'<div class="mini-map" id="mini-map" data-lat="{lat:.6f}" data-lon="{lon:.6f}"'
            f'{" data-approx" if info.get("approx") else ""} role="img" '
            f'aria-label="{h(shown)} на карте"></div>'
            '<p class="mini-map-links">'
            + ('<span class="mini-map-note">Расположение приблизительное — по городу.</span> '
               if info.get("approx") else "")
            + f'<a href="{card_link}">Карта собраний</a> · '
            f'<a href="{h(ya)}" target="_blank" rel="noopener">Яндекс Карты ↗</a></p>'
            '</div>')
    else:
        # Координат нет — карточка на карте собраний всё равно есть,
        # в списке под картой, с адресом и сайтом.
        about.append(("На карте", f'<a href="{card_link}">Карточка на карте собраний</a>'))
        map_block = ""

    about_caption = ("Адрес и сайт" if address and info.get("site") else
                     "Адрес" if address else "Сайт" if info.get("site") else "Где")
    blocks = []
    if about:
        blocks.append(f'<div class="museum-about"><h2 class="museum-caption">{about_caption}</h2>'
                      f'{table(about)}</div>')
    if here:
        scope = ('<p class="museum-scope">Это не всё собрание музея — только работы, '
                 'которые есть на этом сайте.</p>') if works else ""
        blocks.append(f'<div class="museum-here"><h2 class="museum-caption">На этом сайте</h2>'
                      f'{table(here)}{scope}</div>')
    hero = (f'<div class="museum-hero{"" if map_block else " no-map"}">'
            + "".join(blocks) + map_block + '</div>')

    prev_name, next_name = neighbours
    nav = []
    if prev_name:
        nav.append(f'<a class="prev-post" href="{h(museum_page(prev_name))}">'
                   f'<span class="icon-prev" aria-hidden="true"></span> {h(typo_ru(prev_name))}</a>')
    if next_name:
        nav.append(f'<a class="next-post" href="{h(museum_page(next_name))}">'
                   f'{h(typo_ru(next_name))} <span class="icon-next" aria-hidden="true"></span></a>')
    nav_html = f'<nav class="post-nav">{"".join(nav)}</nav>' if nav else ""

    title = f"{shown} — Old Picture Art"
    if len(title) > 70:
        title = shown if len(shown) <= 70 else shown[:67].rsplit(" ", 1)[0] + "…"
    bits = []
    if works:
        bits.append(f"{len(works)} {plural_ru(len(works), 'работа', 'работы', 'работ')} в собрании Old Picture Art")
    if been:
        bits.append(been_phrase_ru(len(been)).lower())
    desc = f"{shown}: " + (", ".join(bits) if bits else "место на карте Old Picture Art") + "."
    if info.get("address"):
        desc += f" Адрес: {info['address']}."
    cover = (works[0].get("images") or [""])[0] if works else (been[0].get("images") or [""])[0] if been else ""

    ld = place_jsonld(info, "Museum")
    ld["@context"] = "https://schema.org"
    if cover:
        ld["image"] = f"{BASE_URL}/{quote(cover, safe='/')}"
    if info.get("site"):
        ld["sameAs"] = [info["site"]]
    ld["mainEntityOfPage"] = f"{BASE_URL}/{museum_page(name)}"

    head = head_common(
        title=h(title),
        description=desc,
        canonical=f"{BASE_URL}/{museum_page(name)}",
        og_image=f"{BASE_URL}/{cover}" if cover else "",
        extra="\n" + jsonld_script(ld) + ("\n" + LEAFLET_CSS if has_map else ""),
    )
    # Картины собрания, под ними — походы сюда теми же карточками, что в
    # разделе «Посещения». Что это не всё собрание музея, сказано в шапке.
    main = []
    # Выставки музея из афиши — над работами: это то, что можно увидеть
    # сейчас. Что идёт, решает браузер; нечего показать — блока не видно.
    now_html = museum_afisha_block(afisha)
    if now_html:
        main.append(now_html)
    if cards:
        main.append('<h2 class="museum-section">Работы</h2>'
                    f'<div class="grid list">{"".join(cards)}</div>')
    if been:
        main.append('<h2 class="museum-section">Походы</h2>'
                    f'<div class="grid list museum-visit-grid">'
                    f'{"".join(visit_card(v, show_place=False) for v in been)}</div>')
    # Выставки, которые музей делал вместе с другими и которые шли не у
    # него: «Митрополичье варенье» МРИ — в Ростовском кремле. На карте и в
    # походах они стоят там, где шли, а здесь — чтобы не потерялись.
    if away:
        away = sorted(away, key=lambda item: visit_sort_key(item[0]), reverse=True)
        here_city = info.get("city") or ""
        cities = [c or "" for _, _, c in away]
        heading = ("Выставки в других городах" if here_city and all(c and c != here_city for c in cities)
                   else "Выставки в других музеях")
        # Под названием — где шла (сам этот музей в строке места лишний).
        main.append(f'<h2 class="museum-section">{heading}</h2>'
                    f'<div class="grid list museum-visit-grid museum-away">'
                    f'{"".join(visit_card(v, place_text=venue) for v, venue, _ in away)}</div>')
    grid = '<div class="museum-main">' + "".join(main) + '</div>' if main else ""
    map_js = ""
    if has_map:
        # Подложки — те же, что на карте собраний, и так же по умолчанию
        # Яндекс (ключ в map-config.js), с переключателем в углу.
        map_js = LEAFLET_JS + '\n<script src="map-config.js"></script>\n<script>' + MAP_LAYERS_JS + """
(function () {
  var el = document.getElementById('mini-map');
  if (!el || !window.L) { if (el) el.hidden = true; return; }
  var lat = +el.getAttribute('data-lat'), lon = +el.getAttribute('data-lon');
  var approx = el.hasAttribute('data-approx');
  // Карта живая: колесо мыши приближает, пальцем двигается, двумя —
  // приближается. Высота у неё умеренная, так что страницу есть за что
  // прокрутить мимо карты.
  var map = L.map(el, {scrollWheelZoom: true, dragging: true})
    .setView([lat, lon], approx ? 11 : 15);
  OPA_MAP.attach(map, el);
  L.circleMarker([lat, lon], {radius: 9, weight: 3, className: 'mini-map-dot'}).addTo(map);
  el.miniMap = map;   // для проверок
})();
</script>"""
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page artist-page museum-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="museums.html" class="back">Карта собраний</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head museum-head">
  <p class="eyebrow">{"Собрание" if works else "Место"}</p>
  <h1>{h(shown)}</h1>
  {hero}
</header>
{grid}
{nav_html}
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{RUN_STATUS_JS if been else ""}
{MUSEUM_AFISHA_JS if now_html else ""}
{map_js}
</body></html>"""


def generate_museum_pages(all_posts, visits):
    """Страницы всех мест. Вызывать после карты: координаты берутся из её кэша."""
    names = prepare_museums(all_posts, visits)
    directory = museum_directory()
    cat_no, cat_width = catalogue_numbers(all_posts)
    by_museum = defaultdict(list)
    for p in all_posts:
        if p.get("museum"):
            by_museum[p["museum"].strip()].append(p)
    map_names = visit_map_names(visits, all_posts)
    by_place = defaultdict(list)
    for v in visits or []:
        key = map_names.get((v.get("place") or "").strip())
        if key:
            by_place[key].append(v)
    # Музеи-участники выставок, которые шли в другом месте.
    away = defaultdict(list)
    post_names = visit_museum_names(all_posts)
    for v in visits or []:
        place = (v.get("place") or "").strip()
        venue = map_names.get(place)
        for _, card in visit_organizers(place, post_names, map_names):
            if card and card != venue:
                away[card].append((v, venue or "", museum_info(venue, directory)["city"] if venue else ""))

    # Выставки из афиши по музеям (поле museum — точное название места).
    on_show = defaultdict(list)
    for it in load_afisha()[0]:
        if it.get("museum"):
            on_show[it["museum"].strip()].append(it)

    ordered = sorted(names, key=lambda n: n.lower())
    seen = {}
    for i, name in enumerate(ordered):
        fn = museum_page(name)
        if fn in seen:
            logger.warning(f"Страница музея {fn}: одинаковый адрес у «{seen[fn]}» и «{name}»")
        seen[fn] = name
        neighbours = (ordered[i - 1] if i > 0 else None,
                      ordered[i + 1] if i < len(ordered) - 1 else None)
        html = render_museum_page(name, by_museum.get(name, []), by_place.get(name, []),
                                  museum_info(name, directory), all_posts, cat_no, cat_width,
                                  neighbours, away.get(name, ()), on_show.get(name, ()))
        with open(os.path.join(OUTPUT_DIR, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
    moved, removed = retire_pages("museum-", set(seen), {})
    logger.info(f"Страниц музеев: {len(seen)}" + (f", убрано прежних: {removed}" if removed else ""))
    return seen

def generate_museums_page(all_posts):
    """Генерирует карту музеев через отдельный скрипт."""
    logger.info("Генерация карты музеев...")
    try:
        subprocess.run([sys.executable, "generate_map.py"], check=True)
        logger.info("Карта собраний сгенерирована")
    except Exception as e:
        logger.error(f"Ошибка генерации карты: {e}")

__all__ = [
    'render_museum_page',
    'generate_museum_pages',
    'generate_museums_page',
]
