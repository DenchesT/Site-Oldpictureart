# -*- coding: utf-8 -*-
"""Ссылки из постов: чистка меток слежения и подстановка ссылок в названия.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import re
import urllib.parse
from html import escape as h

def _link_key(text):
    """Название для сравнения со ссылкой: без регистра, кавычек, эмодзи и
    лишних пробелов. «Выставка "Сокровищница графики"» и «Сокровищница
    графики 🖼» должны узнавать друг друга."""
    t = (text or "").lower().replace("ё", "е")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def link_for(field, links, used=()):
    """Номер ссылки из поста, которая стоит на этом названии, или None.

    Ссылку в канале ставят по-разному: на всю строку «Выставка "…"», на
    одно название или на его часть. Поэтому узнаём и так, и так, но
    совсем короткие подписи (меньше четырёх букв) не берём — «им.» или
    «ГМ» совпали бы с чем угодно. Из нескольких подходящих берётся самая
    точная, а уже занятая другим названием второй раз не используется.
    """
    f = _link_key(field)
    if not f:
        return None
    best, score = None, None
    for i, ln in enumerate(links or []):
        if i in used:
            continue
        k = _link_key(ln.get("text"))
        if not k or (len(k) < 4 and k != f):
            continue
        if k == f:
            s = 3
        elif f in k:
            s = 2
        elif k in f:
            s = 1
        else:
            continue
        if score is None or (s, len(k)) > score:
            best, score = i, (s, len(k))
    return best


def ext_link(text, url):
    """Название, под которым лежит внешняя ссылка из поста."""
    return (f'<a href="{h(url)}" class="ext-link" target="_blank" rel="noopener" '
            f'title="{h(url)}">{h(text)}</a>')


def source_items(links, urls, used=()):
    """Строки блока ссылок: сперва подписанные из поста, потом голые
    адреса. Один и тот же адрес — один раз."""
    seen, items = set(), []
    for i, ln in enumerate(links or []):
        u = ln.get("url")
        if i in used or not u or u in seen:
            continue
        seen.add(u)
        items.append((ln.get("text") or u, u))
    for u in urls or []:
        if u and u not in seen:
            seen.add(u)
            items.append((u, u))
    return items


def source_block(items, words=("Источник", "Источники")):
    """Блок ссылок в правой колонке: заголовок в числе по количеству."""
    if not items:
        return ""
    its = "".join(f'<li><a href="{h(u)}" target="_blank" rel="noopener">{h(t)}</a></li>'
                  for t, u in items)
    word = words[0] if len(items) == 1 else words[1]
    return f'<div class="aside-block"><h3>{word}</h3><ul class="source-list">{its}</ul></div>'


# ======================================================================
#                   ССЫЛКИ В ТЕКСТЕ ПОСТА
# ======================================================================
#
# В постах о походах название выставки или музея — ссылка: «Сокровищница
# графики» ведёт на страницу выставки, «ГМИИ им. А.С. Пушкина» — на сайт
# музея. В тексте поста (raw_text) их не видно: Телеграм хранит ссылки не
# в тексте, а разметкой поверх него, и сайт их до сих пор просто терял.
# Теперь разметка читается, и у записи появляется поле links:
#     [{"text": "Сокровищница графики", "url": "https://…"}, …]
# У прежних записей его нет — сборка дочитывает его один раз сама.


# Метки, которые браузер дописывает к ссылке сам: ysclid — Яндекс,
# utm_* — рекламные, fbclid/gclid/yclid — счётчики переходов. К адресу
# выставки они отношения не имеют, а в ссылке с сайта выглядят мусором.
TRACKING_PARAMS = re.compile(r"^(ysclid|yclid|fbclid|gclid|_openstat|utm_[a-z]+)$", re.I)


def clean_url(url):
    """Адрес без меток слежения; всё остальное — как было."""
    try:
        parts = urllib.parse.urlsplit(url or "")
    except ValueError:
        return url
    if not parts.query:
        return url
    # Режем по сырым кускам «ключ=значение», не раскодируя: остальной
    # адрес должен остаться буква в букву, как его поставили в посте.
    pieces = parts.query.split("&")
    kept = [x for x in pieces if not TRACKING_PARAMS.match(x.split("=", 1)[0])]
    if len(kept) == len(pieces):
        return url
    return urllib.parse.urlunsplit(parts._replace(query="&".join(kept)))


def clean_links(links):
    """Ссылки записи с вычищенными метками — для старых записей, где они
    остались с тех времён, когда их никто не чистил."""
    return [dict(ln, url=clean_url(ln.get("url", ""))) for ln in (links or []) if ln.get("url")]

__all__ = [
    '_link_key',
    'link_for',
    'ext_link',
    'source_items',
    'source_block',
    'TRACKING_PARAMS',
    'clean_url',
    'clean_links',
]
