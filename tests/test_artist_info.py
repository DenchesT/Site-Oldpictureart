# -*- coding: utf-8 -*-
"""Годы жизни художников и статьи в Википедии (sitebuild/artist_info.py).

Сети нет: Wikidata подставная. Проверяется то, что может тихо сломаться:
  • годы и ссылка берутся из записи Wikidata, статья — русская, иначе
    английская;
  • номер записи, известный квизу, используется без поиска;
  • найденное запоминается, вписанное руками главнее и не переспрашивается,
    ненайденное переспрашивается через месяц, сбой сети не запоминается;
  • на странице художника — «Годы жизни», «Годы работ», «Википедия» и
    разметка Person; в указателе — годы рядом с именем.

Запуск:  python tests/test_artist_info.py
"""

import datetime
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.argv = ["build_site.py"]

import build_site as bs  # noqa: E402
import sitebuild.artist_info as ai  # noqa: E402

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


MONET = {"id": "Q296", "claims": {
    "P569": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": "+1840-11-14T00:00:00Z"}}}}],
    "P570": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": "+1926-12-05T00:00:00Z"}}}}]},
    "sitelinks": {"ruwiki": {"title": "Моне, Клод"}, "enwiki": {"title": "Claude Monet"}}}


class FakeQuiz:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def find_artist(self, artist, year=None):
        self.calls.append(("find", artist))
        if self.fail:
            raise OSError("нет сети")
        return {"id": "Q296"} if "Моне" in artist else None

    def _wd(self, params):
        self.calls.append(("wd", params.get("ids")))
        if self.fail:
            raise OSError("нет сети")
        return {"entities": {params["ids"]: MONET if params["ids"] == "Q296" else
                             {"id": params["ids"], "claims": {}, "sitelinks": {"enwiki": {"title": "Somebody X"}}}}}


ok("годы из дат Wikidata", ai.year_of(MONET["claims"], "P569") == 1840 and ai.year_of(MONET["claims"], "P570") == 1926)
ok("статья — русская", ai.wikipedia_url(MONET["sitelinks"]) == "https://ru.wikipedia.org/wiki/%D0%9C%D0%BE%D0%BD%D0%B5%2C_%D0%9A%D0%BB%D0%BE%D0%B4")
ok("нет русской — английская", ai.wikipedia_url({"enwiki": {"title": "Claude Monet"}}) == "https://en.wikipedia.org/wiki/Claude_Monet")
ok("годы жизни подписью", ai.life_years({"born": 1840, "died": 1926}) == "1840–1926"
   and ai.life_years({"born": 1953}) == "род. 1953" and ai.life_years({}) == "")

tmp = tempfile.mkdtemp()
old_cwd = os.getcwd()
os.chdir(tmp)
try:
    with open("artist_schools.json", "w", encoding="utf-8") as f:
        json.dump({"Эдгар Дега": {"school": "fr", "wikidata": "Q46373"}}, f)
    quiz = FakeQuiz()
    today = datetime.date(2026, 10, 17)
    got = ai.resolve({"Клод Моне": 1880, "Эдгар Дега": 1875, "Никто Неизвестный": 1900}, today=today, quiz=quiz, log=lambda *_: None)
    ok("найденный художник — годы и статья", got["Клод Моне"]["born"] == 1840 and got["Клод Моне"]["died"] == 1926
       and "ru.wikipedia.org" in got["Клод Моне"]["wikipedia"], str(got["Клод Моне"]))
    ok("номер из artist_schools.json — без поиска", ("find", "Эдгар Дега") not in quiz.calls
       and ("wd", "Q46373") in quiz.calls)
    ok("ненайденный — пустая запись с датой проверки",
       got["Никто Неизвестный"]["wikidata"] is None and got["Никто Неизвестный"]["checked"] == "2026-10-17")
    saved = json.load(open(ai.INFO_FILE, encoding="utf-8"))
    ok("найденное записано в artist_info.json", saved["Клод Моне"]["born"] == 1840)

    quiz2 = FakeQuiz()
    ai.resolve({"Клод Моне": 1880, "Никто Неизвестный": 1900}, today=today + datetime.timedelta(days=5), quiz=quiz2,
               log=lambda *_: None)
    ok("второй раз в сеть не ходим — ни за найденным, ни за свежим ненайденным", not quiz2.calls, str(quiz2.calls))
    quiz3 = FakeQuiz()
    ai.resolve({"Никто Неизвестный": 1900}, today=today + datetime.timedelta(days=40), quiz=quiz3, log=lambda *_: None)
    ok("ненайденного переспрашиваем через месяц", ("find", "Никто Неизвестный") in quiz3.calls)

    saved = json.load(open(ai.INFO_FILE, encoding="utf-8"))
    saved["Исаак Левитан"] = {"born": 1860, "died": 1900, "wikipedia": "https://ru.wikipedia.org/wiki/Левитан"}
    json.dump(saved, open(ai.INFO_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    quiz4 = FakeQuiz()
    got = ai.resolve({"Исаак Левитан": 1890}, today=today, quiz=quiz4, log=lambda *_: None)
    ok("вписанное руками главнее и не переспрашивается", got["Исаак Левитан"]["born"] == 1860 and not quiz4.calls)

    quiz5 = FakeQuiz(fail=True)
    got = ai.resolve({"Новый Художник": 1900}, today=today, quiz=quiz5, log=lambda *_: None)
    saved = json.load(open(ai.INFO_FILE, encoding="utf-8"))
    ok("сбой сети не запоминается", "Новый Художник" not in saved)
    quiz6 = FakeQuiz()
    ai.resolve({"Другой Художник": 1900}, offline=True, today=today, quiz=quiz6, log=lambda *_: None)
    ok("без сети (--offline) не спрашиваем", not quiz6.calls)

    # Одна заминка Wikidata не обрывает поиск остальных: раньше за сборку
    # находилось по два художника, дальше «Wikidata недоступна».
    class Flaky(FakeQuiz):
        def __init__(self, bad):
            super().__init__()
            self.bad = bad

        def find_artist(self, artist, year=None):
            self.calls.append(("find", artist))
            if artist in self.bad:
                raise OSError("429 Too Many Requests")
            return {"id": "Q296"}
    flaky = Flaky({"Б Заминка"})
    logs = []
    got = ai.resolve({"А Первый": 1880, "Б Заминка": 1880, "В Третий": 1880}, today=today, quiz=flaky, log=logs.append)
    saved = json.load(open(ai.INFO_FILE, encoding="utf-8"))
    ok("одна неудача — остальные художники всё равно найдены", "А Первый" in saved and "В Третий" in saved, str(sorted(saved)))
    ok("…а неудачный не запомнен — спросим в следующий раз", "Б Заминка" not in saved)
    down = Flaky({"Г1", "Г2", "Г3", "Г4", "Г5"})
    logs = []
    ai.resolve({n: 1880 for n in ("Г1", "Г2", "Г3", "Г4", "Г5")}, today=today, quiz=down, log=logs.append)
    asked = [c for c in down.calls if c[0] == "find"]
    ok(f"{ai.MAX_FAILURES} неудачи подряд — Wikidata оставляем в покое", len(asked) == ai.MAX_FAILURES, str(asked))
    ok("…и в журнале — что ответил сервер", any("429" in m for m in logs), str(logs))
finally:
    os.chdir(old_cwd)
    shutil.rmtree(tmp, ignore_errors=True)

# ---------- повтор запроса к Wikidata ----------
import io  # noqa: E402
import urllib.error  # noqa: E402
import generate_quiz  # noqa: E402


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_with(answers):
    seq = list(answers)

    def opener(req, timeout=None):
        a = seq.pop(0)
        if isinstance(a, Exception):
            raise a
        return Resp(json.dumps(a).encode("utf-8"))
    return opener


def http_error(code, retry_after=None):
    return urllib.error.HTTPError("https://www.wikidata.org/w/api.php", code, "x",
                                  {"Retry-After": retry_after} if retry_after else {}, None)


naps = []
data = generate_quiz._wd({"action": "x"}, sleep=naps.append,
                         opener=opener_with([http_error(429, "7"), urllib.error.URLError("timeout"), {"ok": 1}]))
ok("429 и обрыв — запрос повторяется и доходит", data == {"ok": 1}, str(naps))
ok("…ждёт, сколько попросил сервер (Retry-After), потом дольше", naps[:2] == [7, 6], str(naps))
try:
    generate_quiz._wd({"action": "x"}, sleep=lambda s: None, opener=opener_with([http_error(404)]))
    ok("404 — без повторов, сразу ошибка", False)
except urllib.error.HTTPError:
    ok("404 — без повторов, сразу ошибка", True)
try:
    generate_quiz._wd({"action": "x"}, tries=3, sleep=lambda s: None,
                      opener=opener_with([urllib.error.URLError("x")] * 3))
    ok("сети нет совсем — после повторов ошибка доходит до сборки", False)
except urllib.error.URLError:
    ok("сети нет совсем — после повторов ошибка доходит до сборки", True)

info = {"born": 1840, "died": 1926, "wikipedia": "https://ru.wikipedia.org/wiki/Моне", "wikidata": "Q296"}
post = {"artist": "Клод Моне", "title": "Кувшинки, 1906", "creation_year": 1906, "filename": "monet-a.html",
        "images": ["images/a.jpg"], "material": "Холст", "techniques": ["масло"], "date": "2026-01-01"}
page = bs.render_artist_page("Клод Моне", [post], [post], {"monet-a.html": 1}, 3, info)
ok("на странице художника — годы жизни", "<span>Годы жизни</span><b>1840–1926</b>" in page)
ok("…годы работ подписаны как годы работ", "<span>Годы работ</span>" in page and "<span>Годы</span>" not in page)
ok("…и ссылка на Википедию", "<span>Википедия</span><b><a href=\"https://ru.wikipedia.org/wiki/" in page)
ok("разметка Person с годами и ссылками",
   '"@type":"Person"' in page and '"birthDate":"1840"' in page and "wikidata.org/wiki/Q296" in page)
page = bs.render_artist_page("Клод Моне", [post], [post], {"monet-a.html": 1}, 3, None)
ok("без сведений — строк нет, страница цела", "Годы жизни" not in page and "Википедия" not in page)
idx = bs.render_ukazatel([post], {"Клод Моне": info})
ok("в указателе — годы рядом с именем", '<span class="idx-years">1840–1926</span>' in idx)

print("\n====== ГОДЫ ЖИЗНИ И ВИКИПЕДИЯ ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra and not passed else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
