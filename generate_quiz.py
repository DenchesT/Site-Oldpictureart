# -*- coding: utf-8 -*-
"""
Генератор страницы квиза для Old Picture Art.
Запуск: python generate_quiz.py            # школы новых художников — из Wikidata
        python generate_quiz.py --offline  # без сети
"""

import datetime
import json
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request

from site_common import (head_common, theme_button, site_footer, COMMON_JS, BASE_URL,
                         split_title_date, date_years)

META_FILE = "posts_meta.json"
OUTPUT_DIR = "docs"

# ------------------------------------------------------------ школы
# Варианты ответа раньше брались наугад из всех художников, и вопрос
# решался без знания живописи: к французскому пейзажу 1870-х рядом
# стояли Репин, Пуссен и Бирштадт, и лишнее отпадало само. Теперь
# варианты подбираются из той же школы и того же времени.
#
# Страны в записях канала нет. Откуда она берётся, по порядку:
#   1. artist_schools.json — если там у художника вписана школа. Это
#      файл для поправок: что в нём написано, то и главное.
#   2. Список SCHOOLS ниже — художники, разобранные вручную (по фамилии).
#   3. Wikidata — для всех остальных, сама, при сборке: ищет художника,
#      берёт гражданство и переводит его в школу. Ответ запоминается в
#      artist_schools.json, и в сеть за этим художником больше не ходим.
#   4. Отчество — русского видно по нему, даже когда сети нет.
# Не нашлось ничего — варианты к нему подбираются по годам, а сборка
# пишет строку, где это поправить.
#
# Коды школ: fr, ru, de (Германия, Австрия, Швейцария), north
# (Скандинавия и Финляндия), us, gb (Британия и Ирландия), es, it,
# nl (Нидерланды и Бельгия).
SCHOOLS = {
    # Франция — и те, кто стал французским художником (Сислей, Луар)
    "fr": """Сислей Дега Писсарро Кайботт Базиль Курбе Форен Гийомен Мане
             Ренуар Пуссен Брюн Луар Мартен Делакруа Тройон Лотрек Эллё
             Латур Дюриваж Буден Руар Милле Детай Моризо Ангран Пьетт""",
    "ru": """Репин Тархов Морозов Кузнецов Куинджи Юон Грабарь Серов
             Савицкий Левитан Брюллов Кустодиев Жуковский Сверчков
             Маковский Коровин""",
    "de": "Фридрих Штук Либерман Слефогт Ходлер Альт Штерль",
    "north": "Таулов Даль Петерссен Юхансен Каллела Цорн Осслунд",
    "us": "Гассам Бирштадт Кент Сарджент",
    "gb": "Гловер Каделл Констебл",
    "es": "Беруэте Мейфрен Рузиньол",
    "it": "Дзандоменеги",
    "nl": "Сегерс Гог Бош",
}
SCHOOL_NAMES = {
    "fr": "Франция", "ru": "Россия", "de": "Германия, Австрия, Швейцария",
    "north": "Скандинавия и Финляндия", "us": "США", "gb": "Британия и Ирландия",
    "es": "Испания", "it": "Италия", "nl": "Нидерланды и Бельгия",
}

# Если своей школы на три варианта не хватает (британцев всего трое),
# добираем из близкой, а не из первой попавшейся.
NEAR = {
    "gb": ["us"], "us": ["gb"],
    "es": ["it", "fr"], "it": ["es", "fr"],
    "nl": ["de", "fr"], "de": ["north", "nl"], "north": ["de", "ru"],
    "fr": ["nl", "it", "es"], "ru": ["north"],
}

SCHOOLS_CACHE = "artist_schools.json"
# Художника, которого Wikidata не знает, переспрашиваем раз в месяц, а не
# на каждой сборке: вдруг статью о нём за это время завели.
RETRY_DAYS = 30

_SURNAME_SCHOOL = {w.lower().replace("ё", "е"): code
                   for code, names in SCHOOLS.items() for w in names.split()}
_PATRONYMIC = re.compile(r"(ович|евич|ьич|ична|овна|евна)$")


def _words(name):
    return re.findall(r"[а-яa-z]+", name.lower().replace("ё", "е"))


