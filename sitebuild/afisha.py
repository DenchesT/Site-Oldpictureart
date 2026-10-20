# -*- coding: utf-8 -*-
"""Афиша: крупные выставки искусства до 1940 года — в России и в мире.

«Идёт сейчас» показывает выставки, где я был. Афиша — то, куда стоит
сходить: большие выставки в музеях России и мира, что идут сегодня и
что скоро откроются. Список ведётся руками в afisha.json (один раз его
собрали по сайтам музеев), сайт строит из него:

  • страницу afisha.html — вкладки «Россия» и «Мир», в каждой «Идут
    сейчас» (кто закрывается раньше — выше) и «Скоро откроются»;
  • блок на главной — по три ближайших к закрытию в России и в мире.

Что закончилось, решает браузер по сегодняшней дате (как и «Идёт до…»):
собранная страница не знает, в какой день её откроют, и закончившаяся
выставка исчезает сама, без пересборки. Сборка подсказывает в журнале,
какие записи пора убрать, где ошибка в записи и когда идущих выставок
осталось мало и пора добавить новые.
"""

import json
import logging
import os
import re
from datetime import date
from html import escape as h

from site_common import (
    head_common, scroll_top_button, theme_button, site_footer, COMMON_JS, SCROLL_TOP_JS,
    BASE_URL, latin_slug, museum_page, AFISHA_FILE, has_afisha, MAP_LAYERS_JS,
)
from .config import OUTPUT_DIR
from .text import load_json, plural_ru, save_json
from .html import tidy
from .places import LEAFLET_CSS, LEAFLET_JS, museum_directory, museum_info

logger = logging.getLogger("build_site")

AFISHA_PAGE = "afisha.html"
# Где выставки на карте: найденное геокодером карты собраний запоминается
# здесь (как museum_coordinates.json у карты) — второй раз не ищется.
PLACES_FILE = "afisha_places.json"
RUSSIA = "Россия"
# Меньше стольких идущих выставок — сборка напомнит пополнить список.
MIN_RUNNING = {"russia": 5, "world": 8}
# Закончилась больше стольких дней назад — запись можно убрать.
STALE_DAYS = 14
# «Скоро откроются» — только то, что откроется в ближайшие столько дней.
SOON_DAYS = 92
# В панели главной — столько выставок в России и в мире (упор на Россию).
INDEX_COUNT = {"russia": 3, "world": 2}
REQUIRED = ("title", "venue", "city", "country", "start", "end", "url")
# Во вкладке «Россия» выставок много — её можно сузить до Москвы, Петербурга
# или остальных городов. Город относится к Москве или Петербургу по этим
# спискам (пригороды тоже); любой другой — «Другие города». Если город не
# угадывается, в записи можно указать "area": "moscow" | "spb" | "regions".
AREAS = (("moscow", "Москва"), ("spb", "Петербург"), ("regions", "Другие города"))
MOSCOW_AREA = {"Москва", "Абрамцево", "Архангельское", "Серпухов", "Коломна", "Сергиев Посад", "Истра",
               "Новый Иерусалим", "Мелихово", "Мураново", "Подольск", "Клин", "Звенигород", "Дмитров",
               "Можайск", "Бородино", "Кусково", "Коломенское", "Царицыно", "Ясенево"}
SPB_AREA = {"Санкт-Петербург", "Петербург", "Петергоф", "Пушкин", "Царское Село", "Павловск", "Гатчина",
            "Ломоносов", "Ораниенбаум", "Кронштадт", "Стрельна", "Репино"}
_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")


def _iso(s):
    try:
        return date.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def problems(item):
    """Что не так с записью афиши — пустой список, если всё хорошо."""
    out = []
    if not isinstance(item, dict):
        return ["это не запись (нужны фигурные скобки)"]
    for k in REQUIRED:
        if not str(item.get(k) or "").strip():
            out.append(f"нет поля {k}")
    start, end = _iso(item.get("start")), _iso(item.get("end"))
    if item.get("start") and not start:
        out.append(f"start не дата ГГГГ-ММ-ДД: {item.get('start')}")
    if item.get("end") and not end:
        out.append(f"end не дата ГГГГ-ММ-ДД: {item.get('end')}")
    if start and end and end < start:
        out.append("end раньше start")
    if item.get("url") and not re.match(r"https?://", str(item["url"])):
        out.append("url должен начинаться с https://")
    if ("lat" in item) != ("lon" in item):
        out.append("lat и lon пишутся парой")
    elif "lat" in item:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except (TypeError, ValueError):
            out.append("lat и lon — числа: широта от -90 до 90, долгота от -180 до 180")
    if item.get("area") and item["area"] not in dict(AREAS):
        out.append(f"area бывает только {', '.join(k for k, _ in AREAS)}")
    return out


