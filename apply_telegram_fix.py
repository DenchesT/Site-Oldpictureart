#!/usr/bin/env python3
"""Безопасная правка проверки MIME в sitebuild/telegram.py.

Перед исправлением сохраняет sitebuild/telegram.py.before-quality-update.bak.
Никаких сетевых запросов или Telegram-операций не выполняет.
"""

from pathlib import Path
import sys

OLD = '    docs = [m for m in group if getattr(m,"document",None) and m.document.mime_type.startswith("image/")]'
NEW = ('    docs = [m for m in group\n'
       '            if (getattr(getattr(m, "document", None), "mime_type", "") or "")\n'
       '            .startswith("image/")]')


def refactor(source: str) -> str:
    if source.count(NEW) == 1 and OLD not in source:
        return source
    if source.count(OLD) != 1 or NEW in source:
        raise ValueError("Исходный фрагмент изменился, исправление нужно проверить вручную")
    result = source.replace(OLD, NEW, 1)
    compile(result, 'sitebuild/telegram.py', 'exec')
    return result


def main():
    root = Path(__file__).resolve().parent
    target = root / 'sitebuild' / 'telegram.py'
    if not target.is_file():
        print('Поместите apply_telegram_fix.py в корень проекта')
        return 2
    before = target.read_text(encoding='utf-8')
    try:
        after = refactor(before)
    except (ValueError, SyntaxError) as exc:
        print(f'Ничего не изменено: {exc}')
        return 1
    if before == after:
        print('sitebuild/telegram.py уже обновлён')
        return 0
    backup = target.with_name('telegram.py.before-quality-update.bak')
    if backup.exists():
        print('Резервная копия уже существует, исходник не изменён')
        return 1
    backup.write_text(before, encoding='utf-8')
    target.write_text(after, encoding='utf-8', newline='\n')
    print('sitebuild/telegram.py обновлён')
    return 0


if __name__ == '__main__':
    sys.exit(main())
