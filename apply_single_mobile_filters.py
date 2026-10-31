#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Old Picture Art: один уровень фильтров в мобильной афише.

Десктоп, описание, выставки, данные и CSS остальных страниц не затрагиваются.

  python apply_single_mobile_filters.py --check
  python apply_single_mobile_filters.py --apply
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile

AFISHA = Path("sitebuild/afisha.py")
CSS = Path("docs/style.css")
JS_MARKER = "OPA SINGLE-LEVEL MOBILE AFISHA — START"
CSS_MARKER = "OPA SINGLE-LEVEL MOBILE AFISHA — CSS START"

JS_ANCHOR = """  var mobileFilterToggle = document.getElementById('afisha-mobile-filter-toggle');
  if (mobileFilterToggle) mobileFilterToggle.addEventListener('click', function () {
    var panel = document.querySelector('.afisha-filter-panel');
    var expanded = panel.classList.toggle('expanded');
    this.setAttribute('aria-expanded', String(expanded));
  });
  function show() {"""

JS_PATCH = """  // OPA SINGLE-LEVEL MOBILE AFISHA — START
  // On phones there is ONE accordion: the outer 'Фильтры' button.
  // Keep the nested <details> open, hide only its summary via mobile CSS.
  // Restore the previous desktop <details> state when crossing 700px.
  var opaMoreFilters = document.getElementById('afisha-more-filters');
  if (opaMoreFilters && mobileFilterToggle && window.matchMedia) {
    var opaMobileMedia = window.matchMedia('(max-width: 700px)');
    var opaDesktopDetailsOpen = opaMoreFilters.open;
    function opaSyncSingleLevelFilters() {
      if (opaMobileMedia.matches) {
        if (!opaMoreFilters.hasAttribute('data-opa-mobile-detail')) {
          opaDesktopDetailsOpen = opaMoreFilters.open;
        }
        opaMoreFilters.setAttribute('data-opa-mobile-detail', '');
        opaMoreFilters.open = true;
      } else if (opaMoreFilters.hasAttribute('data-opa-mobile-detail')) {
        opaMoreFilters.removeAttribute('data-opa-mobile-detail');
        opaMoreFilters.open = opaDesktopDetailsOpen;
      }
    }
    if (opaMobileMedia.addEventListener) {
      opaMobileMedia.addEventListener('change', opaSyncSingleLevelFilters);
    } else if (opaMobileMedia.addListener) {
      opaMobileMedia.addListener(opaSyncSingleLevelFilters);
    }
    opaSyncSingleLevelFilters();
  }
  // OPA SINGLE-LEVEL MOBILE AFISHA — END
"""

CSS_PATCH = """/* OPA SINGLE-LEVEL MOBILE AFISHA — CSS START
   Phone: only the outer 'Фильтры' accordion. The secondary controls are
   rendered with the primary ones, not hidden behind another summary.
   The status tabs, search and sorting stay outside and visible. */
@media screen and (max-width: 700px) {
  .afisha-page #afisha-more-filters > summary {
    display: none !important;
  }
  .afisha-page .afisha-filter-panel.expanded #afisha-filter-actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: .65rem;
    align-items: start;
    width: 100%;
  }
  .afisha-page #afisha-more-filters {
    flex: none;
    min-width: 0;
    max-width: 100%;
    width: 100%;
  }
  .afisha-page #afisha-more-filters .afisha-secondary-filters {
    padding: .3rem 0 0;
  }
  .afisha-page .afisha-filter-panel.expanded #afisha-reset {
    justify-self: start;
    margin-top: .25rem;
  }
}
/* OPA SINGLE-LEVEL MOBILE AFISHA — CSS END */
"""


