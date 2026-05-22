"""
Сборка сайта-галереи из Telegram-канала Old Picture Art.

Формат поста в канале:
  Художник ⸻ Название, год ⸻ Материал, размеры ⸻ Музей[, доп. примечания]
  [⸻ История картины (опционально, через ⸻)]
  [ссылка]#теги@oldpictureart
"""
import asyncio
import os
import re
import sys
import json
import shutil
import subprocess
from datetime import datetime
from collections import defaultdict
from html import escape as h

from telethon import TelegramClient, connection

# Pillow — для сжатия больших файлов (опционально, если установлен).
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ---------- Чтение .env без внешних зависимостей ----------

def load_dotenv(path: str = ".env") -> None:
    """Подгружает .env в os.environ. Не перезаписывает уже заданные переменные."""
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


# ==================== НАСТРОЙКИ ====================
try:
    API_ID  = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"]
except KeyError as e:
    raise SystemExit(f"❌ В .env не найдена переменная {e}. "
                     f"Пример .env:\nAPI_ID=12345\nAPI_HASH=abcdef0123456789...")

CHANNEL_URL    = "https://t.me/oldpictureart"
OUTPUT_DIR     = "docs"            # GitHub Pages раздаёт из этой папки
IMAGES_DIR     = "docs/images"
META_FILE      = "posts_meta.json"
PROCESSED_FILE = "processed_ids.json"

# Лимиты для сжатия больших картинок (GitHub: soft-limit 50MB, hard-limit 100MB).
MAX_IMAGE_SIZE_MB    = 25      # Файлы больше этого размера будут сжаты.
MAX_IMAGE_DIMENSION  = 2800    # Картинка ужимается до этой стороны (по большей).
JPEG_QUALITY         = 88

PROXY = (
    '138.226.236.46',
    8443,
    'ee5a76b164eadb451a845bfae212bf8649706574726f766963682e7275'
)
# ===================================================


# ---------- ПАРСИНГ ПОСТА ----------

SEPARATOR_RE = re.compile(r"\s*[⸻⸺]\s*")
URL_RE       = re.compile(r"https?://\S+")
TAG_RE       = re.compile(r"#([\w]+)(?:@\w+)?")

# Имя художника: 2–5 слов, каждое с заглавной (кириллица/латиница),
# либо служебная частица (van/de/von/да/ле/фон/ди/del/della и т.п.) с маленькой.
_NAME_WORD = (r"(?:[А-ЯЁA-Z][а-яёa-zA-Z'\-]+"
              r"|van|de|von|да|ле|ла|дю|фон|ди|del|della|der|den|ten|te|af|y|и"
              r"|el|al|ibn|bin|ben|mac|mc|Ó|O')")
NAME_RE = re.compile(rf"^(?:{_NAME_WORD})(?:\s+{_NAME_WORD}){{1,6}}$")

def parse_post(text: str) -> dict:
    """Раскладывает текст поста по полям.

    Структура: художник ⸻ название ⸻ техника ⸻ музей [⸻ история...].
    Всё, что идёт после музея через ⸻, считается историей провенанса.
    """
    if not text:
        return {}

    # Защита от служебных постов (список хештегов, реклама, анонсы).
    # Если в тексте нет фирменного длинного тире, это не картина!
    if not SEPARATOR_RE.search(text):
        return {}

    raw_tags = TAG_RE.findall(text)
    text_no_tags = TAG_RE.sub("", text).strip()

    url_match = URL_RE.search(text_no_tags)
    url = url_match.group(0) if url_match else ""
    if url_match:
        text_no_tags = (text_no_tags[:url_match.start()]
                        + " "
                        + text_no_tags[url_match.end():])

    parts = [p.strip() for p in SEPARATOR_RE.split(text_no_tags) if p.strip()]

    artist = parts[0] if parts else ""
    title  = parts[1] if len(parts) > 1 else ""
    medium = parts[2] if len(parts) > 2 else ""

    # parts[3] — это музей. Он может содержать перенос строки,
    # после которого уже начинается история провенанса.
    museum = ""
    history_lines: list[str] = []

    if len(parts) > 3:
        museum_raw = parts[3]
        museum_chunks = [l.strip() for l in museum_raw.split("\n") if l.strip()]
        museum = museum_chunks[0] if museum_chunks else ""
        # Всё что после первой строки внутри parts[3] — уже история
        if len(museum_chunks) > 1:
            history_lines.extend(museum_chunks[1:])

    # parts[4], parts[5], ... — продолжение истории, разделённое ⸻
    if len(parts) > 4:
        history_lines.extend(parts[4:])

    history = " ⸻ ".join(history_lines) if history_lines else ""

    return {
        "artist":  artist,
        "title":   title,
        "medium":  medium,
        "museum":  museum,
        "history": history,
        "url":     url,
        "tags":    sorted(set(raw_tags)),
        "raw":     text,
    }

