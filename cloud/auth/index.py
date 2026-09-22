# -*- coding: utf-8 -*-
"""
Вход через Яндекс ID и VK ID и избранное — функция для Yandex Cloud Functions.

Зачем она. Сайт статический, своего сервера у него нет, а вход через
Яндекс и VK выдаёт одноразовый код, который нужно обменять на данные
человека. Делать это в браузере нельзя — там секрет приложения увидел бы
любой. Эта функция и есть тот маленький сервер: меняет код на имя и номер
пользователя, выдаёт сайту собственный пропуск (подписанный токен) и
хранит отметки «в избранное» в базе YDB. Всё лежит в России, у Яндекса.

Что хранится в базе: номер пользователя у Яндекса или VK и номера
отмеченных картин. Имя в базу не пишется — оно живёт только в пропуске
в браузере человека, чтобы показать его на кнопке.

Запросы — POST с телом JSON и заголовком Content-Type: text/plain (так
браузер не устраивает предварительный OPTIONS-запрос). Действие — поле
"action":
    ping    — проверка: жива ли функция и достаёт ли она до базы
    login   — обменять код Яндекса или VK на пропуск
    sync    — свести отметки браузера с облачными, вернуть общий список
    like    — отметить картину        unlike — снять отметку
    delete  — удалить все отметки этого человека из облака
    counts  — сколько раз отмечены картины (без пропуска, только числа)
    top     — самые отмечаемые картины (без пропуска, только числа)

Настройки — переменные окружения функции (см. AUTH_SETUP.md):
    SESSION_SECRET        длинная случайная строка для подписи пропусков
    ALLOWED_ORIGINS       https://oldpictureart.ru (через запятую, если несколько)
    REDIRECT_URI          https://oldpictureart.ru/auth.html
    YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET
    VK_CLIENT_ID
    YDB_ENDPOINT, YDB_DATABASE
"""

import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

SESSION_DAYS = 180
MAX_LIKES = 5000
# Число отметок у картин видно всем, поэтому его спрашивает каждая
# открытая страница. Чтобы не гонять по базе полный подсчёт на каждый
# просмотр, итог держится в памяти функции пару минут; своя отметка или
# снятие сбрасывает его сразу.
COUNTS_TTL = 120
POST_ID_RE = re.compile(r"^[0-9A-Za-z_-]{1,40}$")
VK_HOST = os.environ.get("VK_HOST", "https://id.vk.ru").rstrip("/")


def env(name, default=""):
    return os.environ.get(name, default).strip()


class Fail(Exception):
    """Ошибка, о которой нужно честно ответить сайту."""
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


