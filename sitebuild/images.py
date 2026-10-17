# -*- coding: utf-8 -*-
"""Картинки: сжатие, миниатюры, копии для лупы, карточки для соцсетей, размеры.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
import hires_store
import logging
from .config import (
    CARD_DIR, JPEG_QUALITY, MAX_IMAGE_DIMENSION, MAX_IMAGE_SIZE_MB, OUTPUT_DIR, SIZES_FILE,
    THUMB_DIMENSION, THUMB_DIR, THUMB_QUALITY, VIEW_DIMENSION, VIEW_DIR, VIEW_QUALITY,
)
from .text import load_json, save_json
from .html import russian_title, short_artist

logger = logging.getLogger("build_site")

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    Image = ImageDraw = ImageFont = None
    PIL_AVAILABLE = False

if PIL_AVAILABLE:
    # Картинка, у которой не хватает последних байтов, обычно приходит
    # из оборвавшейся загрузки: видно её целиком, кроме нижней полоски
    # в несколько пикселей. По умолчанию Pillow на такой бросает
    # «image file is truncated», и миниатюра с карточкой не делаются
    # вовсе. Показать почти целую картинку лучше, чем не показать
    # никакой, — но в логе о ней сказано, чтобы файл можно было
    # перекачать.
    try:
        from PIL import ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True
    except ImportError:
        pass

def compress_if_huge(fp):
    if not PIL_AVAILABLE or not os.path.exists(fp): return fp
    try:
        if os.path.getsize(fp)/1024/1024 < MAX_IMAGE_SIZE_MB: return fp
        img = Image.open(fp)
        if img.mode in ("RGBA","P","LA"): img = img.convert("RGB")
        img.thumbnail((MAX_IMAGE_DIMENSION,MAX_IMAGE_DIMENSION), Image.LANCZOS)
        base, ext = os.path.splitext(fp)
        np = base+".jpg" if ext.lower() not in (".jpg",".jpeg") else fp
        if np != fp:
            try: os.remove(fp)
            except OSError: pass
        img.save(np, "JPEG", quality=JPEG_QUALITY, optimize=True)
        logger.info(f"Сжато: {os.path.getsize(np)/1024/1024:.1f}MB")
        return np
    except Exception as e:
        logger.warning(f"Не сжато: {e}")
        return fp

def make_thumbnail(src, slug, idx):
    if not PIL_AVAILABLE or not os.path.exists(src): return ""
    os.makedirs(THUMB_DIR, exist_ok=True)
    sfx = "" if idx == 1 else f"-{idx}"
    tn = f"{slug}{sfx}.jpg"
    tp = os.path.join(THUMB_DIR, tn)
    if os.path.exists(tp): return f"images/thumbs/{tn}"
    try:
        img = Image.open(src)
        if img.mode in ("RGBA","P","LA"): img = img.convert("RGB")
        img.thumbnail((THUMB_DIMENSION,THUMB_DIMENSION), Image.LANCZOS)
        img.save(tp, "JPEG", quality=THUMB_QUALITY, optimize=True)
        return f"images/thumbs/{tn}"
    except Exception as e:
        # Имя файла в предупреждении обязательно: без него «image file is
        # truncated» сообщает, что где-то среди полутора тысяч картинок
        # одна битая, и искать её нечем.
        logger.warning(f"Миниатюра не сделана — {src}: {e}")
        return ""
CARD_W, CARD_H = 1200, 630
CARD_BG = (21, 26, 34)          # тёмно-синие чернила
CARD_CREAM = (242, 237, 227)
CARD_OCHRE = (201, 163, 94)
CARD_MUTED = (150, 160, 174)

# Шрифт ищем среди системных: свои у сайта подключаются из сети, а карточку
# рисует Pillow — ему нужен файл. Первым идёт fonts/ в самом проекте, чтобы
# можно было положить туда Old Standard TT и получить точную типографику сайта.
FONT_CANDIDATES = {
    "regular": ["fonts/OldStandardTT-Regular.ttf", "fonts/regular.ttf",
                "C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/georgia.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
                "/System/Library/Fonts/Supplemental/Times New Roman.ttf"],
    "bold":    ["fonts/OldStandardTT-Bold.ttf", "fonts/bold.ttf",
                "C:/Windows/Fonts/timesbd.ttf", "C:/Windows/Fonts/georgiab.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
                "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"],
    "mono":    ["fonts/IBMPlexMono-Regular.ttf", "fonts/mono.ttf",
                "C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
                "/System/Library/Fonts/Supplemental/Courier New.ttf"],
}
_font_files = {}


def font_file(kind):
    """Путь к шрифту нужного начертания или None, если ничего не нашлось."""
    if kind not in _font_files:
        _font_files[kind] = next((p for p in FONT_CANDIDATES[kind] if os.path.exists(p)), None)
    return _font_files[kind]


def _font(kind, size):
    path = font_file(kind)
    return ImageFont.truetype(path, size) if path else None


def _wrap(draw, text, font, width, max_lines):
    """Разбивает строку по словам под заданную ширину. Последняя строка,
    если не влезла, обрывается многоточием."""
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        probe = (cur + " " + w).strip()
        if draw.textlength(probe, font=font) <= width or not cur:
            cur = probe
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and (len(" ".join(lines)) < len(text or "")):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        lines[-1] = last.rstrip(" ,;") + "…"
    return lines


def _fit(draw, text, kind, big, small, width, max_lines):
    """Подбирает кегль так, чтобы текст уложился в отведённые строки."""
    size = big
    while size > small:
        f = _font(kind, size)
        if f is None:
            return None, []
        lines = _wrap(draw, text, f, width, max_lines + 1)
        if len(lines) <= max_lines:
            return f, lines
        size -= 2
    f = _font(kind, small)
    return f, _wrap(draw, text, f, width, max_lines)


def make_card(post):
    """Карточка 1200×630 для превью ссылки. Пустая строка — если не вышло."""
    # Оба начертания обязательны: подбор кегля опирается на реальный шрифт,
    # и подстановка встроенного растрового превратила бы подпись в кашу.
    if not PIL_AVAILABLE or not font_file("regular") or not font_file("bold"):
        return ""
    src = (post.get("images") or [None])[0]
    if not src:
        return ""
    os.makedirs(CARD_DIR, exist_ok=True)
    name = f"{post['filename'][:-5]}.jpg"
    out = os.path.join(CARD_DIR, name)
    if os.path.exists(out):
        return f"images/cards/{name}"
    try:
        card = Image.new("RGB", (CARD_W, CARD_H), CARD_BG)
        draw = ImageDraw.Draw(card)

        # Картина слева, целиком и по центру своей половины
        art = Image.open(os.path.join(OUTPUT_DIR, src))
        if art.mode != "RGB":
            art = art.convert("RGB")
        box_w, box_h = 540, 510
        art.thumbnail((box_w, box_h), Image.LANCZOS)
        ax = 56 + (box_w - art.width) // 2
        ay = (CARD_H - art.height) // 2
        draw.rectangle([ax - 2, ay - 2, ax + art.width + 1, ay + art.height + 1],
                       outline=(70, 82, 100))
        card.paste(art, (ax, ay))

        # Подпись справа
        x = 56 + box_w + 56
        w = CARD_W - x - 56
        mono = _font("mono", 20)
        if mono:
            draw.text((x, 92), "OLD PICTURE ART", font=mono, fill=CARD_OCHRE)
        draw.line([x, 128, x + 64, 128], fill=CARD_OCHRE, width=2)

        y = 160
        af, alines = _fit(draw, short_artist(post.get("artist", ""), 60), "bold", 46, 30, w, 2)
        for line in alines:
            draw.text((x, y), line, font=af, fill=CARD_CREAM)
            y += af.size + 8
        y += 10
        tf, tlines = _fit(draw, russian_title(post.get("title", "")) or post.get("title", ""),
                          "regular", 34, 24, w, 3)
        for line in tlines:
            draw.text((x, y), line, font=tf, fill=(206, 214, 224))
            y += tf.size + 6

        foot = " · ".join(v for v in (str(post.get("creation_year") or ""),
                                      (post.get("museum") or "").strip()) if v)
        mf = _font("mono", 18)
        if foot and mf:
            lines = _wrap(draw, foot, mf, w, 2)
            fy = CARD_H - 76 - (len(lines) - 1) * 26
            for line in lines:
                draw.text((x, fy), line, font=mf, fill=CARD_MUTED)
                fy += 26

        card.save(out, "JPEG", quality=88, optimize=True, progressive=True)
        return f"images/cards/{name}"
    except Exception as e:
        logger.warning(f"Карточка ссылки не сделана — {post.get('filename', '?')}: {e}")
        return ""


def build_cards(posts):
    """Досоздаёт карточки там, где их ещё нет."""
    if not PIL_AVAILABLE:
        return 0
    if not font_file("regular") or not font_file("bold"):
        logger.info("Карточки ссылок пропущены: не нашёлся шрифт "
                    "(положите ttf в папку fonts/ — см. README)")
        return 0
    made = 0
    for post in posts:
        if post.get("card"):
            continue
        c = make_card(post)
        if c:
            post["card"] = c
            made += 1
    if made:
        logger.info(f"Карточек ссылок создано: {made}")
    return made


def make_view(src, slug, idx):
    """Копия оригинала шириной до 2000 пикселей — то, что показывает лупа.

    Если оригинал и так меньше предела, копия не нужна: лупа возьмёт его
    самого. Пустая строка означает «отдельной копии нет».
    """
    if not PIL_AVAILABLE or not src or not os.path.exists(src):
        return ""
    os.makedirs(VIEW_DIR, exist_ok=True)
    vn = f"{slug}-{idx}.jpg"
    vp = os.path.join(VIEW_DIR, vn)
    if os.path.exists(vp):
        return f"images/views/{vn}"
    try:
        img = Image.open(src)
        if max(img.size) <= VIEW_DIMENSION and os.path.getsize(src) < 1_500_000:
            return ""
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.thumbnail((VIEW_DIMENSION, VIEW_DIMENSION), Image.LANCZOS)
        img.save(vp, "JPEG", quality=VIEW_QUALITY, optimize=True, progressive=True)
        return f"images/views/{vn}"
    except Exception as e:
        logger.warning(f"Копия для просмотра: {e}")
        return ""


def build_views(records):
    """Досоздаёт копии для просмотра там, где их ещё нет.

    Считается по оригиналам: у записи без -hires- разглядывать нечего,
    лупа и так показывает ту картинку, что на странице.
    """
    if not PIL_AVAILABLE:
        return 0
    made = 0
    for rec in records:
        hires = rec.get("hires") or []
        if not hires or len(rec.get("views") or []) == len(hires):
            continue
        slug = rec["filename"][:-5]
        views = []
        for i, hr in enumerate(hires, 1):
            # Оригинал мог уже уехать в хранилище — тогда его копия лежит
            # в архиве hires/, копию для лупы делаем из неё.
            v = make_view(hires_store.local_path(hr) or os.path.join(OUTPUT_DIR, hr), slug, i)
            views.append(v)
            if v:
                made += 1
        rec["views"] = views
    if made:
        logger.info(f"Копий для просмотра создано: {made}")
    return made
_image_sizes = None


def image_size(rel_path):
    """Размеры картинки в пикселях по пути вида images/xxx.jpg.

    Нужны, чтобы проставить width и height у <img>. Без них браузер не знает,
    сколько места занять, рисует страницу, а потом раздвигает её под каждую
    подгрузившуюся миниатюру: на телефоне опись из восьмидесяти строк
    дёргается под пальцем. С размерами место резервируется сразу.

    Считанное складываем в image_sizes.json — заново открывать полтысячи
    файлов при каждой пересборке незачем.
    """
    global _image_sizes
    if _image_sizes is None:
        _image_sizes = load_json(SIZES_FILE, {})
    if not rel_path:
        return None
    hit = _image_sizes.get(rel_path)
    if hit is not None:
        return tuple(hit) if hit else None
    if not PIL_AVAILABLE:
        return None
    try:
        with Image.open(os.path.join(OUTPUT_DIR, rel_path)) as im:
            size = [im.width, im.height]
    except Exception:
        size = []          # запоминаем и неудачу, чтобы не пытаться снова
    _image_sizes[rel_path] = size
    return tuple(size) if size else None


def save_image_sizes():
    if _image_sizes:
        save_json(SIZES_FILE, _image_sizes)


def size_attrs(rel_path):
    """Готовые атрибуты width/height или пустая строка."""
    wh = image_size(rel_path)
    return f' width="{wh[0]}" height="{wh[1]}"' if wh else ""

__all__ = [
    'Image',
    'ImageDraw',
    'ImageFont',
    'PIL_AVAILABLE',
    'compress_if_huge',
    'make_thumbnail',
    'CARD_W',
    'CARD_H',
    'CARD_BG',
    'CARD_CREAM',
    'CARD_OCHRE',
    'CARD_MUTED',
    'FONT_CANDIDATES',
    '_font_files',
    'font_file',
    '_font',
    '_wrap',
    '_fit',
    'make_card',
    'build_cards',
    'make_view',
    'build_views',
    '_image_sizes',
    'image_size',
    'save_image_sizes',
    'size_attrs',
]
