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
from .html import jsonld_script, tidy
from .images import size_attrs
from .places import LEAFLET_CSS, LEAFLET_JS, museum_directory, museum_info
from .slugs import artist_slug

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
# Эпохи и темы — фильтр на странице. У записи — "tags": ["xix", "russian"].
EPOCHS = (("old", "Старые мастера"), ("xix", "XIX век"), ("impr", "Импрессионизм"),
          ("russian", "Русское искусство"), ("modern", "Модерн и авангард"), ("east", "Искусство Востока"))
# Ссылки афиши проверяются раз в столько дней (сборкой, если есть сеть);
# итог — в этом файле, он только для себя и в репозиторий не идёт.
LINKS_FILE = "afisha_links.json"
LINKS_EVERY_DAYS = 7
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
    tags = item.get("tags")
    if tags is not None and (not isinstance(tags, list) or set(tags) - set(dict(EPOCHS))):
        out.append(f"tags — список из: {', '.join(k for k, _ in EPOCHS)}")
    for k in ("artists",):
        if item.get(k) is not None and not isinstance(item[k], list):
            out.append(f"{k} — список имён, как в постах: [\"Пьер Огюст Ренуар\"]")
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


# ---------------------------------------------------- картины с этого сайта
#
# У выставки «Айвазовский» — строка «На сайте: Айвазовский — 3 работы» с
# миниатюрами. Художника узнаём по фамилии в названии и описании выставки,
# с русскими падежными окончаниями («работы Шишкина», «рядом с Репиным»).
# Фамилии, которые часто встречаются у других людей (Кузнецов, Морозов…),
# засчитываются только вместе с именем или инициалом художника: иначе
# «Константин Кузнецов» дал бы работы Николая Кузнецова, а «собрание
# Морозова» — картины Александра Морозова. Ошиблось — поле "artists" в
# записи: список имён как в постах, или [] — не показывать никого.

_PARTICLES = {"де", "ван", "фон", "ди", "да", "дю", "ле", "ла", "дер"}
COMMON_SURNAMES = {"Кузнецов", "Морозов", "Жуковский", "Мартен", "Брюн", "Даль", "Кент", "Габриэль",
                   "Фридрих", "Альт", "Луар", "Бош", "Иванов"}
SURNAME_ALIASES = {"Сантьяго Рузиньол-и-Пратс": ["Русиньоль"]}
_LETTER = "А-Яа-яЁёA-Za-z"
_ENDS_CONSONANT = ("а", "у", "ом", "е", "ым", "ой", "ы", "ых", "ыми", "ам", "ами")
_ENDS_SKIY = ("ий", "ого", "ому", "им", "ом", "ие", "их", "ими")


def artist_keys(name):
    """Как художник называется в тексте выставки: [(фамилия для образца, подпись)]."""
    name = (name or "").strip()
    if not name or "," in name:                         # «Анонимные художники, …» — не один человек
        return []
    keys = []
    paren = re.search(r"\(([^)]+)\)", name)
    if paren:                                           # «Илер-Жермен-Эдгар де Га (Эдгар Дега)»
        keys.append(paren.group(1).split()[-1])
    words = re.sub(r"\([^)]*\)", "", name).split()
    last = words[-1] if words else ""
    if len(words) >= 2 and words[-2].lower() == "ван":  # «Винсент Виллем ван Гог» → «Ван Гог»
        keys.append("Ван " + last)
    elif "-и-" in last:                                 # «Рузиньол-и-Пратс» → «Рузиньол»
        keys.append(last.split("-и-")[0])
    elif last.count("-") >= 2:                          # «Тулуз-Лотрек-Монфа» → «Тулуз-Лотрек»
        keys.append("-".join(last.split("-")[:2]))
    elif last and not paren:
        keys.append(last)
    keys = list(dict.fromkeys(keys))
    label = keys[0] if keys else ""
    # Другое написание той же фамилии («Русиньоль») — подпись всё равно наша.
    return [(k, k) for k in keys] + [(k, label) for k in SURNAME_ALIASES.get(name, []) if k not in keys]


def _surname_re(key):
    """Образец фамилии с падежными окончаниями."""
    words = key.split()
    last = words[-1]
    head = ""
    for w in words[:-1]:                                # «Ван Гог» и «ван Гог»
        head += f"[{w[0].upper()}{w[0].lower()}]{re.escape(w[1:])}\\s+"
    if re.search(r"(ский|цкий)$", last):
        body = re.escape(last[:-2]) + "(?:" + "|".join(_ENDS_SKIY) + ")"
    elif re.search(r"[бвгджзйклмнпрстфхцчшщ]$", last):
        body = re.escape(last) + "(?:" + "|".join(_ENDS_CONSONANT) + ")?"
    else:                                               # Моне, Дега, Куинджи — не склоняются
        body = re.escape(last)
    return head + body


