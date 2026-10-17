# -*- coding: utf-8 -*-
"""Обновление уже собранного: перечитать тексты, «--refresh» для правленого поста, оригиналы.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
import re
import sys
import hires_store
from site_common import (VISITS_FILE)
import logging
from .config import META_FILE, OUTPUT_DIR, PROCESSED_FILE
from .text import parse_post
from .slugs import visit_filename
from .html import download_name
from .visits import parse_visit

logger = logging.getLogger("build_site")

def refresh_visits(visits):
    """Перечитывает сохранённые посещения тем разбором, что сейчас в коде.

    Текст поста лежит в базе целиком, поэтому чинить разбор можно не ходя
    в Telegram: скачанные снимки остаются на месте, обновляются только
    разобранные поля и имя файла страницы.
    """
    changed = 0
    for v in visits:
        raw = v.get("raw")
        if not raw:
            continue
        fresh = parse_visit(raw)
        if not fresh:
            continue
        if any(v.get(k) != val for k, val in fresh.items()):
            changed += 1
        v.update(fresh)
        # Имя считается заново из заголовка, поэтому прежнее надо
        # запомнить здесь: до rename_pages дело дойдёт, когда имя уже
        # будет новым, и перенаправлять станет не с чего.
        name = visit_filename(v)
        if v.get("filename") and v["filename"] != name:
            v.setdefault("old_filenames", []).append(v["filename"])
        v["filename"] = name
    if changed:
        logger.info(f"Посещения перечитаны заново: обновлено {changed}")
    return visits


# Поля, которые видно на карточке ссылки: изменились — карточку надо
# нарисовать заново, иначе в превью останется прежняя подпись.
CARD_FIELDS = ("artist", "title", "creation_year", "museum")


def refresh_posts(all_posts):
    """Перечитывает сохранённые посты тем разбором, что сейчас в коде.

    Текст поста лежит в базе целиком (поле raw), поэтому починить разбор
    или подправить текст можно не перекачивая снимки: обновляются только
    разобранные поля. Новое имя страницы посчитает rename_pages, а
    прежний адрес сам уйдёт в перенаправление.

    Текст в базе — тот, что был при скачивании. Если пост подправлен уже
    в канале, сперва притяните новый текст: python build_site.py --refresh …
    """
    changed = 0
    for post in all_posts:
        raw = post.get("raw")
        if not raw:
            continue
        fresh = parse_post(raw)
        if not fresh:
            logger.warning(f"Пост {post.get('filename', '?')} не разобрался — "
                           "оставляю как был")
            continue
        if not any(post.get(k) != v for k, v in fresh.items()):
            continue
        changed += 1
        if any(post.get(k) != fresh.get(k) for k in CARD_FIELDS):
            drop_card(post)
        post.update(fresh)
    if changed:
        logger.info(f"Посты перечитаны заново: обновлено {changed}")
    return changed


def drop_card(post):
    """Убирает карточку ссылки, чтобы её нарисовали заново.

    Файл именно удаляем: make_card отдаёт уже лежащую картинку, и без
    этого в превью осталась бы прежняя подпись — имя файла-то от имени
    страницы, а оно могло и не поменяться.
    """
    card = post.pop("card", None)
    if not card:
        return
    path = os.path.join(OUTPUT_DIR, card)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            logger.warning(f"Карточка {card} не удалилась: {e}")

# ======================================================================
#              ПРАВКА СТАРОГО ПОСТА:  python build_site.py --refresh
# ======================================================================
#
# Пост в канале можно подправить и через год после выхода, а сайт о
# правке не узнает: скачанные посты отсеиваются по processed_ids.json и
# второй раз не читаются. Ключ --refresh притягивает нынешний текст
# указанных постов, а разбор и страницы обновляются обычным ходом сборки.
#
#     python build_site.py --refresh 1234           # номер поста в канале
#     python build_site.py --refresh sisley-lug-1875.html   # или адрес страницы
#     python build_site.py --refresh "Union Square" # или кусок названия
#     python build_site.py --refresh               # все посты разом
#
# Снимки при этом не перекачиваются: правка подписи их не меняет.

REFRESH_FLAG = "--refresh"


def match_posts(all_posts, needle):
    """Посты, подходящие под одно слово из --refresh.

    Понимает номер поста, ссылку на канал, имя страницы (в том числе
    прежнее) и просто кусок имени художника или названия — чтобы не
    искать номер поста вручную.
    """
    n = (needle or "").strip()
    if not n:
        return []
    if n.isdigit():
        return [p for p in all_posts if str(p.get("id")) == n]
    m = re.search(r"t\.me/[^/]+/(\d+)", n)
    if m:
        return [p for p in all_posts if str(p.get("id")) == m.group(1)]
    name = n.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".html"):
        hit = [p for p in all_posts if p.get("filename") == name
               or name in (p.get("old_filenames") or [])]
        if hit:
            return hit
        name = name[:-5]
    low = name.lower()
    hit = [p for p in all_posts if p.get("filename", "")[:-5].lower() == low]
    if hit:
        return hit
    return [p for p in all_posts if low in
            f"{p.get('artist', '')} {p.get('title', '')} {p.get('place', '')} "
            f"{p.get('filename', '')}".lower()]


def refresh_targets(all_posts, argv=None):
    """Посты, у которых надо перечитать текст. None — ключа нет вовсе."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if REFRESH_FLAG not in argv:
        return None
    needles = []
    for a in argv[argv.index(REFRESH_FLAG) + 1:]:
        if a.startswith("--"):
            break
        needles.append(a)
    if not needles or any(a.lower() in ("all", "все") for a in needles):
        return list(all_posts)
    out = []
    for needle in needles:
        hit = match_posts(all_posts, needle)
        if not hit:
            logger.warning(f"--refresh {needle}: такого поста в базе нет")
        for p in hit:
            if p not in out:
                out.append(p)
    return out


