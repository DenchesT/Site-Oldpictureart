# -*- coding: utf-8 -*-
"""IndexNow: после push сборка сообщает поисковикам о новых страницах.

  • ключ подходит под правила IndexNow, файл docs/<ключ>.txt лежит на месте
    и содержит ровно ключ;
  • отправляются только страницы из карты сайта: 404, перенаправления,
    данные и картинки — нет;
  • запрос — такой, как просит Яндекс: host, key, keyLocation, urlList;
  • 200 и 202 — приняли; 403, 429, нет сети — адреса ждут следующей сборки
    в indexnow_pending.json и уходят вместе с новыми;
  • перед отправкой сборка ждёт, пока GitHub Pages выложит новую версию.

Запуск:  python tests/test_indexnow.py
"""

import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.argv = ["build_site.py"]

import build_site as bs  # noqa: E402
from sitebuild import indexnow as ix  # noqa: E402

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


KEY = ix.INDEXNOW_KEY
BASE = "https://oldpictureart.ru"
ok("ключ по правилам IndexNow (8–128 символов: латиница, цифры, дефис)",
   re.fullmatch(r"[A-Za-z0-9-]{8,128}", KEY), KEY)
live = os.path.join("docs", KEY + ".txt")
ok("файл ключа в docs/ лежит на месте", os.path.isfile(live))
ok("…и в нём ровно ключ, без перевода строки", os.path.isfile(live) and open(live, encoding="utf-8").read() == KEY)
robots = open("docs/robots.txt", encoding="utf-8").read() if os.path.exists("docs/robots.txt") else ""
ok("robots.txt не закрывает файл ключа", f"Disallow: /{KEY}" not in robots and "Disallow: /\n" not in robots + "\n")

