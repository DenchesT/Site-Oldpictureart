# -*- coding: utf-8 -*-
"""Афиша: крупные выставки в России и в мире (afisha.json → afisha.html).

  • запись с ошибкой (нет поля, дата не ГГГГ-ММ-ДД, конец раньше начала,
    ссылка не https, дубль) пропускается, а сборка говорит, что не так;
  • на день сборки: идущие — по дате закрытия, будущие — по дате открытия,
    закончившиеся и те, что откроются нескоро, на страницу не попадают;
  • «Россия» — country «Россия», остальное — «Мир»;
  • ссылка на страницу музея — только если музей есть на карте собраний;
  • сборка подсказывает, что убрать и когда пополнить список;
  • нет afisha.json — нет ни страницы, ни ссылок на неё;
  • сам afisha.json в порядке: без ошибок, ссылки https, даты разумные.

Запуск:  python tests/test_afisha.py
"""

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.argv = ["build_site.py"]

import build_site as bs  # noqa: E402
import site_common as sc  # noqa: E402
from sitebuild import afisha as af  # noqa: E402

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


TODAY = date(2026, 10, 19)


def item(title, country="Франция", start="2026-09-01", end="2026-12-31", **kw):
    d = {"title": title, "venue": kw.pop("venue", "Музей " + title), "city": kw.pop("city", "Париж"),
         "country": country, "start": start, "end": end, "url": kw.pop("url", "https://example.org/" + str(len(title)))}
    d.update(kw)
    return d


# ---------- проверка записи ----------
ok("хорошая запись — без замечаний", af.problems(item("Моне")) == [])
ok("нет поля — замечание", any("venue" in p for p in af.problems({k: v for k, v in item("Моне").items() if k != "venue"})))
ok("дата не ГГГГ-ММ-ДД — замечание", any("start" in p for p in af.problems(item("Моне", start="01.09.2026"))))
ok("конец раньше начала — замечание", any("раньше" in p for p in af.problems(item("Моне", start="2026-12-01", end="2026-11-01"))))
ok("area — только moscow, spb или regions", any("area" in p for p in af.problems(item("Моне", area="москва"))))
ok("город России: Москва и Подмосковье", af.area(item("М", country="Россия", city="Москва")) == "moscow"
   and af.area(item("А", country="Россия", city="Абрамцево")) == "moscow")
ok("…Петербург и пригороды", af.area(item("П", country="Россия", city="Санкт-Петербург")) == "spb"
   and af.area(item("Г", country="Россия", city="Гатчина")) == "spb")
ok("…остальное — «Другие города»", af.area(item("К", country="Россия", city="Казань")) == "regions")
ok("…город не угадался — можно указать area", af.area(item("Х", country="Россия", city="Хотьково", area="moscow")) == "moscow")
ok("у выставок мира города нет", af.area(item("Л", city="Лондон")) == "")
ok("ссылка не http(s) — замечание", any("url" in p for p in af.problems(item("Моне", url="www.example.org"))))

