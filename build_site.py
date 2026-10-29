# -*- coding: utf-8 -*-
"""Old Picture Art: local build and push; automated tests run in GitHub Actions."""
import asyncio
import os
import sys
import subprocess
import logging
import logging.handlers
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.handlers.RotatingFileHandler('parser.log', maxBytes=2_000_000,
        backupCount=2, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)
from html import escape as h
from urllib.parse import quote
from site_common import (head_common, scroll_top_button, theme_button, site_footer,
    mark_svg, TELEGRAM_URL, TELEGRAM_NAME, SITE_DOMAIN, hires_url,
    COMMON_JS, SCROLL_TOP_JS, LUPA_JS, TOAST_JS, SHARE_JS, AUTH_JS, CLOUD_JS, BASE_URL,
    VISITS_FILE, has_visits, visit_places, place_parts, visit_organizers,
    METRIKA_ID, SITE_OWNER, PRIVACY_CONTACT, PRIVACY_CONTACT_TEXT, PRIVACY_DATE,
    work_year, AUTH_API_URL, YANDEX_CLIENT_ID, VK_CLIENT_ID,
    TRANSLIT, translit, latin_slug, museum_page, visit_kind_label, MAP_LAYERS_JS)
from sitebuild.config import *
from sitebuild.text import *
from sitebuild.slugs import *
from sitebuild.links import *
from sitebuild.html import *
from sitebuild.images import *
from sitebuild.places import *
from sitebuild.visits import *
from sitebuild.posts import *
from sitebuild.artists import *
from sitebuild.museums import *
from sitebuild.static import *
from sitebuild.telegram import *
from sitebuild.refresh import *
from sitebuild.artist_info import *
from sitebuild.deps import *
from sitebuild.indexnow import *
from sitebuild.afisha import *
from sitebuild.indexnow import notify as notify_indexnow
from sitebuild.safety import publish_generated


def auto_update_modules():
    logger.info("Проверка модулей...")
    if ensure_requirements() == "installed":
        sys.exit(subprocess.call([sys.executable] + sys.argv + ["--no-update"]))


def push_to_github():
    root = Path(__file__).resolve().parent
    if Path.cwd().resolve() != root:
        raise RuntimeError("Запустите сборку из корня репозитория")
    logger.info("GitHub: отправка изменений. Тесты выполняются в GitHub Actions, не на компьютере.")
    return publish_generated(root)

