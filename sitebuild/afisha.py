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
    BASE_URL, latin_slug, museum_page, AFISHA_FILE, has_afisha,
)
from .config import OUTPUT_DIR
from .text import plural_ru
from .html import tidy

logger = logging.getLogger("build_site")

AFISHA_PAGE = "afisha.html"
RUSSIA = "Россия"
# Меньше стольких идущих выставок — сборка напомнит пополнить список.
MIN_RUNNING = {"russia": 5, "world": 8}
# Закончилась больше стольких дней назад — запись можно убрать.
STALE_DAYS = 14
# «Скоро откроются» — только то, что откроется в ближайшие столько дней.
SOON_DAYS = 92
# На главной — столько выставок в каждой колонке.
INDEX_COUNT = 3
REQUIRED = ("title", "venue", "city", "country", "start", "end", "url")
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


def afisha_item(item, known):
    """Запись на странице афиши."""
    orig = item.get("title_orig") or ""
    note = item.get("note") or ""
    link = museum_link(item, known)
    return (
        f'<li class="afisha-item" id="{h(item["id"])}" data-start="{h(item["start"])}" '
        f'data-end="{h(item["end"])}" data-region="{region(item)}">'
        f'<h3 class="afisha-title"><a href="{h(item["url"])}" target="_blank" rel="noopener">'
        f'{h(item["title"])}</a></h3>'
        + (f'<p class="afisha-orig">{h(orig)}</p>' if orig and orig != item["title"] else "")
        + f'<p class="afisha-where">{h(where_line(item))}</p>'
        f'<p class="afisha-dates"><span class="afisha-range">{h(date_range(item))}</span>'
        f'<span class="now-when afisha-when"></span></p>'
        + (f'<p class="afisha-note">{h(note)}</p>' if note else "")
        + (f'<p class="afisha-links">{link}</p>' if link else "")
        + '</li>')


def afisha_block(items, today=None):
    """Блок «Выставки в России и в мире» на главной.

    В разметке — все идущие и будущие на день сборки; браузер оставит по
    INDEX_COUNT ближайших к закрытию в каждой колонке. Нет записей — нет блока.
    """
    today = today or date.today()
    parts = split(items, today)
    cols = []
    for key, label in (("russia", "В России"), ("world", "В мире")):
        rows = parts[key]["running"] + parts[key]["soon"]
        if not rows:
            continue
        lis = "".join(
            f'<li class="now-item" data-start="{h(it["start"])}" data-end="{h(it["end"])}" hidden>'
            f'<a href="{AFISHA_PAGE}#{h(it["id"])}">{h(it["title"])}</a>'
            f'<span class="now-where">{h(it["venue"])}, {h(it["city"])}</span>'
            f'<span class="now-when"></span></li>'
            for it in rows)
        cols.append(f'<div class="afisha-col" data-region="{key}"><h3 class="afisha-col-title">{label}</h3>'
                    f'<ul class="now-list">{lis}</ul></div>')
    if not cols:
        return ""
    return (f'<section class="now-on afisha-block" id="afisha-block" aria-labelledby="afisha-block-title" hidden>'
            f'<h2 id="afisha-block-title" class="now-title">Выставки в России и в мире</h2>'
            f'<div class="afisha-cols">{"".join(cols)}</div>'
            f'<p class="afisha-more"><a href="{AFISHA_PAGE}">Вся афиша →</a></p></section>')


