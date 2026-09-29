# -*- coding: utf-8 -*-
"""Оригиналы в облачном хранилище.

GitHub Pages не публикует сайт больше 1 ГБ, а оригиналы («-hires-») —
три четверти веса. hires_store.py выгружает их в Yandex Object Storage и
переносит локальные копии в архив hires/, а страницы ведут туда, где файл
лежит на самом деле. Проверяется то, что может тихо сломаться:

  • адрес хранилища разбирается в обоих видах, ключ совпадает с путём на
    сайте — иначе ссылка со страницы вела бы мимо файла;
  • оригинал, который служит и картинкой страницы, не уезжает;
  • у файла в хранилище правильный тип и Content-Disposition с именем
    «Художник — Название, год.jpg» — без него кнопка «Скачать» с чужого
    домена откроет картинку вместо сохранения;
  • локальная копия уходит в архив только после сверки размера —
    оборванная выгрузка не оставляет картину без оригинала;
  • отчёт (без --upload) ничего не трогает;
  • hires_url ведёт в хранилище, только когда файла уже нет в docs;
  • копия для лупы делается и из архива.

Хранилище подставное (moto). Если moto не установлен — проверки с ним
пропускаются, остальные идут.

Запуск:  python tests/test_hires_store.py
"""

import os
import shutil
import sys
import tempfile
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("OPA_OFFLINE_RENDER", "1")
sys.argv = ["hires_store.py"]

import hires_store as hs
import site_common as sc

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# ------------------------------------------------------------ адрес и ключ
ok("адрес вида storage.yandexcloud.net/бакет",
   hs.bucket_of("https://storage.yandexcloud.net/oldpictureart") == ("oldpictureart", ""))
ok("адрес с папкой внутри бакета",
   hs.bucket_of("https://storage.yandexcloud.net/opa/site/") == ("opa", "site"))
ok("адрес вида бакет.storage.yandexcloud.net",
   hs.bucket_of("https://opa.storage.yandexcloud.net") == ("opa", ""))
ok("чужой адрес не принимается за хранилище", hs.bucket_of("https://example.org/x") == ("", ""))
ok("ключ — тот же путь, что на сайте", hs.object_key("", "images/a-hires-1.jpg") == "images/a-hires-1.jpg")
ok("ключ с папкой бакета", hs.object_key("site", "images/a-hires-1.jpg") == "site/images/a-hires-1.jpg")

cd = hs.disposition("images/sisley-lug-1875-hires-1.jpg", "Альфред Сислей — Луг, 1875.jpg")
ok("скачивание, а не открытие", cd.startswith("attachment;"), cd)
ok("запасное имя — латиницей и без «-hires-1»", 'filename="sisley-lug-1875.jpg"' in cd, cd)
ok("русское имя — по RFC 5987",
   "filename*=UTF-8''" + urllib.parse.quote("Альфред Сислей — Луг, 1875.jpg", safe="") in cd)
ok("заголовок целиком латиницей (иначе HTTP его не пропустит)", cd.isascii())
ok("второй оригинал помнит свой номер",
   'filename="guillaumin-x-2.jpg"' in hs.disposition("images/guillaumin-x-hires-2.jpg"))


# ------------------------------------------------------------ подставной сайт
def make_site():
    tmp = tempfile.mkdtemp()
    docs = os.path.join(tmp, "docs")
    os.makedirs(os.path.join(docs, "images"))
    files = {"images/a-hires-1.jpg": b"A" * 3000, "images/b-hires-1.png": b"B" * 5000,
             "images/c-hires-1.jpg": b"C" * 100, "images/a-1.jpg": b"a" * 50}
    for rel, data in files.items():
        with open(os.path.join(docs, rel), "wb") as f:
            f.write(data)
    records = [
        {"filename": "a.html", "artist": "Альфред Сислей", "title": "Луг, 1875",
         "images": ["images/a-1.jpg"], "hires": ["images/a-hires-1.jpg"]},
        {"filename": "b.html", "artist": "Б", "title": "Б", "images": ["images/b-1.jpg"],
         "hires": ["images/b-hires-1.png", "images/missing-hires-2.jpg"]},
        # пост из одних документов: оригинал он же картинка страницы
        {"filename": "c.html", "images": ["images/c-hires-1.jpg"], "hires": ["images/c-hires-1.jpg"]},
    ]
    return tmp, docs, records


