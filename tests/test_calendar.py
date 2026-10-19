# -*- coding: utf-8 -*-
"""Блок «Идёт сейчас» — и то, что календаря выставок больше нет.

Раньше здесь проверялся и календарь exhibitions.ics; его убрали
(19.10.2026), имя файла проверки осталось прежним.

  • в «Идёт сейчас» — только выставки, которые на день сборки не закрылись,
    закрывающиеся раньше — выше; без таких блока нет вовсе;
  • ссылок на подписку на календарь в блоке нет, файла календаря сборка
    не пишет, а оставшийся от прежней сборки убирает.

Запуск:  python tests/test_calendar.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.chdir(os.path.join(HERE, ".."))
sys.argv = ["build_site.py"]

import build_site as bs  # noqa: E402

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


V = [
    {"kind": "выставка", "title": "Старая, давняя; выставка", "place": "Музей Альфа", "filename": "visit-a.html",
     "run": "01.02.2025 — 01.05.2025", "visited": "10.03.2025", "date": "2025-03-12"},
    {"kind": "выставка", "title": "Идущая", "place": "Музей Бета", "filename": "visit-b.html",
     "run": "01.09.2026 — 30.11.2026", "visited": "05.10.2026", "date": "2026-10-06"},
    {"kind": "выставка", "title": "Скорая", "place": "Музей Гамма", "filename": "visit-c.html",
     "run": "01.11.2026 — 31.12.2026", "visited": "", "date": "2026-10-10"},
    {"kind": "музей", "title": "", "place": "Музей Дельта", "filename": "visit-d.html", "run": "",
     "visited": "01.10.2026", "date": "2026-10-02"},
]

block = bs.now_on_block(V, [], today="2026-10-17")
ok("закрывшиеся к сборке выставки в блок не попадают", "visit-a.html" not in block)
ok("идущие и будущие — в блоке, закрывающиеся раньше — выше",
   block.find("visit-b.html") != -1 and block.find("visit-b.html") < block.find("visit-c.html"))
ok("у строки — даты для браузера", 'data-start="2026-09-01" data-end="2026-11-30"' in block)
ok("блок спрятан до скрипта", '<section class="now-on" id="now-on"' in block and " hidden>" in block)
ok("ссылок на подписку на календарь нет",
   "webcal:" not in block and "calendar.google.com" not in block and ".ics" not in block)
ok("нет идущих и будущих — нет и блока", bs.now_on_block(V[:1], [], today="2026-10-17") == "")

# ---------- календаря больше нет ----------
ok("функций календаря в сборке нет", not hasattr(bs, "render_calendar") and not hasattr(bs, "calendar_links"))
import shutil  # noqa: E402
import tempfile  # noqa: E402
import sitebuild.visits as sv  # noqa: E402
# Только уборку файла: generate_visit_pages целиком здесь звать нельзя —
# она убирает из настоящей docs/ страницы походов, которых нет в списке.
tmp = tempfile.mkdtemp()
try:
    open(os.path.join(tmp, "exhibitions.ics"), "w").close()
    ok("прежний exhibitions.ics сборка убирает", sv.drop_calendar(tmp) and not os.path.exists(os.path.join(tmp, "exhibitions.ics")))
    ok("нет файла — и делать нечего", sv.drop_calendar(tmp) is False)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
src = open(sv.__file__, encoding="utf-8").read()
ok("generate_visit_pages убирает его сама и нового не пишет",
   "    drop_calendar()\n" in src and ".ics" not in src.replace("exhibitions.ics", ""))
ok("на страницах нет ссылок на календарь",
   not any("exhibitions.ics" in open(p, encoding="utf-8").read() for p in
           [os.path.join("docs", n) for n in ("index.html", "visits.html") if os.path.exists(os.path.join("docs", n))]))

print("\n====== «ИДЁТ СЕЙЧАС» ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra and not passed else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
