import asyncio
import os
import re
import sys
import json
import shutil
import subprocess
import logging
import logging.handlers
import random
from datetime import datetime, timezone
from email.utils import format_datetime
import difflib
import unicodedata
import urllib.parse
from urllib.parse import quote
import functools
from collections import defaultdict, Counter
from html import escape as h
from pathlib import Path

# Журнал сборки. Пишется с обрезкой по размеру: прежде это был обычный
# FileHandler, который дописывает в конец и никогда не укорачивается —
# за полгода parser.log дорос до мегабайта и продолжал бы расти. Теперь
# файл обрезается на 2 МБ, а две прошлые сборки остаются в parser.log.1
# и parser.log.2 — этого хватает, чтобы посмотреть, что было в прошлый
# раз, и не хватает, чтобы захламить папку.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.handlers.RotatingFileHandler('parser.log', maxBytes=2_000_000,
                                                   backupCount=2, encoding='utf-8'),
              logging.StreamHandler()])
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

from site_common import (head_common, scroll_top_button, theme_button, site_footer,
                         mark_svg, TELEGRAM_URL, TELEGRAM_NAME, SITE_DOMAIN, hires_url,
                         COMMON_JS, SCROLL_TOP_JS, LUPA_JS, TOAST_JS, SHARE_JS, AUTH_JS, CLOUD_JS, BASE_URL,
                         VISITS_FILE, has_visits, visit_places,
                         METRIKA_ID, SITE_OWNER, PRIVACY_CONTACT, PRIVACY_CONTACT_TEXT, PRIVACY_DATE,
                         work_year, AUTH_API_URL, YANDEX_CLIENT_ID, VK_CLIENT_ID)

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

# Копия для просмотра в лупе. Оригиналы бывают по пять тысяч пикселей и
# по нескольку мегабайт: на мобильном интернете такая картинка едет полминуты,
# а разглядеть на телефоне больше двух тысяч всё равно нельзя. Кнопка
# «Скачать картину» по-прежнему отдаёт оригинал как есть.
VIEW_DIR = "docs/images/views"
VIEW_DIMENSION = 2000
VIEW_QUALITY = 82

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
    with open(DICTIONARY_FILE, "w", encoding="utf-8", newline="\n") as f:
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
        
        # Год создания — из даты в конце названия (см. work_year)
        creation_year = work_year(title) if title else None
        
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


# ======================================================================
#                        АДРЕСА СТРАНИЦ
# ======================================================================
#
# Имена страниц были кириллические: 2025-11-07-фрэнсис-кэмпбелл-буало-каделл.html.
# В адресной строке браузер показывает их по-человечески, но стоит ссылку
# скопировать — и она превращается в
# %D1%84%D1%80%D1%8D%D0%BD%D1%81%D0%B8%D1%81-… длиной 341 знак. Именно в
# таком виде ссылка уходит в переписку, в канал и в чужие письма.
#
# Второе: в имени стояла дата публикации в канале и имя художника. Дата
# посетителю ничего не говорит — его интересует не когда вы это выложили,
# а что на картине. Название работы в адресе не упоминалось вовсе.
#
# Стало: <фамилия>-<название>-<год>. Фамилия западных художников берётся
# из тегов самого канала (#renoir, #sisley) — там она уже записана так,
# как её пишут в мире. Обратная транслитерация с русской транскрипции
# дала бы «renuar» и «pussen», по которым художника не узнать.

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text):
    """Кириллица и буквы с надстрочными знаками — в простую латиницу.

    Надстрочные знаки снимаются разложением: é → e, ä → a. Иначе
    французские и немецкие названия снова уехали бы в проценты.
    """
    out = []
    for ch in unicodedata.normalize("NFKD", text or "").lower():
        if unicodedata.combining(ch):
            continue
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isascii() and ch.isalnum():
            out.append(ch)
        elif ch.isalnum():
            out.append(unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode())
        else:
            out.append("-")
    return re.sub(r"-+", "-", "".join(out)).strip("-")


def looks_latin(text):
    """Записано ли слово латиницей — с поправкой на надстрочные знаки.

    rusiñol и café написаны латиницей: ñ и é раскладываются на обычную
    букву плюс знак. А вот «сonstable» из тегов канала только выглядит
    латинским — первая буква там русская «с», это опечатка. Буквальная
    транслитерация превратила бы её в «sonstable» и увековечила описку
    в адресе страницы.
    """
    bare = "".join(c for c in unicodedata.normalize("NFKD", text or "")
                   if not unicodedata.combining(c))
    return bool(bare) and bare.isascii()


def latin_slug(text, limit=60):
    """Кусок адреса: только латиница, цифры и дефис."""
    return translit(text)[:limit].strip("-")


def surname_of(artist):
    """Фамилия из имени художника: последнее слово до скобки или запятой."""
    a = re.sub(r"\(.*?\)", "", artist or "").split(",")[0].strip()
    words = [w for w in a.split() if len(w) > 1]
    return words[-1] if words else a


# Заполняется один раз за сборку в prepare_slugs(): имена страниц
# художников нужны в десятке мест, и таскать словарь через все вызовы
# было бы хуже, чем держать его здесь.
_ARTIST_LATIN = {}


def fix_work_years(all_posts):
    """Пересчитывает год создания у уже скачанных записей. Возвращает,
    сколько записей поправлено.

    Год раньше брался как первое четырёхзначное число в названии, и у
    работ, в названии которых есть дата события, годом становилось само
    событие: «Парад на Красной площади 7 ноября 1941 года, 1949» стоял в
    таймлайне и статистике в 1941-м. Разбор поправлен, а записи, скачанные
    до этого, чинятся здесь — без похода в Telegram. Вместе с годом
    меняется и адрес страницы (год — его последняя часть); прежний адрес
    остаётся перенаправлением.
    """
    fixed = 0
    for post in all_posts:
        year = work_year(post.get("title"))
        if year != post.get("creation_year"):
            logger.info(f"Год создания: {post.get('creation_year')} → {year} — {post.get('title', '')[:70]}")
            post["creation_year"] = year
            fixed += 1
    return fixed


def prepare_slugs(all_posts):
    """Считает латинские имена художников. Вызывать до генерации страниц."""
    _ARTIST_LATIN.clear()
    _ARTIST_LATIN.update(artist_latin_map(all_posts))
    return _ARTIST_LATIN


def tag_slug(tag):
    """Имя страницы тега.

    Тег, записанный обычной латиницей, остаётся ровно таким, как есть —
    вместе с заглавными буквами. Приводить его к нижнему регистру было
    ошибкой: #vonAlt и #Mulot_Durivage превращались в tag-vonalt.html,
    и на Windows это тот же самый файл, что и прежний tag-vonAlt.html.
    Сборка писала страницу и перенаправление в один файл, из репозитория
    уезжало что-то одно, а GitHub Pages, где регистр различается, отдавал
    на другое имя «страница не найдена».

    Плюс к тому это лишний переезд: адреса 82 тегов и без того были
    нормальными, менять их было незачем.

    Переводятся только те, где латиницы недостаточно: русские теги и
    те, где затесались ñ, ü, é — в ссылке они всё равно превращаются
    в проценты.
    """
    tag = (tag or "").strip()
    if tag and tag.isascii() and re.fullmatch(r"[A-Za-z0-9._~-]+", tag):
        return tag
    return latin_slug(tag, 48) or "tag"


def artist_latin_map(all_posts):
    """Художник → фамилия латиницей.

    Сначала ищем в тегах поста латинское слово: канал помечает работы
    настоящей фамилией автора (#caillebotte, #friedrich), и это куда
    лучше, чем переложить обратно русскую транскрипцию. Для русских
    художников латинского тега нет — там транслитерация и уместна.

    Однофамильцев разводим отчеством или именем, иначе две разные
    страницы претендовали бы на один адрес.
    """
    chosen = {}
    for p in all_posts:
        artist = (p.get("artist") or "").strip()
        if not artist or artist in chosen:
            continue
        # Теги идут по алфавиту, и брать первый латинский нельзя: у
        # работы из Прадо тег музея окажется раньше фамилии, и в адрес
        # уедет «prado-ploschad-parizha». Поэтому тег не берётся, а
        # опознаётся: он должен быть похож на фамилию художника, как
        # caillebotte похож на «кайботт», а poussin — на «пуссен».
        ru_surname = latin_slug(surname_of(artist), 40)
        ru_full = latin_slug(artist, 60)
        # Теги приводим к латинице до сравнения, а не отбираем заранее
        # «только латинские»: в канале попадаются rusiñol с испанской
        # буквой и сonstable, у которого первая буква русская «с». По
        # виду они латинские, по кодам — нет, и такой отбор их терял.
        best, score = "", 0.0
        for t in p.get("tags", []):
            t = t.strip()
            if not t or t == "картина" or t.isdigit() or not looks_latin(t):
                continue
            cand = latin_slug(t, 40)
            if not cand:
                continue
            near = max(difflib.SequenceMatcher(None, cand, ru_surname).ratio(),
                       difflib.SequenceMatcher(None, cand, ru_full).ratio())
            if near > score:
                best, score = cand, near

        # Запятая в имени означает, что авторов несколько: «Анонимные
        # художники, Феликс Огюстен Милиус, Александр-Огюст Розе, …».
        # Фамилии у такой записи нет — разбор выдаёт «hudozhniki», — и
        # выбирать из нескольких авторов одного было бы неправдой.
        # Такие страницы называются по самой работе, без автора.
        if "," in (artist or ""):
            chosen[artist] = best if score >= 0.6 else ""
        else:
            chosen[artist] = (best if score >= 0.45 else "") or ru_surname or "author"

    taken = {}
    for artist in sorted(chosen):
        base = chosen[artist]
        if base not in taken:
            taken[base] = artist
            continue
        extra = latin_slug(" ".join((artist or "").split()[:-1]), 18)
        name, n = (f"{base}-{extra}" if extra else base), 2
        while name in taken:
            name = f"{base}-{n}"
            n += 1
        taken[name] = artist
        chosen[artist] = name
    return chosen


def work_title_slug(title):
    """Название работы для адреса.

    В базе название хранится как в канале: «Les Fiancés (Пара), около
    1868» — сначала на языке оригинала, в скобках по-русски, в конце год.
    Для адреса берём русскую часть (сайт русский), а год отрезаем: он
    станет отдельным куском имени и дважды в адресе не нужен.
    """
    t = title or ""
    m = re.search(r"\(([^)]*[А-Яа-яЁё][^)]*)\)", t)
    if m:
        t = m.group(1)
    t = re.sub(r",?\s*(около\s*|ок\.\s*|до\s*|после\s*)?\d{3,4}\s*(?:[–—-]\s*\d{2,4})?\s*$", "", t)
    return latin_slug(t, 48)


def post_slug(post, artists):
    """Имя страницы работы: фамилия-название-год."""
    parts = []
    author = artists.get((post.get("artist") or "").strip())
    if author:
        parts.append(author)
    title = work_title_slug(post.get("title"))
    if title:
        parts.append(title)
    if not parts:
        parts.append("kartina")
    year = post.get("creation_year")
    if year:
        parts.append(str(year))
    return "-".join(parts)


def rename_pages(all_posts, visits=None):
    """Переводит имена страниц на латиницу. Возвращает True, если что-то
    изменилось.

    Прежнее имя не выбрасывается, а копится в old_filenames: по нему
    потом кладётся страница-перенаправление. Ссылку на картину могли
    уже отправить в переписке, и превращать её в «страница не найдена»
    нельзя. Список именно список: если имя поменяется ещё раз, обе
    прежние ссылки должны продолжать работать.

    Вызывать можно сколько угодно раз: если имя уже правильное, функция
    ничего не трогает.
    """
    artists = artist_latin_map(all_posts)
    taken = set()
    changed = False

    for post in all_posts:
        base = post_slug(post, artists)
        name, n = f"{base}.html", 2
        while name in taken:
            name = f"{base}-{n}.html"
            n += 1
        taken.add(name)
        old = post.get("filename")
        if old and old != name:
            history = post.setdefault("old_filenames", [])
            if old not in history:
                history.append(old)
            changed = True
        if old != name:
            post["filename"] = name
            changed = True

    for visit in (visits or []):
        base = "visit-" + "-".join(x for x in (
            visit.get("date", ""), latin_slug(visit_heading(visit), 48)) if x)
        name, n = f"{base}.html", 2
        while name in taken:
            name = f"{base}-{n}.html"
            n += 1
        taken.add(name)
        old = visit.get("filename")
        if old and old != name:
            history = visit.setdefault("old_filenames", [])
            if old not in history:
                history.append(old)
            changed = True
        if old != name:
            visit["filename"] = name
            changed = True

    return changed




def legacy_post_names(all_posts):
    """Прежние имена страниц работ, восстановленные по самим записям.

    Зачем восстанавливать, а не читать из old_filenames: история имён
    появляется в базе только в тот прогон, который переименовывает. Если
    переименование уже прошло, а база до перенаправлений не дожила —
    сборкой с чужой машины, откатом файла, чем угодно, — то 88 адресов,
    которые люди могли отправить друг другу, молча превращаются в
    «страница не найдена», и восстановить их будет уже неоткуда.

    Имя считалось как <дата поста>-<имя художника>, а повторы в тот же
    день получали -2, -3. Правило простое и обратимое, поэтому прежний
    адрес выводится из даты и художника — так же, как у страниц тегов
    и художников он выводится из тега и имени.
    """
    seen, out = {}, {}
    for post in all_posts:
        base = f"{post.get('date', '')}-{slugify(post.get('artist', ''))}"
        seen[base] = seen.get(base, 0) + 1
        n = seen[base]
        out[f"{base}.html" if n == 1 else f"{base}-{n}.html"] = post.get("filename")
    return out