async def main():
    if "--rebuild" in sys.argv: rebuild_reset()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, ".nojekyll"), "w") as f: pass
    if not PIL_AVAILABLE: logger.warning("Pillow не установлен")
    processed_ids = set(load_json(PROCESSED_FILE, []))
    all_posts = load_json(META_FILE, [])
    all_visits = load_json(VISITS_FILE, [])
    to_refresh = refresh_targets(all_posts + all_visits)
    if to_refresh is not None and not to_refresh:
        raise ValueError("--refresh: ни один пост не подошёл, сборка не начата")
    logger.info("Подключение к Telegram...")
    api_id, api_hash, phone = require_credentials()
    client = await connect_with_proxy(api_id, api_hash, phone, PROXY_LIST)
    try:
        if to_refresh:
            await refetch_texts(client, to_refresh)
        await backfill_links(client, all_posts + all_visits)
        full_scan = (not os.path.exists(VISITS_FILE)
                     or not all(v.get("extras_done") for v in all_visits)
                     or "--rescan" in sys.argv)
        accepted, new_visits, extras_for_known = await fetch_new_posts(
            client, processed_ids, full_scan, all_visits)
        for i, (mm, group, parsed) in enumerate(accepted, 1):
            date = mm.date.strftime("%Y-%m-%d")
            provisional = {**parsed, "date": date}
            base = post_slug(provisional, prepare_slugs(all_posts + [provisional]))
            fn, n = f"{base}.html", 2
            ex = {p["filename"] for p in all_posts}
            while fn in ex or os.path.exists(os.path.join(OUTPUT_DIR, fn)):
                fn = f"{base}-{n}.html"
                n += 1
            logger.info(f"[{i}/{len(accepted)}] {parsed['artist'][:40]} — {parsed['title'][:50]}")
            comments = []
            if getattr(mm, "replies", None) and mm.replies.replies > 0:
                try:
                    async for reply in client.iter_messages(CHANNEL_URL, reply_to=mm.id):
                        if getattr(reply, "document", None) and reply.document.mime_type.startswith("image/"):
                            comments.append(reply)
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
            for g in groups:
                im, hi, th = await download_images(client, g, [], slug,
                                                   start=len(visit.get("images") or []))
                visit["images"] = (visit.get("images") or []) + im
                visit["hires"] = (visit.get("hires") or []) + hi
                visit["thumbs"] = (visit.get("thumbs") or []) + th
                processed_ids.update(m.id for m in g)

        for i, (vm, group, parsed, extra) in enumerate(new_visits, 1):
            date = vm.date.strftime("%Y-%m-%d")
            base = f"visit-{date}-{slugify(visit_heading(parsed))}"
            fn, n = f"{base}.html", 2
            ex = {v["filename"] for v in all_visits}
            while fn in ex or os.path.exists(os.path.join(OUTPUT_DIR, fn)):
                fn = f"{base}-{n}.html"
                n += 1
            logger.info(f"[посещение {i}/{len(new_visits)}] {visit_heading(parsed)[:60]}"
                        + (f" (+{len(extra)} без подписи)" if extra else ""))
            im, hi, th = await download_images(client, group, await visit_comments(vm), fn[:-5])
            visit = {"id":vm.id,"date":date,"filename":fn,"images":im,"hires":hi,"thumbs":th,
                     "extras_done":True, "links":message_links(group), **parsed}
            processed_ids.update(m.id for m in group)
            await add_photos(visit, extra, fn[:-5])
            all_visits.append(visit)
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
    finally:
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
        shrink_thumbs(all_posts + all_visits)
        build_views(all_posts + all_visits)
        build_cards(all_posts)
    sync_hires(all_posts + all_visits)
    refresh_visits(all_visits)
    refresh_posts(all_posts)
    fix_work_years(all_posts)
    prepare_slugs(all_posts)
    rename_pages(all_posts, all_visits)
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
    generate_museum_pages(all_posts, all_visits)
    generate_afisha(museum_names(all_posts, all_visits), all_posts=all_posts, visits=all_visits)
    subprocess.run([sys.executable, "generate_quiz.py"], check=True)
    logger.info("Квиз сгенерирован")
    subprocess.run([sys.executable, "generate_timeline.py"], check=True)
    logger.info("Хронология сгенерирована")
    for name, render in (("index.html", lambda: render_index(all_posts)),
                         ("404.html", render_404), ("privacy.html", render_privacy),
                         ("auth.html", render_auth_page)):
        with open(os.path.join(OUTPUT_DIR, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(render())
    save_image_sizes()
    logger.info(f"Новых постов: {len(accepted)}. Всего: {len(all_posts)}")
    map_reminder(all_posts, all_visits)
    if "--no-push" in sys.argv:
        logger.info("Сборка завершена локально (--no-push); Git и IndexNow не вызываются")
        return
    pushed = push_to_github()
    if pushed:
        try:
            notify_indexnow(pushed)
        except Exception as e:
            logger.warning(f"IndexNow: {e}")


def indexnow_command():
    i = sys.argv.index("--indexnow")
    n = sys.argv[i + 1] if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else "1"
    notify_commits(int(n))


if __name__ == "__main__":
    try:
        if "--indexnow" in sys.argv:
            indexnow_command()
        else:
            if "--no-update" not in sys.argv:
                auto_update_modules()
            asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Прервано")
        sys.exit(130)
    except Exception:
        logger.exception("Критическая ошибка")
        sys.exit(1)
