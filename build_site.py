import asyncio
import os
import re
import sys
import json
import shutil
import subprocess
import logging
import random
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import quote
from collections import defaultdict
from html import escape as h
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('parser.log', encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

REQUIRED_PACKAGES = ["telethon", "Pillow", "TelethonFakeTLS"]

def auto_update_modules():
    logger.info("Проверка модулей...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade"] + REQUIRED_PACKAGES + ["--quiet"])
        logger.info("Модули актуальны!")
    except Exception as e:
        logger.warning(f"Ошибка: {e}")

# Модули обновляем только при реальном запуске парсера. Раньше pip дёргался
# при любом импорте файла, из-за чего страницы нельзя было пересобрать офлайн.
if __name__ == "__main__" and "--no-update" not in sys.argv:
    auto_update_modules()

try:
    from telethon import TelegramClient
    import TelethonFakeTLS
    TELETHON_AVAILABLE = True
except ImportError:
    TelegramClient = None
    TelethonFakeTLS = None
    TELETHON_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from site_common import head_common, scroll_top_button, theme_button, COMMON_JS, SCROLL_TOP_JS, BASE_URL

def load_dotenv(path=".env"):
    if not os.path.exists(path): return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

load_dotenv()

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
PHONE = os.environ.get("PHONE")


def require_credentials():
    """Проверяем .env только перед походом в Telegram, а не при импорте файла."""
    if not (API_ID and API_HASH and PHONE):
        raise SystemExit("✕ Нужен .env с API_ID, API_HASH, PHONE")
    if not TELETHON_AVAILABLE:
        raise SystemExit("✕ Не установлены telethon / TelethonFakeTLS")
    logger.info(f"Аккаунт: {PHONE}")
    return int(API_ID), API_HASH, PHONE

CHANNEL_URL = "https://t.me/oldpictureart"
OUTPUT_DIR = "docs"
IMAGES_DIR = "docs/images"
META_FILE = "posts_meta.json"
PROCESSED_FILE = "processed_ids.json"
DICTIONARY_FILE = "medium_dictionary.json"

MAX_IMAGE_SIZE_MB = 100
MAX_IMAGE_DIMENSION = 4096
JPEG_QUALITY = 95
THUMB_DIR = "docs/images/thumbs"
THUMB_DIMENSION = 1200
THUMB_QUALITY = 90

PROXY_LIST = [
    {'server': '62.113.59.20', 'port': 443, 'secret': '3f71a99978cf97e115dc89cc80aeca1f706574726f766963682e7275'},
    {'server': '138.226.237.34', 'port': 8443, 'secret': '5a76b164eadb451a845bfae212bf864973616D73756E672E636F6D'},
]

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

async def connect_with_proxy(api_id, api_hash, phone, proxy_list):
    for i, cfg in enumerate(proxy_list, 1):
        logger.info(f"Прокси #{i}: {cfg['server']}:{cfg['port']}")
        try:
            client = TelegramClient(f"session_{i}", api_id, api_hash,
                connection=TelethonFakeTLS.ConnectionTcpMTProxyFakeTLS,
                proxy=(cfg['server'], cfg['port'], cfg['secret']))
            await client.start(phone=phone)
            logger.info(f"Подключено через прокси #{i}")
            return client
        except Exception as e:
            logger.error(f"Прокси #{i} не работает: {str(e)[:80]}")
    raise SystemExit("Все прокси не работают!")

def load_dictionary():
    default = {
        "materials": ["холст","бумага","картон","дерево","доска","металл","стекло","тонированная бумага","рифлёная бумага","тонированная рифлёная бумага","пергамент","шёлк","ткань","медь","цинк","алюминий","дуб","сосна","фанера","оргалит","двп","дсп","наждачная бумага","крафт-бумага","ватман","калька","береста","кожа","кость","слоновая кость","перламутр","мрамор","гранит","известняк","гипс","терракота","майолика"],
        "techniques": ["масло","акварель","гуашь","темпера","пастель","уголь","карандаш","графит","тушь","сепия","сангина","мел","акрил","чернила","белила","лак","золото","серебро","бронза","эмаль","керамика","фарфор","гобелен","мозаика","литография","офорт","гравюра","ксилография","шелкография","тушь-сепия","акварель-сепия","белая гуашь","чёрный мел","итальянский карандаш","свинцовый карандаш","серебряный штифт","соус","бистр","лавис","акватинта","меццо-тинто","сухая игла","монотипия","резцовая гравюра","пунктир"],
        "unknown_words": []
    }
    if os.path.exists(DICTIONARY_FILE):
        with open(DICTIONARY_FILE, encoding="utf-8") as f:
            saved = json.load(f)
            for k in default:
                if k not in saved: saved[k] = default[k]
            return saved
    return default

