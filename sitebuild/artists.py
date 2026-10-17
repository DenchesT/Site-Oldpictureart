# -*- coding: utf-8 -*-
"""Страницы художников, указатель и статистика.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
from collections import defaultdict, Counter
from html import escape as h
from site_common import (
    head_common, scroll_top_button, theme_button, site_footer, COMMON_JS, SCROLL_TOP_JS,
    BASE_URL,
)
import logging
from .config import OUTPUT_DIR
from .text import lower_first, plural_ru, slugify
from .slugs import artist_slug, retire_pages, surname_key
from .html import catalogue_numbers, jsonld_script, site_og_image, tidy, year_span
from .places import museum_href
from .posts import card_html

from .artist_info import artists_years, life_years, resolve as resolve_artist_info, wiki_host

logger = logging.getLogger("build_site")

@tidy
def render_artist_page(artist, posts, all_posts, cat_no, cat_width, info=None):
    """Страница художника: все его работы, годы, собрания.

    Раньше художник был только значением фильтра на главной — такую
    подборку нельзя было послать ссылкой и её не видел поиск.
    """
    works = sorted(posts, key=lambda x: (x.get("creation_year") or 9999, x.get("date", "")))
    cards = [card_html(p, cat_no, cat_width, show_artist=False) for p in works]

    museums = sorted({p["museum"].strip() for p in works if p.get("museum")})
    techs = sorted({t for p in works for t in p.get("techniques", []) if t})
    mats = sorted({p["material"] for p in works if p.get("material")})
    span = year_span(works)

    # Годы жизни и статья в Википедии — из Wikidata (artist_info.py).
    # «Годы» без пояснения читались двояко, поэтому «Годы работ».
    info = info or {}
    lived = life_years(info)
    wiki = info.get("wikipedia") or ""
    facts = []
    if lived:
        facts.append(("Годы жизни", h(lived)))
    if span:
        facts.append(("Годы работ", h(span)))
    facts.append(("Работ на сайте", str(len(works))))
    if mats:
        facts.append(("Материал", h(", ".join(lower_first(m) for m in mats))))
    if techs:
        facts.append(("Техника", h(", ".join(techs))))
    if wiki:
        facts.append(("Википедия", f'<a href="{h(wiki)}" target="_blank" rel="noopener">{h(wiki_host(wiki))} ↗</a>'))
    facts_html = "".join(f'<div><span>{h(k)}</span><b>{v}</b></div>' for k, v in facts)

    # Разметка для поисковиков: человек, годы, ссылки на Википедию и Wikidata.
    person = {"@context": "https://schema.org", "@type": "Person", "name": artist,
              "url": f"{BASE_URL}/{artist_slug(artist)}"}
    if info.get("born"):
        person["birthDate"] = str(info["born"])
    if info.get("died"):
        person["deathDate"] = str(info["died"])
    same = [x for x in (wiki, f"https://www.wikidata.org/wiki/{info['wikidata']}" if info.get("wikidata") else "") if x]
    if same:
        person["sameAs"] = same

    museum_html = ""
    if museums:
        items = "".join(
            f'<li><a href="{h(museum_href(m))}">{h(m)}</a></li>' for m in museums)
        museum_html = (f'<div class="aside-block"><h3>Собрания</h3>'
                       f'<ul class="plain-list">{items}</ul></div>')

    # Соседи по алфавиту — по фамилии, как в описи
    names = sorted({p["artist"].strip() for p in all_posts if p.get("artist")}, key=surname_key)
    pos = names.index(artist) if artist in names else -1
    nav = []
    if pos > 0:
        nav.append(f'<a class="prev-post" href="{h(artist_slug(names[pos-1]))}">'
                   f'<span class="icon-prev" aria-hidden="true"></span> {h(names[pos-1])}</a>')
    if 0 <= pos < len(names) - 1:
        nav.append(f'<a class="next-post" href="{h(artist_slug(names[pos+1]))}">'
                   f'{h(names[pos+1])} <span class="icon-next" aria-hidden="true"></span></a>')
    nav_html = f'<nav class="post-nav">{"".join(nav)}</nav>' if nav else ""

    page_title = f"{artist} — Old Picture Art"
    if len(page_title) > 70:
        page_title = artist
    if len(page_title) > 70:
        page_title = page_title[:67].rsplit(" ", 1)[0] + "…"

    word = plural_ru(len(works), "работа", "работы", "работ")
    desc = (f"{artist}" + (f" ({lived})" if lived else "") + f": {len(works)} {word} в собрании Old Picture Art"
            + (f", {span}." if span else "."))
    head = head_common(
        # длинные имена не влезают в выдачу поисковика: сначала убираем
        # название сайта, а совсем длинные (у одной записи в авторах
        # перечислено одиннадцать человек) подрезаем по слову.
        title=h(page_title),
        description=desc,
        canonical=f"{BASE_URL}/{artist_slug(artist)}",
        og_image=f"{BASE_URL}/{works[0]['images'][0]}" if works and works[0].get("images") else "",
        extra="\n" + jsonld_script(person),
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page artist-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="ukazatel.html" class="back">Указатель</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head">
  <p class="eyebrow">Художник</p>
  <h1>{h(artist)}</h1>
  <div class="spec-table artist-facts">{facts_html}</div>
</header>
<div class="artist-layout">
  <div class="grid list">{''.join(cards)}</div>
  <aside class="post-aside">{museum_html}</aside>
</div>
{nav_html}
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
</body></html>"""


