#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Выбирает первую фотографию Telegram-поста об экспозиции как обложку посещения.

Версия для DenchesT/Site-Oldpictureart от 2026-11-08.
Не скачивает данные, не обращается к сети и не запускает Git.
Сначала `--check`, потом `--apply`; для обновления docs/ — `rebuild_pages.py --offline`.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import tempfile

TARGET = Path("sitebuild/visits.py")
START_RE = re.compile(r"^def visit_cover_index\(v\):\n", re.M)
NEXT_RE = re.compile(r"^def visit_cover\(v\):\n", re.M)
NEW_BLOCK = '''def visit_cover_index(v):
    """Обложка посещения — строго первый снимок оригинального поста.

    Первая миниатюра (если создана) и первая исходная фотография
    соответствуют одному и тому же кадру. Ранее обложка выбиралась
    автоматически по цветности/детализации; это нарушало порядок поста.
    """
    return 0


'''


def generate_patch(source: str) -> tuple[str, bool]:
    """Проверяет уникальные границы и возвращает новое содержимое без записи."""
    starts = list(START_RE.finditer(source))
    ends = list(NEXT_RE.finditer(source))
    if len(starts) != 1 or len(ends) != 1 or ends[0].start() <= starts[0].start():
        raise ValueError("Не удалось однозначно найти visit_cover_index/visit_cover. Версия проекта отличается.")
    start, end = starts[0].start(), ends[0].start()
    old = source[start:end]
    if old == NEW_BLOCK:
        return source, False
    # Структура должна быть исходной: замена только функции расчёта индекса.
    if "return" not in old or "cover_index" not in old:
        raise ValueError("Функция выбора обложки отличается от ожидаемой; замена отменена.")
    changed = source[:start] + NEW_BLOCK + source[end:]
    ast.parse(changed, filename=str(TARGET))
    return changed, True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='Только проверка; файлы не изменяются')
    group.add_argument('--apply', action='store_true', help='Применить к генератору сайта')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    # Можно распаковать ZIP в корень проекта или в отдельную папку.
    if not (root / TARGET).is_file() and (root.parent / TARGET).is_file():
        root = root.parent
    target = root / TARGET
    if not target.is_file():
        print('ОШИБКА: sitebuild/visits.py не найден. Распакуйте скрипт в корень репозитория.')
        return 2
    original = target.read_text(encoding='utf-8')
    try:
        updated, needed = generate_patch(original)
        ast.parse(updated, filename=str(target))
    except (ValueError, SyntaxError) as e:
        print('ОШИБКА:', e)
        return 2
    if not needed:
        print('ОК: первая фотография уже используется как обложка. Изменений не требуется.')
        return 0
    if args.check:
        print('ОК: можно обновить sitebuild/visits.py. Данные и фото останутся прежними.')
        return 0
    # Резервная копия СНАРУЖИ репозитория, чтобы случайно не попасть в git add -A.
    backup_dir = root.parent / 'OldPictureArt_visit_cover_backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'visits_{datetime.now():%Y%m%d_%H%M%S_%f}.py'
    shutil.copy2(target, backup)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n',
                                         dir=target.parent, prefix='.visits_',
                                         suffix='.tmp', delete=False) as f:
            tmp = Path(f.name)
            f.write(updated)
        os.replace(tmp, target)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()
    print('ГОТОВО:', target.relative_to(root))
    print('Резервная копия:', backup)
    print('Далее: python rebuild_pages.py --offline')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