def save_dictionary(d):
    with open(DICTIONARY_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def parse_medium_details(medium_text):
    if not medium_text: return {"material":"","techniques":[],"size":""}
    d = load_dictionary()
    text = medium_text.strip().rstrip(".")
    size = ""
    for p in [r'(\d+[,.]?\d*\s*[xх×]\s*\d+[,.]?\d*\s*(?:см|mm|мм|m|м)?)', r'(\d+[,.]?\d*\s*(?:см|mm|мм|m|м)\s*[xх×]\s*\d+[,.]?\d*\s*(?:см|mm|мм|m|м)?)', r'(\d+[,.]?\d*\s*[xх×]\s*\d+[,.]?\d*)']:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            size = m.group(1).strip()
            text = text.replace(m.group(0),"").strip().rstrip(",.").strip()
            break
    for mat in d["materials"]:
        if mat in text.lower():
            idx = text.lower().find(mat)
            end_idx = idx + len(mat)
            if end_idx < len(text) and text[end_idx] != ',':
                text = text[:end_idx] + ',' + text[end_idx:]
            break
    parts = [p.strip() for p in text.split(",") if p.strip()]
    material, techniques = "", []
    sw = re.compile(r'^\d+[,.]?\d*\s*(?:[xх×]|см|mm|мм|m|м)')
    for part in parts:
        pl = part.lower().strip()
        if sw.match(part) or re.match(r'^\d+[,.]?\d*$', part): continue
        if re.search(r'\d+[,.]?\d*\s*[xх×]\s*\d+', part): continue
        found = False
        for mat in d["materials"]:
            if mat in pl:
                if not material: material = part
                found = True
                break
        if found: continue
        for tech in d["techniques"]:
            if tech in pl:
                techniques.append(part)
                found = True
                break
        if found: continue
        if len(part) > 2 and not re.search(r'\d{3,}', part):
            mkw = ["бумаг","холст","картон","дерев","доск","металл","стекл","ткань","шёлк","кож","кость","камень"]
            if any(kw in pl for kw in mkw):
                if not material: material = part
                if part not in d["materials"]:
                    d["materials"].append(part)
                    logger.info(f"Новый материал: {part}")
            else:
                techniques.append(part)
                if part not in d["techniques"]:
                    d["techniques"].append(part)
                    logger.info(f"Новая техника: {part}")
    save_dictionary(d)
    return {"material":material,"techniques":techniques,"size":size}

SEPARATOR_RE = re.compile(r"\s*[⸻⸺]\s*")
URL_RE = re.compile(r"https?://(?:(?!https?://)[^\s⸻⸺])+")
TAG_RE = re.compile(r"#(\w+)@\w+")

def parse_post(text):
    """Парсит пост, разделяя поля строго по ⸻."""
    if not text: return {}
    try:
        # Извлекаем URL и теги
        urls = URL_RE.findall(text)
        raw_tags = TAG_RE.findall(text)
        
        # Удаляем URL и теги из текста для парсинга структуры
        tc = URL_RE.sub(" ", text)
        tc = TAG_RE.sub("", tc)
        
        # Разделяем по ⸻
        parts = [p.strip() for p in SEPARATOR_RE.split(tc) if p.strip()]
        
        # Минимальная структура: автор, название, medium, музей
        if len(parts) < 4: 
            return {}
        
        artist = re.sub(r"\s+", " ", parts[0]) if len(parts) > 0 else ""
        title = re.sub(r"\s+", " ", parts[1]) if len(parts) > 1 else ""
        medium = re.sub(r"\s+", " ", parts[2]) if len(parts) > 2 else ""
        museum = re.sub(r"\s+", " ", parts[3]) if len(parts) > 3 else ""
        
        if not artist or not title: 
            return {}
        
        # Части после музея (индексы 4+)
        extras = parts[4:] if len(parts) > 4 else []
        
        hist = []
        desc = ""
        
        # Функция для проверки, является ли текст происхождением
        def is_provenance(text):
            """Проверяет, является ли текст происхождением (нумерованные строки)."""
            if not text:
                return False
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            if not lines:
                return False
            # Проверяем, что хотя бы 50% строк начинаются с цифры и скобки
            numbered = sum(1 for l in lines if re.match(r'^\d+\s*\)', l))
            return numbered > 0 and numbered >= len(lines) * 0.5
        
        for extra in extras:
            # Пропускаем URL и теги (их уже нет, но на всякий случай)
            if re.match(r'^https?://', extra) or extra.startswith('#'):
                continue
            
            if is_provenance(extra):
                hist = [l.strip() for l in extra.split('\n') if l.strip()]
            else:
                # Всё остальное — описание
                desc_part = re.sub(r"\s*\n\s*", " ", extra).strip()
                if desc_part:
                    if desc:
                        desc += "\n\n" + desc_part
                    else:
                        desc = desc_part
        
        md = parse_medium_details(medium)
        
        # Извлекаем год создания
        creation_year = None
        if title:
            year_match = re.search(r'(\d{4})', title)
            if year_match:
                creation_year = int(year_match.group(1))
        
        return {
            "artist": artist,
            "title": title,
            "medium": medium,
            "material": md["material"],
            "techniques": md["techniques"],
            "size": md["size"],
            "museum": museum,
            "history": hist,
            "description": desc,
            "urls": urls,
            "tags": sorted(set(raw_tags)),
            "raw": text,
            "creation_year": creation_year
        }
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return {}

def lower_first(text):
    """«Холст» → «холст». Опускаем только первую букву: внутри значения
    может стоять имя собственное, которое трогать нельзя."""
    return (text[:1].lower() + text[1:]) if text else text


def slugify(text):
    t = text.lower()
    t = re.sub(r"[^\w\s-]","",t,flags=re.UNICODE)
    t = re.sub(r"\s+","-",t).strip("-")
    return t[:60] or "post"

def plural_ru(n, one, two, five):
    """Склоняет существительное: 1 картина, 2 картины, 5 картин"""
    n = abs(n) % 100
    if 11 <= n <= 19:
        return five
    n = n % 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return two
    return five

def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f: return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

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
        logger.warning(f"Миниатюра: {e}")
        return ""

async def download_with_retry(client, msg, fp, retries=3):
    for a in range(retries):
        try:
            await client.download_media(msg, fp)
            return True
        except Exception as e:
            if a < retries-1:
                logger.warning(f"Попытка {a+1}, жду...")
                await asyncio.sleep(5)
            else: raise
    return False

async def download_images(client, group, comments, slug):
    images, hires, thumbs = [], [], []
    idx = 0
    for msg in group:
        if getattr(msg,"photo",None):
            idx += 1
            fn = f"{slug}-{idx}.jpg"
            fp = os.path.join(IMAGES_DIR, fn)
            if not os.path.exists(fp): await download_with_retry(client, msg, fp)
            images.append(f"images/{fn}")
            t = make_thumbnail(fp, slug, idx)
            if t: thumbs.append(t)
    docs = [m for m in group if getattr(m,"document",None) and m.document.mime_type.startswith("image/")]
    docs.extend(comments)
    for i, msg in enumerate(docs, 1):
        ext = ".jpg"
        for attr in getattr(msg.document,"attributes",[]):
            if hasattr(attr,"file_name"): ext = os.path.splitext(attr.file_name)[1].lower(); break
        fn = f"{slug}-hires-{i}{ext}"
        fp = os.path.join(IMAGES_DIR, fn)
        if not os.path.exists(fp):
            try: await download_with_retry(client, msg, fp)
            except Exception as e:
                logger.error(f"Не скачан {msg.id}: {e}")
                continue
        fp = compress_if_huge(fp)
        hires.append(f"images/{os.path.basename(fp)}")
    if not images and hires:
        images = hires.copy()
        if PIL_AVAILABLE and not thumbs:
            for i, hr in enumerate(hires, 1):
                t = make_thumbnail(os.path.join(OUTPUT_DIR, hr), slug, i)
                if t: thumbs.append(t)
    return images, hires, thumbs

# ===================== HTML-ФУНКЦИИ =====================

def render_post_page(post, all_posts=None):
    artist, title, museum = h(post["artist"]), h(post["title"]), h(post["museum"])
    desc = post.get("description") or ""
    urls = post.get("urls") or ([post["url"]] if post.get("url") else [])
    cover_image = post['images'][0] if post.get('images') else ''
    post_id = str(post.get("id", ""))

    parts = []
    hl = post.get("hires", [])
    for i, src in enumerate(post["images"]):
        lh = hl[i] if i < len(hl) else src
        # Первая картина — главный элемент страницы (LCP): грузим её сразу,
        # остальные ленимся. Раньше lazy стоял на всех, включая первую.
        loading = 'fetchpriority="high" decoding="async"' if i == 0 else 'loading="lazy" decoding="async"'
        parts.append(
            f'<a href="{h(lh)}" target="_blank" rel="noopener" title="Открыть оригинал в новой вкладке">'
            f'<img src="{h(src)}" alt="{artist} — {title}" class="painting" {loading}></a>'
        )
    img_html = "\n".join(parts)

    mat = f'<span class="detail-item"><span class="detail-icon icon-material-card"></span> {h(post.get("material","").capitalize())}</span>' if post.get("material") else ""
    techniques_list = post.get("techniques", [])
    if techniques_list:
        formatted_techs = []
        for i, t in enumerate(techniques_list):
            formatted_techs.append(t.capitalize() if i == 0 else t.lower())
        tech = f'<span class="detail-item"><span class="detail-icon icon-technique-card"></span> {h(", ".join(formatted_techs))}</span>'
    else:
        tech = ""
    sz = f'<span class="detail-item"><span class="detail-icon icon-size-card"></span> {h(post.get("size",""))}</span>' if post.get("size") else ""
    mdet = f'<div class="medium-details">{mat} {tech} {sz}</div>'

    # Сведения о работе — отдельной таблицей в правой колонке: в каталоге
    # это главный справочный блок, а не строчка под заголовком.
    spec_rows = [
        ("Год", str(post.get("creation_year")) if post.get("creation_year") else ""),
        ("Материал", lower_first(post.get("material", ""))),
        ("Техника", ", ".join(post.get("techniques", []))),
        ("Размер", post.get("size", "")),
    ]
    spec_html = '<div class="spec-table">' + "".join(
        f'<div><span>{h(k)}</span><b>{h(v)}</b></div>' for k, v in spec_rows if v)
    if post.get("museum"):
        # Собрание — ссылка на карту музеев с якорем на нужную карточку
        spec_html += (f'<div><span>Собрание</span><b><a href="museums.html#museum-'
                      f'{h(slugify(post["museum"]))}">{h(post["museum"])}</a></b></div>')
    spec_html += '</div>'

    tags_html = ""
    if post["tags"]:
        tags_html = '<div class="tags">' + " ".join(f'<a href="tag-{h(t)}.html" class="tag">#{h(t)}</a>' for t in post["tags"]) + "</div>"
    tags_block = f'<div class="aside-block"><h3>Теги</h3>{tags_html}</div>' if tags_html else ""

    desc_html = ""
    if desc:
        paras = "".join(f"<p>{h(p)}</p>" for p in desc.split("\n\n") if p.strip())
        desc_html = f'<section class="description">{paras}</section>'

    hist = post.get("history") or post.get("note") or ""
    if isinstance(hist, str): hist = [s.strip() for s in re.split(r"⸻|\n", hist) if s.strip()]
    hist_html = ""
    if hist:
        its = "".join(f"<li>{h(s)}</li>" for s in hist)
        hist_html = f'<section class="history"><h3>Происхождение</h3><ul>{its}</ul></section>'

    src_html = ""
    src_block = ""
    if urls:
        its = "".join(f'<li><a href="{h(u)}" target="_blank" rel="noopener">{h(u)}</a></li>' for u in urls)
        word = "Источник" if len(urls) == 1 else "Источники"
        src_html = f'<div class="source-section"><strong>{word}</strong><ul class="source-list">{its}</ul></div>'
        src_block = f'<div class="aside-block"><h3>{word}</h3><ul class="source-list">{its}</ul></div>'

    # Prev/Next навигация
    prev_link = ""
    next_link = ""
    if all_posts:
        sorted_posts = sorted(all_posts, key=lambda x: x["date"])
        current_idx = next((i for i, p in enumerate(sorted_posts) if p.get("id") == post.get("id")), -1)
        if current_idx > 0:
            prev_post = sorted_posts[current_idx - 1]
            prev_link = f'<a href="{h(prev_post["filename"])}" class="prev-post" title="{h(prev_post["artist"])} — {h(prev_post["title"])}"><span class="icon-prev"></span> Предыдущая</a>'
        if current_idx < len(sorted_posts) - 1 and current_idx != -1:
            next_post = sorted_posts[current_idx + 1]
            next_link = f'<a href="{h(next_post["filename"])}" class="next-post" title="{h(next_post["artist"])} — {h(next_post["title"])}">Следующая <span class="icon-next"></span></a>'
    post_nav = f'<nav class="post-nav">{prev_link}{next_link}</nav>' if (prev_link or next_link) else ""

    page_desc = (desc[:200] if desc else f"{post.get('artist','')} — {post.get('title','')}. {post.get('museum','')}").strip()
    head = head_common(
        title=f"{artist} — {title}",
        description=page_desc,
        og_image=f"{BASE_URL}/{cover_image}" if cover_image else "",
        canonical=f"{BASE_URL}/{post.get('filename','')}",
        og_type="article",
    )

    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="post-page">
<a href="#main" class="skip-link">К содержанию</a>
<div class="post-topbar">
  <a href="index.html" class="topbar-back"><span class="icon-back" aria-hidden="true"></span> Галерея</a>
  <div class="post-topbar-right">
    <button type="button" onclick="goRandom()" class="topbar-btn" aria-label="Случайная картина" title="Случайная картина"><span class="icon-random" aria-hidden="true"></span></button>
    <button type="button" onclick="sharePage()" class="topbar-btn" aria-label="Поделиться" title="Поделиться"><span class="icon-share" aria-hidden="true"></span></button>
    <button type="button" id="like-btn" data-post-id="{post_id}" onclick="toggleLike()" class="topbar-btn topbar-like" aria-pressed="false" aria-label="В избранное" title="В избранное"><span class="icon-heart" aria-hidden="true"></span></button>
    <button type="button" class="topbar-btn" data-theme-toggle onclick="toggleTheme()" aria-label="Переключить тему" title="Светлая / тёмная тема"><span class="icon-theme-toggle" aria-hidden="true"></span></button>
    <button type="button" id="auth-btn" class="topbar-btn" title="Войти"><span class="icon-login" aria-hidden="true"></span> Войти</button>
  </div>
</div>
{scroll_top_button()}
<article id="main" class="post-layout">
  <div class="post-main">
    <header class="post-head">
      <h1>{artist}</h1>
      <h2>{title}</h2>
    </header>
    {img_html}
    <div class="color-palette" id="color-palette"></div>
    {desc_html}
    {hist_html}
  </div>
  <aside class="post-aside">
    {spec_html}
    {src_block}
    {tags_block}
    <div class="aside-block">
      <h3>Запись</h3>
      <time>{h(post['date'])}</time><span class="views-count" id="views-count"></span>
    </div>
  </aside>
</article>
{post_nav}
{SCROLL_TOP_JS}
{COMMON_JS}
<script src="https://cdnjs.cloudflare.com/ajax/libs/color-thief/2.3.0/color-thief.umd.js" defer></script>
<script>
// ---------- Палитра цветов ----------
// Раньше палитра вешалась только на событие load: если картинка бралась из
// кэша, load уже прошёл и палитра не появлялась никогда. Теперь проверяем
// img.complete, а сам скрипт ждём через window load (color-thief стоит defer).
(function() {{
    function buildPalette() {{
        var img = document.querySelector('.painting');
        var container = document.getElementById('color-palette');
        if (!img || !container || !window.ColorThief) return;
        try {{
            var palette = new ColorThief().getPalette(img, 5);
            if (!palette) return;
            palette.forEach(function(color) {{
                var hex = '#' + color.map(function(c) {{ return c.toString(16).padStart(2, '0'); }}).join('');
                var swatch = document.createElement('button');
                swatch.type = 'button';
                swatch.className = 'palette-swatch';
                swatch.style.background = hex;
                swatch.title = hex + ' — скопировать';
                swatch.setAttribute('aria-label', 'Скопировать цвет ' + hex);
                swatch.addEventListener('click', function() {{
                    var self = this;
                    function flash() {{
                        self.classList.add('copied');
                        setTimeout(function() {{ self.classList.remove('copied'); }}, 700);
                    }}
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                        navigator.clipboard.writeText(hex).then(flash).catch(function() {{ flash(); }});
                    }} else {{ flash(); }}
                }});
                container.appendChild(swatch);
            }});
        }} catch (e) {{ /* картинка с другого домена или ещё не декодирована */ }}
    }}
    function start() {{
        var img = document.querySelector('.painting');
        if (!img) return;
        if (img.complete && img.naturalWidth) buildPalette();
        else img.addEventListener('load', buildPalette, {{once: true}});
    }}
    if (document.readyState === 'complete') start();
    else window.addEventListener('load', start);
}})();