# ---------- УТИЛИТЫ ----------

def slugify(text: str) -> str:
    """Имя для URL. Оставляем кириллицу — GitHub Pages с ней работает."""
    t = text.lower()
    # Убираем всё кроме букв, цифр, пробелов и дефисов (\w в Python работает с юникодом)
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
    """Если файл больше MAX_IMAGE_SIZE_MB, сжимает его (через Pillow).
    Возвращает фактический путь к файлу (может измениться на .jpg)."""
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
        print(f"    🗜  Сжато: {size_mb:.1f}MB → {new_mb:.1f}MB ({os.path.basename(new_path)})")
        return new_path
    except Exception as e:
        print(f"    ⚠️ Не удалось сжать {filepath}: {e}")
        return filepath


# ---------- СКАЧИВАНИЕ ----------

async def download_images(client, group, comments, post_slug):
    images = []
    hires = []

    # 1. Скачиваем обычные сжатые фото из самого поста
    for i, msg in enumerate(group, 1):
        if getattr(msg, "photo", None):
            filename = f"{post_slug}-{i}.jpg"
            filepath = os.path.join(IMAGES_DIR, filename)
            if not os.path.exists(filepath):
                await client.download_media(msg, filepath)
            images.append(f"images/{filename}")

    # 2. Собираем документы-картинки (из комментариев, и на всякий случай из поста)
    all_docs = [m for m in group if getattr(m, "document", None) and m.document.mime_type.startswith("image/")]
    all_docs.extend(comments)

    for i, msg in enumerate(all_docs, 1):
        ext = ".jpg"
        # Пытаемся достать оригинальное расширение файла
        for attr in getattr(msg.document, "attributes", []):
            if hasattr(attr, 'file_name'):
                ext = os.path.splitext(attr.file_name)[1].lower()
                break

        filename = f"{post_slug}-hires-{i}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            try:
                await client.download_media(msg, filepath)
            except Exception as e:
                print(f"    ⚠️ Не скачался оригинал {msg.id}: {e}")
                continue

        # Сжимаем, если файл получился слишком большим для GitHub
        filepath = compress_if_huge(filepath)
        hires.append(f"images/{os.path.basename(filepath)}")

    # Если сжатой картинки почему-то нет, используем оригинал для показа
    if not images and hires:
        images = hires.copy()

    return images, hires

# ---------- HTML ----------

