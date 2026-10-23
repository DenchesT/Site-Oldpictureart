# -*- coding: utf-8 -*-
"""Мелочи оформления и веса страниц.

  • типографика текста из канала: « - » → « — », "кавычки" → «ёлочки»,
    названия на языке оригинала не трогаем;
  • миниатюры не крупнее THUMB_DIMENSION: прежние, под 1200px, сборка
    уменьшает сама, и width/height у <img> считываются заново;
  • происхождение — нумерованный список без «1)» в тексте;
  • у похода в музей заголовок вкладки не совпадает со страницей музея.

Запуск:  python tests/test_polish.py
"""

import collections
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

from sitebuild import images as im  # noqa: E402
from sitebuild.text import typo_ru  # noqa: E402

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# ---------- типографика ----------
ok("дефис между словами — тире с неразрывным пробелом",
   typo_ru("флаг - чёрный, белый и красный - виден") == "флаг — чёрный, белый и красный — виден")
ok("прямые кавычки — ёлочки", typo_ru('картина "Rue Monier mit Fahnen", 1878 г.') == "картина «Rue Monier mit Fahnen», 1878 г.")
ok("дефис в слове и в датах остаётся", typo_ru("Унтер-ден-Линден, 1880-1890 гг.") == "Унтер-ден-Линден, 1880-1890 гг.")
ok("текст без кириллицы не трогаем", typo_ru('Paysage - "Le Rêve"') == 'Paysage - "Le Rêve"')
ok("непарная кавычка остаётся как есть", typo_ru('один "два - три') == 'один "два — три')
ok("пустое — пустое", typo_ru("") == "" and typo_ru(None) is None)

# ---------- миниатюры ----------
ok("миниатюры делаются не крупнее 600px", im.THUMB_DIMENSION <= 600)
if im.PIL_AVAILABLE:
    from PIL import Image
    tmp = tempfile.mkdtemp()
    saved_out, saved_sizes = im.OUTPUT_DIR, im._image_sizes
    try:
        im.OUTPUT_DIR = tmp
        os.makedirs(os.path.join(tmp, "images", "thumbs"))
        big = os.path.join(tmp, "images", "thumbs", "x.jpg")
        Image.new("RGB", (1200, 800), (120, 90, 60)).save(big, "JPEG", quality=90)
        small = os.path.join(tmp, "images", "thumbs", "y.jpg")
        Image.new("RGB", (400, 300), (20, 90, 60)).save(small, "JPEG", quality=80)
        before_small = os.path.getmtime(small)
        im._image_sizes = {"images/thumbs/x.jpg": [1200, 800], "images/thumbs/y.jpg": [400, 300]}
        recs = [{"thumbs": ["images/thumbs/x.jpg", "images/thumbs/y.jpg"]}, {"thumbs": []}, {}]
        n = im.shrink_thumbs(recs)
        with Image.open(big) as i2:
            size = i2.size
        ok("крупная миниатюра уменьшена до THUMB_DIMENSION, пропорции те же",
           n == 1 and size == (im.THUMB_DIMENSION, im.THUMB_DIMENSION * 2 // 3), f"{n} {size}")
        ok("…маленькую не трогаем", os.path.getmtime(small) == before_small)
        ok("…запомненные размеры уменьшенной забыты, остальные целы",
           "images/thumbs/x.jpg" not in im._image_sizes and im._image_sizes.get("images/thumbs/y.jpg") == [400, 300])
        ok("…второй проход ничего не делает", im.shrink_thumbs(recs) == 0)
        ok("…и нового размера width/height", im.size_attrs("images/thumbs/x.jpg") == f' width="{size[0]}" height="{size[1]}"')
    finally:
        im.OUTPUT_DIR, im._image_sizes = saved_out, saved_sizes
        shutil.rmtree(tmp, ignore_errors=True)

# ---------- собранный сайт ----------
DOCS = os.path.join(ROOT, "docs")
if os.path.exists(os.path.join(DOCS, "index.html")):
    pages = [f for f in os.listdir(DOCS) if f.endswith(".html")]
    hist = [f for f in pages if 'class="history"' in open(os.path.join(DOCS, f), encoding="utf-8").read()]
    bad = [f for f in hist if re.search(r'<section class="history">.*?<li>\d+[).]\s', open(os.path.join(DOCS, f), encoding="utf-8").read(), re.S)]
    ok("происхождение — без «1)» в тексте пунктов", hist and not bad, ", ".join(bad[:3]))
    titles = collections.defaultdict(list)
    for f in pages:
        head = open(os.path.join(DOCS, f), encoding="utf-8").read(3000)
        if 'http-equiv="refresh"' in head:
            continue
        t = re.search(r"<title>(.*?)</title>", head, re.S)
        if t:
            titles[t.group(1).strip()].append(f)
    dup = {t: fs for t, fs in titles.items() if len(fs) > 1}
    ok("у страниц нет одинаковых заголовков вкладки", not dup, "; ".join(f"{t}: {fs}" for t, fs in list(dup.items())[:3]))
    thumbs = os.path.join(DOCS, "images", "thumbs")
    if im.PIL_AVAILABLE and os.path.isdir(thumbs):
        from PIL import Image
        fat = []
        for f in os.listdir(thumbs):
            with Image.open(os.path.join(thumbs, f)) as i3:
                if max(i3.size) > im.THUMB_DIMENSION:
                    fat.append(f)
        ok("в docs/images/thumbs нет миниатюр крупнее нужного (после сборки)", not fat, ", ".join(fat[:3]))

print("\n====== ОФОРМЛЕНИЕ И ВЕС ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra and not passed else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