// ---------- Случайная картина ----------
// Список страниц кладёт главная. Если человек пришёл сразу на карточку и
// списка нет — раньше кнопка молча не работала, теперь уводим на главную.
function goRandom() {{
    var p = [];
    try {{ p = JSON.parse(localStorage.getItem('allPosts') || '[]'); }} catch (e) {{}}
    if (p && p.length) location.href = p[Math.floor(Math.random() * p.length)];
    else location.href = 'index.html?random=1';
}}

function sharePage() {{
    var url = window.location.href;
    if (navigator.share) {{
        navigator.share({{title: document.title, url: url}}).catch(function() {{}});
        return;
    }}
    if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(url)
            .then(function() {{ toast('Ссылка скопирована'); }})
            .catch(function() {{ window.prompt('Скопируйте ссылку:', url); }});
    }} else {{
        window.prompt('Скопируйте ссылку:', url);
    }}
}}

function toast(text) {{
    var el = document.createElement('div');
    el.className = 'toast';
    el.setAttribute('role', 'status');
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(function() {{ el.classList.add('hide'); }}, 1800);
    setTimeout(function() {{ el.remove(); }}, 2200);
}}

// ---------- Счётчик просмотров (локальный) ----------
(function() {{
    try {{
        var key = window.location.pathname;
        var views = JSON.parse(localStorage.getItem('pageViews') || '{{}}');
        views[key] = (views[key] || 0) + 1;
        localStorage.setItem('pageViews', JSON.stringify(views));
        var el = document.getElementById('views-count');
        if (el) {{
            el.innerHTML = '<span class="icon-views" aria-hidden="true"></span> ';
            el.appendChild(document.createTextNode(views[key]));
            el.title = 'Вы открывали эту страницу ' + views[key] + ' раз(а)';
        }}
    }} catch (e) {{}}
}})();

// ---------- Локальное состояние лайка ----------
// Раньше «сердечко» подсвечивалось только после входа в аккаунт: без входа
// лайк ставился, но после перезагрузки кнопка снова была пустой.
(function() {{
    try {{
        var btn = document.getElementById('like-btn');
        if (!btn) return;
        var likes = JSON.parse(localStorage.getItem('likes') || '{{}}');
        var on = !!likes[btn.dataset.postId];
        btn.classList.toggle('liked', on);
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }} catch (e) {{}}
}})();

// ---------- Горячие клавиши ----------
document.addEventListener('keydown', function(e) {{
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target;
    // не мешаем набору текста в полях (форма входа)
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    var k = e.key;
    if (k === 'r' || k === 'к') goRandom();
    else if (k === 'h' || k === 'р') window.location.href = 'index.html';
    else if (k === 't' || k === 'е') toggleTheme();
    else if (k === 'Escape') {{
        var m = document.querySelector('.auth-modal-overlay');
        if (m) m.remove();
    }}
    else if (k === 'ArrowLeft') {{
        var p = document.querySelector('.prev-post');
        if (p) p.click();
    }}
    else if (k === 'ArrowRight') {{
        var n = document.querySelector('.next-post');
        if (n) n.click();
    }}
}});
</script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-auth-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore-compat.js"></script>
<script src="firebase-config.js"></script>
<script>
// ---------- Firebase ----------
// Инициализацию оборачиваем в try: если скрипты Google заблокированы
// (расширение, корпоративная сеть, офлайн), страница раньше падала целиком
// и переставали работать ВСЕ кнопки. Теперь лайки просто остаются локальными.
var auth = null, db = null, currentUser = null;
var FIREBASE_OK = false;
try {{
    if (typeof firebase !== 'undefined' && typeof firebaseConfig !== 'undefined') {{
        firebase.initializeApp(firebaseConfig);
        auth = firebase.auth();
        db = firebase.firestore();
        FIREBASE_OK = true;
    }}
}} catch (e) {{ console.warn('Firebase недоступен, избранное работает локально:', e.message); }}

if (FIREBASE_OK) {{
    auth.onAuthStateChanged(function(user) {{
        currentUser = user;
        var btn = document.getElementById('auth-btn');
        if (btn) {{
            if (user) {{
                btn.innerHTML = '<span class="icon-user" aria-hidden="true"></span> ';
                btn.appendChild(document.createTextNode(user.email ? user.email.split('@')[0] : 'Профиль'));
                btn.title = 'Выйти из аккаунта';
                btn.onclick = function() {{ auth.signOut(); }};
            }} else {{
                btn.innerHTML = '<span class="icon-login" aria-hidden="true"></span> Войти';
                btn.title = 'Войти';
                btn.onclick = showAuthForm;
            }}
        }}
        if (user) loadLikesFromCloud();
    }});
}} else {{
    var authBtnOffline = document.getElementById('auth-btn');
    if (authBtnOffline) authBtnOffline.style.display = 'none';
}}