tmp, docs, records = make_site()
found = [rel for rel, _, _ in hs.local_originals(records, docs)]
ok("в выгрузку идут оригиналы, которые есть на диске",
   found == ["images/a-hires-1.jpg", "images/b-hires-1.png"], str(found))
ok("оригинал, который и картинка страницы, остаётся на месте", "images/c-hires-1.jpg" not in found)


# ------------------------------------------------------------ выгрузка
try:
    import boto3
    from moto import mock_aws
    HAVE_MOTO = True
except ImportError:
    HAVE_MOTO = False
    ok("moto не установлен — проверки выгрузки пропущены", True)

if HAVE_MOTO:
    os.environ.update(AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x", AWS_DEFAULT_REGION="us-east-1")
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="opa")
        archive = os.path.join(tmp, "hires")
        names = lambda rec, rel: f"{rec['artist']} — {rec['title']}{os.path.splitext(rel)[1]}"
        log = []

        dry = hs.sync(records, s3, "opa", name_for=names, apply=False,
                      output_dir=docs, archive_dir=archive, log=log.append)
        ok("отчёт считает, но ничего не выгружает и не трогает",
           dry["to_upload"] == 2 and s3.list_objects_v2(Bucket="opa").get("KeyCount", 0) == 0
           and os.path.exists(os.path.join(docs, "images/a-hires-1.jpg")), str(dry))

        st = hs.sync(records, s3, "opa", name_for=names, output_dir=docs,
                     archive_dir=archive, log=log.append)
        ok("оба оригинала выгружены", st["uploaded"] == 2 and st["failed"] == 0, str(st))
        head = s3.head_object(Bucket="opa", Key="images/a-hires-1.jpg")
        ok("тип файла по расширению", head["ContentType"] == "image/jpeg"
           and s3.head_object(Bucket="opa", Key="images/b-hires-1.png")["ContentType"] == "image/png")
        ok("Content-Disposition с именем картины",
           head.get("ContentDisposition", "").startswith("attachment;")
           and urllib.parse.quote("Альфред Сислей — Луг, 1875.jpg", safe="") in head["ContentDisposition"],
           head.get("ContentDisposition"))
        ok("кэш на год — имена оригиналов не меняются", "max-age=31536000" in head.get("CacheControl", ""))
        ok("в хранилище ровно тот файл, что был (не пережат)",
           s3.get_object(Bucket="opa", Key="images/a-hires-1.jpg")["Body"].read() == b"A" * 3000)
        ok("локальные копии ушли из docs в архив hires/",
           not os.path.exists(os.path.join(docs, "images/a-hires-1.jpg"))
           and os.path.getsize(os.path.join(archive, "a-hires-1.jpg")) == 3000)
        ok("картинка страницы и её «оригинал» остались в docs",
           os.path.exists(os.path.join(docs, "images/c-hires-1.jpg"))
           and os.path.exists(os.path.join(docs, "images/a-1.jpg")))

        again = hs.sync(records, s3, "opa", output_dir=docs, archive_dir=archive, log=log.append)
        ok("второй прогон: выгружать нечего", again["found"] == 0 and again["uploaded"] == 0)

        # файл вернулся в docs (например, после --rebuild) — повторно не льём
        shutil.copy(os.path.join(archive, "a-hires-1.jpg"), os.path.join(docs, "images/a-hires-1.jpg"))
        st3 = hs.sync(records, s3, "opa", output_dir=docs, archive_dir=archive, log=log.append)
        ok("уже лежащий в хранилище файл не заливается снова",
           st3["already"] == 1 and st3["uploaded"] == 0 and st3["moved"] == 1, str(st3))

        # --stats: сверка бакета с базой
        s3.put_object(Bucket="opa", Key="images/old-hires-1.jpg", Body=b"x" * 10)   # лишний
        objs = hs.bucket_objects(s3, "opa")
        recs_st = records + [{"filename": "d.html", "hires": ["images/lost-hires-1.jpg"]}]
        st = hs.compare_bucket(recs_st, objs, output_dir=docs)
        ok("сводка: сколько файлов и сколько места в бакете",
           st["files"] == 3 and st["bytes"] == 3000 + 5000 + 10, str({k: st[k] for k in ("files", "bytes")}))
        ok("сводка: оригинал, которого нет ни в бакете, ни в docs, назван",
           st["missing"] == ["images/lost-hires-1.jpg", "images/missing-hires-2.jpg"], str(st["missing"]))
        ok("сводка: лишний файл в бакете назван", st["extra"] == ["images/old-hires-1.jpg"], str(st["extra"]))
        out = []
        hs.print_stats(st, "opa", out=out.append)
        text = "\n".join(out)
        ok("сводка печатает объём и долю бесплатного гигабайта",
           "3 файлов" in text and "Бесплатный гигабайт занят" in text, out[0] if out else "")
        shutil.copy(os.path.join(archive, "b-hires-1.png"), os.path.join(docs, "images/b-hires-1.png"))
        empty_bucket = hs.compare_bucket(records, {}, output_dir=docs)
        ok("сводка: ещё не выгруженное в docs — «ждут выгрузки», а не «пропали»",
           "images/b-hires-1.png" in empty_bucket["waiting"]
           and "images/b-hires-1.png" not in empty_bucket["missing"], str(empty_bucket))
        ok("сводка: оригинал-картинку страницы не ждёт и не ищет",
           "images/c-hires-1.jpg" not in empty_bucket["waiting"] + empty_bucket["missing"])
        os.remove(os.path.join(docs, "images/b-hires-1.png"))

        # оборванная выгрузка: хранилище говорит «не тот размер»
        tmp2, docs2, recs2 = make_site()

        class Truncating:
            def __init__(self, real):
                self.real = real

            def upload_file(self, *a, **kw):
                return self.real.upload_file(*a, **kw)

            def head_object(self, **kw):
                r = self.real.head_object(**kw)
                return dict(r, ContentLength=r["ContentLength"] - 1)

        st4 = hs.sync(recs2, Truncating(s3), "opa", output_dir=docs2,
                      archive_dir=os.path.join(tmp2, "hires"), log=log.append, force=True)
        ok("размер не сошёлся — оригинал остаётся в docs",
           st4["failed"] == 2 and os.path.exists(os.path.join(docs2, "images/a-hires-1.jpg")), str(st4))
        shutil.rmtree(tmp2, ignore_errors=True)