def school_of(artist):
    """Школа по ручному списку или по отчеству — без сети. None, если не знаем."""
    words = _words(artist)
    for w in words:
        if w in _SURNAME_SCHOOL:
            return _SURNAME_SCHOOL[w]
    if any(_PATRONYMIC.search(w) for w in words):
        return "ru"
    return None


# ------------------------------------------------------------ Wikidata
USER_AGENT = "OldPictureArt/1.0 (github.com/DenchesT/Site-Oldpictureart)"
WD_API = "https://www.wikidata.org/w/api.php"

# Страна → школа по английскому названию страны. Так узнаются и нынешние
# государства, и исторические — «Russian Empire», «Kingdom of Prussia»,
# «Second French Empire», «Austria-Hungary» — без таблицы из сотни
# номеров. Порядок важен: «Grand Duchy of Finland» — это Финляндия,
# а не Россия; «United Kingdom of the Netherlands» — Нидерланды, а не
# Британия; «Spanish Netherlands» — тоже Нидерланды.
COUNTRY_WORDS = [
    ("north", ("norway", "sweden", "denmark", "finland", "iceland")),
    ("nl", ("netherlands", "dutch", "belgium", "holland", "flanders")),
    ("ru", ("russia", "soviet")),
    ("de", ("german", "prussia", "bavaria", "saxony", "württemberg", "hanover",
            "austria", "switzerland", "swiss", "holy roman")),
    ("fr", ("france", "french")),
    ("gb", ("united kingdom", "great britain", "england", "scotland", "wales",
            "ireland", "irish", "british")),
    ("us", ("united states",)),
    ("es", ("spain", "spanish", "catalonia")),
    ("it", ("italy", "italian", "venice", "venetian", "sardinia", "papal",
            "tuscany", "naples", "two sicilies", "genoa", "milan", "lombardy")),
]

# Род занятий, по которому ясно, что нашёлся художник, а не тёзка-генерал:
# живописец, художник, график, рисовальщик, гравёр, офортист, акварелист.
ARTIST_OCCUPATIONS = {"Q1028181", "Q483501", "Q1925963", "Q15296811",
                      "Q11569986", "Q10862983", "Q3391743", "Q18074503"}
PAINTER = "Q1028181"


def school_from_country(label_en):
    # Слово ищется с начала слова: иначе «Kingdom of Prussia» — это
    # «russia» внутри «prussia», и Пруссия уезжала в Россию.
    s = (label_en or "").lower()
    for code, words in COUNTRY_WORDS:
        if any(re.search(r"\b" + re.escape(w), s) for w in words):
            return code
    return None


def _wd(params):
    """Запрос к API Wikidata. Отдельной функцией — чтобы проверки могли
    подставить готовые ответы и не ходить в сеть."""
    query = urllib.parse.urlencode(dict(params, format="json"))
    req = urllib.request.Request(f"{WD_API}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    time.sleep(0.3)       # вежливость к чужому серверу
    return data


def _ids(claims, prop):
    out = []
    for c in claims.get(prop) or []:
        if c.get("rank") == "deprecated":
            continue
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            out.append((c.get("rank") == "preferred", v["id"]))
    # сначала предпочтительные, дальше в том порядке, как записано
    return [q for _, q in sorted(out, key=lambda x: not x[0])]


def _year_claim(claims, prop):
    for c in claims.get(prop) or []:
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, dict):
            m = re.match(r"[+-]?(\d{3,4})-", v.get("time", ""))
            if m:
                return int(m.group(1))
    return None


def _name_queries(artist):
    """Во что превратить имя из канала, чтобы Wikidata его узнала.

    В канале имя полное — «Жакоб Абраам Камиль Писсарро», «Илер-Жермен-
    Эдгар де Га (Эдгар Дега)», — а в Wikidata его знают как «Камиль
    Писсарро» и «Эдгар Дега». Пробуем от самого точного к самому общему.
    """
    inner = re.search(r"\(([^)]+)\)", artist)
    base = re.sub(r"\s*\([^)]*\)", "", artist).strip()
    words = base.split()
    queries = []
    if inner:
        queries.append(inner.group(1).strip())
    queries.append(base)
    if len(words) > 2:
        queries += [f"{words[-2]} {words[-1]}", f"{words[0]} {words[-1]}"]
    return list(dict.fromkeys(q for q in queries if q))