def render_post_page(post: dict) -> str:
    artist = h(post["artist"]); title = h(post["title"])
    medium = h(post["medium"]); museum = h(post["museum"])
    url    = post["url"]

    # Обратная совместимость со старыми записями в posts_meta.json (поле note вместо history)
    history = post.get("history") or post.get("note") or ""

    # Картинка кликается → открывается оригинал в новой вкладке
    img_html_parts = []
    hires_list = post.get("hires", [])

    for i, src in enumerate(post["images"]):
        link_href = hires_list[i] if i < len(hires_list) else src
        img_html_parts.append(
            f'<a href="{h(link_href)}" target="_blank" title="Нажмите, чтобы открыть оригинал">'
            f'<img src="{h(src)}" alt="{artist} — {title}" class="painting" loading="lazy">'
            f'</a>'
        )
    img_html = "\n".join(img_html_parts)

    tags_html = ""
    if post["tags"]:
        tags_html = '<div class="tags">' + " ".join(
            f'<a href="tag-{h(t)}.html" class="tag">#{h(t)}</a>' for t in post["tags"]
        ) + "</div>"

    source_html = (f'<p class="source">Источник: '
                   f'<a href="{h(url)}" target="_blank" rel="noopener">{h(url)}</a></p>'
                   if url else "")

    # Блок истории провенанса. Делим обратно по " ⸻ " чтобы каждый этап стал отдельной строкой
    history_html = ""
    if history:
        parts_h = [p.strip() for p in history.split("⸻") if p.strip()]
        items = "".join(f"<li>{h(p)}</li>" for p in parts_h)
        history_html = (
            '<section class="history">'
            '<h3>История картины</h3>'
            f'<ul>{items}</ul>'
            '</section>'
        )

    return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{artist} — {title}</title>
<style>
body{{max-width:900px;margin:0 auto;padding:1.5rem;
     font-family:Georgia,serif;background:#fafafa;color:#222;line-height:1.55;
     overflow-wrap:break-word}}
.painting{{max-width:100%;max-height:70vh;width:auto;display:block;
          margin:1.5rem auto;box-shadow:0 4px 20px rgba(0,0,0,.15);
          transition:transform .2s ease,box-shadow .2s ease;cursor:zoom-in}}
