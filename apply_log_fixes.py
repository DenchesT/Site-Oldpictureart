#!/usr/bin/env python3
"""Conservative offline updater for the OldPictureArt 2026-10-29 build log.

Run from the repository root, after extracting the update ZIP there.
  python apply_log_fixes.py --dry-run
  python apply_log_fixes.py

No network, Telegram, git push or build commands are executed.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent

EXHIBITION_LINKS = {
    "Ева Гонсалес. Путь свободной художницы": (
        "https://www.petitpalais.paris.fr/en/node/3992",
        "https://www.petitpalais.paris.fr/decouvrir-la-programmation/expositions/eva-gonzales",
    ),
    "Сокровища Саньсиндуя и Цзиньша": (
        "https://www.guimet.fr/sites/default/files/2026-10/cp_guimet_sanxingdui.pdf",
        "https://www.guimet.fr/fr/expositions/tresors-de-sanxingdui-et-jinsha-une-fascinante-civilisation-chinoise",
    ),
}
MUSEUM = "Частная коллекция, Фонд Константина Кузнецова, Москва"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if new in source:
        if old in source:
            raise ValueError(f"{label}: одновременно найдены старая и новая реализации")
        return source
    if source.count(old) != 1:
        raise ValueError(f"{label}: ожидаемая строка не найдена ровно один раз")
    return source.replace(old, new, 1)


def update_afisha(source: str) -> str:
    obj = json.loads(source)
    items = obj.get("exhibitions")
    if not isinstance(items, list):
        raise ValueError("afisha.json: поле exhibitions должно быть списком")
    for title, (old, new) in EXHIBITION_LINKS.items():
        found = [item for item in items if item.get("title") == title]
        if len(found) != 1 or found[0].get("url") not in (old, new):
            raise ValueError(f"afisha.json: не узнаю запись {title!r}; ничего не меняю")
        source = replace_once(source, '"url": "' + old + '"', '"url": "' + new + '"', title) if found[0]["url"] == old else source
    json.loads(source)
    return source


def update_overrides(source: str) -> str:
    data = json.loads(source)
    if MUSEUM in data:
        if data[MUSEUM] != {"skip": True}:
            raise ValueError("museum_overrides.json: для этой записи уже есть ручная правка — проверьте её")
        return source
    # Add next to other private collections without reformatting the whole file.
    needle = '  "Частная коллекция, Монте-Карло": {'
    replacement = '  "' + MUSEUM + '": {"skip": true},\n' + needle
    source = replace_once(source, needle, replacement, "museum_overrides.json")
    json.loads(source)
    return source


def update_places(source: str) -> str:
    old = '''    try:
        import generate_map as gm
        doubts = gm.map_warnings(museum_names(all_posts, visits),
                                 gm.load_cache(), gm.load_overrides(quiet=True))'''
    new = '''    overrides = {}
    try:
        import generate_map as gm
        overrides = gm.load_overrides(quiet=True)
        doubts = gm.map_warnings(museum_names(all_posts, visits),
                                 gm.load_cache(), overrides)'''
    source = replace_once(source, old, new, "sitebuild/places.py: overrides")
    old2 = '''        bare = [n for n in museum_names(all_posts, visits) if not museum_info(n, directory)["address"]]'''
    new2 = '''        bare = [n for n in museum_names(all_posts, visits)
                if not (overrides.get(n) or {}).get("skip")
                and not museum_info(n, directory)["address"]]'''
    source = replace_once(source, old2, new2, "sitebuild/places.py: no-address warning")
    ast.parse(source)
    return source


def update_telegram(source: str) -> str:
    old = '''    import TelethonFakeTLS
    TELETHON_AVAILABLE = True'''
    new = '''    import TelethonFakeTLS
    from .telethon_compat import patch_faketls_wait_closed
    patch_faketls_wait_closed()
    TELETHON_AVAILABLE = True'''
    source = replace_once(source, old, new, "sitebuild/telegram.py: wait_closed")
    source = replace_once(source, '    logger.info(f"Аккаунт: {PHONE}")',
                          '    logger.info("Учётные данные Telegram найдены")',
                          "sitebuild/telegram.py: phone in logs")
    ast.parse(source)
    return source


def update_workflow(source: str) -> str:
    old = '''      - name: Все проверки сайта
        run: node tests/run.js'''
    new = '''      - name: Регрессии исправлений лога
        run: python tests/test_log_fixes.py
      - name: Все проверки сайта
        run: node tests/run.js'''
    if new in source:
        return source
    return replace_once(source, old, new, ".github/workflows/tests.yml")


UPDATES = {
    "afisha.json": update_afisha,
    "museum_overrides.json": update_overrides,
    "sitebuild/places.py": update_places,
    "sitebuild/telegram.py": update_telegram,
    ".github/workflows/tests.yml": update_workflow,
}


def plan(root: Path) -> dict[Path, str]:
    """Validate *all* file contents before writing any of them."""
    if not (root / "build_site.py").is_file() or not (root / "sitebuild").is_dir():
        raise ValueError("Распакуйте архив в КОРЕНЬ проекта рядом с build_site.py")
    result = {}
    for relative, updater in UPDATES.items():
        path = root / relative
        before = path.read_text(encoding="utf-8")
        after = updater(before)
        if before != after:
            result[path] = after
    if not (root / "sitebuild/telethon_compat.py").exists():
        raise ValueError("Не найден sitebuild/telethon_compat.py из архива")
    if not (root / "tests/test_log_fixes.py").exists():
        raise ValueError("Не найден tests/test_log_fixes.py из архива")
    return result


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="показать изменения без записи")
    args = parser.parse_args(argv)
    try:
        updates = plan(root)
    except (OSError, ValueError, SyntaxError, json.JSONDecodeError) as exc:
        print(f"ОСТАНОВЛЕНО: {exc}", file=sys.stderr)
        return 1
    if not updates:
        print("Изменения уже применены — делать ничего не нужно.")
        return 0
    for path in updates:
        print(("Будет изменён: " if args.dry_run else "Исправляю: ") + str(path.relative_to(root)))
    if args.dry_run:
        return 0
    # Never clobber previous backup on a later run.
    for path in updates:
        backup = path.with_name(path.name + ".bak")
        if backup.exists():
            print(f"ОСТАНОВЛЕНО: резервная копия уже существует: {backup}", file=sys.stderr)
            return 1
    for path, content in updates.items():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
        tmp = path.with_name(path.name + ".opa-new")
        try:
            tmp.write_text(content, encoding="utf-8", newline="\n")
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
    print("Готово. ZIP не запускает сборку или отправку на GitHub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
