# -*- coding: utf-8 -*-
"""Правка старого поста доезжает до сайта.

Пост в канале можно подправить и через год, но сайт о правке не узнавал:
скачанные посты отсеиваются по processed_ids.json и второй раз не
читаются. Появились две вещи:

  • python build_site.py --refresh …  — притягивает нынешний текст
    указанных постов из канала (снимки не перекачиваются);
  • refresh_posts() — перечитывает сохранённый текст тем разбором, что
    сейчас в коде; вызывается и в сборке, и в rebuild_pages.py, так что
    правка текста прямо в posts_meta.json видна без Телеграма.

В проверках сети нет: Телеграм подставной. Проверяется то, что может
тихо сломаться:
  • пост находится по номеру, ссылке на канал, адресу страницы (в том
    числе прежнему) и куску названия;
  • подпись альбома собирается из всех записей группы по порядку;
  • удалённый из канала пост и неразбираемый текст не портят базу;
  • при смене названия страница переезжает, прежний адрес остаётся в
    old_filenames (с него потом кладётся перенаправление), а карточка
    ссылки стирается, чтобы её нарисовали заново;
  • перечитывание ничего не меняет у настоящей базы сайта.

Запуск:  python tests/test_refresh.py
"""

import asyncio
import copy
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.chdir(os.path.join(HERE, ".."))
os.environ.setdefault("OPA_OFFLINE_RENDER", "1")

import build_site as bs

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


def tg(artist, title, museum="Национальная галерея Ирландии", tail="", tag="sisley"):
    """Текст поста так, как его отдаёт Телеграм: без перевода строки в конце."""
    return (f"{artist}\n⸻\n{title}\n⸻\nХолст, масло, 54 x 73 см\n⸻\n"
            f"{museum}\n⸻\n{tail}#{tag}@oldpictureart\n#картина@oldpictureart")


def raw_of(*a, **kw):
    """Тот же текст, как он лежит в базе: сборка склеивает записи группы
    через перевод строки, поэтому в конце он есть."""
    return tg(*a, **kw) + "\n"


def post(pid, artist, title, filename, tag="sisley", **extra):
    p = {"id": pid, "date": "2025-03-17", "filename": filename,
         "images": [f"images/{filename[:-5]}-1.jpg"], "hires": [], "thumbs": []}
    p.update(bs.parse_post(raw_of(artist, title, tag=tag)))
    p.update(extra)
    return p


def base():
    return [
        post(101, "Альфред Сислей", "La Prairie (Луг), 1875", "sisley-lug-1875.html",
             old_filenames=["2025-03-17-alfred-sisley.html"]),
        post(202, "Фредерик Чайльд Гассам", "Union Square in Spring (Юнион-сквер весной), 1896",
             "hassam-yunion-skver-vesnoi-1896.html", tag="hassam"),
    ]


# ------------------------------------------------------------ кого перечитывать
posts = base()
ok("номер поста находит пост", bs.match_posts(posts, "101") == [posts[0]])
ok("ссылка на канал находит пост",
   bs.match_posts(posts, "https://t.me/oldpictureart/202") == [posts[1]])
ok("адрес страницы находит пост",
   bs.match_posts(posts, "sisley-lug-1875.html") == [posts[0]])
ok("ссылка на страницу сайта находит пост",
   bs.match_posts(posts, "https://oldpictureart.ru/sisley-lug-1875.html") == [posts[0]])
ok("прежний адрес страницы находит пост",
   bs.match_posts(posts, "2025-03-17-alfred-sisley.html") == [posts[0]])
ok("имя страницы без .html находит пост",
   bs.match_posts(posts, "sisley-lug-1875") == [posts[0]])
ok("кусок названия находит пост", bs.match_posts(posts, "union square") == [posts[1]])
ok("имя художника находит пост", bs.match_posts(posts, "Сислей") == [posts[0]])
ok("чужое слово не находит ничего", bs.match_posts(posts, "Рембрандт") == [])
ok("пустое слово не находит ничего", bs.match_posts(posts, "  ") == [])