# ------------------------------------------------------------ пропуск
def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(user, name, provider, now=None):
    now = int(now or time.time())
    payload = {"u": user, "n": name, "p": provider, "exp": now + SESSION_DAYS * 86400}
    body = _b64(json.dumps(payload, ensure_ascii=False).encode())
    sig = _b64(hmac.new(env("SESSION_SECRET").encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}", payload


def read_token(token, now=None):
    """Проверяет подпись и срок. Возвращает содержимое или бросает Fail(401)."""
    try:
        body, sig = (token or "").split(".", 1)
        want = _b64(hmac.new(env("SESSION_SECRET").encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, want):
            raise ValueError("подпись")
        payload = json.loads(_unb64(body))
    except Exception:
        raise Fail(401, "Пропуск недействителен — войдите заново")
    if payload.get("exp", 0) < int(now or time.time()):
        raise Fail(401, "Срок входа истёк — войдите заново")
    return payload


# ------------------------------------------------------------ сеть
def http_json(url, data=None, headers=None):
    """GET или POST (form-urlencoded) с ответом JSON. Отдельной функцией —
    проверки подставляют сюда готовые ответы Яндекса и VK."""
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    if body is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"error": f"http {e.code}"}


def login_yandex(req):
    code = str(req.get("code") or "")
    if not code:
        raise Fail(400, "Нет кода от Яндекса")
    tok = http_json("https://oauth.yandex.ru/token", {
        "grant_type": "authorization_code", "code": code,
        "client_id": env("YANDEX_CLIENT_ID"), "client_secret": env("YANDEX_CLIENT_SECRET"),
    })
    access = tok.get("access_token")
    if not access:
        raise Fail(401, "Яндекс не подтвердил вход: " + str(tok.get("error_description") or tok.get("error") or ""))
    info = http_json("https://login.yandex.ru/info?format=json",
                     headers={"Authorization": f"OAuth {access}"})
    uid = str(info.get("id") or "")
    # Пропуск должен быть выдан именно нашему приложению.
    if not uid or str(info.get("client_id") or "") != env("YANDEX_CLIENT_ID"):
        raise Fail(401, "Яндекс не отдал данные пользователя")
    name = info.get("first_name") or info.get("display_name") or info.get("login") or "Профиль"
    return "ya:" + uid, name


def login_vk(req):
    need = ("code", "code_verifier", "device_id", "state")
    if not all(req.get(k) for k in need):
        raise Fail(400, "Нет кода от VK")
    tok = http_json(f"{VK_HOST}/oauth2/auth", {
        "grant_type": "authorization_code",
        "code": req["code"], "code_verifier": req["code_verifier"],
        "device_id": req["device_id"], "state": req["state"],
        "client_id": env("VK_CLIENT_ID"), "redirect_uri": env("REDIRECT_URI"),
    })
    access = tok.get("access_token")
    if not access:
        raise Fail(401, "VK не подтвердил вход: " + str(tok.get("error_description") or tok.get("error") or ""))
    info = http_json(f"{VK_HOST}/oauth2/user_info",
                     {"access_token": access, "client_id": env("VK_CLIENT_ID")})
    user = info.get("user") or {}
    uid = str(user.get("user_id") or "")
    if not uid or (tok.get("user_id") and str(tok["user_id"]) != uid):
        raise Fail(401, "VK не отдал данные пользователя")
    return "vk:" + uid, user.get("first_name") or "Профиль"


# ------------------------------------------------------------ хранилище
class YdbStore:
    """Отметки в Yandex Database (serverless). Таблица likes:
    user_id Utf8, post_id Utf8, created_at Timestamp, ключ (user_id, post_id)."""

    def __init__(self):
        import ydb
        import ydb.iam
        self.ydb = ydb
        self.driver = ydb.Driver(endpoint=env("YDB_ENDPOINT"), database=env("YDB_DATABASE"),
                                 credentials=ydb.iam.MetadataUrlCredentials())
        self.driver.wait(fail_fast=True, timeout=5)
        self.pool = ydb.SessionPool(self.driver)

    def _run(self, statements, commit=True):
        """statements: [(текст запроса, параметры)]. Всё в одной транзакции."""
        def work(session):
            tx = session.transaction(self.ydb.SerializableReadWrite())
            out = []
            for query, params in statements:
                out.append(tx.execute(session.prepare(query), params))
            tx.commit()
            return out
        return self.pool.retry_operation_sync(work)

    def ping(self):
        self._run([("SELECT 1 AS one;", {})])
        return True

    def list(self, user):
        res = self._run([("DECLARE $u AS Utf8; SELECT post_id FROM likes WHERE user_id = $u;",
                          {"$u": user})])
        rows = res[0][0].rows if res and res[0] else []
        return [r.post_id for r in rows]

    def add(self, user, posts):
        q = ("DECLARE $u AS Utf8; DECLARE $p AS Utf8; "
             "UPSERT INTO likes (user_id, post_id, created_at) VALUES ($u, $p, CurrentUtcTimestamp());")
        if posts:
            self._run([(q, {"$u": user, "$p": p}) for p in posts])

    def remove(self, user, post):
        self._run([("DECLARE $u AS Utf8; DECLARE $p AS Utf8; "
                    "DELETE FROM likes WHERE user_id = $u AND post_id = $p;",
                    {"$u": user, "$p": post})])

    def clear(self, user):
        self._run([("DECLARE $u AS Utf8; DELETE FROM likes WHERE user_id = $u;", {"$u": user})])

    def counts(self):
        """{номер картины: сколько человек её отметили}."""
        res = self._run([("SELECT post_id, COUNT(*) AS n FROM likes GROUP BY post_id "
                          "ORDER BY n DESC LIMIT 1000;", {})])
        rows = res[0][0].rows if res and res[0] else []
        return {r.post_id: int(r.n) for r in rows}


_store = None
_counts = {"at": 0.0, "data": {}}


def all_counts(db, now=None):
    now = now or time.time()
    if now - _counts["at"] > COUNTS_TTL:
        _counts["data"] = db.counts()
        _counts["at"] = now
    return _counts["data"]


def forget_counts():
    _counts["at"] = 0.0


def store():
    global _store
    if _store is None:
        _store = YdbStore()
    return _store


# ------------------------------------------------------------ действия
def clean_ids(values, limit=MAX_LIKES):
    out = []
    for v in values if isinstance(values, list) else []:
        v = str(v)
        if POST_ID_RE.match(v) and v not in out:
            out.append(v)
        if len(out) >= limit:
            break
    return out


def act(req):
    action = req.get("action")
    if action == "ping":
        ok = True
        try:
            store().ping()
        except Exception as e:
            ok = False
            print("ping: база недоступна:", repr(e))
        return {"ok": True, "db": ok}

    if action == "login":
        provider = req.get("provider")
        if provider == "yandex" and env("YANDEX_CLIENT_ID"):
            user, name = login_yandex(req)
        elif provider == "vk" and env("VK_CLIENT_ID"):
            user, name = login_vk(req)
        else:
            raise Fail(400, "Такой способ входа не настроен")
        token, payload = make_token(user, name, provider)
        return {"token": token, "name": name, "provider": provider, "exp": payload["exp"]}

    # Общие числа — без пропуска: кто отметил, в ответе нет, только сколько.
    if action == "counts":
        ids = clean_ids(req.get("post_ids"), limit=200)
        data = all_counts(store())
        return {"counts": {i: data[i] for i in ids if data.get(i)}}
    if action == "top":
        try:
            limit = max(1, min(24, int(req.get("limit") or 6)))
        except (TypeError, ValueError):
            limit = 6
        data = all_counts(store())
        best = sorted(data.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return {"top": [[k, v] for k, v in best if v > 0]}

    if action not in ("sync", "like", "unlike", "delete"):
        raise Fail(400, "Неизвестное действие")

    who = read_token(req.get("token"))["u"]
    db = store()
    forget_counts()          # отметки меняются — общий счёт пересчитается
    if action == "sync":
        cloud = db.list(who)
        local = clean_ids(req.get("likes"))
        new = [p for p in local if p not in cloud][:max(0, MAX_LIKES - len(cloud))]
        db.add(who, new)
        return {"likes": cloud + new}
    if action == "like":
        post = str(req.get("post_id") or "")
        if not POST_ID_RE.match(post):
            raise Fail(400, "Неверный номер картины")
        db.add(who, [post])
        return {"ok": True}
    if action == "unlike":
        post = str(req.get("post_id") or "")
        if not POST_ID_RE.match(post):
            raise Fail(400, "Неверный номер картины")
        db.remove(who, post)
        return {"ok": True}
    db.clear(who)            # delete
    return {"ok": True}


# ------------------------------------------------------------ вход HTTP
def handler(event, context=None):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin", "")
    allowed = [o.strip().rstrip("/") for o in env("ALLOWED_ORIGINS", "https://oldpictureart.ru").split(",") if o.strip()]
    cors = {"Vary": "Origin"}
    if origin:
        if origin.rstrip("/") not in allowed:
            return {"statusCode": 403, "headers": cors,
                    "body": json.dumps({"error": "Запрос не с сайта"}, ensure_ascii=False)}
        cors["Access-Control-Allow-Origin"] = origin
        cors["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        cors["Access-Control-Allow-Headers"] = "Content-Type"

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 204, "headers": cors, "body": ""}

    def reply(status, data):
        return {"statusCode": status,
                "headers": dict(cors, **{"Content-Type": "application/json; charset=utf-8"}),
                "body": json.dumps(data, ensure_ascii=False)}

    try:
        raw = event.get("body") or ""
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        req = json.loads(raw) if raw else {}
        if not isinstance(req, dict):
            raise ValueError
    except Exception:
        return reply(400, {"error": "Тело запроса — не JSON"})

    if not env("SESSION_SECRET") or len(env("SESSION_SECRET")) < 32:
        print("SESSION_SECRET не задан или короче 32 знаков")
        return reply(500, {"error": "Функция не настроена"})
    try:
        return reply(200, act(req))
    except Fail as f:
        return reply(f.status, {"error": f.message})
    except Exception as e:
        print("ошибка:", repr(e))
        return reply(500, {"error": "Что-то пошло не так на сервере"})