// Функция показа формы авторизации
function showAuthForm() {{
    var old = document.querySelector('.auth-modal-overlay');
    if (old) old.remove();
    
    var overlay = document.createElement('div');
    overlay.className = 'auth-modal-overlay';
    overlay.innerHTML = 
        '<div class="auth-modal">' +
        '<button class="auth-modal-close" id="auth-close-btn">×</button>' +
        '<h3 id="auth-title">Вход в аккаунт</h3>' +
        '<p>Сохраняйте избранное на всех устройствах</p>' +
        '<button class="auth-btn-google" id="google-login-btn">' +
        '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>' +
        'Войти через Google' +
        '</button>' +
        '<div class="auth-divider">или</div>' +
        '<form id="auth-form" autocomplete="on">' +
        '<input type="email" class="auth-input" id="auth-email" name="email" placeholder="Email" autocomplete="email">' +
        '<input type="password" class="auth-input" id="auth-password" name="password" placeholder="Пароль" autocomplete="current-password">' +
        '<button type="submit" class="auth-submit" id="auth-submit-btn">Войти</button>' +
        '</form>' +
        '<div class="auth-error" id="auth-error"></div>' +
        '<div class="auth-switch">' +
        'Нет аккаунта? <button type="button" class="auth-link" id="auth-switch-link">Создать</button>' +
        '</div>' +
        '<div class="auth-switch auth-reset-row" id="auth-reset-container">' +
        '<button type="button" class="auth-link" id="auth-reset-link">Забыли пароль?</button>' +
        '</div>' +
        '</div>';
    
    document.body.appendChild(overlay);
    
    var emailInp = document.getElementById('auth-email');
    var passInp = document.getElementById('auth-password');
    var submitBtn = document.getElementById('auth-submit-btn');
    var switchLink = document.getElementById('auth-switch-link');
    var errorDiv = document.getElementById('auth-error');
    var isLogin = true;
    
    // Закрытие
    document.getElementById('auth-close-btn').onclick = function() {{ overlay.remove(); }};
    overlay.onclick = function(e) {{ if (e.target === overlay) overlay.remove(); }};
    
    // Google login
    document.getElementById('google-login-btn').onclick = function() {{
        var provider = new firebase.auth.GoogleAuthProvider();
        auth.signInWithPopup(provider)
            .then(function() {{ overlay.remove(); }})
            .catch(function(err) {{ errorDiv.textContent = 'Ошибка: ' + err.message; }});
    }};
    
    // Switch login/register
    switchLink.onclick = function() {{
        isLogin = !isLogin;
        submitBtn.textContent = isLogin ? 'Войти' : 'Создать аккаунт';
        switchLink.textContent = isLogin ? 'Создать' : 'Войти';
        document.getElementById('auth-title').textContent = isLogin ? 'Вход в аккаунт' : 'Регистрация';
        errorDiv.textContent = '';
        document.getElementById('auth-reset-container').style.display = 'none';
    }};
    
    // Reset password
    document.getElementById('auth-reset-link').onclick = function() {{
        var email = emailInp.value.trim();
        if (!email) {{ errorDiv.textContent = 'Введите email для сброса пароля'; return; }}
        auth.sendPasswordResetEmail(email)
            .then(function() {{ alert('Письмо для сброса пароля отправлено на ' + email); }})
            .catch(function(err) {{ errorDiv.textContent = 'Ошибка: ' + err.message; }});
    }};
    
    // Submit формы
    document.getElementById('auth-form').onsubmit = function(e) {{
        e.preventDefault();
        var email = emailInp.value.trim();
        var pass = passInp.value;
        if (!email) {{ errorDiv.textContent = 'Введите email'; return; }}
        if (pass.length < 6) {{ errorDiv.textContent = 'Пароль: минимум 6 символов'; return; }}
        
        var promise = isLogin 
            ? auth.signInWithEmailAndPassword(email, pass)
            : auth.createUserWithEmailAndPassword(email, pass);
        
        promise
            .then(function() {{ overlay.remove(); }})
            .catch(function(err) {{
                if (err.code === 'auth/user-not-found') {{
                    errorDiv.textContent = 'Аккаунт не найден. Проверьте email или создайте новый.';
                    document.getElementById('auth-reset-container').style.display = 'none';
                }} else if (err.code === 'auth/wrong-password' || err.code === 'auth/invalid-credential') {{
                    errorDiv.textContent = 'Неверный пароль.';
                    document.getElementById('auth-reset-container').style.display = 'block';
                }} else if (err.code === 'auth/email-already-in-use') {{
                    errorDiv.textContent = 'Email уже используется.';
                    document.getElementById('auth-reset-container').style.display = 'block';
                }} else {{
                    errorDiv.textContent = 'Ошибка: ' + err.message;
                    document.getElementById('auth-reset-container').style.display = 'none';
                }}
            }});
    }};
    
    setTimeout(function() {{ emailInp.focus(); }}, 100);
}}
  
// Синхронизация лайков
async function syncLike(postId, liked) {{
    try {{
        var local = JSON.parse(localStorage.getItem('likes') || '{{}}');
        local[postId] = liked;
        localStorage.setItem('likes', JSON.stringify(local));
    }} catch (e) {{}}
    if (FIREBASE_OK && currentUser) {{
        try {{
            await db.collection('likes').doc(currentUser.uid + '_' + postId).set({{
                userId: currentUser.uid,
                postId: postId,
                liked: liked,
                time: firebase.firestore.FieldValue.serverTimestamp()
            }});
        }} catch(e) {{ console.warn('Не удалось сохранить лайк в облако:', e.message); }}
    }}
}}

// Загрузка лайков из облака
async function loadLikesFromCloud() {{
    if (!FIREBASE_OK || !currentUser) return;
    try {{
        var snap = await db.collection('likes')
            .where('userId', '==', currentUser.uid)
            .where('liked', '==', true)
            .get();
        var cloud = {{}};
        snap.forEach(function(d) {{ cloud[d.data().postId] = true; }});
        var local = JSON.parse(localStorage.getItem('likes') || '{{}}');
        var merged = Object.assign({{}}, local, cloud);
        localStorage.setItem('likes', JSON.stringify(merged));
        var btn = document.getElementById('like-btn');
        if (btn && merged[btn.dataset.postId]) {{
            btn.classList.add('liked');
            btn.setAttribute('aria-pressed', 'true');
        }}
    }} catch (e) {{ console.warn('Не удалось загрузить избранное:', e.message); }}
}}

// Переключение лайка — работает и без аккаунта, и без Firebase
async function toggleLike() {{
    var btn = document.getElementById('like-btn');
    if (!btn) return;
    var pid = btn.dataset.postId;
    var likes = {{}};
    try {{ likes = JSON.parse(localStorage.getItem('likes') || '{{}}'); }} catch (e) {{}}
    var newState = !likes[pid];
    btn.classList.toggle('liked', newState);
    btn.setAttribute('aria-pressed', newState ? 'true' : 'false');
    btn.setAttribute('aria-label', newState ? 'Убрать из избранного' : 'В избранное');
    await syncLike(pid, newState);
    try {{
        if (window.opener && window.opener.updateFavList) window.opener.updateFavList();
    }} catch(e) {{}}
}}
</script></body></html>"""

def surname_key(n):
    f = n.split(",")[0].strip()
    w = f.split()
    return w[-1].lower() if w else n.lower()

def render_tag_page(tag, posts, cat_no=None, cat_width=3):
    """cat_no — сквозные каталожные номера всего собрания: на странице тега
    номер должен остаться тем же, что и на главной, иначе он ничего не значит."""
    cat_no = cat_no or {}
    cards = []
    for p in sorted(posts, key=lambda x: x["date"], reverse=True):
        cv = ""
        if p.get("thumbs"): cv = p["thumbs"][0]
        elif p.get("images"): cv = p["images"][0]
        cv = h(cv)
        museum_name = h(p.get('museum', ''))
        artist_name = h(p["artist"])
        title_name = h(p["title"])
        # Экранированные кавычки внутри f-строки требуют Python 3.12+,
        # на 3.11 это была синтаксическая ошибка. Собираем строку заранее.
        museum_html = (f'<div class="card-museum"><a href="museums.html#museum-{h(slugify(p.get("museum","")))}"'
                       f' title="Показать музей на карте">{museum_name}</a></div>') if museum_name else ''
        no = cat_no.get(p.get("filename"))
        no_html = f'<span class="card-no">{no:0{cat_width}d}</span>' if no else '<span class="card-no"></span>'
        facts = [("Год", str(p.get("creation_year")) if p.get("creation_year") else ""),
                 ("Материал", lower_first(p.get("material", ""))),
                 ("Техника", ", ".join(p.get("techniques", []))),
                 ("Размер", p.get("size", ""))]
        facts_html = "".join(f'<div><span>{h(k)}</span><b>{h(v)}</b></div>' for k, v in facts if v)
        cards.append(
            f'<article class="card">{no_html}'
            f'<div class="card-img"><img src="{cv}" alt="{artist_name} — {title_name}" loading="lazy" decoding="async"></div>'
            f'<div class="card-body">'
            f'<div class="card-artist"><a class="card-link" href="{h(p["filename"])}">{artist_name}</a></div>'
            f'<div class="card-title">{title_name}</div>{museum_html}</div>'
            f'<div class="card-facts">{facts_html}</div></article>'
        )
    head = head_common(
        title=f"#{h(tag)} — Old Picture Art",
        description=f"Картины по тегу #{tag} — подборка из {len(posts)} работ в галерее Old Picture Art.",
        canonical=f"{BASE_URL}/tag-{tag}.html",
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page">
<div class="tag-topbar">
  <a href="index.html" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<h1>#{h(tag)} <span class="tag-count">({len(posts)})</span></h1>
<div class="grid list">{''.join(cards)}</div>
{SCROLL_TOP_JS}
{COMMON_JS}
</body></html>"""

