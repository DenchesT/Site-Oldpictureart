# -*- coding: utf-8 -*-
"""Correct the date-filter Playwright test after the afisha UI redesign.

Only tests/test_afisha.js is modified. Nothing in sitebuild, docs or .env changes.
Run --check before --apply. The patch is idempotent and makes a .bak backup.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MARKER = '// OPA afisha UI: select the soon tab before testing the opening filter.'
TARGET = "await page.selectOption('#afisha-opening', '90');"
OPENING = re.compile(r"(?m)^([ \t]*)await page\.selectOption\('#afisha-opening', '90'\);[ \t]*$")


def patch(source: str) -> tuple[str, str]:
    if MARKER in source:
        return source, 'Исправление уже применено.'
    if 'OPA AFISHA UI TESTS 2026-10-31' not in source or '#afisha-more-filters' not in source:
        raise RuntimeError('Тест ещё не обновлён для нового интерфейса афиши. Не меняю файл.')
    found = list(OPENING.finditer(source))
    if len(found) != 1:
        raise RuntimeError(f'Ожидалась одна проверка открытия на 90 дней, найдено {len(found)}. Не меняю файл.')
    m = found[0]
    # The preceding browser-test step unfolds the <details> containing the date controls.
    preceding = source[:m.start()].splitlines()[-4:]
    if not any("#afisha-more-filters" in line and "open = true" in line for line in preceding):
        raise RuntimeError('Не найдено раскрытие дополнительных фильтров перед проверкой. Не меняю файл.')
    indent = m.group(1)
    extra = (
        f'{indent}{MARKER}\n'
        f'{indent}await page.click(\'.afisha-status-switch [data-status="soon"]\');\n'
    )
    return source[:m.start()] + extra + source[m.start():], 'Исправление подготовлено.'


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--root', type=Path, default=Path.cwd(), help='Корневая папка Old Picture Art')
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Проверить совместимость и JS; файлы не менять')
    mode.add_argument('--apply', action='store_true', help='Создать резервную копию и исправить тест')
    args = cli.parse_args()

    target = args.root.resolve() / 'tests' / 'test_afisha.js'
    if not target.is_file():
        raise RuntimeError(f'Не найден {target}')
    original = target.read_text(encoding='utf-8')
    updated, status = patch(original)
    node = shutil.which('node')
    if node:
        result = subprocess.run([node, '--check'], input=updated, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError('Проверка синтаксиса JavaScript не прошла: ' + result.stderr)
    if args.check:
        print('OK:', status)
        print('Синтаксис JavaScript:', 'OK' if node else 'Node.js не найден; проверка пропущена')
        print('Файлы не изменены.')
        return 0
    if original == updated:
        print('OK: исправление уже установлено; ничего менять не нужно.')
        return 0
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = target.with_name(f'{target.name}.before_afisha_test_fix_{stamp}.bak')
    shutil.copy2(target, backup)
    try:
        target.write_text(updated, encoding='utf-8', newline='\n')
    except Exception:
        shutil.copy2(backup, target)
        raise
    print('OK: обновлён', target)
    print('Резервная копия:', backup)
    print('Повторите: node tests/test_afisha.js')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as exc:
        print('ОШИБКА:', exc, file=sys.stderr)
        sys.exit(1)