# ------------------------------------------------------------ ссылки со страниц
old_base, old_cwd = sc.HIRES_BASE_URL, os.getcwd()
os.chdir(tmp)                      # тут docs/ подставного сайта
sc.HIRES_BASE_URL = "https://storage.yandexcloud.net/opa"
try:
    gone = "images/a-hires-1.jpg" if not os.path.exists("docs/images/a-hires-1.jpg") else "images/zz-hires-1.jpg"
    ok("уехавший оригинал — ссылка на хранилище",
       sc.hires_url(gone) == f"https://storage.yandexcloud.net/opa/{gone}", sc.hires_url(gone))
    ok("оригинал ещё в docs — ссылка локальная",
       sc.hires_url("images/c-hires-1.jpg") == "images/c-hires-1.jpg")
    ok("картинка страницы в хранилище не уводится",
       sc.hires_url("images/zz-1.jpg") == "images/zz-1.jpg")
    sc.HIRES_BASE_URL = ""
    ok("без хранилища всё как было", sc.hires_url("images/zz-hires-1.jpg") == "images/zz-hires-1.jpg")
finally:
    sc.HIRES_BASE_URL = old_base
    os.chdir(old_cwd)

if HAVE_MOTO:
    ok("копию для лупы можно сделать и из архива",
       hs.local_path("images/b-hires-1.png", docs, os.path.join(tmp, "hires"))
       == os.path.join(tmp, "hires", "b-hires-1.png"))
ok("нет нигде — пустая строка", hs.local_path("images/nope-hires-1.jpg", docs, tmp) == "")

# ------------------------------------------------------------ сборка
import build_site as bs

sc_base = sc.HIRES_BASE_URL
real_settings = hs.settings
hs.settings = lambda: ("", "", "", ["HIRES_BASE_URL в site_common.py"])
ok("хранилище не указано — сборка молчит и ничего не делает", bs.sync_hires(records) is None)
hs.settings = lambda: ("https://storage.yandexcloud.net/opa", "", "", ["S3_KEY_ID и S3_SECRET в .env"])
ok("адрес есть, ключей нет — ничего не выгружаем, файлы на месте", bs.sync_hires(records) is None)
hs.settings = real_settings

ok(".gitignore не пускает архив в репозиторий",
   "\nhires/\n" in open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read())

shutil.rmtree(tmp, ignore_errors=True)

print("\n====== ОРИГИНАЛЫ В ХРАНИЛИЩЕ ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
