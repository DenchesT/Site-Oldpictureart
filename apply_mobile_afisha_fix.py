#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Мобильная афиша + заголовок бокового меню Old Picture Art.

Применяет изменения только к docs/style.css и sitebuild/posts.py.
Заголовок и описание афиши (sitebuild/afisha.py) не затрагивает.
Использование:
  python apply_mobile_afisha_fix.py --check
  python apply_mobile_afisha_fix.py --apply
"""

import argparse
import datetime
import os
import sys
import tempfile
from pathlib import Path

CSS_START = "/* OPA MOBILE AFISHA UI FIX 2026-10-31 — START"
OLD_HEADING = '<p class="opa-sidebar-heading">Подборки</p>\n{fav_html}\n{popular_html}'
NEW_HEADING = '<p class="opa-sidebar-heading">Избранное и популярное</p>\n{fav_html}\n{popular_html}'
CSS_FILE = "docs/style.css"
POSTS_FILE = "sitebuild/posts.py"
DESCRIPTION = ("Актуальные и предстоящие выставки в музеях России и мира. "
               "Завершившиеся события сохраняются в архиве.")


def prepare(root):
    root = Path(root)
    css_path = root / CSS_FILE
    posts_path = root / POSTS_FILE
    payload_path = Path(__file__).with_name("afisha_mobile_ui.css")
    for path in (css_path, posts_path, payload_path):
        if not path.is_file():
            raise RuntimeError(f"Не найден файл: {path}")
    css = css_path.read_text(encoding="utf-8")
    posts = posts_path.read_text(encoding="utf-8")
    payload = payload_path.read_text(encoding="utf-8").strip()
    if CSS_START not in payload or "@media (max-width: 700px)" not in payload:
        raise RuntimeError("Отсутствуют маркеры мобильного CSS в пакете")
    if CSS_START not in css:
        # На GitHub 31 октября используются именно эти классы. Если их нет,
        # остановиться, а не добавлять потенциально несовместимый CSS.
        for anchor in (".afisha-status-switch", ".afisha-filter-panel", ".tag-topbar"):
            if anchor not in css:
                raise RuntimeError(f"В {CSS_FILE} нет {anchor}; несовместимая версия")
        new_css = css.rstrip() + "\n\n" + payload + "\n"
    else:
        if payload not in css:
            raise RuntimeError("Мобильный патч уже есть, но отличается; нужна ручная сверка")
        new_css = css
    if OLD_HEADING in posts:
        if posts.count(OLD_HEADING) != 1:
            raise RuntimeError("Найдены повторяющиеся секции бокового меню")
        new_posts = posts.replace(OLD_HEADING, NEW_HEADING, 1)
    elif NEW_HEADING in posts:
        new_posts = posts
    else:
        raise RuntimeError("Не найден блок Избранное/Популярное: версия генератора отличается")
    # Не следует трогать тексты афиши; эта проверка — дополнительная защита.
    afisha = root / "sitebuild" / "afisha.py"
    if afisha.is_file() and DESCRIPTION not in afisha.read_text(encoding="utf-8"):
        print("Внимание: описание афиши отличается от версии 31.10; оно не изменяется.")
    return {css_path: (css, new_css), posts_path: (posts, new_posts)}


def write_all(changes, root):
    changed = [(p, after) for p, (before, after) in changes.items() if before != after]
    if not changed:
        return []
    # Резервные копии перед записью; никаких git-команд и удаления файлов.
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backups = {}
    try:
        for path, _ in changed:
            old = changes[path][0]
            backup = path.with_name(path.name + f".before-mobile-afisha-{stamp}.bak")
            if backup.exists():
                raise RuntimeError(f"Резервная копия уже существует: {backup}")
            backup.write_text(old, encoding="utf-8", newline="")
            backups[path] = backup
        for path, new in changed:
            fd, tempname = tempfile.mkstemp(prefix=".opa-afisha-", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                    f.write(new)
                os.replace(tempname, path)
            finally:
                if os.path.exists(tempname):
                    os.remove(tempname)
    except Exception:
        # Восстанавливаем оба исходника даже при частичном отказе записи.
        for path, (old, _) in changes.items():
            if path in backups:
                path.write_text(old, encoding="utf-8", newline="")
        raise
    return list(backups.values())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--check", action="store_true", help="Проверить совместимость без записи")
    command.add_argument("--apply", action="store_true", help="Применить изменения")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Корневая папка проекта")
    args = parser.parse_args(argv)
    try:
        changes = prepare(args.root)
        for path, (old, new) in changes.items():
            status = "уже обновлён" if old == new else "готов к изменению"
            print(f"{path.relative_to(args.root)}: {status}")
        if args.check:
            print("OK: проверка пройдена, файлов не меняли.")
        else:
            backups = write_all(changes, args.root)
            if backups:
                print("Резервные копии:")
                for b in backups:
                    print(" -", b)
                print("OK: правки внесены. Теперь пересоберите страницы, чтобы обновить версию CSS.")
            else:
                print("OK: изменения уже были применены.")
    except (OSError, RuntimeError) as e:
        print("ОШИБКА:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
