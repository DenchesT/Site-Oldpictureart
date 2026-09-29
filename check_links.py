# -*- coding: utf-8 -*-
"""
Проверка внешних ссылок сайта: источники картин, ссылки походов, сайты музеев.

Зачем: страницы выставок в архивах музеев переезжают, карточки в онлайн-
собраниях меняют адреса, домены истекают. Сайт при этом ничего не знает —
ссылка тихо превращается в «страница не найдена» у посетителя. Здесь все
ссылки проверяются разом тем же правилом, что и сайты музеев на карте
(generate_map.py --check):

  ✗ не работает  — 404, нет такого домена, сертификат на чужое имя,
                   переезд на другой домен;
  ? проверить не вышло — 403/429 (сайт не пускает робота), долгий ответ,
                   сертификат Минцифры: в браузере такие обычно открываются.

Запуск:
    python check_links.py            # всё: посты, походы, сайты музеев
    python check_links.py --posts    # только ссылки из постов

Ссылка из поста правится в самом канале, а на сайт притягивается так:
    python build_site.py --refresh <страница или номер поста>
Сайт музея — поле "site" в museum_overrides.json.
"""

import json
import os
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

META_FILE = "posts_meta.json"
VISITS_FILE = "visits_meta.json"
OVERRIDES_FILE = "museum_overrides.json"


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def collect(posts, visits, overrides=None, clean=lambda u: u):
    """{адрес: [(где стоит, подпись)]}.

    Один адрес может стоять на нескольких страницах — проверяется он один
    раз, а в отчёте видно, где его править. Метки слежения (ysclid, utm_…)
    снимаются до проверки: страницы с ними и без них — одна страница.
    """
    found = {}

    def add(url, where, label):
        url = clean((url or "").strip())
        if not url.lower().startswith(("http://", "https://")):
            return
        places = found.setdefault(url, [])
        if (where, label) not in places:
            places.append((where, label))

    for p in posts:
        label = " — ".join(x for x in (p.get("artist"), p.get("title")) if x)
        for u in p.get("urls") or []:
            add(u, p.get("filename", "?"), label)
        for ln in p.get("links") or []:
            add(ln.get("url"), p.get("filename", "?"), label)
    for v in visits:
        label = (v.get("title") or v.get("place") or "поход").strip()
        for u in v.get("urls") or []:
            add(u, v.get("filename", "?"), label)
        for ln in v.get("links") or []:
            add(ln.get("url"), v.get("filename", "?"), label)
    for name, rec in (overrides or {}).items():
        if name.startswith("_") or not isinstance(rec, dict):
            continue
        if rec.get("site"):
            add(rec["site"], OVERRIDES_FILE, name)
    return found


def interleave(urls):
    """Адреса вперемешку по сайтам: десять ссылок на один музей подряд,
    да ещё разом в восемь потоков, — верный способ получить от него
    «429 слишком много запросов» вместо ответа."""
    by_host = {}
    for u in urls:
        by_host.setdefault(urllib.parse.urlsplit(u).netloc.lower(), []).append(u)
    queues = list(by_host.values())
    out = []
    while queues:
        out += [q.pop(0) for q in queues]
        queues = [q for q in queues if q]
    return out


def check_all(urls, check, workers=8):
    """{адрес: (состояние, пояснение)}. Несколько проверок разом: сайты
    разные, и по очереди полторы сотни ссылок шли бы минут десять."""
    urls = interleave(urls)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(urls, pool.map(check, urls)))


def report(found, results, out=print):
    """Печатает отчёт. Возвращает число нерабочих ссылок."""
    bad = sorted(u for u, (state, _) in results.items() if state == "bad")
    unclear = sorted(u for u, (state, _) in results.items() if state == "unknown")
    good = sum(1 for state, _ in results.values() if state == "ok")

    out(f"\nПроверено ссылок: {len(results)} — работают {good}, "
        f"не работают {len(bad)}, проверить не вышло {len(unclear)}")

    if bad:
        out(f"\nНе работают ({len(bad)}) — это надо поправить:")
        for u in bad:
            out(f"  ✗ {u}\n      {results[u][1]}")
            for where, label in found.get(u, []):
                out(f"      на странице: {where}" + (f" ({label})" if label else ""))
        posts_bad = any(where != OVERRIDES_FILE for u in bad for where, _ in found.get(u, []))
        if posts_bad:
            out("\n  Ссылку из поста правят в канале, а на сайт притягивают так:\n"
                "      python build_site.py --refresh <страница из списка выше>")
        if any(where == OVERRIDES_FILE for u in bad for where, _ in found.get(u, [])):
            out(f'  Сайт музея — поле "site" в {OVERRIDES_FILE}.')
    if unclear:
        out(f"\nПроверить не вышло ({len(unclear)}) — скорее всего, в порядке, "
            "загляните глазами:")
        for u in unclear:
            out(f"  ? {u}\n      {results[u][1]}")
    if not bad:
        out("\nНерабочих ссылок нет.")
    return len(bad)


def main():
    posts_only = "--posts" in sys.argv
    posts = load(META_FILE, [])
    visits = load(VISITS_FILE, [])
    overrides = {} if posts_only else load(OVERRIDES_FILE, {})

    # Правила проверки и чистки — общие с картой и сборкой, чтобы «не
    # работает» здесь значило ровно то же, что в generate_map.py --check.
    from generate_map import check_site
    from build_site import clean_url

    found = collect(posts, visits, overrides, clean=clean_url)
    from_posts = sum(1 for places in found.values() if any(w != OVERRIDES_FILE for w, _ in places))
    print(f"Ссылок из постов и походов: {from_posts}"
          + ("" if posts_only else f", сайтов музеев: {len(found) - from_posts}"))
    print("Проверяю…")
    results = check_all(found, check_site)
    return 1 if report(found, results) else 0


if __name__ == "__main__":
    sys.exit(main())