tmp = tempfile.mkdtemp()
old_cwd = os.getcwd()
try:
    os.chdir(tmp)
    out = os.path.join(tmp, "docs")
    os.makedirs(out)
    path = ix.generate_key_file(out)
    ok("generate_key_file пишет docs/<ключ>.txt", open(path, encoding="utf-8").read() == KEY
       and os.path.basename(path) == KEY + ".txt")

    with open(os.path.join(out, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("<urlset>"
                f"<url><loc>{BASE}/</loc></url>"
                f"<url><loc>{BASE}/levitan-mart-1895.html</loc></url>"
                f"<url><loc>{BASE}/feed.xml</loc></url>"
                f"<url><loc>{BASE}/museum-ermitazh.html</loc></url>"
                "</urlset>")
    files = ["docs/index.html", "docs/levitan-mart-1895.html", "docs/404.html", "docs/feed.xml",
             "docs/old-cyrillic-page.html", "docs/images/levitan.jpg", "posts_meta.json",
             "docs/museum-ermitazh.html", "sitebuild/posts.py"]
    urls = ix.urls_to_send(files, "docs", BASE)
    ok("главная — адрес сайта со слешем", f"{BASE}/" in urls, str(urls))
    ok("страница картины и лента — отправляются", f"{BASE}/levitan-mart-1895.html" in urls and f"{BASE}/feed.xml" in urls)
    ok("страница музея — отправляется", f"{BASE}/museum-ermitazh.html" in urls)
    ok("404, перенаправления, картинки, данные, код — нет", len(urls) == 4, str(urls))
    ok("адрес не из docs/ — не страница", ix.page_url("posts_meta.json", "docs", BASE) is None)

    class R:
        def __init__(self, code, out=""):
            self.returncode, self.stdout = code, out
    seen = []
    got = ix.changed_files(2, run=lambda cmd, **kw: seen.append(cmd) or R(0, "docs/a.html\ndocs/b.html\n"))
    ok("изменённые файлы берутся из git за N коммитов", got == ["docs/a.html", "docs/b.html"]
       and "HEAD~2" in seen[0] and "--diff-filter=AMR" in seen[0], str(seen))
    ok("git не сработал — список пуст", ix.changed_files(1, run=lambda cmd, **kw: R(128)) == [])

    # ---------- запрос ----------
    sent = []

    def post_200(url, body):
        sent.append((url, json.loads(body.decode("utf-8"))))
        return 200
    logs = []
    ok("200 — адреса приняты", ix.submit(urls, base=BASE, post=post_200, log=logs.append))
    endpoints = [u for u, _ in sent]
    ok("отправка — Яндексу и в общий IndexNow", any("yandex" in u for u in endpoints)
       and any("indexnow.org" in u for u in endpoints), str(endpoints))
    body = sent[0][1]
    ok("в запросе host, key, keyLocation и urlList", body.get("host") == "oldpictureart.ru" and body.get("key") == KEY
       and body.get("keyLocation") == f"{BASE}/{KEY}.txt" and body.get("urlList") == urls, str(body))
    ok("в журнале — что ответил поисковик", any("200" in line and "приняты" in line for line in logs), str(logs))
    ok("202 (ключ ещё проверяется) — тоже принято", ix.submit(urls, base=BASE, post=lambda u, b: 202, log=lambda m: None))
    logs = []
    ok("403 — не принято", not ix.submit(urls, base=BASE, post=lambda u, b: 403, log=logs.append))
    ok("…и в журнале подсказка, что проверить", any(f"{KEY}.txt" in line for line in logs), str(logs))

    def no_net(u, b):
        raise OSError("нет сети")
    ok("нет сети — не падает, просто не принято", not ix.submit(urls, base=BASE, post=no_net, log=lambda m: None))
    ok("пустой список — ничего не отправляет", ix.submit([], post=no_net, log=lambda m: None))

    # ---------- ожидание выкладки ----------
    with open(os.path.join(out, "levitan-mart-1895.html"), "wb") as f:
        f.write(b"<html>new</html>")
    answers = iter([b"<html>old</html>", b"<html>old</html>", b"<html>new</html>"])
    naps = []
    ok("ждёт, пока GitHub Pages отдаст новую версию",
       ix.wait_for_deploy("u", "docs/levitan-mart-1895.html", fetch=lambda u: next(answers), sleep=naps.append,
                          now=lambda: 0) and len(naps) == 2, str(naps))
    clock = iter(range(0, 1000, 10))
    ok("не дождался — сдаётся по таймеру, а не висит",
       not ix.wait_for_deploy("u", "docs/levitan-mart-1895.html", timeout=60, fetch=lambda u: b"old",
                              sleep=lambda s: None, now=lambda: next(clock)))

    # ---------- не вышло — до следующего раза ----------
    real_submit, real_wait = ix.submit, ix.wait_for_deploy
    calls = []
    try:
        ix.wait_for_deploy = lambda *a, **k: True
        ix.submit = lambda u, **k: calls.append(list(u)) or False
        ok("отказ — notify сообщает об этом", not ix.notify(files, out_dir="docs", log=lambda m: None))
        ok("…адреса сохранены в indexnow_pending.json", os.path.exists(ix.PENDING_FILE)
           and json.load(open(ix.PENDING_FILE, encoding="utf-8")) == urls)
        ix.submit = lambda u, **k: calls.append(list(u)) or True
        ok("со следующей сборкой уходят и они, и новые",
           ix.notify(["docs/museum-ermitazh.html"], out_dir="docs", log=lambda m: None)
           and set(calls[-1]) == set(urls) and len(calls[-1]) == len(urls), str(calls[-1]))
        ok("приняли — файл ожидания убран", not os.path.exists(ix.PENDING_FILE))
        n = len(calls)
        ok("нечего отправлять — не отправляет", ix.notify(["sitebuild/x.py"], out_dir="docs") and len(calls) == n)
    finally:
        ix.submit, ix.wait_for_deploy = real_submit, real_wait
finally:
    os.chdir(old_cwd)
    shutil.rmtree(tmp, ignore_errors=True)

# ---------- сборка ----------
src = open("build_site.py", encoding="utf-8").read()
ok("после push сборка зовёт IndexNow", "pushed = push_to_github()" in src and "notify_indexnow(pushed)" in src)
ok("ключ --indexnow — отправить вручную", '"--indexnow" in sys.argv' in src and hasattr(bs, "notify_commits"))
ok("файл ключа пишут и сборка, и пересборка", "generate_key_file()" in src
   and "generate_key_file()" in open("rebuild_pages.py", encoding="utf-8").read())
ok("indexnow_pending.json — не в репозиторий", "indexnow_pending.json" in open(".gitignore", encoding="utf-8").read())

print("\n====== INDEXNOW ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra and not passed else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
