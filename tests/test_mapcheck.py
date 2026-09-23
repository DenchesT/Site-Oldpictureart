# -*- coding: utf-8 -*-
"""Метки на карте: находить те, что стоят не там.

Геокодер по адресу музея отдаёт что угодно в том же доме: у
Художественного музея Платтсбурга в карточке значилась кофейня «Tim
Hortons», а сам поиск брал первую находку и был этим доволен. Теперь:

  • из нескольких находок Nominatim выбирается та, что похожа на музей,
    а род объекта («tourism=museum», «amenity=fast_food») запоминается;
  • прежние записи кэша, сделанные старым поиском, один раз
    перепроверяются — иначе улучшение не дошло бы до уже найденного;
  • сборка в конце сама называет подозрительные метки, а
    python generate_map.py --check разбирает их подробно и проверяет
    ссылки «Сайт музея».

В проверках сети нет: и геокодер, и сайты подставные. Проверяется то,
что может тихо сломаться:
  • кофейню в вестибюле музея больше не берём, а порядок Nominatim при
    равном роде объекта сохраняется;
  • «Нортхемптон» и «Нортгемптон» — один город, «Хайдексбург» и
    «Rudolstadt» — разные;
  • у метки, поставленной по адресу из справочника, написание города не
    придирается;
  • приблизительные метки, двойники в одной точке и заведения не того
    рода попадают в отчёт, а «Частная коллекция» со skip — нет;
  • ссылка, уводящая на чужой домен или отвечающая ошибкой, считается
    неверной, а обычное перенаправление внутри сайта — нет.

Запуск:  python tests/test_mapcheck.py
"""

import io
import json
import logging
import os
import sys
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.argv = ["generate_map.py"]

import generate_map as gm

logging.disable(logging.CRITICAL)

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# ------------------------------------------------------------ род объекта
ok("музей узнаётся по роду", gm.kind_score("tourism=museum") > gm.kind_score("building=yes"))
ok("кофейня — не музей", gm.odd_kind("amenity=fast_food"))
ok("магазин — не музей", gm.odd_kind("shop=bakery"))
ok("галерея — музей", not gm.odd_kind("tourism=gallery"))
ok("замок — сойдёт", not gm.odd_kind("historic=castle"))
ok("пустой род не судим", not gm.odd_kind("") and not gm.odd_kind(None))
ok("неизвестный род не судим", not gm.odd_kind("boundary=administrative"))


# ------------------------------------------------------- выбор из находок
def fake_nominatim(items):
    gm._get_json = lambda url, timeout=15: items
    gm.time.sleep = lambda *_: None


fake_nominatim([
    {"lat": "44.69", "lon": "-73.46", "display_name": "Tim Hortons, 101, Broad Street",
     "class": "amenity", "type": "fast_food"},
    {"lat": "44.70", "lon": "-73.47", "display_name": "Plattsburgh State Art Museum",
     "class": "tourism", "type": "museum"},
])
found = gm.nominatim_search("101 Broad St, Plattsburgh")
ok("из находок берётся музей, а не кофейня в том же доме",
   found and "Museum" in found["display_name"], str(found))
ok("род объекта запоминается", found.get("kind") == "tourism=museum", str(found))

fake_nominatim([
    {"lat": "1", "lon": "1", "display_name": "Первый", "class": "place", "type": "house"},
    {"lat": "2", "lon": "2", "display_name": "Второй", "class": "place", "type": "house"},
])
found = gm.nominatim_search("улица Такая-то, 5")
ok("при равном роде остаётся порядок Nominatim", found["display_name"] == "Первый")

fake_nominatim([])
ok("пустой ответ — ничего не нашлось", gm.nominatim_search("нигде") is None)


# --------------------------------------------------------------- город
ok("город совпадает", gm.city_named("Монпелье", "Musée Fabre, 39, Монпелье, Франция"))
ok("разное написание — тот же город",
   gm.city_named("Нортхемптон", "Smith College Museum of Art, Нортгемптон, Массачусетс"))
ok("ё и е не различаем", gm.city_named("Онфлёр", "Musée, Онфлер, Франция"))
ok("чужой город виден", not gm.city_named("Хайдексбург", "Naturhistorisches Museum, Rudolstadt"))
ok("пустой город не придирается", gm.city_named("", "что угодно"))


# ------------------------------------------------------- разбор полётов
MUSEUMS = ["Музей А, Тверь", "Музей Б, Тверь", "Музей В, Тверь",
           "Музей Г, Тверь", "Частная коллекция", "Музей Д, Псков"]
CACHE = {
    "Музей А, Тверь": {"lat": 56.86, "lon": 35.91, "display_name": "Музей А, Тверь",
                       "source": "nominatim", "precision": "exact", "kind": "tourism=museum"},
    "Музей Б, Тверь": {"lat": 56.87, "lon": 35.92, "display_name": "Шаурма, Тверь",
                       "source": "nominatim", "precision": "exact", "kind": "amenity=fast_food"},
    "Музей В, Тверь": {"lat": 56.88, "lon": 35.93, "display_name": "Тверь",
                       "source": "nominatim", "precision": "approx"},
    "Музей Г, Тверь": {"lat": 56.86, "lon": 35.91, "display_name": "Музей Г, Тверь",
                       "source": "nominatim", "precision": "exact", "kind": "tourism=museum"},
    "Частная коллекция": None,
    "Музей Д, Псков": {"lat": 57.0, "lon": 28.66, "display_name": "Музей, Опочка, Псковская область",
                       "source": "nominatim", "precision": "exact", "kind": "tourism=museum"},
}
OVERRIDES = {"Частная коллекция": {"skip": True}}
warns = gm.map_warnings(MUSEUMS, CACHE, OVERRIDES)
text = {m: w for m, w in warns}
ok("кофейня вместо музея замечена", "не музей" in text.get("Музей Б, Тверь", ""))
ok("приблизительная метка замечена", "приблизительная" in text.get("Музей В, Тверь", ""))
ok("чужой город замечен", "нет в найденном адресе" in text.get("Музей Д, Псков", ""))
ok("двойник в одной точке замечен",
   any("ровно там же" in w for m, w in warns if m == "Музей А, Тверь"))
