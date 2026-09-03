# -*- coding: utf-8 -*-
"""
Уборка в папке с картинками.

Зачем: сайт вырос до 1,2 ГБ, а у GitHub Pages жёсткий предел — 1 ГБ на
опубликованный сайт. При этом больше половины веса оказалось файлами,
на которые не ссылается ни один пост и ни одна страница: остатки от
переименованных и удалённых записей, вторые копии одних и тех же
оригиналов, случайно попавшие файлы.

Что делает скрипт:
  1. собирает все упоминания картинок — из posts_meta.json и из готовых
     страниц в docs/ (html, xml, json, css, js);
  2. показывает, какие файлы не упомянуты нигде, сколько они весят,
     какие файлы битые и какие не годятся для веба (например .tif);
  3. пересобирает раздутые миниатюры под тот размер, в котором они
     показываются;
  4. по флагу --apply всё это выполняет.

Чего скрипт НЕ делает: не трогает оригиналы (файлы «-hires-»). Их отдаёт
кнопка «Скачать картину», поэтому они остаются ровно такими, какими были —
ни уменьшения, ни пережатия.

Запуск:
    python optimize_images.py                 # только посмотреть отчёт
    python optimize_images.py --apply         # выполнить
    python optimize_images.py --apply --keep  # не удалять, а сложить в docs/_unused
    python optimize_images.py --thumb-width 400

ВАЖНО: запускать после сборки сайта (build_site.py или rebuild_pages.py),
чтобы страницы в docs/ были свежими. Иначе картинка нового поста, для
которого страница ещё не собрана, может показаться ненужной — впрочем,
posts_meta.json такие файлы всё равно защитит.
"""

import json
import os
import re
import shutil
import sys
import urllib.parse

OUTPUT_DIR = "docs"
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
META_FILE = "posts_meta.json"
UNUSED_DIR = os.path.join(OUTPUT_DIR, "_unused")

# Форматы, которые браузеры не показывают: держать их на сайте бессмысленно.
NOT_FOR_WEB = {".tif", ".tiff", ".bmp", ".psd", ".heic"}

TEXT_EXT = {".html", ".xml", ".json", ".css", ".js", ".txt"}
REF_RE = re.compile(r"images/[^\s\"'<>)\\]+")


def human(n):
    return f"{n / 1024 / 1024:.1f} МБ" if n >= 1024 * 1024 else f"{n / 1024:.0f} КБ"


