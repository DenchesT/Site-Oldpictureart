# -*- coding: utf-8 -*-
"""Ссылки из постов: название выставки и музея ведут туда же, куда в канале.

В постах о походах название выставки — ссылка на её страницу, а музей —
на сайт музея. Телеграм хранит такие ссылки не в тексте, а разметкой
поверх него, и в raw_text их нет — сайт их просто терял. Теперь:

  • сборка читает разметку и складывает ссылки в поле links;
  • у записей, скачанных раньше, links дочитывается один раз;
  • на странице похода заголовок и место становятся ссылками, а то,
    что ни к какому названию не подошло, уходит в блок справа;
  • на странице картины подписанные ссылки попадают в «Источники».

Сети нет: посты подставные. Если установлен Telethon, часть проверок
идёт на его настоящих объектах — там смещения ссылок считаются в UTF-16,
и эмодзи в тексте сдвигает всё, что после него.

Запуск:  python tests/test_links.py
"""

import asyncio
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.chdir(os.path.join(HERE, ".."))
os.environ.setdefault("OPA_OFFLINE_RENDER", "1")
sys.argv = ["build_site.py"]

import build_site as bs

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# ------------------------------------------------------------ подставной пост
class Ent:
    def __init__(self, url=None):
        if url is not None:
            self.url = url


class Msg:
    """Запись канала: текст и ссылки поверх него, как у Telethon."""

    def __init__(self, mid, text="", spans=(), grouped_id=None):
        self.id = mid
        self.raw_text = text
        self.grouped_id = grouped_id
        self._spans = list(spans)

    def get_entities_text(self, cls=None):
        return [(Ent(url), text) for text, url in self._spans]


EXPO = "https://pushkinmuseum.art/events/archive/2025/exhibitions/graphics/index.php?lang=ru&x=1"
SITE = "https://pushkinmuseum.art"
TEXT = ('Выставка "Сокровищница графики"\n(18.03.2025 - 15.06.2025)\n\n'
        'ГМИИ им. А.С. Пушкина, 19.03.2025\n\n#гмии@oldpictureart \n#выставка@oldpictureart')

m = Msg(10, TEXT, [("Сокровищница графики", EXPO), ("ГМИИ им. А.С. Пушкина", SITE),
                   ("19.03.2025", "javascript:alert(1)"), ("#гмии@oldpictureart", None),
                   ("Сокровищница графики", EXPO)])
links = bs.message_links([m])
ok("ссылки под словами читаются", [l["text"] for l in links] ==
   ["Сокровищница графики", "ГМИИ им. А.С. Пушкина"], str(links))
ok("javascript: и прочее не http в страницу не пускаем",
   all(l["url"].startswith("http") for l in links))
ok("одна и та же ссылка — один раз", len(links) == 2)

album = [Msg(12, "", [("хвост", "https://b.example")], grouped_id=5),
         Msg(11, TEXT, [("Сокровищница графики", EXPO)], grouped_id=5)]
ok("ссылки альбома — по порядку записей",
   [l["url"] for l in bs.message_links(album)] == [EXPO, "https://b.example"])


class Broken(Msg):
    def get_entities_text(self, cls=None):
        raise ValueError("битая разметка")


ok("битая разметка поста сборку не роняет", bs.message_links([Broken(1, "x")]) == [])

try:
    from telethon.tl.custom.message import Message
    from telethon.tl.types import (MessageEntityTextUrl, MessageEntityUrl,
                                   MessageEntityHashtag, PeerChannel)
    from telethon.helpers import add_surrogate

    real_text = ('Выставка "Коснуться главного" 🖼\n\n'
                 'Музей русского импрессионизма, 12.02.2025\n\nhttps://rusimp.su/x\n#выставка@oldpictureart')

    def span(sub):
        i = real_text.index(sub)
        return len(add_surrogate(real_text[:i])), len(add_surrogate(sub))

    real = Message(id=20, peer_id=PeerChannel(1), message=real_text, entities=[
        MessageEntityTextUrl(*span("Коснуться главного"), "https://rusimp.su/expo"),
        MessageEntityTextUrl(*span("Музей русского импрессионизма"), "https://rusimp.su"),
        MessageEntityUrl(*span("https://rusimp.su/x")),
        MessageEntityHashtag(*span("#выставка@oldpictureart"))])
    got = bs.message_links([real])
    ok("настоящий пост Telethon: эмодзи перед ссылкой её не сдвигает",
       [l["text"] for l in got] == ["Коснуться главного", "Музей русского импрессионизма"],
       str(got))