def render_index(all_posts):
    MONTHS = {"01":"Январь","02":"Февраль","03":"Март","04":"Апрель","05":"Май","06":"Июнь","07":"Июль","08":"Август","09":"Сентябрь","10":"Октябрь","11":"Ноябрь","12":"Декабрь"}
    ps = sorted(all_posts, key=lambda x: x["date"], reverse=True)
    
    authors = sorted({p["artist"] for p in ps if p.get("artist")}, key=surname_key)
    museums = sorted({p.get("museum","") for p in ps if p.get("museum")})
    ms, ts = set(), set()
    for p in ps:
        if p.get("material"): ms.add(p["material"])
        for t in p.get("techniques",[]):
            if t and len(t)>2: ts.add(t)
    materials, techniques = sorted(ms), sorted(ts)
    
    archive = defaultdict(set)
    archive_count = defaultdict(int)
    for p in ps:
        if p.get("date") and "-" in p["date"]:
            y, m, _ = p["date"].split("-")
            archive[y].add(m)
            archive_count[y] += 1
    ars = {y: sorted(list(m), reverse=True) for y, m in sorted(archive.items(), reverse=True)}
    
    creation_years = []
    for p in ps:
        cy = p.get("creation_year")
        if cy: creation_years.append(cy)
    decades = {}
    for y in creation_years:
        d_start = y // 10 * 10
        d_label = f"{d_start}–{d_start+9}"
        decades[d_label] = decades.get(d_label, 0) + 1
    decades_sorted = sorted(decades.keys())
    
    year_range = f"{min(creation_years)}–{max(creation_years)}" if creation_years else ""
    
    # Каталожный номер закреплён за работой навсегда: он показывает место
    # в хронологии собрания, а не позицию в текущей сортировке.
    chrono = sorted(ps, key=lambda x: (x.get("creation_year") or 9999, x.get("date", "")))
    cat_no = {id(x): i for i, x in enumerate(chrono, 1)}
    cat_width = max(3, len(str(len(ps))))

    cards = []
    for p in ps:
        cv = ""
        if p.get("thumbs"): cv = p["thumbs"][0]
        elif p.get("images"): cv = p["images"][0]
        cv = h(cv)
        y, m = "", ""
        if p.get("date") and "-" in p["date"]: y, m, _ = p["date"].split("-")
        decade_attr = ""
        creation_year = p.get("creation_year")
        if creation_year:
            d_start = creation_year // 10 * 10
            decade_attr = f'data-decade="{d_start}–{d_start+9}"'
        artist_name = h(p['artist'])
        title_name = h(p['title'])
        museum_name = h(p.get('museum', ''))
        material_name = h(p.get('material', ''))
        techniques_list = p.get('techniques', [])
        size_val = h(p.get('size', ''))

        # Дата публикации
        pub_date = p.get('date', '')[:10] if p.get('date') else ''

        # data-search собирает всё, по чему ищем: раньше поиск шёл по
        # видимому тексту карточки, а названия картины в нём нет — искать
        # по названию было невозможно.
        search_blob = " ".join(filter(None, [
            p.get('artist', ''), p.get('title', ''), p.get('museum', ''),
            p.get('material', ''), " ".join(p.get('techniques', [])),
            " ".join(p.get('tags', [])), pub_date,
        ])).lower()

        # Сведения о работе: в описи это столбец таблицы, в плитках —
        # строчка через точку. Разметка одна, раскладку задаёт CSS.
        facts = [("Год", str(creation_year) if creation_year else ""),
                 ("Материал", lower_first(p.get('material', ''))),
                 ("Техника", ", ".join(p.get('techniques', []))),
                 ("Размер", p.get('size', ''))]
        facts_html = "".join(
            f'<div><span>{h(k)}</span><b>{h(v)}</b></div>' for k, v in facts if v)

        # Карточка — <article>, а не <a>: внутри должна быть вторая ссылка,
        # на музей, а ссылку в ссылку вкладывать нельзя. Вся карточка всё
        # равно кликабельна — за счёт растянутой на неё .card-link.
        museum_slug = slugify(p.get('museum', ''))
        museum_html = (f'<div class="card-museum"><a href="museums.html#museum-{h(museum_slug)}"'
                       f' title="Показать музей на карте">{museum_name}</a></div>') if museum_name else ''

        cards.append(f"""<article class="card" data-artist="{h(p['artist'].lower())}" data-title="{h(p['title'].lower())}" data-year="{y}" data-month="{m}" data-cyear="{creation_year or ''}" data-museum="{h(museum_slug)}" data-material="{h(slugify(p.get('material','')))}" data-techniques="{h(' '.join(slugify(t) for t in p.get('techniques',[])))}" data-search="{h(search_blob)}" data-no="{cat_no[id(p)]}" {decade_attr}>
    <span class="card-no">{cat_no[id(p)]:0{cat_width}d}</span>
    <div class="card-img"><img src="{cv}" alt="{artist_name} — {title_name}" loading="lazy" decoding="async"></div>
    <div class="card-body">
        <div class="card-artist"><a class="card-link" href="{h(p['filename'])}">{artist_name}</a></div>
        <div class="card-title">{title_name}</div>
        {museum_html}
        <div class="card-date">{pub_date}</div>
    </div>
    <div class="card-facts">{facts_html}</div>
    </article>""")
    
    artist_count = defaultdict(int)
    museum_count = defaultdict(int)
    material_count = defaultdict(int)
    technique_count = defaultdict(int)
    for p in ps:
        if p.get("artist"): artist_count[p["artist"]] += 1
        if p.get("museum"): museum_count[p["museum"]] += 1
        if p.get("material"): material_count[p["material"]] += 1
        for t in p.get("techniques",[]):
            if t and len(t)>2: technique_count[t] += 1
    
    ah = "".join(f'<li><a href="#" class="filter-link" data-type="artist" data-val="{h(a.lower())}">{h(a)} <span class="count">({artist_count[a]})</span></a></li>' for a in authors)
    mh = "".join(f'<li><a href="#" class="filter-link" data-type="museum" data-val="{h(slugify(m))}">{h(m)} <span class="count">({museum_count[m]})</span></a></li>' for m in museums if m)
    mth = "".join(f'<li><a href="#" class="filter-link" data-type="material" data-val="{h(slugify(m))}">{h(m)} <span class="count">({material_count[m]})</span></a></li>' for m in materials)
    th = "".join(f'<li><a href="#" class="filter-link" data-type="technique" data-val="{h(slugify(t))}">{h(t)} <span class="count">({technique_count[t]})</span></a></li>' for t in techniques)
    # Годы: столбики по десятилетиям вместо простого списка. Высота — сколько
    # работ, клик по столбику выбирает десятилетие, а поля «от / до» задают
    # точный диапазон. Один ряд данных, поэтому легенда не нужна: подпись
    # под гистограммой словами говорит, что именно сейчас выбрано.
    hist_max = max(decades.values()) if decades else 1
    bars = []
    for d in decades_sorted:
        start = int(d.split("–")[0])
        n = decades.get(d, 0)
        pct = max(6, round(n / hist_max * 100))
        bars.append(
            f'<button type="button" class="hbar" data-decade="{start}" style="--h:{pct}%" '
            f'title="{h(d)} — {n} {plural_ru(n, "работа", "работы", "работ")}" '
            f'aria-label="{h(d)}, {n} {plural_ru(n, "работа", "работы", "работ")}">'
            f'<span class="hbar-fill"></span></button>'
        )
    decade_starts = [int(d.split("–")[0]) for d in decades_sorted]
    opts_from = "".join(f'<option value="{v}">{v}</option>' for v in decade_starts)
    opts_to = "".join(f'<option value="{v + 9}">{v + 9}</option>' for v in decade_starts)
    dech = f'''<div class="year-filter">
      <div class="histogram" id="year-hist">{''.join(bars)}</div>
      <div class="hist-axis"><span>{decade_starts[0] if decade_starts else ''}</span><span>{(decade_starts[-1] + 9) if decade_starts else ''}</span></div>
      <div class="year-range">
        <label class="visually-hidden" for="year-from">Год от</label>
        <select id="year-from" class="year-select"><option value="">любой</option>{opts_from}</select>
        <span class="year-dash">—</span>
        <label class="visually-hidden" for="year-to">Год до</label>
        <select id="year-to" class="year-select"><option value="">любой</option>{opts_to}</select>
      </div>
      <p class="year-caption" id="year-caption" role="status" aria-live="polite"></p>
    </div>'''
    
    arh = ""
    for y, ms_list in ars.items():
        arh += f'<li><a href="#" class="filter-link" data-type="year" data-val="{y}"><b>{y} год</b> <span class="count">({archive_count[y]})</span></a><ul class="month-list">'
        for mn in ms_list: arh += f'<li><a href="#" class="filter-link" data-type="month" data-year="{y}" data-val="{mn}">{MONTHS.get(mn,mn)}</a></li>'
        arh += '</ul></li>'
    
    af = json.dumps([p["filename"] for p in ps])
    post_map_data = {
        str(p.get("id", "")): {"file": p["filename"], "title": p.get("title", f"Картина #{p.get('id', '')}")} 
        for p in ps if p.get("id")
    }
    pm_js = json.dumps(post_map_data, ensure_ascii=False)
    
    # Разделы сайдбара. Заголовки-«аккордеоны» теперь настоящие <button>:
    # раньше это были <div onclick>, недоступные с клавиатуры и для скринридеров.
    empty_fav = ('<li class="fav-empty">Нажмите <span class="icon-heart" aria-hidden="true"></span>'
                 ' на странице картины</li>')
    fav_html = ('<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon icon-fav" '
                'aria-expanded="false" onclick="toggleSection(this)">Избранное '
                '<span id="fav-count" class="count"></span></button>'
                f'<div class="sidebar-content collapsed"><ul id="fav-list">{empty_fav}</ul></div></div>')
    theme_html = ('<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon icon-theme no-arrow" '
                  'data-theme-toggle aria-pressed="false" onclick="toggleTheme()">Тема</button></div>')
    quiz_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-quiz no-arrow" '
                      'href="quiz.html">Квиз</a></div>')
    timeline_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-timeline no-arrow" '
                          'href="timeline.html">Таймлайн</a></div>')
    map_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-map no-arrow" '
                     'href="museums.html">Карта музеев</a></div>')
    
    head = head_common(
        title="Old Picture Art — Галерея",
        description=(f"Галерея из {len(ps)} картин: {len(authors)} художников, {len(museums)} музеев. "
                     "Поиск по художникам, музеям, технике и десятилетиям."),
        canonical=f"{BASE_URL}/",
    )

    def section(icon, label, content):
        return (f'<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon {icon}" '
                f'aria-expanded="false" onclick="toggleSection(this)">{label}</button>'
                f'<div class="sidebar-content collapsed"><ul>{content}</ul></div></div>')

    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="index-page">
<a href="#cards" class="skip-link">К галерее</a>
<button type="button" class="menu-toggle" id="menu-toggle" onclick="toggleMenu()" aria-expanded="false" aria-controls="sidebar"><span class="icon-menu" aria-hidden="true"></span> Меню</button>
<div class="overlay" id="overlay" onclick="toggleMenu()" aria-hidden="true" hidden></div>
{scroll_top_button()}
<header><h1><span class="icon-logo" aria-hidden="true"></span> Old Picture Art</h1>
<div class="subtitle">{len(ps)} {plural_ru(len(ps), 'картина', 'картины', 'картин')} · {len(authors)} {plural_ru(len(authors), 'художник', 'художника', 'художников')} · {len(museums)} {plural_ru(len(museums), 'музей', 'музея', 'музеев')} · {year_range}</div>
<button type="button" class="random-btn" onclick="goRandom()"><span class="icon-random-white" aria-hidden="true"></span> Случайная картина</button></header>
<div class="layout"><aside class="sidebar" id="sidebar" aria-label="Фильтры">
<div class="sidebar-section sidebar-search">
  <label class="visually-hidden" for="search">Поиск по галерее</label>
  <input type="search" class="search-box" placeholder="Поиск по художнику, картине, музею…" id="search" autocomplete="off">
