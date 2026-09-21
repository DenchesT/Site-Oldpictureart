# -*- coding: utf-8 -*-
"""Школа нового художника определяется сама — по Wikidata.

Раньше каждого нового художника нужно было вручную вписать в список
SCHOOLS в generate_quiz.py, иначе варианты к нему в квизе подбирались
только по годам. Теперь сборка сама находит его в Wikidata, берёт
гражданство и переводит в школу, а ответ запоминает в artist_schools.json.

В проверках сети нет: ответы Wikidata подставлены. Проверяется то, что
может тихо сломаться:
  • полное имя из канала («Жан Батист Камиль Коро») Wikidata не знает —
    ищется короткое, а потом фамилия среди живописцев;
  • тёзку из другого века и не-человека (город, улицу) не берём;
  • исторические страны («Германская империя», «Великое княжество
    Финляндское») переводятся в школы правильно;
  • ответ запоминается и в сеть за тем же художником больше не ходим;
  • «не нашёлся» переспрашивается раз в месяц, а не на каждой сборке;
  • сбой сети не запоминается как «не нашёлся»;
  • поправка, вписанная в artist_schools.json руками, главнее всего.
Заодно — год создания по дате в конце названия.

Запуск:  python tests/test_artist_schools.py
"""

import datetime
import json
import os
import sys
import tempfile
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.argv = ["generate_quiz.py"]

import generate_quiz as gq
from site_common import work_year, split_title_date

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# ------------------------------------------------------------ поддельная Wikidata
def item(qid):
    return {"mainsnak": {"datavalue": {"value": {"id": qid}}}, "rank": "normal"}


def when(year):
    return [{"mainsnak": {"datavalue": {"value": {"time": f"+{year}-01-01T00:00:00Z"}}}}]


def person(qid, ru, born, countries, painter=True, aliases=(), died=None):
    claims = {"P31": [item("Q5")], "P569": when(born),
              "P106": [item("Q1028181" if painter else "Q82955")],
              "P27": [item(c) for c in countries]}
    if died:
        claims["P570"] = when(died)
    return {"id": qid, "labels": {"ru": {"value": ru}},
            "aliases": {"ru": [{"value": a} for a in aliases]}, "claims": claims}


ENTITIES = {
    "Q1": person("Q1", "Ханс Тома", 1839, ["C_GERMAN_EMPIRE"]),
    "Q2": {"id": "Q2", "labels": {"ru": {"value": "Тома"}}, "claims": {"P31": [item("Q515")]}},   # город
    "Q3": person("Q3", "Камиль Коро", 1796, ["C_FRANCE"]),
    "Q4": person("Q4", "Джон Смит", 1700, ["C_UK"]),              # тёзка на полтора века старше
    "Q5": person("Q5", "Джон Смит", 1840, ["C_UK"]),
    "Q6": person("Q6", "Хелена Шерфбек", 1862, ["C_FINLAND_GD", "C_FINLAND"],
                 aliases=["Хелене Шьерфбек"]),
    "Q7": person("Q7", "Юзеф Хелмоньский", 1849, ["C_POLAND"]),
}
COUNTRIES = {
    "C_GERMAN_EMPIRE": ("German Empire", "Германская империя"),
    "C_FRANCE": ("France", "Франция"),
    "C_UK": ("United Kingdom of Great Britain and Ireland", "Соединённое Королевство"),
    "C_FINLAND_GD": ("Grand Duchy of Finland", "Великое княжество Финляндское"),
    "C_FINLAND": ("Finland", "Финляндия"),
    "C_POLAND": ("Poland", "Польша"),
}
SEARCH = {                   # wbsearchentities: запрос → найденные номера
    "Ханс Тома": ["Q2", "Q1"],
    "Камиль Коро": ["Q3"],
    "Джон Смит": ["Q4", "Q5"],
    "Юзеф Хелмоньский": ["Q7"],
}
PAINTERS = {"Шьерфбек": ["Q6"]}   # поиск фамилии среди живописцев

calls = []
fail_network = False


