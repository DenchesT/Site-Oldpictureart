# -*- coding: utf-8 -*-
"""IndexNow — сообщить поисковикам, какие страницы появились или изменились.

Без него Яндекс узнаёт о новой картине, когда сам заглянет в карту сайта, —
через дни, а то и недели. С IndexNow сборка после push говорит ему сразу:
вот эти адреса новые или поменялись.

Как устроено:
  • ключ — INDEXNOW_KEY ниже; он не секрет, а подтверждение, что сайт
    ваш: файл docs/<ключ>.txt с тем же ключом сборка кладёт в корень сайта;
  • после push сборка берёт из коммита изменённые страницы и оставляет те,
    что есть в карте сайта (служебные — 404, вход, перенаправления — туда
    не входят), ждёт, пока GitHub Pages выложит новую версию, и отправляет
    список Яндексу и в общий IndexNow (оттуда его берут Bing и другие);
  • не получилось (нет сети, сервер не ответил) — адреса ждут в
    indexnow_pending.json и уйдут со следующей сборкой.

Вручную, например после push без build_site.py:
    python build_site.py --indexnow           страницы из последнего коммита
    python build_site.py --indexnow 3         из трёх последних коммитов
"""

import json
import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from site_common import BASE_URL
from .config import OUTPUT_DIR

logger = logging.getLogger("build_site")

INDEXNOW_KEY = "607fce3d40984930b74b3e6e2ddd26cc"
ENDPOINTS = ("https://yandex.com/indexnow", "https://api.indexnow.org/indexnow")
PENDING_FILE = "indexnow_pending.json"
MAX_URLS = 10000                 # больше за раз IndexNow не принимает
DEPLOY_WAIT = 180                # сколько ждать, пока GitHub Pages выложит сайт, с
ANSWERS = {
    200: "приняты",
    202: "приняты, ключ ещё проверяется",
    400: "неверный запрос",
    403: f"ключ не подошёл — открывается ли {BASE_URL}/{INDEXNOW_KEY}.txt?",
    422: "адреса не с этого сайта или ключ не тот",
    429: "слишком часто — отправлю в следующий раз",
}


def key_file_name(key=INDEXNOW_KEY):
    return f"{key}.txt"


def generate_key_file(out_dir=None, key=INDEXNOW_KEY):
    """docs/<ключ>.txt — по нему поисковик проверяет, что сайт ваш."""
    path = os.path.join(out_dir or OUTPUT_DIR, key_file_name(key))
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == key:
                return path
    except OSError:
        pass
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(key)
    return path


def sitemap_urls(out_dir=None):
    """Адреса из docs/sitemap.xml — только их и есть смысл отправлять."""
    try:
        with open(os.path.join(out_dir or OUTPUT_DIR, "sitemap.xml"), encoding="utf-8") as f:
            return set(re.findall(r"<loc>([^<]+)</loc>", f.read()))
    except OSError:
        return set()


def page_url(path, out_dir=None, base=BASE_URL):
    """docs/x.html → https://сайт/x.html; docs/index.html → https://сайт/."""
    out = (out_dir or OUTPUT_DIR).replace("\\", "/").rstrip("/") + "/"
    path = path.replace("\\", "/")
    if not path.startswith(out):
        return None
    rel = path[len(out):]
    if rel == "index.html":
        return base + "/"
    return base + "/" + urllib.parse.quote(rel, safe="/")


def changed_files(commits=1, run=subprocess.run):
    """Файлы, добавленные или изменённые последними commits коммитами."""
    r = run(["git", "-c", "core.quotepath=false", "diff", "--name-only", "--diff-filter=AMR",
             f"HEAD~{int(commits)}", "HEAD"],
            capture_output=True, text=True, encoding="utf-8")
    if getattr(r, "returncode", 1):
        return []
    return [line.strip().strip('"') for line in r.stdout.splitlines() if line.strip()]


def urls_to_send(files, out_dir=None, base=BASE_URL):
    """Изменённые файлы → адреса, которые есть в карте сайта."""
    known = sitemap_urls(out_dir)
    urls = []
    for f in files:
        u = page_url(f, out_dir, base)
        if u and u in known and u not in urls:
            urls.append(u)
    return urls