ok("правильная метка не ругается",
   not any(m == "Музей А, Тверь" and "ровно там же" not in w for m, w in warns))
ok("«Частная коллекция» со skip молчит", "Частная коллекция" not in text)

with_address = dict(OVERRIDES)
with_address["Музей Д, Псков"] = {"address": "улица Некрасова, 7, Псков"}
text2 = {m: w for m, w in gm.map_warnings(MUSEUMS, CACHE, with_address)}
ok("при поиске по адресу к написанию города не придираемся",
   "нет в найденном адресе" not in text2.get("Музей Д, Псков", ""))

hand = dict(OVERRIDES)
hand["Музей Д, Псков"] = {"lat": 57.8, "lon": 28.33}
text3 = {m: w for m, w in gm.map_warnings(MUSEUMS, CACHE, hand)}
ok("метка, поставленная руками, не обсуждается",
   "нет в найденном адресе" not in text3.get("Музей Д, Псков", ""))

ok("пустой кэш не роняет проверку", gm.map_warnings(MUSEUMS, {}, OVERRIDES) == [])


# ------------------------------------------------- старые записи кэша
def no_network():
    def boom(*a, **kw):
        raise AssertionError("поход в сеть там, где он не нужен")
    gm.wikidata_search = boom
    gm.nominatim_search = boom


old_wiki, old_nomi = gm.wikidata_search, gm.nominatim_search
asked = []


def fake_finder(query, *a, **kw):
    asked.append(query)
    return {"lat": 44.70, "lon": -73.47, "display_name": "Plattsburgh State Art Museum",
            "source": "nominatim", "precision": "exact", "kind": "tourism=museum"}


gm.wikidata_search = lambda q: None
gm.nominatim_search = fake_finder
gm.city_point = lambda place: None      # проверку расстояния тут не гоняем

cache = {"Музей, Платтсбург": {"lat": 44.69, "lon": -73.46, "source": "nominatim",
                               "display_name": "Tim Hortons", "precision": "exact",
                               "hint": "101 Broad St, Plattsburgh\n"}}
overrides = {"Музей, Платтсбург": {"address": "101 Broad St, Plattsburgh"}}
got = gm.geocode("Музей, Платтсбург", cache, overrides=overrides)
ok("запись без рода объекта перепроверяется", asked and got.get("kind") == "tourism=museum")
asked.clear()
got = gm.geocode("Музей, Платтсбург", cache, overrides=overrides)
ok("во второй раз в сеть уже не ходим", not asked and got.get("kind") == "tourism=museum")

wiki_cache = {"Музей, Осло": {"lat": 59.9, "lon": 10.7, "source": "wikidata:Q1",
                              "display_name": "Музей", "precision": "exact",
                              "hint": "\n"}}
asked.clear()
got = gm.geocode("Музей, Осло", wiki_cache, overrides={})
ok("записи из Викиданных не перепроверяются", not asked and got["source"].startswith("wikidata"))

gm.wikidata_search, gm.nominatim_search = old_wiki, old_nomi


# ------------------------------------------------------------- ссылки
class FakeResponse(io.BytesIO):
    def __init__(self, url):
        super().__init__(b"")
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(answer):
    def opener(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else req
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer or url)
    gm.urllib.request.urlopen = opener


real_urlopen = gm.urllib.request.urlopen

fake_urlopen(None)
ok("живая ссылка — в порядке", gm.check_site("https://www.museefabre.fr")[0])

fake_urlopen("https://www.museefabre.fr/informations-pratiques")
ok("перенаправление внутри сайта — в порядке",
   gm.check_site("https://www.museefabre.fr")[0])

fake_urlopen("https://montpellier3m.fr/actualites")
good, why = gm.check_site("https://www.museefabre.fr")
ok("уход на чужой домен — неверная ссылка", not good and "другой адрес" in why, why)

fake_urlopen(urllib.error.HTTPError("u", 404, "Not Found", {}, None))
good, why = gm.check_site("https://example.org/нет")
ok("ответ 404 — неверная ссылка", not good and "404" in why, why)

fake_urlopen(urllib.error.URLError("нет такого хоста"))
good, why = gm.check_site("https://нет-такого.example")
ok("сайт не отвечает — неверная ссылка", not good and "не открывается" in why, why)

gm.urllib.request.urlopen = real_urlopen


# --------------------------------------------------------- настоящая база
if os.path.exists("museum_overrides.json"):
    ov = {k: v for k, v in json.load(open("museum_overrides.json", encoding="utf-8")).items()
          if not k.startswith("_")}
    bad = [k for k, v in ov.items()
           if (v or {}).get("site", "").startswith("http") is False and (v or {}).get("site")]
    ok("все ссылки в справочнике — с https", not bad, str(bad))
    ok("у Музея Фабра ссылка на museefabre.fr",
       "museefabre.fr" in (ov.get("Музей Фабра, Монпелье") or {}).get("site", ""),
       str((ov.get("Музей Фабра, Монпелье") or {}).get("site")))

print("\n====== ПРОВЕРКА КАРТЫ ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
