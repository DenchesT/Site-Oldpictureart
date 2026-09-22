# -*- coding: utf-8 -*-
"""Функция входа и избранного (cloud/auth/index.py) — без облака и без сети.

Функция живёт в Yandex Cloud, и ошибки в ней видны только там, после
загрузки. Здесь она запускается на месте: Яндекс ID, VK ID и база
подменены, а проверяется то, что может тихо сломаться:
  • чужой или просроченный пропуск не открывает чужие отметки;
  • код входа меняется на пропуск только после ответа Яндекса или VK,
    и только если Яндекс выдал его нашему приложению;
  • запрос с чужого сайта отклоняется, со своего — получает CORS;
  • мусор вместо номеров картин в базу не попадает;
  • запросы к YDB составлены так, как их ждёт база (объявлены все
    параметры, на месте ключ user_id).

Запуск:  python tests/test_auth_function.py
"""

import base64
import importlib.util
import json
import os
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
spec = importlib.util.spec_from_file_location("authfn", os.path.join(ROOT, "cloud", "auth", "index.py"))
fn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fn)

os.environ.update({
    "SESSION_SECRET": "x" * 40,
    "ALLOWED_ORIGINS": "https://oldpictureart.ru",
    "REDIRECT_URI": "https://oldpictureart.ru/auth.html",
    "YANDEX_CLIENT_ID": "ya-app", "YANDEX_CLIENT_SECRET": "ya-secret",
    "VK_CLIENT_ID": "vk-app",
})

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# ------------------------------------------------------------ подмены
class Memory:
    def __init__(self):
        self.rows = {}

    def ping(self):
        return True

    def list(self, user):
        return sorted(self.rows.get(user, set()), key=lambda x: (len(x), x))

    def add(self, user, posts):
        self.rows.setdefault(user, set()).update(posts)

    def remove(self, user, post):
        self.rows.get(user, set()).discard(post)

    def clear(self, user):
        self.rows.pop(user, None)


mem = Memory()
fn._store = mem
calls = []


def fake_http(url, data=None, headers=None):
    calls.append((url, data, headers))
    if url == "https://oauth.yandex.ru/token":
        if data.get("code") == "good" and data.get("client_secret") == "ya-secret":
            return {"access_token": "YA-TOKEN", "token_type": "bearer"}
        if data.get("code") == "alien":
            return {"access_token": "ALIEN-TOKEN"}
        return {"error": "invalid_grant", "error_description": "Code has expired"}
    if url.startswith("https://login.yandex.ru/info"):
        tok = (headers or {}).get("Authorization", "")
        if tok == "OAuth YA-TOKEN":
            return {"id": "1001", "login": "denis", "first_name": "Денис", "client_id": "ya-app"}
        if tok == "OAuth ALIEN-TOKEN":        # пропуск, выданный чужому приложению
            return {"id": "666", "login": "evil", "client_id": "other-app"}
        return {"error": "unauthorized"}
    if url.endswith("/oauth2/auth"):
        if data.get("code") == "vk-good" and data.get("code_verifier") == "V" * 64:
            return {"access_token": "VK-TOKEN", "user_id": 2002, "expires_in": 3600}
        return {"error": "invalid_grant"}
    if url.endswith("/oauth2/user_info"):
        if data.get("access_token") == "VK-TOKEN":
            return {"user": {"user_id": "2002", "first_name": "Анна"}}
        return {"error": "invalid_token"}
    raise AssertionError("неожиданный адрес " + url)


fn.http_json = fake_http


def call(body, origin="https://oldpictureart.ru", b64=False, method="POST"):
    raw = json.dumps(body, ensure_ascii=False)
    if b64:
        raw = base64.b64encode(raw.encode()).decode()
    ev = {"httpMethod": method, "headers": {"Origin": origin} if origin else {},
          "body": raw, "isBase64Encoded": b64}
    r = fn.handler(ev, None)
    try:
        data = json.loads(r["body"]) if r["body"] else {}
    except ValueError:
        data = {}
    return r["statusCode"], data, r.get("headers", {})


# ------------------------------------------------------------ вход
st, d, h = call({"action": "login", "provider": "yandex", "code": "good"})
ok("Яндекс: код меняется на пропуск", st == 200 and d.get("token") and d.get("name") == "Денис", f"{st} {d}")
ok("секрет приложения уходит только в oauth.yandex.ru",
   all("ya-secret" not in json.dumps(c) for c in calls if not c[0].startswith("https://oauth.yandex.ru/token")))
ya_token = d.get("token")
ok("со своего сайта — разрешение CORS", h.get("Access-Control-Allow-Origin") == "https://oldpictureart.ru")

st, d, _ = call({"action": "login", "provider": "yandex", "code": "old"})
ok("просроченный код — отказ с понятной причиной", st == 401 and "Code has expired" in d.get("error", ""), f"{st} {d}")

st, d, _ = call({"action": "login", "provider": "yandex", "code": "alien"})
ok("пропуск чужого приложения Яндекса не принимается", st == 401, f"{st} {d}")

st, d, _ = call({"action": "login", "provider": "vk", "code": "vk-good", "code_verifier": "V" * 64,
                 "device_id": "dev", "state": "s" * 43})
ok("VK ID: код + PKCE меняются на пропуск", st == 200 and d.get("name") == "Анна", f"{st} {d}")
vk_token = d.get("token")
vk_call = [c for c in calls if c[0].endswith("/oauth2/auth")][-1][1]
ok("VK получает redirect_uri, device_id и state", vk_call.get("redirect_uri") == "https://oldpictureart.ru/auth.html"
   and vk_call.get("device_id") == "dev" and vk_call.get("state") == "s" * 43)

