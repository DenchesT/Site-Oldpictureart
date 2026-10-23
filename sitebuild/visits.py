# -*- coding: utf-8 -*-
"""Посещения (#выставка, #галерея): разбор постов, сроки выставок, страницы походов.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
import re
from datetime import datetime
from urllib.parse import quote
from html import escape as h
from site_common import (
    head_common, scroll_top_button, theme_button, site_footer, hires_url, COMMON_JS,
    SCROLL_TOP_JS, LUPA_JS, TOAST_JS, SHARE_JS, BASE_URL, place_parts, visit_organizers,
    visit_kind_label,
)
import logging
from .config import OUTPUT_DIR
from .text import SEPARATOR_RE, TAG_RE, URL_RE, plural_ru, slugify, typo_ru
from .slugs import retire_pages, tag_slug, visit_heading
from .links import clean_links, ext_link, link_for, source_block, source_items
from .html import jsonld_script, site_og_image, telegram_post_link, tidy
from .images import size_attrs
from .places import museum_href, museum_info, place_jsonld, visit_map_names, visit_museum_names
from .afisha import AFISHA_PAGE, load_afisha, match_visits

logger = logging.getLogger("build_site")

# ===================== ПОСЕЩЕНИЯ (#выставка, #галерея) =====================

# Дата посещения и срок работы выставки. Разделителем диапазона в канале
# бывает и дефис, и тире, поэтому принимаем любой.
VISIT_DATE_RE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")
VISIT_RANGE_RE = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–—]\s*(\d{1,2}\.\d{1,2}\.\d{4})")
VISIT_TAIL_DATE_RE = re.compile(r"[,;\s]*(\d{1,2}\.\d{1,2}\.\d{4})\s*$")
# Пустые скобки остаются там, где стоял срок работы или ссылка: срок мы
# из текста вынимаем, а «Выставка "Арктика. Полюс цвета" ( )» — не заголовок.
EMPTY_BRACKETS_RE = re.compile(r"[(\[{]\s*[)\]}]")
# Слово «Выставка» перед названием повторяет то, что и так написано
# в шапке страницы и в строке вида, поэтому в заголовке оно лишнее.
VISIT_PREFIX_RE = re.compile(r"^(?:выставка|экспозиция)\b[\s:—-]*", re.I)
VISIT_TAGS = {"выставка": "выставка", "галерея": "музей"}


def visit_date(text):
    """«6.10.2024» → «06.10.2024». В канале день и месяц пишут и с нулём,
    и без; без выравнивания даты не сортируются и выглядят вразнобой."""
    m = VISIT_DATE_RE.search(text or "")
    if not m:
        return ""
    d, mo, y = m.group(0).split(".")
    return f"{int(d):02d}.{int(mo):02d}.{y}"


def clean_visit_line(line):
    """Одна строка поста: без лишних пробелов, пустых скобок и хвостовых
    запятых. Пустые скобки — след вынутого срока работы."""
    line = EMPTY_BRACKETS_RE.sub(" ", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip(" ,;·—-\t")


def strip_quotes(text):
    """Название в кавычках оставляем без них: кавычки нужны в посте, где
    название стоит рядом со словом «Выставка», а в заголовке — уже нет."""
    text = text.strip()
    pairs = (('"', '"'), ('«', '»'), ('“', '”'), ("'", "'"))
    for a, b in pairs:
        if len(text) > 2 and text.startswith(a) and text.endswith(b):
            return text[1:-1].strip()
    return text


def parse_visit(text):
    """Разбирает пост о посещении: #выставка или #галерея.

    Это не картины, а отчёты о походах, и структура у них своя:

        Выставка "Арктика. Полюс цвета"      ← название
        (12.12.2025 - 21.06.2026)            ← сколько работала

        Корпус на Кадашёвской набережной, 17.01.2026   ← где и когда был

        #гтг@oldpictureart
        #выставка@oldpictureart

    У #галерея названия нет — первой строкой идёт сам музей, дальше дата.
    Разбор нарочно терпимый: части ищутся сначала по разделителю ⸻, потом
    по пустым строкам, потом по обычным переносам, потому что в канале
    встречается и так, и так. Даты узнаются по виду — и отдельной строкой,
    и хвостом после запятой; что осталось, это название и место.
    """
    if not text:
        return {}
    low = text.lower()
    kind = ""
    for tag, name in VISIT_TAGS.items():
        if f"#{tag}" in low:
            kind = name
            break
    if not kind:
        return {}

    urls = URL_RE.findall(text)
    # Теги музеев (#гмии, #гтг) пригодятся ссылками на подборки, а теги
    # самого раздела в них не нужны — они и так видны по виду записи.
    tags = sorted({t for t in TAG_RE.findall(text) if t.lower() not in VISIT_TAGS})
    body = TAG_RE.sub("", URL_RE.sub(" ", text))

    run = ""
    m = VISIT_RANGE_RE.search(body)
    if m:
        run = f"{visit_date(m.group(1))} — {visit_date(m.group(2))}"
        # Заменяем пробелом, а не переносом: срок работы стоит в скобках,
        # и от переноса скобки разъезжались по разным строкам — по одной
        # пустую пару уже не узнать, и в заголовке оставалось «( )».
        body = body[:m.start()] + " " + body[m.end():]

    parts = []
    for split in (SEPARATOR_RE.split,
                  lambda s: re.split(r"\n\s*\n", s),
                  lambda s: s.split("\n")):
        parts = [p.strip() for p in split(body) if p.strip()]
        if len(parts) > 1:
            break

    # Дату вынимаем построчно: она бывает и отдельной строкой, и хвостом
    # после места («Музей русского импрессионизма, 04.11.2023»). Без этого
    # она приклеивалась к названию музея и не попадала в сведения.
    visited, keep = "", []
    for part in parts:
        lines = []
        for line in part.split("\n"):
            line = clean_visit_line(line)
            if not line:
                continue
            if VISIT_DATE_RE.fullmatch(line):
                visited = visited or visit_date(line)
                continue
            tail = VISIT_TAIL_DATE_RE.search(line)
            if tail:
                visited = visited or visit_date(tail.group(1))
                line = clean_visit_line(line[:tail.start()])
                if not line:
                    continue
            lines.append(line)
        if lines:
            keep.append(" ".join(lines))

    if not keep:
        return {}

    if kind == "выставка":
        title = strip_quotes(VISIT_PREFIX_RE.sub("", keep[0]))
        place = keep[1] if len(keep) > 1 else ""
        note = " · ".join(keep[2:])
    else:
        # У похода в музей главное — сам музей, а он в посте бывает и второй
        # строкой: «Зал "Французские пастели" (402)» и под ним «Эрмитаж,
        # Главный штаб». Название музея длиннее и идёт последним, зал —
        # уточнение, поэтому местом считаем последнюю строку.
        title = ""
        place = keep[-1]
        note = " · ".join(keep[:-1])

    return {"kind": kind, "title": title, "place": place, "note": note,
            "run": run, "visited": visited, "urls": urls, "tags": tags, "raw": text}


def visit_sort_key(v):
    """По дате посещения, а не по дате записи: сходил в мае, написал
    в июне. Дата в посте записана по-человечески (19.06.2026), поэтому
    для сравнения переворачиваем её в год-месяц-день."""
    d = (v.get("visited") or "").split(".")
    ymd = f"{d[2]}-{d[1]:0>2}-{d[0]:0>2}" if len(d) == 3 else ""
    return (ymd, v.get("date", ""), v.get("filename", ""))


def visit_stats(visits):
    shows = sum(1 for v in visits if v.get("kind") == "выставка")
    return shows, len(visits) - shows


RUN_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[—–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")


def run_dates(run):
    """«18.03.2025 — 15.06.2025» → ("2025-03-18", "2025-06-15"), иначе None."""
    m = RUN_RE.search(run or "")
    if not m:
        return None
    d1, m1, y1, d2, m2, y2 = m.groups()
    return f"{y1}-{int(m1):02d}-{int(d1):02d}", f"{y2}-{int(m2):02d}-{int(d2):02d}"


def run_status(visit, tag="p", full=False):
    """Место под плашку «Идёт до 4 октября» — её пишет скрипт в браузере.

    Считать на сборке нельзя: сайт статический, собранная сегодня страница
    через месяц соврёт. Поэтому в разметке только даты, а что сегодня —
    решает браузер посетителя. full — на странице похода пишем и
    «Закрылась», в списке закрытые молчат: их там большинство.
    """
    dates = run_dates(visit.get("run"))
    if not dates:
        return ""
    return (f'<{tag} class="run-status" data-start="{dates[0]}" data-end="{dates[1]}"'
            f'{" data-full" if full else ""} hidden></{tag}>')


# Подпись к срокам выставки — во времени, которое сейчас верно:
# «Работает 12.12.2025 — 21.06.2026», пока выставка идёт, «Работала» —
# когда закрылась, «Будет работать» — до открытия. На сборке ставится
# слово на её день, а браузер переписывает его на сегодняшний (тот же
# RUN_STATUS_JS, что и плашка «Идёт до…»): страницу могут открыть и
# через полгода после сборки.
RUN_WORDS = {"soon": "Будет работать", "on": "Работает", "off": "Работала"}


def run_phase(dates, today=None):
    """("2025-12-12", "2026-06-21") → soon / on / off на сегодня."""
    today = today or datetime.now().date().isoformat()
    start, end = dates
    if today < start:
        return "soon"
    return "on" if today <= end else "off"


def run_label(run, today=None):
    """<span> с подписью к срокам: «Работает» / «Работала» / «Будет работать»."""
    dates = run_dates(run)
    if not dates:
        return "<span>Сроки</span>"
    return (f'<span class="run-word" data-start="{dates[0]}" data-end="{dates[1]}">'
            f'{RUN_WORDS[run_phase(dates, today)]}</span>')


RUN_STATUS_JS = """<script>
(function () {
  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
                'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  function day(s) {
    var p = (s || '').split('-');
    return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : null;
  }
  var now = new Date();
  var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  function human(d) {
    return d.getDate() + ' ' + MONTHS[d.getMonth()] +
      (d.getFullYear() !== today.getFullYear() ? ' ' + d.getFullYear() : '');
  }
  Array.prototype.forEach.call(document.querySelectorAll('.run-status[data-end]'), function (el) {
    var start = day(el.getAttribute('data-start')), end = day(el.getAttribute('data-end'));
    if (!end) return;
    var text = '', state = '';
    if (start && today < start) {
      text = 'Откроется ' + human(start); state = 'soon';
    } else if (today <= end) {
      var left = Math.round((end - today) / 864e5);
      if (left === 0) { text = 'Последний день'; state = 'last'; }
      else if (left <= 7) { text = 'Последние дни — до ' + human(end); state = 'last'; }
      else { text = 'Идёт до ' + human(end); state = 'on'; }
    } else if (el.hasAttribute('data-full')) {
      text = 'Закрылась ' + human(end); state = 'off';
    }
    if (!text) return;
    el.textContent = text;
    el.setAttribute('data-state', state);
    el.hidden = false;
  });
  // Подпись к срокам: «Работает» / «Работала» / «Будет работать» на сегодня.
  var WORDS = {soon: 'Будет работать', on: 'Работает', off: 'Работала'};
  Array.prototype.forEach.call(document.querySelectorAll('.run-word[data-end]'), function (el) {
    var start = day(el.getAttribute('data-start')), end = day(el.getAttribute('data-end'));
    if (!end) return;
    el.textContent = WORDS[start && today < start ? 'soon' : today <= end ? 'on' : 'off'];
  });
})();
</script>"""


def visit_card(v, show_place=True, place_text=None):
    """Карточка похода — одна для списка походов и для страницы музея.
    show_place=False — на странице места: оно и так в заголовке.
    place_text — что написать вместо места из поста (на странице
    музея-участника — где шла выставка)."""
    cover = (v.get("thumbs") or v.get("images") or [""])[0]
    heading = visit_heading(v)
    shots = len(v.get("images") or [])
    # Классы у строк сведений нужны плиткам: там подписи прячутся,
    # и без них «17.01.2026 · 12.12.2025 — 21.06.2026 · 7» не прочесть.
    facts = [("f-when", "<span>Побывал</span>", v.get("visited", "")),
             ("f-run", run_label(v.get("run")), v.get("run", "")),
             ("f-shots", "<span>Снимков</span>", str(shots) if shots else "")]
    facts_html = "".join(f'<div class="{cls}">{label}<b>{h(val)}</b></div>'
                         for cls, label, val in facts if val)
    img = (f'<div class="card-img"><img src="{h(cover)}" alt="{h(heading)}"{size_attrs(cover)}'
           f' loading="lazy" decoding="async"></div>') if cover else '<div class="card-img"></div>'
    place = place_text if place_text is not None else v.get("place")
    sub = (place if show_place else "") if v.get("title") else v.get("note", "")
    sub_html = f'<div class="card-title">{h(typo_ru(sub))}</div>' if sub else ''
    # Вид похода стоит там же, где у картины собрание, — строкой под
    # названием. В колонке номера ему не место: на телефоне она шириной
    # в два знака, и слово «выставка» наезжало на снимок.
    return (
        f'<article class="card visit-card" data-kind="{h(v["kind"])}">'
        f'{img}'
        f'<div class="card-body">'
        f'<div class="card-artist"><a class="card-link" href="{h(v["filename"])}">{h(heading)}</a></div>'
        f'{sub_html}'
        f'<div class="card-museum visit-kind">{h(visit_kind_label(v["kind"]))}</div>'
        f'{run_status(v, "div")}</div>'
        f'<div class="card-facts">{facts_html}</div></article>'
    )


@tidy
def render_visits_page(visits, all_posts=None):
    """Список посещений с переключателем «все / выставки / постоянные экспозиции».

    Один список вместо двух разделов: походы идут одной хронологией,
    а переключатель устроен так же, как раскладки на главной, — тем же
    классом кнопок и с тем же запоминанием выбора.
    """
    items = sorted(visits, key=visit_sort_key, reverse=True)
    shows, museums = visit_stats(items)

    cards = [visit_card(v) for v in items]

    head = head_common(
        title="Посещения — Old Picture Art",
        description=(f"Выставки и постоянные экспозиции музеев, где я побывал: {shows} "
                     f"{plural_ru(shows, 'выставка', 'выставки', 'выставок')} "
                     f"и {museums} {plural_ru(museums, 'постоянная экспозиция', 'постоянные экспозиции', 'постоянных экспозиций')}."),
        canonical=f"{BASE_URL}/visits.html",
        og_image=site_og_image(items),
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page visits-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="museums.html" class="back">Карта собраний</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head">
  <p class="eyebrow">Дневник</p>
  <h1>Посещения</h1>
  <p class="idx-lede visits-lede">Выставки и постоянные экспозиции музеев, где я побывал, — с датами и своими снимками.</p>
  {now_on_block(visits, all_posts)}
  <div class="visit-bar">
    <div class="view-switch visit-switch" role="group" aria-label="Что показывать">
      <button type="button" data-kind="all" aria-pressed="true">Все<span class="visit-count">{len(items)}</span></button>
      <button type="button" data-kind="выставка" aria-pressed="false">Выставки<span class="visit-count">{shows}</span></button>
      <button type="button" data-kind="музей" aria-pressed="false">Постоянные экспозиции<span class="visit-count">{museums}</span></button>
    </div>
    <div class="view-switch visit-view" role="group" aria-label="Как показывать">
      <button type="button" data-view="grid" aria-pressed="true">Плитки</button>
      <button type="button" data-view="list" aria-pressed="false">Опись</button>
    </div>
  </div>
</header>
<div class="grid" id="visits">{''.join(cards)}</div>
<p class="no-results" id="visits-empty" hidden>Пока ничего нет.</p>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{RUN_STATUS_JS}
{NOW_ON_JS}
<script>
(function () {{
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.visit-switch button'));
  var cards = Array.prototype.slice.call(document.querySelectorAll('#visits .visit-card'));
  var empty = document.getElementById('visits-empty');
  function show(kind) {{
    var shown = 0;
    cards.forEach(function (c) {{
      var ok = kind === 'all' || c.getAttribute('data-kind') === kind;
      c.hidden = !ok;
      if (ok) shown++;
    }});
    buttons.forEach(function (b) {{
      b.setAttribute('aria-pressed', b.getAttribute('data-kind') === kind ? 'true' : 'false');
    }});
    if (empty) empty.hidden = shown !== 0;
    try {{ localStorage.setItem('visitFilter', kind); }} catch (e) {{}}
  }}
  buttons.forEach(function (b) {{
    b.addEventListener('click', function () {{ show(b.getAttribute('data-kind')); }});
  }});
  var saved = 'all';
  try {{ saved = localStorage.getItem('visitFilter') || 'all'; }} catch (e) {{}}
  if (!buttons.some(function (b) {{ return b.getAttribute('data-kind') === saved; }})) saved = 'all';
  show(saved);

  // Раскладка. По умолчанию плитки: походов много, и описью страница
  // растягивается на несколько экранов — прокручивать её никто не станет.
  var grid = document.getElementById('visits');
  var viewBtns = Array.prototype.slice.call(document.querySelectorAll('.visit-view button'));
  function setView(mode) {{
    grid.classList.toggle('list', mode === 'list');
    viewBtns.forEach(function (b) {{
      b.setAttribute('aria-pressed', b.getAttribute('data-view') === mode ? 'true' : 'false');
    }});
    try {{ localStorage.setItem('visitView', mode); }} catch (e) {{}}
  }}
  viewBtns.forEach(function (b) {{
    b.addEventListener('click', function () {{ setView(b.getAttribute('data-view')); }});
  }});
  var view = 'grid';
  try {{ view = localStorage.getItem('visitView') || 'grid'; }} catch (e) {{}}
  setView(view === 'list' ? 'list' : 'grid');
}})();
</script>
</body></html>"""