def write_redirect(old_name, new_name):
    """Кладёт на прежний адрес страницу-перенаправление.

    Без noindex, хотя он тут просится. Google считает мгновенный
    meta refresh обычным постоянным переездом, и страница-перенаправление
    в указатель не попадает сама по себе. А вот noindex рядом с canonical
    — это два противоречащих указания на одной странице: «этой страницы в
    поиске быть не должно» и «настоящая страница вот эта, перенеси на неё
    всё накопленное». Разбирая противоречие, поисковик может отнести
    запрет к той самой странице, на которую мы переносим. В отчёте Google
    такие адреса и всплыли — в разделе «запрещено тегом noindex».
    """
    target = urllib.parse.quote(new_name)
    with open(os.path.join(OUTPUT_DIR, old_name), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"""<!DOCTYPE html><html lang="ru"><head>
<meta charset="UTF-8">
<link rel="canonical" href="{BASE_URL}/{target}">
<meta http-equiv="refresh" content="0; url={target}">
<title>Страница переехала</title>
</head><body>
<p>Страница переехала: <a href="{target}">{h(new_name)}</a></p>
<script>location.replace({json.dumps(target)});</script>
</body></html>""")


def retire_pages(prefix, live, legacy):
    """Прибирает страницы с приставкой prefix, которых больше нет.

    legacy — {прежнее имя: нынешнее}. Перенаправление по таким адресам
    кладётся всегда, а не только если прежний файл ещё лежит в папке:
    иначе сборка с нуля — и все прежние ссылки разом превращаются в
    «страница не найдена». Имена тегов и художников считаются из данных,
    так что прежний адрес известен и без файла на диске.

    Всё прочее с этой приставкой — след исчезнувшего тега или ушедшего
    художника, такое убирается совсем.
    """
    live_ci = {n.lower() for n in live}
    moved = removed = 0
    for old_name, new_name in legacy.items():
        # Различие только в регистре — не переезд. На Windows это один и
        # тот же файл, и перенаправление затёрло бы саму страницу.
        if (old_name in live or new_name not in live
                or old_name.lower() in live_ci):
            continue
        write_redirect(old_name, new_name)
        moved += 1
    keep = live_ci | {n.lower() for n in legacy}
    for name in os.listdir(OUTPUT_DIR):
        if name.startswith(prefix) and name.endswith(".html") and name.lower() not in keep:
            os.remove(os.path.join(OUTPUT_DIR, name))
            removed += 1
    return moved, removed


def generate_redirects(all_posts, visits=None):
    """Страницы-перенаправления на прежних адресах.

    GitHub Pages раздаёт файлы и ничего не умеет перенаправлять на своей
    стороне, поэтому перенаправление приходится класть страницей. В ней
    три способа сразу: canonical — чтобы поисковик понял, какой адрес
    настоящий, и перенёс на него всё, что успел накопить; meta refresh —
    чтобы сработало без скриптов; и строчка на javascript, которая
    уводит мгновенно и, в отличие от meta refresh, не засоряет кнопку
    «назад».
    """
    live = {r.get("filename") for r in list(all_posts) + list(visits or [])}
    moves = dict(legacy_post_names(all_posts))
    for rec in list(all_posts) + list(visits or []):
        for old in rec.get("old_filenames", []):
            moves[old] = rec.get("filename")

    made = 0
    for old, new in moves.items():
        if (not old or not new or old == new or "/" in old
                or not old.endswith(".html") or old in live):
            continue
        write_redirect(old, new)
        made += 1
    if made:
        logger.info(f"Перенаправлений со старых адресов: {made}")
    return made


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
    with open(path, "w", encoding="utf-8", newline="\n") as f: json.dump(data, f, ensure_ascii=False, indent=2)

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

# ---------------------------------------------------------- карточка ссылки
#
# Когда ссылку на картину кидают в мессенджер, превью берёт og:image. Раньше
# это была сама картина — красиво, но безымянно: кто автор и что это, видно
# только если открыть. Карточка добавляет к картине подпись, набранную теми же
# цветами, что и сайт.
CARD_DIR = "docs/images/cards"
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
            v = make_view(os.path.join(OUTPUT_DIR, hr), slug, i)
            views.append(v)
            if v:
                made += 1
        rec["views"] = views
    if made:
        logger.info(f"Копий для просмотра создано: {made}")
    return made


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

async def download_images(client, group, comments, slug, start=0):
    """start — сколько снимков у записи уже есть. Добавки к походу качаются
    отдельным заходом, и без сдвига они перезаписали бы первые файлы."""
    images, hires, thumbs = [], [], []
    idx = start
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
    for i, msg in enumerate(docs, start + 1):
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
            for i, hr in enumerate(hires, start + 1):
                t = make_thumbnail(os.path.join(OUTPUT_DIR, hr), slug, i)
                if t: thumbs.append(t)
    return images, hires, thumbs

# ===================== HTML-ФУНКЦИИ =====================

def tidy(fn):
    """Убирает пробелы в конце строк готовой страницы.

    В шаблонах есть необязательные куски — описание, происхождение,
    «рядом в собрании». Когда такой кусок пуст, от строки остаётся один
    отступ: валидатор считает это ошибкой, а в исходнике страницы это
    выглядит как мусор. Декоратор снимает вопрос на всех страницах сразу.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        html = fn(*args, **kwargs)
        return "\n".join(line.rstrip() for line in html.split("\n"))
    return wrapper


SIZES_FILE = "image_sizes.json"
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


def site_og_image(all_posts):
    """Картинка для превью ссылки на сайт.

    Когда ссылку на главную кидают в мессенджер, превью брала только
    страница работы: у главной, указателя и статистики og:image не было
    вовсе, и ссылка выглядела голым текстом. Берём самую свежую работу —
    превью само обновляется вместе с собранием.
    """
    for post in sorted(all_posts, key=lambda x: x.get("date", ""), reverse=True):
        if post.get("images"):
            return f"{BASE_URL}/{post['images'][0]}"
    return ""


def russian_title(title):
    """Русская часть названия работы, если она есть в скобках.

    Названия хранятся как «Lisière de la forêt de Fontainebleau (Опушка
    леса Фонтенбло), 1865»: сначала оригинал, потом перевод, потом год.
    В заголовке вкладки и в выдаче поисковика полезен перевод — по нему
    и ищут. Скобки бывают вложенными («Бухта на острове Сент-Томас
    (Антильские острова)»), поэтому разбираем их счётчиком, а не regexp.
    """
    best = ""
    depth = 0
    start = -1
    for i, ch in enumerate(title):
        if ch == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                inner = title[start:i]
                if any("а" <= c.lower() <= "я" or c.lower() == "ё" for c in inner):
                    if len(inner) > len(best):
                        best = inner
    return best.strip()


def short_artist(artist, limit=40):
    """Длинный список авторов сворачиваем до первого имени."""
    artist = (artist or "").strip()
    if len(artist) <= limit or "," not in artist:
        return artist
    return artist.split(",")[0].strip() + " и другие"


def page_title(post, limit=70):
    """Заголовок вкладки и выдачи поисковика.

    Полное «художник — название» доходило до 339 знаков и обрезалось
    в выдаче на полуслове у 46 страниц из 81. Берём русское название,
    год и фамилию автора — то, что человек и набирает в поиске.
    """
    title = (post.get("title") or "").strip()
    ru = russian_title(title)
    if ru:
        # год в исходном названии стоит после скобок, вернём его к переводу
        tail = title.rsplit(")", 1)[-1].strip(" ,")
        name = f"{ru}, {tail}" if tail and tail not in ru else ru
    else:
        name = title

    artist = short_artist(post.get("artist", ""))
    full = f"{name} — {artist}" if artist else name
    if len(full) <= limit:
        return full
    room = limit - len(artist) - 3
    if room > 20:
        return f"{name[:room].rsplit(' ', 1)[0]}… — {artist}"
    return full[:limit - 1].rsplit(" ", 1)[0] + "…"


def artwork_jsonld(post):
    """Разметка Schema.org для страницы работы.

    Для каталога живописи есть готовый тип VisualArtwork: он описывает
    автора, год, материал, технику, размер и собрание так, как это
    понимают поисковики. Без него страница для них — просто текст.
    """
    def text(x):
        """Строка, которую нельзя принять за ссылку.

        В словаре Schema.org у artMedium, artworkSurface и unitCode
        допустимы и текст, и URL, поэтому разборщик по умолчанию читает
        значение как адрес: «масло» превращается в ссылку на
        oldpictureart.ru/масло, а «CMT» — в ссылку на oldpictureart.ru/CMT.
        Обёртка {"@value": …} говорит, что это именно текст.
        """
        return {"@value": x}

    data = {
        "@context": "https://schema.org",
        "@type": "VisualArtwork",
        "name": post.get("title", ""),
        "url": f"{BASE_URL}/{post.get('filename', '')}",
        "inLanguage": "ru",
    }
    if post.get("artist"):
        data["creator"] = {"@type": "Person", "name": post["artist"]}
    if post.get("creation_year"):
        data["dateCreated"] = str(post["creation_year"])
    if post.get("techniques"):
        data["artMedium"] = text(", ".join(post["techniques"]))
    if post.get("material"):
        data["artworkSurface"] = text(lower_first(post["material"]))
    if post.get("images"):
        data["image"] = f"{BASE_URL}/{post['images'][0]}"
    if post.get("museum"):
        data["isPartOf"] = {"@type": "Collection", "name": post["museum"]}
    if post.get("description"):
        data["description"] = post["description"][:500]
    if post.get("urls"):
        data["sameAs"] = post["urls"][:3]

    # «105 x 75 см» → высота и ширина отдельными величинами
    m = re.match(r"\s*([\d.,]+)\s*[xх×]\s*([\d.,]+)", post.get("size") or "")
    if m:
        def cm(v):
            return {"@type": "QuantitativeValue", "value": float(v.replace(",", ".")),
                    "unitCode": text("CMT"), "unitText": text("см")}
        data["height"], data["width"] = cm(m.group(1)), cm(m.group(2))

    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


def generate_cname():
    """Файл CNAME — то, по чему GitHub Pages понимает, что у сайта свой домен.

    Пишем его сборкой, а не руками: иначе однажды он потеряется при
    очередной пересборке или переносе, и сайт молча вернётся на github.io
    вместе со всеми ссылками. Если домена нет, ничего не трогаем — в том
    числе не удаляем файл, который мог быть создан через настройки GitHub.
    """
    if not SITE_DOMAIN:
        return
    with open(os.path.join(OUTPUT_DIR, "CNAME"), "w", encoding="utf-8", newline="\n") as f:
        f.write(SITE_DOMAIN + "\n")
    logger.info(f"CNAME → {SITE_DOMAIN}")


def generate_robots():
    """robots.txt со ссылкой на карту сайта.

    Без него поисковик находит sitemap.xml только случайно.
    """
    body = ("User-agent: *\n"
            "Allow: /\n"
            "\n"
            f"Sitemap: {BASE_URL}/sitemap.xml\n")
    with open(os.path.join(OUTPUT_DIR, "robots.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    logger.info("robots.txt")


def download_name(post, src):
    """Осмысленное имя файла для скачивания: «Художник — Название, год.jpg».

    Браузер иначе сохранит его как «2025-11-26-исаак-ильич-левитан-hires-1.jpg» —
    в папке «Загрузки» по такому имени работу потом не найти.
    """
    ext = os.path.splitext(src)[1] or ".jpg"
    parts = [post.get("artist", ""), post.get("title", "")]
    name = " — ".join(x.strip() for x in parts if x and x.strip()) or "painting"
    year = post.get("creation_year")
    if year and str(year) not in name:
        name = f"{name}, {year}"
    # символы, которые файловые системы не принимают
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name[:120] or "painting") + ext


@tidy
def render_post_page(post, all_posts=None):
    artist, title, museum = h(post["artist"]), h(post["title"]), h(post["museum"])
    title_plain = post.get("title") or ""
    desc = post.get("description") or ""
    urls = post.get("urls") or ([post["url"]] if post.get("url") else [])
    cover_image = post['images'][0] if post.get('images') else ''
    post_id = str(post.get("id", ""))

    parts = []
    hl = post.get("hires", [])
    views = post.get("views") or []
    for i, src in enumerate(post["images"]):
        lh = hires_url(hl[i] if i < len(hl) else src)
        # Первая картина — главный элемент страницы (LCP): грузим её сразу,
        # остальные ленимся. Раньше lazy стоял на всех, включая первую.
        loading = 'fetchpriority="high" decoding="async"' if i == 0 else 'loading="lazy" decoding="async"'
        # Ссылка на оригинал остаётся настоящей: без JS она откроет файл, как
        # раньше, а со скриптом клик перехватывает лупа. data-* нужны ей для
        # подписи — лезть за ними в разметку страницы не приходится.
        # Год в подписи лупы повторялся: он и так стоит в конце названия
        # («…, 1832»), а на телефоне подпись и без того длинная.
        year = str(post.get("creation_year") or "")
        meta_bits = [x for x in (("" if year and year in title_plain else year),
                                 post.get("museum") or "") if x]
        # data-view — то, что грузит лупа: копия до 2000 пикселей. Ссылка
        # остаётся на оригинал: и без JS, и по Ctrl+клик, и кнопкой «скачать»
        # человек получает файл таким, каким он пришёл из канала. Адрес копии
        # не переписывается под HIRES_BASE_URL: в хранилище уезжают только
        # оригиналы, всё остальное остаётся рядом с сайтом.
        vw = views[i] if i < len(views) else ""
        parts.append(
            f'<a href="{h(lh)}" class="painting-link" target="_blank" rel="noopener" '
            + (f'data-view="{h(vw)}" ' if vw else '')
            + f'title="Рассмотреть" data-title="{artist} — {title}" data-meta="{h(", ".join(meta_bits))}" '
            f'data-download="{h(download_name(post, lh))}">'
            f'<img src="{h(src)}" alt="{artist} — {title}" class="painting"{size_attrs(src)} {loading}>'
            f'<span class="painting-hint" aria-hidden="true">'
            f'<span class="icon-lupa" aria-hidden="true"></span> Рассмотреть</span></a>'
        )
    img_html = "\n".join(parts)

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
        tags_html = '<div class="tags">' + " ".join(f'<a href="tag-{h(tag_slug(t))}.html" class="tag">#{h(t)}</a>' for t in post["tags"]) + "</div>"
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

    # Скачать работу. Это ссылка, а не кнопка: атрибут download отдаёт файл
    # напрямую, работает без JS и не мешает «сохранить как» из меню правой
    # кнопки. Файлы лежат на том же домене, иначе download браузер игнорирует.
    download_src = hires_url(hl[0] if hl else (post["images"][0] if post.get("images") else ""))
    download_btn = ""
    if download_src:
        download_btn = (f'<a href="{h(download_src)}" download="{h(download_name(post, download_src))}" '
                        f'class="topbar-btn" aria-label="Скачать картину" title="Скачать картину">'
                        f'<span class="icon-download" aria-hidden="true"></span></a>')

    # «Рядом в собрании»: после описания человек упирался в тупик, хотя
    # у того же художника и в том же музее есть что показать.
    similar_block = similar_html(post, all_posts) if all_posts else ""
    artist_link = (f'<a href="{h(artist_slug(post["artist"]))}">{artist}</a>'
                   if post.get("artist") else artist)

    page_desc = (desc[:200] if desc else f"{post.get('artist','')} — {post.get('title','')}. {post.get('museum','')}").strip()
    head = head_common(
        title=h(page_title(post)),
        description=page_desc,
        og_image=f"{BASE_URL}/{post.get('card') or cover_image}" if (post.get('card') or cover_image) else "",
        canonical=f"{BASE_URL}/{post.get('filename','')}",
        og_type="article",
        extra="\n" + artwork_jsonld(post),
    )

    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="post-page">
<a href="#main" class="skip-link">К содержанию</a>
<div class="post-topbar">
  <a href="./" class="topbar-back"><span class="icon-back" aria-hidden="true"></span> Галерея</a>
  <div class="post-topbar-right">
    <button type="button" onclick="goRandom()" class="topbar-btn" aria-label="Случайная картина" title="Случайная картина"><span class="icon-random" aria-hidden="true"></span></button>
    <button type="button" data-share-btn onclick="sharePage(this)" class="topbar-btn" aria-label="Поделиться" title="Поделиться" aria-haspopup="menu"><span class="icon-share" aria-hidden="true"></span></button>
    {download_btn}
    <button type="button" id="like-btn" data-post-id="{post_id}" onclick="toggleLike()" class="topbar-btn topbar-like" aria-pressed="false" aria-label="В избранное" title="В избранное"><span class="icon-heart" aria-hidden="true"></span><span class="like-count" id="like-count" hidden></span></button>
    <button type="button" class="topbar-btn" data-theme-toggle onclick="toggleTheme()" aria-label="Переключить тему" title="Светлая / тёмная тема"><span class="icon-theme-toggle" aria-hidden="true"></span></button>
    <button type="button" id="auth-btn" class="topbar-btn ym-hide-content" title="Войти"><span class="icon-login" aria-hidden="true"></span> Войти</button>
  </div>
</div>
{scroll_top_button()}
<article id="main" class="post-layout">
  <div class="post-main">
    <header class="post-head">
      <h1>{artist_link}</h1>
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
{similar_block}
{post_nav}
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{LUPA_JS}
{TOAST_JS}
{SHARE_JS}
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
    else location.href = './?random=1';
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
    else if (k === 'h' || k === 'р') window.location.href = './';
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
{AUTH_JS}
</body></html>"""