def works_index(all_posts):
    """Что нужно для поиска работ: образцы фамилий и работы каждого художника."""
    by_artist = {}
    for p in all_posts or []:
        a = (p.get("artist") or "").strip()
        if a and p.get("filename"):
            by_artist.setdefault(a, []).append(p)
    keys = {}
    for a in by_artist:
        pats = []
        first = (a.split() or [""])[0]
        for key, label in artist_keys(a):
            body = _surname_re(key)
            if key in COMMON_SURNAMES and first:
                # Только с именем («Николая Кузнецова») или инициалом («Н. Д. Кузнецов»).
                body = (f"(?:{re.escape(first[:4])}[а-яё]*|{re.escape(first[0])}\\.(?:\\s?[{_LETTER}]\\.)?)"
                        f"\\s+" + body)
            pats.append((re.compile(f"(?<![{_LETTER}-]){body}(?![{_LETTER}-])"), label))
        if pats:
            keys[a] = pats
    for posts in by_artist.values():
        posts.sort(key=lambda p: (p.get("creation_year") or 9999, p.get("filename")))
    return {"keys": keys, "posts": by_artist}


def site_works(item, index):
    """[(художник, подпись, [работы])] — художники этого сайта, о которых выставка."""
    if not index:
        return []
    posts = index["posts"]
    if isinstance(item.get("artists"), list):
        return [(a, (artist_keys(a) or [(a, a)])[0][1], posts[a]) for a in item["artists"] if a in posts]
    text = f"{item.get('title', '')} {item.get('note', '')}"
    out = []
    for a, pats in index["keys"].items():
        hit = next((label for rx, label in pats if rx.search(text)), None)
        if hit:
            out.append((a, hit, posts[a]))
    return sorted(out, key=lambda x: text.find(x[1].split()[-1]))


def works_html(found, limit=4):
    """«На сайте: Айвазовский — 3 работы» и до limit миниатюр со ссылками."""
    if not found:
        return ""
    names = ", ".join(
        f'<a href="{h(artist_slug(a))}">{h(label)}</a> — {len(ps)} '
        f'{plural_ru(len(ps), "работа", "работы", "работ")}' for a, label, ps in found)
    thumbs, queues = [], [list(ps) for _, _, ps in found]
    while queues and len(thumbs) < limit:              # по очереди от каждого художника
        for q in queues:
            if q and len(thumbs) < limit:
                thumbs.append(q.pop(0))
        queues = [q for q in queues if q]
    cells = []
    for p in thumbs:
        src = (p.get("thumbs") or p.get("images") or [""])[0]
        if not src:
            continue
        alt = f"{p.get('artist', '')} — {p.get('title', '')}"
        cells.append(f'<li><a href="{h(p["filename"])}" title="{h(alt)}">'
                     f'<img src="{h(src)}" alt="{h(alt)}" loading="lazy"{size_attrs(src)}></a></li>')
    return (f'<div class="afisha-works"><p class="afisha-works-title">На сайте: {names}</p>'
            + (f'<ul class="afisha-thumbs">{"".join(cells)}</ul>' if cells else "") + '</div>')


# --------------------------------------------------- «был — снимки»

