# -*- coding: utf-8 -*-
"""
Оригиналы для скачивания — в облачное хранилище.

Зачем: GitHub Pages не публикует сайты больше 1 ГБ, а docs/images весит
991 МБ, из них 769 МБ — оригиналы (файлы «-hires-»), которые нужны только
кнопке «Скачать картину» и лупе. Если они уедут в Yandex Object Storage,
сайт похудеет вчетверо, и места хватит на годы.

Что делает скрипт:
  1. находит в docs/images оригиналы, на которые ссылаются посты, — кроме
     тех, что служат ещё и картинкой страницы (такие остаются на месте);
  2. выгружает недостающие в бакет — с правильным типом файла и заголовком
     Content-Disposition: без него кнопка «Скачать» с чужого домена просто
     открыла бы картинку, а с ним браузер сохраняет файл под человеческим
     именем «Художник — Название, год.jpg»;
  3. сверяет размер загруженного с локальным и только тогда переносит файл
     из docs/images в папку hires/ — это ваш архив оригиналов. На сайт и в
     репозиторий он не попадает (стоит в .gitignore).

Страницы сами решают, куда вести: пока оригинал лежит в docs/images,
ссылка локальная, как только уехал — на хранилище (см. hires_url в
site_common.py). Поэтому сбой посреди выгрузки ничего не ломает.

Запуск:
    python hires_store.py                    # только отчёт, ничего не меняет
    python hires_store.py --upload           # выгрузить и перенести
    python hires_store.py --upload --force   # перезалить всё (например,
                                             # чтобы обновить заголовки)
    python hires_store.py --stats            # сколько файлов и места в хранилище,
                                             # всё ли на месте

Потом — python rebuild_pages.py и push (удаления из docs/images тоже).
Новые посты build_site.py выгружает сам, если хранилище настроено.
Как завести бакет и ключ — STORAGE_SETUP.md.

Оригиналы не пережимаются и не уменьшаются: в хранилище уезжает ровно тот
файл, что пришёл из канала.
"""

import importlib.util
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

OUTPUT_DIR = "docs"
HIRES_DIR = "hires"
ENDPOINT = "https://storage.yandexcloud.net"
REGION = "ru-central1"
STORAGE_HOST = "storage.yandexcloud.net"

CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif", ".tif": "image/tiff",
    ".tiff": "image/tiff", ".bmp": "image/bmp",
}
# Имена оригиналов не меняются никогда — значит, кэшировать их можно
# надолго: повторное скачивание пойдёт из кэша браузера и не будет стоить
# ни трафика, ни денег за запросы к хранилищу.
CACHE_CONTROL = "public, max-age=31536000"


