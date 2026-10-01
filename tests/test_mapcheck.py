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
ok("дефибриллятор у входа — не музей (так нашёлся MuMa в Гавре)", gm.odd_kind("emergency=defibrillator"))


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
town = gm.map_warnings(
    ["Ассоциация, Довиль"],
    {"Ассоциация, Довиль": {"lat": 49.36, "lon": 0.07, "display_name": "Довиль, Лизьё, Кальвадос",
                            "source": "nominatim", "precision": "exact", "kind": "boundary=administrative"}},
    {})
ok("нашёлся только город — так и сказано, а не «это не музей»",
   town and "только город" in town[0][1], str(town))
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


# ------------------------------------------- адрес, сайт и страна сами
# У нового музея в справочнике пусто, и страница выходила с одной строкой
# «Где: Оттерло». Теперь сборка сама спрашивает Викиданные (сайт, адрес)
# и OpenStreetMap (что стоит в точке) и запоминает ответ в кэше.
ok("адрес: «улица дом, город»",
   gm.osm_address({"road": "Houtkampweg", "house_number": "6", "village": "Оттерло", "country_code": "nl"})
   == "Houtkampweg 6, Оттерло")
ok("адрес во Франции: дом перед улицей",
   gm.osm_address({"road": "Boulevard Bonne Nouvelle", "house_number": "39", "city": "Монпелье", "country_code": "fr"})
   == "39 Boulevard Bonne Nouvelle, Монпелье")
ok("адрес в России: дом через запятую",
   gm.osm_address({"road": "улица Волхонка", "house_number": "12", "city": "Москва", "country_code": "ru"})
   == "улица Волхонка, 12, Москва")
ok("без улицы адреса нет — один город не адрес", gm.osm_address({"city": "Гаага", "country_code": "nl"}) == "")
ok("сайт — только настоящий адрес", gm.clean_site("https://krollermuller.nl") == "https://krollermuller.nl"
   and gm.clean_site("krollermuller.nl") == "" and gm.clean_site("javascript:alert(1)") == "")

calls = []
REVERSE = {"category": "tourism", "type": "museum",
           "address": {"road": "Houtkampweg", "house_number": "6", "village": "Оттерло",
                       "country": "Нидерланды", "country_code": "nl"},
           "extratags": {"website": "https://osm.example/museum"}}
ENTITY = {"entities": {"Q1051928": {"claims": {
    "P856": [{"rank": "deprecated", "mainsnak": {"datavalue": {"value": "http://old.example"}}},
             {"rank": "normal", "mainsnak": {"datavalue": {"value": "https://krollermuller.nl"}}}],
    "P6375": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"text": "Houtkampweg 6, Otterlo", "language": "nl"}}}}],
}}}}


def fake_net(reverse=REVERSE, entity=ENTITY, fail=False):
    def get(url, timeout=15):
        calls.append(url)
        if fail:
            raise OSError("нет сети")
        return entity if "wikidata.org" in url else reverse
    gm._get_json = get
    gm.time.sleep = lambda *_: None


real_get = gm._get_json
fake_net()
rev = gm.nominatim_reverse(52.0958, 5.8169)
ok("в точке музей — берём адрес, сайт и страну",
   rev == {"country": "Нидерланды", "address": "Houtkampweg 6, Оттерло", "site": "https://osm.example/museum"}, str(rev))
fake_net(reverse=dict(REVERSE, category="amenity", type="cafe"))
rev = gm.nominatim_reverse(52.0958, 5.8169)
ok("в точке кафе — чужие адрес и сайт не берём, только страну", rev == {"country": "Нидерланды"}, str(rev))
fake_net(reverse=dict(REVERSE, category="building", type="yes"))
rev = gm.nominatim_reverse(52.0958, 5.8169)
ok("в точке просто дом — адрес берём, сайт нет", "address" in rev and "site" not in rev, str(rev))

fake_net()
wd = gm.wikidata_details("Q1051928")
ok("Викиданные: сайт и адрес, отменённое значение пропущено",
   wd == {"site": "https://krollermuller.nl", "address": "Houtkampweg 6, Otterlo"}, str(wd))

# Новый музей, найденный в Викиданных: в справочнике о нём ничего.
loc = {"lat": 52.0958, "lon": 5.8169, "display_name": "Музей Крёллер-Мюллер",
       "source": "wikidata:Q1051928", "precision": "exact"}