def _surnames(artist):
    """Фамилия для поиска среди художников: «Тулуз-Лотрек-Монфа» →
    «Тулуз-Лотрек-Монфа», «Тулуз-Лотрек»; «Мейфрен-и-Роч» → «Мейфрен»."""
    inner = re.search(r"\(([^)]+)\)", artist)
    base = re.sub(r"\s*\([^)]*\)", "", artist).strip()
    out = []
    for name in ([inner.group(1)] if inner else []) + [base]:
        last = name.split()[-1] if name.split() else ""
        parts = [x for x in last.split("-") if x.lower() not in ("и", "де", "да", "ди")]
        for k in range(len(parts), 0, -1):
            out.append("-".join(parts[:k]))
    return list(dict.fromkeys(x for x in out if len(x) > 2))


def _judge(entity, artist, year):
    """Насколько найденная запись похожа на нашего художника. None — точно не он."""
    claims = entity.get("claims") or {}
    if "Q5" not in _ids(claims, "P31"):                 # не человек
        return None
    names = []
    for lang in ("ru", "en"):
        lab = (entity.get("labels") or {}).get(lang)
        if lab:
            names.append(lab.get("value", ""))
        names += [a.get("value", "") for a in (entity.get("aliases") or {}).get(lang, [])]
    have = set(_words(" ".join(names)))
    want = set(_words(re.sub(r"[()]", " ", artist)))
    surname = set(_words(" ".join(_surnames(artist))))
    if not (surname & have):                            # фамилия не та
        return None
    born, died = _year_claim(claims, "P569"), _year_claim(claims, "P570")
    if year:
        if born and not (born + 8 <= year <= born + 100):   # тёзка из другого века
            return None
        if died and year > died + 1:
            return None
    painter = bool(set(_ids(claims, "P106")) & ARTIST_OCCUPATIONS)
    overlap = len(want & have) / max(1, len(want))
    if not painter and overlap < 0.75:
        return None
    return overlap + (0.5 if painter else 0) + (0.1 if born else 0)


def wikidata_school(artist, year=None):
    """Ищет художника в Wikidata. Возвращает запись для artist_schools.json:
    {"school", "country", "wikidata"}; school и wikidata могут быть None,
    если не нашёлся или страна не переводится в школу.

    Ошибки сети не глотаются — их ловит вызывающий: неудачный запрос не
    должен запомниться как «такого художника нет».
    """
    seen, best = set(), (0, None)

    def consider(ids):
        nonlocal best
        ids = [q for q in ids if q not in seen][:20]
        if not ids:
            return
        seen.update(ids)
        data = _wd({"action": "wbgetentities", "ids": "|".join(ids),
                    "props": "labels|aliases|claims", "languages": "ru|en"})
        for qid, ent in (data.get("entities") or {}).items():
            score = _judge(ent, artist, year)
            if score is not None and score > best[0]:
                best = (score, ent)

    for q in _name_queries(artist):
        found = _wd({"action": "wbsearchentities", "search": q, "language": "ru",
                     "uselang": "ru", "type": "item", "limit": 10})
        consider([x["id"] for x in found.get("search") or []])
        if best[0] >= 1.1:          # имя совпало почти целиком, и это художник
            break
    if best[0] < 1.1:
        # Полного имени Wikidata не знает — ищем фамилию среди живописцев.
        for q in _surnames(artist):
            found = _wd({"action": "query", "list": "search", "srnamespace": 0, "srlimit": 10,
                         "srsearch": f"{q} haswbstatement:P106={PAINTER}"})
            consider([x["title"] for x in (found.get("query") or {}).get("search") or []])
            if best[0] >= 0.8:
                break

    if best[1] is None or best[0] < 0.75:
        return {"school": None, "country": None, "wikidata": None}

    ent = best[1]
    countries = _ids(ent.get("claims") or {}, "P27")[:5]
    if not countries:
        return {"school": None, "country": None, "wikidata": ent.get("id")}
    data = _wd({"action": "wbgetentities", "ids": "|".join(countries),
                "props": "labels", "languages": "ru|en"})
    labels = [((data.get("entities") or {}).get(c) or {}).get("labels") or {} for c in countries]
    school = next((sc for sc in (school_from_country((l.get("en") or {}).get("value")) for l in labels) if sc), None)
    country = ", ".join((l.get("ru") or l.get("en") or {}).get("value", "") for l in labels if l)
    return {"school": school, "country": country or None, "wikidata": ent.get("id")}


