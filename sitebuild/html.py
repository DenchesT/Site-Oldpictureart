# -*- coding: utf-8 -*-
"""Общие помощники страниц: @tidy, заголовки, разметка Schema.org, номера каталога.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
import re
import json
import functools
from site_common import (BASE_URL, TELEGRAM_URL)
from .text import lower_first

# ===================== HTML-ФУНКЦИИ =====================

def tidy(fn):
    """Убирает пробелы в конце строк готовой страницы.

    В шаблонах есть необязательные куски — описание, происхождение,
    «рядом в собрании». Когда такой кусок пуст, от строки остаётся один
    отступ: валидатор считает это ошибкой, а в исходнике страницы это
    выглядит как мусор. Декоратор снимает вопрос на всех страницах сразу.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        html = fn(*args, **kwargs)
        return "\n".join(line.rstrip() for line in html.split("\n"))
    return wrapper


def site_og_image(all_posts):
    """Картинка для превью ссылки на сайт.

    Когда ссылку на главную кидают в мессенджер, превью брала только
    страница работы: у главной, указателя и статистики og:image не было
    вовсе, и ссылка выглядела голым текстом. Берём самую свежую работу —
    превью само обновляется вместе с собранием.
    """
    for post in sorted(all_posts, key=lambda x: x.get("date", ""), reverse=True):
        if post.get("images"):
            return f"{BASE_URL}/{post['images'][0]}"
    return ""


def russian_title(title):
    """Русская часть названия работы, если она есть в скобках.

    Названия хранятся как «Lisière de la forêt de Fontainebleau (Опушка
    леса Фонтенбло), 1865»: сначала оригинал, потом перевод, потом год.
    В заголовке вкладки и в выдаче поисковика полезен перевод — по нему
    и ищут. Скобки бывают вложенными («Бухта на острове Сент-Томас
    (Антильские острова)»), поэтому разбираем их счётчиком, а не regexp.
    """
    best = ""
    depth = 0
    start = -1
    for i, ch in enumerate(title):
        if ch == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                inner = title[start:i]
                if any("а" <= c.lower() <= "я" or c.lower() == "ё" for c in inner):
                    if len(inner) > len(best):
                        best = inner
    return best.strip()


def short_artist(artist, limit=40):
    """Длинный список авторов сворачиваем до первого имени."""
    artist = (artist or "").strip()
    if len(artist) <= limit or "," not in artist:
        return artist
    return artist.split(",")[0].strip() + " и другие"


def page_title(post, limit=70):
    """Заголовок вкладки и выдачи поисковика.

    Полное «художник — название» доходило до 339 знаков и обрезалось
    в выдаче на полуслове у 46 страниц из 81. Берём русское название,
    год и фамилию автора — то, что человек и набирает в поиске.
    """
    title = (post.get("title") or "").strip()
    ru = russian_title(title)
    if ru:
        # год в исходном названии стоит после скобок, вернём его к переводу
        tail = title.rsplit(")", 1)[-1].strip(" ,")
        name = f"{ru}, {tail}" if tail and tail not in ru else ru
    else:
        name = title

    artist = short_artist(post.get("artist", ""))
    full = f"{name} — {artist}" if artist else name
    if len(full) <= limit:
        return full
    room = limit - len(artist) - 3
    if room > 20:
        return f"{name[:room].rsplit(' ', 1)[0]}… — {artist}"
    return full[:limit - 1].rsplit(" ", 1)[0] + "…"


