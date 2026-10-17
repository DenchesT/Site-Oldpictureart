# -*- coding: utf-8 -*-
"""Адреса страниц: латинские имена файлов, переезды страниц и перенаправления.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
import re
import json
import difflib
import unicodedata
import urllib.parse
from html import escape as h
from site_common import (BASE_URL, work_year, latin_slug)
import logging
from .config import OUTPUT_DIR
from .text import slugify

logger = logging.getLogger("build_site")

# ======================================================================
#                        АДРЕСА СТРАНИЦ
# ======================================================================
#
# Имена страниц были кириллические: 2025-11-07-фрэнсис-кэмпбелл-буало-каделл.html.
# В адресной строке браузер показывает их по-человечески, но стоит ссылку
# скопировать — и она превращается в
# %D1%84%D1%80%D1%8D%D0%BD%D1%81%D0%B8%D1%81-… длиной 341 знак. Именно в
# таком виде ссылка уходит в переписку, в канал и в чужие письма.
#
# Второе: в имени стояла дата публикации в канале и имя художника. Дата
# посетителю ничего не говорит — его интересует не когда вы это выложили,
# а что на картине. Название работы в адресе не упоминалось вовсе.
#
# Стало: <фамилия>-<название>-<год>. Фамилия западных художников берётся
# из тегов самого канала (#renoir, #sisley) — там она уже записана так,
# как её пишут в мире. Обратная транслитерация с русской транскрипции
# дала бы «renuar» и «pussen», по которым художника не узнать.

def looks_latin(text):
    """Записано ли слово латиницей — с поправкой на надстрочные знаки.

    rusiñol и café написаны латиницей: ñ и é раскладываются на обычную
    букву плюс знак. А вот «сonstable» из тегов канала только выглядит
    латинским — первая буква там русская «с», это опечатка. Буквальная
    транслитерация превратила бы её в «sonstable» и увековечила описку
    в адресе страницы.
    """
    bare = "".join(c for c in unicodedata.normalize("NFKD", text or "")
                   if not unicodedata.combining(c))
    return bool(bare) and bare.isascii()


def surname_of(artist):
    """Фамилия из имени художника: последнее слово до скобки или запятой."""
    a = re.sub(r"\(.*?\)", "", artist or "").split(",")[0].strip()
    words = [w for w in a.split() if len(w) > 1]
    return words[-1] if words else a


# Заполняется один раз за сборку в prepare_slugs(): имена страниц
# художников нужны в десятке мест, и таскать словарь через все вызовы
# было бы хуже, чем держать его здесь.
_ARTIST_LATIN = {}


def fix_work_years(all_posts):
    """Пересчитывает год создания у уже скачанных записей. Возвращает,
    сколько записей поправлено.

    Год раньше брался как первое четырёхзначное число в названии, и у
    работ, в названии которых есть дата события, годом становилось само
    событие: «Парад на Красной площади 7 ноября 1941 года, 1949» стоял в
    таймлайне и статистике в 1941-м. Разбор поправлен, а записи, скачанные
    до этого, чинятся здесь — без похода в Telegram. Вместе с годом
    меняется и адрес страницы (год — его последняя часть); прежний адрес
    остаётся перенаправлением.
    """
    fixed = 0
    for post in all_posts:
        year = work_year(post.get("title"))
        if year != post.get("creation_year"):
            logger.info(f"Год создания: {post.get('creation_year')} → {year} — {post.get('title', '')[:70]}")
            post["creation_year"] = year
            fixed += 1
    return fixed


def prepare_slugs(all_posts):
    """Считает латинские имена художников. Вызывать до генерации страниц."""
    _ARTIST_LATIN.clear()
    _ARTIST_LATIN.update(artist_latin_map(all_posts))
    return _ARTIST_LATIN


def tag_slug(tag):
    """Имя страницы тега.

    Тег, записанный обычной латиницей, остаётся ровно таким, как есть —
    вместе с заглавными буквами. Приводить его к нижнему регистру было
    ошибкой: #vonAlt и #Mulot_Durivage превращались в tag-vonalt.html,
    и на Windows это тот же самый файл, что и прежний tag-vonAlt.html.
    Сборка писала страницу и перенаправление в один файл, из репозитория
    уезжало что-то одно, а GitHub Pages, где регистр различается, отдавал
    на другое имя «страница не найдена».

    Плюс к тому это лишний переезд: адреса 82 тегов и без того были
    нормальными, менять их было незачем.

    Переводятся только те, где латиницы недостаточно: русские теги и
    те, где затесались ñ, ü, é — в ссылке они всё равно превращаются
    в проценты.
    """
    tag = (tag or "").strip()
    if tag and tag.isascii() and re.fullmatch(r"[A-Za-z0-9._~-]+", tag):
        return tag
    return latin_slug(tag, 48) or "tag"


def artist_latin_map(all_posts):
    """Художник → фамилия латиницей.

    Сначала ищем в тегах поста латинское слово: канал помечает работы
    настоящей фамилией автора (#caillebotte, #friedrich), и это куда
    лучше, чем переложить обратно русскую транскрипцию. Для русских
    художников латинского тега нет — там транслитерация и уместна.

    Однофамильцев разводим отчеством или именем, иначе две разные
    страницы претендовали бы на один адрес.
    """
    chosen = {}
    for p in all_posts:
        artist = (p.get("artist") or "").strip()
        if not artist or artist in chosen:
            continue
        # Теги идут по алфавиту, и брать первый латинский нельзя: у
        # работы из Прадо тег музея окажется раньше фамилии, и в адрес
        # уедет «prado-ploschad-parizha». Поэтому тег не берётся, а
        # опознаётся: он должен быть похож на фамилию художника, как
        # caillebotte похож на «кайботт», а poussin — на «пуссен».
        ru_surname = latin_slug(surname_of(artist), 40)
        ru_full = latin_slug(artist, 60)
        # Теги приводим к латинице до сравнения, а не отбираем заранее
        # «только латинские»: в канале попадаются rusiñol с испанской
        # буквой и сonstable, у которого первая буква русская «с». По
        # виду они латинские, по кодам — нет, и такой отбор их терял.
        best, score = "", 0.0
        for t in p.get("tags", []):
            t = t.strip()
            if not t or t == "картина" or t.isdigit() or not looks_latin(t):
                continue
            cand = latin_slug(t, 40)
            if not cand:
                continue
            near = max(difflib.SequenceMatcher(None, cand, ru_surname).ratio(),
                       difflib.SequenceMatcher(None, cand, ru_full).ratio())
            if near > score:
                best, score = cand, near

        # Запятая в имени означает, что авторов несколько: «Анонимные
        # художники, Феликс Огюстен Милиус, Александр-Огюст Розе, …».
        # Фамилии у такой записи нет — разбор выдаёт «hudozhniki», — и
        # выбирать из нескольких авторов одного было бы неправдой.
        # Такие страницы называются по самой работе, без автора.
        if "," in (artist or ""):
            chosen[artist] = best if score >= 0.6 else ""
        else:
            chosen[artist] = (best if score >= 0.45 else "") or ru_surname or "author"

    taken = {}
    for artist in sorted(chosen):
        base = chosen[artist]
        if base not in taken:
            taken[base] = artist
            continue
        extra = latin_slug(" ".join((artist or "").split()[:-1]), 18)
        name, n = (f"{base}-{extra}" if extra else base), 2
        while name in taken:
            name = f"{base}-{n}"
            n += 1
        taken[name] = artist
        chosen[artist] = name
    return chosen


def work_title_slug(title):
    """Название работы для адреса.

    В базе название хранится как в канале: «Les Fiancés (Пара), около
    1868» — сначала на языке оригинала, в скобках по-русски, в конце год.
    Для адреса берём русскую часть (сайт русский), а год отрезаем: он
    станет отдельным куском имени и дважды в адресе не нужен.
    """
    t = title or ""
    m = re.search(r"\(([^)]*[А-Яа-яЁё][^)]*)\)", t)
    if m:
        t = m.group(1)
    t = re.sub(r",?\s*(около\s*|ок\.\s*|до\s*|после\s*)?\d{3,4}\s*(?:[–—-]\s*\d{2,4})?\s*$", "", t)
    return latin_slug(t, 48)


def post_slug(post, artists):
    """Имя страницы работы: фамилия-название-год."""
    parts = []
    author = artists.get((post.get("artist") or "").strip())
    if author:
        parts.append(author)
    title = work_title_slug(post.get("title"))
    if title:
        parts.append(title)
    if not parts:
        parts.append("kartina")
    year = post.get("creation_year")
    if year:
        parts.append(str(year))
    return "-".join(parts)


def rename_pages(all_posts, visits=None):
    """Переводит имена страниц на латиницу. Возвращает True, если что-то
    изменилось.

    Прежнее имя не выбрасывается, а копится в old_filenames: по нему
    потом кладётся страница-перенаправление. Ссылку на картину могли
    уже отправить в переписке, и превращать её в «страница не найдена»
    нельзя. Список именно список: если имя поменяется ещё раз, обе
    прежние ссылки должны продолжать работать.

    Вызывать можно сколько угодно раз: если имя уже правильное, функция
    ничего не трогает.
    """
    artists = artist_latin_map(all_posts)
    taken = set()
    changed = False

    for post in all_posts:
        base = post_slug(post, artists)
        name, n = f"{base}.html", 2
        while name in taken:
            name = f"{base}-{n}.html"
            n += 1
        taken.add(name)
        old = post.get("filename")
        if old and old != name:
            history = post.setdefault("old_filenames", [])
            if old not in history:
                history.append(old)
            changed = True
        if old != name:
            post["filename"] = name
            changed = True

    for visit in (visits or []):
        base = "visit-" + "-".join(x for x in (
            visit.get("date", ""), latin_slug(visit_heading(visit), 48)) if x)
        name, n = f"{base}.html", 2
        while name in taken:
            name = f"{base}-{n}.html"
            n += 1
        taken.add(name)
        old = visit.get("filename")
        if old and old != name:
            history = visit.setdefault("old_filenames", [])
            if old not in history:
                history.append(old)
            changed = True
        if old != name:
            visit["filename"] = name
            changed = True

    return changed


def legacy_post_names(all_posts):
    """Прежние имена страниц работ, восстановленные по самим записям.

    Зачем восстанавливать, а не читать из old_filenames: история имён
    появляется в базе только в тот прогон, который переименовывает. Если
    переименование уже прошло, а база до перенаправлений не дожила —
    сборкой с чужой машины, откатом файла, чем угодно, — то 88 адресов,
    которые люди могли отправить друг другу, молча превращаются в
    «страница не найдена», и восстановить их будет уже неоткуда.

    Имя считалось как <дата поста>-<имя художника>, а повторы в тот же
    день получали -2, -3. Правило простое и обратимое, поэтому прежний
    адрес выводится из даты и художника — так же, как у страниц тегов
    и художников он выводится из тега и имени.
    """
    seen, out = {}, {}
    for post in all_posts:
        base = f"{post.get('date', '')}-{slugify(post.get('artist', ''))}"
        seen[base] = seen.get(base, 0) + 1
        n = seen[base]
        out[f"{base}.html" if n == 1 else f"{base}-{n}.html"] = post.get("filename")
    return out


def write_redirect(old_name, new_name):
    """Кладёт на прежний адрес страницу-перенаправление.

    Без noindex, хотя он тут просится. Google считает мгновенный
    meta refresh обычным постоянным переездом, и страница-перенаправление
    в указатель не попадает сама по себе. А вот noindex рядом с canonical
    — это два противоречащих указания на одной странице: «этой страницы в
    поиске быть не должно» и «настоящая страница вот эта, перенеси на неё
    всё накопленное». Разбирая противоречие, поисковик может отнести
    запрет к той самой странице, на которую мы переносим. В отчёте Google
    такие адреса и всплыли — в разделе «запрещено тегом noindex».
    """
    target = urllib.parse.quote(new_name)
    with open(os.path.join(OUTPUT_DIR, old_name), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"""<!DOCTYPE html><html lang="ru"><head>
<meta charset="UTF-8">
<link rel="canonical" href="{BASE_URL}/{target}">
<meta http-equiv="refresh" content="0; url={target}">
<title>Страница переехала</title>
</head><body>
<p>Страница переехала: <a href="{target}">{h(new_name)}</a></p>
<script>location.replace({json.dumps(target)});</script>
</body></html>""")


def retire_pages(prefix, live, legacy):
    """Прибирает страницы с приставкой prefix, которых больше нет.

    legacy — {прежнее имя: нынешнее}. Перенаправление по таким адресам
    кладётся всегда, а не только если прежний файл ещё лежит в папке:
    иначе сборка с нуля — и все прежние ссылки разом превращаются в
    «страница не найдена». Имена тегов и художников считаются из данных,
    так что прежний адрес известен и без файла на диске.

    Всё прочее с этой приставкой — след исчезнувшего тега или ушедшего
    художника, такое убирается совсем.
    """
    live_ci = {n.lower() for n in live}
    moved = removed = 0
    for old_name, new_name in legacy.items():
        # Различие только в регистре — не переезд. На Windows это один и
        # тот же файл, и перенаправление затёрло бы саму страницу.
        if (old_name in live or new_name not in live
                or old_name.lower() in live_ci):
            continue
        write_redirect(old_name, new_name)
        moved += 1
    keep = live_ci | {n.lower() for n in legacy}
    for name in os.listdir(OUTPUT_DIR):
        if name.startswith(prefix) and name.endswith(".html") and name.lower() not in keep:
            os.remove(os.path.join(OUTPUT_DIR, name))
            removed += 1
    return moved, removed


def generate_redirects(all_posts, visits=None):
    """Страницы-перенаправления на прежних адресах.

    GitHub Pages раздаёт файлы и ничего не умеет перенаправлять на своей
    стороне, поэтому перенаправление приходится класть страницей. В ней
    три способа сразу: canonical — чтобы поисковик понял, какой адрес
    настоящий, и перенёс на него всё, что успел накопить; meta refresh —
    чтобы сработало без скриптов; и строчка на javascript, которая
    уводит мгновенно и, в отличие от meta refresh, не засоряет кнопку
    «назад».
    """
    live = {r.get("filename") for r in list(all_posts) + list(visits or [])}
    moves = dict(legacy_post_names(all_posts))
    for rec in list(all_posts) + list(visits or []):
        for old in rec.get("old_filenames", []):
            moves[old] = rec.get("filename")

    made = 0
    for old, new in moves.items():
        if (not old or not new or old == new or "/" in old
                or not old.endswith(".html") or old in live):
            continue
        write_redirect(old, new)
        made += 1
    if made:
        logger.info(f"Перенаправлений со старых адресов: {made}")
    return made

def surname_key(n):
    """Ключ сортировки по фамилии. У однофамильцев (два Мартена) дальше
    решает полное имя: иначе порядок зависел от случайного порядка в
    множестве, и страницы менялись от сборки к сборке без всякой правки."""
    f = n.split(",")[0].strip()
    w = f.split()
    return (w[-1].lower() if w else n.lower()) + "\0" + n.lower()


def artist_slug(name):
    """Имя страницы художника.

    Берётся та же фамилия, что и в адресах его работ, — чтобы
    renoir-para-1868.html и artist-renoir.html читались как одно
    семейство, а не как два разных способа записать человека.
    """
    key = _ARTIST_LATIN.get((name or "").strip()) or latin_slug(surname_of(name), 40)
    return "artist-" + (key or "author") + ".html"


def visit_filename(visit):
    """Имя страницы похода. Дата записи впереди, чтобы соседние походы
    в одно место не сливались в одно имя.

    Латиницей — по той же причине, что и остальные адреса. Важно, что
    здесь тот же расчёт, что и в rename_pages: refresh_visits зовётся
    при каждой пересборке и переписывает имя заново, и разойдись эти
    два места — страница переезжала бы туда-сюда каждую сборку."""
    return f"visit-{visit.get('date', '')}-{latin_slug(visit_heading(visit), 48)}.html"


def visit_heading(v):
    """Чем подписан поход: названием выставки или названием музея."""
    return (v.get("title") or v.get("place") or "Посещение").strip()

__all__ = [
    'looks_latin',
    'surname_of',
    '_ARTIST_LATIN',
    'fix_work_years',
    'prepare_slugs',
    'tag_slug',
    'artist_latin_map',
    'work_title_slug',
    'post_slug',
    'rename_pages',
    'legacy_post_names',
    'write_redirect',
    'retire_pages',
    'generate_redirects',
    'surname_key',
    'artist_slug',
    'visit_filename',
    'visit_heading',
]
