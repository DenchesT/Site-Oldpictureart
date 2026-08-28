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

from site_common import head_common, theme_button, scroll_top_button, COMMON_JS, SCROLL_TOP_JS, BASE_URL

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

META_FILE = "posts_meta.json"
OUTPUT_DIR = "docs"
CACHE_FILE = "museum_coordinates.json"


def _nominatim(query):
    """Один запрос к Nominatim. Возвращает результат или None."""
    params = {'q': query, 'format': 'json', 'limit': 1, 'accept-language': 'ru'}
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'OldPictureArt/1.0 (github.com/DenchesT/Site-Oldpictureart)'})
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode())
    time.sleep(1.1)  # правила Nominatim: не чаще 1 запроса в секунду
    if not data:
        return None
    return {
        'lat': float(data[0]['lat']),
        'lon': float(data[0]['lon']),
        'display_name': data[0].get('display_name', query),
    }


def build_queries(museum_name):
    """Варианты запроса от точного к общему.

    Раньше спрашивали Nominatim ровно одной строкой вида
    «Государственный Русский музей, Санкт-Петербург». По таким полным
    названиям геокодер часто не находит ничего — из-за этого 38 музеев
    из 50 не попадали на карту. Пробуем несколько формулировок.
    """
    name = museum_name.strip()
    parts = [p.strip() for p in name.split(',') if p.strip()]
    queries = [name]

    if len(parts) >= 2:
        museum, city = parts[0], parts[-1]
        queries.append(f"{museum} {city}")
        queries.append(museum)
        queries.append(city)          # хотя бы город, чтобы метка была
    elif parts:
        queries.append(parts[0])

    # «Частная коллекция, Швейцария» — музея нет, но страна на карте есть
    seen, out = set(), []
    for q in queries:
        q = q.strip(" ,")
        if len(q) > 2 and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def geocode(museum_name, cache, retry_failed=False):
    """Ищет координаты музея через Nominatim API.

    retry_failed=True заставляет заново спросить те названия, которые раньше
    записались в кэш как null: без этого один неудачный поиск запоминался
    навсегда и музей уже никогда не появлялся на карте.
    """
    if museum_name in cache:
        cached = cache[museum_name]
        if cached or not retry_failed:
            logger.info(f"  ✓ (из кэша) {museum_name}" if cached else f"  – (из кэша, без координат) {museum_name}")
            return cached

    for query in build_queries(museum_name):
        try:
            result = _nominatim(query)
        except Exception as e:
            logger.error(f"  ✗ Ошибка запроса «{query}»: {e}")
            time.sleep(2)
            continue
        if result:
            cache[museum_name] = result
            note = "" if query == museum_name else f" (по запросу «{query}»)"
            logger.info(f"  ✓ {museum_name} → {result['lat']:.4f}, {result['lon']:.4f}{note}")
            return result

    logger.warning(f"  ✗ Не найдено: {museum_name}")
    cache[museum_name] = None
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


