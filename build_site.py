# -*- coding: utf-8 -*-
"""
Сборка сайта Old Picture Art из Telegram-канала @oldpictureart.

    python build_site.py                 новые посты из канала → страницы → push
    python build_site.py --refresh <что> перечитать правленый пост из канала
    python build_site.py --rescan        пройти канал целиком
    python build_site.py --indexnow [N]  сообщить поисковикам о страницах из N последних коммитов
    python rebuild_pages.py              пересобрать страницы без Telegram

Сама сборка разложена по модулям пакета sitebuild/ (раньше всё жило в этом
файле — пять тысяч строк):

    config     пути, размеры картинок, канал, .env
    text       разбор текста поста, slugify, склонения, JSON
    slugs      адреса страниц, переезды и перенаправления
    links      ссылки из постов
    html       общие помощники страниц
    images     миниатюры, копии для лупы, карточки ссылок
    places     справочник музеев, сведение походов к карточкам карты
    visits     посещения: разбор, сроки выставок, страницы походов
    posts      страницы картин, подборки по тегам, главная
    artists    художники, указатель, статистика
    museums    страницы музеев и карта собраний
    static     404, конфиденциальность, вход, карта сайта, RSS, иконки
    telegram   загрузка из канала
    refresh    обновление уже собранного, --refresh
    artist_info  годы жизни художников и статьи в Википедии (Wikidata)
    deps       модули питона версий из requirements.txt
    indexnow   новые и изменённые страницы — сразу поисковикам
    afisha     афиша: крупные выставки в России и в мире (afisha.json)

Здесь остались запуск и порядок шагов (main). Все имена модулей видны и
отсюда — build_site.clean_url, build_site.render_post_page и т. д., — так
продолжают работать rebuild_pages.py, проверки и прочие скрипты.
"""

import asyncio
import os
import sys
import subprocess
import logging
import logging.handlers
from datetime import datetime

# Журнал сборки. Пишется с обрезкой по размеру: прежде это был обычный
# FileHandler, который дописывает в конец и никогда не укорачивается —
# за полгода parser.log дорос до мегабайта и продолжал бы расти. Теперь
# файл обрезается на 2 МБ, а две прошлые сборки остаются в parser.log.1
# и parser.log.2 — этого хватает, чтобы посмотреть, что было в прошлый
# раз, и не хватает, чтобы захламить папку.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.handlers.RotatingFileHandler('parser.log', maxBytes=2_000_000,
                                                   backupCount=2, encoding='utf-8'),
              logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Всё, из чего собирается сайт, — по модулям (см. начало файла). Общие
# части из site_common и html.escape видны отсюда, как и прежде: на них
# опираются rebuild_pages.py и проверки.
from html import escape as h  # noqa: F401
from urllib.parse import quote  # noqa: F401
from site_common import (head_common, scroll_top_button, theme_button, site_footer,  # noqa: F401
                         mark_svg, TELEGRAM_URL, TELEGRAM_NAME, SITE_DOMAIN, hires_url,
                         COMMON_JS, SCROLL_TOP_JS, LUPA_JS, TOAST_JS, SHARE_JS, AUTH_JS, CLOUD_JS, BASE_URL,
                         VISITS_FILE, has_visits, visit_places, place_parts, visit_organizers,
                         METRIKA_ID, SITE_OWNER, PRIVACY_CONTACT, PRIVACY_CONTACT_TEXT, PRIVACY_DATE,
                         work_year, AUTH_API_URL, YANDEX_CLIENT_ID, VK_CLIENT_ID,
                         TRANSLIT, translit, latin_slug, museum_page, visit_kind_label,
                         MAP_LAYERS_JS)
from sitebuild.config import *  # noqa: F401,F403
from sitebuild.text import *  # noqa: F401,F403
from sitebuild.slugs import *  # noqa: F401,F403
from sitebuild.links import *  # noqa: F401,F403
from sitebuild.html import *  # noqa: F401,F403
from sitebuild.images import *  # noqa: F401,F403
from sitebuild.places import *  # noqa: F401,F403
from sitebuild.visits import *  # noqa: F401,F403
from sitebuild.posts import *  # noqa: F401,F403
from sitebuild.artists import *  # noqa: F401,F403
from sitebuild.museums import *  # noqa: F401,F403
from sitebuild.static import *  # noqa: F401,F403
from sitebuild.telegram import *  # noqa: F401,F403
from sitebuild.refresh import *  # noqa: F401,F403
from sitebuild.artist_info import *  # noqa: F401,F403
from sitebuild.deps import *  # noqa: F401,F403
from sitebuild.indexnow import *  # noqa: F401,F403
from sitebuild.afisha import *  # noqa: F401,F403
from sitebuild.indexnow import notify as notify_indexnow  # noqa: F401

