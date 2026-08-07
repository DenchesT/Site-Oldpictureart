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
CACHE_FILE = "museum_coordinates.json"


def geocode(museum_name, cache):
    """Ищет координаты музея через Nominatim API."""
    if museum_name in cache:
        logger.info(f"  ✓ (из кэша) {museum_name}")
        return cache[museum_name]
    
    params = {
        'q': museum_name,
        'format': 'json',
        'limit': 1,
        'accept-language': 'ru'
    }
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(params)
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OldPictureArt/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        if data:
            result = {
                'lat': float(data[0]['lat']),
                'lon': float(data[0]['lon']),
                'display_name': data[0].get('display_name', museum_name)
            }
            cache[museum_name] = result
            logger.info(f"  ✓ {museum_name} → {result['lat']:.4f}, {result['lon']:.4f}")
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
    import re
    t = text.lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t).strip("-")
    return t[:60] or "post"

def plural_ru(n, one, two, five):
    """Склоняет существительное: 1 картина, 2 картины, 5 картин"""
    n = abs(n) % 100
    if 11 <= n <= 19: return five
    n = n % 10
    if n == 1: return one
    if 2 <= n <= 4: return two
    return five

def extract_city_country(display_name):
    parts = [p.strip() for p in display_name.split(',')]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return "", ""


def generate_museums_page():
    if not os.path.exists(META_FILE):
        logger.error(f"Файл {META_FILE} не найден!")
        return
    
    with open(META_FILE, "r", encoding="utf-8") as f:
        all_posts = json.load(f)
    
    logger.info(f"Загружено {len(all_posts)} постов")
    
    museums_dict = defaultdict(list)
    for p in all_posts:
        museum = p.get("museum", "")
        if museum:
            museums_dict[museum].append(p)
    
    logger.info(f"Найдено {len(museums_dict)} музеев")
    
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    
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
    
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    
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
        
        museum_id = slugify(museum)
        
        # Все картины (скрытые, если >5)
        all_posts_html = ""
        for p in posts:
            all_posts_html += f'<li><a href="{h(p["filename"])}">{h(p["artist"])} — {h(p["title"])}</a></li>'
        
        show_more_btn = ""
        hidden_class = ""
# Формируем HTML для списка картин
        if len(posts) > 5:
            visible_posts = posts[:5]
            hidden_posts = posts[5:]
            
            visible_html = "".join([f'<li><a href="{h(p["filename"])}">{h(p["artist"])} — {h(p["title"])}</a></li>' for p in visible_posts])
            hidden_html = "".join([f'<li><a href="{h(p["filename"])}">{h(p["artist"])} — {h(p["title"])}</a></li>' for p in hidden_posts])
            
            show_more_btn = f'<button class="show-more-btn" onclick="toggleMuseumPosts(\'{museum_id}\')">Показать все {len(posts)} {plural_ru(len(posts), "картину", "картины", "картин")} ▾</button>'
            hidden_class = 'hidden-posts'
        else:
            visible_html = "".join([f'<li><a href="{h(p["filename"])}">{h(p["artist"])} — {h(p["title"])}</a></li>' for p in posts])
            hidden_html = ""
            show_more_btn = ""
            hidden_class = ""
        
        location_html = ""
        if city:
            location_html = f'<p class="museum-location">📍 {h(city)}{", " if city and country else ""}{h(country)}</p>'
        
        museum_list.append(f"""
        <div class="museum-card" id="museum-{museum_id}">
          <h3>🏛 {h(museum)}</h3>
          {location_html}
          <p class="museum-count">{len(posts)} {plural_ru(len(posts), 'картина', 'картины', 'картин')}</p>
          <ul class="museum-posts-list">
            {visible_html}
          </ul>
          <div class="{hidden_class}" id="hidden-{museum_id}" style="display:none">
            <ul class="museum-posts-list">
              {hidden_html}
            </ul>
          </div>
          {show_more_btn}
        </div>""")
        
        # Маркер с ссылкой на карточку музея
        if lat and lon:
            popup_html = f'<b>{h(museum)}</b><br>{h(city)}, {h(country)}<br>{len(posts)} {plural_ru(len(posts), 'картина', 'картины', 'картин')}<br><a href="#museum-{museum_id}" onclick="scrollToMuseum(\'{museum_id}\')" style="color:var(--active)">🔍 Показать в списке</a>'
            markers_js.append(
            f"L.marker([{lat}, {lon}]).addTo(map).bindPopup(`{popup_html}`);"
             )
    
    missing = len(museums_dict) - found_locations
    all_markers = "\n            ".join(markers_js)
    
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
.museum-posts-list {{ margin: .3rem 0; padding-left: 1.2rem; font-size: .85rem; }}
.museum-posts-list li {{ margin-bottom: .15rem; }}
.museum-posts-list a {{ color: var(--link); text-decoration: none; }}
.museum-posts-list a:hover {{ text-decoration: underline; }}
.show-more-btn {{
  background: none; border: 1px solid var(--border); color: var(--link);
  padding: .3rem .8rem; border-radius: 15px; cursor: pointer;
  font-size: .8rem; margin-top: .3rem; transition: all .2s;
  font-family: inherit;
}}
.show-more-btn:hover {{ background: var(--border); }}
@media (max-width: 768px) {{ #map {{ height: 350px; }} }}
</style>
</head><body>
<button class="theme-toggle" onclick="toggleTheme()">🌓</button>
<a href="index.html" class="back" style="padding:1rem;display:inline-block">← На главную</a>
<h1 style="text-align:center">🗺 Карта музеев</h1>
<p style="text-align:center;color:var(--muted)">{len(museums_dict)} {plural_ru(len(museums_dict), 'музей', 'музея', 'музеев')} в коллекции ({found_locations} на карте)</p>
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

const markers = [];
map.eachLayer(function(layer) {{
    if (layer instanceof L.Marker) markers.push(layer);
}});
if (markers.length > 0) {{
    const group = new L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.1));
}}

function scrollToMuseum(id) {{
    const el = document.getElementById('museum-' + id);
    if (el) {{
        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        el.style.boxShadow = '0 0 20px var(--active)';
        setTimeout(function() {{ el.style.boxShadow = ''; }}, 2000);
    }}
}}

function toggleMuseumPosts(id) {{
    const hidden = document.getElementById('hidden-' + id);
    const btn = event.target;
    if (hidden.style.display === 'none' || !hidden.style.display) {{
        hidden.style.display = 'block';
        btn.textContent = 'Свернуть ▴';
    }} else {{
        hidden.style.display = 'none';
        var count = hidden.querySelectorAll('li').length;
btn.textContent = 'Показать все ' + count + ' ' + (count%10==1&&count%100!=11 ? 'картину' : count%10>=2&&count%10<=4&&(count%100<10||count%100>=20) ? 'картины' : 'картин') + ' ▾';
    }}
}}
</script>
</body></html>"""
    
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