del calls[:]
went = gm.enrich("Музей Крёллер-Мюллер, Оттерло", loc, {})
det = loc.get("details") or {}
ok("новый музей: адрес и сайт из Викиданных, страна из карты",
   went and det.get("address") == "Houtkampweg 6, Otterlo" and det.get("site") == "https://krollermuller.nl"
   and det.get("country") == "Нидерланды", str(det))
ok("подпись места теперь со страной",
   gm.museum_place("Музей Крёллер-Мюллер, Оттерло", {}, loc) == ("Оттерло", "Нидерланды"),
   str(gm.museum_place("Музей Крёллер-Мюллер, Оттерло", {}, loc)))
ok("адрес и сайт идут на страницу и в карточку",
   gm.place_address({}, loc) == "Houtkampweg 6, Otterlo" and gm.place_site({}, loc) == "https://krollermuller.nl")
ok("справочник главнее найденного",
   gm.place_address({"address": "Свой адрес"}, loc) == "Свой адрес"
   and gm.place_site({"site": "https://свой.example"}, loc) == "https://свой.example"
   and gm.museum_place("Музей Икс, Город", {"country": "Своя"}, loc)[1] == "Своя")
del calls[:]
ok("второй раз для той же точки в сеть не ходим",
   gm.enrich("Музей Крёллер-Мюллер, Оттерло", loc, {}) is False and not calls, str(calls))
moved = dict(loc, lat=52.2)
ok("метку передвинули — спрашиваем заново", gm.enrich("Музей Крёллер-Мюллер, Оттерло", moved, {}) and calls)

del calls[:]
full = {"address": "а", "site": "https://b.example", "country": "в"}
ok("в справочнике всё есть — сеть не нужна",
   gm.enrich("Музей", {"lat": 1.0, "lon": 2.0, "source": "override"}, full) is False and not calls)
ok("метка по городу — адрес не ищем",
   gm.enrich("Музей", {"lat": 1.0, "lon": 2.0, "source": "wikidata:Q1", "precision": "approx"}, {}) is False and not calls)
ok("без сети (--no-geocode) — не ищем",
   gm.enrich("Музей", {"lat": 1.0, "lon": 2.0, "source": "nominatim"}, {}, offline=True) is False and not calls)

fake_net(fail=True)
broken = {"lat": 1.0, "lon": 2.0, "source": "wikidata:Q1", "display_name": "Музей"}
gm.enrich("Музей, Город", broken, {})
ok("сеть подвела — ничего не запомнили, спросим в следующий раз", "details" not in broken, str(broken))

fake_net(reverse={"error": "Unable to geocode"}, entity={"entities": {}})
empty = {"lat": 1.0, "lon": 2.0, "source": "wikidata:Q1", "display_name": "Музей"}
gm.enrich("Музей, Город", empty, {})
del calls[:]
ok("ничего не нашлось — запомнили, повторно не спрашиваем",
   empty.get("details") == {"lat": 1.0, "lon": 2.0} and gm.enrich("Музей, Город", empty, {}) is False and not calls,
   str(empty.get("details")))

# Музей найден не в Викиданных (по адресу из справочника): в точке на карте
# стоит просто дом без сайта. Сайт берём из Викиданных по названию — но
# только у записи, которая стоит в той же точке, что и метка.
def wd_net(lat, lon, site="https://www.hermitagemuseum.org"):
    def get(url, timeout=15):
        calls.append(url)
        if "nominatim" in url:
            return {"category": "building", "type": "yes",
                    "address": {"road": "Дворцовая набережная", "house_number": "34",
                                "city": "Санкт-Петербург", "country": "Россия", "country_code": "ru"}}
        if "wbsearchentities" in url:
            return {"search": [{"id": "Q132783", "label": "Эрмитаж", "description": "музей в Санкт-Петербурге"}]}
        return {"entities": {"Q132783": {"labels": {"ru": {"value": "Эрмитаж"}}, "claims": {
            "P625": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"latitude": lat, "longitude": lon}}}}],
            "P856": [{"rank": "normal", "mainsnak": {"datavalue": {"value": site}}}]}}}}
    gm._get_json = get
    gm.time.sleep = lambda *_: None