def surname_key(n):
    f = n.split(",")[0].strip()
    w = f.split()
    return w[-1].lower() if w else n.lower()

def card_html(p, cat_no=None, cat_width=3, show_artist=True):
    """Карточка работы в описи. Одна на все списки — главную, теги,
    страницы художников: раньше разметка была скопирована и разъезжалась.

    show_artist=False — для страницы художника: там его имя стоит в
    заголовке и повторять его в каждой строке незачем, поэтому главной
    строкой карточки становится название работы."""
    cat_no = cat_no or {}
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
    head_line = artist_name if show_artist else title_name
    sub_line = f'<div class="card-title">{title_name}</div>' if show_artist else ''
    return (
        f'<article class="card">{no_html}'
        f'<div class="card-img"><img src="{cv}" alt="{artist_name} — {title_name}"{size_attrs(cv)} loading="lazy" decoding="async"></div>'
        f'<div class="card-body">'
        f'<div class="card-artist"><a class="card-link" href="{h(p["filename"])}">{head_line}</a></div>'
        f'{sub_line}{museum_html}</div>'
        f'<div class="card-facts">{facts_html}</div></article>'
    )


@tidy
def render_tag_page(tag, posts, cat_no=None, cat_width=3):
    """cat_no — сквозные каталожные номера всего собрания: на странице тега
    номер должен остаться тем же, что и на главной, иначе он ничего не значит."""
    cards = [card_html(p, cat_no, cat_width)
             for p in sorted(posts, key=lambda x: x["date"], reverse=True)]
    head = head_common(
        title=f"#{h(tag)} — Old Picture Art",
        description=f"Картины по тегу #{tag} — подборка из {len(posts)} работ в галерее Old Picture Art.",
        canonical=f"{BASE_URL}/tag-{tag_slug(tag)}.html",
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<h1>#{h(tag)} <span class="tag-count">({len(posts)})</span></h1>
<div class="grid list">{''.join(cards)}</div>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
</body></html>"""

@tidy
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
    <div class="card-img"><img src="{cv}" alt="{artist_name} — {title_name}"{size_attrs(cv)} loading="lazy" decoding="async"></div>
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
    # Материал в базе записан с заглавной («Холст»), техника — со строчной
    # («масло»). В списке фильтров они стоят рядом, поэтому приводим
    # к одному виду: со строчной, как принято в описании работы.
    mth = "".join(f'<li><a href="#" class="filter-link" data-type="material" data-val="{h(slugify(m))}">{h(lower_first(m))} <span class="count">({material_count[m]})</span></a></li>' for m in materials)
    th = "".join(f'<li><a href="#" class="filter-link" data-type="technique" data-val="{h(slugify(t))}">{h(t)} <span class="count">({technique_count[t]})</span></a></li>' for t in techniques)
    # Годы: строка на десятилетие, полоса показывает, сколько работ. Раньше
    # это были столбики гистограммы шириной в восемнадцать пикселей — пальцем
    # в такой не попасть, а на сенсорных экранах читают чаще, чем мышью.
    # Строки устроены как соседние разделы сайдбара и как страница статистики,
    # так что это не новый элемент, а тот же самый. Поля «от / до» под списком
    # задают точный диапазон, подпись словами говорит, что сейчас выбрано.
    hist_max = max(decades.values()) if decades else 1
    bars = []
    for d in decades_sorted:
        start = int(d.split("–")[0])
        n = decades.get(d, 0)
        pct = round(n / hist_max * 100)
        word = plural_ru(n, "работа", "работы", "работ")
        bars.append(
            f'<li><button type="button" class="dec-row" data-decade="{start}" style="--w:{pct}%" '
            f'aria-pressed="false" title="{h(d)} — {n} {word}" aria-label="{h(d)}, {n} {word}">'
            f'<span class="dec-year">{start}-е</span>'
            f'<span class="dec-track"><span class="dec-fill"></span></span>'
            f'<span class="dec-n">{n}</span></button></li>'
        )
    decade_starts = [int(d.split("–")[0]) for d in decades_sorted]
    opts_from = "".join(f'<option value="{v}">{v}</option>' for v in decade_starts)
    opts_to = "".join(f'<option value="{v + 9}">{v + 9}</option>' for v in decade_starts)
    dech = f'''<div class="year-filter">
      <ul class="dec-list" id="year-hist">{''.join(bars)}</ul>
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
        str(p.get("id", "")): {"file": p["filename"], "title": p.get("title", f"Картина #{p.get('id', '')}"),
                               "artist": p.get("artist", ""),
                               "thumb": (p.get("thumbs") or p.get("images") or [""])[0]}
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
    # «Популярное у посетителей» — рядом с «Избранным»: то же по сути,
    # только отметки чужие. Раздел появляется, когда список пришёл из
    # облака; пока отмеченных картин мало, в сайдбаре ничего не висит.
    popular_html = ('<div class="sidebar-section" id="popular" hidden>'
                    '<button type="button" class="sidebar-title sidebar-icon icon-popular open" '
                    'aria-expanded="true" onclick="toggleSection(this)">Популярное '
                    '<span id="popular-count" class="count"></span></button>'
                    '<div class="sidebar-content"><ul id="popular-list"></ul></div></div>')
    theme_html = ('<div class="sidebar-section"><button type="button" class="sidebar-title sidebar-icon icon-theme no-arrow" '
                  'data-theme-toggle aria-pressed="false" onclick="toggleTheme()">Тема</button></div>')
    quiz_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-quiz no-arrow" '
                      'href="quiz.html">Квиз</a></div>')
    timeline_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-timeline no-arrow" '
                          'href="timeline.html">Таймлайн</a></div>')
    map_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-map no-arrow" '
                     'href="museums.html">Карта собраний</a></div>')
    # Посещения появляются в меню только когда в канале нашлись
    # посты #выставка или #галерея — пустой раздел никому не нужен.
    visits_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-visits no-arrow" '
                        'href="visits.html">Посещения</a></div>') if has_visits() else ''
    index_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-artists no-arrow" '
                       'href="ukazatel.html">Указатель</a></div>')
    stats_link_html = ('<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-decades no-arrow" '
                       'href="stats.html">Статистика</a></div>')
    # Канал — источник всего собрания, поэтому он в том же ряду, что карта
    # и указатель, а не мелкой строкой где-то внизу.
    tg_link_html = (f'<div class="sidebar-section"><a class="sidebar-title sidebar-icon icon-tg no-arrow" '
                    f'href="{TELEGRAM_URL}" target="_blank" rel="noopener">Канал</a></div>')
    
    head = head_common(
        title="Old Picture Art — Галерея",
        og_image=site_og_image(all_posts),
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
<header>
<div class="head-text">
<h1><span class="icon-logo" aria-hidden="true"></span> Old Picture Art</h1>
<p class="site-lede">Собрание живописи из музеев мира. У каждой работы указаны автор, год, материал, размер и место, где она сейчас, а любую картину можно скачать в высоком разрешении. Пополняется из телеграм-канала <a href="{TELEGRAM_URL}" target="_blank" rel="noopener">{TELEGRAM_NAME}</a>.</p>
<div class="subtitle">{len(ps)} {plural_ru(len(ps), 'картина', 'картины', 'картин')} · {len(authors)} {plural_ru(len(authors), 'художник', 'художника', 'художников')} · {len(museums)} {plural_ru(len(museums), 'музей', 'музея', 'музеев')} · {year_range}</div>
</div>
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
{popular_html}
{theme_html}
{map_link_html}
{visits_link_html}
{index_link_html}
{stats_link_html}
{tg_link_html}
{quiz_link_html}
{timeline_link_html}
</aside><main class="main-content">
<div class="results-bar">
  <span id="results-count" class="results-count" role="status" aria-live="polite"></span>
  <div class="bar-controls">
  <span class="bar-label" id="sort-label">Порядок</span>
  <label class="visually-hidden" for="sort">Порядок записей</label>
  <select id="sort" class="sort-select" aria-labelledby="sort-label">
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
{site_footer()}
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
    document.querySelectorAll('.dec-row').forEach(b => {{
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

    // Клик по строке — это десятилетие целиком
    document.querySelectorAll('.dec-row').forEach(bar => {{
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

    // Из указателя сюда ведут ссылки вида index.html#mat-холст. Без разбора
    // якоря такой переход просто открывал главную без всякого фильтра.
    function applyHashFilter() {{
        const raw = (location.hash || '').replace(/^#/, '');
        const cut = raw.indexOf('-');
        if (cut < 1) return;
        const kind = {{mat: 'material', tech: 'technique', artist: 'artist', museum: 'museum'}}[raw.slice(0, cut)];
        if (!kind) return;
        let val = raw.slice(cut + 1);
        try {{ val = decodeURIComponent(val); }} catch (e) {{}}
        const link = [...document.querySelectorAll('.filter-link')]
            .find(l => l.dataset.type === kind && l.dataset.val === val);
        if (!link) return;
        const section = link.closest('.sidebar-section');
        const body = section && section.querySelector('.sidebar-content');
        if (body && body.classList.contains('collapsed')) section.querySelector('.sidebar-title').click();
        link.click();
    }}
    applyHashFilter();
    window.addEventListener('hashchange', applyHashFilter);

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
{CLOUD_JS}
<script>
// Вошедшему в аккаунт — отметки из облака в список «Избранное».
cloudSync().then(function (changed) {{ if (changed) updateFavList(); }});

// «Популярное у посетителей»: самые отмечаемые картины. Функция отдаёт
// только номера картин и числа — кто отмечал, в ответе нет. Блок
// появляется, когда отмеченных картин набралось хотя бы три: полка из
// одной картины выглядела бы случайной.
if (CLOUD.on) cloudCall('top', {{limit: 6}}).then(function (j) {{
  var items = (j.top || []).filter(function (x) {{ return POSTS_DATA[x[0]]; }});
  if (items.length < 3) return;
  var list = document.getElementById('popular-list');
  items.forEach(function (x) {{
    var info = POSTS_DATA[x[0]], n = x[1];
    var li = document.createElement('li');
    var a = document.createElement('a');
    a.href = info.file;
    a.className = 'popular-link';
    a.title = info.artist ? info.artist + ' — ' + info.title : info.title;
    if (info.thumb) {{
      var img = document.createElement('img');
      img.src = info.thumb; img.alt = ''; img.loading = 'lazy'; img.decoding = 'async';
      img.width = 34; img.height = 34;
      a.appendChild(img);
    }}
    var name = document.createElement('span');
    name.className = 'popular-name';
    name.textContent = info.title;
    a.appendChild(name);
    var cnt = document.createElement('span');
    cnt.className = 'popular-count count';
    cnt.innerHTML = '<span class="icon-heart" aria-hidden="true"></span> ';
    cnt.appendChild(document.createTextNode(n));
    var hidden = document.createElement('span');
    hidden.className = 'visually-hidden';
    hidden.textContent = ' — добавили в избранное';
    cnt.appendChild(hidden);
    a.appendChild(cnt);
    li.appendChild(a);
    list.appendChild(li);
  }});
  document.getElementById('popular-count').textContent = '(' + items.length + ')';
  document.getElementById('popular').hidden = false;
}}).catch(function () {{}});
</script></body></html>"""

# ===================== TELEGRAM =====================

async def fetch_new_posts(client, processed_ids, full_scan=False, known_visits=None):
    """Возвращает три пачки: картины, новые посещения и добавки к прежним.

    В канале восемь хештегов, а сайт до сих пор понимал только #картина —
    остальные посты молча уходили в отбраковку. Теперь #выставка и #галерея
    разбираются своим разбором и живут в отдельном разделе; всё прочее
    по-прежнему пропускается.

    Отдельная забота — снимки без подписи. С похода привозят больше фото,
    чем влезает в один пост, и остальные идут следом отдельными записями
    без текста. Такой пост сам по себе ничего не значит, но относится
    к ближайшему посещению того же дня — к нему его и приписываем.
    """
    logger.info("Сканирую канал...")
    accepted, visits, extras_for_known = [], [], {}
    known = {v.get("id"): v for v in (known_visits or []) if v.get("id")}
    stats = {"total":0,"no_kartina_tag":0,"no_main_msg":0,"already_seen":0,
             "parse_failed":0,"visits":0,"extra_groups":0}
    sf = []
    # Канал читается от новых к старым, поэтому безымянные посты со снимками
    # встречаются РАНЬШЕ того посещения, к которому относятся. Копим их и
    # отдаём ближайшему посещению того же дня.
    pending = []

    def _day(msg):
        return msg.date.strftime("%Y-%m-%d")

    def _take_pending(anchor):
        """Забирает накопленные безымянные посты того же дня."""
        day = _day(anchor)
        # Канал читается от новых к старым, поэтому очередь накопилась
        # задом наперёд: разворачиваем, чтобы снимки легли в том порядке,
        # в котором их выложили.
        mine = [g for g in pending if _day(g[0]) == day][::-1]
        pending.clear()
        return mine

    def _pg(group):
        stats["total"] += 1
        group.reverse()
        ft, mm, vm = "", None, None
        for m in group:
            t = m.raw_text or ""
            if t: ft += t + "\n"
            low = t.lower()
            if "#картина" in low: mm = m
            if vm is None and any(f"#{tag}" in low for tag in VISIT_TAGS): vm = m

        # Посещение: пост о выставке или музее, а не о работе из собрания
        if not mm and vm:
            extra = _take_pending(vm)
            if vm.id in processed_ids:
                stats["already_seen"] += 1
                # Само посещение уже разобрано, но снимки к нему могли
                # появиться позже или просто не собирались раньше.
                if extra and vm.id in known:
                    extras_for_known.setdefault(vm.id, []).extend(extra)
                    stats["extra_groups"] += len(extra)
                return
            try:
                v = parse_visit(ft)
            except Exception as e:
                logger.error(f"Ошибка посещения {vm.id}: {e}"); v = {}
            if v:
                stats["visits"] += 1
                stats["extra_groups"] += len(extra)
                visits.append((vm, group, v, extra))
            else:
                stats["parse_failed"] += 1; sf.append(ft[:500])
            return

        if not mm:
            # Пост без подписи и со снимками — вероятная добавка к походу.
            # Оставляем в очереди до ближайшего посещения; любая запись
            # с текстом очередь обрывает: между постами дня она не тянется.
            if not ft.strip() and any(getattr(m, "photo", None) or getattr(m, "document", None) for m in group):
                pending.append(group)
            else:
                pending.clear()
            stats["no_main_msg"] += 1
            return

        pending.clear()
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

    # Обычно смотрим только то, что новее последнего разобранного поста.
    # Но посты #выставка и #галерея лежат в канале давно, а сайт их до сих
    # пор не понимал: при первом запуске с этой возможностью проходим канал
    # целиком, иначе прошлые походы так и останутся ненайденными.
    mid = 0 if full_scan else (max(processed_ids) if processed_ids else 0)
    if full_scan:
        logger.info("Полный проход по каналу: собираю прошлые походы и снимки к ним")
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
    logger.info(f"Новых постов: {len(accepted)}, посещений: {len(visits)}"
                + (f", добавок со снимками: {stats['extra_groups']}" if stats['extra_groups'] else "")
                + f". Всего проверено: {stats['total']}, обработано: {stats['already_seen']}, "
                f"не картина: {stats['no_main_msg']+stats['no_kartina_tag']}, ошибки: {stats['parse_failed']}")
    if sf:
        with open("rejected_posts.txt","w",encoding="utf-8", newline="\n") as f:
            f.write(f"# Отбракованные посты — {datetime.now():%Y-%m-%d %H:%M}\n\n")
            for i, s in enumerate(sf, 1): f.write(f"--- #{i} ---\n{s}\n\n")
        logger.info(f"rejected_posts.txt ({len(sf)} шт.)")
    return accepted[::-1], visits[::-1], extras_for_known


def catalogue_numbers(all_posts):
    """Сквозные номера собрания: по году создания, потом по дате записи.

    Номер обязан быть одним и тем же на главной, на теге и на странице
    художника — иначе он перестаёт что-либо обозначать.
    """
    chrono = sorted(all_posts, key=lambda x: (x.get("creation_year") or 9999, x.get("date", "")))
    return ({x["filename"]: i for i, x in enumerate(chrono, 1)},
            max(3, len(str(len(all_posts)))))


def artist_slug(name):
    """Имя страницы художника.

    Берётся та же фамилия, что и в адресах его работ, — чтобы
    renoir-para-1868.html и artist-renoir.html читались как одно
    семейство, а не как два разных способа записать человека.
    """
    key = _ARTIST_LATIN.get((name or "").strip()) or latin_slug(surname_of(name), 40)
    return "artist-" + (key or "author") + ".html"


def year_span(posts):
    """«1871—1896» или «1896», если год один. Работы без года пропускаем."""
    years = sorted(p["creation_year"] for p in posts if p.get("creation_year"))
    if not years:
        return ""
    return str(years[0]) if years[0] == years[-1] else f"{years[0]}—{years[-1]}"


def similar_works(post, all_posts, limit=6):
    """Похожие работы: сначала тот же художник, затем то же собрание,
    затем то же десятилетие. Считается при сборке, на странице ничего
    не ищется — поэтому блок ничего не стоит посетителю.
    """
    me = post.get("filename")
    picked, seen = [], {me}

    def take(candidates, why):
        for p in candidates:
            if len(picked) >= limit:
                return
            fn = p.get("filename")
            if not fn or fn in seen:
                continue
            seen.add(fn)
            picked.append((p, why))

    by_date = sorted(all_posts, key=lambda x: x.get("date", ""), reverse=True)

    artist = (post.get("artist") or "").strip()
    if artist:
        take([p for p in by_date if (p.get("artist") or "").strip() == artist], "того же художника")

    museum = (post.get("museum") or "").strip()
    if museum and not museum.lower().startswith("частная"):
        take([p for p in by_date if (p.get("museum") or "").strip() == museum], "из того же собрания")

    year = post.get("creation_year")
    if year:
        lo = (int(year) // 10) * 10
        take([p for p in by_date
              if p.get("creation_year") and lo <= int(p["creation_year"]) < lo + 10],
             f"{lo}-х годов")

    return picked


def similar_html(post, all_posts):
    """Блок «Рядом в собрании» в конце страницы картины."""
    items = similar_works(post, all_posts)
    if not items:
        return ""
    cards = []
    for p, why in items:
        cv = ""
        if p.get("thumbs"):
            cv = p["thumbs"][0]
        elif p.get("images"):
            cv = p["images"][0]
        # Когда работа попала в подборку «за десятилетие», год уже назван
        # в самой причине — второй раз его писать незачем.
        year = "" if why.endswith("-х годов") else str(p.get("creation_year") or "")
        cards.append(
            f'<a class="near-card" href="{h(p["filename"])}">'
            f'<span class="near-img"><img src="{h(cv)}" alt="{h(p["artist"])} — {h(p["title"])}"{size_attrs(cv)} '
            f'loading="lazy" decoding="async"></span>'
            f'<span class="near-body">'
            f'<span class="near-artist">{h(p["artist"])}</span>'
            f'<span class="near-title">{h(p["title"])}</span>'
            f'<span class="near-why">{h(why)}{" · " + year if year else ""}</span>'
            f'</span></a>'
        )
    return ('<section class="near"><h3>Рядом в собрании</h3>'
            '<div class="near-grid">' + "".join(cards) + '</div></section>')


@tidy
def render_artist_page(artist, posts, all_posts, cat_no, cat_width):
    """Страница художника: все его работы, годы, собрания.

    Раньше художник был только значением фильтра на главной — такую
    подборку нельзя было послать ссылкой и её не видел поиск.
    """
    works = sorted(posts, key=lambda x: (x.get("creation_year") or 9999, x.get("date", "")))
    cards = [card_html(p, cat_no, cat_width, show_artist=False) for p in works]

    museums = sorted({p["museum"].strip() for p in works if p.get("museum")})
    techs = sorted({t for p in works for t in p.get("techniques", []) if t})
    mats = sorted({p["material"] for p in works if p.get("material")})
    span = year_span(works)

    facts = []
    if span:
        facts.append(("Годы", span))
    facts.append(("Работ", str(len(works))))
    if mats:
        facts.append(("Материал", ", ".join(lower_first(m) for m in mats)))
    if techs:
        facts.append(("Техника", ", ".join(techs)))
    facts_html = "".join(f'<div><span>{h(k)}</span><b>{h(v)}</b></div>' for k, v in facts)

    museum_html = ""
    if museums:
        items = "".join(
            f'<li><a href="museums.html#museum-{h(slugify(m))}">{h(m)}</a></li>' for m in museums)
        museum_html = (f'<div class="aside-block"><h3>Собрания</h3>'
                       f'<ul class="plain-list">{items}</ul></div>')

    # Соседи по алфавиту — по фамилии, как в описи
    names = sorted({p["artist"].strip() for p in all_posts if p.get("artist")}, key=surname_key)
    pos = names.index(artist) if artist in names else -1
    nav = []
    if pos > 0:
        nav.append(f'<a class="prev-post" href="{h(artist_slug(names[pos-1]))}">'
                   f'<span class="icon-prev" aria-hidden="true"></span> {h(names[pos-1])}</a>')
    if 0 <= pos < len(names) - 1:
        nav.append(f'<a class="next-post" href="{h(artist_slug(names[pos+1]))}">'
                   f'{h(names[pos+1])} <span class="icon-next" aria-hidden="true"></span></a>')
    nav_html = f'<nav class="post-nav">{"".join(nav)}</nav>' if nav else ""

    page_title = f"{artist} — Old Picture Art"
    if len(page_title) > 70:
        page_title = artist
    if len(page_title) > 70:
        page_title = page_title[:67].rsplit(" ", 1)[0] + "…"

    word = plural_ru(len(works), "работа", "работы", "работ")
    desc = f"{artist}: {len(works)} {word} в собрании Old Picture Art" + (f", {span}." if span else ".")
    head = head_common(
        # длинные имена не влезают в выдачу поисковика: сначала убираем
        # название сайта, а совсем длинные (у одной записи в авторах
        # перечислено одиннадцать человек) подрезаем по слову.
        title=h(page_title),
        description=desc,
        canonical=f"{BASE_URL}/{artist_slug(artist)}",
        og_image=f"{BASE_URL}/{works[0]['images'][0]}" if works and works[0].get("images") else "",
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page artist-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="ukazatel.html" class="back">Указатель</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head">
  <p class="eyebrow">Художник</p>
  <h1>{h(artist)}</h1>
  <div class="spec-table artist-facts">{facts_html}</div>
</header>
<div class="artist-layout">
  <div class="grid list">{''.join(cards)}</div>
  <aside class="post-aside">{museum_html}</aside>
</div>
{nav_html}
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
</body></html>"""


@tidy
def render_ukazatel(all_posts):
    """Указатель: художники, собрания, материал и техника по алфавиту.

    Всё это было спрятано в раскрывающихся разделах сайдбара — с телефона
    туда не добраться одним взглядом, а для каталога это обязательная часть.
    """
    artists = defaultdict(list)
    museums = defaultdict(list)
    techs = defaultdict(list)
    mats = defaultdict(list)
    for p in all_posts:
        if p.get("artist"):
            artists[p["artist"].strip()].append(p)
        if p.get("museum"):
            museums[p["museum"].strip()].append(p)
        for t in p.get("techniques", []):
            if t and len(t) > 2:
                techs[lower_first(t.strip())].append(p)
        if p.get("material"):
            mats[lower_first(p["material"].strip())].append(p)

    def letter(name):
        ch = (name or "?")[:1].upper()
        return ch if ch.isalpha() else "#"

    def column(title, data, href, key=None, anchor=""):
        """Список с группировкой по первой букве и числом работ."""
        items = sorted(data.items(), key=lambda kv: (key(kv[0]) if key else kv[0].lower()))
        out, cur = [], None
        for name, posts in items:
            first = letter(key(name).upper() if key else name)
            if first != cur:
                cur = first
                out.append(f'<li class="idx-letter" aria-hidden="true">{h(cur)}</li>')
            link = href(name)
            n = len(posts)
            out.append(f'<li><a href="{h(link)}">{h(name)}</a><span class="idx-n">{n}</span></li>')
        return (f'<section class="idx-col" id="{anchor}"><h2>{h(title)} '
                f'<span class="idx-total">{len(items)}</span></h2>'
                f'<ul class="idx-list">{"".join(out)}</ul></section>')

    body = "".join([
        column("Художники", artists, artist_slug, key=surname_key, anchor="hudozhniki"),
        column("Собрания", museums, lambda m: f"museums.html#museum-{slugify(m)}", anchor="sobraniya"),
        column("Материал", mats, lambda m: f"./#mat-{slugify(m)}", anchor="material"),
        column("Техника", techs, lambda t: f"./#tech-{slugify(t)}", anchor="tehnika"),
    ])

    head = head_common(
        title="Указатель — Old Picture Art",
        og_image=site_og_image(all_posts),
        description=(f"Художники, собрания и техники коллекции Old Picture Art "
                     f"по алфавиту: {len(artists)} художников, {len(museums)} собраний."),
        canonical=f"{BASE_URL}/ukazatel.html",
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page index-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="stats.html" class="back">Статистика</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head">
  <p class="eyebrow">Собрание</p>
  <h1>Указатель</h1>
  <p class="idx-lede">Всё, что есть в каталоге, по алфавиту и с числом работ.</p>
</header>
<div class="idx-grid">{body}</div>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
</body></html>"""


def _bar_rows(pairs, total, href=None, unit=("работа", "работы", "работ")):
    """Строки «название — полоса — число».

    Число всегда написано словами рядом с полосой, поэтому таблица читается
    и без цвета, и в распечатке, и скринридером — полоса лишь помогает
    сравнить на глаз.
    """
    top = max((n for _, n in pairs), default=1) or 1
    out = []
    for name, n in pairs:
        w = round(n / top * 100, 1)
        label = h(name)
        if href:
            link = href(name)
            label = f'<a href="{h(link)}">{label}</a>'
        share = f"{n} {plural_ru(n, *unit)}" + (f", {round(n / total * 100)}%" if total else "")
        out.append(
            f'<li class="stat-row">'
            f'<span class="stat-name">{label}</span>'
            f'<span class="stat-track"><span class="stat-fill" style="--w:{w}%"></span></span>'
            f'<span class="stat-n" title="{h(share)}">{n}</span>'
            f'</li>'
        )
    return "".join(out)


def _bar_block(title, pairs, total, note="", href=None, anchor=""):
    if not pairs:
        return ""
    return (f'<section class="stat-block" id="{anchor}">'
            f'<h2>{h(title)}</h2>'
            f'<ol class="stat-list">{_bar_rows(pairs, total, href)}</ol>'
            + (f'<p class="stat-note">{h(note)}</p>' if note else "")
            + '</section>')


@tidy
def render_stats(all_posts):
    """Статистика собрания: чем оно на самом деле является.

    Одна мера — число работ — по разным разрезам, поэтому везде один цвет
    и никаких легенд: цвет ничего не кодирует, он просто рисует длину.
    """
    ps = list(all_posts)
    total = len(ps)

    artists = Counter(p["artist"].strip() for p in ps if p.get("artist"))
    museums = Counter(p["museum"].strip() for p in ps if p.get("museum"))
    cities = Counter(p["museum"].rsplit(",", 1)[-1].split("(")[0].strip()
                     for p in ps if p.get("museum") and "," in p["museum"])
    techs = Counter(lower_first(t.strip()) for p in ps for t in p.get("techniques", []) if t and len(t) > 2)
    mats = Counter(lower_first(p["material"].strip()) for p in ps if p.get("material"))

    years = sorted(int(p["creation_year"]) for p in ps if p.get("creation_year"))
    decades = Counter((y // 10) * 10 for y in years)

    # ---- столбцы по десятилетиям ----
    bars = ""
    if decades:
        lo, hi = min(decades), max(decades)
        peak = max(decades.values())
        cols = []
        for d in range(lo, hi + 10, 10):
            n = decades.get(d, 0)
            hpct = round(n / peak * 100, 1)
            # подписываем каждые полвека и обязательно края
            show = (d % 50 == 0) or d == lo or d == hi
            cols.append(
                f'<div class="dec-col" title="{d}-е: {n} {h(plural_ru(n, "работа", "работы", "работ"))}">'
                f'<span class="dec-bar" style="--hgt:{hpct}%"></span>'
                f'<span class="dec-cap{"" if show else " dec-cap-hidden"}">{d}</span>'
                f'</div>'
            )
        no_year = total - len(years)
        note = f"Самая ранняя работа — {years[0]} год, самая поздняя — {years[-1]}."
        if no_year:
            note += f" У {no_year} {plural_ru(no_year, 'работы', 'работ', 'работ')} год не указан."
        bars = (f'<section class="stat-block" id="desyatiletiya"><h2>По десятилетиям</h2>'
                f'<div class="dec-chart" role="img" aria-label="Распределение работ по десятилетиям, '
                f'от {lo}-х до {hi}-х годов">{"".join(cols)}</div>'
                f'<p class="stat-note">{h(note)}</p></section>')

    def many(counter, least=2):
        return [(k, v) for k, v in counter.most_common() if v >= least]

    def tail(counter, least=2, word=("художник", "художника", "художников")):
        rest = sum(1 for v in counter.values() if v < least)
        if not rest:
            return ""
        return f"И ещё {rest} {plural_ru(rest, *word)} — по одной работе."

    span = f"{years[0]}—{years[-1]}" if years else "—"
    tiles = [
        (str(total), plural_ru(total, "работа", "работы", "работ")),
        (str(len(artists)), plural_ru(len(artists), "художник", "художника", "художников")),
        (str(len(museums)), plural_ru(len(museums), "собрание", "собрания", "собраний")),
        (str(len(cities)), plural_ru(len(cities), "город", "города", "городов")),
        (span, "годы создания"),
    ]
    tiles_html = "".join(f'<div class="stat-tile"><b>{h(v)}</b><span>{h(k)}</span></div>' for v, k in tiles)

    blocks = [
        bars,
        _bar_block("Художники", many(artists), total,
                   tail(artists, 2, ("художник", "художника", "художников")),
                   href=artist_slug, anchor="hudozhniki"),
        _bar_block("Собрания", many(museums), total,
                   tail(museums, 2, ("собрание", "собрания", "собраний")),
                   href=lambda m: f"museums.html#museum-{slugify(m)}", anchor="sobraniya"),
        _bar_block("Города", many(cities), total,
                   tail(cities, 2, ("город", "города", "городов")), anchor="goroda"),
        _bar_block("Материал", mats.most_common(), total, anchor="material"),
        _bar_block("Техника", techs.most_common(), total, anchor="tehnika"),
    ]

    head = head_common(
        title="Статистика собрания — Old Picture Art",
        og_image=site_og_image(ps),
        description=(f"Чем собрано Old Picture Art: {total} работ, {len(artists)} художников, "
                     f"{len(museums)} собраний, {span}."),
        canonical=f"{BASE_URL}/stats.html",
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page stats-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="ukazatel.html" class="back">Указатель</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head">
  <p class="eyebrow">Собрание</p>
  <h1>Статистика</h1>
  <div class="stat-tiles">{tiles_html}</div>
</header>
{''.join(b for b in blocks if b)}
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
</body></html>"""


# ===================== ПОСЕЩЕНИЯ (#выставка, #галерея) =====================

# Дата посещения и срок работы выставки. Разделителем диапазона в канале
# бывает и дефис, и тире, поэтому принимаем любой.
VISIT_DATE_RE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")
VISIT_RANGE_RE = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–—]\s*(\d{1,2}\.\d{1,2}\.\d{4})")
VISIT_TAIL_DATE_RE = re.compile(r"[,;\s]*(\d{1,2}\.\d{1,2}\.\d{4})\s*$")
# Пустые скобки остаются там, где стоял срок работы или ссылка: срок мы
# из текста вынимаем, а «Выставка "Арктика. Полюс цвета" ( )» — не заголовок.
EMPTY_BRACKETS_RE = re.compile(r"[(\[{]\s*[)\]}]")
# Слово «Выставка» перед названием повторяет то, что и так написано
# в шапке страницы и в строке вида, поэтому в заголовке оно лишнее.
VISIT_PREFIX_RE = re.compile(r"^(?:выставка|экспозиция)\b[\s:—-]*", re.I)
VISIT_TAGS = {"выставка": "выставка", "галерея": "музей"}


def visit_date(text):
    """«6.10.2024» → «06.10.2024». В канале день и месяц пишут и с нулём,
    и без; без выравнивания даты не сортируются и выглядят вразнобой."""
    m = VISIT_DATE_RE.search(text or "")
    if not m:
        return ""
    d, mo, y = m.group(0).split(".")
    return f"{int(d):02d}.{int(mo):02d}.{y}"


def clean_visit_line(line):
    """Одна строка поста: без лишних пробелов, пустых скобок и хвостовых
    запятых. Пустые скобки — след вынутого срока работы."""
    line = EMPTY_BRACKETS_RE.sub(" ", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip(" ,;·—-\t")


def strip_quotes(text):
    """Название в кавычках оставляем без них: кавычки нужны в посте, где
    название стоит рядом со словом «Выставка», а в заголовке — уже нет."""
    text = text.strip()
    pairs = (('"', '"'), ('«', '»'), ('“', '”'), ("'", "'"))
    for a, b in pairs:
        if len(text) > 2 and text.startswith(a) and text.endswith(b):
            return text[1:-1].strip()
    return text


def parse_visit(text):
    """Разбирает пост о посещении: #выставка или #галерея.

    Это не картины, а отчёты о походах, и структура у них своя:

        Выставка "Арктика. Полюс цвета"      ← название
        (12.12.2025 - 21.06.2026)            ← сколько работала

        Корпус на Кадашёвской набережной, 17.01.2026   ← где и когда был

        #гтг@oldpictureart
        #выставка@oldpictureart

    У #галерея названия нет — первой строкой идёт сам музей, дальше дата.
    Разбор нарочно терпимый: части ищутся сначала по разделителю ⸻, потом
    по пустым строкам, потом по обычным переносам, потому что в канале
    встречается и так, и так. Даты узнаются по виду — и отдельной строкой,
    и хвостом после запятой; что осталось, это название и место.
    """
    if not text:
        return {}
    low = text.lower()
    kind = ""
    for tag, name in VISIT_TAGS.items():
        if f"#{tag}" in low:
            kind = name
            break
    if not kind:
        return {}

    urls = URL_RE.findall(text)
    # Теги музеев (#гмии, #гтг) пригодятся ссылками на подборки, а теги
    # самого раздела в них не нужны — они и так видны по виду записи.
    tags = sorted({t for t in TAG_RE.findall(text) if t.lower() not in VISIT_TAGS})
    body = TAG_RE.sub("", URL_RE.sub(" ", text))

    run = ""
    m = VISIT_RANGE_RE.search(body)
    if m:
        run = f"{visit_date(m.group(1))} — {visit_date(m.group(2))}"
        # Заменяем пробелом, а не переносом: срок работы стоит в скобках,
        # и от переноса скобки разъезжались по разным строкам — по одной
        # пустую пару уже не узнать, и в заголовке оставалось «( )».
        body = body[:m.start()] + " " + body[m.end():]

    parts = []
    for split in (SEPARATOR_RE.split,
                  lambda s: re.split(r"\n\s*\n", s),
                  lambda s: s.split("\n")):
        parts = [p.strip() for p in split(body) if p.strip()]
        if len(parts) > 1:
            break

    # Дату вынимаем построчно: она бывает и отдельной строкой, и хвостом
    # после места («Музей русского импрессионизма, 04.11.2023»). Без этого
    # она приклеивалась к названию музея и не попадала в сведения.
    visited, keep = "", []
    for part in parts:
        lines = []
        for line in part.split("\n"):
            line = clean_visit_line(line)
            if not line:
                continue
            if VISIT_DATE_RE.fullmatch(line):
                visited = visited or visit_date(line)
                continue
            tail = VISIT_TAIL_DATE_RE.search(line)
            if tail:
                visited = visited or visit_date(tail.group(1))
                line = clean_visit_line(line[:tail.start()])
                if not line:
                    continue
            lines.append(line)
        if lines:
            keep.append(" ".join(lines))

    if not keep:
        return {}

    if kind == "выставка":
        title = strip_quotes(VISIT_PREFIX_RE.sub("", keep[0]))
        place = keep[1] if len(keep) > 1 else ""
        note = " · ".join(keep[2:])
    else:
        # У похода в музей главное — сам музей, а он в посте бывает и второй
        # строкой: «Зал "Французские пастели" (402)» и под ним «Эрмитаж,
        # Главный штаб». Название музея длиннее и идёт последним, зал —
        # уточнение, поэтому местом считаем последнюю строку.
        title = ""
        place = keep[-1]
        note = " · ".join(keep[:-1])

    return {"kind": kind, "title": title, "place": place, "note": note,
            "run": run, "visited": visited, "urls": urls, "tags": tags, "raw": text}


def refresh_visits(visits):
    """Перечитывает сохранённые посещения тем разбором, что сейчас в коде.

    Текст поста лежит в базе целиком, поэтому чинить разбор можно не ходя
    в Telegram: скачанные снимки остаются на месте, обновляются только
    разобранные поля и имя файла страницы.
    """
    changed = 0
    for v in visits:
        raw = v.get("raw")
        if not raw:
            continue
        fresh = parse_visit(raw)
        if not fresh:
            continue
        if any(v.get(k) != val for k, val in fresh.items()):
            changed += 1
        v.update(fresh)
        # Имя считается заново из заголовка, поэтому прежнее надо
        # запомнить здесь: до rename_pages дело дойдёт, когда имя уже
        # будет новым, и перенаправлять станет не с чего.
        name = visit_filename(v)
        if v.get("filename") and v["filename"] != name:
            v.setdefault("old_filenames", []).append(v["filename"])
        v["filename"] = name
    if changed:
        logger.info(f"Посещения перечитаны заново: обновлено {changed}")
    return visits


def visit_filename(visit):
    """Имя страницы похода. Дата записи впереди, чтобы соседние походы
    в одно место не сливались в одно имя.

    Латиницей — по той же причине, что и остальные адреса. Важно, что
    здесь тот же расчёт, что и в rename_pages: refresh_visits зовётся
    при каждой пересборке и переписывает имя заново, и разойдись эти
    два места — страница переезжала бы туда-сюда каждую сборку."""
    return f"visit-{visit.get('date', '')}-{latin_slug(visit_heading(visit), 48)}.html"


def visit_heading(v):
    """Чем подписан поход: названием выставки или названием музея."""
    return (v.get("title") or v.get("place") or "Посещение").strip()


def visit_sort_key(v):
    """По дате посещения, а не по дате записи: сходил в мае, написал
    в июне. Дата в посте записана по-человечески (19.06.2026), поэтому
    для сравнения переворачиваем её в год-месяц-день."""
    d = (v.get("visited") or "").split(".")
    ymd = f"{d[2]}-{d[1]:0>2}-{d[0]:0>2}" if len(d) == 3 else ""
    return (ymd, v.get("date", ""), v.get("filename", ""))


def visit_map_names(visits, all_posts):
    """{место из поста: название карточки на карте}.

    Считается ровно тем же способом, что и на карте, иначе ссылка со
    страницы похода вела бы в никуда: якорь собирается из этого названия.
    """
    names = sorted({p["museum"].strip() for p in (all_posts or []) if p.get("museum")})
    return visit_places(visits or [], names)


def visit_stats(visits):
    shows = sum(1 for v in visits if v.get("kind") == "выставка")
    return shows, len(visits) - shows


@tidy
def render_visits_page(visits, all_posts=None):
    """Список посещений с переключателем «все / выставки / музеи».

    Один список вместо двух разделов: походы идут одной хронологией,
    а переключатель устроен так же, как раскладки на главной, — тем же
    классом кнопок и с тем же запоминанием выбора.
    """
    items = sorted(visits, key=visit_sort_key, reverse=True)
    shows, museums = visit_stats(items)

    cards = []
    for v in items:
        cover = (v.get("thumbs") or v.get("images") or [""])[0]
        heading = visit_heading(v)
        shots = len(v.get("images") or [])
        # Классы у строк сведений нужны плиткам: там подписи прячутся,
        # и без них «17.01.2026 · 12.12.2025 — 21.06.2026 · 7» не прочесть.
        facts = [("f-when", "Побывал", v.get("visited", "")),
                 ("f-run", "Работала", v.get("run", "")),
                 ("f-shots", "Снимков", str(shots) if shots else "")]
        facts_html = "".join(f'<div class="{cls}"><span>{h(k)}</span><b>{h(val)}</b></div>'
                             for cls, k, val in facts if val)
        img = (f'<div class="card-img"><img src="{h(cover)}" alt="{h(heading)}"{size_attrs(cover)}'
               f' loading="lazy" decoding="async"></div>') if cover else '<div class="card-img"></div>'
        sub = v.get("place") if v.get("title") else v.get("note", "")
        sub_html = f'<div class="card-title">{h(sub)}</div>' if sub else ''
        # Вид похода стоит там же, где у картины собрание, — строкой под
        # названием. В колонке номера ему не место: на телефоне она шириной
        # в два знака, и слово «выставка» наезжало на снимок.
        cards.append(
            f'<article class="card visit-card" data-kind="{h(v["kind"])}">'
            f'{img}'
            f'<div class="card-body">'
            f'<div class="card-artist"><a class="card-link" href="{h(v["filename"])}">{h(heading)}</a></div>'
            f'{sub_html}'
            f'<div class="card-museum visit-kind">{h(v["kind"])}</div></div>'
            f'<div class="card-facts">{facts_html}</div></article>'
        )

    head = head_common(
        title="Посещения — Old Picture Art",
        description=(f"Выставки и музеи, где я побывал: {shows} "
                     f"{plural_ru(shows, 'выставка', 'выставки', 'выставок')} "
                     f"и {museums} {plural_ru(museums, 'музей', 'музея', 'музеев')}."),
        canonical=f"{BASE_URL}/visits.html",
        og_image=site_og_image(items),
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page visits-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  <a href="museums.html" class="back">Карта собраний</a>
  {theme_button('theme-toggle-inline')}
</div>
{scroll_top_button()}
<header class="artist-head">
  <p class="eyebrow">Дневник</p>
  <h1>Посещения</h1>
  <p class="idx-lede visits-lede">Выставки и музеи, где я побывал, — с датами и своими снимками.</p>
  <div class="visit-bar">
    <div class="view-switch visit-switch" role="group" aria-label="Что показывать">
      <button type="button" data-kind="all" aria-pressed="true">Все <span class="visit-count">{len(items)}</span></button>
      <button type="button" data-kind="выставка" aria-pressed="false">Выставки <span class="visit-count">{shows}</span></button>
      <button type="button" data-kind="музей" aria-pressed="false">Музеи <span class="visit-count">{museums}</span></button>
    </div>
    <div class="view-switch visit-view" role="group" aria-label="Как показывать">
      <button type="button" data-view="grid" aria-pressed="true">Плитки</button>
      <button type="button" data-view="list" aria-pressed="false">Опись</button>
    </div>
  </div>
</header>
<div class="grid" id="visits">{''.join(cards)}</div>
<p class="no-results" id="visits-empty" hidden>Пока ничего нет.</p>
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
<script>
(function () {{
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.visit-switch button'));
  var cards = Array.prototype.slice.call(document.querySelectorAll('#visits .visit-card'));
  var empty = document.getElementById('visits-empty');
  function show(kind) {{
    var shown = 0;
    cards.forEach(function (c) {{
      var ok = kind === 'all' || c.getAttribute('data-kind') === kind;
      c.hidden = !ok;
      if (ok) shown++;
    }});
    buttons.forEach(function (b) {{
      b.setAttribute('aria-pressed', b.getAttribute('data-kind') === kind ? 'true' : 'false');
    }});
    if (empty) empty.hidden = shown !== 0;
    try {{ localStorage.setItem('visitFilter', kind); }} catch (e) {{}}
  }}
  buttons.forEach(function (b) {{
    b.addEventListener('click', function () {{ show(b.getAttribute('data-kind')); }});
  }});
  var saved = 'all';
  try {{ saved = localStorage.getItem('visitFilter') || 'all'; }} catch (e) {{}}
  if (!buttons.some(function (b) {{ return b.getAttribute('data-kind') === saved; }})) saved = 'all';
  show(saved);

  // Раскладка. По умолчанию плитки: походов много, и описью страница
  // растягивается на несколько экранов — прокручивать её никто не станет.
  var grid = document.getElementById('visits');
  var viewBtns = Array.prototype.slice.call(document.querySelectorAll('.visit-view button'));
  function setView(mode) {{
    grid.classList.toggle('list', mode === 'list');
    viewBtns.forEach(function (b) {{
      b.setAttribute('aria-pressed', b.getAttribute('data-view') === mode ? 'true' : 'false');
    }});
    try {{ localStorage.setItem('visitView', mode); }} catch (e) {{}}
  }}
  viewBtns.forEach(function (b) {{
    b.addEventListener('click', function () {{ setView(b.getAttribute('data-view')); }});
  }});
  var view = 'grid';
  try {{ view = localStorage.getItem('visitView') || 'grid'; }} catch (e) {{}}
  setView(view === 'list' ? 'list' : 'grid');
}})();
</script>
</body></html>"""


@tidy
def render_visit_page(visit, visits, all_posts=None, map_names=None):
    """Страница одного посещения: все снимки, сведения, ссылка на карту.

    Разметка та же, что у страницы работы, — шапка, колонка снимков,
    таблица сведений справа, лупа по клику: посещение в каталоге такая же
    запись, как картина, и выглядеть должно так же.
    """
    heading = visit_heading(visit)
    photos = visit.get("images") or []
    hires = visit.get("hires") or []
    place = (visit.get("place") or "").strip()
    slug = slugify(heading)

    # Снимков с похода бывает десяток, и колонкой во всю ширину страница
    # растягивалась на пять экранов. Сетка: два-три снимка в ряд, клик
    # открывает лупу — рассматривают в ней, а не на странице.
    shots = []
    thumbs = visit.get("thumbs") or []
    vlist = visit.get("views") or []
    for i, src in enumerate(photos):
        big = hires_url(hires[i] if i < len(hires) else src)
        small = thumbs[i] if i < len(thumbs) else src
        loading = ('fetchpriority="high" decoding="async"' if i == 0
                   else 'loading="lazy" decoding="async"')
        meta_bits = [x for x in (place if place != heading else "", visit.get("visited", "")) if x]
        vw = vlist[i] if i < len(vlist) else ""
        shots.append(
            f'<a href="{h(big)}" class="painting-link shot" target="_blank" rel="noopener" '
            + (f'data-view="{h(vw)}" ' if vw else '')
            + f'title="Рассмотреть" data-title="{h(heading)}" data-meta="{h(", ".join(meta_bits))}" '
            f'data-download="{h(slug)}-{i + 1}{h(os.path.splitext(big)[1] or ".jpg")}">'
            f'<img src="{h(small)}" alt="{h(heading)}, снимок {i + 1}" class="painting"{size_attrs(small)} {loading}>'
            f'<span class="painting-hint" aria-hidden="true">'
            f'<span class="icon-lupa" aria-hidden="true"></span> Рассмотреть</span></a>'
        )
    img_html = ('<div class="shots">' + "\n".join(shots) + '</div>') if shots else ""

    spec_rows = [("Что", visit["kind"].capitalize()),
                 ("Место", place if place != heading else ""),
                 ("Раздел", visit.get("note", "")),
                 ("Работала", visit.get("run", "")),
                 ("Побывал", visit.get("visited", "")),
                 ("Снимков", str(len(photos)) if photos else "")]
    spec_html = '<div class="spec-table">' + "".join(
        f'<div><span>{h(k)}</span><b>{h(v)}</b></div>' for k, v in spec_rows if v)
    # Место всегда есть на карте: карта собирает и музеи из собрания,
    # и залы, где были только походы.
    museum = (map_names or {}).get(place, "")
    if museum:
        spec_html += (f'<div><span>На карте</span><b><a href="museums.html#museum-'
                      f'{h(slugify(museum))}">{h(museum)}</a></b></div>')
    spec_html += '</div>'

    # Теги музеев из поста (#гмии, #гтг) ведут в подборки картин — если
    # такая страница есть. Тег без страницы был бы битой ссылкой.
    tags_block = ""
    known_tags = {t for p in (all_posts or []) for t in p.get("tags", [])}
    tags = [t for t in visit.get("tags", []) if t in known_tags]
    if tags:
        its = " ".join(f'<a href="tag-{h(tag_slug(t))}.html" class="tag">#{h(t)}</a>' for t in tags)
        tags_block = f'<div class="aside-block"><h3>Собрание</h3><div class="tags">{its}</div></div>'

    src_block = ""
    if visit.get("urls"):
        its = "".join(f'<li><a href="{h(u)}" target="_blank" rel="noopener">{h(u)}</a></li>'
                      for u in visit["urls"])
        word = "Источник" if len(visit["urls"]) == 1 else "Источники"
        src_block = f'<div class="aside-block"><h3>{word}</h3><ul class="source-list">{its}</ul></div>'

    download_btn = ""
    if photos:
        first = hires_url(hires[0] if hires else photos[0])
        download_btn = (f'<a href="{h(first)}" download="{h(slug)}-1{h(os.path.splitext(first)[1] or ".jpg")}" '
                        f'class="topbar-btn" aria-label="Скачать снимок" title="Скачать снимок">'
                        f'<span class="icon-download" aria-hidden="true"></span></a>')

    ordered = sorted(visits, key=visit_sort_key)
    idx = next((i for i, v in enumerate(ordered) if v["filename"] == visit["filename"]), -1)
    nav = []
    if idx > 0:
        prev = ordered[idx - 1]
        nav.append(f'<a href="{h(prev["filename"])}" class="prev-post" title="{h(visit_heading(prev))}">'
                   f'<span class="icon-prev" aria-hidden="true"></span> Раньше</a>')
    if 0 <= idx < len(ordered) - 1:
        nxt = ordered[idx + 1]
        nav.append(f'<a href="{h(nxt["filename"])}" class="next-post" title="{h(visit_heading(nxt))}">'
                   f'Позже <span class="icon-next" aria-hidden="true"></span></a>')
    nav_html = f'<nav class="post-nav">{"".join(nav)}</nav>' if nav else ""

    desc = heading + (f", {place}" if place and place != heading else "")
    desc += f". Побывал {visit['visited']}." if visit.get("visited") else "."
    tab = f"{heading} — Old Picture Art"
    if len(tab) > 70:
        tab = heading if len(heading) <= 70 else heading[:67].rsplit(" ", 1)[0] + "…"
    head = head_common(
        title=h(tab),
        description=desc,
        og_image=f"{BASE_URL}/{photos[0]}" if photos else "",
        canonical=f"{BASE_URL}/{visit['filename']}",
        og_type="article",
    )
    sub_head = f'<h2>{h(place)}</h2>' if place and place != heading else ''
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="post-page visit-page">
<a href="#main" class="skip-link">К содержанию</a>
<div class="post-topbar">
  <a href="visits.html" class="topbar-back"><span class="icon-back" aria-hidden="true"></span> Посещения</a>
  <div class="post-topbar-right">
    <button type="button" data-share-btn onclick="sharePage(this)" class="topbar-btn" aria-label="Поделиться" title="Поделиться" aria-haspopup="menu"><span class="icon-share" aria-hidden="true"></span></button>
    {download_btn}
    <button type="button" class="topbar-btn" data-theme-toggle onclick="toggleTheme()" aria-label="Переключить тему" title="Светлая / тёмная тема"><span class="icon-theme-toggle" aria-hidden="true"></span></button>
  </div>
</div>
{scroll_top_button()}
<article id="main" class="post-layout">
  <div class="post-main">
    <header class="post-head">
      <p class="eyebrow">{h(visit["kind"].capitalize())}</p>
      <h1>{h(heading)}</h1>
      {sub_head}
    </header>
    {img_html}
  </div>
  <aside class="post-aside">
    {spec_html}
    {tags_block}
    {src_block}
    <div class="aside-block">
      <h3>Запись</h3>
      <time>{h(visit.get('date', ''))}</time>
    </div>
  </aside>
</article>
{nav_html}
{site_footer()}
{SCROLL_TOP_JS}
{COMMON_JS}
{LUPA_JS}
{TOAST_JS}
{SHARE_JS}
</body></html>"""


def generate_visit_pages(visits, all_posts=None):
    """Страницы посещений и общий список. Если посещений нет — ничего
    не создаём: раздел появится сам, когда в канале найдутся такие посты."""
    if not visits:
        return 0
    map_names = visit_map_names(visits, all_posts)
    wanted = set()
    for v in visits:
        wanted.add(v["filename"])
        with open(os.path.join(OUTPUT_DIR, v["filename"]), "w", encoding="utf-8", newline="\n") as f:
            f.write(render_visit_page(v, visits, all_posts, map_names))
    with open(os.path.join(OUTPUT_DIR, "visits.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_visits_page(visits, all_posts))
    # Заголовок поста могли поправить — имя страницы тогда меняется,
    # а прежняя остаётся в docs/ навсегда и попадает в поиск.
    # Прежние адреса посещений оставляем перенаправлениями, а не сносим:
    # уборка шла по приставке visit-, под которую попадали и они.
    legacy = {old: v["filename"] for v in visits for old in v.get("old_filenames", [])}
    moved, removed = retire_pages("visit-", wanted, legacy)
    if moved:
        logger.info(f"Прежних адресов посещений оставлено перенаправлениями: {moved}")
    if removed:
        logger.info(f"Убрано устаревших страниц посещений: {removed}")
    logger.info(f"Посещения: {len(visits)} + список")
    return len(visits)


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
        with open(os.path.join(OUTPUT_DIR, f"tag-{tag_slug(tag)}.html"), "w", encoding="utf-8") as f:
            f.write(render_tag_page(tag, posts, cat_no, cat_width))
        c += 1

    # Страницы тегов, которых в собрании больше нет, надо убирать.
    # Исправили опечатку в посте — и tag-freidrich.html остаётся лежать
    # навсегда: на него никто не ссылается, в карте сайта его нет, но
    # поисковик, раз его увидев, будет ходить по нему годами и показывать
    # людям пустой раздел.
    live = {f"tag-{tag_slug(t)}.html" for t in tp}
    legacy = {f"tag-{t}.html": f"tag-{tag_slug(t)}.html" for t in tp}
    moved, removed = retire_pages("tag-", live, legacy)
    if moved:
        logger.info(f"Прежних адресов тегов оставлено перенаправлениями: {moved}")
    if removed:
        logger.info(f"Убрано страниц исчезнувших тегов: {removed}")

    logger.info(f"Сгенерировано {c} страниц тегов")
    return tp


def generate_extra_pages(all_posts):
    """Страницы художников, указатель и статистика."""
    cat_no, cat_width = catalogue_numbers(all_posts)

    by_artist = defaultdict(list)
    for p in all_posts:
        if p.get("artist"):
            by_artist[p["artist"].strip()].append(p)
    for artist, posts in by_artist.items():
        with open(os.path.join(OUTPUT_DIR, artist_slug(artist)), "w", encoding="utf-8") as f:
            f.write(render_artist_page(artist, posts, all_posts, cat_no, cat_width))
    logger.info(f"Сгенерировано {len(by_artist)} страниц художников")

    # Та же уборка, что и у тегов: художник ушёл из собрания или его
    # страница переехала на латинский адрес — прежний файл остаётся
    # лежать и подбирать поисковых роботов.
    live = {artist_slug(a) for a in by_artist}
    legacy = {"artist-" + slugify(a) + ".html": artist_slug(a) for a in by_artist}
    moved, removed = retire_pages("artist-", live, legacy)
    if moved:
        logger.info(f"Прежних адресов художников оставлено перенаправлениями: {moved}")
    if removed:
        logger.info(f"Убрано прежних страниц художников: {removed}")

    with open(os.path.join(OUTPUT_DIR, "ukazatel.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_ukazatel(all_posts))
    with open(os.path.join(OUTPUT_DIR, "stats.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_stats(all_posts))
    logger.info("Указатель и статистика готовы")
    return by_artist

@tidy
def render_404():
    """Раньше 404 была пустой страницей с meta refresh: без заголовка,
    без объяснения, и на вложенных адресах редирект вёл в никуда."""
    # base href="/" — обязательно. GitHub Pages показывает эту страницу
    # по любому несуществующему адресу, в том числе вложенному вроде
    # /старое/имя.html. Все адреса на странице относительные — стили,
    # значок, ссылки, — и без base они считались бы от /старое/: стили не
    # загрузились бы, а «В галерею» вело бы на ещё одну страницу 404.
    head = head_common(
        title="Страница не найдена — Old Picture Art",
        description="Такой страницы нет. Вернитесь в галерею Old Picture Art.",
    )
    # Сразу после кодировки, до всего остального: элементы, стоящие в
    # head раньше base, успевают разрешить свои адреса по адресу самой
    # страницы. Поставь base в конец — и стиль на вложенном адресе
    # всё равно бы не загрузился.
    head = head.replace('<meta charset="UTF-8">', '<meta charset="UTF-8">\n<base href="/">', 1)
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="error-page">
<main class="error-box">
  <p class="error-code">404</p>
  <h1>Страница не найдена</h1>
  <p class="error-text">Возможно, картину переименовали или ссылка устарела.</p>
  <p><a class="random-btn" href="./">В галерею</a></p>
  <p class="error-links"><a href="quiz.html">Квиз</a> · <a href="timeline.html">Таймлайн</a> · <a href="museums.html">Карта собраний</a></p>
</main>
{site_footer()}
{COMMON_JS}
</body></html>"""



@tidy
def render_privacy():
    """Страница о данных: что сайт узнаёт о посетителе, зачем и как отказаться.

    Написана для людей, а не для проверяющих: коротко, по разделам, без
    «настоящим уведомляем». Каждый раздел отвечает на три вопроса — что
    собирается, кем и как это выключить. Раздел о Метрике исчезает, если
    счётчик выключен (METRIKA_ID пуст), — не описывать того, чего нет.
    """
    auth_on = bool(AUTH_API_URL and (YANDEX_CLIENT_ID or VK_CLIENT_ID))
    head = head_common(
        title="Конфиденциальность — Old Picture Art",
        description="Какие данные собирает сайт Old Picture Art, зачем и как от этого отказаться: "
                    + ("Яндекс Метрика, вход через Яндекс ID и VK ID, настройки в браузере."
                       if auth_on else "Яндекс Метрика и настройки в браузере."),
        canonical=f"{BASE_URL}/privacy.html",
    )
    contact = (f'<a href="{h(PRIVACY_CONTACT)}"'
               + ('' if PRIVACY_CONTACT.startswith("mailto:") else ' target="_blank" rel="noopener"')
               + f'>{h(PRIVACY_CONTACT_TEXT)}</a>')
    owner = f"Сайт ведёт {h(SITE_OWNER)}. " if SITE_OWNER else ""
    # Про вход рассказываем, только когда он настроен (AUTH_API_URL и хотя
    # бы один из YANDEX_CLIENT_ID / VK_CLIENT_ID в site_common.py):
    # описывать на странице о данных то, чего на сайте нет, — путать людей.
    # Пока входа нет, страница так и говорит: аккаунтов нет, отметки —
    # только в браузере. Входа через Google и Firebase больше нет совсем.
    account = f"""<section class="doc-block" id="account">
  <h2>Вход в аккаунт</h2>
  <p>Нужен только для одного — чтобы отмеченные картины были на всех ваших устройствах.
  Без входа отметки хранятся в вашем браузере и никуда не отправляются.</p>
  <h3>Как входят</h3>
  <p>Через Яндекс ID или VK ID. Пароль вы вводите на странице Яндекса или VK — сайт его
  не видит. Яндекс или VK сообщают сайту номер вашего аккаунта у них и имя.</p>
  <h3>Что хранится</h3>
  <ul>
    <li>номер аккаунта у Яндекса или VK и список отмеченных картин со временем отметки —
    в базе на серверах Yandex Cloud в России;</li>
    <li>имя — только в вашем браузере, чтобы показать его на кнопке; на сервер оно не записывается.</li>
  </ul>
  <p>Сколько раз отмечена картина, видят все посетители — только число, без имён и
  аккаунтов; из этих же чисел собран блок «Популярное у посетителей» на главной.</p>
  <p>Почту, телефон и список друзей сайт не запрашивает. Базу держит ООО «Яндекс.Облако»,
  вход проверяют ООО «ЯНДЕКС» (Яндекс ID) и ООО «ВК» (VK ID) — каждый по своим правилам.</p>
  <h3>Как удалить</h3>
  <p>Снятая отметка удаляется сразу. Все отметки разом — кнопкой «Удалить мои отметки из
  облака» в окне аккаунта (нажмите на своё имя вверху страницы картины). Выйти из аккаунта
  можно там же. Вопросы — {contact}.</p>
</section>"""

    metrika = "" if not METRIKA_ID else """
<section class="doc-block" id="metrika">
  <h2>Статистика посещений — Яндекс Метрика</h2>
  <p>Включается, только если вы нажали «Принять» на плашке внизу страницы. До этого
  счётчик не загружается и ничего не отправляет.</p>
  <div class="consent-controls" id="consent-controls">
    <p class="consent-state" id="consent-state" role="status">Статистика: вы пока не решили.</p>
    <p class="consent-actions">
      <button type="button" class="consent-btn" data-consent="yes">Разрешить статистику</button>
      <button type="button" class="consent-btn" data-consent="no">Отключить статистику</button>
    </p>
  </div>
  <h3>Что получает Метрика</h3>
  <ul>
    <li>cookie <code>_ym_uid</code>, <code>_ym_d</code>, <code>_ym_isad</code> и другие — чтобы отличить повторный визит от нового; самая долгая живёт год;</li>
    <li>IP-адрес, тип устройства, браузер, размер экрана, язык;</li>
    <li>адрес страницы и откуда вы на неё пришли;</li>
    <li>действия на странице — прокрутку, нажатия, движение указателя (это Вебвизор).</li>
  </ul>
  <p>Имени, почты и телефона Метрика не получает.</p>
  <h3>Зачем</h3>
  <p>Чтобы понимать, какие картины смотрят, откуда приходят и где на сайте неудобно.
  Рекламы здесь нет, и данные для неё не используются.</p>
  <h3>Кто обрабатывает</h3>
  <p>ООО «ЯНДЕКС» — по своим <a href="https://yandex.ru/legal/metrica_termsofuse/" target="_blank" rel="noopener">условиям
  использования Метрики</a> и <a href="https://yandex.ru/legal/confidential/" target="_blank" rel="noopener">политике
  конфиденциальности</a>.</p>
  <h3>Как отказаться</h3>
  <ul>
    <li>кнопкой «Отключить статистику» выше — сайт сотрёт cookie Метрики на своём адресе и больше её не загрузит;</li>
    <li>для всех сайтов сразу — <a href="https://yandex.ru/support/metrica/ru/general/opt-out" target="_blank" rel="noopener">блокировщиком
    Яндекс Метрики</a>, расширением для браузера от самого Яндекса;</li>
    <li>в настройках браузера — запретив cookie или очистив данные сайта.</li>
  </ul>
</section>"""

    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page doc-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
<header class="artist-head">
  <p class="eyebrow">О сайте</p>
  <h1>Конфиденциальность</h1>
  <p class="doc-lede">Old Picture Art — некоммерческое собрание картин из телеграм-канала
  {h(TELEGRAM_NAME)}. {owner}Здесь коротко о том, что сайт узнаёт о посетителях, зачем и как от этого отказаться.</p>
  <p class="doc-date">Редакция от {h(PRIVACY_DATE)}</p>
</header>
<main class="doc-body">
<section class="doc-block" id="short">
  <h2>Коротко</h2>
  <ul>
    <li>Смотреть картины, искать, играть в квиз можно без регистрации и без согласия на статистику.</li>
    <li>Статистика посещений включается, только если вы её разрешили.</li>
{'    <li>Аккаунт нужен только для переноса отметок между устройствами; вход — через Яндекс ID или VK ID. Номер аккаунта хранится, только если вы сами вошли.</li>' if auth_on else '    <li>Аккаунтов на сайте нет: отмеченные картины хранятся только в вашем браузере.</li>'}
    <li>Данные не продаются и не передаются никому, кроме названных ниже сервисов.</li>
  </ul>
</section>
{metrika}
{account if auth_on else ""}
<section class="doc-block" id="browser">
  <h2>Что остаётся только в вашем браузере</h2>
  <p>В хранилище браузера (localStorage) сайт запоминает тему оформления, отмеченные
  картины, счёт в квизе и ваш ответ насчёт статистики{", а если вы вошли — ещё пропуск для входа и ваше имя" if auth_on else ""}.
  {"Отметки вошедших дублируются в облако (см. выше), остальное" if auth_on else "Это"} не уходит ни на какой сервер;
  стереть — очистить данные сайта в настройках браузера.</p>
</section>

<section class="doc-block" id="services">
  <h2>Откуда загружаются части страниц</h2>
  <p>Чтобы показать страницу, браузер обращается к этим сервисам и, как при любом запросе
  в интернете, сообщает им свой IP-адрес:</p>
  <ul>
    <li>GitHub Pages — хостинг сайта (<a href="https://docs.github.com/ru/site-policy/privacy-policies/github-general-privacy-statement" target="_blank" rel="noopener">политика GitHub</a>);</li>
    <li>Google Fonts — шрифты;</li>
    <li>cdnjs.cloudflare.com — код подбора цвета рамки;</li>
{'    <li>functions.yandexcloud.net — отметки тех, кто вошёл в аккаунт;</li>' if auth_on else ''}
    <li>на карте собраний — подложки OpenStreetMap, OpenTopoMap, Esri и Яндекс Карт и библиотека карты с unpkg.com.</li>
  </ul>
</section>

<section class="doc-block" id="contact">
  <h2>Вопросы</h2>
  <p>О данных{", об удалении отметок из облака" if auth_on else ""} и обо всём остальном — {contact}.</p>
</section>
</main>
{site_footer()}
{COMMON_JS}
<script>
// Кнопки согласия на этой странице и строка с текущим выбором.
(function () {{
  var box = document.getElementById('consent-controls');
  if (!box || !window.metrikaConsent) return;
  var state = document.getElementById('consent-state');
  function show() {{
    var v = window.metrikaConsent.state();
    state.textContent = v === 'yes' ? 'Статистика сейчас разрешена.'
                      : v === 'no' ? 'Статистика сейчас отключена.'
                      : 'Статистика: вы пока не решили — счётчик не загружается.';
    box.querySelectorAll('[data-consent]').forEach(function (b) {{
      b.setAttribute('aria-pressed', b.getAttribute('data-consent') === v ? 'true' : 'false');
    }});
  }}
  box.addEventListener('click', function (e) {{
    var v = e.target.getAttribute && e.target.getAttribute('data-consent');
    if (v === 'yes') window.metrikaConsent.allow();
    else if (v === 'no' && window.metrikaConsent.deny()) {{
      // счётчик уже работал на этой странице — остановить его можно только перезагрузкой
      location.reload();
      return;
    }}
    show();
  }});
  show();
}})();
</script>
</body></html>"""


@tidy
def render_auth_page():
    """auth.html — куда Яндекс ID и VK ID возвращают человека после входа.

    Страница служебная: забирает из адреса код входа, проверяет, что это
    ответ на наш же запрос (state), отдаёт код функции в Yandex Cloud,
    получает пропуск, сводит отметки и возвращает человека туда, откуда
    он нажал «Войти». Если что-то не так — говорит об этом словами и
    даёт вернуться. В поиск ей незачем, отсюда noindex.
    """
    head = head_common(
        title="Вход — Old Picture Art",
        description="Вход в аккаунт Old Picture Art.",
        extra='\n<meta name="robots" content="noindex">',
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="error-page">
<main class="error-box">
  <h1 id="auth-status">Входим…</h1>
  <p class="error-text" id="auth-msg" role="status">Минуту — сверяемся с Яндексом или VK.</p>
  <p><a class="random-btn" id="auth-back" href="./">Вернуться на сайт</a></p>
</main>
{CLOUD_JS}
<script>
(function () {{
  var q = new URLSearchParams(location.search);
  var flow = null;
  try {{ flow = JSON.parse(sessionStorage.getItem('auth-flow') || 'null'); sessionStorage.removeItem('auth-flow'); }} catch (e) {{}}
  // Вернуть можно только на свой же сайт — чужой адрес в back не пройдёт.
  var back = './';
  try {{ if (flow && flow.back && new URL(flow.back).origin === location.origin) back = flow.back; }} catch (e) {{}}
  document.getElementById('auth-back').href = back;

  function fail(text) {{
    document.getElementById('auth-status').textContent = 'Войти не получилось';
    document.getElementById('auth-msg').textContent = text;
  }}
  if (!CLOUD.on) return fail('Вход на сайте сейчас выключен.');
  if (q.get('error')) {{
    return fail(q.get('error') === 'access_denied' ? 'Вход отменён.'
                : 'Ответ сервиса входа: ' + (q.get('error_description') || q.get('error')));
  }}
  if (!flow || !q.get('code') || q.get('state') !== flow.state) {{
    return fail('Не удалось проверить, что это ваш вход. Попробуйте войти ещё раз.');
  }}
  var data = {{provider: flow.provider, code: q.get('code'), state: q.get('state')}};
  if (flow.provider === 'vk') {{ data.code_verifier = flow.verifier; data.device_id = q.get('device_id'); }}
  cloudCall('login', data)
    .then(function (j) {{
      setSession({{token: j.token, name: j.name, provider: j.provider, exp: j.exp}});
      return cloudSync('merge');
    }})
    .then(function () {{
      try {{ sessionStorage.setItem('auth-greet', '1'); }} catch (e) {{}}
      location.replace(back);
    }})
    .catch(function (e) {{ fail(e.message || 'Сервер не ответил. Попробуйте позже.'); }});
}})();
</script>
</body></html>"""

def generate_sitemap(all_posts, visits=None):
    logger.info("Sitemap...")
    bu = BASE_URL
    # Кодирование оставлено, хотя имена страниц теперь латинские: в
    # карту попадают и адреса картинок, а те по-прежнему кириллические.
    # Страницы-перенаправления со старых адресов сюда не попадают —
    # список строится по нынешним именам, а не по содержимому папки.
    def u(path):
        return quote(path, safe="/")
    urls = [f"  <url><loc>{bu}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for p in all_posts: urls.append(f"  <url><loc>{bu}/{u(p['filename'])}</loc><lastmod>{p['date']}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>")
    urls.append(f"  <url><loc>{bu}/feed.xml</loc><changefreq>daily</changefreq><priority>0.6</priority></url>")
    urls.append(f"  <url><loc>{bu}/museums.html</loc><changefreq>monthly</changefreq><priority>0.4</priority></url>")
    urls.append(f"  <url><loc>{bu}/quiz.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    urls.append(f"  <url><loc>{bu}/timeline.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    urls.append(f"  <url><loc>{bu}/ukazatel.html</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>")
    urls.append(f"  <url><loc>{bu}/stats.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    urls.append(f"  <url><loc>{bu}/privacy.html</loc><changefreq>yearly</changefreq><priority>0.2</priority></url>")
    # Посещения — только если они есть: ссылка на несуществующую
    # страницу в карте сайта портит её целиком.
    visits = visits or []
    if visits:
        urls.append(f"  <url><loc>{bu}/visits.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
        for v in visits:
            urls.append(f"  <url><loc>{bu}/{u(v['filename'])}</loc><lastmod>{v['date']}</lastmod><changefreq>monthly</changefreq><priority>0.5</priority></url>")
    # Страницы художников — то, что ищут чаще всего («Левитан картины»),
    # поэтому приоритет у них выше, чем у тегов.
    for a in sorted({p["artist"].strip() for p in all_posts if p.get("artist")}):
        urls.append(f"  <url><loc>{bu}/{u(artist_slug(a))}</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>")
    at = set()
    for p in all_posts:
        for t in p.get("tags",[]): at.add(t)
    for t in sorted(at): urls.append(f"  <url><loc>{bu}/{u('tag-' + tag_slug(t) + '.html')}</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + '\n</urlset>')
    logger.info(f"Sitemap ({len(urls)} URL)")

def _draw_mark(size, inset=0.0):
    """Знак сайта растром. inset — доля поля вокруг рисунка: для плиток
    Android (maskable) края обрезаются, поэтому там знак ужимаем внутрь."""
    from PIL import ImageDraw
    navy = (31, 58, 107, 255)
    cream = (242, 237, 227, 255)
    ochre = (201, 163, 94, 255)
    img = Image.new("RGBA", (size, size), navy)
    d = ImageDraw.Draw(img)
    pad = size * inset
    s = (size - 2 * pad) / 32.0

    def box(x0, y0, x1, y1, fill):
        d.rectangle([pad + x0 * s, pad + y0 * s, pad + x1 * s, pad + y1 * s], fill=fill)

    box(4, 6, 28, 26, cream)          # холст
    box(4, 20, 28, 26, ochre)         # земля
    r = 3 * s
    cx, cy = pad + 22 * s, pad + 12 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=navy)   # солнце
    return img


def generate_icons():
    """Значки сайта: svg для вкладки, ico для старых браузеров, png для
    телефона и манифеста. Раньше манифест ссылался на файлы, которых
    в репозитории не было, а фавикон был отдельной картинкой, ничем
    не связанной с оформлением."""
    # svg пишем всегда: он не требует PIL и именно его берут современные браузеры
    with open(os.path.join(OUTPUT_DIR, "favicon.svg"), "w", encoding="utf-8", newline="\n") as f:
        f.write(mark_svg())

    if not PIL_AVAILABLE:
        logger.warning("PIL не установлен — png и ico значки не обновлены")
        return []

    # ico собираем из отрисованных размеров, а не уменьшением одного:
    # у знака прямые границы, и пересчёт их размывает
    ico_sizes = [16, 32, 48]
    frames = [_draw_mark(n) for n in ico_sizes]
    frames[-1].save(os.path.join(OUTPUT_DIR, "favicon.ico"),
                    format="ICO", sizes=[(n, n) for n in ico_sizes],
                    append_images=frames[:-1])

    _draw_mark(180).save(os.path.join(OUTPUT_DIR, "apple-touch-icon.png"), "PNG")

    made = []
    for size in (192, 512):
        _draw_mark(size).save(os.path.join(IMAGES_DIR, f"icon-{size}.png"), "PNG")
        made.append((f"images/icon-{size}.png", size, "any"))
        # maskable Android обрезает по кругу — знак должен уместиться внутри
        _draw_mark(size, inset=0.18).save(os.path.join(IMAGES_DIR, f"icon-{size}-maskable.png"), "PNG")
        made.append((f"images/icon-{size}-maskable.png", size, "maskable"))
    return made


def generate_manifest():
    icons = [{"src": src, "sizes": f"{n}x{n}", "type": "image/png", "purpose": purpose}
             for src, n, purpose in generate_icons()]
    data = {
        "name": "Old Picture Art",
        "short_name": "OldPictureArt",
        "description": "Галерея картин из старых музейных собраний",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "lang": "ru",
        "background_color": "#eceef1",
        "theme_color": "#eceef1",
        "icons": icons,
    }
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
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
    with open(os.path.join(OUTPUT_DIR, "feed.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(rss)
    logger.info("RSS сгенерирован")

def generate_museums_page(all_posts):
    """Генерирует карту музеев через отдельный скрипт."""
    logger.info("Генерация карты музеев...")
    try:
        subprocess.run([sys.executable, "generate_map.py"], check=True)
        logger.info("Карта собраний сгенерирована")
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
    for fn in (PROCESSED_FILE, META_FILE, VISITS_FILE):
        if os.path.exists(fn): os.remove(fn)

async def main():
    if "--rebuild" in sys.argv: rebuild_reset()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, ".nojekyll"), "w") as f: pass
    if not PIL_AVAILABLE: logger.warning("Pillow не установлен")
    processed_ids = set(load_json(PROCESSED_FILE, []))
    all_posts = load_json(META_FILE, [])
    all_visits = load_json(VISITS_FILE, [])
    logger.info("Подключение к Telegram...")
    api_id, api_hash, phone = require_credentials()
    client = await connect_with_proxy(api_id, api_hash, phone, PROXY_LIST)
    # Полный проход нужен дважды: когда файла посещений ещё нет (сборка
    # первая, которая умеет #выставка и #галерея) и когда у прежних походов
    # ещё не собраны безымянные посты со снимками. Картинам это не мешает —
    # их отсеет processed_ids.
    full_scan = (not os.path.exists(VISITS_FILE)
                 or not all(v.get("extras_done") for v in all_visits)
                 or "--rescan" in sys.argv)
    try:
        accepted, new_visits, extras_for_known = await fetch_new_posts(
            client, processed_ids, full_scan, all_visits)
    except Exception as e: logger.error(f"Ошибка сканирования: {e}"); await client.disconnect(); return
    for i, (mm, group, parsed) in enumerate(accepted, 1):
        date = mm.date.strftime("%Y-%m-%d")
        # Имя страницы считаем сразу тем же способом, что и при
        # пересборке, — иначе новая запись сначала получила бы
        # кириллическое имя, под ним скачались бы картинки, и лишь потом
        # страница переехала бы, оставив файлы с прежними именами.
        provisional = {**parsed, "date": date}
        base = post_slug(provisional, prepare_slugs(all_posts + [provisional]))
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
        with open(os.path.join(OUTPUT_DIR, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(render_post_page(post, all_posts))
    async def visit_comments(anchor):
        out = []
        if getattr(anchor, "replies", None) and anchor.replies.replies > 0:
            try:
                async for reply in client.iter_messages(CHANNEL_URL, reply_to=anchor.id):
                    if getattr(reply, "document", None) and reply.document.mime_type.startswith("image/"):
                        out.append(reply)
            except Exception as e: logger.warning(f"Комментарии: {e}")
        return out

    async def add_photos(visit, groups, slug):
        """Докачивает снимки из безымянных постов к тому же походу."""
        for g in groups:
            im, hi, th = await download_images(client, g, [], slug,
                                               start=len(visit.get("images") or []))
            visit["images"] = (visit.get("images") or []) + im
            visit["hires"] = (visit.get("hires") or []) + hi
            visit["thumbs"] = (visit.get("thumbs") or []) + th
            processed_ids.update(m.id for m in g)

    # Посещения качаем тем же порядком: снимков в таком посте бывает
    # десяток, и все они нужны на странице похода.
    for i, (vm, group, parsed, extra) in enumerate(new_visits, 1):
        date = vm.date.strftime("%Y-%m-%d")
        base = f"visit-{date}-{slugify(visit_heading(parsed))}"
        fn, n = f"{base}.html", 2
        ex = {v["filename"] for v in all_visits}
        while fn in ex or os.path.exists(os.path.join(OUTPUT_DIR, fn)): fn = f"{base}-{n}.html"; n += 1
        logger.info(f"[посещение {i}/{len(new_visits)}] {visit_heading(parsed)[:60]}"
                    + (f" (+{len(extra)} без подписи)" if extra else ""))
        im, hi, th = await download_images(client, group, await visit_comments(vm), fn[:-5])
        visit = {"id":vm.id,"date":date,"filename":fn,"images":im,"hires":hi,"thumbs":th,
                 "extras_done":True, **parsed}
        processed_ids.update(m.id for m in group)
        await add_photos(visit, extra, fn[:-5])
        all_visits.append(visit)

    # Добавки к походам, которые уже были в базе: пост со снимками мог
    # выйти позже самого посещения или просто не собирался прежней сборкой.
    by_id = {v.get("id"): v for v in all_visits}
    for vid, groups in extras_for_known.items():
        visit = by_id.get(vid)
        if not visit:
            continue
        before = len(visit.get("images") or [])
        await add_photos(visit, groups, visit["filename"][:-5])
        added = len(visit.get("images") or []) - before
        if added:
            logger.info(f"[посещение] {visit_heading(visit)[:50]}: +{added} снимков без подписи")
    if full_scan:
        for v in all_visits:
            v["extras_done"] = True
    await client.disconnect()
    logger.info("Отключено")
    if PIL_AVAILABLE:
        miss = [p for p in all_posts + all_visits if not p.get("thumbs") and p.get("images")]
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
        build_views(all_posts + all_visits)
        build_cards(all_posts)
    # Файл посещений пишем до страниц: по нему подвал и сайдбар решают,
    # показывать ли раздел, а страницы картин собираются следом.
    refresh_visits(all_visits)
    # Адреса страниц — до записи страниц: на имена файлов опираются
    # ссылки между страницами, карта сайта и RSS. Переименование
    # идемпотентно: у записей с правильным именем ничего не меняется.
    fix_work_years(all_posts)
    prepare_slugs(all_posts)
    rename_pages(all_posts, all_visits)
    save_json(VISITS_FILE, all_visits)
    for post in all_posts:
        with open(os.path.join(OUTPUT_DIR, post["filename"]), "w", encoding="utf-8", newline="\n") as f:
            f.write(render_post_page(post, all_posts))
    save_json(META_FILE, all_posts)
    save_json(PROCESSED_FILE, sorted(processed_ids))
    generate_visit_pages(all_visits, all_posts)
    generate_tag_pages(all_posts)
    generate_extra_pages(all_posts)
    generate_redirects(all_posts, all_visits)
    generate_robots()
    generate_cname()
    generate_sitemap(all_posts, all_visits)
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
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8", newline="\n") as f: f.write(render_index(all_posts))
    with open(os.path.join(OUTPUT_DIR, "404.html"), "w", encoding="utf-8", newline="\n") as f: f.write(render_404())
    with open(os.path.join(OUTPUT_DIR, "privacy.html"), "w", encoding="utf-8", newline="\n") as f: f.write(render_privacy())
    with open(os.path.join(OUTPUT_DIR, "auth.html"), "w", encoding="utf-8", newline="\n") as f: f.write(render_auth_page())
    save_image_sizes()
    logger.info(f"Новых постов: {len(accepted)}. Всего: {len(all_posts)}")
    push_to_github()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: logger.info("Прервано")
    except Exception as e: logger.error(f"Критическая ошибка: {e}", exc_info=True)