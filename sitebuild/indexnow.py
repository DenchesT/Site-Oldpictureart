# -*- coding: utf-8 -*-
"""IndexNow: уведомление поисковиков о страницах, изменённых после публикации.

Адреса направляются каждому endpoint в пачках не более MAX_URLS.
При частичном отказе сохраняется весь набор для повторной попытки.
Повторные заявки допустимы по протоколу IndexNow.
"""

from html import unescape
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
from .safety import atomic_json

logger = logging.getLogger("build_site")

INDEXNOW_KEY = "607fce3d40984930b74b3e6e2ddd26cc"
ENDPOINTS = ("https://yandex.com/indexnow", "https://api.indexnow.org/indexnow")
PENDING_FILE = "indexnow_pending.json"
MAX_URLS = 10000
DEPLOY_WAIT = 180
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
    """Создать публичный ключ проверки владельца IndexNow."""
    path = os.path.join(out_dir or OUTPUT_DIR, key_file_name(key))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        with open(path, encoding="utf-8") as stream:
            if stream.read() == key:
                return path
    except OSError:
        pass
    with open(path, "w", encoding="utf-8", newline="") as stream:
        stream.write(key)
    return path


def sitemap_urls(out_dir=None):
    """Адреса из локальной sitemap.xml; XML-сущности декодируются."""
    try:
        with open(os.path.join(out_dir or OUTPUT_DIR, "sitemap.xml"), encoding="utf-8") as stream:
            return {unescape(value) for value in re.findall(r"<loc>([^<]+)</loc>", stream.read())}
    except OSError:
        return set()


def page_url(path, out_dir=None, base=BASE_URL):
    """docs/x.html -> https://сайт/x.html; docs/index.html -> / ."""
    out = (out_dir or OUTPUT_DIR).replace("\\", "/").rstrip("/") + "/"
    path = path.replace("\\", "/")
    if not path.startswith(out):
        return None
    rel = path[len(out):]
    if rel == "index.html":
        return base.rstrip("/") + "/"
    return base.rstrip("/") + "/" + urllib.parse.quote(rel, safe="/")


def changed_files(commits=1, run=subprocess.run):
    """Добавленные/изменённые в последних N коммитах файлы."""
    r = run(["git", "-c", "core.quotepath=false", "diff", "--name-only", "--diff-filter=AMR",
             f"HEAD~{int(commits)}", "HEAD"],
            capture_output=True, text=True, encoding="utf-8")
    if getattr(r, "returncode", 1):
        return []
    return [line.strip().strip('"') for line in r.stdout.splitlines() if line.strip()]


def urls_to_send(files, out_dir=None, base=BASE_URL):
    """Адреса затронутых файлов, включённые в sitemap.xml."""
    known = sitemap_urls(out_dir)
    urls = []
    seen = set()
    for filename in files:
        url = page_url(filename, out_dir, base)
        if url and url in known and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def load_pending(path=PENDING_FILE):
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        return [u for u in data if isinstance(u, str)] if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def save_pending(urls, path=PENDING_FILE):
    """Сохранить очередь атомарно, чтобы сбой процесса не обнулил файл."""
    if not urls:
        if os.path.exists(path):
            os.remove(path)
        return
    atomic_json(path, list(urls), backup=False)


def _post(url, body, timeout=30):
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "User-Agent": "oldpictureart-build"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def submit(urls, key=INDEXNOW_KEY, base=BASE_URL, endpoints=ENDPOINTS,
           post=_post, log=logger.info):
    """Отправить все URL в каждый endpoint; True только при полном успехе.

    Более MAX_URLS делятся на отдельные HTTP-запросы, без потери хвоста.
    Частичный отказ оставляет очередь на следующий запуск. Повторная
    отправка адресов безопасна: IndexNow допускает повторные уведомления.
    """
    if not urls:
        return True
    if not endpoints:
        return False
    host = urllib.parse.urlsplit(base).netloc
    success = True
    for start in range(0, len(urls), MAX_URLS):
        chunk = urls[start:start + MAX_URLS]
        body = json.dumps({
            "host": host, "key": key,
            "keyLocation": f"{base.rstrip('/')}/{key_file_name(key)}",
            "urlList": chunk,
        }, ensure_ascii=False).encode("utf-8")
        batch = (start // MAX_URLS) + 1
        for endpoint in endpoints:
            name = urllib.parse.urlsplit(endpoint).netloc
            try:
                code = post(endpoint, body)
            except Exception as exc:
                log(f"IndexNow: {name}, партия {batch} — нет ответа ({exc.__class__.__name__})")
                success = False
                continue
            log(f"IndexNow: {name}, партия {batch} — {code}, {ANSWERS.get(code, 'неожиданный ответ')}")
            if code not in (200, 202):
                success = False
    return success


def wait_for_deploy(url, local_path, timeout=DEPLOY_WAIT, every=10,
                    fetch=None, sleep=time.sleep, now=time.monotonic):
    """Ожидать, пока публичная страница совпадёт с локальным файлом."""
    try:
        with open(local_path, "rb") as stream:
            want = stream.read()
    except OSError:
        return False

    def default_fetch(address):
        sep = "&" if "?" in address else "?"
        req = urllib.request.Request(
            f"{address}{sep}nocache={int(time.time())}",
            headers={"User-Agent": "oldpictureart-build", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read()

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
    """Отправить изменённые страницы плюс очередь предыдущих запусков."""
    out_dir = out_dir or OUTPUT_DIR
    fresh = urls_to_send(files, out_dir)
    pending = load_pending()
    urls = list(dict.fromkeys(fresh + pending))
    if not urls:
        return True
    log(f"IndexNow: страниц — {len(urls)}" +
        (f" (из них ждали с прошлого раза — {len(pending)})" if pending else ""))
    if wait and fresh:
        probe = next((filename for filename in files
                      if page_url(filename, out_dir) == fresh[0]), None)
        if probe and not wait_for_deploy(fresh[0], probe):
            log("IndexNow: GitHub Pages ещё выкладывает сайт — поисковик может прийти раньше")
    ok = submit(urls, log=log)
    save_pending([] if ok else urls)
    if not ok:
        log(f"IndexNow: неполная отправка, адреса сохранены в {PENDING_FILE}")
    return ok


def notify_commits(commits=1, log=logger.info):
    """Отправить адреса из последних N коммитов без ожидания деплоя."""
    return notify(changed_files(commits), wait=False, log=log)


__all__ = [
    'INDEXNOW_KEY', 'ENDPOINTS', 'PENDING_FILE', 'MAX_URLS', 'DEPLOY_WAIT',
    'ANSWERS', 'key_file_name', 'generate_key_file', 'sitemap_urls', 'page_url',
    'changed_files', 'urls_to_send', 'load_pending', 'save_pending', 'submit',
    'wait_for_deploy', 'notify', 'notify_commits',
]