@tidy
def render_ukazatel(all_posts, info=None):
    """Указатель: художники, собрания, материал и техника по алфавиту.

    Всё это было спрятано в раскрывающихся разделах сайдбара — с телефона
    туда не добраться одним взглядом, а для каталога это обязательная часть.
    """
    artists = defaultdict(list)
    museums = defaultdict(list)
    techs = defaultdict(list)
    mats = defaultdict(list)
    for p in all_posts:
        if p.get("artist"):
            artists[p["artist"].strip()].append(p)
        if p.get("museum"):
            museums[p["museum"].strip()].append(p)
        for t in p.get("techniques", []):
            if t and len(t) > 2:
                techs[lower_first(t.strip())].append(p)
        if p.get("material"):
            mats[lower_first(p["material"].strip())].append(p)

    def letter(name):
        ch = (name or "?")[:1].upper()
        return ch if ch.isalpha() else "#"

    def column(title, data, href, key=None, anchor="", note=None):
        """Список с группировкой по первой букве и числом работ.
        note — приписка к имени (у художников — годы жизни)."""
        items = sorted(data.items(), key=lambda kv: (key(kv[0]) if key else kv[0].lower()))
        out, cur = [], None
        for name, posts in items:
            first = letter(key(name).upper() if key else name)
            if first != cur:
                cur = first
                out.append(f'<li class="idx-letter" aria-hidden="true">{h(cur)}</li>')
            link = href(name)
            n = len(posts)
            extra = note(name) if note else ""
            extra_html = f' <span class="idx-years">{h(extra)}</span>' if extra else ""
            out.append(f'<li><a href="{h(link)}">{h(name)}</a>{extra_html}<span class="idx-n">{n}</span></li>')
        return (f'<section class="idx-col" id="{anchor}"><h2>{h(title)} '
                f'<span class="idx-total">{len(items)}</span></h2>'
                f'<ul class="idx-list">{"".join(out)}</ul></section>')

    body = "".join([
        column("Художники", artists, artist_slug, key=surname_key, anchor="hudozhniki",
               note=lambda a: life_years((info or {}).get(a))),
        column("Собрания", museums, museum_href, anchor="sobraniya"),
        column("Материал", mats, lambda m: f"./#mat-{slugify(m)}", anchor="material"),
        column("Техника", techs, lambda t: f"./#tech-{slugify(t)}", anchor="tehnika"),
    ])

    head = head_common(
        title="Указатель — Old Picture Art",
        og_image=site_og_image(all_posts),
        description=(f"Художники, собрания и техники коллекции Old Picture Art "
                     f"по алфавиту: {len(artists)} художников, {len(museums)} собраний."),
        canonical=f"{BASE_URL}/ukazatel.html",
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page index-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="stats.html" class="back">Статистика</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head">
  <p class="eyebrow">Собрание</p>
  <h1>Указатель</h1>
  <p class="idx-lede">Всё, что есть в каталоге, по алфавиту и с числом работ.</p>
</header>
<div class="idx-grid">{body}</div>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
</body></html>"""


def _bar_rows(pairs, total, href=None, unit=("работа", "работы", "работ")):
    """Строки «название — полоса — число».

    Число всегда написано словами рядом с полосой, поэтому таблица читается
    и без цвета, и в распечатке, и скринридером — полоса лишь помогает
    сравнить на глаз.
    """
    top = max((n for _, n in pairs), default=1) or 1
    out = []
    for name, n in pairs:
        w = round(n / top * 100, 1)
        label = h(name)
        if href:
            link = href(name)
            label = f'<a href="{h(link)}">{label}</a>'
        share = f"{n} {plural_ru(n, *unit)}" + (f", {round(n / total * 100)}%" if total else "")
        out.append(
            f'<li class="stat-row">'
            f'<span class="stat-name">{label}</span>'
            f'<span class="stat-track"><span class="stat-fill" style="--w:{w}%"></span></span>'
            f'<span class="stat-n" title="{h(share)}">{n}</span>'
            f'</li>'
        )
    return "".join(out)


def _bar_block(title, pairs, total, note="", href=None, anchor=""):
    if not pairs:
        return ""
    return (f'<section class="stat-block" id="{anchor}">'
            f'<h2>{h(title)}</h2>'
            f'<ol class="stat-list">{_bar_rows(pairs, total, href)}</ol>'
            + (f'<p class="stat-note">{h(note)}</p>' if note else "")
            + '</section>')


@tidy
def render_stats(all_posts):
    """Статистика собрания: чем оно на самом деле является.

    Одна мера — число работ — по разным разрезам, поэтому везде один цвет
    и никаких легенд: цвет ничего не кодирует, он просто рисует длину.
    """
    ps = list(all_posts)
    total = len(ps)

    artists = Counter(p["artist"].strip() for p in ps if p.get("artist"))
    museums = Counter(p["museum"].strip() for p in ps if p.get("museum"))
    cities = Counter(p["museum"].rsplit(",", 1)[-1].split("(")[0].strip()
                     for p in ps if p.get("museum") and "," in p["museum"])
    techs = Counter(lower_first(t.strip()) for p in ps for t in p.get("techniques", []) if t and len(t) > 2)
    mats = Counter(lower_first(p["material"].strip()) for p in ps if p.get("material"))

    years = sorted(int(p["creation_year"]) for p in ps if p.get("creation_year"))
    decades = Counter((y // 10) * 10 for y in years)

    # ---- столбцы по десятилетиям ----
    bars = ""
    if decades:
        lo, hi = min(decades), max(decades)
        peak = max(decades.values())
        cols = []
        for d in range(lo, hi + 10, 10):
            n = decades.get(d, 0)
            hpct = round(n / peak * 100, 1)
            # подписываем каждые полвека и обязательно края
            show = (d % 50 == 0) or d == lo or d == hi
            cols.append(
                f'<div class="dec-col" title="{d}-е: {n} {h(plural_ru(n, "работа", "работы", "работ"))}">'
                f'<span class="dec-bar" style="--hgt:{hpct}%"></span>'
                f'<span class="dec-cap{"" if show else " dec-cap-hidden"}">{d}</span>'
                f'</div>'
            )
        no_year = total - len(years)
        note = f"Самая ранняя работа — {years[0]} год, самая поздняя — {years[-1]}."
        if no_year:
            note += f" У {no_year} {plural_ru(no_year, 'работы', 'работ', 'работ')} год не указан."
        bars = (f'<section class="stat-block" id="desyatiletiya"><h2>По десятилетиям</h2>'
                f'<div class="dec-chart" role="img" aria-label="Распределение работ по десятилетиям, '
                f'от {lo}-х до {hi}-х годов">{"".join(cols)}</div>'
                f'<p class="stat-note">{h(note)}</p></section>')

    def many(counter, least=2):
        return [(k, v) for k, v in counter.most_common() if v >= least]

    def tail(counter, least=2, word=("художник", "художника", "художников")):
        rest = sum(1 for v in counter.values() if v < least)
        if not rest:
            return ""
        return f"И ещё {rest} {plural_ru(rest, *word)} — по одной работе."

    span = f"{years[0]}—{years[-1]}" if years else "—"
    tiles = [
        (str(total), plural_ru(total, "работа", "работы", "работ")),
        (str(len(artists)), plural_ru(len(artists), "художник", "художника", "художников")),
        (str(len(museums)), plural_ru(len(museums), "собрание", "собрания", "собраний")),
        (str(len(cities)), plural_ru(len(cities), "город", "города", "городов")),
        (span, "годы создания"),
    ]
    tiles_html = "".join(f'<div class="stat-tile"><b>{h(v)}</b><span>{h(k)}</span></div>' for v, k in tiles)

    blocks = [
        bars,
        _bar_block("Художники", many(artists), total,
                   tail(artists, 2, ("художник", "художника", "художников")),
                   href=artist_slug, anchor="hudozhniki"),
        _bar_block("Собрания", many(museums), total,
                   tail(museums, 2, ("собрание", "собрания", "собраний")),
                   href=museum_href, anchor="sobraniya"),
        _bar_block("Города", many(cities), total,
                   tail(cities, 2, ("город", "города", "городов")), anchor="goroda"),
        _bar_block("Материал", mats.most_common(), total, anchor="material"),
        _bar_block("Техника", techs.most_common(), total, anchor="tehnika"),
    ]

    head = head_common(
        title="Статистика собрания — Old Picture Art",
        og_image=site_og_image(ps),
        description=(f"Чем собрано Old Picture Art: {total} работ, {len(artists)} художников, "
                     f"{len(museums)} собраний, {span}."),
        canonical=f"{BASE_URL}/stats.html",
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page stats-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="ukazatel.html" class="back">Указатель</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head">
  <p class="eyebrow">Собрание</p>
  <h1>Статистика</h1>
  <div class="stat-tiles">{tiles_html}</div>
</header>
{''.join(b for b in blocks if b)}
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
</body></html>"""


def generate_extra_pages(all_posts, offline=False):
    """Страницы художников, указатель и статистика.
    offline — не спрашивать Wikidata о годах жизни новых художников."""
    cat_no, cat_width = catalogue_numbers(all_posts)
    info = resolve_artist_info(artists_years(all_posts), offline=offline)

    by_artist = defaultdict(list)
    for p in all_posts:
        if p.get("artist"):
            by_artist[p["artist"].strip()].append(p)
    for artist, posts in by_artist.items():
        with open(os.path.join(OUTPUT_DIR, artist_slug(artist)), "w", encoding="utf-8") as f:
            f.write(render_artist_page(artist, posts, all_posts, cat_no, cat_width, info.get(artist)))
    logger.info(f"Сгенерировано {len(by_artist)} страниц художников")

    # Та же уборка, что и у тегов: художник ушёл из собрания или его
    # страница переехала на латинский адрес — прежний файл остаётся
    # лежать и подбирать поисковых роботов.
    live = {artist_slug(a) for a in by_artist}
    legacy = {"artist-" + slugify(a) + ".html": artist_slug(a) for a in by_artist}
    moved, removed = retire_pages("artist-", live, legacy)
    if moved:
        logger.info(f"Прежних адресов художников оставлено перенаправлениями: {moved}")
    if removed:
        logger.info(f"Убрано прежних страниц художников: {removed}")

    with open(os.path.join(OUTPUT_DIR, "ukazatel.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_ukazatel(all_posts, info))
    with open(os.path.join(OUTPUT_DIR, "stats.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_stats(all_posts))
    logger.info("Указатель и статистика готовы")
    return by_artist

__all__ = [
    'render_artist_page',
    'render_ukazatel',
    '_bar_rows',
    '_bar_block',
    'render_stats',
    'generate_extra_pages',
]
