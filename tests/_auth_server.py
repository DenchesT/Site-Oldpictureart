# -*- coding: utf-8 -*-
"""Настоящая функция входа (cloud/auth/index.py) на местном порту — для
test_login.js. Яндекс ID, VK ID и база подменены; всё остальное — ровно
тот код, что уедет в Yandex Cloud.

Запуск: python tests/_auth_server.py <порт> <разрешённый Origin> [номера картин через запятую]
"""
import base64
import hashlib
import importlib.util
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
spec = importlib.util.spec_from_file_location("authfn", os.path.join(ROOT, "cloud", "auth", "index.py"))
fn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fn)

port, origin = int(sys.argv[1]), sys.argv[2]
os.environ.update({"SESSION_SECRET": "t" * 40, "ALLOWED_ORIGINS": origin,
                   "REDIRECT_URI": origin + "/auth.html",
                   "YANDEX_CLIENT_ID": "ya-app", "YANDEX_CLIENT_SECRET": "s", "VK_CLIENT_ID": "vk-app"})


class Memory:
    rows = {}
    def ping(self): return True
    def list(self, u): return sorted(self.rows.get(u, set()))
    def add(self, u, ps): self.rows.setdefault(u, set()).update(ps)
    def remove(self, u, p): self.rows.get(u, set()).discard(p)
    def clear(self, u): self.rows.pop(u, None)

    def counts(self):
        out = {}
        for ps in self.rows.values():
            for p in ps:
                out[p] = out.get(p, 0) + 1
        return out


fn._store = Memory()
# у «облачного» Денниса уже отмечена картина 7 — после входа она должна появиться в браузере
fn._store.rows["ya:1001"] = {"7"}
# другой посетитель уже отметил несколько картин — для «Популярного»
if len(sys.argv) > 3 and sys.argv[3]:
    fn._store.rows["vk:9"] = set(sys.argv[3].split(","))
LOG = []


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def fake_http(url, data=None, headers=None):
    if url == "https://oauth.yandex.ru/token":
        return {"access_token": "YA"} if data["code"] == "good" else {"error": "invalid_grant"}
    if url.startswith("https://login.yandex.ru/info"):
        return {"id": "1001", "first_name": "Денис", "client_id": "ya-app"}
    if url.endswith("/oauth2/auth"):
        # код вида vk-<отпечаток>: так проверяется, что сайт прислал тот
        # самый code_verifier, отпечаток которого ушёл в VK
        want = data["code"][3:]
        got = b64url(hashlib.sha256(data["code_verifier"].encode()).digest())
        return {"access_token": "VK", "user_id": "2002"} if want == got else {"error": "invalid_grant"}
    if url.endswith("/oauth2/user_info"):
        return {"user": {"user_id": "2002", "first_name": "Анна"}}
    raise AssertionError(url)


fn.http_json = fake_http


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _go(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode() if n else ""
        if self.path.startswith("/__log"):
            out = {"statusCode": 200, "headers": {}, "body": json.dumps(LOG)}
        else:
            try:
                LOG.append(json.loads(body))
            except Exception:
                LOG.append({"raw": body})
            out = fn.handler({"httpMethod": method, "headers": dict(self.headers), "body": body,
                              "isBase64Encoded": False}, None)
        self.send_response(out["statusCode"])
        for k, v in out.get("headers", {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write((out.get("body") or "").encode())

    def do_POST(self):
        self._go("POST")

    def do_GET(self):
        self._go("GET")

    def do_OPTIONS(self):
        self._go("OPTIONS")


srv = ThreadingHTTPServer(("127.0.0.1", port), H)
print("READY", flush=True)
srv.serve_forever()
