"""
Генератор карты музеев для Old Picture Art.
Автоматически находит координаты через OpenStreetMap Nominatim API.
Запуск: python generate_map.py
"""

import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from collections import defaultdict
from html import escape as h
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

META_FILE = "posts_meta.json"
OUTPUT_DIR = "docs"
CACHE_FILE = "museum_coordinates.json"  # Кэш координат, чтобы не запрашивать повторно


def geocode(museum_name, cache):
    """Ищет координаты музея через Nominatim API."""
    
    # Проверяем кэш
    if museum_name in cache:
        logger.info(f"  ✓ (из кэша) {museum_name}")
        return cache[museum_name]
    
    # Формируем запрос
    params = {
        'q': museum_name,
        'format': 'json',
        'limit': 1,
        'accept-language': 'ru'
    }
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(params)
    
    try:
        # Nominatim требует User-Agent
        req = urllib.request.Request(url, headers={'User-Agent': 'OldPictureArt/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        if data:
            result = {
                'lat': float(data[0]['lat']),
                'lon': float(data[0]['lon']),
                'display_name': data[0].get('display_name', museum_name)
            }
            # Сохраняем в кэш
            cache[museum_name] = result
            logger.info(f"  ✓ {museum_name} → {result['lat']:.4f}, {result['lon']:.4f}")
            # Пауза, чтобы не нагружать API (1 запрос в секунду)
            time.sleep(1.1)
            return result
        else:
            logger.warning(f"  ✗ Не найдено: {museum_name}")
            cache[museum_name] = None
            time.sleep(1.1)
            return None
            
    except Exception as e:
        logger.error(f"  ✗ Ошибка для {museum_name}: {e}")
        time.sleep(2)
        return None


def slugify(text):
    """Создаёт slug из текста."""
    import re
    t = text.lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t).strip("-")
    return t[:60] or "post"


def extract_city_country(display_name):
    """Извлекает город и страну из полного адреса Nominatim."""
    parts = [p.strip() for p in display_name.split(',')]
    if len(parts) >= 2:
        city = parts[0]
        country = parts[-1]
    else:
        city = ""
        country = ""
    return city, country


def generate_museums_page():
    """Генерирует страницу с картой музеев."""
    
    # Загружаем посты
    if not os.path.exists(META_FILE):
        logger.error(f"Файл {META_FILE} не найден! Сначала запустите build_site.py")
        return
    
    with open(META_FILE, "r", encoding="utf-8") as f:
        all_posts = json.load(f)
    
    logger.info(f"Загружено {len(all_posts)} постов")
    
    # Группируем по музеям
    museums_dict = defaultdict(list)
    for p in all_posts:
        museum = p.get("museum", "")
        if museum:
            museums_dict[museum].append(p)
    
    logger.info(f"Найдено {len(museums_dict)} музеев")
    
    # Загружаем кэш координат
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        logger.info(f"Загружен кэш координат ({len(cache)} записей)")
    
    # Ищем координаты
    logger.info("🔍 Поиск координат музеев...")
    locations = {}
    for museum in sorted(museums_dict.keys()):
        result = geocode(museum, cache)
        if result:
            city, country = extract_city_country(result.get('display_name', museum))
            locations[museum] = {
                'lat': result['lat'],
                'lon': result['lon'],
                'city': city,
                'country': country
            }
    
    # Сохраняем обновлённый кэш
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    logger.info(f"Кэш сохранён ({len(cache)} записей)")
    
    # Генерируем карточки музеев и маркеры
    museum_list = []
    markers_js = []
    found_locations = 0
    
    for museum, posts in sorted(museums_dict.items()):
        loc = locations.get(museum, {})
        city = loc.get('city', '')
        country = loc.get('country', '')
        lat = loc.get('lat')
        lon = loc.get('lon')
        
        if lat and lon:
            found_locations += 1
        
        # Карточка музея
        posts_links = ""
        for p in posts[:5]:
            posts_links += f'<li><a href="{h(p["filename"])}">{h(p["artist"])} — {h(p["title"])}</a></li>'
        
        more = f'<li>... и ещё {len(posts)-5}</li>' if len(posts) > 5 else ""
        
        location_html = ""
        if city:
            location_html = f'<p class="museum-location">📍 {h(city)}{", " if city and country else ""}{h(country)}</p>'
        
        museum_list.append(f"""
        <div class="museum-card" id="museum-{h(slugify(museum))}">
          <h3>🏛 {h(museum)}</h3>
          {location_html}
          <p class="museum-count">{len(posts)} картин(ы)</p>
          <ul>{posts_links}{more}</ul>
        </div>""")
        
        # Маркер для карты
        if lat and lon:
            markers_js.append(
                f"L.marker([{lat}, {lon}]).addTo(map)"
                f".bindPopup('<b>{h(museum)}</b><br>{h(city)}, {h(country)}<br>{len(posts)} картин(ы)');"
            )
    
    # Предупреждение о музеях без координат
    missing = len(museums_dict) - found_locations
    if missing > 0:
        logger.warning(f"⚠️ {missing} музеев не найдено на карте")
    
    all_markers = "\n            ".join(markers_js)
    
    # Собираем HTML
    html = f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a2e" media="(prefers-color-scheme: dark)">
<title>🗺 Карта музеев — Old Picture Art</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<link rel="stylesheet" href="style.css">
<style>
#map {{ height: 500px; border-radius: 8px; margin-bottom: 2rem; border: 1px solid var(--border); z-index: 1; }}
.museum-location {{ color: var(--muted); font-size: .85rem; margin: .2rem 0; }}
.museum-count {{ color: var(--active); font-weight: 600; font-size: .9rem; }}
@media (max-width: 768px) {{ #map {{ height: 350px; }} }}
</style>
</head><body>
<button class="theme-toggle" onclick="toggleTheme()">🌓</button>
<a href="index.html" class="back" style="padding:1rem;display:inline-block">← На главную</a>
<h1 style="text-align:center">🗺 Карта музеев</h1>
<p style="text-align:center;color:var(--muted)">{len(museums_dict)} музеев в коллекции ({found_locations} на карте)</p>
<div style="max-width:1200px;margin:0 auto;padding:0 1.5rem">
  <div id="map"></div>
</div>
<div class="museums-grid">{''.join(museum_list)}</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
function toggleTheme(){{const h=document.documentElement;const c=h.getAttribute('data-theme');const n=c==='light'?'dark':'light';h.setAttribute('data-theme',n);localStorage.setItem('theme',n)}}
(()=>{{const s=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',s)}})();

const map = L.map('map').setView([50, 10], 3);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 18
}}).addTo(map);

{all_markers}

// Автоматически показываем все маркеры
const markers = [];
map.eachLayer(function(layer) {{
    if (layer instanceof L.Marker) markers.push(layer);
}});
if (markers.length > 0) {{
    const group = new L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.1));
}}
</script>
</body></html>"""
    
    # Сохраняем
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "museums.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    logger.info(f"✅ Карта музеев сохранена: {output_path}")
    logger.info(f"   Всего музеев: {len(museums_dict)}")
    logger.info(f"   На карте: {found_locations}")
    logger.info(f"   Не найдено: {missing}")


if __name__ == "__main__":
    generate_museums_page()
    print("\n✨ Готово! Откройте docs/museums.html в браузере.")