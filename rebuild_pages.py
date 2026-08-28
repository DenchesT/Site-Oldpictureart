# -*- coding: utf-8 -*-
"""
Пересборка всех страниц сайта из posts_meta.json — без Telegram.

Зачем: build_site.py ходит в Telegram за новыми постами, поэтому починить
вёрстку и прогнать сайт заново раньше было нельзя без .env и телефона.
Этот скрипт берёт уже скачанные данные и перегенерирует HTML: страницы
картин, теги, главную, 404, sitemap, RSS, манифест, квиз, таймлайн и карту.

Запуск:
    python rebuild_pages.py            # всё
    python rebuild_pages.py --no-map   # без карты (не ходить в Nominatim)
"""

import os
import sys
import json
import subprocess

os.environ.setdefault("OPA_OFFLINE_RENDER", "1")

import build_site as bs


def main():
    meta = bs.load_json(bs.META_FILE, [])
    if not meta:
        raise SystemExit(f"✕ {bs.META_FILE} пуст или не найден — пересобирать нечего")

    os.makedirs(bs.OUTPUT_DIR, exist_ok=True)
    os.makedirs(bs.IMAGES_DIR, exist_ok=True)
    with open(os.path.join(bs.OUTPUT_DIR, ".nojekyll"), "w"):
        pass

    print(f"Постов в базе: {len(meta)}")

    for post in meta:
        with open(os.path.join(bs.OUTPUT_DIR, post["filename"]), "w", encoding="utf-8") as f:
            f.write(bs.render_post_page(post, meta))
    print(f"✓ Страницы картин: {len(meta)}")

    bs.generate_tag_pages(meta)
    bs.generate_sitemap(meta)
    bs.generate_manifest()
    bs.generate_rss(meta)

    with open(os.path.join(bs.OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(bs.render_index(meta))
    print("✓ index.html")

    with open(os.path.join(bs.OUTPUT_DIR, "404.html"), "w", encoding="utf-8") as f:
        f.write(bs.render_404())
    print("✓ 404.html")

    for script, flag in (("generate_quiz.py", None), ("generate_timeline.py", None), ("generate_map.py", "--no-map")):
        if flag and flag in sys.argv:
            print(f"– {script} пропущен")
            continue
        # Флаги карты пробрасываем дальше: --no-geocode собирает карту
        # только по готовым координатам и в сеть не ходит вообще.
        args = [a for a in ("--no-geocode", "--regeocode") if a in sys.argv] if script == "generate_map.py" else []
        try:
            subprocess.run([sys.executable, script] + args, check=True)
            print(f"✓ {script}")
        except Exception as e:
            print(f"✕ {script}: {e}")

    print("\nГотово. Откройте docs/index.html")


if __name__ == "__main__":
    main()
