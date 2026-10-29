# -*- coding: utf-8 -*-
"""Telegram: подключение, загрузка новых постов, снимков, правленых текстов и ссылок.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import asyncio
import os
import re
from datetime import datetime
import logging
from .config import API_HASH, API_ID, CHANNEL_URL, IMAGES_DIR, OUTPUT_DIR, PHONE
from .text import parse_post
from .links import clean_url
from .images import PIL_AVAILABLE, compress_if_huge, make_thumbnail
from .visits import VISIT_TAGS, parse_visit

logger = logging.getLogger("build_site")

try:
    from telethon import TelegramClient
    import TelethonFakeTLS
    from .telethon_compat import patch_faketls_wait_closed
    patch_faketls_wait_closed()
    TELETHON_AVAILABLE = True
except ImportError:
    TelegramClient = None
    TelethonFakeTLS = None
    TELETHON_AVAILABLE = False


def require_credentials():
    """Проверяем .env только перед походом в Telegram, а не при импорте файла."""
    if not (API_ID and API_HASH and PHONE):
        raise SystemExit("✕ Нужен .env с API_ID, API_HASH, PHONE")
    if not TELETHON_AVAILABLE:
        raise SystemExit("✕ Не установлены telethon / TelethonFakeTLS")
    logger.info("Учётные данные Telegram найдены")
    return int(API_ID), API_HASH, PHONE

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

async def connect_with_proxy(api_id, api_hash, phone, proxy_list):
    for i, cfg in enumerate(proxy_list, 1):
        logger.info(f"Прокси #{i}: {cfg['server']}:{cfg['port']}")
        try:
            client = TelegramClient(f"session_{i}", api_id, api_hash,
                connection=TelethonFakeTLS.ConnectionTcpMTProxyFakeTLS,
                proxy=(cfg['server'], cfg['port'], cfg['secret']))
            await client.start(phone=phone)
            logger.info(f"Подключено через прокси #{i}")
            return client
        except Exception as e:
            logger.error(f"Прокси #{i} не работает: {str(e)[:80]}")
    raise SystemExit("Все прокси не работают!")


async def download_with_retry(client, msg, fp, retries=3):
    for a in range(retries):
        try:
            await client.download_media(msg, fp)
            return True
        except Exception as e:
            if a < retries-1:
                logger.warning(f"Попытка {a+1} ({e.__class__.__name__}), жду...")
                await asyncio.sleep(5)
            else: raise
    return False

async def download_images(client, group, comments, slug, start=0):
    """start — сколько снимков у записи уже есть. Добавки к походу качаются
    отдельным заходом, и без сдвига они перезаписали бы первые файлы."""
    images, hires, thumbs = [], [], []
    idx = start
    for msg in group:
        if getattr(msg,"photo",None):
            idx += 1
            fn = f"{slug}-{idx}.jpg"
            fp = os.path.join(IMAGES_DIR, fn)
            if not os.path.exists(fp): await download_with_retry(client, msg, fp)
            images.append(f"images/{fn}")
            t = make_thumbnail(fp, slug, idx)
            if t: thumbs.append(t)
    docs = [m for m in group
            if (getattr(getattr(m, "document", None), "mime_type", "") or "")
            .startswith("image/")]
    docs.extend(comments)
    for i, msg in enumerate(docs, start + 1):
        ext = ".jpg"
        for attr in getattr(msg.document,"attributes",[]):
            if hasattr(attr,"file_name"): ext = os.path.splitext(attr.file_name)[1].lower(); break
        fn = f"{slug}-hires-{i}{ext}"
        fp = os.path.join(IMAGES_DIR, fn)
        if not os.path.exists(fp):
            try: await download_with_retry(client, msg, fp)
            except Exception as e:
                logger.error(f"Не скачан {msg.id}: {e}")
                continue
        fp = compress_if_huge(fp)
        hires.append(f"images/{os.path.basename(fp)}")
    if not images and hires:
        images = hires.copy()
        if PIL_AVAILABLE and not thumbs:
            for i, hr in enumerate(hires, start + 1):
                t = make_thumbnail(os.path.join(OUTPUT_DIR, hr), slug, i)
                if t: thumbs.append(t)
    return images, hires, thumbs

# ===================== TELEGRAM =====================

async def fetch_new_posts(client, processed_ids, full_scan=False, known_visits=None):
    """Возвращает три пачки: картины, новые посещения и добавки к прежним.

    В канале восемь хештегов, а сайт до сих пор понимал только #картина —
    остальные посты молча уходили в отбраковку. Теперь #выставка и #галерея
    разбираются своим разбором и живут в отдельном разделе; всё прочее
    по-прежнему пропускается.

    Отдельная забота — снимки без подписи. С похода привозят больше фото,
    чем влезает в один пост, и остальные идут следом отдельными записями
    без текста. Такой пост сам по себе ничего не значит, но относится
    к ближайшему посещению того же дня — к нему его и приписываем.
    """
    logger.info("Сканирую канал...")
    accepted, visits, extras_for_known = [], [], {}
    known = {v.get("id"): v for v in (known_visits or []) if v.get("id")}
    stats = {"total":0,"no_kartina_tag":0,"no_main_msg":0,"already_seen":0,
             "parse_failed":0,"visits":0,"extra_groups":0}
    sf = []
    # Канал читается от новых к старым, поэтому безымянные посты со снимками
    # встречаются РАНЬШЕ того посещения, к которому относятся. Копим их и
    # отдаём ближайшему посещению того же дня.
    pending = []

    def _day(msg):
        return msg.date.strftime("%Y-%m-%d")

    def _take_pending(anchor):
        """Забирает накопленные безымянные посты того же дня."""
        day = _day(anchor)
        # Канал читается от новых к старым, поэтому очередь накопилась
        # задом наперёд: разворачиваем, чтобы снимки легли в том порядке,
        # в котором их выложили.
        mine = [g for g in pending if _day(g[0]) == day][::-1]
        pending.clear()
        return mine

    def _pg(group):
        stats["total"] += 1
        group.reverse()
        ft, mm, vm = "", None, None
        for m in group:
            t = m.raw_text or ""
            if t: ft += t + "\n"
            low = t.lower()
            if "#картина" in low: mm = m
            if vm is None and any(f"#{tag}" in low for tag in VISIT_TAGS): vm = m

        # Посещение: пост о выставке или музее, а не о работе из собрания
        if not mm and vm:
            extra = _take_pending(vm)
            if vm.id in processed_ids:
                stats["already_seen"] += 1
                # Само посещение уже разобрано, но снимки к нему могли
                # появиться позже или просто не собирались раньше.
                if extra and vm.id in known:
                    extras_for_known.setdefault(vm.id, []).extend(extra)
                    stats["extra_groups"] += len(extra)
                return
            try:
                v = parse_visit(ft)
            except Exception as e:
                logger.error(f"Ошибка посещения {vm.id}: {e}"); v = {}
            if v:
                stats["visits"] += 1
                stats["extra_groups"] += len(extra)
                visits.append((vm, group, v, extra))
            else:
                stats["parse_failed"] += 1; sf.append(ft[:500])
            return

        if not mm:
            # Пост без подписи и со снимками — вероятная добавка к походу.
            # Оставляем в очереди до ближайшего посещения; любая запись
            # с текстом очередь обрывает: между постами дня она не тянется.
            if not ft.strip() and any(getattr(m, "photo", None) or getattr(m, "document", None) for m in group):
                pending.append(group)
            else:
                pending.clear()
            stats["no_main_msg"] += 1
            return

        pending.clear()
        if "#картина@oldpictureart" not in ft.lower(): stats["no_kartina_tag"] += 1; return
        if mm.id in processed_ids: stats["already_seen"] += 1; return
        try:
            p = parse_post(ft)
            if not p: stats["parse_failed"] += 1; sf.append(ft[:500]); return
            accepted.append((mm, group, p))
        except Exception as e:
            stats["parse_failed"] += 1
            logger.error(f"Ошибка поста {mm.id}: {e}")
            sf.append(ft[:500])

    # Обычно смотрим только то, что новее последнего разобранного поста.
    # Но посты #выставка и #галерея лежат в канале давно, а сайт их до сих
    # пор не понимал: при первом запуске с этой возможностью проходим канал
    # целиком, иначе прошлые походы так и останутся ненайденными.
    mid = 0 if full_scan else (max(processed_ids) if processed_ids else 0)
    if full_scan:
        logger.info("Полный проход по каналу: собираю прошлые походы и снимки к ним")
    cai, cg = None, []
    async for msg in client.iter_messages(CHANNEL_URL, min_id=mid):
        if msg.grouped_id:
            if cai == msg.grouped_id: cg.append(msg)
            else:
                if cg: _pg(cg)
                cai, cg = msg.grouped_id, [msg]
        else:
            if cg: _pg(cg); cg = []; cai = None
            _pg([msg])
    if cg: _pg(cg)
    logger.info(f"Новых постов: {len(accepted)}, посещений: {len(visits)}"
                + (f", добавок со снимками: {stats['extra_groups']}" if stats['extra_groups'] else "")
                + f". Всего проверено: {stats['total']}, обработано: {stats['already_seen']}, "
                f"не картина: {stats['no_main_msg']+stats['no_kartina_tag']}, ошибки: {stats['parse_failed']}")
    if sf:
        with open("rejected_posts.txt","w",encoding="utf-8", newline="\n") as f:
            f.write(f"# Отбракованные посты — {datetime.now():%Y-%m-%d %H:%M}\n\n")
            for i, s in enumerate(sf, 1): f.write(f"--- #{i} ---\n{s}\n\n")
        logger.info(f"rejected_posts.txt ({len(sf)} шт.)")
    return accepted[::-1], visits[::-1], extras_for_known


def message_links(msgs):
    """Ссылки, спрятанные под словами поста: [{text, url}].

    Берутся только ссылки-подписи (слово, под которым лежит адрес).
    Голые адреса в тексте и так попадают в urls, а хештеги и упоминания
    ссылками на сайт не являются. Адреса — только http(s): javascript:
    и прочее в страницу сайта не пускаем.
    """
    out, seen = [], set()
    for m in sorted(msgs or [], key=lambda x: getattr(x, "id", 0)):
        try:
            pairs = m.get_entities_text() or []
        except Exception:
            continue
        for ent, text in pairs:
            url = (getattr(ent, "url", None) or "").strip()
            text = re.sub(r"\s+", " ", text or "").strip()
            if not text or not url.lower().startswith(("http://", "https://")):
                continue
            url = clean_url(url)
            if (text, url) in seen:
                continue
            seen.add((text, url))
            out.append({"text": text, "url": url})
    return out


async def fetch_groups(client, records):
    """Забирает из канала посты записей вместе с их альбомами.

    Возвращает ({номер: [записи альбома по порядку]}, {номера, про которые
    канал ответил}). Второе нужно, чтобы отличить удалённый пост (канал
    ответил, а поста нет) от сбоя связи (не ответил вовсе): удалённый
    незачем спрашивать снова, а после сбоя — надо.
    """
    # Подпись в посте из нескольких снимков лежит на одном из них,
    # поэтому вокруг каждого номера берём небольшое окно: в альбоме
    # Телеграма не больше десяти записей.
    wanted = set()
    for rec in records:
        pid = rec.get("id")
        if pid:
            wanted.update(x for x in range(pid - 9, pid + 10) if x > 0)
    got, asked = {}, set()
    wanted = sorted(wanted)
    for i in range(0, len(wanted), 100):
        chunk = wanted[i:i + 100]
        try:
            for m in await client.get_messages(CHANNEL_URL, ids=chunk):
                if m:
                    got[m.id] = m
            asked.update(chunk)
        except Exception as e:
            logger.error(f"Не прочитались посты {chunk[0]}…: {e}")

    groups = {}
    for rec in records:
        main = got.get(rec.get("id"))
        if main is None:
            continue
        gid = getattr(main, "grouped_id", None)
        group = ([m for m in got.values() if getattr(m, "grouped_id", None) == gid]
                 if gid else [main])
        groups[rec["id"]] = sorted(group, key=lambda m: m.id)
    return groups, asked


async def refetch_texts(client, posts):
    """Притягивает из канала нынешний текст постов и ссылки в нём.

    Пост в канале мог поменяться, а снимки — нет, поэтому качаем только
    текст: разбор, имя страницы, карточка ссылки и сами страницы
    обновятся дальше обычным ходом сборки. Ссылки сверяются отдельно:
    поправить адрес под словом можно, не тронув ни буквы текста.
    """
    if not posts:
        return 0
    logger.info(f"Перечитываю текст постов: {len(posts)}")
    groups, _ = await fetch_groups(client, posts)

    changed = 0
    for i, post in enumerate(posts, 1):
        who = post.get("filename", "?")
        group = groups.get(post.get("id"))
        if not group:
            logger.warning(f"[{i}/{len(posts)}] {who}: поста {post.get('id')} "
                           "в канале нет — пропускаю")
            continue
        text = ""
        for m in group:
            t = m.raw_text or ""
            if t:
                text += t + "\n"
        if not text.strip():
            logger.warning(f"[{i}/{len(posts)}] {who}: текста в посте нет — пропускаю")
            continue
        links = message_links(group)
        what = []
        old_links = post.get("links")
        if old_links is None or links != old_links:
            post["links"] = links
            # Первое прочтение ссылок у поста без них правкой не считается:
            # правка — это когда ссылка была одна, а стала другая.
            if links != (old_links or []):
                what.append("ссылки")
        if text != post.get("raw"):
            # У похода свой разбор: проверять его разбором картины значило
            # бы отвергнуть любую правку — разделителей ⸻ там нет.
            parse = parse_visit if post.get("kind") else parse_post
            if parse(text):
                post["raw"] = text
                what.append("текст")
            else:
                logger.error(f"[{i}/{len(posts)}] {who}: новый текст не разбирается "
                             "(не хватает разделителей ⸻?) — оставляю прежний")
        if what:
            changed += 1
            logger.info(f"[{i}/{len(posts)}] {who}: обновлено — {', '.join(what)}")
    logger.info("Изменились посты: " + (str(changed) if changed else "нет"))
    return changed


async def backfill_links(client, records):
    """Дочитывает ссылки у записей, скачанных до того, как сборка их
    замечала. Делается один раз: поле links, даже пустое, значит «уже
    читали». Удалённому из канала посту ставится пустой список — иначе
    его спрашивали бы на каждой сборке."""
    todo = [r for r in records if r.get("id") and "links" not in r]
    if not todo:
        return 0
    logger.info(f"Ссылки в тексте постов: дочитываю у {len(todo)} записей (один раз)")
    groups, asked = await fetch_groups(client, todo)
    done = found = 0
    for rec in todo:
        group = groups.get(rec["id"])
        if group is not None:
            rec["links"] = message_links(group)
        elif rec["id"] in asked:
            rec["links"] = []           # пост удалён из канала
        else:
            continue                    # сбой связи — спросим в следующий раз
        done += 1
        found += len(rec["links"])
    logger.info(f"   дочитано записей: {done}, ссылок нашлось: {found}")
    return done

__all__ = [
    'TELETHON_AVAILABLE',
    'TelegramClient',
    'TelethonFakeTLS',
    'require_credentials',
    'connect_with_proxy',
    'download_with_retry',
    'download_images',
    'fetch_new_posts',
    'message_links',
    'fetch_groups',
    'refetch_texts',
    'backfill_links',
]