def load_env(path=".env"):
    """Ключи хранилища лежат в том же .env, что и ключи Телеграма."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def bucket_of(base_url):
    """(бакет, приставка) из адреса хранилища.

    Понимает оба вида адреса Yandex Object Storage:
    https://storage.yandexcloud.net/<бакет>[/папка] и
    https://<бакет>.storage.yandexcloud.net[/папка].
    """
    u = urllib.parse.urlsplit((base_url or "").strip())
    host = u.netloc.lower()
    parts = [p for p in u.path.split("/") if p]
    if host == STORAGE_HOST:
        return (parts[0] if parts else ""), "/".join(parts[1:])
    if host.endswith("." + STORAGE_HOST):
        return host[:-len(STORAGE_HOST) - 1], "/".join(parts)
    return "", ""


def object_key(prefix, rel):
    """Ключ в бакете — тот же путь, что и на сайте: images/<файл>.

    Тогда адрес в хранилище складывается из HIRES_BASE_URL и пути из базы
    без всякого пересчёта — так и делает hires_url().
    """
    rel = rel.lstrip("/")
    return f"{prefix.strip('/')}/{rel}" if prefix.strip("/") else rel


def local_path(rel, output_dir=OUTPUT_DIR, archive_dir=HIRES_DIR):
    """Где оригинал лежит на диске: в docs или уже в архиве hires/."""
    for path in (os.path.join(output_dir, rel),
                 os.path.join(archive_dir, os.path.basename(rel))):
        if os.path.exists(path):
            return path
    return ""


def local_originals(records, output_dir=OUTPUT_DIR):
    """Оригиналы в docs/images, которые можно отправлять в хранилище:
    [(путь из базы, путь на диске, запись)].

    Оригинал, который служит ещё и картинкой страницы (пост из одних
    документов без сжатой копии), остаётся на месте: <img> на странице
    ссылается на него напрямую, и в хранилище его не перенаправить.
    """
    on_page = set()
    for rec in records:
        for field in ("images", "thumbs", "views"):
            on_page.update(x for x in (rec.get(field) or []) if x)
        if rec.get("card"):
            on_page.add(rec["card"])
    out, seen = [], set()
    for rec in records:
        for rel in rec.get("hires") or []:
            if (not rel or rel in seen or rel in on_page
                    or "-hires-" not in os.path.basename(rel)):
                continue
            seen.add(rel)
            path = os.path.join(output_dir, rel)
            if os.path.exists(path):
                out.append((rel, path, rec))
    return out


def disposition(rel, pretty=""):
    """Заголовок Content-Disposition: скачать, а не открыть, и под каким именем.

    Заголовок HTTP должен быть латиницей, поэтому имя по-русски идёт
    отдельно, в кодировке из RFC 5987 (filename*=UTF-8''…) — её понимают
    все нынешние браузеры. filename= — запасное имя для совсем старых:
    имя файла без «-hires-1».
    """
    base = os.path.basename(rel)
    plain = re.sub(r"-hires-(\d+)", lambda m: "" if m.group(1) == "1" else f"-{m.group(1)}", base)
    plain = re.sub(r"[^A-Za-z0-9._-]", "_", plain) or "painting.jpg"
    header = f'attachment; filename="{plain}"'
    if pretty and pretty != plain:
        header += "; filename*=UTF-8''" + urllib.parse.quote(pretty, safe="")
    return header


def make_client(key_id, secret):
    """Клиент S3 для Yandex Object Storage."""
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name=REGION,
        aws_access_key_id=key_id, aws_secret_access_key=secret,
        config=Config(retries={"max_attempts": 5, "mode": "standard"},
                      s3={"addressing_style": "path"}))


def settings():
    """Что настроено, а что нет: (base_url, key_id, secret, чего не хватает)."""
    load_env()
    broken = ""
    try:
        from site_common import HIRES_BASE_URL
    except Exception as e:
        # Ошибку в site_common.py не прячем: иначе она выглядела бы как
        # «адрес не вписан», и искать пришлось бы не там.
        HIRES_BASE_URL, broken = "", f"{type(e).__name__}: {e}"
    key_id = os.environ.get("S3_KEY_ID", "").strip()
    secret = os.environ.get("S3_SECRET", "").strip()
    missing = []
    if broken:
        missing.append(f"site_common.py не читается — {broken}")
    elif not HIRES_BASE_URL:
        missing.append('HIRES_BASE_URL в site_common.py (строка HIRES_BASE_URL = "" '
                       "должна быть одна, с адресом бакета)")
    elif not bucket_of(HIRES_BASE_URL)[0]:
        missing.append("HIRES_BASE_URL вида https://storage.yandexcloud.net/<бакет>")
    if not key_id or not secret:
        missing.append("S3_KEY_ID и S3_SECRET в .env")
    if importlib.util.find_spec("boto3") is None:
        missing.append("модуль boto3 (pip install boto3)")
    return HIRES_BASE_URL, key_id, secret, missing


def configured():
    return not settings()[3]


def remote_size(client, bucket, key):
    """Размер объекта в бакете или None, если его там нет."""
    try:
        return client.head_object(Bucket=bucket, Key=key)["ContentLength"]
    except Exception as e:
        code = str(getattr(e, "response", {}).get("Error", {}).get("Code", ""))
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def public_ok(url, timeout=15):
    """Открывается ли файл без ключа — так, как его увидит посетитель."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout):
            return True, ""
    except urllib.error.HTTPError as e:
        return False, f"ответ {e.code}"
    except Exception as e:
        return False, str(e)


