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

auto_update_modules()

from telethon import TelegramClient
import TelethonFakeTLS

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

def load_dotenv(path=".env"):
    if not os.path.exists(path): return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

load_dotenv()

try:
    API_ID = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"]
    PHONE = os.environ["PHONE"]
except KeyError:
    raise SystemExit("❌ Нужен .env с API_ID, API_HASH, PHONE")

logger.info(f"Аккаунт: {PHONE}")

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
            # Находим позицию материала и вставляем запятую после него
            idx = text.lower().find(mat)
            end_idx = idx + len(mat)
            # Если после материала нет запятой, добавляем
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

PROVENANCE_MARKERS = ["до ","с 1","с 2","поступил","поступла","собрание","коллекци","приобрет","продан","продаж","галере","бывш","передан","находил","хранил","наследств","bequest","acquired","purchased","donated","gift of","private"]

def looks_like_provenance(s):
    return len(re.findall(r"\b1[5-9]\d{2}\b|\b20\d{2}\b", s)) >= 2 and any(m in s.lower() for m in PROVENANCE_MARKERS)

def parse_post(text):
    if not text: return {}
    try:
        urls = []
        def _grab(m):
            urls.append(m.group(0))
            return " "
        tc = URL_RE.sub(_grab, text)
        raw_tags = TAG_RE.findall(tc)
        tc = TAG_RE.sub("", tc)
        parts = [p.strip() for p in SEPARATOR_RE.split(tc) if p.strip()]
        if len(parts) < 4: return {}
        artist = re.sub(r"\s+"," ",parts[0]) if parts[0] else ""
        title = re.sub(r"\s+"," ",parts[1]) if parts[1] else ""
        medium = re.sub(r"\s+"," ",parts[2]) if parts[2] else ""
        museum = re.sub(r"\s+"," ",parts[3]) if parts[3] else ""
        if not artist or not title: return {}
        extras = parts[4:]
        hist, desc = [], ""
        if len(extras) == 1:
            if looks_like_provenance(extras[0]): hist = [l.strip() for l in extras[0].split("\n") if l.strip()]
            else: desc = re.sub(r"\s*\n\s*"," ",extras[0]).strip()
        elif len(extras) >= 2:
            if looks_like_provenance(extras[0]):
                hist = [l.strip() for l in extras[0].split("\n") if l.strip()]
                desc = "\n\n".join(re.sub(r"\s*\n\s*"," ",e).strip() for e in extras[1:])
            else: desc = "\n\n".join(re.sub(r"\s*\n\s*"," ",e).strip() for e in extras)
        md = parse_medium_details(medium)
        return {"artist":artist,"title":title,"medium":medium,"material":md["material"],"techniques":md["techniques"],"size":md["size"],"museum":museum,"history":hist,"description":desc,"urls":urls,"tags":sorted(set(raw_tags)),"raw":text}
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return {}

def slugify(text):
    t = text.lower()
    t = re.sub(r"[^\w\s-]","",t,flags=re.UNICODE)
    t = re.sub(r"\s+","-",t).strip("-")
    return t[:60] or "post"

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

def render_post_page(post):
    artist, title, museum = h(post["artist"]), h(post["title"]), h(post["museum"])
    desc = post.get("description") or ""
    urls = post.get("urls") or ([post["url"]] if post.get("url") else [])

    parts = []
    hl = post.get("hires", [])
    for i, src in enumerate(post["images"]):
        lh = hl[i] if i < len(hl) else src
        parts.append(f'<a href="{h(lh)}" target="_blank" title="Оригинал"><img src="{h(src)}" alt="{artist} — {title}" class="painting" loading="lazy"></a>')
    img_html = "\n".join(parts)

    mat = f'<span class="material">📄 {h(post.get("material",""))}</span>' if post.get("material") else ""
    tech = f'<span class="techniques">🖌 {h(", ".join(post.get("techniques",[])))}</span>' if post.get("techniques") else ""
    sz = f'<span class="size">📏 {h(post.get("size",""))}</span>' if post.get("size") else ""
    mdet = f'<div class="medium-details">{mat} {tech} {sz}</div>'

    tags_html = ""
    if post["tags"]:
        tags_html = '<div class="tags">' + " ".join(f'<a href="tag-{h(t)}.html" class="tag">#{h(t)}</a>' for t in post["tags"]) + "</div>"

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
    if urls:
        if len(urls) == 1:
            u = urls[0]
            src_html = f'<p class="source">Источник: <a href="{h(u)}" target="_blank" rel="noopener">{h(u)}</a></p>'
        else:
            its = "".join(f'<li><a href="{h(u)}" target="_blank" rel="noopener">{h(u)}</a></li>' for u in urls)
            src_html = f'<div class="sources"><strong>Источники:</strong><ul class="source-list">{its}</ul></div>'

    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a2e" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>{artist} — {title}</title>