class Catch(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append((record.levelno, record.getMessage()))


catch = Catch()
catch.setLevel(logging.INFO)
gm.logger.addHandler(catch)
old_level, old_propagate = gm.logger.level, gm.logger.propagate
gm.logger.setLevel(logging.INFO)
gm.logger.propagate = False        # в вывод проверки лог не нужен
logging.disable(logging.NOTSET)

wd_net(59.9404, 30.3138)
herm = {"lat": 59.9414, "lon": 30.3161, "source": "nominatim", "kind": "tourism=artwork",
        "display_name": "34, Дворцовая набережная, Санкт-Петербург, Россия"}
gm.enrich("Государственный Эрмитаж", herm, {"address": "Дворцовая набережная, 34, Санкт-Петербург"})
ok("сайт музея, найденного по адресу, берётся из Викиданных по названию",
   (herm.get("details") or {}).get("site") == "https://www.hermitagemuseum.org", str(herm.get("details")))

wd_net(55.75, 37.61)            # одноимённая запись в другом городе
del catch.records[:]
other = {"lat": 59.9414, "lon": 30.3161, "source": "nominatim",
         "display_name": "34, Дворцовая набережная, Санкт-Петербург, Россия"}
gm.enrich("Государственный Эрмитаж", other, {"address": "Дворцовая набережная, 34, Санкт-Петербург"})
ok("запись Викиданных в другом городе не подходит — чужой сайт не берём",
   "site" not in (other.get("details") or {}), str(other.get("details")))
notes = [(lvl, msg) for lvl, msg in catch.records if "не нашёлся" in msg]
ok("не нашёлся только сайт — одна строка в логе, не предупреждение, и просит только сайт",
   len(notes) == 1 and notes[0][0] == logging.INFO and '"site"' in notes[0][1] and '"address"' not in notes[0][1],
   str(notes))

fake_net(reverse={"error": "Unable to geocode"}, entity={"entities": {}})
del catch.records[:]
gm.enrich("Музей, Город", {"lat": 1.0, "lon": 2.0, "source": "wikidata:Q1", "display_name": "Музей"}, {})
notes = [(lvl, msg) for lvl, msg in catch.records if "не нашёлся" in msg]
ok("не нашёлся адрес — это уже предупреждение",
   len(notes) == 1 and notes[0][0] == logging.WARNING and '"address"' in notes[0][1], str(notes))
gm.logger.removeHandler(catch)
gm.logger.setLevel(old_level)
gm.logger.propagate = old_propagate
logging.disable(logging.CRITICAL)

# Музей с координатами из справочника: запись кэша переписывается при
# каждой сборке — найденные раньше сведения не должны теряться.
cache = {"Музей Икс, Город": {"lat": 1.0, "lon": 2.0, "source": "override",
                              "details": {"lat": 1.0, "lon": 2.0, "country": "Страна"}}}
got = gm.geocode("Музей Икс, Город", cache, overrides={"Музей Икс, Город": {"lat": 1.0, "lon": 2.0}})
ok("у музея из справочника найденные сведения переживают сборку",
   (got.get("details") or {}).get("country") == "Страна", str(got))
gm._get_json = real_get


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

    # Коллекция Месдага стояла в центре Гааги: по русскому названию
    # автопоиск не нашёл ничего и поставил метку по городу.
    md = ov.get("Коллекция Месдага, Гаага") or {}
    ok("Коллекция Месдага — на Laan van Meerdervoort 7F, а не в центре Гааги",
       "lat" in md and gm.distance_km(md, {"lat": 52.0860, "lon": 4.2955}) < 0.3, str(md))

    # Вся настоящая карта: ни одной метки по городу, на улице, на кофейне
    # или двойника. Новый музей встал не туда — проверка скажет какой.
    if os.path.exists("museum_coordinates.json") and os.path.exists("posts_meta.json"):
        real_names = {p["museum"].strip() for p in json.load(open("posts_meta.json", encoding="utf-8"))
                      if p.get("museum")}
        doubts = gm.map_warnings(real_names, gm.load_cache(), gm.load_overrides(quiet=True))
        ok("на настоящей карте все метки на своих зданиях", not doubts,
           "; ".join(f"{m}: {w}" for m, w in doubts[:5]))

    no_site = [k for k, v in ov.items()
               if isinstance(v, dict) and not v.get("skip") and not v.get("same_as") and not v.get("site")]
    ok("у каждого музея в справочнике есть сайт", not no_site, ", ".join(no_site))

    km = ov.get("Музей Крёллер-Мюллер, Оттерло") or {}
    ok("у Музея Крёллер-Мюллер есть адрес, сайт и страна",
       km.get("address") and km.get("site") and km.get("country"), str(km))

print("\n====== ПРОВЕРКА КАРТЫ ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