def load_afisha(path=AFISHA_FILE):
    """(записи, ошибки, дата обновления). Записи с ошибками пропускаются."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        return [], [], ""
    except ValueError as e:
        return [], [f"{path} не читается как JSON: {e}"], ""
    raw = data.get("exhibitions", []) if isinstance(data, dict) else data
    updated = data.get("updated", "") if isinstance(data, dict) else ""
    items, errors, seen = [], [], set()
    for i, item in enumerate(raw or [], 1):
        bad = problems(item)
        name = (item.get("title") if isinstance(item, dict) else None) or f"запись {i}"
        if bad:
            errors.append(f"«{name}»: " + "; ".join(bad))
            continue
        key = (item["title"].strip().lower(), item["venue"].strip().lower())
        if key in seen:
            errors.append(f"«{name}»: записана дважды")
            continue
        seen.add(key)
        items.append(dict(item, id=afisha_id(item)))
    return items, errors, updated


def afisha_id(item):
    """Якорь записи на странице: латиница из названия и города."""
    return "a-" + (latin_slug(f"{item.get('title', '')} {item.get('city', '')}", 70) or "x")


def region(item):
    return "russia" if (item.get("country") or "").strip() == RUSSIA else "world"


def area(item):
    """Для записей России: 'moscow', 'spb' или 'regions'; для мира — ''."""
    if region(item) != "russia":
        return ""
    explicit = (item.get("area") or "").strip()
    if explicit in dict(AREAS):
        return explicit
    city = (item.get("city") or "").strip()
    if city in MOSCOW_AREA:
        return "moscow"
    if city in SPB_AREA:
        return "spb"
    return "regions"


def place_key(item):
    """Под каким именем место ищется и лежит в кэше: «Музей, город»."""
    return f"{item['venue'].strip()}, {item['city'].strip()}"


def locate(items, known=(), offline=False, path=PLACES_FILE, log=logger.info):
    """{id записи: (широта, долгота, приблизительно ли)} — для карты афиши.

    Откуда координаты, по старшинству:
      1. "lat" и "lon" в самой записи afisha.json — поправка руками;
      2. поле "museum" — место с карты собраний, у него координаты уже есть;
      3. кэш afisha_places.json;
      4. тот же поиск, что у карты собраний (generate_map.geocode): Wikidata,
         OpenStreetMap, на худой конец — город. Без сети (--offline) — нет.
    Подсказка поиску — поле "query" в записи (адрес или название по-английски).
    """
    known = set(known or ())
    cache = load_json(path, {})
    directory = None
    out, changed, network = {}, False, not offline
    pending = sorted({place_key(it) for it in items
                      if not ("lat" in it and "lon" in it)
                      and not ((it.get("museum") or "") in known)
                      and place_key(it) not in cache})
    if pending and network:
        log(f"Афиша: ищу на карте места выставок — {len(pending)} (один раз, дальше из {path})")
    for it in items:
        try:
            if "lat" in it and "lon" in it:
                out[it["id"]] = (float(it["lat"]), float(it["lon"]), bool(it.get("approx")))
                continue
        except (TypeError, ValueError):
            pass
        name = (it.get("museum") or "").strip()
        if name in known:
            directory = directory or museum_directory()
            info = museum_info(name, directory)
            if info.get("lat") is not None and info.get("lon") is not None:
                out[it["id"]] = (info["lat"], info["lon"], bool(info.get("approx")))
                continue
        key = place_key(it)
        hint = (it.get("query") or "").strip()
        cached = cache.get(key)
        if cached and (cached.get("hint") or "") == hint:
            out[it["id"]] = (cached["lat"], cached["lon"], cached.get("precision") == "approx")
            continue
        if key in cache and cached is None and not hint:
            continue                                   # уже искали — не нашлось
        if not network:
            if cached:
                out[it["id"]] = (cached["lat"], cached["lon"], cached.get("precision") == "approx")
            continue
        try:
            import generate_map as gm
            found = gm.geocode(key, cache, {key: {"query": hint}} if hint else {}, retry_failed=bool(hint),
                               hint=f'Точнее — впишите в {AFISHA_FILE} у этой выставки "query": "адрес, город" '
                                    f'или "lat" и "lon".')
        except Exception as e:                         # сеть пропала — остальных в следующий раз
            log(f"Афиша: поиск мест на карте прервался ({e.__class__.__name__}) — продолжу в следующий раз")
            network = False
            continue
        changed = True
        if found:
            cache[key] = dict(found, hint=hint)
            out[it["id"]] = (found["lat"], found["lon"], found.get("precision") == "approx")
    if changed:
        save_json(path, cache)
    return out


def phase(item, today):
    """'ended', 'running', 'soon' (откроется в ближайшие SOON_DAYS) или 'later'."""
    start, end = _iso(item["start"]), _iso(item["end"])
    if end < today:
        return "ended"
    if start <= today:
        return "running"
    return "soon" if (start - today).days <= SOON_DAYS else "later"


def ru_date(d, year=True):
    return f"{d.day} {_MONTHS[d.month - 1]}" + (f" {d.year}" if year else "")


def date_range(item):
    """«9 сентября — 13 декабря 2026», «16 октября 2026 — 10 мая 2027»."""
    start, end = _iso(item["start"]), _iso(item["end"])
    return f"{ru_date(start, start.year != end.year)} — {ru_date(end)}"


def split(items, today):
    """{регион: {'running': [...], 'soon': [...]}} на день today — для сборки.

    Браузер потом пересчитает то же самое на сегодняшний день.
    """
    out = {"russia": {"running": [], "soon": []}, "world": {"running": [], "soon": []}}
    for it in items:
        ph = phase(it, today)
        if ph in ("running", "soon"):
            out[region(it)][ph].append(it)
    for r in out.values():
        r["running"].sort(key=lambda x: (x["end"], x["start"]))
        r["soon"].sort(key=lambda x: (x["start"], x["end"]))
    return out


def where_line(item):
    """«Лувр · Париж, Франция»; для России — без страны."""
    place = item["city"] if region(item) == "russia" else f"{item['city']}, {item['country']}"
    return f"{item['venue']} · {place}"


def museum_link(item, known):
    """Ссылка на страницу музея на этом сайте, если он есть на карте собраний."""
    name = (item.get("museum") or "").strip()
    if not name or name not in known:
        return ""
    return (f'<a class="afisha-museum" href="{h(museum_page(name))}">'
            f'Картины этого музея на сайте</a>')


def afisha_item(item, known, coords=None):
    """Запись на странице афиши. coords — (широта, долгота, приблизительно)."""
    orig = item.get("title_orig") or ""
    note = item.get("note") or ""
    link = museum_link(item, known)
    geo = ""
    if coords:
        geo = f' data-lat="{coords[0]:.5f}" data-lon="{coords[1]:.5f}"' + (" data-approx" if coords[2] else "")
    return (
        f'<li class="afisha-item" id="{h(item["id"])}" data-start="{h(item["start"])}" '
        f'data-end="{h(item["end"])}" data-region="{region(item)}"'
        + (f' data-area="{area(item)}"' if area(item) else "") + geo + '>'
        + f'<h3 class="afisha-title"><a href="{h(item["url"])}" target="_blank" rel="noopener">'
        f'{h(item["title"])}</a></h3>'
        + (f'<p class="afisha-orig">{h(orig)}</p>' if orig and orig != item["title"] else "")
        + f'<p class="afisha-where">{h(where_line(item))}'
        + ('<button type="button" class="afisha-pin">на карте</button>' if coords else '') + '</p>'
        f'<p class="afisha-dates"><span class="afisha-range">{h(date_range(item))}</span>'
        f'<span class="now-when afisha-when"></span></p>'
        + (f'<p class="afisha-note">{h(note)}</p>' if note else "")
        + (f'<p class="afisha-links">{link}</p>' if link else "")
        + '</li>')


def afisha_block(items, today=None):
    """Афиша в левой панели главной — под фильтрами.

    Заголовок раздела — ссылка на afisha.html, под ним выставки «В России»
    и «В мире» (сколько — INDEX_COUNT), ближайшие к закрытию: название в одну
    строку (целиком — в подсказке), ниже город и срок. В разметке — все
    идущие и будущие на день сборки, браузер оставляет нужные на сегодня.
    Раньше это был блок над галереей, на всю ширину, — занимал полэкрана.
    """
    if not items:
        return ""
    today = today or date.today()
    parts = split(items, today)
    cols = []
    for key, label in (("russia", "В России"), ("world", "В мире")):
        rows = parts[key]["running"] + parts[key]["soon"]
        if not rows:
            continue
        lis = "".join(
            f'<li class="now-item afisha-side-item" data-start="{h(it["start"])}" data-end="{h(it["end"])}" hidden>'
            f'<a href="{AFISHA_PAGE}#{h(it["id"])}" title="{h(it["title"])} — {h(it["venue"])}, {h(it["city"])}">'
            f'{h(it["title"])}</a>'
            f'<span class="now-where">{h(it["city"])}</span>'
            f'<span class="now-when"></span></li>'
            for it in rows)
        cols.append(f'<div class="afisha-col" data-region="{key}" data-limit="{INDEX_COUNT[key]}">'
                    f'<p class="afisha-col-title">{label}</p>'
                    f'<ul class="afisha-side-list">{lis}</ul></div>')
    return (f'<div class="sidebar-section sidebar-afisha" id="afisha-block">'
            f'<a class="sidebar-title sidebar-icon icon-afisha no-arrow" href="{AFISHA_PAGE}">Выставки сейчас</a>'
            f'<div class="afisha-side" hidden>{"".join(cols)}</div></div>')


# Что идёт сегодня — решает браузер. Одна функция на страницу афиши и на
# раздел в панели главной: подпись срока, «последние дни», «откроется …»;
# закончившееся убирается, на главной — по INDEX_COUNT в группе, и подписи
# короче («до 25 окт.»), чтобы влезали в узкую панель.
AFISHA_JS = """<script>
(function () {
  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
                'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  function day(s) { var p = (s || '').split('-'); return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : null; }
  var now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  var SHORT = ['янв.', 'февр.', 'марта', 'апр.', 'мая', 'июня', 'июля',
               'авг.', 'сент.', 'окт.', 'нояб.', 'дек.'];
  function human(d, short) {
    return d.getDate() + ' ' + (short ? SHORT : MONTHS)[d.getMonth()] +
      (d.getFullYear() !== today.getFullYear() ? ' ' + d.getFullYear() : '');
  }
  // 'ended' | 'running' | 'soon' | 'later' — и подпись к сроку.
  function mark(li, soonDays, short) {
    var start = day(li.getAttribute('data-start')), end = day(li.getAttribute('data-end'));
    var when = li.querySelector('.now-when');
    li.classList.remove('now-last', 'now-soon');
    if (!end || today > end) return 'ended';
    if (start && today < start) {
      if ((start - today) / 864e5 > soonDays) return 'later';
      if (when) when.textContent = (short ? 'с ' : 'откроется ') + human(start, short);
      li.classList.add('now-soon');
      return 'soon';
    }
    var left = Math.round((end - today) / 864e5);
    if (when) when.textContent = left === 0 ? 'последний день'
      : (left <= 7 && !short ? 'последние дни — до ' : 'до ') + human(end, short);
    if (left <= 7) li.classList.add('now-last');
    return 'running';
  }

  // ---- раздел в панели главной
  var block = document.getElementById('afisha-block');
  if (block) {
    var any = false, box = block.querySelector('.afisha-side') || block;
    Array.prototype.forEach.call(block.querySelectorAll('.afisha-col'), function (col) {
      var shown = 0, running = [], soon = [];
      Array.prototype.forEach.call(col.querySelectorAll('.now-item'), function (li) {
        var st = mark(li, 31, true);
        if (st === 'running') running.push(li); else if (st === 'soon') soon.push(li); else li.remove();
      });
      // Порядок — на сегодня: идущие по дате закрытия, потом скорые.
      var by = function (attr) { return function (a, b) { return a.getAttribute(attr) < b.getAttribute(attr) ? -1 : 1; }; };
      running.sort(by('data-end'));
      soon.sort(by('data-start'));
      var list = col.querySelector('ul'), limit = +col.getAttribute('data-limit') || 3;
      running.concat(soon).forEach(function (li) {
        if (shown < limit) { li.hidden = false; list.appendChild(li); shown++; } else li.remove();
      });
      col.hidden = !shown;
      if (shown) any = true;
    });
    // Ничего не идёт — остаётся только ссылка на афишу.
    box.hidden = !any;
  }

  // ---- страница афиши
  var page = document.getElementById('afisha');
  if (!page) return;
  var lists = {running: document.getElementById('afisha-running'), soon: document.getElementById('afisha-soon')};
  var items = Array.prototype.slice.call(page.querySelectorAll('.afisha-item'));
  var counts = {russia: 0, world: 0, all: 0, moscow: 0, spb: 0, regions: 0};
  items.forEach(function (li) {
    var st = mark(li, __SOON__);
    li.setAttribute('data-phase', st);
    if (st === 'ended' || st === 'later') { li.remove(); return; }
    lists[st].appendChild(li);
    counts[li.getAttribute('data-region')]++;
    var ar = li.getAttribute('data-area');
    if (ar) { counts[ar]++; counts.all++; }
  });
  function order(list, attr) {
    Array.prototype.slice.call(list.children)
      .sort(function (a, b) { return a.getAttribute(attr) < b.getAttribute(attr) ? -1 : a.getAttribute(attr) > b.getAttribute(attr) ? 1 : 0; })
      .forEach(function (li) { list.appendChild(li); });
  }
  order(lists.running, 'data-end');
  order(lists.soon, 'data-start');
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.afisha-switch button'));
  var areaBox = document.querySelector('.afisha-area');
  var areaBtns = Array.prototype.slice.call(document.querySelectorAll('.afisha-area button'));
  function count(b, key) {
    var c = b.querySelector('.visit-count');
    if (c) c.textContent = counts[key];
  }
  buttons.forEach(function (b) { count(b, b.getAttribute('data-region')); });
  // Город, где сегодня ничего не идёт, из переключателя убираем.
  areaBtns.forEach(function (b) { count(b, b.getAttribute('data-area')); b.hidden = !counts[b.getAttribute('data-area')]; });
  var state = {reg: 'russia', area: 'all'};
  function show(reg, ar) {
    state.reg = reg;
    state.area = ar = (reg === 'russia' && ar && counts[ar]) ? ar : 'all';
    var shown = {running: 0, soon: 0};
    Array.prototype.forEach.call(page.querySelectorAll('.afisha-item'), function (li) {
      var ok = li.getAttribute('data-region') === reg && (ar === 'all' || li.getAttribute('data-area') === ar);
      li.hidden = !ok;
      if (ok) shown[li.getAttribute('data-phase')]++;
    });
    document.getElementById('afisha-running-box').hidden = !shown.running;
    document.getElementById('afisha-soon-box').hidden = !shown.soon;
    document.getElementById('afisha-empty').hidden = !!(shown.running || shown.soon);
    buttons.forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-region') === reg ? 'true' : 'false'); });
    areaBtns.forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-area') === ar ? 'true' : 'false'); });
    // Переключатель городов нужен только России, и только если городов больше одного.
    if (areaBox) areaBox.hidden = reg !== 'russia' || areaBtns.filter(function (b) { return !b.hidden; }).length < 3;
    try { localStorage.setItem('afishaRegion', reg); localStorage.setItem('afishaArea', ar); } catch (e) {}
    // Карта слушает это событие и показывает те же выставки, что и список.
    page.dispatchEvent(new CustomEvent('afisha:shown'));
  }
  buttons.forEach(function (b) { b.addEventListener('click', function () { show(b.getAttribute('data-region'), state.area); }); });
  areaBtns.forEach(function (b) { b.addEventListener('click', function () { show('russia', b.getAttribute('data-area')); }); });
  // Пришли по ссылке на запись — открываем её вкладку (и все города).
  var target = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
  var reg = target && target.getAttribute('data-region'), ar = 'all';
  if (!reg) {
    try { reg = localStorage.getItem('afishaRegion'); ar = localStorage.getItem('afishaArea') || 'all'; } catch (e) {}
  }
  if (reg !== 'world') reg = 'russia';
  show(reg, ar);
  function highlight(el) {
    Array.prototype.forEach.call(page.querySelectorAll('.afisha-target'), function (x) { x.classList.remove('afisha-target'); });
    el.classList.add('afisha-target');
  }
  if (target && !target.hidden) { highlight(target); target.scrollIntoView(); }
  // Ссылка из подсказки на карте ведёт на запись: открыть её вкладку и город.
  window.addEventListener('hashchange', function () {
    var el = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
    if (!el || !el.classList.contains('afisha-item')) return;
    if (el.hidden) show(el.getAttribute('data-region'), 'all');
    highlight(el);
    el.scrollIntoView();
  });
})();
</script>""".replace("__SOON__", str(SOON_DAYS))


# Карта на странице афиши: метки — те же выставки, что сейчас в списке
# (вкладка, город, сегодняшняя дата). Скопления меток в одном городе
# собираются в кружок с числом. Кнопка «на карте» у записи приближает
# её метку, ссылка в подсказке метки ведёт к записи. Подложки — общие
# с картой собраний (MAP_LAYERS_JS): Яндекс по умолчанию.
AFISHA_MAP_JS = """
(function () {
  var el = document.getElementById('afisha-map'), page = document.getElementById('afisha');
  if (!el || !page || !window.L) { if (el) el.hidden = true; return; }
  var map = L.map(el, {scrollWheelZoom: true, worldCopyJump: true}).setView([55.75, 37.62], 4);
  OPA_MAP.attach(map, el);
  var cluster = L.markerClusterGroup ? L.markerClusterGroup({
    maxClusterRadius: 36, showCoverageOnHover: false, spiderfyOnMaxZoom: true,
    iconCreateFunction: function (c) {
      return L.divIcon({className: 'afisha-cluster', html: '<span>' + c.getChildCount() + '</span>', iconSize: [30, 30]});
    }
  }) : L.layerGroup();
  cluster.addTo(map);
  var byId = {};
  function esc(s) { return String(s || '').replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function refresh() {
    cluster.clearLayers();
    byId = {};
    var pts = [];
    Array.prototype.forEach.call(page.querySelectorAll('.afisha-item[data-lat]'), function (li) {
      if (li.hidden) return;
      var ll = [+li.getAttribute('data-lat'), +li.getAttribute('data-lon')];
      var cls = li.classList.contains('now-last') ? ' afisha-dot-last' : li.classList.contains('now-soon') ? ' afisha-dot-soon' : '';
      var a = li.querySelector('.afisha-title a');
      var m = L.marker(ll, {title: a.textContent, icon: L.divIcon({className: 'afisha-dot' + cls, iconSize: [16, 16]})});
      m.bindPopup('<b><a href="#' + li.id + '">' + esc(a.textContent) + '</a></b>' +
        '<span class="popup-place">' + esc(li.querySelector('.afisha-where').firstChild.textContent) + '</span>' +
        '<span class="popup-when">' + esc(li.querySelector('.now-when').textContent || li.querySelector('.afisha-range').textContent) + '</span>' +
        (li.hasAttribute('data-approx') ? '<span class="popup-approx">место на карте приблизительное</span>' : '') +
        '<a class="popup-site" href="' + esc(a.getAttribute('href')) + '" target="_blank" rel="noopener">Сайт выставки ↗</a>');
      cluster.addLayer(m);
      byId[li.id] = m;
      pts.push(ll);
    });
    el.hidden = !pts.length;
    if (!pts.length) return;
    map.invalidateSize();
    // Без анимации: переключили вкладку — карта сразу на месте, и щелчок
    // «на карте» не попадает на середину чужого перелёта.
    if (pts.length === 1) map.setView(pts[0], 12, {animate: false});
    else map.fitBounds(L.latLngBounds(pts).pad(0.12), {maxZoom: 11, animate: false});
  }
  page.addEventListener('afisha:shown', refresh);
  page.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('.afisha-pin');
    if (!b) return;
    var m = byId[b.closest('.afisha-item').id];
    if (!m) return;
    // Прокрутка — сразу, без плавности: пока страница плавно едет,
    // анимация приближения у группировки меток не всегда доходит до конца.
    el.scrollIntoView({block: 'center'});
    if (cluster.zoomToShowLayer) cluster.zoomToShowLayer(m, function () { m.openPopup(); });
    else { map.setView(m.getLatLng(), 13); m.openPopup(); }
  });
  refresh();
  el.afishaMap = map;   // для проверок
  el.afishaCluster = cluster;
})();
"""


@tidy
def render_afisha_page(items, updated="", known=(), today=None, coords=None):
    """Страница afisha.html. coords — {id: (широта, долгота, приблизительно)} для карты."""
    today = today or date.today()
    known = set(known or ())
    coords = coords or {}
    parts = split(items, today)
    running = sorted(parts["russia"]["running"] + parts["world"]["running"], key=lambda x: x["end"])
    soon = sorted(parts["russia"]["soon"] + parts["world"]["soon"], key=lambda x: x["start"])
    n_ru = len(parts["russia"]["running"]) + len(parts["russia"]["soon"])
    n_world = len(parts["world"]["running"]) + len(parts["world"]["soon"])
    ru_live = parts["russia"]["running"] + parts["russia"]["soon"]
    area_btns = "".join(
        f'<button type="button" data-area="{key}" aria-pressed="false">{label}'
        f'<span class="visit-count">{sum(1 for it in ru_live if area(it) == key)}</span></button>'
        for key, label in AREAS)
    upd = _iso(updated)
    upd_text = f"Список обновлён {ru_date(upd)}. " if upd else ""
    head = head_common(
        title="Афиша: выставки в России и в мире — Old Picture Art",
        description=("Крупные выставки искусства до 1940 года в музеях России и мира: что идёт сейчас "
                     "и что скоро откроется — старые мастера, XIX век, импрессионисты, модерн и авангард."),
        canonical=f"{BASE_URL}/{AFISHA_PAGE}",
        extra=("\n" + LEAFLET_CSS + '\n<link rel="stylesheet" href="vendor/leaflet.markercluster/MarkerCluster.css">')
        if coords else "",
    )
    has_map = any(it["id"] in coords for it in running + soon)
    map_html = ('<section class="afisha-map mini-map" id="afisha-map" aria-label="Выставки на карте"></section>'
                if has_map else "")
    map_js = (LEAFLET_JS + '\n<script src="vendor/leaflet.markercluster/leaflet.markercluster.js"></script>'
              '\n<script src="map-config.js"></script>\n<script>' + MAP_LAYERS_JS + AFISHA_MAP_JS + '</script>'
              if has_map else "")
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page afisha-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="museums.html" class="back">Карта собраний</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head">
  <p class="eyebrow">Афиша</p>
  <h1>Выставки сейчас</h1>
  <p class="idx-lede afisha-lede">Крупные выставки искусства до 1940 года — от старых мастеров до модерна и авангарда — в музеях России и мира: что идёт сегодня и что скоро откроется. Закончившиеся исчезают сами.</p>
  <div class="visit-bar">
    <div class="view-switch afisha-switch" role="group" aria-label="Где">
      <button type="button" data-region="russia" aria-pressed="true">Россия<span class="visit-count">{n_ru}</span></button>
      <button type="button" data-region="world" aria-pressed="false">Мир<span class="visit-count">{n_world}</span></button>
    </div>
    <div class="view-switch afisha-area" role="group" aria-label="Где в России">
      <button type="button" data-area="all" aria-pressed="true">Все города<span class="visit-count">{n_ru}</span></button>
      {area_btns}
    </div>
  </div>
</header>
<main id="afisha" class="afisha">
{map_html}
<section class="afisha-section" id="afisha-running-box" aria-labelledby="afisha-running-title">
<h2 class="museum-section" id="afisha-running-title">Идут сейчас</h2>
<ul class="afisha-list" id="afisha-running">{''.join(afisha_item(it, known, coords.get(it["id"])) for it in running)}</ul>
</section>
<section class="afisha-section" id="afisha-soon-box" aria-labelledby="afisha-soon-title">
<h2 class="museum-section" id="afisha-soon-title">Скоро откроются</h2>
<ul class="afisha-list" id="afisha-soon">{''.join(afisha_item(it, known, coords.get(it["id"])) for it in soon)}</ul>
</section>
<p class="no-results" id="afisha-empty" hidden>Сейчас здесь пусто — список скоро пополнится.</p>
<p class="afisha-foot">{upd_text}Список собран по сайтам музеев; перед походом сроки и часы работы лучше проверить на странице выставки.</p>
</main>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{AFISHA_JS}
{map_js}
</body></html>"""