def sync_hires(records):
    """Выгружает оригиналы в хранилище, если оно настроено.

    Ничего не настроено — молчим: хранилище необязательно. Указан адрес,
    но нет ключей или boto3 — говорим, чего не хватает: иначе оригиналы
    новых постов тихо копились бы в docs/images, и сайт снова пополз бы
    к пределу в 1 ГБ.
    """
    base, key_id, secret, missing = hires_store.settings()
    if not base:
        return None
    todo = hires_store.local_originals(records)
    if not todo:
        return None
    if missing:
        logger.warning(f"Оригиналов в docs/images: {len(todo)}, а выгрузить их нельзя — "
                       f"не хватает: {', '.join(missing)} (см. STORAGE_SETUP.md)")
        return None
    logger.info(f"Оригиналы в хранилище: {len(todo)}")
    bucket, prefix = hires_store.bucket_of(base)
    try:
        client = hires_store.make_client(key_id, secret)
    except Exception as e:
        logger.warning(f"Хранилище недоступно: {e} — оригиналы остаются в docs/images")
        return None
    stats = hires_store.sync(records, client, bucket, prefix, name_for=download_name,
                             log=logger.info)
    logger.info(f"   выгружено: {stats['uploaded']}, уже были: {stats['already']}, "
                f"ошибок: {stats['failed']}")
    return stats


def rebuild_reset():
    logger.warning("--rebuild: удаление старых страниц")
    if input("Продолжить? [y/N]: ").strip().lower() not in ("y","yes","д","да"): print("Отмена."); sys.exit(0)
    if os.path.isdir(OUTPUT_DIR):
        for n in os.listdir(OUTPUT_DIR):
            if n.endswith(".html") or n.endswith(".xml") or n == "feed.xml":
                os.remove(os.path.join(OUTPUT_DIR, n))
    for fn in (PROCESSED_FILE, META_FILE, VISITS_FILE):
        if os.path.exists(fn): os.remove(fn)

__all__ = [
    'refresh_visits',
    'CARD_FIELDS',
    'refresh_posts',
    'drop_card',
    'REFRESH_FLAG',
    'match_posts',
    'refresh_targets',
    'sync_hires',
    'rebuild_reset',
]