def load_pending(path=PENDING_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [u for u in data if isinstance(u, str)] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_pending(urls, path=PENDING_FILE):
    if not urls:
        if os.path.exists(path):
            os.remove(path)
        return
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(urls, f, ensure_ascii=False, indent=1)


def _post(url, body, timeout=30):
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "User-Agent": "oldpictureart-build"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def submit(urls, key=INDEXNOW_KEY, base=BASE_URL, endpoints=ENDPOINTS, post=_post, log=logger.info):
    """Отправляет адреса. True — хоть один поисковик их принял."""
    if not urls:
        return True
    host = urllib.parse.urlsplit(base).netloc
    body = json.dumps({"host": host, "key": key,
                       "keyLocation": f"{base}/{key_file_name(key)}",
                       "urlList": urls[:MAX_URLS]}, ensure_ascii=False).encode("utf-8")
    accepted = False
    for ep in endpoints:
        name = urllib.parse.urlsplit(ep).netloc
        try:
            code = post(ep, body)
        except Exception as e:                          # нет сети, таймаут
            log(f"IndexNow: {name} не ответил ({e.__class__.__name__})")
            continue
        log(f"IndexNow: {name} — {code}, {ANSWERS.get(code, 'неожиданный ответ')}")
        accepted = accepted or code in (200, 202)
    return accepted


def wait_for_deploy(url, local_path, timeout=DEPLOY_WAIT, every=10, fetch=None, sleep=time.sleep, now=time.monotonic):
    """Ждёт, пока GitHub Pages отдаст по url то же, что лежит в local_path.

    Иначе поисковик мог бы прийти раньше выкладки и увидеть прежнюю версию.
    True — дождались, False — вышло время (адреса всё равно отправляются).
    """
    try:
        with open(local_path, "rb") as f:
            want = f.read()
    except OSError:
        return False

    def default_fetch(u):
        sep = "&" if "?" in u else "?"
        req = urllib.request.Request(f"{u}{sep}nocache={int(time.time())}",
                                     headers={"User-Agent": "oldpictureart-build", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()

    fetch = fetch or default_fetch
    end = now() + timeout
    while True:
        try:
            if fetch(url) == want:
                return True
        except Exception:
            pass
        if now() >= end:
            return False
        sleep(every)


def notify(files, out_dir=None, wait=True, log=logger.info):
    """Изменённые файлы (и ждавшие с прошлого раза) → поисковикам."""
    out_dir = out_dir or OUTPUT_DIR
    fresh = urls_to_send(files, out_dir)
    pending = load_pending()
    urls = list(dict.fromkeys(fresh + pending))
    if not urls:
        return True
    log(f"IndexNow: страниц — {len(urls)}" + (f" (из них ждали с прошлого раза — {len(pending)})" if pending else ""))
    if wait and fresh:
        # Проверяем по одной странице: выложилась она — выложилось всё.
        probe = next((f for f in files if page_url(f, out_dir) == fresh[0]), None)
        if probe and not wait_for_deploy(fresh[0], probe):
            log("IndexNow: GitHub Pages ещё выкладывает сайт — отправляю, поисковик придёт чуть позже")
    ok = submit(urls, log=log)
    save_pending([] if ok else urls)
    if not ok:
        log(f"IndexNow: адреса сохранены в {PENDING_FILE} — уйдут со следующей сборкой")
    return ok


def notify_commits(commits=1, log=logger.info):
    """python build_site.py --indexnow [N] — страницы из последних N коммитов."""
    files = changed_files(commits)
    return notify(files, wait=False, log=log)


__all__ = [
    'INDEXNOW_KEY', 'ENDPOINTS', 'PENDING_FILE', 'MAX_URLS', 'DEPLOY_WAIT', 'ANSWERS', 'key_file_name',
    'generate_key_file', 'sitemap_urls', 'page_url', 'changed_files', 'urls_to_send', 'load_pending',
    'save_pending', 'submit', 'wait_for_deploy', 'notify', 'notify_commits',
]