def _norm_title(s):
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[«»\"'“”„.,:;!?()\[\]—–-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def match_visits(items, visits):
    """{id записи афиши: поход} — если я был на этой выставке.

    Совпадение — по названию (одно содержит другое) и пересечению сроков;
    явно — поле "visit" в записи с именем страницы похода.
    """
    from .visits import run_dates                       # здесь, чтобы не закольцевать модули
    by_file = {v.get("filename"): v for v in visits or []}
    shows = [v for v in visits or [] if v.get("kind") == "выставка" and v.get("title")]
    out = {}
    for it in items:
        if it.get("visit"):
            if it["visit"] in by_file:
                out[it["id"]] = by_file[it["visit"]]
            continue
        t = _norm_title(it["title"])
        for v in shows:
            vt = _norm_title(v["title"])
            same = t == vt or (min(len(t), len(vt)) >= 8 and (t in vt or vt in t))
            if not same:
                continue
            run = run_dates(v.get("run"))
            if run and not (run[0] <= it["end"] and it["start"] <= run[1]):
                continue
            out[it["id"]] = v
            break
    return out


def afisha_jsonld(items, coords):
    """Разметка ExhibitionEvent: поисковики показывают выставки как мероприятия."""
    events = []
    for it in items:
        loc = {"@type": "Museum", "name": it["venue"],
               "address": {"@type": "PostalAddress", "addressLocality": it["city"], "addressCountry": it["country"]}}
        c = (coords or {}).get(it["id"])
        if c and not c[2]:
            loc["geo"] = {"@type": "GeoCoordinates", "latitude": round(c[0], 5), "longitude": round(c[1], 5)}
        ev = {"@type": "ExhibitionEvent", "name": it["title"], "startDate": it["start"], "endDate": it["end"],
              "eventStatus": "https://schema.org/EventScheduled",
              "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
              "location": loc, "url": it["url"]}
        if it.get("note"):
            ev["description"] = it["note"]
        events.append(ev)
    return jsonld_script({"@context": "https://schema.org", "@graph": events}) if events else ""


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


def afisha_item(item, known, coords=None, works=None, visit=None):
    """Запись на странице афиши.

    coords — (широта, долгота, приблизительно) для карты и «рядом со мной»;
    works — [(художник, подпись, работы)] с этого сайта; visit — мой поход.
    """
    orig = item.get("title_orig") or ""
    note = item.get("note") or ""
    link = museum_link(item, known)
    attrs = f' data-country="{h(item["country"])}"'
    if item.get("tags"):
        attrs += f' data-tags="{h(" ".join(item["tags"]))}"'
    if coords:
        attrs += f' data-lat="{coords[0]:.5f}" data-lon="{coords[1]:.5f}"' + (" data-approx" if coords[2] else "")
    been = (f'<p class="afisha-been"><a href="{h(visit["filename"])}">Был — снимки и впечатления</a></p>'
            if visit else "")
    return (
        f'<li class="afisha-item" id="{h(item["id"])}" data-start="{h(item["start"])}" '
        f'data-end="{h(item["end"])}" data-region="{region(item)}"'
        + (f' data-area="{area(item)}"' if area(item) else "") + attrs + '>'
        + f'<h3 class="afisha-title"><a href="{h(item["url"])}" target="_blank" rel="noopener">'
        f'{h(item["title"])}</a></h3>'
        + (f'<p class="afisha-orig">{h(orig)}</p>' if orig and orig != item["title"] else "")
        + f'<p class="afisha-where"><span class="afisha-place">{h(where_line(item))}</span>'
        + ('<button type="button" class="afisha-pin">на карте</button>' if coords else '') + '</p>'
        f'<p class="afisha-dates"><span class="afisha-range">{h(date_range(item))}</span>'
        f'<span class="now-when afisha-when"></span></p>'
        + (f'<p class="afisha-note">{h(note)}</p>' if note else "")
        + been
        + works_html(works or [])
        + (f'<p class="afisha-links">{link}</p>' if link else "")
        + '</li>')


def museum_afisha_block(items):
    """«Сейчас в афише» на странице музея — его выставки из афиши.

    В разметке все записи и даты; что идёт сегодня и что откроется в
    ближайшие SOON_DAYS дней, решает браузер (MUSEUM_AFISHA_JS), как и на
    самой афише. Ничего не идёт — блок остаётся спрятанным.
    """
    if not items:
        return ""
    rows = "".join(
        f'<li class="now-item" data-start="{h(it["start"])}" data-end="{h(it["end"])}" hidden>'
        f'<a href="{AFISHA_PAGE}#{h(it["id"])}">{h(it["title"])}</a>'
        f'<span class="now-where">{h(it["venue"])}</span>'
        f'<span class="now-when"></span></li>'
        for it in sorted(items, key=lambda it: (it["end"], it["start"])))
    return (f'<section class="now-on museum-afisha" id="museum-afisha" data-soon="{SOON_DAYS}" '
            f'aria-labelledby="museum-afisha-title" hidden>'
            f'<h2 id="museum-afisha-title" class="now-title">Сейчас в афише</h2>'
            f'<ul class="now-list">{rows}</ul>'
            f'<p class="museum-afisha-more"><a href="{AFISHA_PAGE}">Все выставки</a></p></section>')


MUSEUM_AFISHA_JS = """<script>
(function () {
  var box = document.getElementById('museum-afisha');
  if (!box) return;
  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
                'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  var SOON = +box.getAttribute('data-soon') || 92;
  function day(s) { var p = (s || '').split('-'); return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : null; }
  var now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  function human(d) {
    return d.getDate() + ' ' + MONTHS[d.getMonth()] + (d.getFullYear() !== today.getFullYear() ? ' ' + d.getFullYear() : '');
  }
  var running = [], soon = [];
  Array.prototype.forEach.call(box.querySelectorAll('.now-item'), function (li) {
    var start = day(li.getAttribute('data-start')), end = day(li.getAttribute('data-end'));
    if (!end || today > end) { li.remove(); return; }
    var when = li.querySelector('.now-when');
    if (start && today < start) {
      if ((start - today) / 864e5 > SOON) { li.remove(); return; }
      when.textContent = 'откроется ' + human(start); li.classList.add('now-soon');
      soon.push([start, li]);
    } else {
      var left = Math.round((end - today) / 864e5);
      when.textContent = left === 0 ? 'последний день' : 'до ' + human(end);
      if (left <= 7) li.classList.add('now-last');
      running.push([end, li]);
    }
    li.hidden = false;
  });
  if (!running.length && !soon.length) return;
  // Сначала идущие — кто раньше закрывается, потом будущие — кто раньше откроется.
  var list = box.querySelector('.now-list');
  running.sort(function (a, b) { return a[0] - b[0]; }).concat(soon.sort(function (a, b) { return a[0] - b[0]; }))
    .forEach(function (x) { list.appendChild(x[1]); });
  if (!running.length) box.querySelector('.now-title').textContent = 'Скоро в афише';
  box.hidden = false;
})();
</script>"""


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
  var items = Array.prototype.slice.call(page.querySelectorAll('.afisha-item')).filter(function (li) {
    var st = mark(li, __SOON__);
    li.setAttribute('data-phase', st);
    if (st === 'ended' || st === 'later') { li.remove(); return false; }
    lists[st].appendChild(li);
    return true;
  });
  function order(list, key, numeric) {
    Array.prototype.slice.call(list.children).sort(function (a, b) {
      var x = a.getAttribute(key), y = b.getAttribute(key);
      if (numeric) return (+x) - (+y);
      return x < y ? -1 : x > y ? 1 : 0;
    }).forEach(function (li) { list.appendChild(li); });
  }
  function defaultOrder() { order(lists.running, 'data-end'); order(lists.soon, 'data-start'); }
  defaultOrder();

  var regionBtns = Array.prototype.slice.call(document.querySelectorAll('.afisha-switch button'));
  var sel = {area: document.getElementById('afisha-area'), country: document.getElementById('afisha-country'),
             epoch: document.getElementById('afisha-epoch')};
  var box = {area: document.getElementById('afisha-area-box'), country: document.getElementById('afisha-country-box')};
  var state = {reg: 'russia', area: 'all', country: 'all', epoch: 'all', near: null};
  function tags(li) { return (' ' + (li.getAttribute('data-tags') || '') + ' '); }
  function fits(li, s, skip) {
    if (li.getAttribute('data-region') !== s.reg) return false;
    if (skip !== 'area' && s.reg === 'russia' && s.area !== 'all' && li.getAttribute('data-area') !== s.area) return false;
    if (skip !== 'country' && s.reg === 'world' && s.country !== 'all' && li.getAttribute('data-country') !== s.country) return false;
    if (skip !== 'epoch' && s.epoch !== 'all' && tags(li).indexOf(' ' + s.epoch + ' ') < 0) return false;
    return true;
  }
  // Числа в списках — сколько выставок останется, если выбрать этот пункт
  // (при остальных фильтрах как сейчас); пустые пункты прячем.
  function recount() {
    regionBtns.forEach(function (b) {
      var c = b.querySelector('.visit-count'), r = b.getAttribute('data-region');
      if (c) c.textContent = items.filter(function (li) { return li.getAttribute('data-region') === r; }).length;
    });
    Object.keys(sel).forEach(function (k) {
      if (!sel[k]) return;
      Array.prototype.forEach.call(sel[k].options, function (o) {
        var s2 = {reg: state.reg, area: state.area, country: state.country, epoch: state.epoch};
        s2[k] = o.value;
        var n = items.filter(function (li) { return fits(li, s2); }).length;
        o.textContent = o.getAttribute('data-label') + ' (' + n + ')';
        o.hidden = o.disabled = !n && o.value !== 'all' && o.value !== state[k];
      });
    });
  }
  // «Успеть на этой неделе»: последние дни среди того, что сейчас в списке.
  var week = document.getElementById('afisha-week'), weekList = document.getElementById('afisha-week-list');
  function updateWeek() {
    if (!week) return;
    var rows = items.filter(function (li) { return !li.hidden && li.classList.contains('now-last'); })
      .sort(function (a, b) { return a.getAttribute('data-end') < b.getAttribute('data-end') ? -1 : 1; });
    weekList.innerHTML = '';
    rows.forEach(function (li) {
      var a = li.querySelector('.afisha-title a'), r = document.createElement('li');
      var link = document.createElement('a');
      link.href = '#' + li.id;
      link.textContent = a.textContent;
      var when = document.createElement('span');
      when.className = 'now-when';
      when.textContent = li.querySelector('.now-when').textContent.replace('последние дни — ', '');
      r.appendChild(link);
      r.appendChild(when);
      weekList.appendChild(r);
    });
    week.hidden = !rows.length;
  }
  function show() {
    var shown = {running: 0, soon: 0};
    items.forEach(function (li) {
      var ok = fits(li, state);
      li.hidden = !ok;
      if (ok) shown[li.getAttribute('data-phase')]++;
    });
    document.getElementById('afisha-running-box').hidden = !shown.running;
    document.getElementById('afisha-soon-box').hidden = !shown.soon;
    document.getElementById('afisha-empty').hidden = !!(shown.running || shown.soon);
    regionBtns.forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-region') === state.reg ? 'true' : 'false'); });
    if (box.area) box.area.hidden = state.reg !== 'russia';
    if (box.country) box.country.hidden = state.reg !== 'world';
    Object.keys(sel).forEach(function (k) { if (sel[k]) sel[k].value = state[k]; });
    recount();
    updateWeek();
    try {
      localStorage.setItem('afishaRegion', state.reg);
      localStorage.setItem('afishaArea', state.area);
      localStorage.setItem('afishaCountry', state.country);
      localStorage.setItem('afishaEpoch', state.epoch);
    } catch (e) {}
    // Карта слушает это событие и показывает те же выставки, что и список.
    page.dispatchEvent(new CustomEvent('afisha:shown'));
  }
  regionBtns.forEach(function (b) {
    b.addEventListener('click', function () { state.reg = b.getAttribute('data-region'); show(); });
  });
  Object.keys(sel).forEach(function (k) {
    if (sel[k]) sel[k].addEventListener('change', function () { state[k] = sel[k].value; show(); });
  });

  // ---- «Рядом со мной»: где вы — знает только этот браузер, на сайт
  // ничего не уходит. Выставки сортируются по расстоянию, у каждой — «2 км».
  var nearBtn = document.getElementById('afisha-near-btn'), nearNote = document.getElementById('afisha-near');
  function km(a, b) {
    var r = Math.PI / 180, dLat = (b[0] - a[0]) * r, dLon = (b[1] - a[1]) * r;
    var x = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 12742 * Math.asin(Math.sqrt(x));
  }
  function distText(d) {
    if (d < 1) return Math.max(100, Math.round(d * 10) * 100) + ' м';
    if (d < 10) return d.toFixed(1).replace('.', ',') + ' км';
    return Math.round(d).toLocaleString('ru-RU') + ' км';
  }
  function applyNear() {
    items.forEach(function (li) {
      var old = li.querySelector('.afisha-dist');
      if (old) old.remove();
      if (!state.near || !li.hasAttribute('data-lat')) { li.setAttribute('data-dist', 1e9); return; }
      var d = km(state.near, [+li.getAttribute('data-lat'), +li.getAttribute('data-lon')]);
      li.setAttribute('data-dist', d.toFixed(3));
      var span = document.createElement('span');
      span.className = 'afisha-dist';
      span.textContent = distText(d);
      li.querySelector('.afisha-where').appendChild(span);
    });
    if (state.near) { order(lists.running, 'data-dist', true); order(lists.soon, 'data-dist', true); }
    else defaultOrder();
  }
  function say(html) { nearNote.innerHTML = html; nearNote.hidden = !html; }
  function esc(s) { return String(s || '').replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  if (nearBtn) nearBtn.addEventListener('click', function () {
    if (state.near) {
      state.near = null;
      nearBtn.setAttribute('aria-pressed', 'false');
      say('');
      applyNear();
      show();
      page.dispatchEvent(new CustomEvent('afisha:near', {detail: null}));
      return;
    }
    if (!navigator.geolocation) { say('Этот браузер не умеет определять местоположение.'); return; }
    nearBtn.disabled = true;
    say('Определяю, где вы…');
    navigator.geolocation.getCurrentPosition(function (pos) {
      nearBtn.disabled = false;
      state.near = [pos.coords.latitude, pos.coords.longitude];
      nearBtn.setAttribute('aria-pressed', 'true');
      applyNear();
      var best = null;
      items.forEach(function (li) {
        if (li.hasAttribute('data-lat') && (!best || +li.getAttribute('data-dist') < +best.getAttribute('data-dist'))) best = li;
      });
      if (best) {
        // Ближайшая — во вкладке, где она есть, без сужения по городу и стране.
        state.reg = best.getAttribute('data-region');
        state.area = state.country = 'all';
        var t = best.querySelector('.afisha-title a').textContent;
        say('Ближайшая — ' + distText(+best.getAttribute('data-dist')) + ': <a href="#' + best.id + '">' + esc(t) +
            '</a>, ' + esc(best.querySelector('.afisha-place').textContent.split(' · ')[0]));
      } else say('');
      show();
      page.dispatchEvent(new CustomEvent('afisha:near', {detail: {lat: state.near[0], lon: state.near[1]}}));
    }, function (err) {
      nearBtn.disabled = false;
      say(err && err.code === 1
        ? 'Нет доступа к местоположению — его можно разрешить для этого сайта в настройках браузера.'
        : 'Не получилось определить, где вы. Попробуйте ещё раз.');
    }, {enableHighAccuracy: false, timeout: 15000, maximumAge: 600000});
  });

  // Пришли по ссылке на запись — открываем её вкладку (без сужения).
  var target = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
  if (target && target.classList.contains('afisha-item')) {
    state.reg = target.getAttribute('data-region');
  } else {
    target = null;
    try {
      state.reg = localStorage.getItem('afishaRegion') || 'russia';
      state.area = localStorage.getItem('afishaArea') || 'all';
      state.country = localStorage.getItem('afishaCountry') || 'all';
      state.epoch = localStorage.getItem('afishaEpoch') || 'all';
    } catch (e) {}
  }
  if (state.reg !== 'world') state.reg = 'russia';
  // Сохранённый пункт, которого больше нет (выставки закончились), — «все».
  Object.keys(sel).forEach(function (k) {
    if (!sel[k] || !Array.prototype.some.call(sel[k].options, function (o) { return o.value === state[k]; })) state[k] = 'all';
  });
  show();
  function highlight(el) {
    Array.prototype.forEach.call(page.querySelectorAll('.afisha-target'), function (x) { x.classList.remove('afisha-target'); });
    el.classList.add('afisha-target');
  }
  if (target && !target.hidden) { highlight(target); target.scrollIntoView(); }
  // Ссылка из подсказки на карте или из «Успеть на этой неделе» — на запись.
  window.addEventListener('hashchange', function () {
    var el = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
    if (!el || !el.classList.contains('afisha-item')) return;
    if (el.hidden) { state.reg = el.getAttribute('data-region'); state.area = state.country = state.epoch = 'all'; show(); }
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
  var wrap = document.getElementById('afisha-map-wrap'), toggle = document.getElementById('afisha-map-toggle');
  if (!el || !page || !window.L) { if (wrap) wrap.hidden = true; return; }
  var map = L.map(el, {scrollWheelZoom: true, worldCopyJump: true}).setView([55.75, 37.62], 4);
  OPA_MAP.attach(map, el);
  var cluster = L.markerClusterGroup ? L.markerClusterGroup({
    maxClusterRadius: 36, showCoverageOnHover: false, spiderfyOnMaxZoom: true,
    iconCreateFunction: function (c) {
      return L.divIcon({className: 'afisha-cluster', html: '<span>' + c.getChildCount() + '</span>', iconSize: [30, 30]});
    }
  }) : L.layerGroup();
  cluster.addTo(map);
  var byId = {}, me = null;
  function esc(s) { return String(s || '').replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  // Подсказка над меткой не шире промежутка между кнопками в верхних
  // углах (слева «+ / −», справа подложки), и при открытии карта
  // сдвигается так, чтобы кнопки её не накрывали. Иначе на телефоне
  // название уезжало под «+», а крестик — под переключатель подложек.
  var LEFT = 52, RIGHT = 66;
  function popupOptions() {
    var room = map.getSize().x - LEFT - RIGHT - 28;
    return {maxWidth: Math.max(140, Math.min(280, room)), minWidth: Math.max(110, Math.min(180, room)),
            autoPanPaddingTopLeft: L.point(LEFT, 10), autoPanPaddingBottomRight: L.point(RIGHT, 10),
            className: 'afisha-popup'};
  }
  function opened() { return !wrap || !toggle || wrap.classList.contains('open') || getComputedStyle(toggle).display === 'none'; }
  function refresh() {
    cluster.clearLayers();
    byId = {};
    var pts = [], opts = popupOptions();
    Array.prototype.forEach.call(page.querySelectorAll('.afisha-item[data-lat]'), function (li) {
      if (li.hidden) return;
      var ll = [+li.getAttribute('data-lat'), +li.getAttribute('data-lon')];
      var cls = li.classList.contains('now-last') ? ' afisha-dot-last' : li.classList.contains('now-soon') ? ' afisha-dot-soon' : '';
      var a = li.querySelector('.afisha-title a'), dist = li.querySelector('.afisha-dist');
      var m = L.marker(ll, {title: a.textContent, icon: L.divIcon({className: 'afisha-dot' + cls, iconSize: [16, 16]})});
      m.bindPopup('<b><a href="#' + li.id + '">' + esc(a.textContent) + '</a></b>' +
        '<span class="popup-place">' + esc(li.querySelector('.afisha-place').textContent) +
        (dist ? ' · ' + esc(dist.textContent) : '') + '</span>' +
        '<span class="popup-when">' + esc(li.querySelector('.now-when').textContent || li.querySelector('.afisha-range').textContent) + '</span>' +
        (li.hasAttribute('data-approx') ? '<span class="popup-approx">место на карте приблизительное</span>' : '') +
        '<a class="popup-site" href="' + esc(a.getAttribute('href')) + '" target="_blank" rel="noopener">Сайт выставки ↗</a>', opts);
      cluster.addLayer(m);
      byId[li.id] = m;
      pts.push(ll);
    });
    if (wrap) wrap.hidden = !pts.length;
    if (toggle) toggle.querySelector('.visit-count').textContent = pts.length;
    if (!pts.length || !opened()) return;
    map.invalidateSize();
    // Без анимации: переключили вкладку — карта сразу на месте, и щелчок
    // «на карте» не попадает на середину чужого перелёта.
    if (me) {
      // «Рядом со мной»: вы и три ближайшие выставки.
      var near = pts.slice().sort(function (p, q) { return me.getLatLng().distanceTo(p) - me.getLatLng().distanceTo(q); }).slice(0, 3);
      map.fitBounds(L.latLngBounds(near.concat([me.getLatLng()])).pad(0.25), {maxZoom: 13, animate: false});
    } else if (pts.length === 1) map.setView(pts[0], 12, {animate: false});
    else map.fitBounds(L.latLngBounds(pts).pad(0.12), {maxZoom: 11, animate: false});
  }
  function open(on) {
    if (!wrap || !toggle) return;
    wrap.classList.toggle('open', on);
    toggle.setAttribute('aria-expanded', on ? 'true' : 'false');
    toggle.querySelector('.afisha-map-label').textContent = on ? 'Скрыть карту' : 'Показать на карте';
    if (on) refresh();
  }
  if (toggle) toggle.addEventListener('click', function () { open(!wrap.classList.contains('open')); });
  page.addEventListener('afisha:shown', refresh);
  page.addEventListener('afisha:near', function (e) {
    if (me) { map.removeLayer(me); me = null; }
    if (e.detail) {
      me = L.circleMarker([e.detail.lat, e.detail.lon], {radius: 8, weight: 3, color: '#fff', fillColor: '#2563eb', fillOpacity: 1})
        .bindTooltip('Вы здесь').addTo(map);
    }
    refresh();
  });
  map.on('resize', function () {
    var o = popupOptions();
    Object.keys(byId).forEach(function (id) {
      var p = byId[id].getPopup();
      if (!p) return;
      p.options.maxWidth = o.maxWidth;
      p.options.minWidth = o.minWidth;
      if (p.isOpen()) p.update();
    });
  });
  page.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('.afisha-pin');
    if (!b) return;
    if (!opened()) open(true);               // на телефоне карта свёрнута — сначала развернуть
    var m = byId[b.closest('.afisha-item').id];
    if (!m) return;
    // Прокрутка — сразу, без плавности: пока страница плавно едет,
    // анимация приближения у группировки меток не всегда доходит до конца.
    el.scrollIntoView({block: 'center'});
    var done = false;
    function openIt() { if (!done) { done = true; m.openPopup(); } }
    if (!cluster.zoomToShowLayer) { map.setView(m.getLatLng(), 13); openIt(); return; }
    cluster.zoomToShowLayer(m, openIt);
    // Несколько выставок в одном здании (пять в Третьяковке) — одна точка.
    // Если карта уже на самом крупном масштабе, группировка не всегда сама
    // раскрывает такую стопку, — раскрываем сами и открываем подсказку.
    setTimeout(function () {
      if (done) return;
      var parent = cluster.getVisibleParent && cluster.getVisibleParent(m);
      if (parent && parent !== m && parent.spiderfy) { cluster.once('spiderfied', openIt); parent.spiderfy(); }
      else openIt();
    }, 1200);
  });
  refresh();
  el.afishaMap = map;   // для проверок
  el.afishaCluster = cluster;
})();
"""


def _options(pairs, all_label):
    """<option> для выпадающего списка; числа рядом с пунктами ставит скрипт."""
    out = [f'<option value="all" data-label="{h(all_label)}">{h(all_label)}</option>']
    out += [f'<option value="{h(k)}" data-label="{h(label)}">{h(label)}</option>' for k, label in pairs]
    return "".join(out)


@tidy
def render_afisha_page(items, updated="", known=(), today=None, coords=None, index=None, visited=None):
    """Страница afisha.html.

    coords — {id: (широта, долгота, приблизительно)} для карты и «рядом со
    мной»; index — works_index(всех работ) для «На сайте: …»; visited —
    {id: поход} для «Был — снимки и впечатления».
    """
    today = today or date.today()
    known = set(known or ())
    coords = coords or {}
    visited = visited or {}
    parts = split(items, today)
    running = sorted(parts["russia"]["running"] + parts["world"]["running"], key=lambda x: x["end"])
    soon = sorted(parts["russia"]["soon"] + parts["world"]["soon"], key=lambda x: x["start"])
    live = running + soon
    n_ru = len(parts["russia"]["running"]) + len(parts["russia"]["soon"])
    n_world = len(parts["world"]["running"]) + len(parts["world"]["soon"])
    countries = sorted({it["country"] for it in live if region(it) == "world"},
                       key=lambda c: (-sum(1 for it in live if it["country"] == c), c))
    used_tags = {t for it in live for t in it.get("tags") or []}
    area_select = _options(AREAS, "Все города")
    country_select = _options([(c, c) for c in countries], "Все страны")
    epoch_select = _options([(k, label) for k, label in EPOCHS if k in used_tags], "Все эпохи")
    upd = _iso(updated)
    upd_text = f"Список обновлён {ru_date(upd)}. " if upd else ""
    has_map = any(it["id"] in coords for it in live)
    head = head_common(
        title="Афиша: выставки в России и в мире — Old Picture Art",
        description=("Крупные выставки искусства до 1940 года в музеях России и мира: что идёт сейчас "
                     "и что скоро откроется — старые мастера, XIX век, импрессионисты, модерн и авангард."),
        canonical=f"{BASE_URL}/{AFISHA_PAGE}",
        extra=(("\n" + LEAFLET_CSS + '\n<link rel="stylesheet" href="vendor/leaflet.markercluster/MarkerCluster.css">')
               if has_map else "") + afisha_jsonld(live, coords),
    )
    map_html = ('<div class="afisha-map-wrap" id="afisha-map-wrap">'
                '<button type="button" class="afisha-map-toggle" id="afisha-map-toggle" aria-expanded="false" '
                'aria-controls="afisha-map"><span class="afisha-map-label">Показать на карте</span>'
                f'<span class="visit-count">{sum(1 for it in live if it["id"] in coords)}</span></button>'
                '<section class="afisha-map mini-map" id="afisha-map" aria-label="Выставки на карте"></section>'
                '</div>' if has_map else "")
    map_js = (LEAFLET_JS + '\n<script src="vendor/leaflet.markercluster/leaflet.markercluster.js"></script>'
              '\n<script src="map-config.js"></script>\n<script>' + MAP_LAYERS_JS + AFISHA_MAP_JS + '</script>'
              if has_map else "")
    near_btn = ('<button type="button" class="afisha-near-btn" id="afisha-near-btn" aria-pressed="false">'
                'Рядом со мной</button>' if has_map else "")
    index = index or {}

    def row(it):
        return afisha_item(it, known, coords.get(it["id"]), site_works(it, index), visited.get(it["id"]))

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
  <div class="visit-bar afisha-bar">
    <div class="view-switch afisha-switch" role="group" aria-label="Где">
      <button type="button" data-region="russia" aria-pressed="true">Россия<span class="visit-count">{n_ru}</span></button>
      <button type="button" data-region="world" aria-pressed="false">Мир<span class="visit-count">{n_world}</span></button>
    </div>
    <div class="afisha-filters">
      <label class="afisha-select" id="afisha-area-box"><span>Город</span><select id="afisha-area">{area_select}</select></label>
      <label class="afisha-select" id="afisha-country-box" hidden><span>Страна</span><select id="afisha-country">{country_select}</select></label>
      <label class="afisha-select"><span>Эпоха</span><select id="afisha-epoch">{epoch_select}</select></label>
      {near_btn}
    </div>
  </div>
  <p class="afisha-near-note" id="afisha-near" role="status" hidden></p>
</header>
<main id="afisha" class="afisha">
<section class="afisha-week" id="afisha-week" aria-labelledby="afisha-week-title" hidden>
<h2 class="now-title" id="afisha-week-title">Успеть на этой неделе</h2>
<ul class="afisha-week-list" id="afisha-week-list"></ul>
</section>
{map_html}
<section class="afisha-section" id="afisha-running-box" aria-labelledby="afisha-running-title">
<h2 class="museum-section" id="afisha-running-title">Идут сейчас</h2>
<ul class="afisha-list" id="afisha-running">{''.join(row(it) for it in running)}</ul>
</section>
<section class="afisha-section" id="afisha-soon-box" aria-labelledby="afisha-soon-title">
<h2 class="museum-section" id="afisha-soon-title">Скоро откроются</h2>
<ul class="afisha-list" id="afisha-soon">{''.join(row(it) for it in soon)}</ul>
</section>
<p class="no-results" id="afisha-empty" hidden>Под эти условия сейчас ничего не идёт — попробуйте другую эпоху или город.</p>
<p class="afisha-foot">{upd_text}Список собран по сайтам музеев; перед походом сроки и часы работы лучше проверить на странице выставки. «Рядом со мной» определяет, где вы, только в вашем браузере — на сайт это не передаётся.</p>
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


def check_afisha_links(items, today, offline=False, path=LINKS_FILE, check=None, log=logger):
    """Раз в LINKS_EVERY_DAYS (и только с сетью) проверяет ссылки выставок;
    о нерабочих напоминает в журнале при каждой сборке, пока их не поправят.

    Нерабочая — нет страницы (404), нет домена, не открывается. Переезд на
    другой адрес не считается: страница выставки при этом открывается.
    """
    state = load_json(path, {})
    urls = sorted({it["url"] for it in items})
    last = _iso(state.get("checked"))
    if urls and not offline and (not last or (today - last).days >= LINKS_EVERY_DAYS):
        log.info(f"Афиша: проверяю ссылки выставок — {len(urls)} (раз в неделю)")
        try:
            if check is None:
                from generate_map import check_site

                def check(u):
                    return check_site(u, timeout=15)
            from check_links import check_all
            results = check_all(urls, check)
        except Exception as e:                          # нет сети, нет модуля — в следующий раз
            log.info(f"Афиша: проверить ссылки не вышло ({e.__class__.__name__}) — в следующий раз")
            results = None
        if results is not None:
            state = {"checked": today.isoformat(),
                     "bad": {u: why for u, (st, why) in results.items() if st == "bad" and not why.startswith("уводит")}}
            save_json(path, state)
    bad = state.get("bad") or {}
    for it in items:
        if it["url"] in bad:
            log.warning(f"Афиша: ссылка не работает — «{it['title']}»: {it['url']} ({bad[it['url']]}). "
                        f"Поправьте url в {AFISHA_FILE}")
    return bad


def generate_afisha(known=(), today=None, path=AFISHA_FILE, offline=False, places=PLACES_FILE,
                    all_posts=None, visits=None, links=LINKS_FILE):
    """Пишет docs/afisha.html. Возвращает число идущих и будущих выставок.

    known — названия мест с карты собраний: у записи с полем museum из
    этого списка появляется ссылка на страницу музея на сайте, а метка на
    карте афиши берёт его координаты. Остальные места ищутся (locate);
    offline=True — только то, что уже найдено, и ссылки не проверяются.
    all_posts — для «На сайте: …», visits — для «Был — снимки».
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
    index = works_index(all_posts)
    visited = match_visits(live_items, visits)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_afisha_page(items, updated, known, today, coords, index, visited))
    afisha_report(items, errors, updated, today)
    check_afisha_links(live_items, today, offline, links)
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
    'ru_date', 'date_range', 'split', 'where_line', 'museum_link', 'afisha_item', 'museum_afisha_block', 'MUSEUM_AFISHA_JS', 'afisha_block',
    'AFISHA_JS', 'AFISHA_MAP_JS', 'PLACES_FILE', 'place_key', 'locate', 'render_afisha_page', 'afisha_report',
    'generate_afisha', 'EPOCHS', 'LINKS_FILE', 'LINKS_EVERY_DAYS', 'COMMON_SURNAMES', 'SURNAME_ALIASES',
    'artist_keys', 'works_index', 'site_works', 'works_html', 'match_visits', 'afisha_jsonld', 'check_afisha_links',
]
