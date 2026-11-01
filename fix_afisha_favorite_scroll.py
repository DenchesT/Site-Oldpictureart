# -*- coding: utf-8 -*-
"""Исправление прокрутки при добавлении выставки в избранное.

  python fix_afisha_favorite_scroll.py --check
  python fix_afisha_favorite_scroll.py --apply

Меняет только sitebuild/afisha.py, с проверкой конкретной версии кода
и резервным копированием. Повторный запуск безопасен.
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime

MARKER = 'OPA AFISHA FAVORITES SCROLL FIX 2026-11-01'

OLD_LISTENER = '''  window.addEventListener('opa:afisha-favorites', function () {
    favorites = readAfishaFavorites();
    items.forEach(paintFavorite);
    show();
  });'''

NEW_LISTENER = '''  // OPA AFISHA FAVORITES SCROLL FIX 2026-11-01
  // The new favorite changes only the star and the favorites counter.
  // Rebuilding / re-appending all cards in show() unexpectedly moves
  // the scroll position on both desktop and mobile browsers.
  window.addEventListener('opa:afisha-favorites', function () {
    favorites = readAfishaFavorites();
    items.forEach(paintFavorite);
    if (state.status !== 'favorites' && !state.favoritesOnly) {
      // No entry enters or leaves the visible list in normal modes.
      // Do not move a single DOM node or change the current scroll position.
      var total = items.filter(function (li) { return !!favorites[favoriteId(li)]; }).length;
      var badge = document.getElementById('afisha-fav-total');
      if (badge) badge.textContent = total ? '(' + total + ')' : '';
      return;
    }
    // In the Favorites view removing an entry really changes the list.
    // Skip unnecessary re-sorting and keep the user's reading position.
    var beforeY = window.scrollY;
    show(true);
    if (Math.abs(window.scrollY - beforeY) > 1) {
      window.scrollTo({top: beforeY, behavior: 'instant'});
    }
  });'''

OLD_SHOW = '  function show() {'
NEW_SHOW = '  function show(skipSort) {'
OLD_SORT = '''    applySort();
    regionBtns.forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-region') === state.reg ? 'true' : 'false'); });'''
NEW_SORT = '''    if (!skipSort) applySort();
    regionBtns.forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-region') === state.reg ? 'true' : 'false'); });'''


def make_patch(source: str) -> tuple[str, bool]:
    if MARKER in source:
        for want in (NEW_LISTENER, NEW_SHOW, NEW_SORT):
            if want not in source:
                raise RuntimeError('Метка исправления есть, но код отличается. Файл не изменён.')
        return source, False
    changes = ((OLD_LISTENER, NEW_LISTENER), (OLD_SHOW, NEW_SHOW), (OLD_SORT, NEW_SORT))
    for needle, _ in changes:
        count = source.count(needle)
        if count != 1:
            raise RuntimeError(
                'Несовместимый sitebuild/afisha.py: не найден ожидаемый участок '
                f'({needle.strip()[:75]!r}, совпадений: {count}). '
                'Сначала синхронизируйте локальный код с актуальным GitHub.')
    result = source
    for old, new in changes:
        result = result.replace(old, new, 1)
    ast.parse(result, filename='sitebuild/afisha.py')
    return result, True


def main() -> int:
    parser = argparse.ArgumentParser(description='Починить скачок прокрутки при отметке избранных выставок')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='Только проверить, ничего не менять')
    group.add_argument('--apply', action='store_true', help='Применить исправление с резервной копией')
    args = parser.parse_args()

    path = Path(__file__).resolve().parent / 'sitebuild' / 'afisha.py'
    if not path.is_file():
        print('ОШИБКА: положите файлы из ZIP в корень проекта, рядом с sitebuild/')
        return 2
    original = path.read_text(encoding='utf-8')
    try:
        updated, needed = make_patch(original)
    except (RuntimeError, SyntaxError) as exc:
        print(f'ОШИБКА: {exc}')
        return 2
    if not needed:
        print('ОК: исправление уже установлено, повторная запись не нужна.')
        return 0
    if args.check:
        print('ОК: исходный код совместим. Исправление готово к применению.')
        print('Будет изменён только sitebuild/afisha.py.')
        return 0

    backup = path.with_name('afisha.py.before_favorite_scroll.bak')
    if backup.exists():
        backup = path.with_name('afisha.py.before_favorite_scroll.' +
                                datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.bak')
    shutil.copy2(path, backup)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n',
                                         dir=path.parent, prefix='.afisha_scroll_',
                                         suffix='.tmp', delete=False) as f:
            tmp = Path(f.name)
            f.write(updated)
        os.replace(tmp, path)
    except Exception:
        if tmp and tmp.exists():
            tmp.unlink()
        raise
    print('ОК: исправлено sitebuild/afisha.py')
    print('Резервная копия:', backup.relative_to(path.parent.parent))
    print('Теперь запустите: python rebuild_pages.py --offline')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