def afisha_report(items, errors, updated, today, log=logger):
    """Подсказки в журнал сборки: ошибки, что убрать, когда пополнить."""
    for e in errors:
        log.warning(f"Афиша ({AFISHA_FILE}): {e} — запись пропущена")
    parts = split(items, today)
    stale = [it for it in items if (today - _iso(it["end"])).days > STALE_DAYS]
    if stale:
        log.info(f"Афиша: закончились больше {STALE_DAYS} дней назад — {len(stale)}, их можно убрать "
                 f"из {AFISHA_FILE}: " + "; ".join(f"«{it['title']}»" for it in stale[:6])
                 + (" …" if len(stale) > 6 else ""))
    for key, label in (("russia", "в России"), ("world", "в мире")):
        n = len(parts[key]["running"])
        if n < MIN_RUNNING[key]:
            log.warning(f"Афиша: {label} идёт всего {n} {plural_ru(n, 'выставка', 'выставки', 'выставок')} — "
                        f"пора добавить новые в {AFISHA_FILE} (README, «Афиша»)")
    upd = _iso(updated)
    if upd and (today - upd).days > 60:
        log.info(f"Афиша: список не обновлялся с {ru_date(upd)} — стоит проверить, что открылось нового")


def generate_afisha(known=(), today=None, path=AFISHA_FILE, offline=False, places=PLACES_FILE):
    """Пишет docs/afisha.html. Возвращает число идущих и будущих выставок.

    known — названия мест с карты собраний: у записи с полем museum из
    этого списка появляется ссылка на страницу музея на сайте, а метка на
    карте афиши берёт его координаты. Остальные места ищутся (locate);
    offline=True — только то, что уже найдено.
    """
    today = today or date.today()
    items, errors, updated = load_afisha(path)
    target = os.path.join(OUTPUT_DIR, AFISHA_PAGE)
    if not has_afisha(path):
        for e in errors:
            logger.warning(f"Афиша: {e}")
        # Списка нет — нет и страницы, и ссылок на неё в меню и подвале.
        if os.path.exists(target):
            os.remove(target)
        return 0
    unknown = sorted({it["museum"] for it in items if it.get("museum") and it["museum"] not in set(known)})
    for name in unknown:
        logger.info(f"Афиша: музея «{name}» нет на карте собраний — ссылки на его страницу не будет")
    parts = split(items, today)
    live_items = [it for r in parts.values() for p in r.values() for it in p]
    coords = locate(live_items, known, offline, places)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_afisha_page(items, updated, known, today, coords))
    afisha_report(items, errors, updated, today)
    missing = [it for it in live_items if it["id"] not in coords]
    approx = sorted({place_key(it) for it in live_items if it["id"] in coords and coords[it["id"]][2]})
    if missing and not offline:
        logger.info(f"Афиша: на карте нет {len(missing)} — место не нашлось; можно вписать в {AFISHA_FILE} "
                    f'"lat" и "lon" у выставки: ' + "; ".join(f"«{it['title']}»" for it in missing[:5])
                    + (" …" if len(missing) > 5 else ""))
    if approx:
        logger.info(f"Афиша: по городу, а не по зданию — {len(approx)}: " + "; ".join(approx[:5])
                    + (" …" if len(approx) > 5 else ""))
    live = sum(len(parts[r][p]) for r in parts for p in parts[r])
    logger.info(f"Афиша: {len(parts['russia']['running'])} идут в России, "
                f"{len(parts['world']['running'])} в мире, скоро откроются — "
                f"{len(parts['russia']['soon']) + len(parts['world']['soon'])}")
    return live


__all__ = [
    'AFISHA_FILE', 'AFISHA_PAGE', 'RUSSIA', 'MIN_RUNNING', 'STALE_DAYS', 'SOON_DAYS', 'INDEX_COUNT',
    'REQUIRED', 'AREAS', 'MOSCOW_AREA', 'SPB_AREA', 'area', 'problems', 'load_afisha', 'afisha_id', 'region', 'phase',
    'ru_date', 'date_range', 'split', 'where_line', 'museum_link', 'afisha_item', 'afisha_block',
    'AFISHA_JS', 'AFISHA_MAP_JS', 'PLACES_FILE', 'place_key', 'locate', 'render_afisha_page', 'afisha_report',
    'generate_afisha',
]