def auto_update_modules():
    """Модули ровно тех версий, что в requirements.txt (sitebuild/deps.py)."""
    logger.info("Проверка модулей...")
    if ensure_requirements() == "installed":
        # Старые версии уже загружены в память — запускаемся заново.
        logger.info("Перезапускаю сборку с новыми модулями")
        sys.exit(subprocess.call([sys.executable] + sys.argv + ["--no-update"]))

# Модули обновляем только при реальном запуске парсера. Раньше pip дёргался
# при любом импорте файла, из-за чего страницы нельзя было пересобрать офлайн.
if __name__ == "__main__" and "--no-update" not in sys.argv:
    auto_update_modules()

def push_to_github():
    """add, commit, push. Возвращает список отправленных файлов (для IndexNow) или None."""
    logger.info("GitHub...")
    try:
        subprocess.run(["git","add","."], check=False)
        st = subprocess.run(["git","status","--porcelain"], capture_output=True, text=True)
        if not st.stdout.strip(): logger.info("Нет изменений"); return None
        files = subprocess.run(["git","-c","core.quotepath=false","diff","--cached","--name-only","--diff-filter=AMR"],
                               capture_output=True, text=True, encoding="utf-8").stdout.split("\n")
        subprocess.run(["git","commit","-m",f"Авто-обновление: {datetime.now():%Y-%m-%d %H:%M}"], check=False)
        if subprocess.run(["git","push"], check=False).returncode:
            logger.error("push не прошёл — поисковикам сообщу в следующий раз")
            return None
        logger.info("Отправлено")
        return [f.strip() for f in files if f.strip()]
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return None

