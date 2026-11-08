# -*- coding: utf-8 -*-
"""Safe, no-push installer for Old Picture Art's personal art passport.

Unzip to repository root; run --check first, then --apply, then rebuild_pages.py.
No network operations, git commands, or mutation in check mode.
"""
from __future__ import annotations
import argparse
import ast
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = (
    'build_site.py', 'rebuild_pages.py', 'sitebuild/posts.py',
    'sitebuild/artists.py', 'sitebuild/museums.py', 'sitebuild/visits.py',
)
ASSETS = (
    'sitebuild/passport.py', 'docs/passport.js',
    'docs/passport-actions.js', 'docs/passport.css',
)
MARKER = 'OPA PERSONAL ART PASSPORT 2026-11-08'


def one(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: ожидался один фрагмент, обнаружено {count}. ' +
                           'Ничего не записано; проверьте версию репозитория.')
    return source.replace(old, new, 1)


def patch(path: str, source: str) -> str:
    if MARKER in source:
        return source  # idempotent installation; whole file already patched
    if path == 'build_site.py':
        source = one(source, 'from sitebuild.afisha import *  # noqa: F401,F403',
                     'from sitebuild.afisha import *  # noqa: F401,F403\n'
                     'from sitebuild.passport import *  # noqa: F401,F403', 'Импорт паспорта')
        source = one(source, '    subprocess.run([sys.executable, "generate_quiz.py"], check=True)',
                     '    generate_passport(all_posts, all_visits)\n'
                     '    subprocess.run([sys.executable, "generate_quiz.py"], check=True)', 'Сборка Telegram')
    elif path == 'rebuild_pages.py':
        source = one(source, '    print("✓ index.html")',
                     '    print("✓ index.html")\n'
                     '    bs.generate_passport(meta, visits)\n'
                     '    print("✓ passport.html")', 'Офлайн-сборка')
    elif path == 'sitebuild/posts.py':
        source = one(source, '    tg_link_html = (',
                     '    passport_link_html = (\'<div class="sidebar-section"><a '
                     'class="sidebar-title sidebar-icon icon-fav no-arrow" '
                     'href="passport.html">Мой арт-паспорт</a></div>\')\n'
                     '    tg_link_html = (', 'Меню главной')
        source = one(source, '{visits_link_html}\n{index_link_html}',
                     '{visits_link_html}\n{passport_link_html}\n{index_link_html}', 'Ссылка в меню')
        source = one(source, '      <h2>{title}</h2>',
                     '      <h2>{title}</h2>\n'
                     '      <div class="opa-passport-actionbar">\n'
                     '        <button type="button" data-opa-passport="originals" data-passport-key="{h(post_id)}" '
                     'data-label-off="Отметить: видел оригинал" data-label-on="✓ Видел оригинал" '
                     'aria-pressed="false">Отметить: видел оригинал</button>\n'
                     '        <a href="passport.html?add={h(post_id)}#collections">В мою коллекцию</a>\n'
                     '        <a href="passport.html">Арт-паспорт</a>\n'
                     '      </div>', 'Кнопки на картине')
        source = one(source, '</head><body class="post-page">',
                     '<link rel="stylesheet" href="passport.css">\n</head><body class="post-page">', 'Стили картин')
        source = one(source, '{AUTH_JS}\n</body></html>"""',
                     '{AUTH_JS}\n<script src="passport-actions.js" defer></script>\n</body></html>"""',
                     'Действия картин')
    elif path == 'sitebuild/artists.py':
        source = one(source, '</head><body class="tag-page artist-page">',
                     '<link rel="stylesheet" href="passport.css">\n</head><body class="tag-page artist-page">',
                     'Стили художников')
        source = one(source, '  <h1>{h(artist)}</h1>\n',
                     '  <h1>{h(artist)}</h1>\n'
                     '  <div class="opa-passport-actionbar">'
                     '<button type="button" data-opa-passport="artists" data-passport-key="{h(artist)}" '
                     'data-label-off="+ Любимый художник" data-label-on="✓ Любимый художник" '
                     'aria-pressed="false">+ Любимый художник</button>'
                     '<a href="passport.html#artists">Мой арт-паспорт</a></div>\n',
                     'Кнопка художника')
        source = one(source, '  <aside class="post-aside">{museum_html}</aside>\n</div>\n{nav_html}\n{site_footer()}\n{SCROLL_TOP_JS}\n{COMMON_JS}\n</body></html>"""',
                     '  <aside class="post-aside">{museum_html}</aside>\n</div>\n{nav_html}\n{site_footer()}\n{SCROLL_TOP_JS}\n{COMMON_JS}\n<script src="passport-actions.js" defer></script>\n</body></html>"""',
                     'Скрипт художников')
    elif path == 'sitebuild/museums.py':
        source = one(source, '</head><body class="tag-page artist-page museum-page">',
                     '<link rel="stylesheet" href="passport.css">\n</head><body class="tag-page artist-page museum-page">',
                     'Стили музеев')
        source = one(source, '  <h1>{h(shown)}</h1>\n  {hero}',
                     '  <h1>{h(shown)}</h1>\n'
                     '  <div class="opa-passport-actionbar">'
                     '<button type="button" data-opa-passport="museums" data-passport-key="{h(name)}" '
                     'data-label-off="+ Я был в этом музее" data-label-on="✓ Я был в этом музее" '
                     'aria-pressed="false">+ Я был в этом музее</button>'
                     '<a href="passport.html#museums">Мой арт-паспорт</a></div>\n'
                     '  {hero}', 'Кнопка музея')
        source = one(source, '{map_js}\n</body></html>"""',
                     '{map_js}\n<script src="passport-actions.js" defer></script>\n</body></html>"""', 'Скрипт музеев')
    elif path == 'sitebuild/visits.py':
        source = one(source, '  <a href="museums.html" class="back">Карта собраний</a>\n',
                     '  <a href="museums.html" class="back">Карта собраний</a>\n'
                     '  <a href="passport.html" class="back">Мой арт-паспорт</a>\n',
                     'Ссылка дневника')
    else:
        raise RuntimeError(f'Неизвестный файл: {path}')
    # Store marker without changing public HTML; makes reinstallation idempotent.
    return f'# {MARKER}\n' + source