def sync(records, client, bucket, prefix="", name_for=None, apply=True,
         force=False, output_dir=OUTPUT_DIR, archive_dir=HIRES_DIR, log=print):
    """Выгружает оригиналы и переносит локальные копии в архив.

    apply=False — только посчитать, что уехало бы. Возвращает счётчики.
    Локальная копия переносится лишь тогда, когда размер в хранилище
    совпал с размером на диске: оборванная выгрузка не должна оставить
    картину без оригинала.
    """
    stats = {"found": 0, "uploaded": 0, "already": 0, "moved": 0,
             "failed": 0, "bytes": 0, "to_upload": 0, "first_rel": ""}
    for rel, path, rec in local_originals(records, output_dir):
        stats["found"] += 1
        key = object_key(prefix, rel)
        size = os.path.getsize(path)
        try:
            remote = remote_size(client, bucket, key)
        except Exception as e:
            log(f"  ✗ {rel}: хранилище не ответило ({e})")
            stats["failed"] += 1
            continue
        if remote != size or force:
            if not apply:
                stats["to_upload"] += 1
                stats["bytes"] += size
                continue
            pretty = name_for(rec, rel) if name_for else ""
            ext = os.path.splitext(rel)[1].lower()
            try:
                client.upload_file(path, bucket, key, ExtraArgs={
                    "ContentType": CONTENT_TYPES.get(ext, "application/octet-stream"),
                    "ContentDisposition": disposition(rel, pretty),
                    "CacheControl": CACHE_CONTROL,
                })
                remote = remote_size(client, bucket, key)
            except Exception as e:
                log(f"  ✗ {rel}: не выгрузился ({e})")
                stats["failed"] += 1
                continue
            if remote != size:
                log(f"  ✗ {rel}: в хранилище {remote} байт вместо {size} — оставляю на месте")
                stats["failed"] += 1
                continue
            stats["uploaded"] += 1
            stats["bytes"] += size
            stats["first_rel"] = stats["first_rel"] or rel
            log(f"  ↑ {rel} ({size / 1048576:.1f} МБ)")
        else:
            stats["already"] += 1
        if apply:
            os.makedirs(archive_dir, exist_ok=True)
            shutil.move(path, os.path.join(archive_dir, os.path.basename(rel)))
            stats["moved"] += 1
    return stats


FREE_BYTES = 1024 ** 3   # первый гигабайт стандартного хранилища бесплатен


def bucket_objects(client, bucket, prefix=""):
    """{ключ: размер} всего, что лежит в бакете (под приставкой)."""
    out = {}
    pager = client.get_paginator("list_objects_v2")
    kw = {"Bucket": bucket}
    if prefix.strip("/"):
        kw["Prefix"] = prefix.strip("/") + "/"
    for page in pager.paginate(**kw):
        for obj in page.get("Contents") or []:
            out[obj["Key"]] = obj["Size"]
    return out


def compare_bucket(records, objects, prefix="", output_dir=OUTPUT_DIR):
    """Сверка бакета с базой: что есть, чего не хватает, что лишнее.

    Возвращает словарь: files, bytes — всего в бакете; missing — оригиналы,
    на которые ссылаются посты, но которых нет ни в бакете, ни в docs
    (скачать их нельзя); waiting — ещё лежат в docs и ждут выгрузки;
    extra — лежат в бакете, но ни один пост на них не ссылается.
    """
    # Оригинал, который служит и картинкой страницы, живёт на сайте и в
    # хранилище не уезжает (см. local_originals) — его не ждём и не ищем.
    on_page = set()
    for rec in records:
        for field in ("images", "thumbs", "views"):
            on_page.update(x for x in (rec.get(field) or []) if x)
    wanted = {}
    for rec in records:
        for rel in rec.get("hires") or []:
            if rel and "-hires-" in os.path.basename(rel) and rel not in on_page:
                wanted[object_key(prefix, rel)] = rel
    waiting = sorted(rel for key, rel in wanted.items()
                     if key not in objects and os.path.exists(os.path.join(output_dir, rel)))
    missing = sorted(rel for key, rel in wanted.items()
                     if key not in objects and not os.path.exists(os.path.join(output_dir, rel)))
    extra = sorted(k for k in objects if k not in wanted)
    return {"files": len(objects), "bytes": sum(objects.values()),
            "missing": missing, "waiting": waiting, "extra": extra,
            "extra_bytes": sum(objects[k] for k in extra)}