def collect_references():
    """Все пути к картинкам, на которые хоть что-то ссылается.

    Двойная опора: база постов и готовые страницы. База важнее — она
    описывает сайт целиком, даже если страницы ещё не пересобраны.
    """
    refs = set()

    if os.path.exists(META_FILE):
        with open(META_FILE, encoding="utf-8") as f:
            for post in json.load(f):
                for field in ("images", "thumbs", "hires"):
                    for path in post.get(field) or []:
                        refs.add(path)

    for root, _, files in os.walk(OUTPUT_DIR):
        if os.path.abspath(root).startswith(os.path.abspath(UNUSED_DIR)):
            continue
        for name in files:
            if os.path.splitext(name)[1].lower() not in TEXT_EXT:
                continue
            try:
                text = open(os.path.join(root, name), encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for hit in REF_RE.findall(text):
                refs.add(urllib.parse.unquote(hit.split("?")[0].rstrip(".,;")))
    return refs


def list_images():
    out = []
    for root, _, files in os.walk(IMAGES_DIR):
        if os.path.abspath(root).startswith(os.path.abspath(UNUSED_DIR)):
            continue
        for name in files:
            full = os.path.join(root, name)
            out.append((os.path.relpath(full, OUTPUT_DIR).replace(os.sep, "/"), full))
    return sorted(out)


def open_size(path):
    """Размеры картинки или None, если файл не читается."""
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def main():
    apply_changes = "--apply" in sys.argv
    keep_unused = "--keep" in sys.argv
    thumb_width = 400
    for i, a in enumerate(sys.argv):
        if a == "--thumb-width" and i + 1 < len(sys.argv):
            thumb_width = int(sys.argv[i + 1])

    if not os.path.isdir(IMAGES_DIR):
        raise SystemExit(f"✕ нет папки {IMAGES_DIR} — запускать из корня проекта")

    refs = collect_references()
    files = list_images()
    total_before = sum(os.path.getsize(p) for _, p in files)

    # Удаляем только то, на что никто не ссылается. Битый или неудобный
    # для веба файл, на который ссылка есть, — это повод показать
    # предупреждение, а не молча снести: удаление сломало бы ссылку.
    unused, broken, not_web, fat_thumbs = [], [], [], []
    for rel, full in files:
        size = os.path.getsize(full)
        ext = os.path.splitext(rel)[1].lower()
        if rel not in refs:
            unused.append((rel, full, size))
            continue
        if ext in NOT_FOR_WEB:
            not_web.append((rel, full, size))
            continue
        dims = open_size(full)
        if dims is None:
            broken.append((rel, full, size))
        elif "/thumbs/" in rel and dims[0] > thumb_width:
            fat_thumbs.append((rel, full, size, dims))

    print("=" * 64)
    print(f"Картинок: {len(files)}, всего {human(total_before)}")
    print("=" * 64)

    def block(title, rows, tail=""):
        if not rows:
            return 0
        weight = sum(r[2] for r in rows)
        print(f"\n{title}: {len(rows)} шт., {human(weight)}{tail}")
        for r in sorted(rows, key=lambda x: -x[2])[:8]:
            print(f"   {human(r[2]):>9}  {r[0]}")
        if len(rows) > 8:
            print(f"   … и ещё {len(rows) - 8}")
        return weight

    freed = block("НА НИХ НИКТО НЕ ССЫЛАЕТСЯ — уберём", unused,
                  "  — остатки переименованных и удалённых записей")

    if broken:
        print(f"\n⚠ ССЫЛКА ЕСТЬ, А ФАЙЛ НЕ ЧИТАЕТСЯ: {len(broken)} шт. — "
              f"на сайте это битая картинка, перекачайте её")
        for rel, _, size in broken:
            print(f"   {human(size):>9}  {rel}")

    if not_web:
        print(f"\nФОРМАТ НЕ ДЛЯ ПОКАЗА В БРАУЗЕРЕ: {len(not_web)} шт., "
              f"{human(sum(r[2] for r in not_web))}")
        for rel, _, size in not_web:
            role = "только для скачивания — это нормально" if "-hires-" in rel else "показывается на странице — замените на jpg"
            print(f"   {human(size):>9}  {rel}  ({role})")

    if fat_thumbs:
        weight = sum(r[2] for r in fat_thumbs)
        print(f"\nМИНИАТЮРЫ КРУПНЕЕ, ЧЕМ НУЖНО: {len(fat_thumbs)} шт., {human(weight)}")
        print(f"   показываются шириной около 130 пикселей, пересоберём под {thumb_width}")
        for rel, _, size, dims in sorted(fat_thumbs, key=lambda x: -x[2])[:5]:
            print(f"   {human(size):>9}  {dims[0]}×{dims[1]}  {rel}")

    hires = [(r, p) for r, p in files if "-hires-" in r and r in refs]
    print(f"\nОРИГИНАЛЫ ДЛЯ СКАЧИВАНИЯ: {len(hires)} шт., "
          f"{human(sum(os.path.getsize(p) for _, p in hires))} — не трогаем")

    if not apply_changes:
        print("\n" + "-" * 64)
        print(f"Освободится примерно {human(freed)}: было {human(total_before)}, "
              f"станет около {human(total_before - freed)}")
        print("Это только отчёт. Чтобы выполнить: python optimize_images.py --apply")
        return

    # ------------------------------------------------------------ выполняем
    moved = 0
    for rel, full, size in unused:
        if keep_unused:
            dst = os.path.join(UNUSED_DIR, os.path.relpath(full, IMAGES_DIR))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(full, dst)
        else:
            os.remove(full)
        moved += 1

    rebuilt = 0
    if fat_thumbs:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        for rel, full, size, dims in fat_thumbs:
            try:
                with Image.open(full) as im:
                    im = im.convert("RGB")
                    im.thumbnail((thumb_width, thumb_width * 4), Image.LANCZOS)
                    im.save(full, "JPEG", quality=82, optimize=True, progressive=True)
                rebuilt += 1
            except Exception as e:
                print(f"   ✕ {rel}: {e}")

    total_after = sum(os.path.getsize(p) for _, p in list_images())
    print("\n" + "-" * 64)
    print(f"{'Перенесено в docs/_unused' if keep_unused else 'Удалено'}: {moved} файлов")
    print(f"Пересобрано миниатюр: {rebuilt}")
    print(f"Было {human(total_before)} → стало {human(total_after)} "
          f"(минус {human(total_before - total_after)})")
    if keep_unused:
        print("\nПапка docs/_unused не нужна сайту — просмотрите и удалите её руками.")
    print("После уборки пересоберите сайт: python rebuild_pages.py")


if __name__ == "__main__":
    main()