def resolve_schools(artists_years, offline=False, today=None, log=print):
    """Школы для всех художников квиза: {имя: код или None}.

    artists_years — {имя: год середины его работ или None}. Читает и
    дополняет artist_schools.json (порядок источников — в начале раздела).
    """
    today = today or datetime.date.today()
    cache = {}
    if os.path.exists(SCHOOLS_CACHE):
        try:
            with open(SCHOOLS_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError) as e:
            log(f"Квиз: {SCHOOLS_CACHE} не читается ({e}) — школы пересчитаю заново")
            cache = {}

    result, changed, network_down = {}, False, offline
    for artist in sorted(artists_years):
        entry = cache.get(artist) or {}
        if entry.get("school"):
            result[artist] = entry["school"]
            continue
        # Разобран вручную или русский по отчеству — в сеть незачем.
        manual = school_of(artist)
        if manual:
            result[artist] = manual
            continue

        checked = entry.get("checked")
        fresh = False
        if checked:
            try:
                fresh = (today - datetime.date.fromisoformat(checked)).days < RETRY_DAYS
            except ValueError:
                pass
        if not network_down and not fresh:
            try:
                found = wikidata_school(artist, artists_years[artist])
            except Exception as e:           # сети нет, сервер не ответил
                log(f"Квиз: Wikidata недоступна ({e.__class__.__name__}) — "
                    f"школы новых художников определю в следующий раз")
                network_down = True
            else:
                entry = dict(found, checked=today.isoformat())
                cache[artist] = entry
                changed = True
                if found["school"]:
                    log(f"Квиз: «{artist}» — {found['country']} → {SCHOOL_NAMES[found['school']]} "
                        f"(Wikidata {found['wikidata']})")

        school = entry.get("school")
        result[artist] = school
        if not school:
            why = (f"гражданство «{entry['country']}» ни к одной школе не относится" if entry.get("country")
                   else "в Wikidata не нашёлся" if entry.get("checked") else "Wikidata не спрашивали")
            log(f"Квиз: школа «{artist}» не определена ({why}); варианты к нему подбираются по годам. "
                f"Вписать вручную: {SCHOOLS_CACHE} → \"school\": \"fr\" (коды: {', '.join(SCHOOL_NAMES)})")

    if changed:
        with open(SCHOOLS_CACHE, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    return result


def year_of(post):
    m = re.search(r"\d{4}", str(post.get("creation_year") or ""))
    return int(m.group()) if m else None


def decade_of(title):
    """Десятилетие для вопроса «когда написано» или None.

    Работы, чья дата перешагивает через границу десятилетий («1885-1895»,
    «около 1618-20»), в этот вопрос не идут: верными были бы сразу два
    ответа из четырёх.
    """
    name, date = split_title_date(title)
    first, last = date_years(date)
    if first is None or first // 10 != last // 10:
        return None
    # И те, где год стоит в самом названии («Парад на Красной площади
    # 7 ноября 1941 года»): ответ был бы написан под картиной.
    if re.search(r"\d{4}", name):
        return None
    return first // 10 * 10


def quiz_data(all_posts, offline=True, log=print):
    """Посты для квиза и сведения о художниках для подбора вариантов.

    Записи, где авторов несколько («Анонимные художники, Феликс Милиус…»),
    в квиз не идут: ответ в них угадывается по длине кнопки, а вариантом
    к чужой картине такая строчка выглядит нелепо.

    offline=False — школы новых художников спрашиваются у Wikidata.
    """
    posts = [p for p in all_posts
             if p.get("images") and p.get("artist") and "," not in p["artist"]]
    years = {}
    for p in posts:
        y = year_of(p)
        if y:
            years.setdefault(p["artist"], []).append(y)
    middle = {a: (int(statistics.median(years[a])) if a in years else None)
              for a in {p["artist"] for p in posts}}

    schools = resolve_schools(middle, offline=offline, log=log)
    artists = {a: [schools.get(a), middle[a]] for a in sorted(middle)}
    unknown = [a for a in artists if not artists[a][0]]

    items = []
    for p in posts:
        name, date = split_title_date(p.get("title", ""))
        items.append({"artist": p["artist"],
                      "title": p.get("title", ""),
                      "filename": p.get("filename", ""),
                      "images": p["images"][:1],
                      "y": year_of(p),
                      # для вопроса «когда»: название без даты, сама дата
                      # как в канале и верное десятилетие
                      "t": name, "d": date, "dec": decade_of(p.get("title", ""))})
    return items, artists, unknown

def generate_quiz_page():
    if not os.path.exists(META_FILE):
        print(f"Файл {META_FILE} не найден!")
        return
    
    with open(META_FILE, "r", encoding="utf-8") as f:
        all_posts = json.load(f)
    
    # В страницу кладём только то, чем квиз пользуется. Раньше сюда
    # целиком уезжала база постов — со всеми описаниями, ссылками на
    # источники, размерами, тегами и путями к оригиналам: 286 КБ из 473 КБ
    # веса страницы ради имени художника и адреса одной картинки.
    # Школы новых художников спрашиваются у Wikidata; с --offline — нет.
    valid_posts, artists, _ = quiz_data(all_posts, offline="--offline" in sys.argv)

    if len(valid_posts) < 4:
        print("Недостаточно постов для квиза")
        return
    
    head = head_common(
        title="Квиз — Old Picture Art",
        description="Угадайте художника по картине: небольшая игра по коллекции Old Picture Art.",
        canonical=f"{BASE_URL}/quiz.html",
    )

    html = f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
{head}
<style>
* {{ box-sizing: border-box; }}

.quiz-wrapper {{
  max-width: 900px;
  margin: 0 auto;
  padding: 0 1rem 0.5rem;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}}

.quiz-container {{
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  text-align: center;
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
  gap: 0.4rem;
}}

.quiz-container h1 {{
  font-size: 1.4rem;
  margin: 0;
}}

.quiz-stage {{
  /* Постоянная высота. Раньше картина просто меняла размер от вопроса
     к вопросу, и вместе с ней прыгали вверх-вниз кнопки ответов: палец
     уже летел к нужной, а под ним оказывалась соседняя. */
  height: 35vh;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;
}}

.quiz-painting {{
  max-width: 100%;
  max-height: 100%;
  height: auto;
  width: auto;
  border-radius: 8px;
  box-shadow: 0 4px 20px var(--shadow);
  margin: 0 auto;
  display: block;
  object-fit: contain;
}}

.quiz-answers {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
  margin: 0;
}}