def prepare():
    if not (ROOT / '.git').exists() and not (ROOT / 'posts_meta.json').exists():
        raise RuntimeError('Запускайте из корня проекта, рядом с posts_meta.json.')
    for item in ASSETS:
        if not (ROOT / item).is_file():
            raise RuntimeError(f'Не найден {item} — распакуйте ZIP целиком в корень репозитория.')
    changes = {}
    for path in FILES:
        file = ROOT / path
        if not file.is_file():
            raise RuntimeError(f'Не найден файл {path}.')
        original = file.read_text('utf-8')
        updated = patch(path, original)
        try:
            ast.parse(updated, filename=path)
        except SyntaxError as exc:
            raise RuntimeError(f'Ошибка Python после изменения {path}: {exc}') from exc
        changes[path] = (original, updated)
    ast.parse((ROOT / ASSETS[0]).read_text('utf-8'), filename=ASSETS[0])
    return changes


def apply(changes):
    pending = {name: state for name, state in changes.items() if state[0] != state[1]}
    if not pending:
        print('Арт-паспорт уже установлен. Повторное изменение не требуется.')
        return
    backup = ROOT.parent / (ROOT.name + '_backup_art_passport_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True, exist_ok=False)
    for path in pending:
        dest = backup / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, dest)
    done = []
    try:
        for path, (_original, updated) in pending.items():
            target = ROOT / path
            fd, temp = tempfile.mkstemp(prefix='.passport_', suffix='.tmp', dir=target.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(updated)
                os.replace(temp, target)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            done.append(path)
    except Exception:
        for path in done:
            shutil.copy2(backup / path, ROOT / path)
        print('Запись отменена, исходные файлы восстановлены.', file=sys.stderr)
        raise
    print('Изменено файлов Python:', len(done))
    print('Резервная копия:', backup)
    print('Далее: python rebuild_pages.py --offline')
    print('Потом: python -m unittest tests.test_passport')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='Проверить совместимость, ничего не менять')
    group.add_argument('--apply', action='store_true', help='Применить с резервной копией')
    args = parser.parse_args()
    try:
        changes = prepare()
        if args.check:
            for path, (old, new) in changes.items():
                print(('Уже готово: ' if old == new else 'Можно изменить: ') + path)
            print('Проверка пройдена. GitHub не затрагивается.')
        else:
            apply(changes)
    except (OSError, UnicodeError, RuntimeError) as e:
        print('ОШИБКА:', e, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