except ImportError:
    ok("Telethon не установлен — проверка на настоящих объектах пропущена", True)


# ------------------------------------------------------------ какое название чьё
L = [{"text": 'Выставка "Сокровищница графики"', "url": EXPO},
     {"text": "ГМИИ им. А.С. Пушкина 🖼", "url": SITE},
     {"text": "им.", "url": "https://short.example"},
     {"text": "Коснуться главного", "url": "https://part.example"}]
ok("ссылка на всей строке «Выставка …» узнаёт название", bs.link_for("Сокровищница графики", L) == 0)
ok("эмодзи и кавычки при сравнении не мешают", bs.link_for("ГМИИ им. А.С. Пушкина", L) == 1)
ok("ссылка на части названия тоже годится",
   bs.link_for("Автор неизвестен. Коснуться главного", L) == 3)
ok("короткая подпись ни к чему не липнет", bs.link_for("им.", L[2:3]) == 0
   and bs.link_for("Музей им. Радищева", L[2:3]) is None)
ok("занятая ссылка второй раз не берётся", bs.link_for("Сокровищница графики", L, used={0}) is None)
ok("ё и е — одно", bs.link_for("Ёлки", [{"text": "елки", "url": "https://e.example"}]) == 0)
ok("пустое название — без ссылки", bs.link_for("", L) is None)


# ------------------------------------------------------------ страница похода
visits = json.load(open("visits_meta.json", encoding="utf-8")) if os.path.exists("visits_meta.json") else []
base = next((v for v in visits if v.get("kind") == "выставка" and v.get("title") and v.get("place")), None)
if base is None:
    base = {"kind": "выставка", "title": "Сокровищница графики", "place": "ГМИИ им. А.С. Пушкина",
            "filename": "visit-2025-03-19-test.html", "date": "2025-03-19", "visited": "19.03.2025",
            "images": [], "urls": [], "tags": []}
v = copy.deepcopy(base)
v["links"] = [{"text": f'Выставка "{v["title"]}"', "url": EXPO},
              {"text": v["place"], "url": SITE},
              {"text": "каталог выставки", "url": "https://catalog.example/pdf"}]
page = bs.render_visit_page(v, [v])
h1 = page[page.index("<h1>"):page.index("</h1>")]
h2 = page[page.index("<h2>"):page.index("</h2>")]
ok("заголовок выставки — ссылка на её страницу", 'class="ext-link"' in h1 and bs.h(EXPO) in h1, h1[:160])
ok("место — ссылка на сайт музея", 'class="ext-link"' in h2 and f'href="{SITE}"' in h2, h2[:160])
ok("ссылка открывается в новой вкладке и без доступа к нашей",
   'target="_blank" rel="noopener"' in h1)
ok("& в адресе экранирован", "&amp;x=1" in h1 and "&x=1" not in h1)
ok("не пришедшаяся к названию ссылка — в блоке справа с подписью",
   "каталог выставки</a>" in page and "<h3>Ссылка</h3>" in page)
ok("ссылки заголовка справа не повторяются", page.count(f'href="{SITE}"') == 1)

ok("страница похода без пробелов в конце строк (их чистит @tidy)",
   not [l for l in page.split("\n") if l != l.rstrip()])

plain = copy.deepcopy(base)
plain.pop("links", None)
page2 = bs.render_visit_page(plain, [plain])
ok("без ссылок заголовок остаётся простым текстом", "ext-link" not in page2)