</div>
<button type="button" id="reset-filter" class="filter-reset">Сбросить все фильтры</button>
{section('icon-archive', 'Архив', arh)}
<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon icon-decades" aria-expanded="false" onclick="toggleSection(this)">Годы</button><div class="sidebar-content collapsed">{dech}</div></div>
{section('icon-artists', 'Художники', ah)}
{section('icon-museums', 'Музеи', mh)}
{section('icon-material', 'Материал', mth)}
{section('icon-technique', 'Техника', th)}
{fav_html}
{theme_html}
{map_link_html}
{quiz_link_html}
{timeline_link_html}
</aside><main class="main-content">
<div class="results-bar">
  <span id="results-count" class="results-count" role="status" aria-live="polite"></span>
  <div class="bar-controls">
  <label class="visually-hidden" for="sort">Порядок записей</label>
  <select id="sort" class="sort-select">
    <option value="new">Сначала новые</option>
    <option value="cyear">По году создания</option>
    <option value="cyear-desc">По году создания, новые сверху</option>
    <option value="artist">По художнику</option>
    <option value="title">По названию</option>
  </select>
  <div class="view-switch" role="group" aria-label="Вид списка">
    <button type="button" id="view-list" aria-pressed="true" onclick="setView('list')">Опись</button>
    <button type="button" id="view-grid" aria-pressed="false" onclick="setView('grid')">Плитки</button>
  </div>
  </div>
</div>
<div class="grid list" id="cards">{''.join(cards)}</div>
<p class="no-results" id="no-results" hidden>Ничего не найдено. Попробуйте изменить запрос или <button type="button" class="linklike" onclick="resetAllFilters()">сбросить фильтры</button>.</p>
</main></div>
{SCROLL_TOP_JS}
{COMMON_JS}
<script>
const ALL_POSTS = {af};
const POSTS_DATA = {pm_js};

try {{ localStorage.setItem('allPosts', JSON.stringify(ALL_POSTS)); }} catch (e) {{}}

function goRandom() {{
    if (ALL_POSTS.length) location.href = ALL_POSTS[Math.floor(Math.random() * ALL_POSTS.length)];
}}

// Переход с карточки: «случайная картина» без сохранённого списка ведёт сюда
if (location.search.indexOf('random=1') !== -1 && ALL_POSTS.length) {{
    location.replace(ALL_POSTS[Math.floor(Math.random() * ALL_POSTS.length)]);
}}

// Опись или плитки. Выбор запоминается: разметка одна, меняется только
// класс контейнера, поэтому фильтры и поиск продолжают работать как были.
function setView(mode) {{
    const grid = document.getElementById('cards');
    if (!grid) return;
    grid.classList.toggle('list', mode === 'list');
    const l = document.getElementById('view-list'), g = document.getElementById('view-grid');
    if (l) l.setAttribute('aria-pressed', mode === 'list' ? 'true' : 'false');
    if (g) g.setAttribute('aria-pressed', mode === 'grid' ? 'true' : 'false');
    try {{ localStorage.setItem('cardView', mode); }} catch (e) {{}}
}}

(function () {{
    let saved = null;
    try {{ saved = localStorage.getItem('cardView'); }} catch (e) {{}}
    if (saved === 'grid') document.addEventListener('DOMContentLoaded', function () {{ setView('grid'); }});
}})();

function updateFavList() {{
    let likes = {{}};
    try {{ likes = JSON.parse(localStorage.getItem('likes') || '{{}}'); }} catch (e) {{}}
    const favList = document.getElementById('fav-list');
    const favCount = document.getElementById('fav-count');
    if (!favList) return;
    const likedIds = Object.keys(likes).filter(id => likes[id]);
    if (favCount) favCount.textContent = likedIds.length ? '(' + likedIds.length + ')' : '';
    favList.textContent = '';
    if (!likedIds.length) {{
        const li = document.createElement('li');
        li.className = 'fav-empty';
        li.innerHTML = 'Нажмите <span class="icon-heart" aria-hidden="true"></span> на странице картины';
        favList.appendChild(li);
        return;
    }}
    likedIds.forEach(id => {{
        const info = POSTS_DATA[id];
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = info ? info.file : '#';
        a.title = info ? info.title : ('Картина #' + id);
        // textContent, а не innerHTML: названия картин приходят из данных
        a.innerHTML = '<span class="icon-painting-small" aria-hidden="true"></span> ';
        a.appendChild(document.createTextNode(info ? info.title : ('Картина #' + id)));
        li.appendChild(a);
        favList.appendChild(li);
    }});
}}

// Аккордеон сайдбара: класс open нужен, чтобы стрелка ▾ поворачивалась —
// раньше он не ставился нигде и стрелка всегда смотрела вниз.
function toggleSection(el) {{
    const content = el.nextElementSibling;
    if (!content) return;
    const willOpen = content.classList.contains('collapsed');
    content.classList.toggle('collapsed', !willOpen);
    el.classList.toggle('open', willOpen);
    el.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
}}

function toggleMenu(force) {{
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');
    const btn = document.getElementById('menu-toggle');
    if (!sidebar) return;
    const open = typeof force === 'boolean' ? force : !sidebar.classList.contains('open');
    sidebar.classList.toggle('open', open);
    if (overlay) {{ overlay.classList.toggle('visible', open); overlay.hidden = !open; }}
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}}

function isMobile() {{ return window.matchMedia('(max-width: 900px)').matches; }}

let activeFilters = {{ search: '', type: null, val: null, year: null, from: null, to: null }};

function resetAllFilters() {{
    activeFilters = {{ search: '', type: null, val: null, year: null, from: null, to: null }};
    const searchBox = document.getElementById('search');
    if (searchBox) searchBox.value = '';
    document.querySelectorAll('.filter-link.active').forEach(l => {{
        l.classList.remove('active');
        l.removeAttribute('aria-current');
    }});
    const f = document.getElementById('year-from'), t = document.getElementById('year-to');
    if (f) f.value = ''; if (t) t.value = '';
    syncHistogram();
    applyFilters();
}}

// Подсветка столбиков и подпись под гистограммой. Выбор показан не только
// цветом: под столбиками стоит строка словами.
function syncHistogram() {{
    const from = activeFilters.from, to = activeFilters.to;
    document.querySelectorAll('.hbar').forEach(b => {{
        const d = +b.dataset.decade;
        const on = (from === null && to === null) ||
                   ((from === null || d + 9 >= from) && (to === null || d <= to));
        b.classList.toggle('dim', !(from === null && to === null) && !on);
        b.setAttribute('aria-pressed', (from !== null || to !== null) && on ? 'true' : 'false');
    }});
    const cap = document.getElementById('year-caption');
    if (!cap) return;
    if (from === null && to === null) cap.textContent = 'Все годы';
    else if (from !== null && to !== null) cap.textContent = from + '—' + to;
    else if (from !== null) cap.textContent = 'с ' + from;
    else cap.textContent = 'по ' + to;
}}

function setYearRange(from, to) {{
    activeFilters.from = from;
    activeFilters.to = to;
    const f = document.getElementById('year-from'), t = document.getElementById('year-to');
    if (f) f.value = from === null ? '' : String(from);
    if (t) t.value = to === null ? '' : String(to);
    syncHistogram();
    applyFilters();
}}

// Порядок записей. Каталожные номера при этом не пересчитываются:
// номер закреплён за работой и показывает её место в хронологии собрания.
function sortCards(mode) {{
    const grid = document.getElementById('cards');
    if (!grid) return;
    const cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
    const byText = (a, b, key) => (a.dataset[key] || '').localeCompare(b.dataset[key] || '', 'ru');
    const year = el => parseInt(el.dataset.cyear, 10) || 0;
    cards.sort((a, b) => {{
        if (mode === 'cyear') return year(a) - year(b) || byText(a, b, 'artist');
        if (mode === 'cyear-desc') return year(b) - year(a) || byText(a, b, 'artist');
        if (mode === 'artist') return byText(a, b, 'artist') || year(a) - year(b);
        if (mode === 'title') return byText(a, b, 'title');
        return (+b.dataset.no) - (+a.dataset.no) === 0 ? 0 : 0;  // «сначала новые» — исходный порядок
    }});
    if (mode === 'new') {{
        cards.sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));
    }}
    const frag = document.createDocumentFragment();
    cards.forEach(c => frag.appendChild(c));
    grid.appendChild(frag);
    try {{ localStorage.setItem('cardSort', mode); }} catch (e) {{}}
}}

let ORDER = [];