def fake_wd(params):
    calls.append(params)
    if fail_network:
        raise urllib.error.URLError("нет сети")
    if params["action"] == "wbsearchentities":
        return {"search": [{"id": q} for q in SEARCH.get(params["search"], [])]}
    if params["action"] == "query":
        name = params["srsearch"].split(" haswbstatement")[0]
        return {"query": {"search": [{"title": q} for q in PAINTERS.get(name, [])]}}
    ents = {}
    for q in params["ids"].split("|"):
        if q in ENTITIES:
            ents[q] = ENTITIES[q]
        elif q in COUNTRIES:
            en, ru = COUNTRIES[q]
            ents[q] = {"labels": {"en": {"value": en}, "ru": {"value": ru}}}
    return {"entities": ents}


gq._wd = fake_wd
tmp = tempfile.mkdtemp()
gq.SCHOOLS_CACHE = os.path.join(tmp, "artist_schools.json")
log = []
TODAY = datetime.date(2026, 9, 21)


def resolve(artists, **kw):
    calls.clear()
    log.clear()
    kw.setdefault("today", TODAY)
    return gq.resolve_schools(artists, log=log.append, **kw)


def cache():
    with open(gq.SCHOOLS_CACHE, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------ без сети
r = resolve({"Альфред Сислей": 1875, "Иван Петрович Новиков": 1880})
ok("разобранный вручную — из списка, без сети", r["Альфред Сислей"] == "fr" and not calls)
ok("русский по отчеству — без сети", r["Иван Петрович Новиков"] == "ru" and not calls)

r = resolve({"Ханс Тома": 1880}, offline=True)
ok("с --offline в сеть не ходим", not calls and r["Ханс Тома"] is None)
ok("и не запоминаем «не нашёлся»", not os.path.exists(gq.SCHOOLS_CACHE))

# ------------------------------------------------------------ находки
r = resolve({"Ханс Тома": 1880})
ok("новый художник найден: Германская империя → de", r["Ханс Тома"] == "de", str(r))
ok("город с тем же именем не взят", cache()["Ханс Тома"]["wikidata"] == "Q1")
ok("в журнале видно, что и откуда", any("Германская империя" in x and "Q1" in x for x in log), " | ".join(log))
ok("ответ записан в artist_schools.json с датой",
   cache()["Ханс Тома"].get("checked") == "2026-09-21" and cache()["Ханс Тома"]["school"] == "de")

r = resolve({"Ханс Тома": 1880})
ok("второй раз — из файла, без сети", r["Ханс Тома"] == "de" and not calls)

r = resolve({"Жан Батист Камиль Коро": 1850})
ok("полное имя не знают — нашёлся по короткому", r["Жан Батист Камиль Коро"] == "fr",
   " → ".join(c.get("search", c.get("srsearch", c.get("ids", ""))) for c in calls))

r = resolve({"Джон Смит": 1885})
ok("из двух тёзок взят тот, что жил в годы картин", cache()["Джон Смит"]["wikidata"] == "Q5"
   and r["Джон Смит"] == "gb", cache()["Джон Смит"]["wikidata"])

r = resolve({"Хелене Шьерфбек": 1890})
ok("не нашёлся по имени — нашёлся по фамилии среди живописцев",
   r["Хелене Шьерфбек"] == "north" and any(c["action"] == "query" for c in calls))
ok("Великое княжество Финляндское — Скандинавия и Финляндия, а не Россия",
   r["Хелене Шьерфбек"] == "north")

r = resolve({"Юзеф Хелмоньский": 1880})
ok("страна вне школ — школы нет, но страна записана",
   r["Юзеф Хелмоньский"] is None and cache()["Юзеф Хелмоньский"]["country"] == "Польша")
ok("и сборка говорит, где поправить", any("Польша" in x and "artist_schools.json" in x for x in log),
   " | ".join(log))

# ------------------------------------------------------------ не нашёлся
r = resolve({"Никто Неизвестный": 1880})
ok("не нашёлся — запомнено с датой", cache()["Никто Неизвестный"]["school"] is None
   and cache()["Никто Неизвестный"]["checked"] == "2026-09-21")
r = resolve({"Никто Неизвестный": 1880}, today=TODAY + datetime.timedelta(days=10))
ok("через 10 дней не переспрашиваем", not calls)
r = resolve({"Никто Неизвестный": 1880}, today=TODAY + datetime.timedelta(days=31))
ok("через месяц переспрашиваем", bool(calls))

# ------------------------------------------------------------ сбой сети
fail_network = True
r = resolve({"Ещё Один": 1880, "И Другой": 1890})
fail_network = False
ok("сбой сети не записан как «не нашёлся»", "Ещё Один" not in cache() and "И Другой" not in cache())
ok("после первого сбоя сеть больше не дёргаем", len(calls) == 1, str(len(calls)))
ok("о сбое сказано в журнале", any("недоступна" in x for x in log), " | ".join(log))

# ------------------------------------------------------------ ручная поправка
data = cache()
data["Ханс Тома"] = {"school": "north"}
with open(gq.SCHOOLS_CACHE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)
r = resolve({"Ханс Тома": 1880})
ok("поправка в artist_schools.json главнее Wikidata", r["Ханс Тома"] == "north" and not calls)

# ------------------------------------------------------------ страны → школы
COUNTRY_CASES = {
    "Russian Empire": "ru", "Soviet Union": "ru", "Kingdom of Prussia": "de",
    "Austria-Hungary": "de", "Switzerland": "de", "Grand Duchy of Finland": "north",
    "Sweden": "north", "United Kingdom of the Netherlands": "nl", "Spanish Netherlands": "nl",
    "Belgium": "nl", "Second French Empire": "fr", "Kingdom of Great Britain": "gb",
    "Kingdom of the Two Sicilies": "it", "Kingdom of Spain": "es", "United States": "us",
    "Poland": None, "Japan": None,
}
wrong = {k: gq.school_from_country(k) for k, v in COUNTRY_CASES.items() if gq.school_from_country(k) != v}
ok("исторические страны переводятся в школы верно", not wrong, str(wrong))

# ------------------------------------------------------------ год создания
YEARS = {
    "Les Fiancés (Пара), около 1868": 1868,
    "Парад на Красной площади 7 ноября 1941 года, 1949": 1949,
    "Inauguration de l'Opéra de Paris, 5 janvier 1875 (Открытие Парижской оперы, 5 января 1875 года), 1878": 1878,
    "Cranberrying, Monhegan (Сбор клюквы, Монхиган),1907": 1907,
    "Горная речка, между 1887 и 1890 годами": 1887,
    "Норвежский фьорд с козами, 1910-е": 1910,
    "У мирового суда, XIX век": None,
    "Florian's café, Venice (Кафе Флориан, Венеция), 1910": 1910,
}
wrong = {t[:40]: work_year(t) for t, y in YEARS.items() if work_year(t) != y}
ok("год — из даты в конце названия, а не из самого названия", not wrong, str(wrong))
ok("название без даты — для вопроса «когда»",
   split_title_date("Les Fiancés (Пара), около 1868") == ("Les Fiancés (Пара)", "около 1868"))
DECADES = {
    "Les Fiancés (Пара), около 1868": 1860,
    "Au théâtre (В театре), 1885-1895": None,              # два десятилетия
    "Woodland Path (Лесная тропа), около 1618-20": None,
    "Ansicht (Вид), 1805–06": 1800,
    "Парад на Красной площади 7 ноября 1941 года, 1949": None,   # год в названии
    "У мирового суда, XIX век": None,
}
wrong = {t[:30]: gq.decade_of(t) for t, d in DECADES.items() if gq.decade_of(t) != d}
ok("десятилетие для вопроса «когда» — только однозначное", not wrong, str(wrong))

# ------------------------------------------------------------ настоящая база
if os.path.exists("posts_meta.json"):
    real = json.load(open("posts_meta.json", encoding="utf-8"))
    gq.SCHOOLS_CACHE = os.path.join(tmp, "empty.json")
    calls.clear()
    items, artists, unknown = gq.quiz_data(real, log=lambda *_: None)
    ok("у всех художников сайта школа известна без сети", not unknown and not calls, ", ".join(unknown))

print("\n====== ШКОЛЫ ХУДОЖНИКОВ И ГОДЫ ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
