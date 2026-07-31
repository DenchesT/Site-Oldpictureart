import asyncio
import os
import re
import sys
import json
import shutil
import subprocess
import logging
import random
from datetime import datetime
from collections import defaultdict
from html import escape as h
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('parser.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

REQUIRED_PACKAGES = ["telethon", "Pillow", "TelethonFakeTLS"]

def auto_update_modules():
    logger.info("Проверка и автообновление модулей...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + REQUIRED_PACKAGES + ["--quiet"]
        subprocess.check_call(cmd)
        logger.info("Все необходимые модули актуальны!")
    except Exception as e:
        logger.warning(f"Ошибка при автообновлении: {e}")

auto_update_modules()

from telethon import TelegramClient, connection
import TelethonFakeTLS

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)

load_dotenv()

try:
    API_ID = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"]
    PHONE = os.environ["PHONE"]
except KeyError as e:
    raise SystemExit("❌ В .env должны быть:\nAPI_ID=...\nAPI_HASH=...\nPHONE=+79991234567")

logger.info(f"Использую пользовательский аккаунт {PHONE}")

CHANNEL_URL    = "https://t.me/oldpictureart"
OUTPUT_DIR     = "docs"
IMAGES_DIR     = "docs/images"
META_FILE      = "posts_meta.json"
PROCESSED_FILE = "processed_ids.json"
DICTIONARY_FILE = "medium_dictionary.json"

MAX_IMAGE_SIZE_MB    = 25
MAX_IMAGE_DIMENSION  = 2800
JPEG_QUALITY         = 88

THUMB_DIR        = "docs/images/thumbs"
THUMB_DIMENSION  = 600
THUMB_QUALITY    = 78

PROXY_LIST = [
    {'server': '62.113.59.20', 'port': 443, 'secret': '3f71a99978cf97e115dc89cc80aeca1f706574726f766963682e7275'},
    {'server': '138.226.237.34', 'port': 8443, 'secret': '5a76b164eadb451a845bfae212bf864973616D73756E672E636F6D'},
]

async def connect_with_proxy(api_id, api_hash, phone, proxy_list):
    for i, proxy_config in enumerate(proxy_list, 1):
        logger.info(f"Пробую прокси #{i}: {proxy_config['server']}:{proxy_config['port']}")
        proxy = (proxy_config['server'], proxy_config['port'], proxy_config['secret'])
        try:
            client = TelegramClient(f"user_session_proxy_{i}", api_id=api_id, api_hash=api_hash,
                                    connection=TelethonFakeTLS.ConnectionTcpMTProxyFakeTLS, proxy=proxy)
            await client.start(phone=phone)
            logger.info(f"Подключено через прокси #{i}: {proxy_config['server']}")
            return client
        except Exception as e:
            logger.error(f"Прокси #{i} не работает: {str(e)[:100]}")
    raise SystemExit("Все прокси не работают!")

def load_dictionary():
    default_dict = {
        "materials": ["холст", "бумага", "картон", "дерево", "доска", "металл", "стекло",
            "тонированная бумага", "рифлёная бумага", "тонированная рифлёная бумага",
            "пергамент", "шёлк", "ткань", "медь", "цинк", "алюминий", "дуб", "сосна",
            "фанера", "оргалит", "двп", "дсп", "наждачная бумага", "крафт-бумага",
            "ватман", "калька", "береста", "кожа", "кость", "слоновая кость",
            "перламутр", "мрамор", "гранит", "известняк", "гипс", "терракота", "майолика"],
        "techniques": ["масло", "акварель", "гуашь", "темпера", "пастель", "уголь",
            "карандаш", "графит", "тушь", "сепия", "сангина", "мел", "акрил", "чернила",
            "белила", "лак", "золото", "серебро", "бронза", "эмаль", "керамика", "фарфор",
            "гобелен", "мозаика", "литография", "офорт", "гравюра", "ксилография",
            "шелкография", "тушь-сепия", "акварель-сепия", "белая гуашь", "чёрный мел",
            "итальянский карандаш", "свинцовый карандаш", "серебряный штифт", "соус",
            "бистр", "лавис", "акватинта", "меццо-тинто", "сухая игла", "монотипия",
            "резцовая гравюра", "пунктир"],
        "unknown_words": []
    }
    if os.path.exists(DICTIONARY_FILE):
        with open(DICTIONARY_FILE, "r", encoding="utf-8") as f:
            saved_dict = json.load(f)
            for key in default_dict:
                if key not in saved_dict:
                    saved_dict[key] = default_dict[key]
            return saved_dict
    return default_dict

def save_dictionary(dictionary):
    with open(DICTIONARY_FILE, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)

def parse_medium_details(medium_text: str) -> dict:
    if not medium_text:
        return {"material": "", "techniques": [], "size": ""}
    dictionary = load_dictionary()
    text = medium_text.strip().rstrip(".")
    size_patterns = [
        r'(\d+[,.]?\d*\s*[xх×]\s*\d+[,.]?\d*\s*(?:см|mm|мм|m|м)?)',
        r'(\d+[,.]?\d*\s*(?:см|mm|мм|m|м)\s*[xх×]\s*\d+[,.]?\d*\s*(?:см|mm|мм|m|м)?)',
        r'(\d+[,.]?\d*\s*[xх×]\s*\d+[,.]?\d*)',
    ]
    size = ""
    for pattern in size_patterns:
        size_match = re.search(pattern, text, re.IGNORECASE)
        if size_match:
            size = size_match.group(1).strip()
            text = text.replace(size_match.group(0), "").strip().rstrip(",.").strip()
            break
    parts = [p.strip() for p in text.split(",") if p.strip()]
    material = ""
    techniques = []
    size_words = re.compile(r'^\d+[,.]?\d*\s*(?:[xх×]|см|mm|мм|m|м)')
    for part in parts:
        part_lower = part.lower().strip()
        if size_words.match(part) or re.match(r'^\d+[,.]?\d*$', part):
            continue
        if re.search(r'\d+[,.]?\d*\s*[xх×]\s*\d+', part):
            continue
        found_material = False
        for mat in dictionary["materials"]:
            if mat in part_lower:
                if not material:
                    material = part
                found_material = True
                break
        if found_material:
            continue
        found_technique = False
        for tech in dictionary["techniques"]:
            if tech in part_lower:
                techniques.append(part)
                found_technique = True
                break
        if found_technique:
            continue
        if len(part) > 2 and not re.search(r'\d{3,}', part):
            material_keywords = ["бумаг", "холст", "картон", "дерев", "доск", "металл",
                               "стекл", "ткань", "шёлк", "кож", "кость", "камень"]
            if any(kw in part_lower for kw in material_keywords):
                if not material:
                    material = part
                if part not in dictionary["materials"]:
                    dictionary["materials"].append(part)
                    logger.info(f"➕ Новый материал: {part}")
            else:
                techniques.append(part)
                if part not in dictionary["techniques"]:
                    dictionary["techniques"].append(part)
                    logger.info(f"➕ Новая техника: {part}")
    save_dictionary(dictionary)
    return {"material": material, "techniques": techniques, "size": size}


# ---------- ПАРСИНГ ПОСТА ----------

SEPARATOR_RE = re.compile(r"\s*[⸻⸺]\s*")
URL_RE = re.compile(r"https?://(?:(?!https?://)[^\s⸻⸺])+")
TAG_RE = re.compile(r"#(\w+)@\w+")

PROVENANCE_MARKERS = [
    "до ", "с 1", "с 2", "поступил", "поступла", "собрание", "коллекци",
    "приобрет", "продан", "продаж", "галере", "бывш", "передан",
    "находил", "хранил", "наследств",
    "bequest", "acquired", "purchased", "donated", "gift of", "private",
]

def looks_like_provenance(s: str) -> bool:
    years = len(re.findall(r"\b1[5-9]\d{2}\b|\b20\d{2}\b", s))
    text_lo = s.lower()
    has_marker = any(m in text_lo for m in PROVENANCE_MARKERS)
    return years >= 2 and has_marker

def _split_steps(block: str) -> list[str]:
    return [line.strip() for line in block.split("\n") if line.strip()]

def _clean_desc(block: str) -> str:
    return re.sub(r"\s*\n\s*", " ", block).strip()

def parse_post(text: str) -> dict:
    if not text:
        return {}
    try:
        urls: list[str] = []
        def _grab(m):
            urls.append(m.group(0))
            return " "
        text_clean = URL_RE.sub(_grab, text)
        raw_tags = TAG_RE.findall(text_clean)
        text_clean = TAG_RE.sub("", text_clean)
        parts = [p.strip() for p in SEPARATOR_RE.split(text_clean) if p.strip()]
        if len(parts) < 4:
            return {}
        artist = re.sub(r"\s+", " ", parts[0]) if parts[0] else ""
        title  = re.sub(r"\s+", " ", parts[1]) if parts[1] else ""
        medium = re.sub(r"\s+", " ", parts[2]) if parts[2] else ""
        museum = re.sub(r"\s+", " ", parts[3]) if parts[3] else ""
        if not artist or not title:
            return {}
        extras = parts[4:]
        history_steps: list[str] = []
        description = ""
        if len(extras) == 1:
            if looks_like_provenance(extras[0]):
                history_steps = _split_steps(extras[0])
            else:
                description = _clean_desc(extras[0])
        elif len(extras) >= 2:
            if looks_like_provenance(extras[0]):
                history_steps = _split_steps(extras[0])
                description = "\n\n".join(_clean_desc(e) for e in extras[1:])
            else:
                description = "\n\n".join(_clean_desc(e) for e in extras)
        medium_details = parse_medium_details(medium)
        return {
            "artist": artist, "title": title, "medium": medium,
            "material": medium_details["material"],
            "techniques": medium_details["techniques"],
            "size": medium_details["size"],
            "museum": museum, "history": history_steps,
            "description": description, "urls": urls,
            "tags": sorted(set(raw_tags)), "raw": text,
        }
    except Exception as e:
        logger.error(f"Ошибка в parse_post: {e}")
        return {}

# ---------- УТИЛИТЫ ----------

def slugify(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t).strip("-")
    return (t[:60] or "post")

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def compress_if_huge(filepath: str) -> str:
    if not PIL_AVAILABLE or not os.path.exists(filepath):
        return filepath
    try:
        size_mb = os.path.getsize(filepath) / 1024 / 1024
    except OSError:
        return filepath
    if size_mb < MAX_IMAGE_SIZE_MB:
        return filepath
    try:
        img = Image.open(filepath)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
        base, ext = os.path.splitext(filepath)
        new_path = base + ".jpg" if ext.lower() not in (".jpg", ".jpeg") else filepath
        if new_path != filepath:
            try: os.remove(filepath)
            except OSError: pass
        img.save(new_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
        new_mb = os.path.getsize(new_path) / 1024 / 1024
        logger.info(f"Сжато: {size_mb:.1f}MB → {new_mb:.1f}MB")
        return new_path
    except Exception as e:
        logger.warning(f"Не удалось сжать {filepath}: {e}")
        return filepath

def make_thumbnail(src_path: str, slug: str, idx: int) -> str:
    if not PIL_AVAILABLE or not os.path.exists(src_path):
        return ""
    os.makedirs(THUMB_DIR, exist_ok=True)
    suffix = "" if idx == 1 else f"-{idx}"
    thumb_name = f"{slug}{suffix}.jpg"
    thumb_path = os.path.join(THUMB_DIR, thumb_name)
    if os.path.exists(thumb_path):
        return f"images/thumbs/{thumb_name}"
    try:
        img = Image.open(src_path)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.thumbnail((THUMB_DIMENSION, THUMB_DIMENSION), Image.LANCZOS)
        img.save(thumb_path, "JPEG", quality=THUMB_QUALITY, optimize=True)
        return f"images/thumbs/{thumb_name}"
    except Exception as e:
        logger.warning(f"Не удалось создать миниатюру: {e}")
        return ""

async def download_with_retry(client, msg, filepath, max_retries=3):
    for attempt in range(max_retries):
        try:
            await client.download_media(msg, filepath)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Попытка {attempt + 1} не удалась. Повтор...")
                await asyncio.sleep(5)
            else:
                raise
    return False

async def download_images(client, group, comments, post_slug):
    images, hires, thumbs = [], [], []
    photo_idx = 0
    for msg in group:
        if getattr(msg, "photo", None):
            photo_idx += 1
            filename = f"{post_slug}-{photo_idx}.jpg"
            filepath = os.path.join(IMAGES_DIR, filename)
            if not os.path.exists(filepath):
                await download_with_retry(client, msg, filepath)
            images.append(f"images/{filename}")
            thumb = make_thumbnail(filepath, post_slug, photo_idx)
            if thumb:
                thumbs.append(thumb)
    all_docs = [m for m in group if getattr(m, "document", None) and m.document.mime_type.startswith("image/")]
    all_docs.extend(comments)
    for i, msg in enumerate(all_docs, 1):
        ext = ".jpg"
        for attr in getattr(msg.document, "attributes", []):
            if hasattr(attr, "file_name"):
                ext = os.path.splitext(attr.file_name)[1].lower()
                break
        filename = f"{post_slug}-hires-{i}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            try:
                await download_with_retry(client, msg, filepath)
            except Exception as e:
                logger.error(f"Не скачался оригинал {msg.id}: {e}")
                continue
        filepath = compress_if_huge(filepath)
        hires.append(f"images/{os.path.basename(filepath)}")
    if not images and hires:
        images = hires.copy()
        if PIL_AVAILABLE and not thumbs:
            for i, hires_rel in enumerate(hires, 1):
                hires_abs = os.path.join(OUTPUT_DIR, hires_rel)
                thumb = make_thumbnail(hires_abs, post_slug, i)
                if thumb:
                    thumbs.append(thumb)
    return images, hires, thumbs

# ---------- HTML ----------

def render_post_page(post: dict) -> str:
    artist = h(post["artist"]); title = h(post["title"])
    medium = h(post["medium"]); museum = h(post["museum"])

    description = post.get("description") or ""
    urls = post.get("urls") or ([post["url"]] if post.get("url") else [])

    img_html_parts = []
    hires_list = post.get("hires", [])
    for i, src in enumerate(post["images"]):
        link_href = hires_list[i] if i < len(hires_list) else src
        img_html_parts.append(
            f'<a href="{h(link_href)}" target="_blank" title="Открыть оригинал">'
            f'<img src="{h(src)}" alt="{artist} — {title}" class="painting" loading="lazy">'
            f'</a>'
        )
    img_html = "\n".join(img_html_parts)

    material_html = f'<span class="material">📄 {h(post.get("material", ""))}</span>' if post.get("material") else ""
    techniques_html = f'<span class="techniques">🖌 {h(", ".join(post.get("techniques", [])))}</span>' if post.get("techniques") else ""
    size_html = f'<span class="size">📏 {h(post.get("size", ""))}</span>' if post.get("size") else ""
    medium_details_html = f'<div class="medium-details">{material_html} {techniques_html} {size_html}</div>'

    tags_html = ""
    if post["tags"]:
        tags_html = '<div class="tags">' + " ".join(
            f'<a href="tag-{h(t)}.html" class="tag">#{h(t)}</a>' for t in post["tags"]
        ) + "</div>"

    description_html = ""
    if description:
        paras = "".join(f"<p>{h(p)}</p>" for p in description.split("\n\n") if p.strip())
        description_html = f'<section class="description">{paras}</section>'

    history = post.get("history") or post.get("note") or ""
    if isinstance(history, str):
        history_steps = [s.strip() for s in re.split(r"⸻|\n", history) if s.strip()]
    else:
        history_steps = history

    history_html = ""
    if history_steps:
        items_str = "".join(f"<li>{h(step)}</li>" for step in history_steps)
        history_html = '<section class="history"><h3>Происхождение</h3><ul>' + items_str + '</ul></section>'

    sources_html = ""
    if urls:
        if len(urls) == 1:
            u = urls[0]
            sources_html = f'<p class="source">Источник: <a href="{h(u)}" target="_blank" rel="noopener">{h(u)}</a></p>'
        else:
            items = "".join(f'<li><a href="{h(u)}" target="_blank" rel="noopener">{h(u)}</a></li>' for u in urls)
            sources_html = f'<div class="sources"><strong>Источники:</strong><ul class="source-list">{items}</ul></div>'

    return f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a2e" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>{artist} — {title}</title>
<style>
:root{{--bg:#fafafa;--text:#222;--card-bg:#fff;--tag-bg:#eee;--tag-text:#555;--border:#ddd;--muted:#555;--link:#0366d6;--shadow:rgba(0,0,0,.15);--history-bg:#f3eedb;--history-border:#b8a86a}}
[data-theme="dark"]{{--bg:#1a1a2e;--text:#e0e0e0;--card-bg:#16213e;--tag-bg:#0f3460;--tag-text:#e0e0e0;--border:#333;--muted:#aaa;--link:#64b5f6;--shadow:rgba(0,0,0,.5);--history-bg:#2d2d1a;--history-border:#8b7a2e}}
*{{box-sizing:border-box}}
body{{max-width:900px;margin:0 auto;padding:1.5rem;font-family:Georgia,serif;background:var(--bg);color:var(--text);line-height:1.55;transition:background .3s,color .3s;-webkit-tap-highlight-color:transparent}}
.painting{{max-width:100%;max-height:70vh;display:block;margin:1.5rem auto;box-shadow:0 4px 20px var(--shadow);border-radius:4px;transition:transform .2s;cursor:pointer}}
.painting:active{{transform:scale(1.02)}}
h1{{font-size:1.8rem;margin:0 0 .3rem;line-height:1.2}}
h2{{font-size:1.25rem;font-style:italic;font-weight:normal;color:var(--muted);margin:0 0 1rem}}
.medium-details{{display:flex;flex-wrap:wrap;gap:.5rem 1.5rem;margin:1rem 0;padding:.8rem;background:var(--card-bg);border-radius:6px;font-size:.9rem;color:var(--muted);border:1px solid var(--border)}}
.museum{{font-style:italic;color:var(--muted);margin:.3rem 0}}
.source a,.source-list a{{color:var(--link);word-break:break-all}}
.description{{margin:1.5rem 0;text-align:justify}}
.description p{{margin:.6rem 0;line-height:1.65}}
.history{{margin:1.8rem 0;padding:1rem 1.25rem;background:var(--history-bg);border-left:3px solid var(--history-border);border-radius:4px}}
.history h3{{margin:0 0 .6rem;font-size:1rem;color:#5a4f2a}}
.history ul{{margin:0;padding-left:1.2rem}}
.history li{{margin:.4rem 0;color:#4a4a4a;font-size:.95rem;line-height:1.5}}
.tags{{margin-top:1.5rem;padding-top:1rem;border-top:1px solid var(--border);display:flex;flex-wrap:wrap;gap:.4rem}}
.tag{{display:inline-block;background:var(--tag-bg);color:var(--tag-text);text-decoration:none;padding:.3rem .7rem;border-radius:4px;font-size:.85rem;transition:background .2s}}
.tag:active{{background:var(--link);color:#fff}}
.top-nav{{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin-bottom:1rem}}
.back{{display:inline-block;color:var(--link);text-decoration:none;font-size:.95rem}}
time{{color:var(--muted);font-size:.85rem;display:block;margin-top:.5rem}}
.theme-toggle{{position:fixed;top:1rem;right:1rem;background:var(--card-bg);border:1px solid var(--border);padding:.5rem 1rem;border-radius:20px;cursor:pointer;color:var(--text);z-index:1000;font-size:.9rem;box-shadow:0 2px 8px var(--shadow)}}
.random-btn{{display:inline-block;padding:.3rem 1rem;background:var(--link);color:#fff;text-decoration:none;border-radius:4px;font-size:.9rem}}
.scroll-top{{position:fixed;bottom:1.5rem;right:1.5rem;width:44px;height:44px;background:var(--link);color:#fff;border:none;border-radius:50%;font-size:1.3rem;cursor:pointer;box-shadow:0 2px 10px var(--shadow);z-index:999;display:none;align-items:center;justify-content:center}}
.scroll-top.visible{{display:flex}}
.scroll-top:active{{transform:scale(.9)}}
@media(max-width:768px){{
  body{{padding:.8rem;font-size:15px}}
  h1{{font-size:1.4rem}}
  h2{{font-size:1.1rem;margin-bottom:.5rem}}
  .painting{{margin:.8rem auto;max-height:50vh}}
  .medium-details{{flex-direction:column;gap:.3rem;padding:.6rem;font-size:.8rem}}
  .theme-toggle{{top:.5rem;right:.5rem;padding:.4rem .8rem;font-size:.75rem}}
  .random-btn{{padding:.2rem .7rem;font-size:.8rem}}
  .tags{{gap:.3rem;margin-top:1rem;padding-top:.8rem}}
  .tag{{padding:.25rem .6rem;font-size:.78rem}}
  .description{{font-size:.9rem}}
  .history{{padding:.8rem 1rem;margin:1.2rem 0}}
  .scroll-top{{width:40px;height:40px;font-size:1.1rem;bottom:1rem;right:1rem}}
  .back{{font-size:.85rem}}
}}
@media(max-width:480px){{
  body{{padding:.5rem;font-size:14px}}
  h1{{font-size:1.2rem}}
  h2{{font-size:1rem}}
  .painting{{max-height:40vh;margin:.5rem auto}}
  .medium-details{{padding:.4rem;font-size:.75rem;gap:.2rem}}
  .tag{{padding:.2rem .5rem;font-size:.7rem}}
  .theme-toggle{{top:.3rem;right:.3rem;padding:.3rem .6rem;font-size:.7rem}}
  .random-btn{{padding:.2rem .6rem;font-size:.7rem}}
  .scroll-top{{width:36px;height:36px;font-size:1rem;bottom:.8rem;right:.8rem}}
}}
</style></head><body>
<button class="theme-toggle" onclick="toggleTheme()">🌓</button>
<button class="scroll-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="Наверх">↑</button>
<div class="top-nav">
<a href="index.html" class="back">← На главную</a>
<a href="#" class="random-btn" onclick="goRandom()">🎲 Случайная</a>
</div>
<article>
<h1>{artist}</h1>
<h2>{title}</h2>
{img_html}
{medium_details_html}
<p class="museum">🏛 {museum}</p>
{description_html}
{history_html}
{sources_html}
<time>{h(post['date'])}</time>
{tags_html}
</article>
<script>
function toggleTheme(){{const h=document.documentElement;const c=h.getAttribute('data-theme');const n=c==='light'?'dark':'light';h.setAttribute('data-theme',n);localStorage.setItem('theme',n)}}
(()=>{{const s=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',s)}})();
function goRandom(){{const p=JSON.parse(localStorage.getItem('allPosts')||'[]');if(p.length)window.location.href=p[Math.floor(Math.random()*p.length)]}}
window.addEventListener('scroll',function(){{const b=document.querySelector('.scroll-top');if(b)b.classList.toggle('visible',window.scrollY>400)}});
</script></body></html>"""


def surname_key(full_name: str) -> str:
    first = full_name.split(",")[0].strip()
    words = first.split()
    if not words:
        return full_name.lower()
    return words[-1].lower()


def render_tag_page(tag: str, posts: list) -> str:
    cards = []
    for p in sorted(posts, key=lambda x: x["date"], reverse=True):
        cover = ""
        if p.get("thumbs"):
            cover = p["thumbs"][0]
        elif p.get("images"):
            cover = p["images"][0]
        cover = h(cover)
        cards.append(f"""
        <a class="card" href="{h(p['filename'])}">
          <div class="card-img"><img src="{cover}" alt="" loading="lazy"></div>
          <div class="card-body">
            <div class="card-artist">{h(p['artist'])}</div>
            <div class="card-title">{h(p['title'])}</div>
          </div>
        </a>""")
    
    return f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a2e" media="(prefers-color-scheme: dark)">
<title>#{h(tag)} — Old Picture Art</title>
<style>
:root{{--bg:#fafafa;--text:#222;--card-bg:#fff;--border:#ddd;--muted:#666}}
[data-theme="dark"]{{--bg:#1a1a2e;--text:#e0e0e0;--card-bg:#16213e;--border:#333;--muted:#aaa}}
*{{box-sizing:border-box}}
body{{max-width:1200px;margin:0 auto;padding:1.5rem;font-family:Georgia,serif;background:var(--bg);color:var(--text);transition:background .3s,color .3s;-webkit-tap-highlight-color:transparent}}
h1{{text-align:center;margin-bottom:2rem;font-size:1.8rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1.5rem}}
.card{{background:var(--card-bg);text-decoration:none;color:var(--text);border-radius:6px;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,.1);transition:transform .15s;border:1px solid var(--border)}}
.card:active{{transform:scale(.98)}}
.card-img{{width:100%;aspect-ratio:4/3;overflow:hidden;background:var(--border)}}
.card-img img{{width:100%;height:100%;object-fit:cover;display:block}}
.card-body{{padding:.8rem 1rem}}
.card-artist{{font-weight:bold;font-size:.95rem}}
.card-title{{font-style:italic;color:var(--muted);margin-top:.3rem;font-size:.85rem}}
.back{{display:inline-block;margin-bottom:1rem;color:#0366d6;text-decoration:none;font-size:.95rem}}
.theme-toggle{{position:fixed;top:1rem;right:1rem;background:var(--card-bg);border:1px solid var(--border);padding:.5rem 1rem;border-radius:20px;cursor:pointer;color:var(--text);z-index:1000;font-size:.9rem;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
.scroll-top{{position:fixed;bottom:1.5rem;right:1.5rem;width:44px;height:44px;background:var(--link,#0366d6);color:#fff;border:none;border-radius:50%;font-size:1.3rem;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.2);z-index:999;display:none;align-items:center;justify-content:center}}
.scroll-top.visible{{display:flex}}
@media(max-width:768px){{
  body{{padding:.8rem}}
  h1{{font-size:1.3rem}}
  .grid{{grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:.8rem}}
  .card-body{{padding:.6rem}}
  .card-artist{{font-size:.85rem}}
  .card-title{{font-size:.75rem}}
  .theme-toggle{{top:.5rem;right:.5rem;padding:.4rem .8rem;font-size:.75rem}}
  .scroll-top{{width:40px;height:40px;font-size:1.1rem;bottom:1rem;right:1rem}}
}}
@media(max-width:480px){{
  body{{padding:.5rem}}
  h1{{font-size:1.1rem;margin-bottom:1.2rem}}
  .grid{{grid-template-columns:repeat(2,1fr);gap:.5rem}}
  .card-img{{aspect-ratio:1/1}}
  .card-body{{padding:.4rem .5rem}}
  .card-artist{{font-size:.78rem}}
  .card-title{{font-size:.7rem}}
  .theme-toggle{{top:.3rem;right:.3rem;padding:.3rem .6rem;font-size:.7rem}}
  .scroll-top{{width:36px;height:36px;font-size:1rem;bottom:.8rem;right:.8rem}}
}}
</style></head><body>
<button class="theme-toggle" onclick="toggleTheme()">🌓</button>
<button class="scroll-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="Наверх">↑</button>
<a href="index.html" class="back">← На главную</a>
<h1>#{h(tag)} ({len(posts)})</h1>
<div class="grid">{''.join(cards)}</div>
<script>
function toggleTheme(){{const h=document.documentElement;const c=h.getAttribute('data-theme');const n=c==='light'?'dark':'light';h.setAttribute('data-theme',n);localStorage.setItem('theme',n)}}
(()=>{{const s=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',s)}})();
window.addEventListener('scroll',function(){{const b=document.querySelector('.scroll-top');if(b)b.classList.toggle('visible',window.scrollY>400)}});
</script></body></html>"""

def render_index(all_posts) -> str:
    MONTHS = {
        "01": "Январь", "02": "Февраль", "03": "Март", "04": "Апрель",
        "05": "Май", "06": "Июнь", "07": "Июль", "08": "Август",
        "09": "Сентябрь", "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь"
    }

    posts_sorted = sorted(all_posts, key=lambda x: x["date"], reverse=True)

    authors = sorted({p["artist"] for p in all_posts if p.get("artist")}, key=surname_key)
    museums = sorted({p.get("museum", "") for p in all_posts if p.get("museum")})
    
    materials_set = set()
    techniques_set = set()
    for p in all_posts:
        material = p.get("material", "")
        if material:
            materials_set.add(material)
        for tech in p.get("techniques", []):
            if tech and len(tech) > 2:
                techniques_set.add(tech)
    
    materials = sorted(materials_set)
    techniques = sorted(techniques_set)

    archive = defaultdict(set)
    for p in all_posts:
        if p.get("date") and "-" in p["date"]:
            year, month, _ = p["date"].split("-")
            archive[year].add(month)

    archive_sorted = {y: sorted(list(ms), reverse=True) for y, ms in sorted(archive.items(), reverse=True)}

    cards = []
    for p in posts_sorted:
        cover = ""
        if p.get("thumbs"):
            cover = p["thumbs"][0]
        elif p.get("images"):
            cover = p["images"][0]
        cover = h(cover)

        year, month = "", ""
        if p.get("date") and "-" in p["date"]:
            year, month, _ = p["date"].split("-")

        museum_slug = slugify(p.get("museum", ""))
        material_slug = slugify(p.get("material", ""))
        techniques_slugs = " ".join([slugify(t) for t in p.get("techniques", [])])

        cards.append(f"""
        <a class="card" href="{h(p['filename'])}"
           data-artist="{h(p['artist'].lower())}"
           data-year="{year}"
           data-month="{month}"
           data-museum="{h(museum_slug)}"
           data-material="{h(material_slug)}"
           data-techniques="{h(techniques_slugs)}">
          <div class="card-img"><img src="{cover}" alt="" loading="lazy" decoding="async"></div>
          <div class="card-body">
            <div class="card-artist">{h(p['artist'])}</div>
            <div class="card-title">{h(p['title'])}</div>
            <div class="card-info">{h(p.get('material', ''))} {h(', '.join(p.get('techniques', [])[:2]))}</div>
          </div>
        </a>""")

    authors_html = "".join(
        f'<li><a href="#" class="filter-link" data-type="artist" data-val="{h(a.lower())}">{h(a)}</a></li>'
        for a in authors
    )
    
    museums_html = "".join(
        f'<li><a href="#" class="filter-link" data-type="museum" data-val="{h(slugify(m))}">{h(m[:50])}</a></li>'
        for m in museums if m
    )
    
    materials_html = "".join(
        f'<li><a href="#" class="filter-link" data-type="material" data-val="{h(slugify(m))}">{h(m)}</a></li>'
        for m in materials
    )
    
    techniques_html = "".join(
        f'<li><a href="#" class="filter-link" data-type="technique" data-val="{h(slugify(t))}">{h(t)}</a></li>'
        for t in techniques
    )

    archive_html = ""
    for y, ms in archive_sorted.items():
        archive_html += f'<li><a href="#" class="filter-link" data-type="year" data-val="{y}"><b>{y} год</b></a><ul class="month-list">'
        for m in ms:
            m_name = MONTHS.get(m, m)
            archive_html += f'<li><a href="#" class="filter-link" data-type="month" data-year="{y}" data-val="{m}">{m_name}</a></li>'
        archive_html += '</ul></li>'

    all_filenames = json.dumps([p["filename"] for p in posts_sorted])

    return f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a2e" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Old Picture Art — Галерея</title>
<style>
:root{{--bg:#fafafa;--text:#222;--card-bg:#fff;--sidebar-bg:#fff;--border:#ddd;--muted:#777;--link:#555;--active:#0366d6;--shadow:rgba(0,0,0,.08);--reset-bg:#ffeef0;--reset-text:#d73a49;--input-border:#ccc}}
[data-theme="dark"]{{--bg:#1a1a2e;--text:#e0e0e0;--card-bg:#16213e;--sidebar-bg:#0f3460;--border:#333;--muted:#aaa;--link:#64b5f6;--active:#90caf9;--shadow:rgba(0,0,0,.3);--reset-bg:#3d1a1a;--reset-text:#ef9a9a;--input-border:#444}}
*{{box-sizing:border-box}}
body{{max-width:1400px;margin:0 auto;padding:1.5rem;font-family:Georgia,serif;background:var(--bg);color:var(--text);transition:background .3s,color .3s;-webkit-tap-highlight-color:transparent}}
header{{margin-bottom:2rem;text-align:center}}
h1{{font-size:2.2rem;margin:0 0 .5rem}}
.subtitle{{color:var(--muted);margin-bottom:1.5rem}}
.search-box{{width:100%;max-width:500px;padding:.8rem 1rem;font-size:1rem;border:1px solid var(--input-border);border-radius:6px;font-family:inherit;background:var(--card-bg);color:var(--text)}}
.layout{{display:flex;gap:2rem;align-items:flex-start}}
.sidebar{{width:300px;flex-shrink:0;background:var(--sidebar-bg);padding:1.5rem;border-radius:6px;box-shadow:0 2px 6px var(--shadow);position:sticky;top:1.5rem;max-height:calc(100vh - 3rem);overflow-y:auto;border:1px solid var(--border)}}
.sidebar::-webkit-scrollbar{{width:6px}}
.sidebar::-webkit-scrollbar-thumb{{background-color:#ccc;border-radius:3px}}
.sidebar-section{{margin-bottom:1.2rem}}
.sidebar-title{{font-size:1rem;font-weight:bold;margin:0 0 .6rem;border-bottom:1px solid var(--border);padding-bottom:.4rem;cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none}}
.sidebar-title::after{{content:'▼';font-size:.7rem;transition:transform .2s}}
.sidebar-title.collapsed::after{{transform:rotate(-90deg)}}
.sidebar-content{{overflow:hidden;transition:max-height .3s ease}}
.sidebar-content.collapsed{{max-height:0!important}}
.sidebar ul{{list-style:none;padding:0;margin:0}}
.sidebar li{{margin-bottom:.35rem}}
.sidebar a{{text-decoration:none;color:var(--link);font-size:.88rem;display:block;transition:color .15s;padding:2px 4px;border-radius:3px}}
.sidebar a:hover,.sidebar a:active{{color:var(--active);background:var(--border)}}
.sidebar a.active{{color:var(--active);font-weight:bold;background:var(--border)}}
.month-list{{padding-left:1.2rem!important;margin-top:.3rem!important;font-size:.9em}}
.filter-reset{{display:none;margin-bottom:.8rem;color:var(--reset-text)!important;font-weight:bold;text-align:center;background:var(--reset-bg);padding:.6rem;border-radius:4px;text-decoration:none}}
.main-content{{flex-grow:1;min-width:0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:1.5rem}}
.card{{background:var(--card-bg);text-decoration:none;color:var(--text);border-radius:8px;overflow:hidden;box-shadow:0 2px 8px var(--shadow);transition:transform .15s,box-shadow .15s;border:1px solid var(--border);-webkit-tap-highlight-color:transparent}}
.card:active{{transform:scale(.98)}}
.card-img{{width:100%;aspect-ratio:4/3;background:var(--border);overflow:hidden}}
.card-img img{{width:100%;height:100%;object-fit:cover;display:block}}
.card-body{{padding:.9rem 1.1rem}}
.card-artist{{font-weight:bold;font-size:1rem;line-height:1.2;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-title{{font-style:italic;color:var(--muted);font-size:.9rem;margin-top:.35rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-info{{font-size:.8rem;color:var(--muted);margin-top:.3rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.theme-toggle{{position:fixed;top:1rem;right:1rem;background:var(--card-bg);border:1px solid var(--border);padding:.5rem 1rem;border-radius:20px;cursor:pointer;color:var(--text);font-size:.9rem;box-shadow:0 2px 8px var(--shadow);z-index:1000}}
.random-btn{{display:inline-block;padding:.5rem 1.5rem;background:var(--active);color:#fff;text-decoration:none;border-radius:20px;font-size:.9rem;transition:opacity .2s;margin-bottom:1rem}}
.random-btn:active{{opacity:.8}}
.scroll-top{{position:fixed;bottom:1.5rem;right:1.5rem;width:44px;height:44px;background:var(--active);color:#fff;border:none;border-radius:50%;font-size:1.3rem;cursor:pointer;box-shadow:0 2px 10px var(--shadow);z-index:999;display:none;align-items:center;justify-content:center}}
.scroll-top.visible{{display:flex}}
.scroll-top:active{{transform:scale(.9)}}
@media(max-width:900px){{
  body{{padding:.8rem}}
  h1{{font-size:1.5rem}}
  .subtitle{{font-size:.9rem}}
  .search-box{{max-width:100%;padding:.7rem;font-size:.9rem}}
  .layout{{flex-direction:column;gap:.5rem}}
  .sidebar{{width:100%;position:static;max-height:none;padding:.8rem;border-radius:8px}}
  .sidebar-section{{margin-bottom:.5rem}}
  .sidebar-title{{font-size:.9rem;padding:.6rem .8rem;margin:0 0 .3rem 0;background:var(--card-bg);border-radius:6px;border:1px solid var(--border)}}
  .sidebar-content{{padding:0 .3rem}}
  .sidebar ul{{display:flex;flex-wrap:wrap;gap:.25rem}}
  .sidebar li{{margin-bottom:0}}
  .sidebar a{{font-size:.78rem;padding:.3rem .6rem;background:var(--bg);border-radius:15px;border:1px solid var(--border)}}
  .month-list{{padding-left:0!important;display:flex;flex-wrap:wrap;gap:.2rem}}
  .month-list li{{margin:0}}
  .month-list a{{font-size:.7rem!important;padding:.2rem .45rem}}
  .grid{{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.8rem}}
  .card{{border-radius:6px}}
  .card-body{{padding:.6rem .7rem}}
  .card-artist{{font-size:.85rem}}
  .card-title{{font-size:.75rem;margin-top:.2rem}}
  .card-info{{font-size:.7rem}}
  .theme-toggle{{top:.5rem;right:.5rem;padding:.4rem .8rem;font-size:.75rem;border-radius:15px}}
  .random-btn{{padding:.4rem 1rem;font-size:.8rem;margin-bottom:.5rem}}
  .filter-reset{{font-size:.85rem;padding:.5rem}}
  .scroll-top{{width:40px;height:40px;font-size:1.1rem;bottom:1rem;right:1rem}}
}}
@media(max-width:480px){{
  body{{padding:.4rem}}
  h1{{font-size:1.3rem}}
  .grid{{grid-template-columns:repeat(2,1fr);gap:.4rem}}
  .card-img{{aspect-ratio:1/1}}
  .search-box{{padding:.6rem;font-size:.85rem}}
  .sidebar{{padding:.5rem}}
  .sidebar a{{font-size:.72rem;padding:.2rem .45rem}}
  .sidebar-title{{font-size:.8rem;padding:.5rem .6rem}}
  .theme-toggle{{padding:.3rem .6rem;font-size:.7rem}}
  .random-btn{{padding:.3rem .8rem;font-size:.75rem}}
  .card-body{{padding:.4rem .5rem}}
  .card-artist{{font-size:.78rem}}
  .card-title{{font-size:.7rem}}
  .scroll-top{{width:36px;height:36px;font-size:1rem;bottom:.7rem;right:.7rem}}
}}
</style></head><body>
<button class="theme-toggle" onclick="toggleTheme()">🌓 Тема</button>
<button class="scroll-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="Наверх">↑</button>
<header>
<h1>🎨 Old Picture Art</h1>
<div class="subtitle">Картин в коллекции: <strong>{len(posts_sorted)}</strong></div>
<a href="#" class="random-btn" onclick="goRandom()">🎲 Случайная картина</a>
<input type="text" class="search-box" placeholder="🔍 Поиск по художнику или картине…" id="search">
</header>
<div class="layout">
  <aside class="sidebar">
    <a href="#" id="reset-filter" class="filter-reset">✕ Сбросить все фильтры</a>
    <div class="sidebar-section">
      <div class="sidebar-title" onclick="toggleSection(this)">📅 Архив</div>
      <div class="sidebar-content"><ul>{archive_html}</ul></div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-title" onclick="toggleSection(this)">👨‍🎨 Художники</div>
      <div class="sidebar-content"><ul>{authors_html}</ul></div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-title" onclick="toggleSection(this)">🏛 Музеи</div>
      <div class="sidebar-content"><ul>{museums_html}</ul></div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-title" onclick="toggleSection(this)">📄 Материал</div>
      <div class="sidebar-content collapsed"><ul>{materials_html}</ul></div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-title" onclick="toggleSection(this)">🖌 Техника</div>
      <div class="sidebar-content collapsed"><ul>{techniques_html}</ul></div>
    </div>
  </aside>
  <main class="main-content">
    <div class="grid" id="cards">{''.join(cards)}</div>
  </main>
</div>
<script>
const ALL_POSTS = {all_filenames};
function toggleTheme(){{const h=document.documentElement;const c=h.getAttribute('data-theme');const n=c==='light'?'dark':'light';h.setAttribute('data-theme',n);localStorage.setItem('theme',n)}}
(()=>{{const s=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',s);localStorage.setItem('allPosts',JSON.stringify(ALL_POSTS))}})();
function goRandom(){{if(ALL_POSTS.length)window.location.href=ALL_POSTS[Math.floor(Math.random()*ALL_POSTS.length)]}}
function toggleSection(el){{el.classList.toggle('collapsed');el.nextElementSibling.classList.toggle('collapsed')}}
window.addEventListener('scroll',function(){{const b=document.querySelector('.scroll-top');if(b)b.classList.toggle('visible',window.scrollY>400)}});
const searchInput=document.getElementById('search');
const cards=document.querySelectorAll('.card');
const filterLinks=document.querySelectorAll('.filter-link');
const resetBtn=document.getElementById('reset-filter');
let activeFilter={{type:null,val:null,year:null}};
function updateView(){{
  const q=searchInput.value.toLowerCase();
  cards.forEach(c=>{{
    let show=true;
    if(q){{const t=(c.querySelector('.card-artist')?.textContent||'')+' '+(c.querySelector('.card-title')?.textContent||'');if(!t.toLowerCase().includes(q))show=false}}
    if(show&&activeFilter.type){{
      if(activeFilter.type==='artist'&&c.dataset.artist!==activeFilter.val)show=false;
      if(activeFilter.type==='museum'&&c.dataset.museum!==activeFilter.val)show=false;
      if(activeFilter.type==='material'&&c.dataset.material!==activeFilter.val)show=false;
      if(activeFilter.type==='technique'){{if(!c.dataset.techniques.includes(activeFilter.val))show=false}}
      if(activeFilter.type==='year'&&c.dataset.year!==activeFilter.val)show=false;
      if(activeFilter.type==='month'&&(c.dataset.year!==activeFilter.year||c.dataset.month!==activeFilter.val))show=false;
    }}
    c.style.display=show?'':'none';
  }});
  filterLinks.forEach(link=>{{
    let isActive=false;
    if(activeFilter.type===link.dataset.type){{
      if(activeFilter.type==='month')isActive=(link.dataset.val===activeFilter.val&&link.dataset.year===activeFilter.year);
      else isActive=(link.dataset.val===activeFilter.val);
    }}
    link.classList.toggle('active',isActive);
  }});
  resetBtn.style.display=activeFilter.type?'block':'none';
}}
searchInput.addEventListener('input',updateView);
filterLinks.forEach(link=>{{link.addEventListener('click',e=>{{e.preventDefault();activeFilter.type=link.dataset.type;activeFilter.val=link.dataset.val;if(activeFilter.type==='month')activeFilter.year=link.dataset.year;updateView()}})}});
resetBtn.addEventListener('click',e=>{{e.preventDefault();activeFilter={{type:null,val:null,year:null}};searchInput.value='';updateView()}});
document.querySelectorAll('.sidebar-title').forEach((t,i)=>{{if(i>0){{t.classList.add('collapsed');t.nextElementSibling.classList.add('collapsed')}}}});
</script></body></html>"""

# ---------- TELEGRAM ----------

async def fetch_new_posts(client, processed_ids):
    logger.info("Сканирую канал (ищу новые альбомы)...")
    accepted = []
    stats = {"total": 0, "no_kartina_tag": 0, "no_main_msg": 0,
             "already_seen": 0, "parse_failed": 0}
    samples_failed = []

    def _process_group(group):
        stats["total"] += 1
        group.reverse()
        full_text = ""
        main_msg = None
        for m in group:
            text = m.raw_text or ""
            if text:
                full_text += text + "\n"
            if "#картина" in text.lower():
                main_msg = m
        if not main_msg:
            stats["no_main_msg"] += 1
            return
        if "#картина@oldpictureart" not in full_text.lower():
            stats["no_kartina_tag"] += 1
            return
        if main_msg.id in processed_ids:
            stats["already_seen"] += 1
            return
        try:
            parsed = parse_post(full_text)
            if not parsed:
                stats["parse_failed"] += 1
                samples_failed.append(full_text[:500])
                return
            accepted.append((main_msg, group, parsed))
        except Exception as e:
            stats["parse_failed"] += 1
            logger.error(f"Ошибка парсинга поста {main_msg.id}: {e}")
            samples_failed.append(full_text[:500])

    min_id = max(processed_ids) if processed_ids else 0
    current_album_id = None
    current_group = []

    async for message in client.iter_messages(CHANNEL_URL, min_id=min_id):
        if message.grouped_id:
            if current_album_id == message.grouped_id:
                current_group.append(message)
            else:
                if current_group:
                    _process_group(current_group)
                current_album_id = message.grouped_id
                current_group = [message]
        else:
            if current_group:
                _process_group(current_group)
                current_group = []
                current_album_id = None
            _process_group([message])

    if current_group:
        _process_group(current_group)

    logger.info(f"Найдено новых постов: {len(accepted)}")
    logger.info(f"Статистика: всего={stats['total']}, обработано={stats['already_seen']}, "
                f"не картина={stats['no_main_msg'] + stats['no_kartina_tag']}, "
                f"ошибки парсера={stats['parse_failed']}")

    if samples_failed:
        with open("rejected_posts.txt", "w", encoding="utf-8") as f:
            f.write(f"# Отбракованные посты — {datetime.now():%Y-%m-%d %H:%M}\n\n")
            for i, s in enumerate(samples_failed, 1):
                f.write(f"--- #{i} ---\n{s}\n\n")
        logger.info(f"Подробности в rejected_posts.txt ({len(samples_failed)} шт.)")

    return accepted[::-1]


# ---------- ГЕНЕРАЦИЯ СТРАНИЦ ТЕГОВ ----------

def generate_tag_pages(all_posts):
    logger.info("Генерация страниц тегов...")
    tags_posts = defaultdict(list)
    for post in all_posts:
        for tag in post.get("tags", []):
            tags_posts[tag].append(post)
    count = 0
    for tag, posts in tags_posts.items():
        tag_html = render_tag_page(tag, posts)
        filepath = os.path.join(OUTPUT_DIR, f"tag-{tag}.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(tag_html)
        count += 1
    logger.info(f"Сгенерировано {count} страниц тегов")
    return tags_posts


# ---------- SITEMAP ----------

def generate_sitemap(all_posts):
    logger.info("Генерация sitemap.xml...")
    base_url = "https://denchest.github.io/Site-Oldpictureart"
    urls = [f"  <url><loc>{base_url}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for post in all_posts:
        urls.append(
            f"  <url><loc>{base_url}/{post['filename']}</loc>"
            f"<lastmod>{post['date']}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>"
        )
    all_tags = set()
    for post in all_posts:
        for tag in post.get("tags", []):
            all_tags.add(tag)
    for tag in all_tags:
        urls.append(
            f"  <url><loc>{base_url}/tag-{tag}.html</loc>"
            f"<changefreq>weekly</changefreq><priority>0.5</priority></url>"
        )
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "\n".join(urls)
    sitemap += '\n</urlset>'
    with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)
    logger.info(f"Sitemap сгенерирован ({len(urls)} URL)")


# ---------- MANIFEST ----------

def generate_manifest():
    manifest = {
        "name": "Old Picture Art",
        "short_name": "OldPictureArt",
        "description": "Галерея картин из Telegram канала Old Picture Art",
        "start_url": "/Site-Oldpictureart/",
        "display": "standalone",
        "background_color": "#fafafa",
        "theme_color": "#fafafa",
        "icons": [
            {"src": "images/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "images/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info("manifest.json сгенерирован")


# ---------- GITHUB ----------

def push_to_github():
    logger.info("Отправка на GitHub...")
    try:
        subprocess.run(["git", "add", "."], check=False)
        status = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True)
        if not status.stdout.strip():
            logger.info("Нет изменений для отправки")
            return
        subprocess.run(["git", "commit", "-m",
                        f"Авто-обновление: {datetime.now():%Y-%m-%d %H:%M}"], check=False)
        subprocess.run(["git", "push"], check=False)
        logger.info("Отправлено на GitHub")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")


# ---------- MAIN ----------

def rebuild_reset():
    logger.warning("Режим --rebuild: удаление старых html-страниц и истории обработки.")
    print("   Папка docs/images/ НЕ трогается — уже скачанные картинки сохранятся.")
    answer = input("   Продолжить? [y/N]: ").strip().lower()
    if answer not in ("y", "yes", "д", "да"):
        print("   Отмена.")
        sys.exit(0)
    if os.path.isdir(OUTPUT_DIR):
        removed = 0
        for name in os.listdir(OUTPUT_DIR):
            if name.endswith(".html") or name.endswith(".xml"):
                os.remove(os.path.join(OUTPUT_DIR, name))
                removed += 1
        logger.info(f"Удалено html/xml файлов: {removed}")
    for fn in (PROCESSED_FILE, META_FILE):
        if os.path.exists(fn):
            os.remove(fn)
            logger.info(f"Удалён {fn}")


async def main():
    rebuild = "--rebuild" in sys.argv
    if rebuild:
        rebuild_reset()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    nojekyll = os.path.join(OUTPUT_DIR, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()

    if not PIL_AVAILABLE:
        logger.warning("Pillow не установлен — крупные оригиналы не будут автоматически сжиматься.")

    processed_ids = set(load_json(PROCESSED_FILE, []))
    all_posts = load_json(META_FILE, [])

    logger.info("Подключение к Telegram как пользователь...")
    
    client = await connect_with_proxy(API_ID, API_HASH, PHONE, PROXY_LIST)

    try:
        accepted = await fetch_new_posts(client, processed_ids)
    except Exception as e:
        logger.error(f"Ошибка при сканировании канала: {e}")
        await client.disconnect()
        return

    for i, (main_msg, group, parsed) in enumerate(accepted, 1):
        date = main_msg.date.strftime("%Y-%m-%d")
        artist_slug = slugify(parsed["artist"])

        base = f"{date}-{artist_slug}"
        filename = f"{base}.html"
        n = 2
        existing = {p["filename"] for p in all_posts}
        while filename in existing or os.path.exists(os.path.join(OUTPUT_DIR, filename)):
            filename = f"{base}-{n}.html"
            n += 1

        logger.info(f"[{i}/{len(accepted)}] {parsed['artist'][:40]} — {parsed['title'][:50]}")

        comments = []
        if getattr(main_msg, "replies", None) and main_msg.replies.replies > 0:
            try:
                async for reply in client.iter_messages(CHANNEL_URL, reply_to=main_msg.id):
                    if getattr(reply, "document", None) and reply.document.mime_type.startswith("image/"):
                        comments.append(reply)
            except Exception as e:
                logger.warning(f"Не удалось проверить комментарии: {e}")

        image_slug = filename[:-5]
        images, hires, thumbs = await download_images(client, group, comments, image_slug)

        post = {"id": main_msg.id, "date": date, "filename": filename,
                "images": images, "hires": hires, "thumbs": thumbs, **parsed}

        with open(os.path.join(OUTPUT_DIR, filename), "w", encoding="utf-8") as f:
            f.write(render_post_page(post))

        all_posts.append(post)
        processed_ids.update(m.id for m in group)

    await client.disconnect()
    logger.info("Отключено от Telegram")

    if PIL_AVAILABLE:
        missing = [p for p in all_posts if not p.get("thumbs") and p.get("images")]
        if missing:
            logger.info(f"Создание миниатюр для {len(missing)} существующих постов...")
            for p in missing:
                slug = p["filename"][:-5]
                thumbs = []
                for i, img_rel in enumerate(p["images"], 1):
                    img_abs = os.path.join(OUTPUT_DIR, img_rel)
                    thumb = make_thumbnail(img_abs, slug, i)
                    if thumb:
                        thumbs.append(thumb)
                p["thumbs"] = thumbs
            logger.info("Миниатюры готовы")

    save_json(META_FILE, all_posts)
    save_json(PROCESSED_FILE, sorted(processed_ids))

    generate_tag_pages(all_posts)
    generate_sitemap(all_posts)
    generate_manifest()

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(all_posts))

    with open(os.path.join(OUTPUT_DIR, "404.html"), "w", encoding="utf-8") as f:
        f.write("""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url=index.html"><title>Перенаправление...</title></head><body></body></html>""")

    logger.info(f"Новых постов: {len(accepted)}. Всего на сайте: {len(all_posts)}")
    push_to_github()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Прервано пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)