.painting:hover{{transform:translateY(-2px) scale(1.01);box-shadow:0 8px 25px rgba(0,0,0,.25)}}
h1{{font-size:1.8rem;margin:0 0 .3rem;font-weight:bold}}
h2{{font-size:1.25rem;font-style:italic;font-weight:normal;color:#555;margin:0 0 1rem}}
.medium,.museum,.source{{margin:.3rem 0;color:#555}}
.museum{{font-style:italic}}
.source a{{word-break:break-all;color:#0366d6}}

/* Блок истории провенанса */
.history{{margin:1.8rem 0;padding:1rem 1.25rem;background:#f3eedb;
         border-left:3px solid #b8a86a;border-radius:4px}}
.history h3{{margin:0 0 .6rem;font-size:1rem;color:#5a4f2a;font-weight:bold}}
.history ul{{margin:0;padding-left:1.2rem}}
.history li{{margin:.35rem 0;color:#4a4a4a;font-size:.95rem}}

.tags{{margin-top:1.5rem;padding-top:1rem;border-top:1px solid #ddd;
     display:flex;flex-wrap:wrap;gap:.4rem}}
.tag{{display:inline-block;background:#eee;color:#555;text-decoration:none;
     padding:.3rem .7rem;border-radius:4px;font-size:.85rem}}
.tag:hover{{background:#ddd}}
.back{{display:inline-block;margin-bottom:1rem;color:#666;text-decoration:none}}
time{{color:#999;font-size:.85rem}}

@media (max-width: 600px) {{
  body{{padding:1rem;overflow-x:hidden}}
  h1{{font-size:1.5rem}}
  h2{{font-size:1.15rem}}
  .painting{{margin:1rem auto;max-height:60vh}}
}}
</style></head><body>
<a href="index.html" class="back">← На главную</a>
<article>
<h1>{artist}</h1>
<h2>{title}</h2>
{img_html}
<p class="medium">{medium}</p>
<p class="museum">{museum}</p>
{history_html}
{source_html}
<time>{h(post['date'])}</time>
{tags_html}
</article></body></html>"""

def render_index(all_posts) -> str:
    # Словарь для красивого отображения месяцев
    MONTHS = {
        "01": "Январь", "02": "Февраль", "03": "Март", "04": "Апрель",
        "05": "Май", "06": "Июнь", "07": "Июль", "08": "Август",
        "09": "Сентябрь", "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь"
    }

    posts_sorted = sorted(all_posts, key=lambda x: x["date"], reverse=True)

    # 1. СОБИРАЕМ ДАННЫЕ ДЛЯ МЕНЮ
    # Уникальные авторы по алфавиту
    authors = sorted({p["artist"] for p in all_posts if p.get("artist")})

    # Группировка по годам и месяцам
    archive = defaultdict(set)
    for p in all_posts:
        if p.get("date") and "-" in p["date"]:
            year, month, _ = p["date"].split("-")
            archive[year].add(month)

    archive_sorted = {
        y: sorted(list(ms), reverse=True)
        for y, ms in sorted(archive.items(), reverse=True)
    }

    # 2. ГЕНЕРИРУЕМ КАРТОЧКИ С DATA-АТРИБУТАМИ
    cards = []
    for p in posts_sorted:
        cover = h(p["images"][0]) if p.get("images") else ""
        year, month = "", ""
        if p.get("date") and "-" in p["date"]:
            year, month, _ = p["date"].split("-")

        cards.append(f"""
        <a class="card" href="{h(p['filename'])}"
           data-artist="{h(p['artist'].lower())}"
           data-year="{year}"
           data-month="{month}">
          <div class="card-img" style="background-image:url('{cover}')"></div>
          <div class="card-body">
            <div class="card-artist">{h(p['artist'])}</div>
            <div class="card-title">{h(p['title'])}</div>
          </div>
        </a>""")

    # 3. ГЕНЕРИРУЕМ HTML САЙДБАРА
    authors_html = "".join(
        f'<li><a href="#" class="filter-link" data-type="artist" data-val="{h(a.lower())}">{h(a)}</a></li>'
        for a in authors
    )

    archive_html = ""
    for y, ms in archive_sorted.items():
        archive_html += f'<li><a href="#" class="filter-link" data-type="year" data-val="{y}"><b>{y} год</b></a><ul class="month-list">'
        for m in ms:
            m_name = MONTHS.get(m, m)
            archive_html += f'<li><a href="#" class="filter-link" data-type="month" data-year="{y}" data-val="{m}">{m_name}</a></li>'
        archive_html += '</ul></li>'

    return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Old Picture Art — Галерея</title>
<style>
*{{box-sizing:border-box}}
body{{max-width:1400px;margin:0 auto;padding:1.5rem;
     font-family:Georgia,serif;background:#fafafa;color:#222}}
header{{margin-bottom:2rem;text-align:center}}
h1{{font-size:2.2rem;margin:0 0 .5rem}}
.subtitle{{color:#777;margin-bottom:1.5rem}}
.search-box{{width:100%;max-width:500px;padding:.8rem 1rem;font-size:1rem;
            border:1px solid #ccc;border-radius:6px;font-family:inherit}}

.layout{{display:flex;gap:2rem;align-items:flex-start}}
.sidebar{{width:280px;flex-shrink:0;background:#fff;padding:1.5rem;
        border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,.08);
        position:sticky;top:1.5rem;max-height:calc(100vh - 3rem);overflow-y:auto}}
.sidebar::-webkit-scrollbar{{width:6px}}
.sidebar::-webkit-scrollbar-thumb{{background-color:#ccc;border-radius:3px}}
.sidebar-section{{margin-bottom:2rem}}
.sidebar-title{{font-size:1.1rem;font-weight:bold;margin:0 0 1rem;
              border-bottom:1px solid #eee;padding-bottom:.5rem}}
.sidebar ul{{list-style:none;padding:0;margin:0}}
.sidebar li{{margin-bottom:.5rem}}
.sidebar a{{text-decoration:none;color:#555;font-size:.95rem;display:block;transition:color .15s}}
.sidebar a:hover{{color:#000}}
.sidebar a.active{{color:#0366d6;font-weight:bold}}
.month-list{{padding-left:1.2rem !important;margin-top:.5rem !important;font-size:.95em}}

.filter-reset{{display:none;margin-bottom:1.5rem;color:#d73a49 !important;
             font-weight:bold;text-align:center;background:#ffeef0;
             padding:.6rem;border-radius:4px}}
.filter-reset:hover{{background:#ffdce0}}

.main-content{{flex-grow:1;min-width:0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1.5rem}}
.card{{background:#fff;text-decoration:none;color:inherit;border-radius:6px;
      overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,.08);transition:transform .15s,box-shadow .15s}}
.card:hover{{transform:translateY(-3px);box-shadow:0 6px 18px rgba(0,0,0,.15)}}
.card-img{{width:100%;aspect-ratio:4/3;background:#ddd center/cover no-repeat}}
.card-body{{padding:.8rem 1rem 1rem}}
.card-artist{{font-weight:bold;font-size:1rem;line-height:1.2;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-title{{font-style:italic;color:#666;font-size:.9rem;margin-top:.35rem;
            display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}

@media (max-width: 850px) {{
    .layout{{flex-direction:column;gap:1rem}}
    .sidebar{{width:100%;position:static;max-height:350px}}
    .grid{{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:1rem}}
}}
</style></head><body>
<header>
<h1>Old Picture Art</h1>
<div class="subtitle">Картин в коллекции: {len(posts_sorted)}</div>
<input type="text" class="search-box" placeholder="Поиск по художнику или картине…" id="search">
</header>

<div class="layout">
  <aside class="sidebar">
    <a href="#" id="reset-filter" class="filter-reset">✕ Сбросить фильтр</a>
    <div class="sidebar-section">
      <div class="sidebar-title">Архив</div>
      <ul>{archive_html}</ul>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-title">Художники (А-Я)</div>
      <ul>{authors_html}</ul>
    </div>
  </aside>

  <main class="main-content">
    <div class="grid" id="cards">{''.join(cards)}</div>
  </main>
</div>

<script>
const searchInput = document.getElementById('search');
const cards = document.querySelectorAll('.card');
const filterLinks = document.querySelectorAll('.filter-link');
const resetBtn = document.getElementById('reset-filter');
let activeFilter = {{ type: null, val: null, year: null }};

function updateView() {{
  const q = searchInput.value.toLowerCase();
  cards.forEach(c => {{
    let show = true;
    if (q && !c.textContent.toLowerCase().includes(q)) show = false;
    if (show && activeFilter.type) {{
      if (activeFilter.type === 'artist' && c.dataset.artist !== activeFilter.val) show = false;
      if (activeFilter.type === 'year' && c.dataset.year !== activeFilter.val) show = false;
      if (activeFilter.type === 'month' && (c.dataset.year !== activeFilter.year || c.dataset.month !== activeFilter.val)) show = false;
    }}
    c.style.display = show ? '' : 'none';
  }});
  filterLinks.forEach(link => {{
    let isActive = false;
    if (activeFilter.type === link.dataset.type) {{
      if (activeFilter.type === 'month') {{
        isActive = (link.dataset.val === activeFilter.val && link.dataset.year === activeFilter.year);
      }} else {{
        isActive = (link.dataset.val === activeFilter.val);
      }}
    }}
    link.classList.toggle('active', isActive);
  }});
  resetBtn.style.display = activeFilter.type ? 'block' : 'none';
}}

searchInput.addEventListener('input', updateView);
filterLinks.forEach(link => {{
  link.addEventListener('click', e => {{
    e.preventDefault();
    activeFilter.type = link.dataset.type;
    activeFilter.val = link.dataset.val;
    if (activeFilter.type === 'month') activeFilter.year = link.dataset.year;
    updateView();
  }});
}});
resetBtn.addEventListener('click', e => {{
  e.preventDefault();
  activeFilter = {{ type: null, val: null, year: null }};
  updateView();
}});
</script></body></html>"""


# ---------- TELEGRAM ----------

async def fetch_new_posts(client, processed_ids):
    print("📥 Сканирую канал (ищу новые альбомы)…")
    accepted = []

    def _process_group(group):
        # iter_messages отдаёт посты от новых к старым (задом наперёд).
        # Разворачиваем альбом, чтобы первая картинка стала обложкой на сайте.
        group.reverse()

        full_text = ""
        main_msg = None
        for m in group:
            text = m.raw_text or ""
            if text:
                full_text += text + "\n"
            if "#картина" in text.lower():
                main_msg = m

        if not main_msg or "#картина@oldpictureart" not in full_text.lower():
            return
        if main_msg.id in processed_ids:
            return

        parsed = parse_post(full_text)
        if not parsed:
            return
        accepted.append((main_msg, group, parsed))

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

    print(f"   Найдено новых постов: {len(accepted)}")
    return accepted[::-1]

# ---------- GITHUB ----------

def push_to_github():
    print("\n📤 Отправляю на GitHub…")
    try:
        subprocess.run(["git", "add", "."], check=False)
        status = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True)
        if not status.stdout.strip():
            print("   ℹ️ Нет изменений."); return
        subprocess.run(["git", "commit", "-m",
                        f"Авто-обновление: {datetime.now():%Y-%m-%d %H:%M}"], check=False)
        subprocess.run(["git", "push"], check=False)
        print("   ✅ Готово")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")


# ---------- MAIN ----------

def rebuild_reset():
    """Полная перегенерация: чистит html и состояние, картинки в docs/images/ оставляет."""
    print("⚠️  Режим --rebuild: удалю старые html-страницы и историю обработки.")
    print("   Папка docs/images/ НЕ трогается — уже скачанные картинки сохранятся.")
    answer = input("   Продолжить? [y/N]: ").strip().lower()
    if answer not in ("y", "yes", "д", "да"):
        print("   Отмена.")
        sys.exit(0)

    if os.path.isdir(OUTPUT_DIR):
        removed = 0
        for name in os.listdir(OUTPUT_DIR):
            if name.endswith(".html"):
                os.remove(os.path.join(OUTPUT_DIR, name))
                removed += 1
        print(f"   Удалено html-файлов: {removed}")

    for fn in (PROCESSED_FILE, META_FILE):
        if os.path.exists(fn):
            os.remove(fn)
            print(f"   Удалён {fn}")


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
        print("ℹ️  Pillow не установлен — крупные оригиналы не будут автоматически сжиматься.")
        print("    Если нужны hires-картинки: pip install Pillow")

    processed_ids = set(load_json(PROCESSED_FILE, []))
    all_posts     = load_json(META_FILE, [])

    print("📡 Подключаюсь к Telegram…")
    client = TelegramClient(
        "my_session", api_id=API_ID, api_hash=API_HASH,
        connection=connection.ConnectionTcpMTProxyRandomizedIntermediate,
        proxy=PROXY,
    )
    await client.start()

    accepted = await fetch_new_posts(client, processed_ids)

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

        print(f"📝 [{i}/{len(accepted)}] {parsed['artist']} — {parsed['title'][:50]}")

        # Ищем картинки-документы в комментариях
        comments = []
        if getattr(main_msg, "replies", None) and main_msg.replies.replies > 0:
            try:
                async for reply in client.iter_messages(CHANNEL_URL, reply_to=main_msg.id):
                    if getattr(reply, "document", None) and reply.document.mime_type.startswith("image/"):
                        comments.append(reply)
            except Exception as e:
                print(f"    ⚠️ Не удалось проверить комментарии: {e}")

        image_slug = filename[:-5]
        images, hires = await download_images(client, group, comments, image_slug)

        post = {"id": main_msg.id, "date": date, "filename": filename,
                "images": images, "hires": hires, **parsed}

        with open(os.path.join(OUTPUT_DIR, filename), "w", encoding="utf-8") as f:
            f.write(render_post_page(post))

        all_posts.append(post)
        processed_ids.update(m.id for m in group)

    await client.disconnect()

    save_json(META_FILE, all_posts)
    save_json(PROCESSED_FILE, sorted(processed_ids))

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(all_posts))

    print(f"\n✨ Новых постов: {len(accepted)}. Всего на сайте: {len(all_posts)}")
    push_to_github()


if __name__ == "__main__":
    asyncio.run(main())