def prepare(root: Path) -> dict[Path, tuple[str, str]]:
    """Check first; return original/new sources without touching disk."""
    root = root.resolve()
    path_js = root / AFISHA
    path_css = root / CSS
    for p in (path_js, path_css):
        if not p.is_file():
            raise RuntimeError(f"Не найден {p}; запускайте из корня сайта")

    original_js = path_js.read_text(encoding="utf-8")
    original_css = path_css.read_text(encoding="utf-8")

    # A failed or interrupted previous install must not silently create duplicates.
    if JS_MARKER in original_js:
        if original_js.count("// OPA SINGLE-LEVEL MOBILE AFISHA — START") != 1 or JS_PATCH.strip() not in original_js:
            raise RuntimeError("Обнаружен иной вариант мобильного JS: проверьте файл вручную")
        updated_js = original_js
    else:
        if original_js.count(JS_ANCHOR) != 1:
            raise RuntimeError("Не найден ожидаемый обработчик фильтров в sitebuild/afisha.py; версия не совпадает")
        updated_js = original_js.replace(JS_ANCHOR, JS_ANCHOR[:-len('  function show() {')] + JS_PATCH + "  function show() {", 1)

    if CSS_MARKER in original_css:
        if original_css.count(CSS_MARKER) != 1 or CSS_PATCH.strip() not in original_css:
            raise RuntimeError("Обнаружен иной вариант мобильного CSS: проверьте файл вручную")
        updated_css = original_css
    else:
        required = (
            ".afisha-filter-panel:not(.expanded) .afisha-primary-filters",
            ".afisha-page .afisha-status-switch",
            ".opa-afisha-mobile-toggle",
        )
        missing = [n for n in required if n not in original_css]
        if missing:
            raise RuntimeError(f"В CSS нет ожидаемых правил: {missing}")
        updated_css = original_css.rstrip() + "\n\n" + CSS_PATCH

    # Verify Python AST and the display logic anchors after patching.
    ast.parse(updated_js, filename=str(path_js))
    for needed in ('id="afisha-more-filters"', 'id="afisha-mobile-filter-toggle"',
                   'id="afisha-query"', 'id="afisha-sort"'):
        if needed not in updated_js:
            raise RuntimeError(f"В афише отсутствует необходимый элемент {needed}")
    if 'Актуальные и предстоящие выставки в музеях России и мира. Завершившиеся события сохраняются в архиве.' not in updated_js:
        print("Примечание: текст описания отличается от проверенной версии, но не меняется.")
    return {path_js: (original_js, updated_js), path_css: (original_css, updated_css)}


def write_all(changes: dict[Path, tuple[str, str]]) -> list[Path]:
    changed = {p: (before, after) for p, (before, after) in changes.items() if before != after}
    if not changed:
        return []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backups = {}
    try:
        for p, (before, _after) in changed.items():
            backup = p.with_name(f"{p.name}.before-single-mobile-filters-{stamp}.bak")
            if backup.exists():
                raise RuntimeError(f"Резервная копия существует: {backup}")
            backup.write_text(before, encoding="utf-8", newline="")
            backups[p] = backup
        for p, (_before, after) in changed.items():
            fd, temp_path = tempfile.mkstemp(prefix=".opa-mobile-filter-", dir=p.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as out:
                    out.write(after)
                os.replace(temp_path, p)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
    except BaseException:
        # Roll back both files on any write problem.
        for p, (before, _) in changed.items():
            if p in backups:
                p.write_text(before, encoding="utf-8", newline="")
        raise
    return list(backups.values())


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Проверить совместимость без изменений")
    mode.add_argument("--apply", action="store_true", help="Установить исправление с резервными копиями")
    cli.add_argument("--root", type=Path, default=Path.cwd())
    args = cli.parse_args(argv)
    try:
        changes = prepare(args.root)
        for p, (before, after) in changes.items():
            print(f"{p.relative_to(args.root.resolve())}: {'без изменений (уже исправлено)' if before == after else 'готово к исправлению'}")
        if args.check:
            print("OK: исходники подходят, изменений на диске нет.")
        else:
            copies = write_all(changes)
            print("OK: исправление установлено." if copies else "OK: уже установлено, повторных изменений нет.")
            for p in copies:
                print("Резервная копия:", p)
    except (OSError, SyntaxError, RuntimeError) as e:
        print("ОШИБКА:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