st, d, _ = call({"action": "login", "provider": "vk", "code": "vk-good", "code_verifier": "W" * 64,
                 "device_id": "dev", "state": "s" * 43})
ok("VK: чужой code_verifier — отказ", st == 401, f"{st}")

st, d, _ = call({"action": "login", "provider": "google", "code": "x"})
ok("неизвестный способ входа — отказ", st == 400)

# ------------------------------------------------------------ избранное
st, d, _ = call({"action": "sync", "token": ya_token, "likes": ["39", "40", "<script>", "40", "a" * 80]})
ok("sync: отметки браузера ушли в облако", st == 200 and d.get("likes") == ["39", "40"], f"{d}")
ok("мусор вместо номеров картин в базу не попал", mem.rows.get("ya:1001") == {"39", "40"}, str(mem.rows))

call({"action": "like", "token": ya_token, "post_id": "41"})
call({"action": "unlike", "token": ya_token, "post_id": "39"})
st, d, _ = call({"action": "sync", "token": ya_token, "likes": []})
ok("like / unlike доходят до базы", d.get("likes") == ["40", "41"], f"{d}")

st, d, _ = call({"action": "sync", "token": vk_token, "likes": []})
ok("отметки разных людей не смешиваются", d.get("likes") == [], f"{d}")

st, d, _ = call({"action": "like", "token": ya_token, "post_id": "../etc"})
ok("неверный номер картины — отказ", st == 400)

# ------------------------------------------------------------ пропуск
forged = ya_token.split(".")[0] + "." + "A" * 43
st, d, _ = call({"action": "sync", "token": forged, "likes": []})
ok("пропуск с чужой подписью — 401", st == 401)

body = json.loads(base64.urlsafe_b64decode(ya_token.split(".")[0] + "=="))
body["u"] = "vk:2002"
tampered = base64.urlsafe_b64encode(json.dumps(body).encode()).rstrip(b"=").decode() + "." + ya_token.split(".")[1]
st, d, _ = call({"action": "sync", "token": tampered, "likes": []})
ok("подменить номер пользователя в пропуске нельзя", st == 401)

old_tok, _ = fn.make_token("ya:1001", "Денис", "yandex", now=time.time() - 200 * 86400)
st, d, _ = call({"action": "sync", "token": old_tok, "likes": []})
ok("просроченный пропуск — 401 и просьба войти снова", st == 401 and "войдите" in d.get("error", ""))

st, d, _ = call({"action": "sync", "likes": []})
ok("без пропуска отметки не отдаются", st == 401)

# ------------------------------------------------------------ удаление
st, d, _ = call({"action": "delete", "token": ya_token})
ok("delete стирает все отметки человека", st == 200 and "ya:1001" not in mem.rows)

# ------------------------------------------------------------ сеть и настройки
st, d, h = call({"action": "ping"}, origin="https://evil.example")
ok("запрос с чужого сайта — 403", st == 403 and "Access-Control-Allow-Origin" not in h)
st, d, h = call({"action": "ping"}, origin=None)
ok("проверка из консоли облака (без Origin) работает", st == 200 and d.get("db") is True, f"{st} {d}")
st, d, h = call({"action": "ping"}, b64=True)
ok("тело в base64 разбирается", st == 200)
r = fn.handler({"httpMethod": "OPTIONS", "headers": {"origin": "https://oldpictureart.ru"}}, None)
ok("OPTIONS — 204 с разрешением CORS", r["statusCode"] == 204 and r["headers"].get("Access-Control-Allow-Origin"))
st, d, _ = call("не объект")
ok("не JSON-объект — 400", st == 400)
os.environ["SESSION_SECRET"] = "short"
st, d, _ = call({"action": "ping"})
ok("без длинного SESSION_SECRET функция не работает вслепую", st == 500)
os.environ["SESSION_SECRET"] = "x" * 40

# ------------------------------------------------------------ запросы к YDB
class FakeTx:
    def __init__(self, log):
        self.log = log

    def execute(self, prepared, params=None, commit_tx=False, settings=None):
        self.log.append((prepared, params))
        class RS:
            rows = []
        return [RS()]

    def commit(self):
        self.log.append(("COMMIT", None))


class FakeSession:
    def __init__(self, log):
        self.log = log

    def prepare(self, q):
        return q

    def transaction(self, mode=None):
        return FakeTx(self.log)


class FakePool:
    def __init__(self):
        self.log = []

    def retry_operation_sync(self, work, *a, **k):
        return work(FakeSession(self.log))


class FakeYdb:
    class SerializableReadWrite:
        pass


y = fn.YdbStore.__new__(fn.YdbStore)
y.ydb, y.pool = FakeYdb, FakePool()
y.list("ya:1"); y.add("ya:1", ["1", "2"]); y.remove("ya:1", "1"); y.clear("ya:1")
queries = [(q, p) for q, p in y.pool.log if q != "COMMIT"]
bad = []
for q, p in queries:
    for name in (p or {}):
        if f"DECLARE {name} AS Utf8" not in q:
            bad.append(f"{name} не объявлен: {q[:50]}")
    if "likes" not in q or "user_id" not in q:
        bad.append("нет таблицы или ключа: " + q[:50])
ok("запросы к YDB: все параметры объявлены, ключ на месте", not bad and len(queries) == 5, "; ".join(bad) or str(len(queries)))
ok("каждая операция закрывается commit", sum(1 for q, _ in y.pool.log if q == "COMMIT") == 4)

print("\n====== ФУНКЦИЯ ВХОДА И ИЗБРАННОГО ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