async def main():
    if "--rebuild" in sys.argv: rebuild_reset()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, ".nojekyll"), "w") as f: pass
    if not PIL_AVAILABLE: logger.warning("Pillow не установлен")
    processed_ids = set(load_json(PROCESSED_FILE, []))
    all_posts = load_json(META_FILE, [])
    all_visits = load_json(VISITS_FILE, [])
    # Ключ --refresh разбираем до Телеграма: если ни один пост не подошёл,
    # незачем и подключаться.
    # Искать правленый пост — и среди картин, и среди походов.
    to_refresh = refresh_targets(all_posts + all_visits)
    if to_refresh is not None and not to_refresh:
        logger.error("--refresh: ни один пост не подошёл, сборка не начата")
        return
    logger.info("Подключение к Telegram...")
    api_id, api_hash, phone = require_credentials()
    client = await connect_with_proxy(api_id, api_hash, phone, PROXY_LIST)
    if to_refresh:
        await refetch_texts(client, to_refresh)
    await backfill_links(client, all_posts + all_visits)
    # Полный проход нужен дважды: когда файла посещений ещё нет (сборка
    # первая, которая умеет #выставка и #галерея) и когда у прежних походов
    # ещё не собраны безымянные посты со снимками. Картинам это не мешает —
    # их отсеет processed_ids.
    full_scan = (not os.path.exists(VISITS_FILE)
                 or not all(v.get("extras_done") for v in all_visits)
                 or "--rescan" in sys.argv)
    try:
        accepted, new_visits, extras_for_known = await fetch_new_posts(
            client, processed_ids, full_scan, all_visits)
    except Exception as e: logger.error(f"Ошибка сканирования: {e}"); await client.disconnect(); return
    for i, (mm, group, parsed) in enumerate(accepted, 1):
        date = mm.date.strftime("%Y-%m-%d")
        # Имя страницы считаем сразу тем же способом, что и при
        # пересборке, — иначе новая запись сначала получила бы
        # кириллическое имя, под ним скачались бы картинки, и лишь потом
        # страница переехала бы, оставив файлы с прежними именами.
        provisional = {**parsed, "date": date}
        base = post_slug(provisional, prepare_slugs(all_posts + [provisional]))
        fn = f"{base}.html"
        n = 2
        ex = {p["filename"] for p in all_posts}
        while fn in ex or os.path.exists(os.path.join(OUTPUT_DIR, fn)): fn = f"{base}-{n}.html"; n += 1
        logger.info(f"[{i}/{len(accepted)}] {parsed['artist'][:40]} — {parsed['title'][:50]}")
        comments = []
        if getattr(mm, "replies", None) and mm.replies.replies > 0:
            try:
                async for reply in client.iter_messages(CHANNEL_URL, reply_to=mm.id):
                    if getattr(reply, "document", None) and reply.document.mime_type.startswith("image/"): comments.append(reply)
            except Exception as e: logger.warning(f"Комментарии: {e}")
        im, hi, th = await download_images(client, group, comments, fn[:-5])
        post = {"id":mm.id,"date":date,"filename":fn,"images":im,"hires":hi,"thumbs":th,
                "links":message_links(group),**parsed}
        all_posts.append(post)
        processed_ids.update(m.id for m in group)
        with open(os.path.join(OUTPUT_DIR, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(render_post_page(post, all_posts))
    async def visit_comments(anchor):
        out = []
        if getattr(anchor, "replies", None) and anchor.replies.replies > 0:
            try:
                async for reply in client.iter_messages(CHANNEL_URL, reply_to=anchor.id):
                    if getattr(reply, "document", None) and reply.document.mime_type.startswith("image/"):
                        out.append(reply)
            except Exception as e: logger.warning(f"Комментарии: {e}")
        return out

    async def add_photos(visit, groups, slug):
        """Докачивает снимки из безымянных постов к тому же походу."""
        for g in groups:
            im, hi, th = await download_images(client, g, [], slug,
                                               start=len(visit.get("images") or []))
            visit["images"] = (visit.get("images") or []) + im
            visit["hires"] = (visit.get("hires") or []) + hi
            visit["thumbs"] = (visit.get("thumbs") or []) + th
            processed_ids.update(m.id for m in g)

    # Посещения качаем тем же порядком: снимков в таком посте бывает
    # десяток, и все они нужны на странице похода.
    for i, (vm, group, parsed, extra) in enumerate(new_visits, 1):
        date = vm.date.strftime("%Y-%m-%d")
        base = f"visit-{date}-{slugify(visit_heading(parsed))}"
        fn, n = f"{base}.html", 2
        ex = {v["filename"] for v in all_visits}
        while fn in ex or os.path.exists(os.path.join(OUTPUT_DIR, fn)): fn = f"{base}-{n}.html"; n += 1
        logger.info(f"[посещение {i}/{len(new_visits)}] {visit_heading(parsed)[:60]}"
                    + (f" (+{len(extra)} без подписи)" if extra else ""))
        im, hi, th = await download_images(client, group, await visit_comments(vm), fn[:-5])
        visit = {"id":vm.id,"date":date,"filename":fn,"images":im,"hires":hi,"thumbs":th,
                 "extras_done":True, "links":message_links(group), **parsed}
        processed_ids.update(m.id for m in group)
        await add_photos(visit, extra, fn[:-5])
        all_visits.append(visit)

    # Добавки к походам, которые уже были в базе: пост со снимками мог
    # выйти позже самого посещения или просто не собирался прежней сборкой.
    by_id = {v.get("id"): v for v in all_visits}
    for vid, groups in extras_for_known.items():
        visit = by_id.get(vid)
        if not visit:
            continue
        before = len(visit.get("images") or [])
        await add_photos(visit, groups, visit["filename"][:-5])
        added = len(visit.get("images") or []) - before
        if added:
            logger.info(f"[посещение] {visit_heading(visit)[:50]}: +{added} снимков без подписи")
    if full_scan:
        for v in all_visits:
            v["extras_done"] = True
    await client.disconnect()
    logger.info("Отключено")
    if PIL_AVAILABLE:
        miss = [p for p in all_posts + all_visits if not p.get("thumbs") and p.get("images")]
        if miss:
            logger.info(f"Миниатюры для {len(miss)} постов...")
            for p in miss:
                sl = p["filename"][:-5]
                th = []
                for i, ir in enumerate(p["images"], 1):
                    t = make_thumbnail(os.path.join(OUTPUT_DIR, ir), sl, i)
                    if t: th.append(t)
                p["thumbs"] = th
            logger.info("Миниатюры готовы")
        shrink_thumbs(all_posts + all_visits)
        build_views(all_posts + all_visits)
        build_cards(all_posts)
    # Оригиналы новых постов — в хранилище, если оно настроено. До записи
    # страниц: ссылка на оригинал ведёт туда, где файл лежит на самом деле,
    # и уехавший оригинал должен получить ссылку на хранилище сразу.
    sync_hires(all_posts + all_visits)
    # Файл посещений пишем до страниц: по нему подвал и сайдбар решают,
    # показывать ли раздел, а страницы картин собираются следом.
    refresh_visits(all_visits)
    # Адреса страниц — до записи страниц: на имена файлов опираются
    # ссылки между страницами, карта сайта и RSS. Переименование
    # идемпотентно: у записей с правильным именем ничего не меняется.
    # Посты перечитываются тем разбором, что сейчас в коде: так видна и
    # правка текста, притянутая ключом --refresh, и починка разбора.
    refresh_posts(all_posts)
    fix_work_years(all_posts)
    prepare_slugs(all_posts)
    rename_pages(all_posts, all_visits)
    # У кого из музеев есть своя страница — до записи страниц: на неё
    # ведут «Собрание» у картины, карточки, опись и страницы походов.
    prepare_museums(all_posts, all_visits)
    save_json(VISITS_FILE, all_visits)
    for post in all_posts:
        with open(os.path.join(OUTPUT_DIR, post["filename"]), "w", encoding="utf-8", newline="\n") as f:
            f.write(render_post_page(post, all_posts))
    save_json(META_FILE, all_posts)
    save_json(PROCESSED_FILE, sorted(processed_ids))
    generate_visit_pages(all_visits, all_posts)
    generate_tag_pages(all_posts)
    generate_extra_pages(all_posts)
    generate_redirects(all_posts, all_visits)
    generate_robots()
    generate_cname()
    generate_key_file()
    generate_sitemap(all_posts, all_visits)
    generate_manifest()
    generate_rss(all_posts)
    generate_museums_page(all_posts)
    # Страницы музеев — после карты: координаты берутся из её свежего кэша.
    generate_museum_pages(all_posts, all_visits)
    # Афиша: крупные выставки в России и в мире (afisha.json).
    generate_afisha(museum_names(all_posts, all_visits), all_posts=all_posts, visits=all_visits)
    # Генерация квиза и таймлайна
    try:
        subprocess.run([sys.executable, "generate_quiz.py"], check=True)
        logger.info("Квиз сгенерирован")
    except Exception as e:
        logger.error(f"Ошибка генерации квиза: {e}")
    
    try:
        subprocess.run([sys.executable, "generate_timeline.py"], check=True)
        logger.info("Хронология сгенерирована")
    except Exception as e:
        logger.error(f"Ошибка генерации хронологии: {e}")
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8", newline="\n") as f: f.write(render_index(all_posts))
    with open(os.path.join(OUTPUT_DIR, "404.html"), "w", encoding="utf-8", newline="\n") as f: f.write(render_404())
    with open(os.path.join(OUTPUT_DIR, "privacy.html"), "w", encoding="utf-8", newline="\n") as f: f.write(render_privacy())
    with open(os.path.join(OUTPUT_DIR, "auth.html"), "w", encoding="utf-8", newline="\n") as f: f.write(render_auth_page())
    save_image_sizes()
    logger.info(f"Новых постов: {len(accepted)}. Всего: {len(all_posts)}")
    map_reminder(all_posts, all_visits)
    pushed = push_to_github()
    # Новые и изменённые страницы — сразу поисковикам (sitebuild/indexnow.py).
    if pushed:
        try:
            notify_indexnow(pushed)
        except Exception as e:
            logger.warning(f"IndexNow: {e}")

def indexnow_command():
    """python build_site.py --indexnow [N] — без Telegram и без сборки."""
    i = sys.argv.index("--indexnow")
    n = sys.argv[i + 1] if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else "1"
    notify_commits(int(n))

if __name__ == "__main__" and "--indexnow" in sys.argv:
    indexnow_command()
elif __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: logger.info("Прервано")
    except Exception as e: logger.error(f"Критическая ошибка: {e}", exc_info=True)
