# -*- coding: utf-8 -*-
"""Ссылки из публикаций Telegram: сопоставление, проверка и безопасный HTML."""

from html import escape as h
import re
import urllib.parse


def _link_key(text):
    """Нормализует подпись ссылки для сопоставления с полем поста."""
    t = (text or "").lower().replace("ё", "е")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def link_for(field, links, used=()):
    """Индекс лучшей незанятой ссылки для названия, либо None."""
    f = _link_key(field)
    if not f:
        return None
    best, score = None, None
    for i, ln in enumerate(links or []):
        if i in used or not isinstance(ln, dict):
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
        candidate_score = (s, len(k))
        if score is None or candidate_score > score:
            best, score = i, candidate_score
    return best


def _http_url(url):
    """Только полноценные HTTP(S)-адреса без управляющих символов.

    Возвращает пустую строку для недоверенных/некорректных адресов.
    Не разрешает ``javascript:``, ``data:``, ``//host`` и ``file:``.
    """
    if not isinstance(url, str):
        return ""
    if any(ord(c) < 32 or ord(c) == 127 for c in url):
        return ""
    value = url.strip()
    try:
        parsed = urllib.parse.urlsplit(value)
        if (parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc
                or not parsed.hostname or parsed.username or parsed.password):
            return ""
        # Проверка некорректных портов (urlsplit не всегда проверяет сразу).
        _ = parsed.port
    except (ValueError, TypeError):
        return ""
    return value


def ext_link(text, url):
    """Внешняя ссылка; недопустимый URL отображается как обычный текст."""
    safe = _http_url(url)
    if not safe:
        return h(str(text or ""))
    return (f'<a href="{h(safe, quote=True)}" class="ext-link" '
            f'target="_blank" rel="noopener" title="{h(safe, quote=True)}">'
            f'{h(str(text or ""))}</a>')


def source_items(links, urls, used=()):
    """Уникальные валидные внешние ссылки: подписанные, затем без подписи."""
    seen, items = set(), []
    for i, ln in enumerate(links or []):
        if i in used or not isinstance(ln, dict):
            continue
        u = _http_url(ln.get("url"))
        if not u:
            continue
        u = clean_url(u)
        if u in seen:
            continue
        seen.add(u)
        items.append((ln.get("text") or u, u))
    for raw in urls or []:
        u = _http_url(raw)
        if not u:
            continue
        u = clean_url(u)
        if u not in seen:
            seen.add(u)
            items.append((u, u))
    return items


def source_block(items, words=("Источник", "Источники")):
    """Безопасный HTML-блок источников; число источников по отфильтрованным URL."""
    valid = [(str(text or url), u) for text, url in (items or [])
             if (u := _http_url(url))]
    if not valid:
        return ""
    its = "".join(f'<li><a href="{h(u, quote=True)}" target="_blank" '
                  f'rel="noopener">{h(t)}</a></li>' for t, u in valid)
    word = words[0] if len(valid) == 1 else words[1]
    return f'<div class="aside-block"><h3>{h(word)}</h3><ul class="source-list">{its}</ul></div>'


TRACKING_PARAMS = re.compile(
    r"^(?:ysclid|yclid|fbclid|gclid|dclid|msclkid|_openstat|"
    r"mc_cid|mc_eid|utm_[a-z0-9_]+)$", re.I
)


def clean_url(url):
    """Удаляет распространённые tracking-параметры, не меняя остальные."""
    try:
        parts = urllib.parse.urlsplit(url or "")
    except (TypeError, ValueError):
        return url
    if not parts.query:
        return url
    pieces = parts.query.split("&")
    kept = [part for part in pieces
            if not TRACKING_PARAMS.fullmatch(part.split("=", 1)[0])]
    if len(kept) == len(pieces):
        return url
    return urllib.parse.urlunsplit(parts._replace(query="&".join(kept)))


def clean_links(links):
    """Валидирует и очищает сохранённые ссылки старых записей."""
    result = []
    for ln in links or []:
        if not isinstance(ln, dict):
            continue
        safe = _http_url(ln.get("url"))
        if safe:
            result.append(dict(ln, url=clean_url(safe)))
    return result


__all__ = [
    '_link_key', 'link_for', 'ext_link', 'source_items', 'source_block',
    'TRACKING_PARAMS', 'clean_url', 'clean_links',
]