def print_stats(st, bucket, out=print):
    mb = lambda b: f"{b / 1048576:.0f} МБ"
    out(f"В хранилище (бакет {bucket}): {st['files']} файлов, {mb(st['bytes'])}")
    share = st["bytes"] / FREE_BYTES * 100
    out(f"Бесплатный гигабайт занят на {share:.0f}%"
        + ("" if share < 100 else " — дальше хранение платное, но это копейки за гигабайт"))
    if st["missing"]:
        out(f"\n✗ Нет ни в хранилище, ни на сайте ({len(st['missing'])}) — эти картины не скачать:")
        for rel in st["missing"][:10]:
            out(f"    {rel}")
        out("  Если копии есть в hires/, верните их в docs/images и запустите --upload.")
    if st["waiting"]:
        out(f"\nЕщё в docs/images, ждут выгрузки: {len(st['waiting'])} — python hires_store.py --upload")
    if st["extra"]:
        out(f"\nЛишние в хранилище (ни один пост не ссылается): {len(st['extra'])}, {mb(st['extra_bytes'])}")
        for key in st["extra"][:10]:
            out(f"    {key}")
    if not (st["missing"] or st["waiting"] or st["extra"]):
        out("Все оригиналы, на которые ссылаются посты, лежат в хранилище, лишнего нет.")


def main():
    upload = "--upload" in sys.argv
    force = "--force" in sys.argv
    base, key_id, secret, missing = settings()

    records = []
    for name in ("posts_meta.json", "visits_meta.json"):
        if os.path.exists(name):
            with open(name, encoding="utf-8") as f:
                records += json.load(f)
    todo = local_originals(records)
    weight = sum(os.path.getsize(p) for _, p, _ in todo)
    archived = len(os.listdir(HIRES_DIR)) if os.path.isdir(HIRES_DIR) else 0
    print(f"Оригиналов в docs/images: {len(todo)}, {weight / 1048576:.0f} МБ")
    print(f"Уже в архиве hires/: {archived}")

    if missing:
        print("\nХранилище не настроено, не хватает:")
        for m in missing:
            print(f"  • {m}")
        print("Как настроить — STORAGE_SETUP.md")
        return 1
    if "--stats" in sys.argv:
        bucket, prefix = bucket_of(base)
        client = make_client(key_id, secret)
        print()
        st = compare_bucket(records, bucket_objects(client, bucket, prefix), prefix)
        print_stats(st, bucket)
        return 1 if st["missing"] else 0
    if not todo:
        print("\nВыгружать нечего: все оригиналы уже в хранилище.")
        return 0

    bucket, prefix = bucket_of(base)
    client = make_client(key_id, secret)
    # Имя для кнопки «Скачать» считает сборка — берём её же правило,
    # чтобы в хранилище и на странице имя было одно.
    from build_site import download_name
    stats = sync(records, client, bucket, prefix, name_for=download_name,
                 apply=upload, force=force)

    if not upload:
        print(f"\nВ хранилище уже есть: {stats['already']}, выгрузить: "
              f"{stats['to_upload']} ({stats['bytes'] / 1048576:.0f} МБ)")
        print("Это только отчёт. Выгрузить: python hires_store.py --upload")
        return 0

    print(f"\nВыгружено: {stats['uploaded']} ({stats['bytes'] / 1048576:.0f} МБ), "
          f"уже были: {stats['already']}, перенесено в hires/: {stats['moved']}, "
          f"ошибок: {stats['failed']}")
    if stats["first_rel"]:
        # Адрес — ровно тот, что поставит на страницу hires_url().
        url = f"{base.rstrip('/')}/{stats['first_rel'].lstrip('/')}"
        good, why = public_ok(url)
        if not good:
            print(f"\n⚠ Файл не открывается без ключа ({why}): {url}\n"
                  "  В настройках бакета поставьте «Чтение объектов — Для всех»\n"
                  "  (STORAGE_SETUP.md, шаг 1).")
    print("\nДальше: python rebuild_pages.py — и push, вместе с удалениями из docs/images.")
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
