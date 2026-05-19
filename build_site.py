"""
Сборка сайта-галереи из Telegram-канала Old Picture Art.

Формат поста в канале:
  Художник ⸻ Название, год ⸻ Материал, размеры ⸻ Музей[ссылка]#теги@oldpictureart
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


def looks_like_artist_name(s: str) -> bool:
    s = s.strip().rstrip(".")
    if not s or len(s) > 100:
        return False
    if "#" in s or "http" in s or "@" in s or "⸻" in s:
        return False
    return bool(NAME_RE.match(s))


def parse_post(text: str) -> dict:
    """Раскладывает текст поста по полям."""
    if not text:
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

    museum_raw = parts[3] if len(parts) > 3 else ""
    museum_lines = [l.strip() for l in museum_raw.split("\n") if l.strip()]
    museum = museum_lines[0] if museum_lines else ""
    note   = " ".join(museum_lines[1:]) if len(museum_lines) > 1 else ""

    return {
        "artist": parts[0] if parts else "",
        "title":  parts[1] if len(parts) > 1 else "",
        "medium": parts[2] if len(parts) > 2 else "",
        "museum": museum,
        "note":   note,
        "url":    url,
        "tags":   sorted(set(raw_tags)),
        "raw":    text,
    }


def has_image(message) -> bool:
    if getattr(message, "photo", None):
        return True
    doc = getattr(message, "document", None)
    if doc and getattr(doc, "mime_type", "").startswith("image/"):
        return True
    return False





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


# ---------- СКАЧИВАНИЕ ----------

async def download_images(client, messages, post_slug):
    paths = []
    image_msgs = [m for m in messages if has_image(m)]
    for i, msg in enumerate(image_msgs, 1):
        suffix = "" if len(image_msgs) == 1 else f"-{i}"
        filename = f"{post_slug}{suffix}.jpg"
        filepath = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            try:
                await client.download_media(msg, filepath)
            except Exception as e:
                print(f"    ⚠️ Не скачалось msg {msg.id}: {e}")
                continue
        paths.append(f"images/{filename}")
    return paths


# ---------- HTML ----------

def render_post_page(post: dict) -> str:
    artist = h(post["artist"]); title = h(post["title"])
    medium = h(post["medium"]); museum = h(post["museum"])
    note   = h(post["note"]);   url    = post["url"]

    img_html = "\n".join(
        f'<img src="{h(src)}" alt="{artist} — {title}" class="painting" loading="lazy">'
        for src in post["images"]
    )
    tags_html = ""
    if post["tags"]:
        tags_html = '<div class="tags">' + " ".join(
            f'<a href="tag-{h(t)}.html" class="tag">#{h(t)}</a>' for t in post["tags"]
        ) + "</div>"
    source_html = (f'<p class="source">Источник: '
                   f'<a href="{h(url)}" target="_blank" rel="noopener">{h(url)}</a></p>'
                   if url else "")
    note_html = f'<p class="note">{note}</p>' if note else ""

    return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{artist} — {title}</title>
<style>
body{{max-width:900px;margin:0 auto;padding:1.5rem;
     font-family:Georgia,serif;background:#fafafa;color:#222;line-height:1.55}}
.painting{{width:100%;max-width:800px;display:block;margin:1.5rem auto;
          box-shadow:0 4px 20px rgba(0,0,0,.15)}}
h1{{font-size:1.8rem;margin:0 0 .3rem}}
h2{{font-size:1.25rem;font-style:italic;font-weight:normal;color:#555;margin:0 0 1rem}}
.medium,.museum,.note,.source{{margin:.3rem 0;color:#555}}
.museum{{font-style:italic}}
.tags{{margin-top:1.5rem;padding-top:1rem;border-top:1px solid #ddd}}
.tag{{display:inline-block;background:#eee;color:#555;text-decoration:none;
     padding:.2rem .6rem;border-radius:4px;margin:.2rem .3rem .2rem 0;font-size:.85rem}}
.tag:hover{{background:#ddd}}
.back{{display:inline-block;margin-bottom:1rem;color:#666;text-decoration:none}}
time{{color:#999;font-size:.85rem}}
</style></head><body>
<a href="index.html" class="back">← На главную</a>
<article>
<h1>{artist}</h1>
<h2>{title}</h2>
{img_html}
<p class="medium">{medium}</p>
<p class="museum">{museum}</p>
{note_html}
{source_html}
<time>{h(post['date'])}</time>
{tags_html}
</article></body></html>"""


def render_index(all_posts) -> str:
    posts_sorted = sorted(all_posts, key=lambda x: x["date"], reverse=True)
    cards = []
    for p in posts_sorted:
        cover = h(p["images"][0]) if p["images"] else ""
        cards.append(f"""
        <a class="card" href="{h(p['filename'])}">
          <div class="card-img" style="background-image:url('{cover}')"></div>
          <div class="card-body">
            <div class="card-artist">{h(p['artist'])}</div>
            <div class="card-title">{h(p['title'])}</div>
          </div>
        </a>""")

    return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Old Picture Art — Галерея</title>
