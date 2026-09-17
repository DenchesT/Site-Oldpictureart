# -*- coding: utf-8 -*-
"""Кэш координат музеев: не переспрашивать сеть без причины.

Проверка появилась после неприятной находки. Каждая сборка тратила
двадцать секунд на поиск координат трёх музеев, которые давно лежали
в кэше. Причина: сверялось «какую подсказку хотели» с «каким запросом
в итоге нашлось», а это разные вещи. У «Музея Эжена Будена» в
справочнике стоял адрес, а нашёлся он по названию — значит совпадения
не было никогда, и музей искался заново вечно.

Ошибка была невидимой: карта собиралась правильно, просто медленно,
и в логе это выглядело как обычная работа.

Запуск:  python tests/test_geocache.py
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.argv = ["generate_map.py"]

import generate_map as gm

logging.disable(logging.CRITICAL)

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


NAME = "Музей Эжена Будена, Онфлёр"
POINT = {"lat": 49.4223, "lon": 0.2306, "display_name": "Музей Эжена Будена",
         "source": "wikidata:Q3329155", "precision": "exact"}


def fake_geocoders():
    """Считает обращения к сети и всегда «находит» по названию."""
    calls = []

    def wikidata(query):
        calls.append(query)
        return dict(POINT) if "Буден" in query else None

    def nominatim(query):
        calls.append(query)
        return None

    gm.wikidata_search = wikidata
    gm.nominatim_search = nominatim
    return calls


# ------------------------------------------------- подсказка держит кэш
calls = fake_geocoders()
overrides = {NAME: {"address": "Place Erik Satie, Honfleur",
                    "query": "Musée Eugène Boudin"}}
cache = {}

gm.geocode(NAME, cache, overrides)
first = len(calls)
ok("первый поиск идёт в сеть", first > 0, f"{first} запросов")
ok("подсказка запомнена вместе с координатами",
   cache[NAME].get("hint") is not None, repr(cache[NAME].get("hint")))
ok("запомнено и то, чем нашлось", cache[NAME].get("query"), repr(cache[NAME].get("query")))

gm.geocode(NAME, cache, overrides)
gm.geocode(NAME, cache, overrides)
ok("повторные сборки в сеть не ходят", len(calls) == first,
   f"лишних запросов: {len(calls) - first}")

# ---------------------------------------------- правка справочника видна
before = len(calls)
overrides[NAME] = {"address": "Rue Albert 1er, Honfleur", "query": "Musée Eugène Boudin"}
gm.geocode(NAME, cache, overrides)
ok("правка адреса в справочнике заставляет искать заново", len(calls) > before,
   f"{len(calls) - before} запросов")

before = len(calls)
gm.geocode(NAME, cache, overrides)
ok("после правки снова тихо", len(calls) == before)

# ------------------------- старый кэш без подсказки не ломает и не зацикливает
calls2 = fake_geocoders()
old_cache = {NAME: dict(POINT, query="Музей Эжена Будена")}   # как до починки
ov = {NAME: {"address": "Place Erik Satie, Honfleur", "query": "Musée Eugène Boudin"}}
gm.geocode(NAME, old_cache, ov)
after_first = len(calls2)
gm.geocode(NAME, old_cache, ov)
gm.geocode(NAME, old_cache, ov)
ok("прежний кэш пересматривается один раз, а не каждый раз",
   len(calls2) == after_first, f"лишних запросов: {len(calls2) - after_first}")

# ------------------------------- появившаяся подсказка оживляет неудачу
calls3 = fake_geocoders()
dead = {NAME: None}          # прошлый поиск ничего не дал
gm.geocode(NAME, dead, {NAME: {"address": "Place Erik Satie, Honfleur"}})
ok("подсказка, добавленная к ненайденному месту, вызывает новый поиск",
   len(calls3) > 0, f"{len(calls3)} запросов")

# без подсказки неудача остаётся неудачей и сеть не трогает
calls4 = fake_geocoders()
gm.geocode("Несуществующее место", {"Несуществующее место": None}, {})
ok("ненайденное без подсказки сеть не беспокоит", len(calls4) == 0,
   f"{len(calls4)} запросов")

# ------------------------------------ частные собрания не ищутся никогда
calls5 = fake_geocoders()
gm.geocode("Частная коллекция", {}, {"Частная коллекция": {"skip": True}})
ok("частные собрания в сеть не отправляются", len(calls5) == 0)

print("\n======== КЭШ КООРДИНАТ ========")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}" + (f"  — {extra}" if extra else ""))
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