# Что идёт сегодня — решает браузер. Одна функция на страницу афиши и на
# блок главной: подпись срока, «последние дни», «откроется …»; закончившееся
# убирается, на главной — по INDEX_COUNT в колонке.
AFISHA_JS = """<script>
(function () {
  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
                'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  function day(s) { var p = (s || '').split('-'); return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : null; }
  var now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  function human(d) {
    return d.getDate() + ' ' + MONTHS[d.getMonth()] + (d.getFullYear() !== today.getFullYear() ? ' ' + d.getFullYear() : '');
  }
  // 'ended' | 'running' | 'soon' | 'later' — и подпись к сроку.
  function mark(li, soonDays) {
    var start = day(li.getAttribute('data-start')), end = day(li.getAttribute('data-end'));
    var when = li.querySelector('.now-when');
    li.classList.remove('now-last', 'now-soon');
    if (!end || today > end) return 'ended';
    if (start && today < start) {
      if ((start - today) / 864e5 > soonDays) return 'later';
      if (when) when.textContent = 'откроется ' + human(start);
      li.classList.add('now-soon');
      return 'soon';
    }
    var left = Math.round((end - today) / 864e5);
    if (when) when.textContent = left === 0 ? 'последний день' : (left <= 7 ? 'последние дни — до ' : 'до ') + human(end);
    if (left <= 7) li.classList.add('now-last');
    return 'running';
  }

  // ---- блок на главной
  var block = document.getElementById('afisha-block');
  if (block) {
    var any = false;
    Array.prototype.forEach.call(block.querySelectorAll('.afisha-col'), function (col) {
      var shown = 0, running = [], soon = [];
      Array.prototype.forEach.call(col.querySelectorAll('.now-item'), function (li) {
        var st = mark(li, 31);
        if (st === 'running') running.push(li); else if (st === 'soon') soon.push(li); else li.remove();
      });
      // Порядок — на сегодня: идущие по дате закрытия, потом скорые.
      var by = function (attr) { return function (a, b) { return a.getAttribute(attr) < b.getAttribute(attr) ? -1 : 1; }; };
      running.sort(by('data-end'));
      soon.sort(by('data-start'));
      var list = col.querySelector('.now-list');
      running.concat(soon).forEach(function (li) {
        if (shown < __COUNT__) { li.hidden = false; list.appendChild(li); shown++; } else li.remove();
      });
      col.hidden = !shown;
      if (shown) any = true;
    });
    block.hidden = !any;
  }

  // ---- страница афиши
  var page = document.getElementById('afisha');
  if (!page) return;
  var lists = {running: document.getElementById('afisha-running'), soon: document.getElementById('afisha-soon')};
  var items = Array.prototype.slice.call(page.querySelectorAll('.afisha-item'));
  var counts = {russia: 0, world: 0};
  items.forEach(function (li) {
    var st = mark(li, __SOON__);
    li.setAttribute('data-phase', st);
    if (st === 'ended' || st === 'later') { li.remove(); return; }
    lists[st].appendChild(li);
    counts[li.getAttribute('data-region')]++;
  });
  function order(list, attr) {
    Array.prototype.slice.call(list.children)
      .sort(function (a, b) { return a.getAttribute(attr) < b.getAttribute(attr) ? -1 : a.getAttribute(attr) > b.getAttribute(attr) ? 1 : 0; })
      .forEach(function (li) { list.appendChild(li); });
  }
  order(lists.running, 'data-end');
  order(lists.soon, 'data-start');
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.afisha-switch button'));
  buttons.forEach(function (b) {
    var c = b.querySelector('.visit-count');
    if (c) c.textContent = counts[b.getAttribute('data-region')];
  });
  function show(reg) {
    var shown = {running: 0, soon: 0};
    Array.prototype.forEach.call(page.querySelectorAll('.afisha-item'), function (li) {
      var ok = li.getAttribute('data-region') === reg;
      li.hidden = !ok;
      if (ok) shown[li.getAttribute('data-phase')]++;
    });
    document.getElementById('afisha-running-box').hidden = !shown.running;
    document.getElementById('afisha-soon-box').hidden = !shown.soon;
    document.getElementById('afisha-empty').hidden = !!(shown.running || shown.soon);
    buttons.forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-region') === reg ? 'true' : 'false'); });
    try { localStorage.setItem('afishaRegion', reg); } catch (e) {}
  }
  buttons.forEach(function (b) { b.addEventListener('click', function () { show(b.getAttribute('data-region')); }); });
  // Пришли по ссылке на запись — открываем её вкладку.
  var target = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
  var reg = target && target.getAttribute('data-region');
  if (!reg) { try { reg = localStorage.getItem('afishaRegion'); } catch (e) {} }
  if (reg !== 'world') reg = 'russia';
  show(reg);
  if (target && !target.hidden) { target.classList.add('afisha-target'); target.scrollIntoView(); }
})();
</script>""".replace("__COUNT__", str(INDEX_COUNT)).replace("__SOON__", str(SOON_DAYS))