function applyFilters() {{
    const cards = document.querySelectorAll('.card');
    let visible = 0;
    cards.forEach(card => {{
        let show = true;
        if (activeFilters.search) {{
            const blob = card.dataset.search || card.textContent.toLowerCase();
            if (blob.indexOf(activeFilters.search) === -1) show = false;
        }}
        if (show && (activeFilters.from !== null || activeFilters.to !== null)) {{
            const cy = parseInt(card.dataset.cyear, 10);
            if (!cy) show = false;
            else if (activeFilters.from !== null && cy < activeFilters.from) show = false;
            else if (activeFilters.to !== null && cy > activeFilters.to) show = false;
        }}
        if (show && activeFilters.type) {{
            const t = activeFilters.type, v = activeFilters.val;
            if (t === 'artist') show = card.dataset.artist === v;
            else if (t === 'museum') show = card.dataset.museum === v;
            else if (t === 'material') show = card.dataset.material === v;
            else if (t === 'technique') show = (card.dataset.techniques || '').split(' ').indexOf(v) !== -1;
            else if (t === 'decade') show = card.dataset.decade === v;
            else if (t === 'year') show = card.dataset.year === v;
            else if (t === 'month') show = card.dataset.year === activeFilters.year && card.dataset.month === v;
        }}
        card.hidden = !show;
        if (show) visible++;
    }});

    const hasActive = !!(activeFilters.search || activeFilters.type ||
                         activeFilters.from !== null || activeFilters.to !== null);
    const resetBtn = document.getElementById('reset-filter');
    if (resetBtn) resetBtn.classList.toggle('visible', hasActive);

    const counter = document.getElementById('results-count');
    if (counter) counter.textContent = hasActive ? (visible + ' ' + plural(visible, 'картина', 'картины', 'картин')) : '';

    const empty = document.getElementById('no-results');
    if (empty) empty.hidden = visible !== 0;
}}

function plural(n, one, few, many) {{
    const n10 = n % 10, n100 = n % 100;
    if (n10 === 1 && n100 !== 11) return one;
    if (n10 >= 2 && n10 <= 4 && (n100 < 10 || n100 >= 20)) return few;
    return many;
}}

document.addEventListener('DOMContentLoaded', function() {{
    updateFavList();

    // Исходный порядок запоминаем один раз — к нему возвращает «сначала новые»
    ORDER = Array.prototype.slice.call(document.querySelectorAll('#cards .card'));

    const sortSel = document.getElementById('sort');
    if (sortSel) {{
        let savedSort = null;
        try {{ savedSort = localStorage.getItem('cardSort'); }} catch (e) {{}}
        if (savedSort && [...sortSel.options].some(o => o.value === savedSort)) {{
            sortSel.value = savedSort;
            sortCards(savedSort);
        }}
        sortSel.addEventListener('change', function () {{ sortCards(this.value); }});
    }}

    // Гистограмма: клик по столбику — это десятилетие целиком
    document.querySelectorAll('.hbar').forEach(bar => {{
        bar.addEventListener('click', function () {{
            const d = +this.dataset.decade;
            if (activeFilters.from === d && activeFilters.to === d + 9) setYearRange(null, null);
            else setYearRange(d, d + 9);
        }});
    }});

    const yf = document.getElementById('year-from'), yt = document.getElementById('year-to');
    [yf, yt].forEach(el => {{
        if (!el) return;
        el.addEventListener('change', function () {{
            let from = yf && yf.value ? +yf.value : null;
            let to = yt && yt.value ? +yt.value : null;
            if (from !== null && to !== null && from > to) {{ const x = from; from = to; to = x; }}
            setYearRange(from, to);
        }});
    }});
    syncHistogram();

    const searchBox = document.getElementById('search');
    if (searchBox) {{
        let t = null;
        searchBox.addEventListener('input', function(e) {{
            const v = e.target.value.toLowerCase().trim();
            clearTimeout(t);
            // debounce: 195 карточек пересчитывать на каждую букву незачем
            t = setTimeout(function() {{ activeFilters.search = v; applyFilters(); }}, 120);
        }});
    }}

    document.querySelectorAll('.filter-link').forEach(link => {{
        link.addEventListener('click', function(e) {{
            e.preventDefault();
            const same = this.classList.contains('active');
            document.querySelectorAll('.filter-link.active').forEach(l => {{
                l.classList.remove('active');
                l.removeAttribute('aria-current');
            }});
            if (same) {{
                // повторный клик по тому же фильтру — снимаем его
                activeFilters.type = activeFilters.val = activeFilters.year = null;
            }} else {{
                this.classList.add('active');
                this.setAttribute('aria-current', 'true');
                activeFilters.type = this.dataset.type;
                activeFilters.val = this.dataset.val;
                activeFilters.year = this.dataset.year || null;
            }}
            applyFilters();
            // на телефоне меню перекрывает результат — закрываем его
            if (isMobile()) toggleMenu(false);
            document.getElementById('cards').scrollIntoView({{block: 'start', behavior: 'auto'}});
        }});
    }});

    const resetBtn = document.getElementById('reset-filter');
    if (resetBtn) resetBtn.addEventListener('click', function(e) {{ e.preventDefault(); resetAllFilters(); }});

    document.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') {{
            if (document.getElementById('sidebar').classList.contains('open')) toggleMenu(false);
            else if (document.activeElement === searchBox && searchBox.value) resetAllFilters();
        }}
        if (e.key === '/' && document.activeElement !== searchBox) {{
            e.preventDefault();
            if (isMobile()) toggleMenu(true);
            if (searchBox) searchBox.focus();
        }}
    }});

    applyFilters();
}});
</script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-auth-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore-compat.js"></script>
<script src="firebase-config.js"></script>
<script>
// Firebase — необязательная часть: если скрипты Google не загрузились,
// главная должна продолжать работать (раньше падала вся страница).
try {{
  if (typeof firebase !== 'undefined' && typeof firebaseConfig !== 'undefined') {{
    firebase.initializeApp(firebaseConfig);
    const auth = firebase.auth();
    const db = firebase.firestore();
    auth.onAuthStateChanged(user => {{
      if (!user) return;
      db.collection('likes')
        .where('userId', '==', user.uid)
        .where('liked', '==', true).get()
        .then(snap => {{
          const cloud = {{}};
          snap.forEach(d => cloud[d.data().postId] = true);
          let local = {{}};
          try {{ local = JSON.parse(localStorage.getItem('likes') || '{{}}'); }} catch (e) {{}}
          localStorage.setItem('likes', JSON.stringify({{...local, ...cloud}}));
          updateFavList();
        }})
        .catch(e => console.warn('Избранное из облака недоступно:', e.message));
    }});
  }}
}} catch (e) {{ console.warn('Firebase недоступен:', e.message); }}
</script></body></html>"""

# ===================== TELEGRAM =====================

async def fetch_new_posts(client, processed_ids):
    logger.info("Сканирую канал...")
    accepted, stats = [], {"total":0,"no_kartina_tag":0,"no_main_msg":0,"already_seen":0,"parse_failed":0}
    sf = []
    def _pg(group):
        stats["total"] += 1
        group.reverse()
        ft, mm = "", None
        for m in group:
            t = m.raw_text or ""
            if t: ft += t + "\n"
            if "#картина" in t.lower(): mm = m
        if not mm: stats["no_main_msg"] += 1; return
        if "#картина@oldpictureart" not in ft.lower(): stats["no_kartina_tag"] += 1; return
        if mm.id in processed_ids: stats["already_seen"] += 1; return
        try:
            p = parse_post(ft)
            if not p: stats["parse_failed"] += 1; sf.append(ft[:500]); return
            accepted.append((mm, group, p))
        except Exception as e:
            stats["parse_failed"] += 1
            logger.error(f"Ошибка поста {mm.id}: {e}")
            sf.append(ft[:500])
    mid = max(processed_ids) if processed_ids else 0
    cai, cg = None, []
    async for msg in client.iter_messages(CHANNEL_URL, min_id=mid):
        if msg.grouped_id:
            if cai == msg.grouped_id: cg.append(msg)
            else:
                if cg: _pg(cg)
                cai, cg = msg.grouped_id, [msg]
        else:
            if cg: _pg(cg); cg = []; cai = None
            _pg([msg])
    if cg: _pg(cg)
    logger.info(f"Новых постов: {len(accepted)}. Всего проверено: {stats['total']}, обработано: {stats['already_seen']}, не картина: {stats['no_main_msg']+stats['no_kartina_tag']}, ошибки: {stats['parse_failed']}")
    if sf:
        with open("rejected_posts.txt","w",encoding="utf-8") as f:
            f.write(f"# Отбракованные посты — {datetime.now():%Y-%m-%d %H:%M}\n\n")
            for i, s in enumerate(sf, 1): f.write(f"--- #{i} ---\n{s}\n\n")
        logger.info(f"rejected_posts.txt ({len(sf)} шт.)")
    return accepted[::-1]

def generate_tag_pages(all_posts):
    logger.info("Генерация страниц тегов...")
    tp = defaultdict(list)
    for p in all_posts:
        for t in p.get("tags",[]): tp[t].append(p)
    chrono = sorted(all_posts, key=lambda x: (x.get("creation_year") or 9999, x.get("date", "")))
    cat_no = {x["filename"]: i for i, x in enumerate(chrono, 1)}
    cat_width = max(3, len(str(len(all_posts))))
    c = 0
    for tag, posts in tp.items():
        with open(os.path.join(OUTPUT_DIR, f"tag-{tag}.html"), "w", encoding="utf-8") as f:
            f.write(render_tag_page(tag, posts, cat_no, cat_width))
        c += 1
    logger.info(f"Сгенерировано {c} страниц тегов")
    return tp

def render_404():
    """Раньше 404 была пустой страницей с meta refresh: без заголовка,
    без объяснения, и на вложенных адресах редирект вёл в никуда."""
    head = head_common(
        title="Страница не найдена — Old Picture Art",
        description="Такой страницы нет. Вернитесь в галерею Old Picture Art.",
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="error-page">
<main class="error-box">
  <p class="error-code">404</p>
  <h1>Страница не найдена</h1>
  <p class="error-text">Возможно, картину переименовали или ссылка устарела.</p>
  <p><a class="random-btn" href="index.html">В галерею</a></p>
  <p class="error-links"><a href="quiz.html">Квиз</a> · <a href="timeline.html">Таймлайн</a> · <a href="museums.html">Карта музеев</a></p>
</main>
{COMMON_JS}
</body></html>"""


