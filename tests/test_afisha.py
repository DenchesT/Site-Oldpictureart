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
  • фильтры: город России, страна для «Мира», эпоха (tags); «Рядом со мной»
    и карта на телефоне — за кнопкой; «Успеть на этой неделе»;
  • «На сайте: Айвазовский — 3 работы» — фамилии в падежах, частые фамилии
    только с именем; явный список artists;
  • «Был — снимки и впечатления» и обратная ссылка «Сейчас в афише»;
  • разметка ExhibitionEvent для поисковиков;
  • ссылки выставок проверяются раз в неделю, нерабочие — в журнал;
  • сам afisha.json в порядке: без ошибок, ссылки https, даты разумные,
    у каждой записи есть эпоха.

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
ok("lat без lon — замечание", any("парой" in p for p in af.problems(item("Моне", lat=48.86))))
ok("широта за пределами — замечание", any("широта" in p for p in af.problems(item("Моне", lat=148.86, lon=2.33))))
ok("area — только moscow, spb или regions", any("area" in p for p in af.problems(item("Моне", area="москва"))))
ok("город России: Москва и Подмосковье", af.area(item("М", country="Россия", city="Москва")) == "moscow"
   and af.area(item("А", country="Россия", city="Абрамцево")) == "moscow")
ok("…Петербург и пригороды", af.area(item("П", country="Россия", city="Санкт-Петербург")) == "spb"
   and af.area(item("Г", country="Россия", city="Гатчина")) == "spb")