def visit_jsonld(visit, info=None, organizers=None):
    """Разметка Schema.org для похода на выставку — ExhibitionEvent.

    Яндекс и Google умеют показывать события прямо в выдаче: название,
    даты, где. Для этого им нужны даты работы, место с адресом и, если
    есть, страница самой выставки — всё это у похода теперь есть. У похода
    в музей (без срока работы) события нет, разметки тоже.
    """
    if visit.get("kind") != "выставка" or not visit.get("title"):
        return ""
    dates = run_dates(visit.get("run"))
    if not dates:
        return ""
    page = f"{BASE_URL}/{visit['filename']}"
    place_name = (info or {}).get("name") or (visit.get("place") or "").strip()
    location = place_jsonld(info, "Museum") if info else {"@type": "Place", "name": place_name}
    data = {
        "@context": "https://schema.org",
        "@type": "ExhibitionEvent",
        "name": visit["title"],
        "startDate": dates[0],
        "endDate": dates[1],
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": location,
        "description": (f"Выставка «{visit['title']}»" + (f", {place_name}" if place_name else "")
                        + f", {visit['run']}."),
        "mainEntityOfPage": page,
    }
    # Официальная страница выставки — ссылка из поста, стоящая на названии.
    links = clean_links(visit.get("links"))
    i = link_for(visit["title"], links)
    data["url"] = links[i]["url"] if i is not None else page
    # Организаторы: все музеи из строки места, если их несколько, иначе
    # сам музей, где идёт выставка.
    orgs = []
    for who in (organizers or ([info] if info else [])):
        if who and who.get("name"):
            org = {"@type": "Organization", "name": who["name"]}
            if who.get("site"):
                org["url"] = who["site"]
            orgs.append(org)
    if orgs:
        data["organizer"] = orgs[0] if len(orgs) == 1 else orgs
    photos = [f"{BASE_URL}/{quote(x, safe='/')}" for x in (visit.get("images") or [])[:3]]
    if photos:
        data["image"] = photos
    return "\n" + jsonld_script(data)


