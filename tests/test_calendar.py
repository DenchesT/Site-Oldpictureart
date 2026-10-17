# -*- coding: utf-8 -*-
"""Календарь выставок и блок «Идёт сейчас».

  • календарь — правильный iCalendar (RFC 5545): строки через CRLF, не
    длиннее 75 байт, запятые и точки с запятой экранированы;
  • событие на весь срок: конец в календаре не включается, поэтому к
    последнему дню прибавлен один;
  • метка времени — день поста, а не сборки: файл не меняется сам собой;
  • в «Идёт сейчас» — только выставки, которые на день сборки не закрылись,
    закрывающиеся раньше — выше; без таких блока нет вовсе.

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

ics = bs.render_calendar(V, [])
lines = ics.split("\r\n")
ok("строки календаря через CRLF и с концом в конце", ics.endswith("\r\n") and "\n" not in ics.replace("\r\n", ""))
ok("ни одна строка не длиннее 75 байт", all(len(x.encode("utf-8")) <= 75 for x in lines),
   max(lines, key=lambda x: len(x.encode("utf-8"))))
unfolded = ics.replace("\r\n ", "")
ok("начало и конец календаря", unfolded.startswith("BEGIN:VCALENDAR") and "END:VCALENDAR" in unfolded)
ok("событие на каждую выставку со сроком, поход в музей — нет", unfolded.count("BEGIN:VEVENT") == 3)
ok("конец события — на следующий день после закрытия",
   "DTSTART;VALUE=DATE:20250201" in unfolded and "DTEND;VALUE=DATE:20250502" in unfolded)
ok("запятая и точка с запятой экранированы",
   "SUMMARY:Выставка «Старая\\, давняя\; выставка»" in unfolded)
ok("метка времени — день поста", "DTSTAMP:20250312T000000Z" in unfolded)
ok("у события постоянный UID — по адресу страницы похода", "UID:visit-a@oldpictureart.ru" in unfolded)
ok("ссылка на страницу похода", "URL:https://oldpictureart.ru/visit-b.html" in unfolded)
ok("одинаковые данные — одинаковый файл", bs.render_calendar(V, []) == ics)

block = bs.now_on_block(V, [], today="2026-10-17")
ok("закрывшиеся к сборке выставки в блок не попадают", "visit-a.html" not in block)
ok("идущие и будущие — в блоке, закрывающиеся раньше — выше",
   block.find("visit-b.html") != -1 and block.find("visit-b.html") < block.find("visit-c.html"))
ok("у строки — даты для браузера", 'data-start="2026-09-01" data-end="2026-11-30"' in block)
ok("блок спрятан до скрипта", '<section class="now-on" id="now-on"' in block and " hidden>" in block)
ok("ссылки подписки на календарь",
   "webcal://oldpictureart.ru/exhibitions.ics" in block and "calendar.google.com" in block)
ok("нет идущих и будущих — нет и блока", bs.now_on_block(V[:1], [], today="2026-10-17") == "")

print("\n====== КАЛЕНДАРЬ ВЫСТАВОК ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra and not passed else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