museum = copy.deepcopy(base)
museum.update(kind="музей", title="", links=[{"text": museum["place"], "url": SITE}])
page3 = bs.render_visit_page(museum, [museum])
ok("у похода в музей ссылкой становится сам заголовок — музей",
   f'href="{SITE}"' in page3[page3.index("<h1>"):page3.index("</h1>")] and "<h2>" not in page3)


# ------------------------------------------------------------ страница картины
posts = json.load(open("posts_meta.json", encoding="utf-8")) if os.path.exists("posts_meta.json") else []
if posts:
    p = copy.deepcopy(posts[0])
    p["urls"] = ["https://collection.example/1"]
    p["links"] = [{"text": p.get("museum") or "Музей", "url": "https://museum.example"},
                  {"text": "карточка в собрании", "url": "https://collection.example/1"}]
    bs.prepare_museums(posts, visits)
    pp = bs.render_post_page(p, posts)
    ok("на странице картины подписанная ссылка — в «Источниках» с подписью",
       '>карточка в собрании</a>' in pp and 'href="https://museum.example"' in pp)
    ok("адрес, который есть и подписанным, и голым, — один раз",
       pp.count('href="https://collection.example/1"') == 1)
    ok("«Собрание» ведёт на страницу музея (а с неё — на карту)",
       f'<span>Собрание</span><b><a href="{bs.museum_page(p["museum"].strip())}"' in pp
       or 'href="museums.html#museum-' in pp)


# ------------------------------------------------------------ дочитать у прежних
class Client:
    def __init__(self, msgs, fail=False):
        self.msgs = {m.id: m for m in msgs}
        self.fail = fail
        self.calls = 0

    async def get_messages(self, channel, ids=None):
        self.calls += 1
        if self.fail:
            raise ConnectionError("нет связи")
        return [self.msgs.get(i) for i in ids]


recs = [{"id": 10, "filename": "a.html"},
        {"id": 50, "filename": "b.html"},
        {"id": 70, "filename": "c.html", "links": [{"text": "x", "url": "https://x.example"}]}]
cl = Client([m])            # пост 10 есть, 50 удалён
n = asyncio.run(bs.backfill_links(cl, recs))
ok("прежним записям ссылки дочитаны", recs[0]["links"] == links and n == 2, str(recs[0].get("links")))
ok("удалённому посту — пустой список, чтобы не спрашивать вечно", recs[1]["links"] == [])
ok("записи с ссылками не трогаются", recs[2]["links"][0]["url"] == "https://x.example")

cl2 = Client([])
asyncio.run(bs.backfill_links(cl2, recs))
ok("когда дочитывать нечего, в канал не ходим", cl2.calls == 0)

lost = [{"id": 10, "filename": "a.html"}]
asyncio.run(bs.backfill_links(Client([], fail=True), lost))
ok("при сбое связи запись не помечается прочитанной", "links" not in lost[0])


# ------------------------------------------------------------ --refresh и ссылки
same = {"id": 10, "filename": "visit.html", "kind": "выставка", "raw": TEXT + "\n",
        "links": [{"text": "Сокровищница графики", "url": "https://old.example"}]}
n = asyncio.run(bs.refetch_texts(Client([m]), [same]))
ok("поменялась только ссылка — это тоже правка", n == 1 and same["links"] == links, str(same["links"]))

visit_rec = {"id": 10, "filename": "visit.html", "kind": "выставка", "raw": "старый текст", "links": links}
n = asyncio.run(bs.refetch_texts(Client([m]), [visit_rec]))
ok("текст похода проверяется разбором похода, а не картины",
   n == 1 and visit_rec["raw"].startswith('Выставка "Сокровищница'), visit_rec["raw"][:40])

vs = [{"id": 10, "filename": "visit-2025-03-19-sokrovischnitsa.html", "title": "Сокровищница графики",
       "place": "ГМИИ им. А.С. Пушкина", "kind": "выставка"}]
ok("--refresh находит поход по месту", bs.match_posts(vs, "Пушкина") == vs)


print("\n====== ССЫЛКИ ИЗ ПОСТОВ ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