@tidy
def render_afisha_page(items, updated="", known=(), today=None):
    """Страница afisha.html."""
    today = today or date.today()
    known = set(known or ())
    parts = split(items, today)
    running = sorted(parts["russia"]["running"] + parts["world"]["running"], key=lambda x: x["end"])
    soon = sorted(parts["russia"]["soon"] + parts["world"]["soon"], key=lambda x: x["start"])
    n_ru = len(parts["russia"]["running"]) + len(parts["russia"]["soon"])
    n_world = len(parts["world"]["running"]) + len(parts["world"]["soon"])
    upd = _iso(updated)
    upd_text = f"Список обновлён {ru_date(upd)}. " if upd else ""
    head = head_common(
        title="Афиша: выставки в России и в мире — Old Picture Art",
        description=("Крупные выставки искусства до 1940 года в музеях России и мира: что идёт сейчас "
                     "и что скоро откроется — старые мастера, XIX век, импрессионисты, модерн и авангард."),
        canonical=f"{BASE_URL}/{AFISHA_PAGE}",
    )
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
  </div>
</header>
<main id="afisha" class="afisha">
<section class="afisha-section" id="afisha-running-box" aria-labelledby="afisha-running-title">
<h2 class="museum-section" id="afisha-running-title">Идут сейчас</h2>
<ul class="afisha-list" id="afisha-running">{''.join(afisha_item(it, known) for it in running)}</ul>
</section>
<section class="afisha-section" id="afisha-soon-box" aria-labelledby="afisha-soon-title">
<h2 class="museum-section" id="afisha-soon-title">Скоро откроются</h2>
<ul class="afisha-list" id="afisha-soon">{''.join(afisha_item(it, known) for it in soon)}</ul>
</section>
<p class="no-results" id="afisha-empty" hidden>Сейчас здесь пусто — список скоро пополнится.</p>
<p class="afisha-foot">{upd_text}Список собран по сайтам музеев; перед походом сроки и часы работы лучше проверить на странице выставки.</p>
</main>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{AFISHA_JS}
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


def generate_afisha(known=(), today=None, path=AFISHA_FILE):
    """Пишет docs/afisha.html. Возвращает число идущих и будущих выставок.

    known — названия мест с карты собраний: у записи с полем museum из
    этого списка появляется ссылка на страницу музея на сайте.
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
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_afisha_page(items, updated, known, today))
    afisha_report(items, errors, updated, today)
    parts = split(items, today)
    live = sum(len(parts[r][p]) for r in parts for p in parts[r])
    logger.info(f"Афиша: {len(parts['russia']['running'])} идут в России, "
                f"{len(parts['world']['running'])} в мире, скоро откроются — "
                f"{len(parts['russia']['soon']) + len(parts['world']['soon'])}")
    return live


__all__ = [
    'AFISHA_FILE', 'AFISHA_PAGE', 'RUSSIA', 'MIN_RUNNING', 'STALE_DAYS', 'SOON_DAYS', 'INDEX_COUNT',
    'REQUIRED', 'problems', 'load_afisha', 'afisha_id', 'region', 'phase',
    'ru_date', 'date_range', 'split', 'where_line', 'museum_link', 'afisha_item', 'afisha_block',
    'AFISHA_JS', 'render_afisha_page', 'afisha_report', 'generate_afisha',
]