<link rel="stylesheet" href="style.css">
</head><body class="post-page">
<button class="theme-toggle" onclick="toggleTheme()">🌓</button>
<button class="scroll-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="Наверх">↑</button>
<div class="top-nav"><a href="index.html" class="back">← На главную</a><a href="#" class="random-btn" onclick="goRandom()">🎲 Случайная</a></div>
<article><h1>{artist}</h1><h2>{title}</h2>{img_html}{mdet}<p class="museum">🏛 {museum}</p>{desc_html}{hist_html}{src_html}<time>{h(post['date'])}</time>{tags_html}</article>
<script>function toggleTheme(){{const h=document.documentElement;const c=h.getAttribute('data-theme');const n=c==='light'?'dark':'light';h.setAttribute('data-theme',n);localStorage.setItem('theme',n)}}
(()=>{{const s=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',s)}})();
function goRandom(){{const p=JSON.parse(localStorage.getItem('allPosts')||'[]');if(p.length)location.href=p[Math.floor(Math.random()*p.length)]}}
window.addEventListener('scroll',function(){{const b=document.querySelector('.scroll-top');if(b)b.classList.toggle('visible',window.scrollY>400)}});</script></body></html>"""

def surname_key(n):
    f = n.split(",")[0].strip()
    w = f.split()
    return w[-1].lower() if w else n.lower()

def render_tag_page(tag, posts):
    cards = []
    for p in sorted(posts, key=lambda x: x["date"], reverse=True):
        cv = ""
        if p.get("thumbs"): cv = p["thumbs"][0]
        elif p.get("images"): cv = p["images"][0]
        cv = h(cv)
        cards.append(f'<a class="card" href="{h(p["filename"])}"><div class="card-img"><img src="{cv}" alt="" loading="lazy"></div><div class="card-body"><div class="card-artist">{h(p["artist"])}</div><div class="card-title">{h(p["title"])}</div></div></a>')
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a2e" media="(prefers-color-scheme: dark)">
<title>#{h(tag)} — Old Picture Art</title>
<link rel="stylesheet" href="style.css">
</head><body class="tag-page">
<button class="theme-toggle" onclick="toggleTheme()">🌓</button>
<button class="scroll-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="Наверх">↑</button>
<a href="index.html" class="back">← На главную</a>
<h1>#{h(tag)} ({len(posts)})</h1>
<div class="grid">{''.join(cards)}</div>
<script>function toggleTheme(){{const h=document.documentElement;const c=h.getAttribute('data-theme');const n=c==='light'?'dark':'light';h.setAttribute('data-theme',n);localStorage.setItem('theme',n)}}
(()=>{{const s=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',s)}})();
window.addEventListener('scroll',function(){{const b=document.querySelector('.scroll-top');if(b)b.classList.toggle('visible',window.scrollY>400)}});</script></body></html>"""

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
    for p in ps:
        if p.get("date") and "-" in p["date"]:
            y, m, _ = p["date"].split("-")
            archive[y].add(m)
    ars = {y: sorted(list(m), reverse=True) for y, m in sorted(archive.items(), reverse=True)}
    cards = []
    for p in ps:
        cv = ""
        if p.get("thumbs"): cv = p["thumbs"][0]
        elif p.get("images"): cv = p["images"][0]
        cv = h(cv)
        y, m = "", ""
        if p.get("date") and "-" in p["date"]: y, m, _ = p["date"].split("-")
        cards.append(f"""<a class="card" href="{h(p['filename'])}" data-artist="{h(p['artist'].lower())}" data-year="{y}" data-month="{m}" data-museum="{h(slugify(p.get('museum','')))}" data-material="{h(slugify(p.get('material','')))}" data-techniques="{h(' '.join(slugify(t) for t in p.get('techniques',[])))}"><div class="card-img"><img src="{cv}" alt="" loading="lazy"></div><div class="card-body"><div class="card-artist">{h(p['artist'])}</div><div class="card-title">{h(p['title'])}</div><div class="card-museum">{h(p.get('museum',''))}</div><div class="card-info">{h(p.get('material',''))} {h(', '.join(p.get('techniques',[])[:2]))}</div></div></a>""")
    
    # Подсчёт количества
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
    arh = ""
    for y, ms_list in ars.items():
        arh += f'<li><a href="#" class="filter-link" data-type="year" data-val="{y}"><b>{y} год</b></a><ul class="month-list">'
        for mn in ms_list: arh += f'<li><a href="#" class="filter-link" data-type="month" data-year="{y}" data-val="{mn}">{MONTHS.get(mn,mn)}</a></li>'
        arh += '</ul></li>'
    af = json.dumps([p["filename"] for p in ps])
    
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a2e" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Old Picture Art — Галерея</title>
<link rel="stylesheet" href="style.css">
</head><body class="index-page">
<button class="theme-toggle" onclick="toggleTheme()">🌓 Тема</button>
<button class="scroll-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="Наверх">↑</button>
<header><h1>🎨 Old Picture Art</h1><div class="subtitle">Картин в коллекции: <strong>{len(ps)}</strong></div><a href="#" class="random-btn" onclick="goRandom()">🎲 Случайная картина</a><input type="text" class="search-box" placeholder="🔍 Поиск по художнику, картине, музею, технике…" id="search"></header>
<div class="layout"><aside class="sidebar">
<a href="#" id="reset-filter" class="filter-reset">✕ Сбросить все фильтры</a>
<div class="sidebar-section"><div class="sidebar-title" onclick="toggleSection(this)">📅 Архив</div><div class="sidebar-content"><ul>{arh}</ul></div></div>
<div class="sidebar-section"><div class="sidebar-title" onclick="toggleSection(this)">👨‍🎨 Художники</div><div class="sidebar-content"><ul>{ah}</ul></div></div>
<div class="sidebar-section"><div class="sidebar-title" onclick="toggleSection(this)">🏛 Музеи</div><div class="sidebar-content"><ul>{mh}</ul></div></div>
<div class="sidebar-section"><div class="sidebar-title" onclick="toggleSection(this)">📄 Материал</div><div class="sidebar-content collapsed"><ul>{mth}</ul></div></div>
<div class="sidebar-section"><div class="sidebar-title" onclick="toggleSection(this)">🖌 Техника</div><div class="sidebar-content collapsed"><ul>{th}</ul></div></div>
</aside><main class="main-content"><div class="grid" id="cards">{''.join(cards)}</div></main></div>
<script>
const ALL_POSTS = {af};

function toggleTheme() {{
    const h = document.documentElement;
    const c = h.getAttribute('data-theme');
    const n = c === 'light' ? 'dark' : 'light';
    h.setAttribute('data-theme', n);
    localStorage.setItem('theme', n);
}}

(() => {{
    const s = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', s);
    localStorage.setItem('allPosts', JSON.stringify(ALL_POSTS));
}})();

function goRandom() {{
    if(ALL_POSTS.length) location.href = ALL_POSTS[Math.floor(Math.random() * ALL_POSTS.length)];
}}

function toggleSection(el) {{
    el.classList.toggle('collapsed');
    el.nextElementSibling.classList.toggle('collapsed');
}}

window.addEventListener('scroll', function() {{
    const b = document.querySelector('.scroll-top');
    if(b) b.classList.toggle('visible', window.scrollY > 400);
}});

const si = document.getElementById('search');
const cards = document.querySelectorAll('.card');
const fl = document.querySelectorAll('.filter-link');
const rb = document.getElementById('reset-filter');
let afilt = {{ type: null, val: null, year: null }};

function updateView() {{
    const q = si.value.toLowerCase();
    cards.forEach(c => {{
        let s = true;
        if(q) {{
            const artist = (c.querySelector('.card-artist')?.textContent || '').toLowerCase();
            const title = (c.querySelector('.card-title')?.textContent || '').toLowerCase();
            const museum = (c.querySelector('.card-museum')?.textContent || '').toLowerCase();
            const info = (c.querySelector('.card-info')?.textContent || '').toLowerCase();
            const all = artist + ' ' + title + ' ' + museum + ' ' + info;
            if(!all.includes(q)) s = false;
        }}
        if(s && afilt.type) {{
            if(afilt.type === 'artist' && c.dataset.artist !== afilt.val) s = false;
            if(afilt.type === 'museum' && c.dataset.museum !== afilt.val) s = false;
            if(afilt.type === 'material' && c.dataset.material !== afilt.val) s = false;
            if(afilt.type === 'technique') {{ if(!c.dataset.techniques.includes(afilt.val)) s = false; }}
            if(afilt.type === 'year' && c.dataset.year !== afilt.val) s = false;
            if(afilt.type === 'month' && (c.dataset.year !== afilt.year || c.dataset.month !== afilt.val)) s = false;
        }}
        c.style.display = s ? '' : 'none';
    }});

    fl.forEach(l => {{
        let isActive = false;
        if(afilt.type === l.dataset.type) {{
            if(afilt.type === 'month') isActive = (l.dataset.val === afilt.val && l.dataset.year === afilt.year);
            else isActive = (l.dataset.val === afilt.val);
        }}
        l.classList.toggle('active', isActive);
    }});
    rb.style.display = afilt.type ? 'block' : 'none';
}}

si.addEventListener('input', updateView);

fl.forEach(l => {{
    l.addEventListener('click', e => {{
        e.preventDefault();
        afilt.type = l.dataset.type;
        afilt.val = l.dataset.val;
        if(afilt.type === 'month') afilt.year = l.dataset.year;
        updateView();
    }});
}});

rb.addEventListener('click', e => {{
    e.preventDefault();
    afilt = {{ type: null, val: null, year: null }};
    si.value = '';
    updateView();
}});

document.querySelectorAll('.sidebar-title').forEach((t) => {{
    t.classList.add('collapsed');
    t.nextElementSibling.classList.add('collapsed');
}});
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
    c = 0
    for tag, posts in tp.items():
        with open(os.path.join(OUTPUT_DIR, f"tag-{tag}.html"), "w", encoding="utf-8") as f:
            f.write(render_tag_page(tag, posts))
        c += 1
    logger.info(f"Сгенерировано {c} страниц тегов")
    return tp

def generate_sitemap(all_posts):
    logger.info("Sitemap...")
    bu = "https://denchest.github.io/Site-Oldpictureart"
    urls = [f"  <url><loc>{bu}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for p in all_posts: urls.append(f"  <url><loc>{bu}/{p['filename']}</loc><lastmod>{p['date']}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>")
    at = set()
    for p in all_posts:
        for t in p.get("tags",[]): at.add(t)
    for t in at: urls.append(f"  <url><loc>{bu}/tag-{t}.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + '\n</urlset>')
    logger.info(f"Sitemap ({len(urls)} URL)")

def generate_manifest():
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"name":"Old Picture Art","short_name":"OldPictureArt","description":"Галерея картин","start_url":"/Site-Oldpictureart/","display":"standalone","background_color":"#fafafa","theme_color":"#fafafa","icons":[{"src":"images/icon-192.png","sizes":"192x192","type":"image/png"},{"src":"images/icon-512.png","sizes":"512x512","type":"image/png"}]}, f, ensure_ascii=False, indent=2)
    logger.info("manifest.json")

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
            if n.endswith(".html") or n.endswith(".xml"): os.remove(os.path.join(OUTPUT_DIR, n))
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
    client = await connect_with_proxy(API_ID, API_HASH, PHONE, PROXY_LIST)
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
        with open(os.path.join(OUTPUT_DIR, fn), "w", encoding="utf-8") as f: f.write(render_post_page(post))
        all_posts.append(post)
        processed_ids.update(m.id for m in group)
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
    save_json(META_FILE, all_posts)
    save_json(PROCESSED_FILE, sorted(processed_ids))
    generate_tag_pages(all_posts)
    generate_sitemap(all_posts)
    generate_manifest()
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f: f.write(render_index(all_posts))
    with open(os.path.join(OUTPUT_DIR, "404.html"), "w", encoding="utf-8") as f: f.write('<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="0;url=index.html"></head><body></body></html>')
    logger.info(f"Новых постов: {len(accepted)}. Всего: {len(all_posts)}")
    push_to_github()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: logger.info("Прервано")
    except Exception as e: logger.error(f"Критическая ошибка: {e}", exc_info=True)