<style>
*{{box-sizing:border-box}}
body{{max-width:1300px;margin:0 auto;padding:1.5rem;
     font-family:Georgia,serif;background:#fafafa;color:#222}}
header{{margin-bottom:2rem;text-align:center}}
h1{{font-size:2.2rem;margin:0 0 .5rem}}
.subtitle{{color:#777;margin-bottom:1.5rem}}
.search-box{{width:100%;max-width:500px;padding:.7rem 1rem;font-size:1rem;
            border:1px solid #ccc;border-radius:6px;font-family:inherit}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:1.5rem}}
.card{{background:#fff;text-decoration:none;color:inherit;border-radius:6px;
      overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,.08);transition:transform .15s,box-shadow .15s}}
.card:hover{{transform:translateY(-3px);box-shadow:0 6px 18px rgba(0,0,0,.15)}}
.card-img{{width:100%;aspect-ratio:4/3;background:#ddd center/cover no-repeat}}
.card-body{{padding:.8rem 1rem 1rem}}
.card-artist{{font-weight:bold;font-size:1rem}}
.card-title{{font-style:italic;color:#666;font-size:.9rem;margin-top:.25rem;
            display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
</style></head><body>
<header>
<h1>🖼 Old Picture Art</h1>
<div class="subtitle">Картин в коллекции: {len(posts_sorted)}</div>
<input type="text" class="search-box" placeholder="Поиск по художнику или картине…" id="search">
</header>
<main><div class="grid" id="cards">{''.join(cards)}</div></main>
<script>
document.getElementById('search').addEventListener('input',e=>{{
  const q=e.target.value.toLowerCase();
  document.querySelectorAll('.card').forEach(c=>{{
    c.style.display=c.textContent.toLowerCase().includes(q)?'':'none';
  }});
}});
</script></body></html>"""


# ---------- TELEGRAM ----------

async def fetch_new_posts(client, processed_ids):
    print("📥 Сканирую канал (только #картина@oldpictureart)…")
    groups = defaultdict(list)
    singles = []
    count = 0
    accepted_count = 0
    
    async for message in client.iter_messages(CHANNEL_URL):
        count += 1
        
        if count % 100 == 0:
            print(f"   Просмотрено: {count}, принято: {accepted_count}")
        
        if message.id in processed_ids:
            continue
        
        text = message.text or message.message or ""
        
        # Фильтр: только посты с хештегом #картина@oldpictureart
        if "#картина@oldpictureart" not in text:
            continue
        
        if getattr(message, "grouped_id", None):
            groups[message.grouped_id].append(message)
        else:
            singles.append(message)
    
    print(f"   Всего просмотрено: {count}, отфильтровано: {accepted_count}")
    
    # Собираем пакеты
    packets = []
    for msgs in groups.values():
        msgs.sort(key=lambda m: m.id)
        main = next((m for m in msgs if (m.text or m.message)), msgs[0])
        packets.append((main, msgs))
    for m in singles:
        packets.append((m, [m]))
    
    # Принимаем все с хештегом (фильтр уже сработал выше)
    accepted = []
    for main, msgs in packets:
        text = main.text or main.message or ""
        parsed = parse_post(text)
        accepted.append((main, msgs, parsed))
        accepted_count += 1
    
    print(f"   Принято постов: {len(accepted)}")
    return accepted


# ---------- GITHUB ----------

def push_to_github():
    print("\n📤 Отправляю на GitHub…")
    try:
        # docs/ уже в нужном месте — GitHub Pages читает прямо оттуда.
        # Просто коммитим всё что изменилось.
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

    # Удаляем все .html в docs/ (включая index.html и страницы постов)
    if os.path.isdir(OUTPUT_DIR):
        removed = 0
        for name in os.listdir(OUTPUT_DIR):
            if name.endswith(".html"):
                os.remove(os.path.join(OUTPUT_DIR, name))
                removed += 1
        print(f"   Удалено html-файлов: {removed}")

    # Сбрасываем состояние
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

    # .nojekyll нужен GitHub Pages, чтобы не пытаться обрабатывать сайт через Jekyll
    nojekyll = os.path.join(OUTPUT_DIR, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()

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

        # Имя файла как у тебя: 2025-02-14-пьер-огюст-ренуар.html
        # Если такое имя уже есть — добавляем -2, -3 и т.д.
        base = f"{date}-{artist_slug}"
        filename = f"{base}.html"
        n = 2
        existing = {p["filename"] for p in all_posts}
        while filename in existing or os.path.exists(os.path.join(OUTPUT_DIR, filename)):
            filename = f"{base}-{n}.html"
            n += 1

        print(f"📝 [{i}/{len(accepted)}] {parsed['artist']} — {parsed['title'][:50]}")

        # Слаг для имён картинок (без расширения)
        image_slug = filename[:-5]
        images = await download_images(client, group, image_slug)

        post = {"id": main_msg.id, "date": date, "filename": filename,
                "images": images, **parsed}

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