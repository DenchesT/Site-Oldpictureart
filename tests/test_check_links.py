# -*- coding: utf-8 -*-
"""Проверка внешних ссылок: источники картин, ссылки походов, сайты музеев.

Сети нет: ответы сайтов подставные. Проверяется то, что может тихо
сломаться:
  • собираются все ссылки — голые адреса и подписанные, у картин и у
    походов, плюс сайты музеев; с --posts сайты музеев не трогаются;
  • один адрес на нескольких страницах проверяется один раз, а в отчёте
    видно все страницы, где его править;
  • метки слежения (ysclid, utm_…) снимаются: с ними и без них — одна
    страница;
  • отчёт делит ответы на «не работает» и «проверить не вышло», в итог
    идёт только первое, и подсказывает, как поправить.

Запуск:  python tests/test_check_links.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.chdir(os.path.join(HERE, ".."))
os.environ.setdefault("OPA_OFFLINE_RENDER", "1")
sys.argv = ["check_links.py"]

import check_links as cl
import build_site as bs

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


POSTS = [
    {"filename": "a.html", "artist": "Сислей", "title": "Луг",
     "urls": ["https://museum.example/card/1"],
     "links": [{"text": "другая работа", "url": "https://museum.example/card/2?ysclid=abc"}]},
    {"filename": "b.html", "artist": "Коровин", "title": "Париж",
     "urls": ["https://museum.example/card/1"], "links": []},
]
VISITS = [
    {"filename": "visit-x.html", "title": "Выставка", "place": "Музей",
     "urls": [], "links": [{"text": "Выставка", "url": "https://expo.example/?utm_source=tg&id=5"}]},
]
OVERRIDES = {"_комментарий": "…", "Музей А, Город": {"site": "https://site.example"},
             "Частная коллекция": {"skip": True}}

found = cl.collect(POSTS, VISITS, OVERRIDES, clean=bs.clean_url)
ok("собраны ссылки картин, походов и сайты музеев",
   set(found) == {"https://museum.example/card/1", "https://museum.example/card/2",
                  "https://expo.example/?id=5", "https://site.example"}, str(sorted(found)))
ok("один адрес на двух страницах — одна проверка, обе страницы в отчёте",
   [w for w, _ in found["https://museum.example/card/1"]] == ["a.html", "b.html"])
ok("метки слежения сняты до проверки", "https://museum.example/card/2" in found
   and "https://expo.example/?id=5" in found)
ok("служебные записи справочника пропущены", not any("_комментарий" in str(v) for v in found.values()))
ok("--posts: без сайтов музеев",
   "https://site.example" not in cl.collect(POSTS, VISITS, {}, clean=bs.clean_url))
ok("не-http адреса не собираются",
   cl.collect([{"filename": "c.html", "urls": ["tg://x", "mailto:a@b"]}], [], {}) == {})

answers = {
    "https://museum.example/card/1": ("bad", "страницы нет (404)"),
    "https://museum.example/card/2": ("ok", ""),
    "https://expo.example/?id=5": ("unknown", "сайт отвечает, но не пускает проверку (403)"),
    "https://site.example": ("bad", "такого домена нет"),
}
asked = []


def fake_check(url):
    asked.append(url)
    return answers[url]


res = cl.check_all(found, fake_check, workers=3)
ok("каждый адрес проверен ровно один раз", sorted(asked) == sorted(found))
lines = []
n = cl.report(found, res, out=lines.append)
text = "\n".join(lines)
ok("в итоге — только нерабочие", n == 2, str(n))
ok("нерабочая ссылка показана со страницами, где её править",
   "на странице: a.html (Сислей — Луг)" in text and "на странице: b.html (Коровин — Париж)" in text)
ok("подсказка про --refresh для ссылок из постов", "--refresh" in text)
ok("подсказка про справочник для сайтов музеев", '"site"' in text)
ok("«проверить не вышло» — отдельно, со знаком вопроса", "? https://expo.example/?id=5" in text)
ok("сводка вверху", "Проверено ссылок: 4 — работают 1, не работают 2, проверить не вышло 1" in text,
   lines[0] if lines else "")

mixed = cl.interleave(["https://a.ru/1", "https://a.ru/2", "https://a.ru/3", "https://b.ru/1", "https://c.ru/1"])
ok("один и тот же сайт не спрашивается подряд",
   mixed[:3] == ["https://a.ru/1", "https://b.ru/1", "https://c.ru/1"] and sorted(mixed) == sorted(set(mixed)),
   str(mixed))

lines = []
n = cl.report({"https://ok.example": [("a.html", "")]}, {"https://ok.example": ("ok", "")}, out=lines.append)
ok("всё работает — так и сказано", n == 0 and any("Нерабочих ссылок нет" in l for l in lines))

print("\n====== ВНЕШНИЕ ССЫЛКИ ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
