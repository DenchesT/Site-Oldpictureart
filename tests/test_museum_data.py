# -*- coding: utf-8 -*-
"""Данные для страниц музеев, плашки выставок и разметки для поисковиков.

  • срок работы выставки разбирается из «18.03.2025 — 15.06.2025» с любым
    тире, а без срока плашки нет;
  • адрес страницы музея — латиница, режется по слову, одинаковых нет;
  • адрес для Schema.org: улица отдельно, город и страна отдельно;
  • ExhibitionEvent только у выставок со сроком, ссылка — на выставку;
  • метки слежения (ysclid, utm_…) снимаются, остальное — буква в букву;
  • подпись к срокам во времени, верном на сегодня: «Работает», пока
    выставка идёт, «Работала» — после, «Будет работать» — до открытия;
  • вид похода «музей» на сайте — «постоянная экспозиция»;
  • страница музея без координат: ссылка на карточку карты — строкой
    сведений, а не пустой колонкой.

Запуск:  python tests/test_museum_data.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.chdir(os.path.join(HERE, ".."))
os.environ.setdefault("OPA_OFFLINE_RENDER", "1")
sys.argv = ["build_site.py"]

import build_site as bs
import site_common as sc

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# ------------------------------------------------------------ срок работы
ok("срок с длинным тире", bs.run_dates("18.03.2025 — 15.06.2025") == ("2025-03-18", "2025-06-15"))
ok("срок с дефисом и однозначными числами", bs.run_dates("1.3.2025 - 5.6.2025") == ("2025-03-01", "2025-06-05"))
ok("без срока — ничего", bs.run_dates("") is None and bs.run_dates("весна 2025") is None)
ok("без срока — и места под плашку нет", bs.run_status({"run": ""}) == "")
tag = bs.run_status({"run": "18.03.2025 — 15.06.2025"}, full=True)
ok("место под плашку спрятано до скрипта и с датами",
   'data-start="2025-03-18"' in tag and 'data-end="2025-06-15"' in tag and " hidden" in tag and "data-full" in tag, tag)

# ------------------------------------------------------------ адрес страницы
ok("адрес — латиница", sc.museum_page("Национальный музей Прадо, Мадрид")
   == "museum-natsionalnyi-muzei-prado-madrid.html")
long = sc.museum_page("Государственный художественный музей Платтсбурга, Галерея Рокуэлла Кента, Платтсбург")
ok("длинное название режется по слову", long.endswith("-rokuella.html") and len(long) <= 84, long)
ok("надстрочные знаки снимаются", sc.museum_page("Musée d’Orsay, Paris") == "museum-musee-d-orsay-paris.html",
   sc.museum_page("Musée d’Orsay, Paris"))
if os.path.exists("posts_meta.json"):
    posts = json.load(open("posts_meta.json", encoding="utf-8"))
    visits = json.load(open("visits_meta.json", encoding="utf-8")) if os.path.exists("visits_meta.json") else []
    names = bs.museum_names(posts, visits)
    files = [sc.museum_page(n) for n in names]
    ok("у всех мест сайта адреса страниц разные", len(set(files)) == len(files),
       str([f for f in files if files.count(f) > 1][:3]))
    ok("частные собрания страниц не получают", not any(n.startswith("Частная коллекция") for n in names))
    bs.prepare_museums(posts, visits)
    ok("ссылка на музей со страницей — на неё", bs.museum_href(names[0]) == sc.museum_page(names[0]))
    ok("ссылка на частное собрание — на карту",
       bs.museum_href("Частная коллекция, США").startswith("museums.html#museum-"))

# ------------------------------------------------------------ адрес для поисковиков
info = {"name": "Музей", "address": "Инженерная улица, 4, Санкт-Петербург",
        "city": "Санкт-Петербург", "country": "Россия", "lat": 59.9386, "lon": 30.3322, "site": "https://rusmuseum.ru"}
addr = bs.postal_address(info)
ok("улица без города", addr["streetAddress"] == "Инженерная улица, 4", str(addr))
ok("город и страна отдельно", addr["addressLocality"] == "Санкт-Петербург" and addr["addressCountry"] == "Россия")
place = bs.place_jsonld(info)
ok("место с координатами и сайтом", place["geo"]["latitude"] == 59.9386 and place["url"] == "https://rusmuseum.ru")
ok("приблизительные координаты в разметку не идут",
   "geo" not in bs.place_jsonld(dict(info, approx=True)))
ok("без адреса и города — без PostalAddress", bs.postal_address({"name": "x"}) is None)

# ------------------------------------------------------------ выставка
visit = {"kind": "выставка", "title": "Сокровищница графики", "place": "ГМИИ им. А.С. Пушкина",
         "run": "18.03.2025 — 15.06.2025", "filename": "visit-x.html", "images": ["images/снимок-1.jpg"],
         "links": [{"text": '"Сокровищница графики"', "url": "https://expo.example/p?lang=ru&ysclid=123"}]}
ld = json.loads(bs.visit_jsonld(visit, info).split(">", 1)[1].rsplit("<", 1)[0])
ok("выставка размечена как ExhibitionEvent", ld["@type"] == "ExhibitionEvent")
ok("даты — ISO", ld["startDate"] == "2025-03-18" and ld["endDate"] == "2025-06-15")
ok("ссылка — на страницу выставки, без ysclid", ld["url"] == "https://expo.example/p?lang=ru", ld["url"])
ok("место — музей с адресом", ld["location"]["@type"] == "Museum" and "address" in ld["location"])
ok("адреса снимков закодированы", ld["image"][0].endswith("/images/%D1%81%D0%BD%D0%B8%D0%BC%D0%BE%D0%BA-1.jpg"),
   ld["image"][0])
ok("поход в музей не размечается событием", bs.visit_jsonld(dict(visit, kind="музей"), info) == "")
ok("выставка без срока не размечается", bs.visit_jsonld(dict(visit, run=""), info) == "")

# ------------------------------------------------------------ метки слежения
ok("ysclid снимается", bs.clean_url("https://a.ru/?ysclid=abc") == "https://a.ru/")
ok("utm_* снимаются, остальное на месте",
   bs.clean_url("https://a.ru/p?utm_source=tg&id=5&utm_medium=x") == "https://a.ru/p?id=5")
ok("кодировка остального адреса не трогается",
   bs.clean_url("https://a.ru/p?q=%D0%B0&ysclid=1") == "https://a.ru/p?q=%D0%B0")
ok("адрес без меток — как был", bs.clean_url("https://a.ru/?id") == "https://a.ru/?id")

# ------------------------------------------------------------ время подписи
RUN = "12.12.2025 — 21.06.2026"
ok("идёт — «Работает»", ">Работает<" in bs.run_label(RUN, today="2026-03-01"))
ok("в последний день ещё «Работает»", ">Работает<" in bs.run_label(RUN, today="2026-06-21"))
ok("закрылась — «Работала»", ">Работала<" in bs.run_label(RUN, today="2026-06-22"))
ok("не открылась — «Будет работать»", ">Будет работать<" in bs.run_label(RUN, today="2025-12-11"))
ok("даты для браузера — в разметке",
   'data-start="2025-12-12" data-end="2026-06-21"' in bs.run_label(RUN, today="2026-03-01"))
ok("срок без дат — нейтрально «Сроки»", bs.run_label("весна 2025") == "<span>Сроки</span>")
card = bs.visit_card({"kind": "выставка", "title": "Т", "place": "М", "filename": "visit-x.html",
                      "run": RUN, "visited": "01.03.2026", "images": []})
ok("в карточке похода подпись к срокам — из run_label", 'class="run-word"' in card)
ok("скрипт переписывает подпись на сегодня", ".run-word[data-end]" in bs.RUN_STATUS_JS)

# ------------------------------------------------------------ вид похода
ok("«музей» на сайте — «постоянная экспозиция»", sc.visit_kind_label("музей") == "постоянная экспозиция")
ok("…во множественном — «постоянные экспозиции»", sc.visit_kind_label("музей", many=True) == "постоянные экспозиции")
ok("«выставка» — как есть", sc.visit_kind_label("выставка") == "выставка")
mcard = bs.visit_card({"kind": "музей", "title": "", "place": "М", "filename": "visit-y.html", "images": []})
ok("в карточке — «постоянная экспозиция», фильтр по-прежнему по «музей»",
   ">постоянная экспозиция<" in mcard and 'data-kind="музей"' in mcard)

# ------------------------------------------------------------ страница без координат
page = bs.render_museum_page("Музей Икс, Город", [], [], {"name": "Музей Икс, Город", "city": "Город"},
                             [], {}, 3)
ok("без координат — ссылка на карточку строкой сведений", "Карточка на карте собраний" in page
   and 'museum-hero no-map' in page and 'id="mini-map"' not in page)
ok("без координат — Leaflet не грузится", "leaflet" not in page.lower())

# ------------------------------------------------------------ напоминание в конце сборки
import generate_map as gm
saved = (gm.load_cache, gm.load_overrides)
gm.load_cache = lambda: {"Музей Икс, Город": {"lat": 1.0, "lon": 2.0, "display_name": "Город",
                                              "source": "wikidata:Q1", "precision": "approx"}}
gm.load_overrides = lambda quiet=False: {}
try:
    doubts = bs.map_reminder([{"museum": "Музей Икс, Город"}], [])
finally:
    gm.load_cache, gm.load_overrides = saved
ok("метка по городу попадает в напоминание в конце сборки",
   len(doubts) == 1 and "по городу" in doubts[0][1], str(doubts))

# ------------------------------------------------------------ несколько музеев у выставки
# «МРИ, Ростовский кремль, Конюшенный двор» — выставка МРИ, которая идёт в
# Ростове: на карте и в походах она должна стоять в Ростове, а не в Москве.
ok("запятая в кавычках не делит место",
   sc.split_place('Музей А, «Музей Б, филиал», Зал 3') == ["Музей А", "«Музей Б, филиал»", "Зал 3"])
pp = sc.place_parts('Музей русского импрессионизма, Государственный  музей-заповедник "Ростовский Кремль", Конюшенный двор')
ok("место проведения — последний музей в строке, дальше его зал",
   pp["venue"] == 'Государственный музей-заповедник "Ростовский Кремль"' and pp["section"] == "Конюшенный двор"
   and pp["organizers"] == ["Музей русского импрессионизма", 'Государственный музей-заповедник "Ростовский Кремль"'], str(pp))
ok("«Музей, Новгородский музей заповедник» — выставка в Новгороде",
   sc.place_parts("Музей русского импрессионизма, Новгородский музей заповедник")["venue"] == "Новгородский музей заповедник")
for place, venue in [("Государственный Эрмитаж, Главный штаб", "Государственный Эрмитаж"),
                     ("Эрмитаж, Главный музейный комплекс", "Эрмитаж"),
                     ("Нижегородский государственный художественный музей, Зарубежное искусство",
                      "Нижегородский государственный художественный музей"),
                     ("ГМИИ им. А.С. Пушкина, Галерея искусства стран Европы и Америки", "ГМИИ им. А.С. Пушкина")]:
    got = sc.place_parts(place)
    ok(f"«{place[:40]}…» — один музей и его раздел", got["venue"] == venue and len(got["organizers"]) == 1, str(got))
ok("известное место узнаётся и без слова «музей»",
   sc.place_parts("Музей Икс, Эрмитаж Тест", known=["Эрмитаж Тест, Город"])["venue"] == "Эрмитаж Тест")

vp = sc.visit_places([{"place": "Музей Альфа, Музей Бета, Зал 1"}, {"place": "Музей Альфа"}], ["Музей Альфа, Город"])
ok("поход на выставку двух музеев — в карточке места проведения",
   vp.get("Музей Альфа, Музей Бета, Зал 1") == "Музей Бета" and vp.get("Музей Альфа") == "Музей Альфа, Город", str(vp))
orgs = sc.visit_organizers("Музей Альфа, Музей Бета, Зал 1", ["Музей Альфа, Город"], vp)
ok("организаторы — оба музея, известные — со своей карточкой",
   orgs == [("Музей Альфа", "Музей Альфа, Город"), ("Музей Бета", "Музей Бета")], str(orgs))
ok("у похода в один музей организаторов не пишем", sc.visit_organizers("Музей Альфа, Зал 2", ["Музей Альфа, Город"]) == [])

ld = json.loads(bs.visit_jsonld(dict(visit, kind="выставка"), info,
                                [{"name": "Музей Альфа", "site": "https://a.example"}, {"name": "Музей Бета"}])
                .split(">", 1)[1].rsplit("<", 1)[0])
ok("в разметке события — все организаторы",
   isinstance(ld.get("organizer"), list) and [o["name"] for o in ld["organizer"]] == ["Музей Альфа", "Музей Бета"],
   str(ld.get("organizer")))

trip = {"kind": "выставка", "title": "Выставка Т", "place": "Музей Альфа, Музей Бета, Зал 1",
        "filename": "visit-t.html", "run": "01.06.2026 — 01.09.2026", "visited": "10.07.2026", "images": []}
page = bs.render_visit_page(trip, [trip], [{"museum": "Музей Альфа, Город"}],
                            {"Музей Альфа, Музей Бета, Зал 1": "Музей Бета"})
ok("на странице похода «Место» — где идёт выставка",
   "<span>Место</span><b>" in page and ">Музей Бета, Зал 1</a>" in page, page[page.find("<span>Место"):][:160])
ok("и строка «Организаторы» с обоими музеями",
   "<span>Организаторы</span>" in page and "Музей Альфа" in page[page.find("Организаторы"):][:300])

mpage = bs.render_museum_page("Музей Альфа, Город", [], [], {"name": "Музей Альфа, Город", "city": "Город"},
                              [], {}, 3, away=[(trip, "Музей Бета, Другой", "Другой")])
ok("на странице музея-участника — «Выставки в других городах», под названием — где шла",
   "Выставки в других городах" in mpage and ">Музей Бета, Другой<" in mpage)
mpage = bs.render_museum_page("Музей Альфа, Город", [], [], {"name": "Музей Альфа, Город", "city": "Город"},
                              [], {}, 3, away=[(trip, "Музей Гамма, Город", "Город")])
ok("если выставка шла в том же городе — «Выставки в других музеях»", "Выставки в других музеях" in mpage)

# Настоящие данные: «Митрополичье варенье» и «Сказка рядом» стоят там, где шли.
real_visits = json.load(open("visits_meta.json", encoding="utf-8")) if os.path.exists("visits_meta.json") else []
real_posts = json.load(open("posts_meta.json", encoding="utf-8")) if os.path.exists("posts_meta.json") else []
real_map = bs.visit_map_names(real_visits, real_posts)
# All public museum pages must have an official museum URL and a usable address.
# Private collections are intentionally absent from museum_names().
public_museums = bs.museum_names(real_posts, real_visits)
missing_details = [n for n in public_museums
                   if not (bs.museum_info(n).get("site") and bs.museum_info(n).get("address"))]
ok("у всех музеев на карте есть адрес и официальный сайт",
   not missing_details, ", ".join(missing_details))
for title, city in [("Митрополичье варенье", "Ростов Великий"), ("Сказка рядом", "Великий Новгород")]:
    v = next((x for x in real_visits if x.get("title") == title), None)
    if v:
        card = real_map.get(v["place"].strip(), "")
        ok(f"«{title}» на карте — в городе «{city}»", bs.museum_info(card)["city"] == city, card)
        ok(f"…а МРИ — среди организаторов «{title}»",
           any(c == "Музей русского импрессионизма"
               for _, c in sc.visit_organizers(v["place"], bs.visit_museum_names(real_posts), real_map)))
ok("Хайдексбург — замок, город — Рудольштадт",
   bs.museum_info("Государственный музей Тюрингии, Хайдексбург")["city"] == "Рудольштадт")

print("\n====== ДАННЫЕ МУЗЕЕВ И ВЫСТАВОК ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
