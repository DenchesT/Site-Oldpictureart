# -*- coding: utf-8 -*-
"""Пути, размеры картинок, канал и доступ к Telegram (.env).

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os

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

# ---------------------------------------------------------- карточка ссылки
#
# Когда ссылку на картину кидают в мессенджер, превью берёт og:image. Раньше
# это была сама картина — красиво, но безымянно: кто автор и что это, видно
# только если открыть. Карточка добавляет к картине подпись, набранную теми же
# цветами, что и сайт.
CARD_DIR = "docs/images/cards"


SIZES_FILE = "image_sizes.json"

__all__ = [
    'load_dotenv',
    'API_ID',
    'API_HASH',
    'PHONE',
    'CHANNEL_URL',
    'OUTPUT_DIR',
    'IMAGES_DIR',
    'META_FILE',
    'PROCESSED_FILE',
    'DICTIONARY_FILE',
    'MAX_IMAGE_SIZE_MB',
    'MAX_IMAGE_DIMENSION',
    'JPEG_QUALITY',
    'THUMB_DIR',
    'THUMB_DIMENSION',
    'THUMB_QUALITY',
    'VIEW_DIR',
    'VIEW_DIMENSION',
    'VIEW_QUALITY',
    'PROXY_LIST',
    'CARD_DIR',
    'SIZES_FILE',
]
