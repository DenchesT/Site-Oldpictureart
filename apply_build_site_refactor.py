#!/usr/bin/env python3
"""Однократное безопасное устранение дублирования комментариев в build_site.py.

Запуск из корня репозитория: python apply_build_site_refactor.py
Ничего не отправляет в GitHub. Перед заменой создаёт build_site.py.before-quality-update.bak.
"""

from pathlib import Path
import sys


_HELPER = '''async def _image_comments(client, message):
    """Изображения из комментариев к картине или посещению."""
    result = []
    replies = getattr(message, "replies", None)
    if not replies or not getattr(replies, "replies", 0):
        return result
    try:
        async for reply in client.iter_messages(CHANNEL_URL, reply_to=message.id):
            document = getattr(reply, "document", None)
            mime = getattr(document, "mime_type", "") or ""
            if mime.startswith("image/"):
                result.append(reply)
    except Exception as exc:
        logger.warning("Комментарии: %s", exc)
    return result


'''

_OLD_POST = '''            comments = []
            if getattr(mm, "replies", None) and mm.replies.replies > 0:
                try:
                    async for reply in client.iter_messages(CHANNEL_URL, reply_to=mm.id):
                        if getattr(reply, "document", None) and reply.document.mime_type.startswith("image/"):
                            comments.append(reply)
                except Exception as e: logger.warning(f"Комментарии: {e}")
            im, hi, th = await download_images(client, group, comments, fn[:-5])'''

_NEW_POST = '''            im, hi, th = await download_images(
                client, group, await _image_comments(client, mm), fn[:-5])'''

_OLD_VISIT = '''        async def visit_comments(anchor):
            out = []
            if getattr(anchor, "replies", None) and anchor.replies.replies > 0:
                try:
                    async for reply in client.iter_messages(CHANNEL_URL, reply_to=anchor.id):
                        if getattr(reply, "document", None) and reply.document.mime_type.startswith("image/"):
                            out.append(reply)
                except Exception as e: logger.warning(f"Комментарии: {e}")
            return out

'''

_OLD_CALL = 'await visit_comments(vm)'
_NEW_CALL = 'await _image_comments(client, vm)'


def refactor(source: str) -> str:
    """Возвращает изменённый исходник или выбрасывает ValueError при расхождении."""
    if 'async def _image_comments(' in source:
        if _OLD_POST not in source and _OLD_VISIT not in source:
            return source  # уже исправлено
        raise ValueError("Найдена частично исправленная версия — требуется ручная проверка")
    replacements = (
        (_OLD_POST, _NEW_POST),
        (_OLD_VISIT, ''),
        (_OLD_CALL, _NEW_CALL),
        ('async def main():', _HELPER + 'async def main():'),
    )
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError(f"Фрагмент встречается {source.count(old)} раз вместо 1: {old[:70]!r}")
        source = source.replace(old, new, 1)
    compile(source, "build_site.py", "exec")
    return source


def main():
    root = Path(__file__).resolve().parent
    source_path = root / "build_site.py"
    if not source_path.is_file():
        print("Скопируйте apply_build_site_refactor.py в корень проекта (рядом с build_site.py).")
        return 2
    source = source_path.read_text(encoding="utf-8")
    try:
        updated = refactor(source)
    except (ValueError, SyntaxError) as exc:
        print(f"Ничего не изменено: {exc}")
        return 1
    if updated == source:
        print("build_site.py уже обновлён")
        return 0
    backup = source_path.with_name("build_site.py.before-quality-update.bak")
    if backup.exists():
        print(f"Ничего не изменено: резервная копия {backup.name} уже существует")
        return 1
    backup.write_text(source, encoding="utf-8")
    source_path.write_text(updated, encoding="utf-8", newline="\n")
    print("build_site.py исправлен; оригинал сохранён в", backup.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
