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
import socket
import ssl
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
ok("улица — не музей", gm.odd_kind("highway=residential"))
ok("дом по адресу — сойдёт", not gm.odd_kind("place=house"))
ok("галерея — музей", not gm.odd_kind("tourism=gallery"))
ok("замок — сойдёт", not gm.odd_kind("historic=castle"))
ok("пустой род не судим", not gm.odd_kind("") and not gm.odd_kind(None))
ok("незнакомый род не судим", not gm.odd_kind("leisure=park"))
ok("граница района — не здание", gm.odd_kind("boundary=administrative"))


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
street = gm.map_warnings(
    ["Музей У, Лондон"],
    {"Музей У, Лондон": {"lat": 51.4965, "lon": -0.1255, "display_name": "Millbank, Вестминстер",
                         "source": "nominatim", "precision": "exact", "kind": "highway=residential"}},
    {})
ok("улица вместо здания замечена и названа по-человечески",
   street and "улица" in street[0][1], str(street))
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
#
# Проверка ссылок делит ответы на три кучи, и это главное в ней. Сайты
# музеев сплошь за Cloudflare: на робота они отвечают 403 и 429, а в
# браузере открываются. Если считать такое поломкой, в отчёте будет
# тринадцать «битых» ссылок, из которых не работает одна, и читать его
# перестанут.
class FakeResponse(io.BytesIO):
    def __init__(self, url):
        super().__init__(b"<html></html>")
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def answer(what, insecure_ok=False):
    """Подставляет ответ сети: адрес, исключение или пару «сначала-потом»."""
    tries = []

    def opener(url, timeout, insecure=False):
        tries.append(insecure)
        if insecure and insecure_ok:
            return url
        if isinstance(what, Exception):
            raise what
        return what or url

    gm.open_site = opener
    return tries


real_open_site = gm.open_site

answer(None)
ok("живая ссылка — в порядке", gm.check_site("https://www.museefabre.fr") == ("ok", ""))

answer("https://www.museefabre.fr/informations-pratiques")
ok("перенаправление внутри сайта — в порядке",
   gm.check_site("https://www.museefabre.fr")[0] == "ok")

answer("https://www.museefabre.fr/ru")
ok("www и без www — один и тот же сайт",
   gm.check_site("https://museefabre.fr")[0] == "ok")

answer("https://montpellier3m.fr/actualites")
state, why = gm.check_site("https://www.museefabre.fr")
ok("уход на чужой домен — ссылку надо поправить",
   state == "bad" and "другой адрес" in why, why)

answer(urllib.error.HTTPError("u", 404, "Not Found", {}, None))
state, why = gm.check_site("https://example.org/нет")
ok("404 — ссылку надо поправить", state == "bad" and "404" in why, why)

for code in (403, 429, 503):
    answer(urllib.error.HTTPError("u", code, "no robots", {}, None))
    state, why = gm.check_site("https://www.nga.gov")
    ok(f"ответ {code} — не поломка, а «не пускают проверку»",
       state == "unknown" and str(code) in why, why)

answer(urllib.error.URLError(socket.gaierror("не нашёлся")))
state, why = gm.check_site("https://нет-такого.example")
ok("несуществующий домен — ссылку надо поправить",
   state == "bad" and "домена нет" in why, why)

answer(urllib.error.URLError(socket.timeout()))
ok("не ответил вовремя — не поломка",
   gm.check_site("https://www.museunacional.cat")[0] == "unknown")


def cert_error(message):
    e = ssl.SSLCertVerificationError(message)
    e.verify_message = message
    return e


tries = answer(cert_error("self-signed certificate in certificate chain"), insecure_ok=True)
state, why = gm.check_site("https://pushkinmuseum.art")
ok("свой корень сертификата (Минцифры) — не поломка, сайт живой",
   state == "unknown" and "браузере" in why, why)
ok("ради этого сайт переспрашивается без проверки сертификата", tries == [False, True],
   str(tries))

answer(cert_error("unable to get local issuer certificate"), insecure_ok=False)
state, why = gm.check_site("https://мёртвый.example")
ok("сертификат не проверился и сайт молчит — это поломка", state == "bad", why)

answer(cert_error("Hostname mismatch, certificate is not valid for 'x.dk'"))
state, why = gm.check_site("https://skagenskunstmuseer.dk")
ok("сертификат на чужое имя — ссылку надо поправить",
   state == "bad" and "другое имя" in why, why)

ok("проверка ходит браузерными заголовками",
   "Mozilla" in gm.BROWSER_HEADERS.get("User-Agent", ""))

gm.open_site = real_open_site


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