ok("без ключа --refresh перечитывать нечего",
   bs.refresh_targets(posts, ["--rescan"]) is None)
ok("--refresh без слов — все посты",
   bs.refresh_targets(posts, ["--refresh"]) == posts)
ok("--refresh all — все посты", bs.refresh_targets(posts, ["--refresh", "all"]) == posts)
ok("--refresh все — все посты", bs.refresh_targets(posts, ["--refresh", "все"]) == posts)
ok("--refresh с двумя словами — оба поста",
   bs.refresh_targets(posts, ["--refresh", "101", "union square"]) == posts)
ok("один и тот же пост не повторяется",
   bs.refresh_targets(posts, ["--refresh", "101", "Сислей"]) == [posts[0]])
ok("следующий ключ обрывает список",
   bs.refresh_targets(posts, ["--refresh", "101", "--no-update"]) == [posts[0]])
ok("чужое слово — пустой список, а не вся база",
   bs.refresh_targets(posts, ["--refresh", "Рембрандт"]) == [])


# ------------------------------------------------------------ подставной Телеграм
class FakeMsg:
    def __init__(self, mid, text="", grouped_id=None):
        self.id = mid
        self.raw_text = text
        self.grouped_id = grouped_id


class FakeClient:
    """Отдаёт записи по номерам, как Telethon: чего нет — None."""

    def __init__(self, msgs):
        self.msgs = {m.id: m for m in msgs}
        self.batches = []

    async def get_messages(self, channel, ids=None):
        self.batches.append(list(ids))
        return [self.msgs.get(i) for i in ids]


def refetch(posts, msgs):
    client = FakeClient(msgs)
    changed = asyncio.run(bs.refetch_texts(client, posts))
    return changed, client


NEW_TITLE = "La Prairie (Луг), 1875"
posts = base()
changed, client = refetch(
    [posts[0]], [FakeMsg(101, tg("Альфред Сислей", "Луг (La Prairie), 1875"))])
ok("правленый текст притянулся", changed == 1
   and "Луг (La Prairie)" in posts[0]["raw"], posts[0]["raw"][:40])
ok("номера запрашиваются пачками по сотне",
   all(len(b) <= 100 for b in client.batches) and len(client.batches) == 1,
   str([len(b) for b in client.batches]))

posts = base()
changed, _ = refetch([posts[0]], [FakeMsg(101, tg("Альфред Сислей", NEW_TITLE))])
ok("неизменившийся текст не считается правкой", changed == 0)

posts = base()
album = [FakeMsg(100, "", grouped_id=7),
         FakeMsg(101, tg("Альфред Сислей", "Луг, 1875"), grouped_id=7),
         FakeMsg(102, "Хвост подписи", grouped_id=7),
         FakeMsg(103, "Соседний пост, не из альбома")]
changed, _ = refetch([posts[0]], album)
ok("подпись альбома собирается по порядку", changed == 1
   and posts[0]["raw"].endswith("Хвост подписи\n")
   and "Соседний пост" not in posts[0]["raw"], posts[0]["raw"][-60:])

posts = base()
was = copy.deepcopy(posts[0])
changed, _ = refetch([posts[0]], [FakeMsg(999, "чужой пост")])
ok("удалённый из канала пост не портит базу", changed == 0 and posts[0] == was)

posts = base()
was = copy.deepcopy(posts[0])
changed, _ = refetch([posts[0]], [FakeMsg(101, "Просто текст без разделителей")])
ok("неразбираемый текст не затирает прежний", changed == 0 and posts[0] == was)

posts = base()
was = copy.deepcopy(posts[0])
changed, _ = refetch([posts[0]], [FakeMsg(101, "   ")])
ok("пустой текст не затирает прежний", changed == 0 and posts[0] == was)


# ------------------------------------------------------------ перечитывание базы
posts = base()
ok("перечитывание ничего не трогает без правок", bs.refresh_posts(posts) == 0)