def generate_museums_page(retry_failed=False):
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
    if retry_failed:
        logger.info("   (режим --regeocode: заново ищем музеи без координат)")
    locations = {}
    for museum in sorted(museums_dict.keys()):
        result = geocode(museum, cache, retry_failed=retry_failed)
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
            
            show_more_btn = (f'<button type="button" class="show-more-btn" aria-expanded="false" '
                             f'aria-controls="hidden-{museum_id}" '
                             f'onclick="toggleMuseumPosts(this, \'{museum_id}\')">Показать все {len(posts)} '
                             f'{plural_ru(len(posts), "картину", "картины", "картин")} ▾</button>')
            hidden_class = 'hidden-posts'
        else:
            visible_html = "".join([f'<li><a href="{h(p["filename"])}">{h(p["artist"])} — {h(p["title"])}</a></li>' for p in posts])
            hidden_html = ""
            show_more_btn = ""
            hidden_class = ""
        
        location_html = ""
        if city:
            location_html = f'<p class="museum-location"><span class="icon-location"></span> {h(city)}{", " if city and country else ""}{h(country)}</p>'
        
        museum_list.append(f"""
        <div class="museum-card" id="museum-{museum_id}">
          <h3><span class="icon-museum-small" aria-hidden="true"></span> {h(museum)}</h3>
          {location_html}
          <p class="museum-count">{len(posts)} {plural_ru(len(posts), 'картина', 'картины', 'картин')}</p>
          <ul class="museum-posts-list">
            {visible_html}
          </ul>
          <div class="{hidden_class}" id="hidden-{museum_id}" hidden>
            <ul class="museum-posts-list">
              {hidden_html}
            </ul>
          </div>
          {show_more_btn}
        </div>""")
        
        # Маркер с ссылкой на карточку музея
        if lat and lon:
            popup_html = (f'<b>{h(museum)}</b><br>{h(city)}, {h(country)}<br>'
                          f'{len(posts)} {plural_ru(len(posts), "картина", "картины", "картин")}<br>'
                          f'<a href="#museum-{museum_id}" onclick="scrollToMuseum(\'{museum_id}\')" class="popup-link">'
                          f'<span class="icon-search-small" aria-hidden="true"></span> Показать в списке</a>')
            markers_js.append(
            f"L.marker([{lat}, {lon}]).addTo(map).bindPopup(`{popup_html}`);"
             )
    
    missing = len(museums_dict) - found_locations
    all_markers = "\n            ".join(markers_js)
    
    head = head_common(
        title="Карта музеев — Old Picture Art",
        description=f"{len(museums_dict)} музеев из коллекции Old Picture Art на карте мира.",
        canonical=f"{BASE_URL}/museums.html",
        extra='\n<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" '
              'integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin>',
    )

    html = f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
{head}
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
.map-topbar {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; padding: .6rem 1.5rem; }}
.map-wrap {{ max-width: 1200px; margin: 0 auto; padding: 0 1.5rem; }}
.map-fallback {{ padding: 1rem; text-align: center; color: var(--muted); }}
@media (max-width: 768px) {{ #map {{ height: 350px; }} .map-wrap {{ padding: 0 .8rem; }} .map-topbar {{ padding: .6rem .8rem; }} }}
</style>
</head><body class="museums-page">
<div class="map-topbar">
  <a href="index.html" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
<h1 class="map-h1"><span class="icon-map-header" aria-hidden="true"></span> Карта музеев</h1>
<p class="map-subtitle">{len(museums_dict)} {plural_ru(len(museums_dict), 'музей', 'музея', 'музеев')} в коллекции ({found_locations} на карте)</p>
<div class="map-wrap">
  <div id="map"></div>
</div>
<div class="museums-grid">{''.join(museum_list)}</div>
{scroll_top_button()}
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin></script>
{SCROLL_TOP_JS}
{COMMON_JS}
<script>
// Карта — не обязательная часть страницы. Если leaflet не загрузился,
// список музеев внизу всё равно должен работать (раньше падал весь скрипт).
if (typeof L === 'undefined') {{
    var box = document.getElementById('map');
    if (box) {{
        box.innerHTML = '<p class="map-fallback">Карта не загрузилась — проверьте соединение. Список музеев доступен ниже.</p>';
    }}
}} else {{
    var map = L.map('map').setView([50, 10], 3);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 18
    }}).addTo(map);

{all_markers}

    var markers = [];
    map.eachLayer(function(layer) {{
        if (layer instanceof L.Marker) markers.push(layer);
    }});
    if (markers.length > 0) {{
        map.fitBounds(L.featureGroup(markers).getBounds().pad(0.1));
    }}
}}

function scrollToMuseum(id) {{
    var el = document.getElementById('museum-' + id);
    if (!el) return;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({{ behavior: reduce ? 'auto' : 'smooth', block: 'center' }});
    el.classList.add('museum-highlight');
    setTimeout(function() {{ el.classList.remove('museum-highlight'); }}, 2000);
}}

// btn передаём аргументом. Раньше здесь был глобальный event.target —
// нестандартный приём, который ломается вне Chrome.
function toggleMuseumPosts(btn, id) {{
    var hidden = document.getElementById('hidden-' + id);
    if (!hidden) return;
    var isOpen = hidden.hasAttribute('hidden') === false;
    if (isOpen) {{
        hidden.setAttribute('hidden', '');
        var count = hidden.querySelectorAll('li').length;
        var word = (count % 10 === 1 && count % 100 !== 11) ? 'картину'
                 : (count % 10 >= 2 && count % 10 <= 4 && (count % 100 < 10 || count % 100 >= 20)) ? 'картины'
                 : 'картин';
        btn.textContent = 'Показать все ' + count + ' ' + word + ' ▾';
        btn.setAttribute('aria-expanded', 'false');
    }} else {{
        hidden.removeAttribute('hidden');
        btn.textContent = 'Свернуть ▴';
        btn.setAttribute('aria-expanded', 'true');
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
    import sys
    # python generate_map.py --regeocode — повторно искать музеи,
    # которые в прошлый раз не нашлись (кэш их запомнил как «нет координат»)
    generate_museums_page(retry_failed="--regeocode" in sys.argv)
    print("\nГотово! Откройте docs/museums.html в браузере.")