ok("…остальное — «Другие города»", af.area(item("К", country="Россия", city="Казань")) == "regions")
ok("…город не угадался — можно указать area", af.area(item("Х", country="Россия", city="Хотьково", area="moscow")) == "moscow")
ok("у выставок мира города нет", af.area(item("Л", city="Лондон")) == "")
_js = open(os.path.join(HERE, "test_afisha.js"), encoding="utf-8").read()
_js_list = lambda name: set(re.findall(r"'([^']+)'", re.search(r"const " + name + r" = \[(.*?)\];", _js, re.S).group(1)))
ok("списки городов в test_afisha.js — те же, что MOSCOW_AREA и SPB_AREA",
   _js_list("MOSCOW") == af.MOSCOW_AREA and _js_list("SPB") == af.SPB_AREA)
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
    ok("прошедшие выставки и дальние анонсы доступны на странице", "Закрылась" in page and "Откроется нескоро" in page)
    ok("архив имеет отдельный список", 'id="afisha-archive"' in page and 'data-status="archive"' in page)
    ok("все девять фильтров подключены", all('id="afisha-' + k + '"' in page for k in (
        'closing', 'opening', 'venue', 'query', 'artist', 'archive-year', 'sort', 'only-favorites', 'reset')))
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
    ok("город России — выпадающий список (числа ставит скрипт)",
       '<select id="afisha-area"><option value="all" data-label="Все города">Все города</option>' in page
       and '<option value="spb" data-label="Петербург">Петербург</option>' in page
       and '<option value="regions" data-label="Другие города">Другие города</option>' in page)
    ok("страна — для «Мира», спрятана, пока выбрана Россия; чаще встречающиеся — выше",
       '<label class="afisha-select" id="afisha-country-box" hidden>' in page
       and page.find('<option value="Франция"') > 0)
    ok("эпохи доступны для всех периодов", '<select id="afisha-epoch"><option value="all" data-label="Все эпохи">Все эпохи</option></select>' in page)
    ok("«Успеть на этой неделе» — место под блок, заполняет скрипт",
       '<section class="afisha-week" id="afisha-week"' in page and 'id="afisha-week-list"' in page)
    ok("без точек на карте нет и «Рядом со мной»", 'id="afisha-near-btn"' not in page)
    ok("у записи России — город, у мира — нет", 'data-region="russia" data-area="spb"' in page
       and 'data-region="world" data-area' not in page)
    ok("адрес страницы — канонический", f'{sc.BASE_URL}/afisha.html' in page)

    # ---------- раздел в панели главной ----------
    block = af.afisha_block(items, TODAY)
    ok("в панели главной: Россия и мир", 'data-region="russia"' in block and 'data-region="world"' in block)
    ok("…в России три, в мире две — упор на Россию",
       'data-region="russia" data-limit="3"' in block and 'data-region="world" data-limit="2"' in block)
    ok("…заголовок — ссылка на афишу", '<a class="sidebar-title sidebar-icon icon-afisha no-arrow" href="afisha.html">' in block)
    ok("строки ведут на запись в афише", f'href="afisha.html#{items[0]["id"]}"' in block)
    ok("…в строке город, без длинного названия музея", '<span class="now-where">Санкт-Петербург</span>' in block)
    ok("закончившихся в разделе нет", "Закрылась" not in block)
    ok("список спрятан до скрипта", 'id="afisha-block"' in block and '<div class="afisha-side" hidden>' in block)
    ended = af.afisha_block([items[2], items[3]], TODAY)
    ok("всё закончилось — остаётся только ссылка", 'href="afisha.html"' in ended and "afisha-col" not in ended)
    ok("афиши нет — нет и раздела", af.afisha_block([], TODAY) == "")

    # ---------- карта ----------
    import types
    calls = []
    fake = types.SimpleNamespace(geocode=lambda key, cache, ov=None, **kw: calls.append((key, ov)) or (
        {"lat": 48.86, "lon": 2.33, "precision": "exact"} if "Последние" in key else None))
    real_gm = sys.modules.get("generate_map")
    places = os.path.join(tmp, "places.json")
    with open(places, "w", encoding="utf-8") as f:
        json.dump({af.place_key(items[4]): {"lat": 48.85, "lon": 2.35, "precision": "approx", "hint": ""}}, f)
    manual = dict(items[0], lat=48.8600, lon=2.3266)
    try:
        sys.modules["generate_map"] = fake
        co = af.locate([manual, items[1], items[4], items[7]], set(), offline=False, path=places, log=lambda m: None)
    finally:
        if real_gm is not None:
            sys.modules["generate_map"] = real_gm
        else:
            sys.modules.pop("generate_map", None)
    ok("координаты: вписанные в запись — главнее всего", co.get(manual["id"]) == (48.86, 2.3266, False), str(co))
    rough = dict(items[0], lat=54.72, lon=55.94, approx=True)
    ok("…с \"approx\": true — метка помечена приблизительной",
       af.locate([rough], set(), offline=True, path=places, log=lambda m: None).get(rough["id"]) == (54.72, 55.94, True))
    ok("…найденное раньше — из кэша, без поиска", co.get(items[4]["id"]) == (48.85, 2.35, True)
       and not any(af.place_key(items[4]) == c[0] for c in calls), str(calls))
    ok("…остальное ищет поиск карты собраний", co.get(items[1]["id"]) == (48.86, 2.33, False)
       and af.place_key(items[1]) in [c[0] for c in calls])
    ok("…не нашлось — метки нет", items[7]["id"] not in co)
    saved_places = json.load(open(places, encoding="utf-8"))
    ok("найденное записано в кэш", saved_places.get(af.place_key(items[1]), {}).get("lat") == 48.86)
    calls.clear()
    try:
        sys.modules["generate_map"] = fake
        co2 = af.locate([items[1], dict(items[2], venue="Новое место")], set(), offline=True, path=places, log=lambda m: None)
    finally:
        if real_gm is not None:
            sys.modules["generate_map"] = real_gm
        else:
            sys.modules.pop("generate_map", None)
    ok("без сети — только найденное, поиск не зовётся", items[1]["id"] in co2 and not calls)
    page_map = af.render_afisha_page(items, updated, known, TODAY, co)
    ok("на странице — карта и данные для меток", 'id="afisha-map"' in page_map
       and f'id="{items[1]["id"]}"' in page_map and 'data-lat="48.86000" data-lon="2.33000"' in page_map)
    ok("…у записи с координатами — кнопка «на карте», без них — нет",
       page_map.count('class="afisha-pin"') == sum(1 for it in items if it["id"] in co and af.phase(it, TODAY) in ("running", "soon")))
    ok("…Leaflet и группировка меток — свои копии", "vendor/leaflet/leaflet.js" in page_map
       and "vendor/leaflet.markercluster/leaflet.markercluster.js" in page_map and "map-config.js" in page_map)
    ok("нет ни одной точки — нет и карты", 'id="afisha-map"' not in af.render_afisha_page(items, updated, known, TODAY, {})
       and "leaflet.js" not in af.render_afisha_page(items, updated, known, TODAY, {}))
    ok("на телефоне карта — за кнопкой «Показать на карте» со счётчиком меток",
       '<button type="button" class="afisha-map-toggle" id="afisha-map-toggle" aria-expanded="false"' in page_map
       and re.search(r'Показать на карте</span><span class="visit-count">\d+</span>', page_map))
    ok("есть точки — есть «Рядом со мной», и сказано, что место не уходит на сайт",
       'id="afisha-near-btn" aria-pressed="false">Рядом со мной</button>' in page_map
       and "только в вашем браузере" in page_map)

    # ---------- разметка для поисковиков ----------
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', page_map, re.S)
    graph = json.loads(ld.group(1))["@graph"] if ld else []
    events = [g for g in graph if g.get("@type") == "ExhibitionEvent"]
    ok("разметка ExhibitionEvent — у каждой идущей и будущей выставки",
       len(events) == sum(1 for it in items if af.phase(it, TODAY) in ("running", "soon")), str(len(events)))
    ev = next((e for e in events if e["name"] == "Последние дни"), {})
    ok("…даты, место с адресом, ссылка", ev.get("startDate") == "2026-09-01" and ev.get("endDate") == "2026-10-22"
       and ev.get("location", {}).get("address", {}).get("addressLocality") == "Париж"
       and ev.get("url", "").startswith("https://"), str(ev))
    ok("…точные координаты — в разметке", ev.get("location", {}).get("geo", {}).get("latitude") == 48.86)
    ev_rough = next((e for e in events if e["name"] == "Скоро откроется"), {})
    ok("…приблизительные (по городу) — нет", "geo" not in ev_rough.get("location", {}), str(ev_rough))
    ok("закончившихся в разметке нет", not any(e["name"] in ("Закрылась", "Откроется нескоро") for e in events))

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
    ok("давно закончившиеся — сохранены для архива", "Давно закрылась" in text and "оставьте их" in text, text)
    ok("мало идущих — напоминание пополнить", any(k == "warning" and "пора добавить" in m for k, m in log.lines), text)
    log = Log()
    af.afisha_report(items, [], "2026-01-01", TODAY, log=log)
    ok("давно не обновлялся список — подсказка", any("не обновлялся" in m for _, m in log.lines))

    # ---------- эпоха ----------
    ok("tags — только из списка эпох", af.problems(item("М", tags=["impr", "xix"])) == []
       and any("tags" in p for p in af.problems(item("М", tags=["импрессионизм"])))
       and any("tags" in p for p in af.problems(item("М", tags="impr"))))
    ok("artists — список имён", any("artists" in p for p in af.problems(item("М", artists="Моне"))))
    tagged = [dict(items[0], tags=["impr"]), dict(items[6], tags=["russian", "xix"])]
    page_t = af.render_afisha_page(tagged, updated, known, TODAY)
    ok("у записи — метки эпохи для фильтра", 'data-tags="russian xix"' in page_t)
    ok("в списке эпох — только встретившиеся, в порядке EPOCHS",
       re.search(r'<select id="afisha-epoch">.*?</select>', page_t).group(0).count("<option") == 4
       and page_t.find('value="xix"') < page_t.find('value="impr"') < page_t.find('value="russian"')
       and 'value="old"' not in page_t)

    # ---------- «На сайте: …» ----------
    posts = [
        {"artist": "Иван Константинович Айвазовский", "filename": "aivazovsky-b-1850.html", "title": "Буря",
         "creation_year": 1850, "thumbs": ["images/thumbs/a1.webp"]},
        {"artist": "Иван Константинович Айвазовский", "filename": "aivazovsky-a-1840.html", "title": "Штиль",
         "creation_year": 1840, "thumbs": ["images/thumbs/a2.webp"]},
        {"artist": "Иван Константинович Айвазовский", "filename": "aivazovsky-c.html", "title": "Без года",
         "thumbs": ["images/thumbs/a3.webp"]},
        {"artist": "Клод Моне", "filename": "monet-1.html", "title": "Кувшинки", "thumbs": ["images/thumbs/m1.webp"]},
        {"artist": "Николай Дмитриевич Кузнецов", "filename": "kuznetsov-1.html", "title": "Портрет"},
        {"artist": "Константин Андреевич Сомов", "filename": "somov-1.html", "title": "Арлекин"},
        {"artist": "Илья Ефимович Репин", "filename": "repin-1.html", "title": "Бурлаки"},
        {"artist": "Винсент Виллем ван Гог", "filename": "gogh-1.html", "title": "Ирисы"},
        {"artist": "Илер-Жермен-Эдгар де Га (Эдгар Дега)", "filename": "degas-1.html", "title": "Балерины"},
        {"artist": "Анри де Тулуз-Лотрек-Монфа", "filename": "lautrec-1.html", "title": "Мулен Руж"},
        {"artist": "Анонимные художники, Италия", "filename": "anon-1.html", "title": "Икона"},
    ]
    idx = af.works_index(posts)
    ok("фамилия: обычная, «Ван Гог», в скобках, тройная через дефис",
       af.artist_keys("Клод Моне") == [("Моне", "Моне")]
       and af.artist_keys("Винсент Виллем ван Гог") == [("Ван Гог", "Ван Гог")]
       and af.artist_keys("Илер-Жермен-Эдгар де Га (Эдгар Дега)") == [("Дега", "Дега")]
       and af.artist_keys("Анри де Тулуз-Лотрек-Монфа") == [("Тулуз-Лотрек", "Тулуз-Лотрек")])
    ok("…«Анонимные художники, …» — не человек, не ищется", af.artist_keys("Анонимные художники, Италия") == [])
    ok("…другое написание фамилии подписывается по-нашему",
       ("Русиньоль", "Рузиньол") in af.artist_keys("Сантьяго Рузиньол-и-Пратс"))

    def found(title, note="", **kw):
        return [(a, label) for a, label, _ in af.site_works(dict(item(title, note=note), **kw), idx)]
    ok("фамилия в падеже: «Айвазовского», «Репина», «ван Гога»",
       found("Мир Айвазовского") == [("Иван Константинович Айвазовский", "Айвазовский")]
       and found("Портреты Репина") == [("Илья Ефимович Репин", "Репин")]
       and found("Подсолнухи ван Гога") == [("Винсент Виллем ван Гог", "Ван Гог")])
    ok("…несклоняемая — как есть: «Моне», «Дега»", found("Моне и Дега") == [("Клод Моне", "Моне"), ("Илер-Жермен-Эдгар де Га (Эдгар Дега)", "Дега")])
    ok("…часть другого слова — не совпадение: «Сомовский», «Репинский»", found("Сомовский дом. Репинский уголок") == [])
    ok("…частая фамилия — только с именем или инициалом",
       found("Собрание Кузнецова") == [] and found("Николай Кузнецов и его круг")[0][0] == "Николай Дмитриевич Кузнецов"
       and found("Н. Д. Кузнецов. Портреты") != [])
    ok("…ищется и в заметке", found("Морская живопись", "В том числе Айвазовский")[0][1] == "Айвазовский")
    ok("…явный список artists главнее поиска", found("Мир Айвазовского", artists=["Клод Моне"]) == [("Клод Моне", "Моне")]
       and found("Мир Айвазовского", artists=[]) == [])
    w = af.works_html(af.site_works(item("Айвазовский и Моне"), idx))
    ok("«На сайте: Айвазовский — 3 работы» со ссылкой на страницу художника",
       '<a href="' + af.artist_slug("Иван Константинович Айвазовский") + '">Айвазовский</a> — 3 работы' in w
       and "Моне</a> — 1 работа" in w, w[:300])
    ok("…миниатюры по очереди от каждого, сначала ранние", re.findall(r'<a href="([^"]+)" title=', w)[:3]
       == ["aivazovsky-a-1840.html", "monet-1.html", "aivazovsky-b-1850.html"], w)
    ok("…не больше четырёх, грузятся лениво", w.count("<li>") == 4 and 'loading="lazy"' in w)
    ok("ничего не нашлось — блока нет", af.works_html([]) == "")
    page_w = af.render_afisha_page([dict(items[6], title="Мир Айвазовского")], updated, known, TODAY, index=idx)
    ok("на странице афиши — блок «На сайте»", 'class="afisha-works"' in page_w and "aivazovsky-a-1840.html" in page_w)

    # ---------- «Был — снимки и впечатления» ----------
    visits = [
        {"filename": "visit-2026-10-12-skazka.html", "kind": "выставка", "title": "«Сказка рядом»",
         "run": "15.08.2026 — 08.11.2026"},
        {"filename": "visit-2024-old.html", "kind": "выставка", "title": "Сказка рядом", "run": "01.02.2024 — 01.05.2024"},
        {"filename": "visit-2026-cafe.html", "kind": "прогулка", "title": "Сказка рядом"},
        {"filename": "visit-2026-repin.html", "kind": "выставка", "title": "Илья Репин. Портреты друзей"},
    ]
    show = [dict(item("Сказка рядом", start="2026-08-15", end="2026-11-08"), id="a-skazka"),
            dict(item("Репин", start="2026-09-01", end="2026-12-01"), id="a-repin"),
            dict(item("Другое", start="2026-09-01", end="2026-12-01"), id="a-other", visit="visit-2026-repin.html"),
            dict(item("Морская живопись XIX века", start="2026-09-01", end="2026-12-01"), id="a-sea")]
    mv = af.match_visits(show, visits)
    ok("поход находится по названию и срокам (кавычки не мешают)", mv.get("a-skazka", {}).get("filename") == "visit-2026-10-12-skazka.html", str(mv))
    ok("…выставка с тем же названием в другие годы — не она",
       af.match_visits([show[0]], visits[1:]).get("a-skazka") is None)
    ok("…прогулка — не выставка", af.match_visits([show[0]], [visits[2]]) == {})
    ok("…короткое название не цепляется за длинное («Репин» ≠ «Илья Репин. …»)", "a-repin" not in mv)
    ok("…поле visit в записи — явно", mv.get("a-other", {}).get("filename") == "visit-2026-repin.html")
    ok("…не был — нет", "a-sea" not in mv)
    page_v = af.render_afisha_page([dict(items[6], id="a-skazka")], updated, known, TODAY,
                                   visited={"a-skazka": visits[0]})
    ok("на странице — «Был — снимки и впечатления» со ссылкой на поход",
       '<p class="afisha-been"><a href="visit-2026-10-12-skazka.html">Был — снимки и впечатления</a></p>' in page_v)
    from sitebuild import visits as vs
    back = vs.afisha_backlink(dict(show[0]))
    ok("обратно: на странице похода — «Сейчас в афише →», пока выставка идёт",
       back == '<p class="afisha-backlink" data-end="2026-11-08" hidden><a href="afisha.html#a-skazka">Сейчас в афише →</a></p>')
    ok("…выставки нет в афише — нет и ссылки", vs.afisha_backlink(None) == "")

    # ---------- «Сейчас в афише» на странице музея ----------
    mb = af.museum_afisha_block([items[6], items[0]])
    ok("блок музея: записи с датами для браузера, ссылки на афишу, спрятан до скрипта",
       'id="museum-afisha"' in mb and ' hidden>' in mb.split("<h2")[0]
       and f'href="afisha.html#{items[0]["id"]}"' in mb and 'data-start="2026-10-16" data-end="2027-05-10"' in mb
       and f'data-soon="{af.SOON_DAYS}"' in mb)
    ok("…по дате закрытия; нет выставок — нет блока",
       mb.find(items[0]["id"]) < mb.find(items[6]["id"]) and af.museum_afisha_block([]) == "")
    from sitebuild import museums as ms
    rm = "Государственный Русский музей, Санкт-Петербург"
    mpage = ms.render_museum_page(rm, [], [], {"name": rm, "city": "Санкт-Петербург"}, [], {}, 3, afisha=[items[6]])
    ok("страница музея: блок «Сейчас в афише» и его скрипт",
       'id="museum-afisha"' in mpage and "museum-afisha" in af.MUSEUM_AFISHA_JS and af.MUSEUM_AFISHA_JS.strip()[:20] in mpage)
    ok("…без выставок — ни блока, ни скрипта",
       'id="museum-afisha"' not in ms.render_museum_page("Музей", [], [], {"name": "Музей"}, [], {}, 3)
       and "getElementById('museum-afisha')" not in ms.render_museum_page("Музей", [], [], {"name": "Музей"}, [], {}, 3))

    # ---------- проверка ссылок раз в неделю ----------
    links = os.path.join(tmp, "links.json")
    checked = []

    def fake_check(u):
        checked.append(u)
        if u.endswith("/12"):
            return ("bad", "нет страницы (404)")
        if u.endswith("/14"):
            return ("bad", "уводит на https://example.org/new")
        return ("ok", "")
    link_items = [item("Двенадцать букв", url="https://example.org/12"),
                  item("Ведёт куда-то", url="https://example.org/14"), item("Хорошая", url="https://example.org/ok")]
    log = Log()
    bad = af.check_afisha_links(link_items, TODAY, path=links, check=fake_check, log=log)
    ok("ссылки афиши проверяются, нерабочие — предупреждением с подсказкой",
       bad == {"https://example.org/12": "нет страницы (404)"}
       and any(k == "warning" and "«Двенадцать букв»" in m and "afisha.json" in m for k, m in log.lines), str(log.lines))
    ok("…переезд на другой адрес — не поломка", "https://example.org/14" not in bad)
    ok("…итог записан с датой", json.load(open(links, encoding="utf-8")).get("checked") == TODAY.isoformat())
    checked.clear()
    log = Log()
    af.check_afisha_links(link_items, date(2026, 10, 23), path=links, check=fake_check, log=log)
    ok("…через несколько дней — не проверяет, но о нерабочей напоминает",
       not checked and any("«Двенадцать букв»" in m for _, m in log.lines))
    af.check_afisha_links(link_items, date(2026, 10, 26), path=links, check=fake_check, log=Log())
    ok("…через неделю — проверяет снова", len(checked) == 3)
    checked.clear()
    af.check_afisha_links(link_items, date(2026, 12, 1), offline=True, path=links, check=fake_check, log=Log())
    ok("…без сети — не проверяет", not checked)
    log = Log()
    af.check_afisha_links(link_items, date(2026, 12, 2), path=os.path.join(tmp, "l2.json"),
                          check=lambda u: 1 / 0, log=log)
    ok("…проверка сломалась — сборка идёт дальше, файл не пишется",
       any("в следующий раз" in m for _, m in log.lines) and not os.path.exists(os.path.join(tmp, "l2.json")))

    # ---------- запись страницы ----------
    out = os.path.join(tmp, "docs")
    os.makedirs(out)
    saved = af.OUTPUT_DIR
    try:
        af.OUTPUT_DIR = out
        # Без сети и со своим кэшем: проверка не должна ни ходить в интернет,
        # ни писать afisha_places.json проекта.
        n = af.generate_afisha(known, TODAY, path, offline=True, places=os.path.join(tmp, "p.json"),
                               links=os.path.join(tmp, "links-gen.json"))
        ok("generate_afisha пишет afisha.html", n == 5 and os.path.exists(os.path.join(out, "afisha.html")), str(n))
        empty = os.path.join(tmp, "empty.json")
        with open(empty, "w", encoding="utf-8") as f:
            json.dump({"exhibitions": []}, f)
        ok("пустой список — страница убирается", af.generate_afisha(known, TODAY, empty, offline=True, places=os.path.join(tmp, "p.json"),
                                                                     links=os.path.join(tmp, "links-gen.json")) == 0
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
    # OPA AFISHA UI TESTS 2026-10-31
    ok("на главной в разделе сайта — одна ссылка «Выставки»",
       idx.find('id="sidebar"') < idx.find('href="afisha.html">Выставки</a>') < idx.find('</aside>')
       and 'id="afisha-block"' not in idx)
    ok("на главной нет повторных анонсов над картинами",
       'opa-now-collapsible' not in idx)
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
untagged = [x["title"] for x in items if not x.get("tags")]
ok("у каждой выставки — эпоха (tags) для фильтра", not untagged, ", ".join(untagged[:5]))
# Перепутанные широта и долгота — частая опечатка: точка улетает в океан.
off = [x["title"] for x in items if "lat" in x and af.region(x) == "russia"
       and not (41 <= float(x["lat"]) <= 82 and 19 <= float(x["lon"]) <= 180)]
ok("у выставок России метки — в России", not off, ", ".join(off))

ok("проверка не оставила кэш мест в проекте", not os.path.exists(os.path.join(ROOT, "afisha_places.json"))
   or open(os.path.join(ROOT, "afisha_places.json"), encoding="utf-8").read().find("Музей Последние дни") < 0)

print("\n====== АФИША ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra and not passed else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