def artwork_jsonld(post):
    """Разметка Schema.org для страницы работы.

    Для каталога живописи есть готовый тип VisualArtwork: он описывает
    автора, год, материал, технику, размер и собрание так, как это
    понимают поисковики. Без него страница для них — просто текст.
    """
    def text(x):
        """Строка, которую нельзя принять за ссылку.

        В словаре Schema.org у artMedium, artworkSurface и unitCode
        допустимы и текст, и URL, поэтому разборщик по умолчанию читает
        значение как адрес: «масло» превращается в ссылку на
        oldpictureart.ru/масло, а «CMT» — в ссылку на oldpictureart.ru/CMT.
        Обёртка {"@value": …} говорит, что это именно текст.
        """
        return {"@value": x}

    data = {
        "@context": "https://schema.org",
        "@type": "VisualArtwork",
        "name": post.get("title", ""),
        "url": f"{BASE_URL}/{post.get('filename', '')}",
        "inLanguage": "ru",
    }
    if post.get("artist"):
        data["creator"] = {"@type": "Person", "name": post["artist"]}
    if post.get("creation_year"):
        data["dateCreated"] = str(post["creation_year"])
    if post.get("techniques"):
        data["artMedium"] = text(", ".join(post["techniques"]))
    if post.get("material"):
        data["artworkSurface"] = text(lower_first(post["material"]))
    if post.get("images"):
        data["image"] = f"{BASE_URL}/{post['images'][0]}"
    if post.get("museum"):
        data["isPartOf"] = {"@type": "Collection", "name": post["museum"]}
    if post.get("description"):
        data["description"] = post["description"][:500]
    if post.get("urls"):
        data["sameAs"] = post["urls"][:3]

    # «105 x 75 см» → высота и ширина отдельными величинами
    m = re.match(r"\s*([\d.,]+)\s*[xх×]\s*([\d.,]+)", post.get("size") or "")
    if m:
        def cm(v):
            return {"@type": "QuantitativeValue", "value": float(v.replace(",", ".")),
                    "unitCode": text("CMT"), "unitText": text("см")}
        data["height"], data["width"] = cm(m.group(1)), cm(m.group(2))

    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


def download_name(post, src):
    """Осмысленное имя файла для скачивания: «Художник — Название, год.jpg».

    Браузер иначе сохранит его как «2025-11-26-исаак-ильич-левитан-hires-1.jpg» —
    в папке «Загрузки» по такому имени работу потом не найти.
    """
    ext = os.path.splitext(src)[1] or ".jpg"
    parts = [post.get("artist", ""), post.get("title", "")]
    name = " — ".join(x.strip() for x in parts if x and x.strip()) or "painting"
    year = post.get("creation_year")
    if year and str(year) not in name:
        name = f"{name}, {year}"
    # символы, которые файловые системы не принимают
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name[:120] or "painting") + ext


def catalogue_numbers(all_posts):
    """Сквозные номера собрания: по году создания, потом по дате записи.

    Номер обязан быть одним и тем же на главной, на теге и на странице
    художника — иначе он перестаёт что-либо обозначать.
    """
    chrono = sorted(all_posts, key=lambda x: (x.get("creation_year") or 9999, x.get("date", "")))
    return ({x["filename"]: i for i, x in enumerate(chrono, 1)},
            max(3, len(str(len(all_posts)))))


def year_span(posts):
    """«1871—1896» или «1896», если год один. Работы без года пропускаем."""
    years = sorted(p["creation_year"] for p in posts if p.get("creation_year"))
    if not years:
        return ""
    return str(years[0]) if years[0] == years[-1] else f"{years[0]}—{years[-1]}"


def jsonld_script(data):
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            + "</script>")

def telegram_post_link(record):
    """Ссылка на сам пост в канале: «Пост в Telegram ↗».

    На странице была только ссылка на канал целиком — найти там пост
    годичной давности было нельзя. Номер сообщения хранится в записи (id).
    """
    msg = record.get("id")
    if not msg:
        return ""
    return (f'<p class="tg-post"><a href="{TELEGRAM_URL}/{int(msg)}" target="_blank" rel="noopener">'
            f'<span class="icon-telegram" aria-hidden="true"></span>Пост в Telegram ↗</a></p>')


__all__ = [
    'telegram_post_link',
    'tidy',
    'site_og_image',
    'russian_title',
    'short_artist',
    'page_title',
    'artwork_jsonld',
    'download_name',
    'catalogue_numbers',
    'year_span',
    'jsonld_script',
]
