# -*- coding: utf-8 -*-
"""Годы жизни художника и статья о нём в Википедии — из Wikidata.

В канале у художника только имя. Годы жизни и ссылку на Википедию сборка
находит сама и запоминает в artist_info.json:

    "Клод Моне": {"wikidata": "Q296", "born": 1840, "died": 1926,
                  "wikipedia": "https://ru.wikipedia.org/wiki/Моне,_Клод",
                  "checked": "2026-10-17"}

Художника ищет тот же поиск, что и квиз (generate_quiz.find_artist): по
полному имени, по короткому, по фамилии среди живописцев, с проверкой,
что годы работ укладываются в годы жизни. Если номер записи уже известен
квизу (artist_schools.json), поиск не нужен.

artist_info.json — и кэш, и файл поправок: вписанные руками "born",
"died" и "wikipedia" главнее найденного, и такую запись сборка больше не
переспрашивает. Не нашёлся — переспросит через месяц. Статья — русская,
а если её нет — английская.
"""

import datetime
import json
import logging
import re
import urllib.parse

logger = logging.getLogger("build_site")

INFO_FILE = "artist_info.json"
SCHOOLS_FILE = "artist_schools.json"
RETRY_DAYS = 30


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def wikipedia_url(sitelinks):
    """Ссылка на статью: русская, а если её нет — английская."""
    for site, host in (("ruwiki", "ru.wikipedia.org"), ("enwiki", "en.wikipedia.org")):
        title = ((sitelinks or {}).get(site) or {}).get("title")
        if title:
            return f"https://{host}/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    return ""


def year_of(claims, prop):
    """Год из даты Wikidata («+1840-11-14T00:00:00Z» → 1840)."""
    for c in (claims or {}).get(prop) or []:
        if c.get("rank") == "deprecated":
            continue
        value = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict):
            m = re.match(r"([+-])(\d{1,4})-", value.get("time", ""))
            if m:
                return int(m.group(2)) * (-1 if m.group(1) == "-" else 1)
    return None


def info_from_entity(entity):
    """Запись для artist_info.json из записи Wikidata."""
    claims = entity.get("claims") or {}
    return {"wikidata": entity.get("id"),
            "born": year_of(claims, "P569"),
            "died": year_of(claims, "P570"),
            "wikipedia": wikipedia_url(entity.get("sitelinks"))}


def fetch_entity(qid, wd):
    """Запись по номеру — с годами и ссылками на статьи."""
    data = wd({"action": "wbgetentities", "ids": qid, "props": "claims|sitelinks",
               "sitefilter": "ruwiki|enwiki"})
    entity = (data.get("entities") or {}).get(qid) or {}
    return entity if entity.get("claims") is not None else None


def lookup(artist, year, qid=None, quiz=None):
    """Сведения о художнике из сети. Ошибки сети не глотаются."""
    if quiz is None:
        import generate_quiz as quiz
    if not qid:
        found = quiz.find_artist(artist, year)
        qid = found.get("id") if found else None
    if not qid:
        return {"wikidata": None, "born": None, "died": None, "wikipedia": ""}
    entity = fetch_entity(qid, quiz._wd)
    return info_from_entity(entity) if entity else {"wikidata": qid, "born": None, "died": None, "wikipedia": ""}


def resolve(artists_years, offline=False, today=None, quiz=None, log=logger.info):
    """{художник: сведения} для всех художников сайта; дополняет INFO_FILE.

    artists_years — {имя: год середины его работ или None}: по нему поиск
    отличает художника от тёзки из другого века.
    """
    today = today or datetime.date.today()
    cache = _load(INFO_FILE, {})
    known_ids = {name: (rec or {}).get("wikidata") for name, rec in _load(SCHOOLS_FILE, {}).items()}
    out, changed, network_down, asked = {}, False, offline, 0

    def pending(artist):
        entry = cache.get(artist) or {}
        if entry.get("born") or entry.get("wikipedia"):
            return False
        try:
            return (today - datetime.date.fromisoformat(entry["checked"])).days >= RETRY_DAYS
        except (KeyError, TypeError, ValueError):
            return True

    todo = sum(1 for a in artists_years if pending(a))
    if todo and not offline:
        log(f"Художники: ищу годы жизни и статьи в Wikidata — {todo} "
            f"(один раз; первый раз это пара минут)")
    for artist in sorted(artists_years):
        entry = cache.get(artist) or {}
        if entry.get("born") or entry.get("wikipedia"):
            out[artist] = entry
            continue
        checked = entry.get("checked")
        fresh = False
        if checked:
            try:
                fresh = (today - datetime.date.fromisoformat(checked)).days < RETRY_DAYS
            except ValueError:
                pass
        if network_down or fresh:
            out[artist] = entry
            continue
        try:
            found = lookup(artist, artists_years[artist], entry.get("wikidata") or known_ids.get(artist), quiz)
        except Exception as e:                       # сети нет, сервер не ответил
            log(f"Художники: Wikidata недоступна ({e.__class__.__name__}) — "
                f"годы жизни остальных найду в следующий раз")
            network_down = True
            out[artist] = entry
            continue
        asked += 1
        entry = dict(found, checked=today.isoformat())
        cache[artist] = entry
        out[artist] = entry
        changed = True
        if not (found.get("born") or found.get("wikipedia")):
            log(f"Художники: «{artist}» в Wikidata не нашёлся — годы жизни и ссылку можно "
                f'вписать в {INFO_FILE}: "{artist}": {{"born": 1840, "died": 1926, '
                f'"wikipedia": "https://ru.wikipedia.org/wiki/…"}}')
    if changed:
        with open(INFO_FILE, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    if asked:
        log(f"Художники: сведения из Wikidata — {asked}")
    return out


def life_years(info):
    """«1840–1926», «род. 1953», «ум. 1890» или пусто."""
    born, died = (info or {}).get("born"), (info or {}).get("died")
    if born and died:
        return f"{born}–{died}"
    if born:
        return f"род. {born}"
    if died:
        return f"ум. {died}"
    return ""


def wiki_host(url):
    """«ru.wikipedia.org» — подпись к ссылке."""
    return urllib.parse.urlsplit(url or "").netloc


def artists_years(all_posts):
    """{художник: год середины его работ} — подсказка поиску."""
    years = {}
    for p in all_posts or []:
        name = (p.get("artist") or "").strip()
        if name:
            years.setdefault(name, [])
            if p.get("creation_year"):
                years[name].append(p["creation_year"])
    return {a: (sorted(ys)[len(ys) // 2] if ys else None) for a, ys in years.items()}


__all__ = [
    'INFO_FILE', 'SCHOOLS_FILE', 'RETRY_DAYS', 'wikipedia_url', 'year_of', 'info_from_entity',
    'fetch_entity', 'lookup', 'resolve', 'life_years', 'wiki_host', 'artists_years',
]