posts = base()
posts[0]["raw"] = raw_of("Альфред Сислей", "Луг (La Prairie), 1876")
ok("правка текста в базе меняет разобранные поля", bs.refresh_posts(posts) == 1
   and posts[0]["title"] == "Луг (La Prairie), 1876")
ok("год создания пересчитался по новому названию", posts[0]["creation_year"] == 1876)
ok("перечитывание второй раз уже ничего не меняет", bs.refresh_posts(posts) == 0)

posts = base()
posts[0]["raw"] = "Совсем не пост"
was = copy.deepcopy(posts[0])
ok("неразбираемый текст в базе оставляет запись как была",
   bs.refresh_posts(posts) == 0 and posts[0] == was)

posts = base()
posts[0].pop("raw")
was = copy.deepcopy(posts[0])
ok("запись без текста не трогается", bs.refresh_posts(posts) == 0 and posts[0] == was)


# ------------------------------------------------------------ карточка ссылки
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "images", "cards"), exist_ok=True)
old_out = bs.OUTPUT_DIR
bs.OUTPUT_DIR = tmp


def with_card(p):
    p["card"] = "images/cards/" + p["filename"][:-5] + ".jpg"
    with open(os.path.join(tmp, p["card"]), "w") as f:
        f.write("картинка")
    return p


posts = base()
card_path = os.path.join(tmp, with_card(posts[0])["card"])
posts[0]["raw"] = raw_of("Альфред Сислей", "Луг (La Prairie), 1875")
bs.refresh_posts(posts)
ok("при смене названия карточка ссылки стирается",
   "card" not in posts[0] and not os.path.exists(card_path))

posts = base()
card_path = os.path.join(tmp, with_card(posts[0])["card"])
posts[0]["raw"] = raw_of("Альфред Сислей", NEW_TITLE, museum="Музей д'Орсе")
bs.refresh_posts(posts)
ok("при смене музея карточка ссылки тоже стирается",
   "card" not in posts[0] and not os.path.exists(card_path))

posts = base()
card_path = os.path.join(tmp, with_card(posts[0])["card"])
posts[0]["raw"] = raw_of("Альфред Сислей", NEW_TITLE, tail="Новое описание картины.\n⸻\n")
bs.refresh_posts(posts)
ok("правка описания карточку не трогает",
   posts[0].get("card") and os.path.exists(card_path))
ok("новое описание попало в запись",
   posts[0]["description"] == "Новое описание картины.", posts[0]["description"])

bs.OUTPUT_DIR = old_out


# ------------------------------------------------------------ переезд страницы
posts = base()
posts[0]["raw"] = raw_of("Альфред Сислей", "Луг (La Prairie), 1875")
bs.refresh_posts(posts)
bs.prepare_slugs(posts)
moved = bs.rename_pages(posts)
ok("страница переехала на новое имя", moved and posts[0]["filename"] != "sisley-lug-1875.html",
   posts[0]["filename"])
ok("прежний адрес остался для перенаправления",
   "sisley-lug-1875.html" in posts[0]["old_filenames"]
   and "2025-03-17-alfred-sisley.html" in posts[0]["old_filenames"],
   str(posts[0].get("old_filenames")))
ok("соседний пост при этом не переехал",
   posts[1]["filename"] == "hassam-yunion-skver-vesnoi-1896.html")


# ------------------------------------------------------------ настоящая база
if os.path.exists("posts_meta.json"):
    real = json.load(open("posts_meta.json", encoding="utf-8"))
    before = copy.deepcopy(real)
    ok("перечитывание не меняет настоящую базу сайта",
       bs.refresh_posts(real) == 0 and real == before)
    ok("у всех постов сохранён текст", all(p.get("raw") for p in real),
       str([p["filename"] for p in real if not p.get("raw")][:3]))

print("\n====== ПРАВКА СТАРОГО ПОСТА ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