@tidy
def render_visit_page(visit, visits, all_posts=None, map_names=None, afisha=None):
    """Страница одного посещения: все снимки, сведения, ссылка на карту.

    Разметка та же, что у страницы работы, — шапка, колонка снимков,
    таблица сведений справа, лупа по клику: посещение в каталоге такая же
    запись, как картина, и выглядеть должно так же.
    """
    heading = visit_heading(visit)
    photos = visit.get("images") or []
    hires = visit.get("hires") or []
    place = (visit.get("place") or "").strip()
    slug = slugify(heading)

    # Снимков с похода бывает десяток, и колонкой во всю ширину страница
    # растягивалась на пять экранов. Сетка: два-три снимка в ряд, клик
    # открывает лупу — рассматривают в ней, а не на странице.
    shots = []
    thumbs = visit.get("thumbs") or []
    vlist = visit.get("views") or []
    for i, src in enumerate(photos):
        big = hires_url(hires[i] if i < len(hires) else src)
        small = thumbs[i] if i < len(thumbs) else src
        loading = ('fetchpriority="high" decoding="async"' if i == 0
                   else 'loading="lazy" decoding="async"')
        meta_bits = [x for x in (place if place != heading else "", visit.get("visited", "")) if x]
        vw = vlist[i] if i < len(vlist) else ""
        shots.append(
            f'<a href="{h(big)}" class="painting-link shot" target="_blank" rel="noopener" '
            + (f'data-view="{h(vw)}" ' if vw else '')
            + f'title="Рассмотреть" data-title="{h(heading)}" data-meta="{h(", ".join(meta_bits))}" '
            f'data-download="{h(slug)}-{i + 1}{h(os.path.splitext(big)[1] or ".jpg")}">'
            f'<img src="{h(small)}" alt="{h(heading)}, снимок {i + 1}" class="painting"{size_attrs(small)} {loading}>'
            f'<span class="painting-hint" aria-hidden="true">'
            f'<span class="icon-lupa" aria-hidden="true"></span> Рассмотреть</span></a>'
        )
    img_html = ('<div class="shots">' + "\n".join(shots) + '</div>') if shots else ""

    # Место — ссылкой на страницу места, если она есть (там карта, все
    # походы туда и картины собрания); иначе просто текстом. У выставки
    # бывает несколько музеев («МРИ, Ростовский кремль, Конюшенный двор»):
    # тогда «Место» — где она идёт, а все музеи — строкой «Организаторы».
    museum = (map_names or {}).get(place, "")
    organizers = visit_organizers(place, visit_museum_names(all_posts), map_names)
    where = place
    if organizers:
        parts = place_parts(place, visit_museum_names(all_posts) + list((map_names or {}).values()))
        where = ", ".join(x for x in (parts["venue"], parts["section"]) if x)
    if museum:
        place_cell = f'<a href="{h(museum_href(museum))}">{h(where)}</a>'
    else:
        place_cell = h(where) if where != heading else ""
    org_cell = ", ".join(f'<a href="{h(museum_href(card))}">{h(name)}</a>' if card else h(name)
                         for name, card in organizers)
    spec_rows = [("<span>Что</span>", h(visit_kind_label(visit["kind"]).capitalize())),
                 ("<span>Место</span>", place_cell),
                 ("<span>Организаторы</span>", org_cell),
                 ("<span>Раздел</span>", h(typo_ru(visit.get("note", "")))),
                 (run_label(visit.get("run")), h(visit.get("run", ""))),
                 ("<span>Побывал</span>", h(visit.get("visited", ""))),
                 ("<span>Снимков</span>", str(len(photos)) if photos else "")]
    spec_html = '<div class="spec-table">' + "".join(
        f'<div>{label}<b>{v}</b></div>' for label, v in spec_rows if v)
    spec_html += '</div>'

    # Теги музеев из поста (#гмии, #гтг) ведут в подборки картин — если
    # такая страница есть. Тег без страницы был бы битой ссылкой.
    tags_block = ""
    known_tags = {t for p in (all_posts or []) for t in p.get("tags", [])}
    tags = [t for t in visit.get("tags", []) if t in known_tags]
    if tags:
        its = " ".join(f'<a href="tag-{h(tag_slug(t))}.html" class="tag">#{h(t)}</a>' for t in tags)
        tags_block = f'<div class="aside-block"><h3>Собрание</h3><div class="tags">{its}</div></div>'

    # Название выставки и музея в посте — ссылки на их страницы. Здесь они
    # тоже ссылки: заголовок ведёт туда же, куда и в канале. Ссылки, не
    # пришедшиеся ни на одно название, уходят в блок справа — не теряются.
    links = clean_links(visit.get("links"))
    used = set()

    def linked(text):
        i = link_for(text, links, used)
        if i is None:
            return h(text)
        used.add(i)
        return ext_link(text, links[i]["url"])

    h1_html = linked(heading)
    sub_head = f'<h2>{linked(place)}</h2>' if place and place != heading else ''
    items = source_items(links, visit.get("urls"), used)
    # Подписанные ссылки у похода — это страницы выставок и музеев, а не
    # источники сведений, поэтому и блок называется по-другому.
    src_block = source_block(items, ("Ссылка", "Ссылки") if any(t != u for t, u in items)
                             else ("Источник", "Источники"))

    download_btn = ""
    if photos:
        first = hires_url(hires[0] if hires else photos[0])
        download_btn = (f'<a href="{h(first)}" download="{h(slug)}-1{h(os.path.splitext(first)[1] or ".jpg")}" '
                        f'class="topbar-btn" aria-label="Скачать снимок" title="Скачать снимок">'
                        f'<span class="icon-download" aria-hidden="true"></span></a>')

    ordered = sorted(visits, key=visit_sort_key)
    idx = next((i for i, v in enumerate(ordered) if v["filename"] == visit["filename"]), -1)
    nav = []
    if idx > 0:
        prev = ordered[idx - 1]
        nav.append(f'<a href="{h(prev["filename"])}" class="prev-post" title="{h(visit_heading(prev))}">'
                   f'<span class="icon-prev" aria-hidden="true"></span> Раньше</a>')
    if 0 <= idx < len(ordered) - 1:
        nxt = ordered[idx + 1]
        nav.append(f'<a href="{h(nxt["filename"])}" class="next-post" title="{h(visit_heading(nxt))}">'
                   f'Позже <span class="icon-next" aria-hidden="true"></span></a>')
    nav_html = f'<nav class="post-nav">{"".join(nav)}</nav>' if nav else ""

    desc = heading + (f", {place}" if place and place != heading else "")
    desc += f". Побывал {visit['visited']}." if visit.get("visited") else "."
    # У постоянной экспозиции заголовок — название музея, как и у страницы
    # музея: в выдаче было две одинаковые строки. Поход отличают снимки и дата.
    suffix = f" — снимки, {visit['visited']}" if visit.get("visited") else " — снимки"
    tab = heading + suffix
    if len(tab) > 70:
        room = 70 - len(suffix) - 1
        tab = heading[:room].rsplit(" ", 1)[0].rstrip(" ,.") + "…" + suffix
    elif len(tab + " — Old Picture Art") <= 70:
        tab += " — Old Picture Art"
    head = head_common(
        title=h(tab),
        description=desc,
        og_image=f"{BASE_URL}/{photos[0]}" if photos else "",
        canonical=f"{BASE_URL}/{visit['filename']}",
        og_type="article",
        extra=visit_jsonld(visit, museum_info(museum) if museum else None,
                           [museum_info(card) if card else {"name": name} for name, card in organizers]),
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="post-page visit-page">
<a href="#main" class="skip-link">К содержанию</a>
<div class="post-topbar">
  <a href="visits.html" class="topbar-back"><span class="icon-back" aria-hidden="true"></span> Посещения</a>
  <div class="post-topbar-right">
    <button type="button" data-share-btn onclick="sharePage(this)" class="topbar-btn" aria-label="Поделиться" title="Поделиться" aria-haspopup="menu"><span class="icon-share" aria-hidden="true"></span></button>
    {download_btn}
    <button type="button" class="topbar-btn" data-theme-toggle onclick="toggleTheme()" aria-label="Переключить тему" title="Светлая / тёмная тема"><span class="icon-theme-toggle" aria-hidden="true"></span></button>
  </div>
</div>
{scroll_top_button()}
<article id="main" class="post-layout">
  <div class="post-main">
    <header class="post-head">
      <p class="eyebrow">{h(visit_kind_label(visit["kind"]).capitalize())}</p>
      <h1>{h1_html}</h1>
      {sub_head}
      {run_status(visit, full=True)}
      {afisha_backlink(afisha)}
    </header>
    {img_html}
  </div>
  <aside class="post-aside">
    {spec_html}
    {tags_block}
    {src_block}
    <div class="aside-block">
      <h3>Запись</h3>
      <time>{h(visit.get('date', ''))}</time>
      {telegram_post_link(visit)}
    </div>
  </aside>
</article>
{nav_html}
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{LUPA_JS}
{TOAST_JS}
{SHARE_JS}
{RUN_STATUS_JS}
{AFISHA_BACKLINK_JS if afisha else ""}
</body></html>"""


# Выставка из похода есть и в афише сайта — ссылка «Сейчас в афише →».
# Пока выставка не закрылась: дату сверяет браузер, как и «Идёт до…».
AFISHA_BACKLINK_JS = """<script>
(function () {
  var p = document.querySelector('.afisha-backlink');
  if (!p) return;
  var e = (p.getAttribute('data-end') || '').split('-'), n = new Date();
  p.hidden = e.length !== 3 || new Date(n.getFullYear(), n.getMonth(), n.getDate()) > new Date(+e[0], +e[1] - 1, +e[2]);
})();
</script>"""


def afisha_backlink(item):
    if not item:
        return ""
    return (f'<p class="afisha-backlink" data-end="{h(item["end"])}" hidden>'
            f'<a href="{AFISHA_PAGE}#{h(item["id"])}">Сейчас в афише →</a></p>')


# ======================================================================
#                          «ИДЁТ СЕЙЧАС»
# ======================================================================
#
# Сроки у выставок уже есть (run). Из них — блок «Идёт сейчас» на главной
# и в посещениях: выставки, где я был и которые ещё идут. Что идёт
# сегодня, решает браузер (как и плашка «Идёт до…»): собранная страница
# не знает, в какой день её откроют. Крупные выставки в России и в мире,
# где я не был, — в «Афише» (sitebuild/afisha.py).



def exhibitions(visits):
    """Выставки со сроком работы: [(поход, (начало, конец))], новые первыми."""
    out = [(v, run_dates(v.get("run"))) for v in visits or []
           if v.get("kind") == "выставка" and run_dates(v.get("run"))]
    return sorted(out, key=lambda item: item[1], reverse=True)


def venue_line(visit, map_names):
    """Где идёт выставка, с городом: «Музей русского импрессионизма, Москва»."""
    card = (map_names or {}).get((visit.get("place") or "").strip(), "")
    if not card:
        return (visit.get("place") or "").strip()
    city = museum_info(card).get("city") or ""
    return card if (not city or city in card) else f"{card}, {city}"


def now_on_block(visits, all_posts=None, today=None):
    """Блок «Идёт сейчас»: выставки, которые на день сборки ещё не закрылись.

    Браузер оставляет только идущие и скоро открывающиеся; если таких нет,
    блок не показывается вовсе (в разметке он спрятан).
    """
    today = today or datetime.now().date().isoformat()
    upcoming = [(v, d) for v, d in exhibitions(visits) if d[1] >= today]
    if not upcoming:
        return ""
    map_names = visit_map_names(visits, all_posts)
    upcoming.sort(key=lambda item: item[1][1])          # закрывается раньше — выше
    items = "".join(
        f'<li class="now-item" data-start="{d[0]}" data-end="{d[1]}" hidden>'
        f'<a href="{h(v["filename"])}">{h(visit_heading(v))}</a>'
        f'<span class="now-where">{h(venue_line(v, map_names))}</span>'
        f'<span class="now-when"></span></li>'
        for v, d in upcoming)
    return (f'<section class="now-on" id="now-on" aria-labelledby="now-on-title" hidden>'
            f'<h2 id="now-on-title" class="now-title">Идёт сейчас</h2>'
            f'<ul class="now-list">{items}</ul></section>')


NOW_ON_JS = """<script>
(function () {
  var box = document.getElementById('now-on');
  if (!box) return;
  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
                'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  function day(s) { var p = (s || '').split('-'); return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : null; }
  var now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  function human(d) {
    return d.getDate() + ' ' + MONTHS[d.getMonth()] + (d.getFullYear() !== today.getFullYear() ? ' ' + d.getFullYear() : '');
  }
  var running = 0, soon = 0;
  Array.prototype.forEach.call(box.querySelectorAll('.now-item'), function (li) {
    var start = day(li.getAttribute('data-start')), end = day(li.getAttribute('data-end'));
    if (!end || today > end) { li.remove(); return; }
    var when = li.querySelector('.now-when');
    if (start && today < start) {
      // Скоро — только то, что откроется в ближайший месяц.
      if ((start - today) / 864e5 > 31) { li.remove(); return; }
      when.textContent = 'откроется ' + human(start); li.classList.add('now-soon'); soon++;
    } else {
      var left = Math.round((end - today) / 864e5);
      when.textContent = left === 0 ? 'последний день' : 'до ' + human(end);
      if (left <= 7) li.classList.add('now-last');
      running++;
    }
    li.hidden = false;
  });
  if (!running && !soon) return;
  if (!running) box.querySelector('.now-title').textContent = 'Скоро откроются';
  box.hidden = false;
})();
</script>"""


def drop_calendar(out_dir=None):
    """Календарь выставок (exhibitions.ics) убран 19.10.2026. У кого он
    остался от прежней сборки — файл убираем, чтобы не висел без ссылок."""
    stale = os.path.join(out_dir or OUTPUT_DIR, "exhibitions.ics")
    if os.path.exists(stale):
        os.remove(stale)
        logger.info("Убран прежний календарь выставок exhibitions.ics")
        return True
    return False


def generate_visit_pages(visits, all_posts=None):
    """Страницы посещений и общий список. Если посещений нет — ничего
    не создаём: раздел появится сам, когда в канале найдутся такие посты."""
    if not visits:
        return 0
    map_names = visit_map_names(visits, all_posts)
    # Выставки, где я был и которые есть в афише, — ссылка «Сейчас в афише».
    afisha_items = load_afisha()[0]
    in_afisha = {v["filename"]: it for it in afisha_items
                 for iid, v in match_visits(afisha_items, visits).items() if iid == it["id"]}
    wanted = set()
    for v in visits:
        wanted.add(v["filename"])
        with open(os.path.join(OUTPUT_DIR, v["filename"]), "w", encoding="utf-8", newline="\n") as f:
            f.write(render_visit_page(v, visits, all_posts, map_names, in_afisha.get(v["filename"])))
    with open(os.path.join(OUTPUT_DIR, "visits.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_visits_page(visits, all_posts))
    drop_calendar()
    # Заголовок поста могли поправить — имя страницы тогда меняется,
    # а прежняя остаётся в docs/ навсегда и попадает в поиск.
    # Прежние адреса посещений оставляем перенаправлениями, а не сносим:
    # уборка шла по приставке visit-, под которую попадали и они.
    legacy = {old: v["filename"] for v in visits for old in v.get("old_filenames", [])}
    moved, removed = retire_pages("visit-", wanted, legacy)
    if moved:
        logger.info(f"Прежних адресов посещений оставлено перенаправлениями: {moved}")
    if removed:
        logger.info(f"Убрано устаревших страниц посещений: {removed}")
    logger.info(f"Посещения: {len(visits)} + список")
    return len(visits)

__all__ = [
    'VISIT_DATE_RE',
    'VISIT_RANGE_RE',
    'VISIT_TAIL_DATE_RE',
    'EMPTY_BRACKETS_RE',
    'VISIT_PREFIX_RE',
    'VISIT_TAGS',
    'visit_date',
    'clean_visit_line',
    'strip_quotes',
    'parse_visit',
    'visit_sort_key',
    'visit_stats',
    'RUN_RE',
    'run_dates',
    'run_status',
    'RUN_WORDS',
    'run_phase',
    'run_label',
    'RUN_STATUS_JS',
    'visit_card',
    'render_visits_page',
    'visit_jsonld',
    'render_visit_page',
    'exhibitions',
    'venue_line',
    'now_on_block',
    'NOW_ON_JS',
    'drop_calendar',
    'AFISHA_BACKLINK_JS',
    'afisha_backlink',
    'generate_visit_pages',
]