.quiz-btn {{
  background: var(--card-bg);
  border: 2px solid var(--border);
  padding: 0.5rem 0.8rem;
  border-radius: 10px;
  cursor: pointer;
  font-size: 0.9rem;
  color: var(--text);
  transition: all .2s;
  font-family: inherit;
  white-space: normal;
  word-break: break-word;
  min-height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  line-height: 1.2;
}}

.quiz-btn:hover {{ border-color: var(--active); background: var(--border); }}
.quiz-btn.correct {{ border-color: #27ae60; background: rgba(39,174,96,.15); color: #27ae60; font-weight: 700; }}
.quiz-btn.wrong {{ border-color: var(--like-color); background: rgba(231,76,60,.15); color: var(--like-color); }}
.quiz-btn:disabled {{ pointer-events: none; opacity: 0.8; }}

.quiz-score {{
  font-size: 1rem;
  font-weight: 700;
  margin: 0;
  color: var(--active);
}}

.quiz-next {{ 
  display: none;
  background: var(--active);
  color: #fff;
  border: none;
  padding: 0.4rem 1.5rem;
  border-radius: 20px;
  cursor: pointer;
  font-size: 0.9rem;
  font-family: inherit;
  margin: 0 auto;
  transition: opacity .2s;
}}

.quiz-next:hover {{ opacity: .8; }}

.quiz-result {{
  font-size: 0.85rem;
  color: var(--muted);
  min-height: 1.2rem;
  margin: 0;
}}

.quiz-reset-btn {{
  background: var(--reset-bg);
  color: var(--reset-text);
  border: none;
  padding: 0.3rem 1rem;
  border-radius: 20px;
  cursor: pointer;
  font-size: 0.8rem;
  font-family: inherit;
  margin: 0 0.3rem;
  transition: opacity .2s;
}}

.quiz-reset-btn:hover {{ opacity: .8; }}

.quiz-modes {{ align-self: center; margin: 0.2rem 0; }}
.quiz-artist {{ margin: 0; font-weight: 700; font-size: 0.9rem; line-height: 1.2; }}

.quiz-title {{
  font-style: italic;
  color: var(--muted);
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.2;
}}

.quiz-buttons {{
  margin: 0;
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0.3rem;
}}

.quiz-buttons .random-btn {{
  font-size: 0.85rem;
  padding: 0.3rem 1rem;
  margin: 0;
}}

/* Десктоп */
@media (min-width: 769px) {{
  .quiz-container {{
    justify-content: center;
  }}
  
  .quiz-stage {{
    height: 40vh;
  }}
  
  .quiz-answers {{
    gap: 0.75rem;
  }}
  
  .quiz-btn {{
    font-size: 1rem;
    padding: 0.75rem 1rem;
    min-height: 3rem;
  }}
  
  .quiz-container h1 {{
    font-size: 1.8rem;
  }}
  
  .quiz-score {{
    font-size: 1.2rem;
  }}
}}

/* Планшеты */
@media (max-width: 768px) {{
  .quiz-stage {{
    height: 30vh;
  }}
  
  .quiz-answers {{
    gap: 0.5rem;
  }}
  
  .quiz-btn {{
    font-size: 0.85rem;
    padding: 0.5rem 0.7rem;
    min-height: 2.5rem;
  }}
}}

/* Телефоны */
@media (max-width: 480px) {{
  .quiz-wrapper {{
    padding: 0 0.5rem 0.5rem;
  }}
  
  .quiz-container h1 {{
    font-size: 1.1rem;
  }}
  
  .quiz-stage {{
    height: 25vh;
  }}
  
  .quiz-answers {{
    grid-template-columns: 1fr;
    gap: 0.35rem;
  }}
  
  .quiz-btn {{
    font-size: 0.8rem;
    padding: 0.4rem 0.6rem;
    min-height: 2.2rem;
    border-radius: 8px;
  }}
  
  .quiz-score {{
    font-size: 0.9rem;
  }}
  
  .quiz-title {{
    font-size: 0.75rem;
  }}
  
  .quiz-next {{
    padding: 0.35rem 1.2rem;
    font-size: 0.8rem;
  }}
  
  .quiz-result {{
    font-size: 0.75rem;
  }}
  
  .quiz-reset-btn {{
    font-size: 0.7rem;
    padding: 0.25rem 0.7rem;
  }}
  
  .quiz-buttons .random-btn {{
    font-size: 0.75rem;
    padding: 0.25rem 0.8rem;
  }}
}}
.quiz-topbar {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; padding: .4rem 1rem; }}
</style>
</head><body class="quiz-page">
<div class="quiz-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
<div class="quiz-wrapper">
  <div class="quiz-container">
    <h1 id="quiz-heading">Квиз: угадай художника</h1>
    <div class="view-switch quiz-modes" role="group" aria-label="Что угадывать">
      <button type="button" data-mode="artist" aria-pressed="true">Художник</button>
      <button type="button" data-mode="year" aria-pressed="false">Десятилетие</button>
    </div>
    <p class="quiz-score">Счёт: <span id="score">0</span> / <span id="total">0</span></p>
    <div class="quiz-stage"><img id="quiz-image" class="quiz-painting" alt="" hidden src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"></div>
    <p id="quiz-artist" class="quiz-artist" hidden></p>
    <p id="quiz-title" class="quiz-title"></p>
    <div id="quiz-answers" class="quiz-answers"></div>
    <p id="quiz-feedback" class="quiz-result" role="status" aria-live="polite"></p>
    <button type="button" id="quiz-next" class="quiz-next" onclick="newQuestion()">Следующий вопрос</button>
    <div class="quiz-buttons">
      <button type="button" class="random-btn" onclick="startNewGame()">Новая игра</button>
      <button type="button" class="quiz-reset-btn" onclick="resetQuiz()">Сбросить счёт</button>
    </div>
  </div>
</div>
{site_footer()}
{COMMON_JS}
<script>
const ALL_POSTS = {json.dumps(valid_posts, ensure_ascii=False)};
// художник → [школа, год середины его работ на сайте]
const ARTISTS = {json.dumps(artists, ensure_ascii=False)};
const NEAR = {json.dumps(NEAR)};

// Два вопроса: «кто написал» и «когда написано». Счёт у каждого свой;
// выбранный запоминается, а адрес quiz.html#year открывает сразу второй.
const MODES = {{
    artist: {{ heading: 'Квиз: угадай художника', key: 'quizProgress' }},
    year:   {{ heading: 'Квиз: угадай десятилетие', key: 'quizProgressYear' }},
}};
function readMode() {{
    const h = location.hash.replace('#', '');
    if (MODES[h]) return h;
    try {{ const m = localStorage.getItem('quizMode'); if (MODES[m]) return m; }} catch (e) {{}}
    return 'artist';
}}
let mode = readMode();
let score = 0;
let total = 0;
let currentPost = null;
let correctLabel = '';

function showScore() {{
    document.getElementById('score').textContent = score;
    document.getElementById('total').textContent = total;
}}
function loadProgress() {{
    let saved = {{}};
    try {{ saved = JSON.parse(localStorage.getItem(MODES[mode].key) || '{{}}') || {{}}; }} catch (e) {{}}
    score = saved.score || 0;
    total = saved.total || 0;
    showScore();
}}
function saveProgress() {{
    try {{ localStorage.setItem(MODES[mode].key, JSON.stringify({{score: score, total: total}})); }} catch (e) {{}}
}}

function shuffle(arr) {{
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {{
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
    }}
    return a;
}}

// Картины идут колодой: пока не показаны все, ни одна не повторяется.
// Раньше каждая бралась наугад заново, и одна и та же могла выпасть
// дважды подряд, пока другие не выпадали ни разу.
// У каждого вопроса своя колода.
const decks = {{ artist: [], year: [] }};
function nextPost(available) {{
    if (!decks[mode].length) {{
        const deck = shuffle(available);
        // новая колода не начинается с картины, которой кончилась старая
        if (currentPost && deck.length > 1 && deck[deck.length - 1] === currentPost) deck.unshift(deck.pop());
        decks[mode] = deck;
    }}
    return decks[mode].pop();
}}

// Три неверных варианта: сначала художники той же школы и близкого
// времени, потом соседней школы. Щепотка случайности — чтобы к одной
// картине не выпадала каждый раз одна и та же тройка.
function pickOthers(post) {{
    const own = ARTISTS[post.artist] || [null, null];
    const school = own[0];
    const year = post.y || own[1];
    return Object.keys(ARTISTS)
        .filter(a => a !== post.artist)
        .map(a => {{
            const [s, y] = ARTISTS[a];
            let score = (school && s) ? (s === school ? 0 : (NEAR[school] || []).includes(s) ? 60 : 150) : 80;
            score += (year && y) ? Math.min(Math.abs(y - year), 150) * 0.6 : 40;
            score += Math.random() * 40;
            return [score, a];
        }})
        .sort((p, q) => p[0] - q[0])
        .slice(0, 3)
        .map(x => x[1]);
}}

// Варианты «когда»: четыре десятилетия подряд, верное — на случайном
// месте. Подряд, а не вразброс: отличить 1860-е от 1870-х и есть вопрос,
// а 1660-е рядом с 1890-ми отпадали бы сами. Точный год из четырёх
// вариантов — лотерея, поэтому спрашиваем десятилетие, а год
// показываем после ответа.
function decadeOptions(dec) {{
    const k = Math.floor(Math.random() * 4);
    return [0, 1, 2, 3].map(i => (dec + 10 * (i - k)) + '-е');
}}

function pool() {{
    return ALL_POSTS.filter(p => p.images && p.images.length > 0 && (mode === 'year' ? p.dec : p.artist));
}}

function newQuestion() {{
    const feedback = document.getElementById('quiz-feedback');
    feedback.textContent = '';
    document.getElementById('quiz-next').style.display = 'none';

    const available = pool();
    if (available.length < 4 || (mode === 'artist' && Object.keys(ARTISTS).length < 4)) {{
        feedback.textContent = 'Недостаточно картин для игры';
        return;
    }}

    currentPost = nextPost(available);
    let options;
    if (mode === 'year') {{
        correctLabel = currentPost.dec + '-е';
        options = decadeOptions(currentPost.dec);      // по порядку, как на шкале
    }} else {{
        correctLabel = currentPost.artist;
        options = shuffle([currentPost.artist].concat(pickOthers(currentPost)));
    }}

    // В вопросе «когда» дата из названия убрана — иначе ответ был бы
    // написан под картиной, — а художник показан: это честная подсказка.
    const title = mode === 'year' ? currentPost.t : currentPost.title;
    const img = document.getElementById('quiz-image');
    img.src = currentPost.images[0];
    img.alt = 'Картина: ' + (title || 'без названия');
    img.hidden = false;
    document.getElementById('quiz-title').textContent = title || '';
    const who = document.getElementById('quiz-artist');
    who.textContent = mode === 'year' ? currentPost.artist : '';
    who.hidden = mode !== 'year';

    // Кнопки строим через DOM, а не склейкой HTML: имя художника с кавычкой
    // или угловой скобкой раньше ломало разметку и обработчик клика.
    const answersDiv = document.getElementById('quiz-answers');
    answersDiv.textContent = '';
    options.forEach(label => {{
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'quiz-btn';
        b.textContent = label;
        b.addEventListener('click', function() {{ checkAnswer(b, label); }});
        answersDiv.appendChild(b);
    }});
}}

function checkAnswer(btn, answer) {{
    if (btn.disabled) return;
    total++;

    const correct = answer === correctLabel;
    const allBtns = document.querySelectorAll('.quiz-btn');
    allBtns.forEach(b => b.disabled = true);

    const feedback = document.getElementById('quiz-feedback');
    feedback.textContent = '';
    const when = currentPost.d ? ' Написана: ' + currentPost.d + '.' : '';
    if (correct) {{
        score++;
        btn.classList.add('correct');
        feedback.appendChild(document.createTextNode('✓ Правильно!' + (mode === 'year' ? when : '') + ' '));
    }} else {{
        btn.classList.add('wrong');
        allBtns.forEach(b => {{ if (b.textContent === correctLabel) b.classList.add('correct'); }});
        feedback.appendChild(document.createTextNode(mode === 'year'
            ? '✗ Неправильно, это ' + correctLabel + '.' + when + ' '
            : '✗ Неправильно. Правильный ответ: ' + currentPost.artist + '. '));
    }}
    showScore();
    const link = document.createElement('a');
    link.href = currentPost.filename;
    link.className = 'quiz-link';
    link.textContent = 'Посмотреть картину';
    feedback.appendChild(link);

    saveProgress();
    document.getElementById('quiz-next').style.display = 'inline-block';
    document.getElementById('quiz-next').focus();
}}

function resetScore() {{
    score = 0;
    total = 0;
    showScore();
    document.getElementById('quiz-feedback').textContent = '';
    try {{ localStorage.removeItem(MODES[mode].key); }} catch (e) {{}}
}}

function startNewGame() {{
    resetScore();
    newQuestion();
}}

// «Сбросить счёт» обнуляет счёт, но оставляет игру идти.
// Раньше кнопка стирала картинку и варианты и оставляла пустой экран,
// с которого можно было выйти только через «Новую игру».
function resetQuiz() {{
    resetScore();
    newQuestion();
}}

function setMode(m) {{
    if (!MODES[m]) return;
    mode = m;
    try {{ localStorage.setItem('quizMode', m); }} catch (e) {{}}
    if (location.hash !== '#' + m && history.replaceState) history.replaceState(null, '', '#' + m);
    document.getElementById('quiz-heading').textContent = MODES[m].heading;
    document.querySelectorAll('.quiz-modes [data-mode]').forEach(b =>
        b.setAttribute('aria-pressed', b.getAttribute('data-mode') === m ? 'true' : 'false'));
    loadProgress();
    newQuestion();
}}

document.querySelector('.quiz-modes').addEventListener('click', function(e) {{
    const m = e.target.getAttribute && e.target.getAttribute('data-mode');
    if (m && m !== mode) setMode(m);
}});
window.addEventListener('hashchange', function() {{
    const h = location.hash.replace('#', '');
    if (MODES[h] && h !== mode) setMode(h);
}});

setMode(mode);
</script>
</body></html>"""
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "quiz.html")
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    
    print(f"Квиз сохранён: {output_path}")

if __name__ == "__main__":
    generate_quiz_page()