def generate_sitemap(all_posts):
    logger.info("Sitemap...")
    bu = BASE_URL
    # Имена файлов кириллические — в sitemap.xml адреса обязаны быть
    # процентно-закодированы, иначе поисковики игнорируют строки.
    def u(path):
        return quote(path, safe="/")
    urls = [f"  <url><loc>{bu}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for p in all_posts: urls.append(f"  <url><loc>{bu}/{u(p['filename'])}</loc><lastmod>{p['date']}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>")
    urls.append(f"  <url><loc>{bu}/feed.xml</loc><changefreq>daily</changefreq><priority>0.6</priority></url>")
    urls.append(f"  <url><loc>{bu}/museums.html</loc><changefreq>monthly</changefreq><priority>0.4</priority></url>")
    urls.append(f"  <url><loc>{bu}/quiz.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    urls.append(f"  <url><loc>{bu}/timeline.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    at = set()
    for p in all_posts:
        for t in p.get("tags",[]): at.add(t)
    for t in sorted(at): urls.append(f"  <url><loc>{bu}/{u('tag-' + t + '.html')}</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + '\n</urlset>')
    logger.info(f"Sitemap ({len(urls)} URL)")

def generate_icons():
    """Иконки для manifest.json. Раньше манифест ссылался на файлы,
    которых в репозитории не было, — установка как приложения не работала."""
    if not PIL_AVAILABLE:
        return []
    from PIL import ImageDraw
    made = []
    for size in (192, 512):
        path = os.path.join(IMAGES_DIR, f"icon-{size}.png")
        s = size / 32.0
        img = Image.new("RGBA", (size, size), (47, 47, 58, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([6*s, 7*s, 26*s, 25*s], fill=(250, 250, 250, 255))
        d.polygon([(8*s, 21*s), (13*s, 15*s), (17*s, 19*s), (20*s, 16*s), (24*s, 21*s)], fill=(107, 142, 107, 255))
        d.ellipse([18*s, 10*s, 22*s, 14*s], fill=(224, 176, 80, 255))
        img.save(path, "PNG")
        made.append(f"images/icon-{size}.png")
    return made


def generate_manifest():
    icons = [{"src": src, "sizes": f"{n}x{n}", "type": "image/png", "purpose": "any maskable"}
             for src, n in zip(generate_icons(), (192, 512))]
    data = {
        "name": "Old Picture Art",
        "short_name": "OldPictureArt",
        "description": "Галерея картин из старых музейных собраний",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "lang": "ru",
        "background_color": "#fafafa",
        "theme_color": "#fafafa",
        "icons": icons,
    }
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"manifest.json ({len(icons)} иконок)")

def rfc822(date_str):
    """RSS 2.0 требует дату в формате RFC-822. Раньше отдавали 2025-11-26,
    и часть читалок такие записи отбрасывала или сортировала как попало."""
    try:
        return format_datetime(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc))
    except Exception:
        return format_datetime(datetime.now(timezone.utc))


def generate_rss(all_posts):
    logger.info("Генерация RSS...")
    base_url = BASE_URL
    items = []
    for p in sorted(all_posts, key=lambda x: x["date"], reverse=True)[:50]:
        desc = (p.get("description") or "")[:500]
        imgs = p.get("images") or [""]
        img = quote(imgs[0], safe="/") if imgs[0] else ""
        link = f"{base_url}/{quote(p['filename'], safe='/')}"
        img_tag = f'<img src="{base_url}/{img}" style="max-width:100%" alt=""/><br>' if img else ""
        items.append(f"""    <item>
      <title>{h(p['artist'])} — {h(p['title'])}</title>
      <link>{link}</link>
      <description><![CDATA[{img_tag}{h(desc)}]]></description>
      <pubDate>{rfc822(p['date'])}</pubDate>
      <guid isPermaLink="true">{link}</guid>
    </item>""")
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>Old Picture Art</title>
  <link>{base_url}</link>
  <description>Галерея картин из Telegram канала Old Picture Art</description>
  <language>ru</language>
  <atom:link href="{base_url}/feed.xml" rel="self" type="application/rss+xml"/>
{''.join(items)}
</channel>
</rss>"""
    with open(os.path.join(OUTPUT_DIR, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(rss)
    logger.info("RSS сгенерирован")

def generate_museums_page(all_posts):
    """Генерирует карту музеев через отдельный скрипт."""
    logger.info("Генерация карты музеев...")
    try:
        subprocess.run([sys.executable, "generate_map.py"], check=True)
        logger.info("Карта музеев сгенерирована")
    except Exception as e:
        logger.error(f"Ошибка генерации карты: {e}")

def push_to_github():
    logger.info("GitHub...")
    try:
        subprocess.run(["git","add","."], check=False)
        st = subprocess.run(["git","status","--porcelain"], capture_output=True, text=True)
        if not st.stdout.strip(): logger.info("Нет изменений"); return
        subprocess.run(["git","commit","-m",f"Авто-обновление: {datetime.now():%Y-%m-%d %H:%M}"], check=False)
        subprocess.run(["git","push"], check=False)
        logger.info("Отправлено")
    except Exception as e: logger.error(f"Ошибка: {e}")

def rebuild_reset():
    logger.warning("--rebuild: удаление старых страниц")
    if input("Продолжить? [y/N]: ").strip().lower() not in ("y","yes","д","да"): print("Отмена."); sys.exit(0)
    if os.path.isdir(OUTPUT_DIR):
        for n in os.listdir(OUTPUT_DIR):
            if n.endswith(".html") or n.endswith(".xml") or n == "feed.xml":
                os.remove(os.path.join(OUTPUT_DIR, n))
    for fn in (PROCESSED_FILE, META_FILE):
        if os.path.exists(fn): os.remove(fn)

async def main():
    if "--rebuild" in sys.argv: rebuild_reset()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, ".nojekyll"), "w") as f: pass
    if not PIL_AVAILABLE: logger.warning("Pillow не установлен")
    processed_ids = set(load_json(PROCESSED_FILE, []))
    all_posts = load_json(META_FILE, [])
    logger.info("Подключение к Telegram...")
    api_id, api_hash, phone = require_credentials()
    client = await connect_with_proxy(api_id, api_hash, phone, PROXY_LIST)
    try: accepted = await fetch_new_posts(client, processed_ids)
    except Exception as e: logger.error(f"Ошибка сканирования: {e}"); await client.disconnect(); return
    for i, (mm, group, parsed) in enumerate(accepted, 1):
        date = mm.date.strftime("%Y-%m-%d")
        base = f"{date}-{slugify(parsed['artist'])}"
        fn = f"{base}.html"
        n = 2
        ex = {p["filename"] for p in all_posts}
        while fn in ex or os.path.exists(os.path.join(OUTPUT_DIR, fn)): fn = f"{base}-{n}.html"; n += 1
        logger.info(f"[{i}/{len(accepted)}] {parsed['artist'][:40]} — {parsed['title'][:50]}")
        comments = []
        if getattr(mm, "replies", None) and mm.replies.replies > 0:
            try:
                async for reply in client.iter_messages(CHANNEL_URL, reply_to=mm.id):
                    if getattr(reply, "document", None) and reply.document.mime_type.startswith("image/"): comments.append(reply)
            except Exception as e: logger.warning(f"Комментарии: {e}")
        im, hi, th = await download_images(client, group, comments, fn[:-5])
        post = {"id":mm.id,"date":date,"filename":fn,"images":im,"hires":hi,"thumbs":th,**parsed}
        all_posts.append(post)
        processed_ids.update(m.id for m in group)
        with open(os.path.join(OUTPUT_DIR, fn), "w", encoding="utf-8") as f:
            f.write(render_post_page(post, all_posts))
    await client.disconnect()
    logger.info("Отключено")
    if PIL_AVAILABLE:
        miss = [p for p in all_posts if not p.get("thumbs") and p.get("images")]
        if miss:
            logger.info(f"Миниатюры для {len(miss)} постов...")
            for p in miss:
                sl = p["filename"][:-5]
                th = []
                for i, ir in enumerate(p["images"], 1):
                    t = make_thumbnail(os.path.join(OUTPUT_DIR, ir), sl, i)
                    if t: th.append(t)
                p["thumbs"] = th
            logger.info("Миниатюры готовы")
    for post in all_posts:
        with open(os.path.join(OUTPUT_DIR, post["filename"]), "w", encoding="utf-8") as f:
            f.write(render_post_page(post, all_posts))
    save_json(META_FILE, all_posts)
    save_json(PROCESSED_FILE, sorted(processed_ids))
    generate_tag_pages(all_posts)
    generate_sitemap(all_posts)
    generate_manifest()
    generate_rss(all_posts)
    generate_museums_page(all_posts)
    # Генерация квиза и таймлайна
    try:
        subprocess.run([sys.executable, "generate_quiz.py"], check=True)
        logger.info("Квиз сгенерирован")
    except Exception as e:
        logger.error(f"Ошибка генерации квиза: {e}")
    
    try:
        subprocess.run([sys.executable, "generate_timeline.py"], check=True)
        logger.info("Таймлайн сгенерирован")
    except Exception as e:
        logger.error(f"Ошибка генерации таймлайна: {e}")
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f: f.write(render_index(all_posts))
    with open(os.path.join(OUTPUT_DIR, "404.html"), "w", encoding="utf-8") as f: f.write(render_404())
    logger.info(f"Новых постов: {len(accepted)}. Всего: {len(all_posts)}")
    push_to_github()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: logger.info("Прервано")
    except Exception as e: logger.error(f"Критическая ошибка: {e}", exc_info=True)