tmp = tempfile.mkdtemp()
try:
    path = os.path.join(tmp, "afisha.json")
    data = {"updated": "2026-10-19", "exhibitions": [
        item("Идёт в Париже", end="2026-11-30", museum="Музей д’Орсе, Париж", title_orig="En cours"),
        item("Последние дни", end="2026-10-22"),
        item("Закрылась", start="2026-01-01", end="2026-09-30"),
        item("Давно закрылась", start="2025-01-01", end="2025-06-30"),
        item("Скоро откроется", start="2026-11-20", end="2027-03-01"),
        item("Откроется нескоро", start="2027-06-01", end="2027-09-01"),
        item("Айвазовский", country="Россия", city="Санкт-Петербург", venue="Русский музей", start="2026-10-16", end="2027-05-10",
             museum="Государственный Русский музей, Санкт-Петербург"),
        item("Репин", country="Россия", city="Ярославль", start="2026-10-24", end="2027-01-24"),
        item("Ошибка в дате", start="2026-31-10"),
        item("Идёт в Париже", end="2026-11-30"),       # дубль
    ]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    items, errors, updated = af.load_afisha(path)
    titles = [x["title"] for x in items]
    ok("записи с ошибками пропущены, остальные прочитаны", len(items) == 8 and "Ошибка в дате" not in titles, str(titles))
    ok("про ошибку сказано, что не так", any("Ошибка в дате" in e and "start" in e for e in errors), str(errors))
    ok("дубль замечен", any("дважды" in e for e in errors), str(errors))
    ok("дата обновления прочитана", updated == "2026-10-19")
    ok("у записи — якорь латиницей", all(re.fullmatch(r"a-[a-z0-9-]+", x["id"]) for x in items), str([x["id"] for x in items]))

    parts = af.split(items, TODAY)
    run_world = [x["title"] for x in parts["world"]["running"]]
    ok("идущие — кто закрывается раньше, выше", run_world == ["Последние дни", "Идёт в Париже"], str(run_world))
    ok("будущие в ближайшие месяцы — в «Скоро»", [x["title"] for x in parts["world"]["soon"]] == ["Скоро откроется"])
    ok("закончившиеся и нескорые — ни там, ни там",
       not {"Закрылась", "Давно закрылась", "Откроется нескоро"} & set(run_world + [x["title"] for x in parts["world"]["soon"]]))
    ok("Россия — отдельно", [x["title"] for x in parts["russia"]["running"]] == ["Айвазовский"]
       and [x["title"] for x in parts["russia"]["soon"]] == ["Репин"])
    ok("срок по-русски: «16 октября 2026 — 10 мая 2027»", af.date_range(items[6]) == "16 октября 2026 — 10 мая 2027", af.date_range(items[6]))
    ok("в одном году год один раз: «1 сентября — 30 ноября 2026»", af.date_range(items[0]) == "1 сентября — 30 ноября 2026", af.date_range(items[0]))
    ok("где: для мира — со страной, для России — без", af.where_line(items[0]).endswith("Париж, Франция")
       and af.where_line(items[6]) == "Русский музей · Санкт-Петербург")

    # ---------- страница ----------
    known = {"Государственный Русский музей, Санкт-Петербург"}
    page = af.render_afisha_page(items, updated, known, TODAY)
    ok("на странице идущие и будущие", "Идёт в Париже" in page and "Скоро откроется" in page and "Репин" in page)
    ok("закончившихся на странице нет", "Закрылась" not in page and "Откроется нескоро" not in page)
    ok("название ведёт на страницу выставки в новой вкладке",
       re.search(r'<h3 class="afisha-title"><a href="https://example\.org/\d+" target="_blank" rel="noopener">', page))
    ok("оригинальное название — под русским", '<p class="afisha-orig">En cours</p>' in page)
    ok("ссылка на страницу музея — только если он есть на карте",
       page.count("afisha-museum") == 1 and sc.museum_page("Государственный Русский музей, Санкт-Петербург") in page)
    ok("у записи даты для браузера и вкладка",
       'data-start="2026-10-16" data-end="2027-05-10" data-region="russia"' in page)
    ok("вкладки Россия и Мир со счётчиками",
       'data-region="russia" aria-pressed="true">Россия<span class="visit-count">2</span>' in page
       and 'data-region="world" aria-pressed="false">Мир<span class="visit-count">3</span>' in page)
    ok("дата обновления списка", "Список обновлён 19 октября 2026" in page)
    ok("переключатель городов России со счётчиками",
       'data-area="all" aria-pressed="true">Все города<span class="visit-count">2</span>' in page
       and 'data-area="spb" aria-pressed="false">Петербург<span class="visit-count">1</span>' in page
       and 'data-area="regions" aria-pressed="false">Другие города<span class="visit-count">1</span>' in page)
    ok("у записи России — город, у мира — нет", 'data-region="russia" data-area="spb"' in page
       and 'data-region="world" data-area' not in page)
    ok("адрес страницы — канонический", f'{sc.BASE_URL}/afisha.html' in page)

    # ---------- блок на главной ----------
    block = af.afisha_block(items, TODAY)
    ok("блок на главной: обе колонки", 'data-region="russia"' in block and 'data-region="world"' in block)
    ok("строки ведут на запись в афише", f'href="afisha.html#{items[0]["id"]}"' in block)
    ok("закончившихся в блоке нет", "Закрылась" not in block)
    ok("блок спрятан до скрипта", 'id="afisha-block"' in block and " hidden>" in block)
    ok("всё закончилось — блока нет", af.afisha_block([items[2], items[3]], TODAY) == "")

    # ---------- подсказки сборки ----------
    class Log:
        def __init__(self):
            self.lines = []

        def info(self, m):
            self.lines.append(("info", m))

        def warning(self, m):
            self.lines.append(("warning", m))
    log = Log()
    af.afisha_report(items, errors, updated, TODAY, log=log)
    text = " | ".join(m for _, m in log.lines)
    ok("ошибки записей — предупреждением", any(k == "warning" and "Ошибка в дате" in m for k, m in log.lines), text)
    ok("давно закончившиеся — подсказка убрать", "Давно закрылась" in text and "Закрылась»" in text, text)
    ok("мало идущих — напоминание пополнить", any(k == "warning" and "пора добавить" in m for k, m in log.lines), text)
    log = Log()
    af.afisha_report(items, [], "2026-01-01", TODAY, log=log)
    ok("давно не обновлялся список — подсказка", any("не обновлялся" in m for _, m in log.lines))

    # ---------- запись страницы ----------
    out = os.path.join(tmp, "docs")
    os.makedirs(out)
    saved = af.OUTPUT_DIR
    try:
        af.OUTPUT_DIR = out
        n = af.generate_afisha(known, TODAY, path)
        ok("generate_afisha пишет afisha.html", n == 5 and os.path.exists(os.path.join(out, "afisha.html")), str(n))
        empty = os.path.join(tmp, "empty.json")
        with open(empty, "w", encoding="utf-8") as f:
            json.dump({"exhibitions": []}, f)
        ok("пустой список — страница убирается", af.generate_afisha(known, TODAY, empty) == 0
           and not os.path.exists(os.path.join(out, "afisha.html")))
    finally:
        af.OUTPUT_DIR = saved
    ok("has_afisha: есть записи — да, нет файла — нет", sc.has_afisha(path) and not sc.has_afisha(os.path.join(tmp, "нет.json")))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---------- сайт ----------
ok("ссылка «Афиша» в подвале", 'href="afisha.html">Афиша</a>' in sc.site_footer())
if os.path.exists("docs/afisha.html"):
    idx = open("docs/index.html", encoding="utf-8").read()
    ok("на главной — блок и пункт меню", 'id="afisha-block"' in idx and 'icon-afisha' in idx)
    ok("афиша в карте сайта", "/afisha.html</loc>" in open("docs/sitemap.xml", encoding="utf-8").read())

# ---------- сам afisha.json ----------
items, errors, updated = af.load_afisha()
ok("afisha.json читается без ошибок", items and not errors, "; ".join(errors[:3]))
ok("в нём и Россия, и мир", any(af.region(x) == "russia" for x in items) and any(af.region(x) == "world" for x in items))
ok("все ссылки — https", all(x["url"].startswith("https://") for x in items),
   ", ".join(x["title"] for x in items if not x["url"].startswith("https://")))
ok("якоря не повторяются", len({x["id"] for x in items}) == len(items))
ok("заметки короткие — в одну-две строки", all(len(x.get("note", "")) <= 140 for x in items),
   ", ".join(x["title"] for x in items if len(x.get("note", "")) > 140))
ok("выставки не длиннее двух лет (опечатка в годе?)",
   all((date.fromisoformat(x["end"]) - date.fromisoformat(x["start"])).days < 730 for x in items),
   ", ".join(x["title"] for x in items if (date.fromisoformat(x["end"]) - date.fromisoformat(x["start"])).days >= 730))
names = set(bs.museum_names(json.load(open("posts_meta.json", encoding="utf-8")),
                            json.load(open("visits_meta.json", encoding="utf-8")) if os.path.exists("visits_meta.json") else []))
lost = [x["museum"] for x in items if x.get("museum") and x["museum"] not in names]
ok("поле museum — точные названия с карты собраний", not lost, ", ".join(lost))
ok("дата обновления записана", bool(updated))

print("\n====== АФИША ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra and not passed else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
