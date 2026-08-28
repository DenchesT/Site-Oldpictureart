"""
Генератор карты музеев для Old Picture Art.
Автоматически находит координаты через OpenStreetMap Nominatim API.
Запуск: python generate_map.py
"""

import json
import os
import re
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
OVERRIDES_FILE = "museum_overrides.json"


USER_AGENT = 'OldPictureArt/1.0 (github.com/DenchesT/Site-Oldpictureart)'


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


# ---------------------------------------------------------------- Wikidata

def wikidata_search(query):
    """Ищет координаты через Wikidata.

    Nominatim — это карта, он знает названия объектов так, как они подписаны
    на местности: «Musée d'Orsay», а не «Музей д'Орсе». Поэтому русские
    названия зарубежных музеев он почти не находил — 38 из 50 оставались
    без координат.

    Wikidata — многоязычная база: у неё есть русские метки и синонимы
    («ГМИИ им. А.С. Пушкина», «Метрополитен-музей») и свойство P625 —
    координаты объекта. Поэтому спрашиваем сначала её.
    """
    params = {
        'action': 'wbsearchentities', 'search': query, 'language': 'ru',
        'uselang': 'ru', 'type': 'item', 'limit': 7, 'format': 'json',
    }
    try:
        data = _get_json('https://www.wikidata.org/w/api.php?' + urllib.parse.urlencode(params))
    except Exception as e:
        logger.debug(f"    wikidata search «{query}»: {e}")
        return None
    time.sleep(0.4)

    candidates = data.get('search') or []
    if not candidates:
        return None

    # Сначала те, чьё описание похоже на музей — иначе «Прадо» может
    # оказаться футбольным клубом или станцией метро.
    museum_words = ('музе', 'галере', 'коллекц', 'собрани', 'дворец', 'институт',
                    'museum', 'gallery', 'collection', 'palace')
    def looks_like_museum(item):
        text = ((item.get('description') or '') + ' ' + (item.get('label') or '')).lower()
        return any(w in text for w in museum_words)

    ordered = [c for c in candidates if looks_like_museum(c)] + \
              [c for c in candidates if not looks_like_museum(c)]

    ids = [c['id'] for c in ordered[:5]]
    params = {'action': 'wbgetentities', 'ids': '|'.join(ids),
              'props': 'claims|labels', 'languages': 'ru|en', 'format': 'json'}
    try:
        data = _get_json('https://www.wikidata.org/w/api.php?' + urllib.parse.urlencode(params))
    except Exception as e:
        logger.debug(f"    wikidata entities: {e}")
        return None
    time.sleep(0.4)

    entities = data.get('entities') or {}
    for qid in ids:
        claims = (entities.get(qid) or {}).get('claims') or {}
        coord = claims.get('P625')          # coordinate location
        if not coord:
            continue
        try:
            value = coord[0]['mainsnak']['datavalue']['value']
            labels = (entities.get(qid) or {}).get('labels') or {}
            name = (labels.get('ru') or labels.get('en') or {}).get('value', query)
            return {'lat': float(value['latitude']), 'lon': float(value['longitude']),
                    'display_name': name, 'source': f'wikidata:{qid}', 'precision': 'exact'}
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return None


# --------------------------------------------------------------- Nominatim

def nominatim_search(query):
    """Один запрос к Nominatim (OpenStreetMap)."""
    params = {'q': query, 'format': 'json', 'limit': 1, 'accept-language': 'ru'}
    try:
        data = _get_json('https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(params))
    except Exception as e:
        logger.debug(f"    nominatim «{query}»: {e}")
        time.sleep(2)
        return None
    time.sleep(1.1)  # правила Nominatim: не чаще одного запроса в секунду
    if not data:
        return None
    return {
        'lat': float(data[0]['lat']),
        'lon': float(data[0]['lon']),
        'display_name': data[0].get('display_name', query),
        'source': 'nominatim',
        'precision': 'exact',
    }


# ------------------------------------------------------------ формулировки

def strip_parens(text):
    """«Лувр, Париж (в запаснике)» → «Лувр, Париж»."""
    return re.sub(r"\s*\([^)]*\)", "", text).strip()


def split_parts(museum_name):
    return [p.strip() for p in strip_parens(museum_name).split(',') if p.strip()]


def build_queries(museum_name):
    """Варианты запроса от самого точного к самому общему.

    Раньше спрашивали ровно одной строкой — полным названием с городом.
    Теперь пробуем и отдельные части: у «Отдел личных коллекций,
    ГМИИ им. А.С. Пушкина, Москва» полезная часть в середине.
    """
    parts = split_parts(museum_name)
    if not parts:
        return []

    queries = [strip_parens(museum_name)]
    city = parts[-1] if len(parts) >= 2 else ''

    for part in parts[:-1] if city else parts:
        queries.append(part)
        if city:
            queries.append(f"{part} {city}")

    seen, out = set(), []
    for q in queries:
        q = q.strip(' ,')
        if len(q) > 2 and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def city_fallback(museum_name):
    """Последний рубеж: ставим метку хотя бы на город или страну.

    Для «Частная коллекция, Швейцария» точного адреса не существует
    в принципе, но показать регион на карте всё равно осмысленно —
    такие метки помечаются как приблизительные.
    """
    parts = split_parts(museum_name)
    if len(parts) < 2:
        return None
    place = parts[-1]
    result = wikidata_search(place) or nominatim_search(place)
    if result:
        result['precision'] = 'approx'
        result['display_name'] = place
    return result


# ------------------------------------------------------------------ geocode

def geocode(museum_name, cache, overrides=None, retry_failed=False, offline=False, stats=None):
    """Ищет координаты музея: ручной справочник → кэш → Wikidata → Nominatim → город.

    Порядок здесь важнее, чем кажется. Кэш проверяется ДО любых сетевых
    запросов: раньше подсказки {"query": ...} из справочника обрабатывались
    первыми, и 35 музеев переспрашивались в сети при каждом запуске —
    сборка занимала минуты вместо секунд.

    retry_failed=True — заново спросить те названия, что записались в кэш
    как null (иначе одна неудача запоминалась навсегда).
    offline=True — вообще не ходить в сеть, брать только готовое.
    """
    overrides = overrides or {}
    stats = stats if stats is not None else {}

    def bump(key):
        stats[key] = stats.get(key, 0) + 1

    manual = overrides.get(museum_name) or {}

    # 1. Записи, для которых сеть не нужна никогда
    if manual.get('skip'):
        # «Частная коллекция» — адреса не существует. Раньше Nominatim
        # находил по этому запросу магазин на Волхонке и ставил метку
        # в центре Москвы. Такие записи остаются в списке под картой,
        # но метки не получают.
        logger.info(f"  – (без метки по справочнику) {museum_name}")
        cache.pop(museum_name, None)
        bump('skip')
        return None

    if 'lat' in manual and 'lon' in manual:
        logger.info(f"  ✓ (справочник) {museum_name}")
        result = {'lat': float(manual['lat']), 'lon': float(manual['lon']),
                  'display_name': manual.get('display_name', museum_name),
                  'source': 'override', 'precision': manual.get('precision', 'exact')}
        cache[museum_name] = result
        bump('override')
        return result

    # 2. Кэш. Запоминаем, каким запросом получен результат: если подсказку
    #    в справочнике поменяли, координаты нужно искать заново — иначе
    #    правка справочника молча ни на что не влияла бы.
    wanted_query = (manual.get('query') or '').strip()
    if museum_name in cache:
        cached = cache[museum_name]
        if cached:
            if wanted_query and cached.get('query', '') != wanted_query:
                logger.info(f"  ↻ подсказка изменилась, ищу заново: {museum_name}")
            else:
                logger.info(f"  ✓ (из кэша) {museum_name}")
                bump('cache')
                return cached
        elif not retry_failed:
            logger.info(f"  – (из кэша, без координат) {museum_name}")
            bump('cache_empty')
            return None

    if offline:
        logger.info(f"  – (офлайн, пропуск) {museum_name}")
        bump('offline')
        return None

    def remember(result, query):
        result['query'] = query
        cache[museum_name] = result
        bump('lookup')
        return result

    # 3. Подсказка из справочника — но уже после кэша
    if wanted_query:
        found = wikidata_search(wanted_query) or nominatim_search(wanted_query)
        if found:
            logger.info(f"  ✓ (справочник: «{wanted_query}») {museum_name} → "
                        f"{found['lat']:.4f}, {found['lon']:.4f}")
            return remember(found, wanted_query)

    # 4. Автопоиск по частям названия
    for query in build_queries(museum_name):
        for finder in (wikidata_search, nominatim_search):
            result = finder(query)
            if result:
                note = "" if query == museum_name else f" (по запросу «{query}»)"
                logger.info(f"  ✓ {museum_name} → {result['lat']:.4f}, {result['lon']:.4f}"
                            f" [{result['source']}]{note}")
                return remember(result, query)

    # 5. Хотя бы город
    result = city_fallback(museum_name)
    if result:
        logger.info(f"  ≈ {museum_name} → приблизительно, по месту «{result['display_name']}»")
        return remember(result, wanted_query or museum_name)

    logger.warning(f"  ✗ Не найдено: {museum_name}")
    cache[museum_name] = None
    bump('not_found')
    return None


def slugify(text):
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


MAP_CONFIG_TEMPLATE = """// Ключи картографических сервисов.
// Пустая строка — слой просто не появится в переключателе,
// остальные карты продолжат работать как были.
//
// ЯНДЕКС.КАРТЫ — нужен ключ от продукта \"Tiles API\" (Подложка карты)
// 1. Кабинет разработчика: https://yandex.ru/maps-api/ → Ключи → Подключить API
// 2. Выберите ИМЕННО \"Tiles API — Подложка карты\".
//    Не JavaScript API: у него другой формат и другие условия.
//    Tiles API бесплатен, лимит 30 запросов в секунду.
// 3. Скопируйте ключ и вставьте между кавычками ниже
// 4. Ограничьте ключ доменом denchest.github.io — на статическом
//    сайте ключ виден всем в исходниках страницы
//
// Этот файл сборка не перезаписывает: ключ переживёт пересборку сайта.
window.MAP_KEYS = {
  yandex: ""
};
"""


# =============================== СТИЛИ СТРАНИЦЫ ===============================
# Стили именно этой страницы держим здесь, а не в общем style.css:
# кроме карты музеев они нигде не нужны.
MUSEUMS_CSS = """
.museums-hero { text-align: center; padding: .5rem 1.5rem 0; }
.museums-hero h1 { font-size: 2rem; justify-content: center; display: flex; align-items: center; gap: 10px; }
.museums-stats { color: var(--muted); font-size: .95rem; margin: .3rem 0 0; }
.museums-stats b { color: var(--text); }

/* ---------- панель поиска и сортировки ---------- */
.museums-toolbar {
  max-width: 1500px;
  margin: 1.2rem auto .8rem;
  padding: 0 1.5rem;
  display: flex;
  gap: .6rem;
  align-items: center;
  flex-wrap: wrap;
}
.museums-toolbar .search-box { flex: 1 1 260px; min-width: 0; }
.museum-sort {
  padding: .7rem .9rem;
  font-size: .9rem;
  font-family: inherit;
  border: 1px solid var(--input-border);
  border-radius: 6px;
  background: var(--card-bg);
  color: var(--text);
  cursor: pointer;
}
.museums-toolbar .results-count { flex: 0 0 auto; }

/* ---------- две колонки: карта закреплена, список едет ---------- */
.museums-layout {
  max-width: 1500px;
  margin: 0 auto;
  padding: 0 1.5rem 2rem;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 1.5rem;
  align-items: start;
}

.museums-map-col { position: sticky; top: 1rem; }

.map-shell {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  box-shadow: 0 4px 20px var(--shadow);
}

#map { height: calc(100vh - 8rem); min-height: 420px; z-index: 1; background: var(--border); }

.map-expand {
  position: absolute;
  right: 12px;
  bottom: 12px;
  z-index: 500;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text);
  font-size: 1.1rem;
  cursor: pointer;
  box-shadow: 0 2px 8px var(--shadow);
}
.map-expand:hover { background: var(--border); }

/* развёрнутая карта */
.map-shell.fullscreen {
  position: fixed;
  inset: 0;
  z-index: 3000;
  border-radius: 0;
  border: none;
}
.map-shell.fullscreen #map { height: 100vh; height: 100dvh; }

.map-fallback { padding: 2rem 1rem; text-align: center; color: var(--muted); }

/* ---------- карточки музеев ---------- */
.museums-list-col { display: flex; flex-direction: column; gap: .9rem; min-width: 0; }

.museum-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1rem 1.1rem;
  transition: border-color .2s, box-shadow .2s, transform .2s;
  cursor: pointer;
  scroll-margin-top: 1rem;
}
.museum-card:hover { border-color: var(--active); box-shadow: 0 4px 14px var(--shadow); }
.museum-card.active {
  border-color: var(--active);
  box-shadow: 0 0 0 2px var(--active), 0 6px 18px var(--shadow);
}

.museum-card-head { display: flex; align-items: flex-start; gap: .6rem; justify-content: space-between; }
.museum-card h3 { margin: 0; font-size: 1.08rem; line-height: 1.3; font-weight: 700; }

.museum-badge {
  flex-shrink: 0;
  background: var(--tag-bg);
  color: var(--tag-text);
  border-radius: 20px;
  padding: .15rem .6rem;
  font-size: .8rem;
  font-weight: 700;
  line-height: 1.5;
}
.museum-card.active .museum-badge { background: var(--active); color: #fff; }

.museum-location { color: var(--muted); font-size: .85rem; margin: .35rem 0 0; }
.museum-nomap { opacity: .65; font-style: italic; }

/* мозаика миниатюр */
.museum-thumbs { display: flex; gap: 6px; margin-top: .7rem; flex-wrap: wrap; }
.museum-thumb {
  width: 62px;
  height: 62px;
  border-radius: 8px;
  overflow: hidden;
  display: block;
  flex-shrink: 0;
  background: var(--border);
  transition: transform .15s;
}
.museum-thumb:hover { transform: scale(1.06); }
.museum-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.museum-thumb-more {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-size: .85rem;
  font-weight: 600;
  border: 1px dashed var(--border);
  background: none;
}

.museum-toggle {
  margin-top: .7rem;
  background: none;
  border: 1px solid var(--border);
  color: var(--link);
  padding: .3rem .8rem;
  border-radius: 15px;
  cursor: pointer;
  font-size: .8rem;
  font-family: inherit;
  transition: background .2s;
}
.museum-toggle:hover { background: var(--border); }

.museum-posts-list { margin: .6rem 0 0; padding-left: 1.2rem; font-size: .85rem; }
.museum-posts-list li { margin-bottom: .2rem; }
.museum-posts-list a { color: var(--link); text-decoration: none; }
.museum-posts-list a:hover { text-decoration: underline; }

/* всплывающее окно на карте */
.leaflet-popup-content { margin: .8rem 1rem; font-family: inherit; }
.leaflet-popup-content b { font-size: .95rem; }
.popup-link { color: var(--active); }
.popup-place { color: #555; font-size: .85rem; }

/* маркер приблизительного расположения */
.marker-approx { opacity: .55; }

/* ---------- телефон и планшет ---------- */
@media (max-width: 1000px) {
  .museums-layout { grid-template-columns: 1fr; gap: 1rem; padding: 0 .8rem 2rem; }
  .museums-map-col { position: static; }
  #map { height: 320px; min-height: 0; }
  .museums-toolbar { padding: 0 .8rem; }
  .museums-hero h1 { font-size: 1.5rem; }
}

@media (max-width: 480px) {
  .museums-hero { padding: .3rem .8rem 0; }
  .museums-hero h1 { font-size: 1.25rem; }
  .museums-stats { font-size: .85rem; }
  .museum-card { padding: .8rem .9rem; }
  .museum-card h3 { font-size: 1rem; }
  .museum-thumb { width: 54px; height: 54px; }
  .museum-sort { flex: 1 1 100%; }
}
"""

# ============================= СКРИПТ СТРАНИЦЫ ================================
MUSEUMS_JS = """
// ------------------------------------------------ слои карты
// Никаких ключей эти четыре слоя не требуют. Тёмная схема нужна,
// потому что обычная карта в тёмной теме сайта светит белым прямоугольником.
var BASE_LAYERS = [
  {id: 'light', name: 'Светлая', url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
   attr: '&copy; OpenStreetMap, &copy; CARTO', max: 20},
  {id: 'dark', name: 'Тёмная', url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
   attr: '&copy; OpenStreetMap, &copy; CARTO', max: 20},
  {id: 'osm', name: 'Подробная', url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
   attr: '&copy; OpenStreetMap', max: 19},
  {id: 'sat', name: 'Спутник',
   url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
   attr: 'Esri, Maxar, Earthstar Geographics', max: 19}
];

var map = null, markers = {}, layers = {}, layerControl = null, userPickedLayer = false;

function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function initMap() {
  if (typeof L === 'undefined') {
    var box = document.getElementById('map');
    if (box) box.innerHTML = '<p class="map-fallback">Карта не загрузилась — проверьте соединение.<br>Список музеев доступен рядом.</p>';
    return;
  }

  map = L.map('map', {scrollWheelZoom: true}).setView([48, 10], 4);

  BASE_LAYERS.forEach(function (cfg) {
    layers[cfg.name] = L.tileLayer(cfg.url, {attribution: cfg.attr, maxZoom: cfg.max});
    layers[cfg.name]._opaId = cfg.id;
  });

  var saved = null;
  try { saved = localStorage.getItem('mapLayer'); } catch (e) {}
  var startName = null;
  if (saved) {
    BASE_LAYERS.forEach(function (c) { if (c.id === saved) startName = c.name; });
    // Яндекса среди BASE_LAYERS нет, он добавляется позже — но выбор
    // всё равно считаем осознанным, чтобы тема его не перебила.
    userPickedLayer = !!startName || saved === 'yandex';
  }
  if (!startName) startName = currentTheme() === 'dark' ? 'Тёмная' : 'Светлая';
  layers[startName].addTo(map);

  layerControl = L.control.layers(layers, null, {position: 'topright'}).addTo(map);

  map.on('baselayerchange', function (e) {
    userPickedLayer = true;
    try { localStorage.setItem('mapLayer', e.layer._opaId || ''); } catch (err) {}
  });

  // Пока человек сам не выбрал слой, карта следует за темой сайта
  new MutationObserver(function () {
    if (userPickedLayer || !map) return;
    var want = currentTheme() === 'dark' ? 'Тёмная' : 'Светлая';
    Object.keys(layers).forEach(function (name) {
      if (name === want) { if (!map.hasLayer(layers[name])) map.addLayer(layers[name]); }
      else if (map.hasLayer(layers[name])) map.removeLayer(layers[name]);
    });
  }).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});

  addMarkers();
  addYandexLayer();
}

function addMarkers() {
  var group = [];
  MUSEUMS.forEach(function (m) {
    var marker = L.marker([m.lat, m.lon], {
      opacity: m.approx ? 0.55 : 1,
      title: m.name
    }).addTo(map);

    var word = m.count % 10 === 1 && m.count % 100 !== 11 ? 'картина'
             : (m.count % 10 >= 2 && m.count % 10 <= 4 && (m.count % 100 < 10 || m.count % 100 >= 20)) ? 'картины'
             : 'картин';

    var html = document.createElement('div');
    var title = document.createElement('b');
    title.textContent = m.name;
    html.appendChild(title);
    if (m.place) {
      var place = document.createElement('div');
      place.className = 'popup-place';
      place.textContent = m.place + (m.approx ? ' — расположение приблизительное' : '');
      html.appendChild(place);
    }
    var cnt = document.createElement('div');
    cnt.textContent = m.count + ' ' + word;
    html.appendChild(cnt);
    var link = document.createElement('a');
    link.href = '#museum-' + m.id;
    link.className = 'popup-link';
    link.textContent = 'Показать в списке';
    link.addEventListener('click', function (e) { e.preventDefault(); focusCard(m.id); });
    html.appendChild(link);

    marker.bindPopup(html);
    marker.on('click', function () { highlightCard(m.id); });
    markers[m.id] = marker;
    group.push(marker);
  });

  if (group.length) map.fitBounds(L.featureGroup(group).getBounds().pad(0.1));
}

// ------------------------------------------------ Яндекс.Карты
// Tiles API отдаёт обычные XYZ-тайлы в проекции web_mercator, поэтому это
// такой же слой Leaflet, как остальные: ни отдельного SDK, ни адаптера,
// ни второго движка карты внутри страницы. Слой появляется только если
// в map-config.js вписан ключ.
function addYandexLayer() {
  var key = (window.MAP_KEYS && window.MAP_KEYS.yandex || '').trim();
  if (!key || !layerControl) return;
  try {
    var url = 'https://tiles.api-maps.yandex.ru/v1/tiles/?apikey=' + encodeURIComponent(key) +
              '&lang=ru_RU&l=map&projection=web_mercator&x={x}&y={y}&z={z}';
    var yandex = L.tileLayer(url, {
      attribution: '&copy; <a href="https://yandex.ru/maps/" target="_blank" rel="noopener">Яндекс Карты</a>',
      maxZoom: 20
    });
    yandex._opaId = 'yandex';
    layers['Яндекс'] = yandex;
    layerControl.addBaseLayer(yandex, 'Яндекс');

    // Слой добавляется после инициализации карты, поэтому сохранённый
    // выбор «Яндекс» включаем здесь.
    var saved = null;
    try { saved = localStorage.getItem('mapLayer'); } catch (err) {}
    if (saved === 'yandex') {
      Object.keys(layers).forEach(function (n) {
        if (n !== 'Яндекс' && map.hasLayer(layers[n])) map.removeLayer(layers[n]);
      });
      map.addLayer(yandex);
    }

    // Ключ мог быть не от того продукта или домен не разрешён — тогда тайлы
    // не приходят. Пишем в консоль один раз, страница при этом не ломается.
    var warned = false;
    yandex.on('tileerror', function () {
      if (warned) return;
      warned = true;
      console.warn('Яндекс.Карты: тайлы не загружаются. Проверьте, что ключ от Tiles API ' +
                   'и что домен разрешён в кабинете разработчика.');
    });
  } catch (e) {
    console.warn('Слой Яндекса не добавлен:', e.message);
  }
}

// ------------------------------------------------ связь списка и карты
function highlightCard(id) {
  document.querySelectorAll('.museum-card.active').forEach(function (c) { c.classList.remove('active'); });
  var card = document.getElementById('museum-' + id);
  if (card) card.classList.add('active');
}

function focusCard(id) {
  highlightCard(id);
  var card = document.getElementById('museum-' + id);
  if (!card) return;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  card.scrollIntoView({behavior: reduce ? 'auto' : 'smooth', block: 'center'});
}

function focusMuseum(id) {
  highlightCard(id);
  var marker = markers[id];
  if (!map || !marker) return;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) map.setView(marker.getLatLng(), Math.max(map.getZoom(), 9));
  else map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), 9), {duration: 0.8});
  marker.openPopup();
}

function toggleMuseumPosts(btn, id) {
  var list = document.getElementById('posts-' + id);
  if (!list) return;
  var open = !list.hasAttribute('hidden');
  if (open) {
    list.setAttribute('hidden', '');
    btn.textContent = 'Список картин ▾';
  } else {
    list.removeAttribute('hidden');
    btn.textContent = 'Свернуть ▴';
  }
  btn.setAttribute('aria-expanded', open ? 'false' : 'true');
}

function toggleMapFullscreen(btn) {
  var shell = document.querySelector('.map-shell');
  if (!shell) return;
  var on = shell.classList.toggle('fullscreen');
  btn.setAttribute('aria-label', on ? 'Свернуть карту' : 'Развернуть карту');
  btn.title = btn.getAttribute('aria-label');
  btn.textContent = on ? '✕' : '⛶';
  document.body.style.overflow = on ? 'hidden' : '';
  if (map) setTimeout(function () { map.invalidateSize(); }, 250);
}

// ------------------------------------------------ поиск и сортировка
function plural(n, one, few, many) {
  var n10 = n % 10, n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return one;
  if (n10 >= 2 && n10 <= 4 && (n100 < 10 || n100 >= 20)) return few;
  return many;
}

function applyMuseumFilter() {
  var box = document.getElementById('search-value');
  var query = (window.__museumQuery || '').toLowerCase().trim();
  var shown = 0;
  document.querySelectorAll('.museum-card').forEach(function (card) {
    var match = !query || (card.dataset.search || '').indexOf(query) !== -1;
    card.hidden = !match;
    if (match) shown++;
    // метки на карте фильтруются вместе со списком
    var marker = markers[card.dataset.id];
    if (marker && map) {
      if (match && !map.hasLayer(marker)) map.addLayer(marker);
      else if (!match && map.hasLayer(marker)) map.removeLayer(marker);
    }
  });
  var counter = document.getElementById('museum-found');
  if (counter) counter.textContent = query ? shown + ' ' + plural(shown, 'музей', 'музея', 'музеев') : '';
  var empty = document.getElementById('museums-empty');
  if (empty) empty.hidden = shown !== 0;
}

function sortMuseums(mode) {
  var list = document.getElementById('museum-list');
  var cards = Array.prototype.slice.call(list.querySelectorAll('.museum-card'));
  cards.sort(function (a, b) {
    if (mode === 'name') return a.dataset.name.localeCompare(b.dataset.name, 'ru');
    if (mode === 'country') {
      var ca = a.dataset.country || 'яяя', cb = b.dataset.country || 'яяя';
      return ca.localeCompare(cb, 'ru') || a.dataset.name.localeCompare(b.dataset.name, 'ru');
    }
    return (+b.dataset.count) - (+a.dataset.count) || a.dataset.name.localeCompare(b.dataset.name, 'ru');
  });
  var frag = document.createDocumentFragment();
  cards.forEach(function (c) { frag.appendChild(c); });
  list.insertBefore(frag, document.getElementById('museums-empty'));
  try { localStorage.setItem('museumSort', mode); } catch (e) {}
}

document.addEventListener('DOMContentLoaded', function () {
  initMap();

  var search = document.getElementById('museum-search');
  if (search) {
    var timer = null;
    search.addEventListener('input', function (e) {
      var value = e.target.value;
      clearTimeout(timer);
      timer = setTimeout(function () { window.__museumQuery = value; applyMuseumFilter(); }, 120);
    });
  }

  var sort = document.getElementById('museum-sort');
  if (sort) {
    var savedSort = null;
    try { savedSort = localStorage.getItem('museumSort'); } catch (e) {}
    if (savedSort) { sort.value = savedSort; sortMuseums(savedSort); }
    sort.addEventListener('change', function () { sortMuseums(this.value); });
  }

  // Клик по карточке ведёт к метке. Ссылки внутри карточки не перехватываем.
  document.getElementById('museum-list').addEventListener('click', function (e) {
    if (e.target.closest('a, button')) return;
    var card = e.target.closest('.museum-card');
    if (card && card.dataset.mapped === '1') focusMuseum(card.dataset.id);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var shell = document.querySelector('.map-shell.fullscreen');
    if (shell) toggleMapFullscreen(document.querySelector('.map-expand'));
  });
});
"""


def generate_museums_page(retry_failed=False, offline=False):
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
    
    overrides = {}
    if os.path.exists(OVERRIDES_FILE):
        with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
            overrides = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
        logger.info(f"Ручной справочник: {len(overrides)} записей")

    logger.info("🔍 Координаты музеев...")
    if retry_failed:
        logger.info("   (--regeocode: заново ищем музеи без координат)")
    if offline:
        logger.info("   (--no-geocode: в сеть не ходим, берём только готовое)")
    geo_stats = {}
    t0 = time.time()
    locations = {}
    not_found = []
    for museum in sorted(museums_dict.keys()):
        result = geocode(museum, cache, overrides=overrides,
                         retry_failed=retry_failed, offline=offline, stats=geo_stats)
        if result:
            city, country = extract_city_country(result.get('display_name', museum))
            locations[museum] = {
                'lat': result['lat'],
                'lon': result['lon'],
                'city': city,
                'country': country,
                'precision': result.get('precision', 'exact'),
            }
        elif not (overrides.get(museum) or {}).get('skip'):
            not_found.append(museum)

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    lookups = geo_stats.get('lookup', 0)
    from_cache = geo_stats.get('cache', 0) + geo_stats.get('cache_empty', 0) + geo_stats.get('override', 0)
    logger.info(f"   Готово за {time.time() - t0:.1f} с: из кэша и справочника {from_cache}, "
                f"запросов в сеть {lookups}")
    if lookups == 0:
        logger.info("   В сеть не ходили — всё было готово")
    
    # ---------------------------------------------------------- карточки
    cards = []
    map_data = []
    found_locations = 0
    countries = set()

    for museum, posts in sorted(museums_dict.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())):
        loc = locations.get(museum, {})
        city = loc.get('city', '')
        country = loc.get('country', '')
        lat, lon = loc.get('lat'), loc.get('lon')
        approx = loc.get('precision') == 'approx'
        museum_id = slugify(museum)

        if lat and lon:
            found_locations += 1
        if country:
            countries.add(country)

        posts_sorted = sorted(posts, key=lambda x: x.get('date', ''), reverse=True)

        # Мозаика миниатюр — главное, что оживляет список: раньше карточка
        # музея была просто текстовым перечнем ссылок.
        thumbs = []
        for post in posts_sorted:
            src = (post.get('thumbs') or post.get('images') or [None])[0]
            if src:
                alt = f"{post.get('artist','')} — {post.get('title','')}"
                thumbs.append((src, post['filename'], alt))
            if len(thumbs) >= 6:
                break
        extra = len(posts_sorted) - len(thumbs)
        thumbs_html = "".join(
            f'<a class="museum-thumb" href="{h(fn)}" title="{h(alt)}">'
            f'<img src="{h(src)}" alt="{h(alt)}" loading="lazy" decoding="async"></a>'
            for src, fn, alt in thumbs
        )
        if extra > 0:
            thumbs_html += f'<span class="museum-thumb museum-thumb-more">+{extra}</span>'
        thumbs_block = f'<div class="museum-thumbs">{thumbs_html}</div>' if thumbs_html else ""

        posts_html = "".join(
            f'<li><a href="{h(post["filename"])}">{h(post.get("artist",""))} — {h(post.get("title",""))}</a></li>'
            for post in posts_sorted
        )

        loc_line = ", ".join(x for x in (city, country) if x)
        if loc_line:
            approx_note = ' <span class="approx-note">(приблизительно)</span>' if approx else ""
            location_html = (f'<p class="museum-location"><span class="icon-location" aria-hidden="true"></span> '
                             f'{h(loc_line)}{approx_note}</p>')
        else:
            location_html = '<p class="museum-location museum-nomap">Нет на карте</p>'

        search_blob = " ".join([museum, city, country]).lower()
        mapped = "1" if (lat and lon) else "0"

        cards.append(
            f'<article class="museum-card" id="museum-{museum_id}" data-id="{museum_id}"\n'
            f'         data-search="{h(search_blob)}" data-count="{len(posts)}"\n'
            f'         data-name="{h(museum.lower())}" data-country="{h(country.lower())}"\n'
            f'         data-mapped="{mapped}">\n'
            f'  <header class="museum-card-head"><h3>{h(museum)}</h3>'
            f'<span class="museum-badge">{len(posts)}</span></header>\n'
            f'  {location_html}\n'
            f'  {thumbs_block}\n'
            f'  <button type="button" class="museum-toggle" aria-expanded="false" aria-controls="posts-{museum_id}"\n'
            f'          onclick="toggleMuseumPosts(this, \'{museum_id}\')">Список картин ▾</button>\n'
            f'  <ul class="museum-posts-list" id="posts-{museum_id}" hidden>{posts_html}</ul>\n'
            f'</article>'
        )

        if lat and lon:
            map_data.append({
                'id': museum_id, 'name': museum, 'place': loc_line,
                'lat': lat, 'lon': lon, 'count': len(posts), 'approx': approx,
            })

    missing = len(museums_dict) - found_locations
    total_paintings = sum(len(v) for v in museums_dict.values())

    # Конфиг с ключами создаём один раз и больше не трогаем — иначе
    # пересборка сайта затирала бы вписанный ключ.
    config_path = os.path.join(OUTPUT_DIR, "map-config.js")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(MAP_CONFIG_TEMPLATE)
        logger.info(f"Создан {config_path} — впишите туда ключ Яндекс.Карт")

    page_head = head_common(
        title="Карта музеев — Old Picture Art",
        description=f"{len(museums_dict)} музеев из коллекции Old Picture Art на карте мира.",
        canonical=f"{BASE_URL}/museums.html",
        extra='\n<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" '
              'integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin>',
    )

    stats = (f"<b>{len(museums_dict)}</b> {plural_ru(len(museums_dict), 'музей', 'музея', 'музеев')} · "
             f"<b>{total_paintings}</b> {plural_ru(total_paintings, 'картина', 'картины', 'картин')} · "
             f"<b>{len(countries)}</b> {plural_ru(len(countries), 'страна', 'страны', 'стран')} · "
             f"{found_locations} на карте")

    html = f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
{page_head}
<style>
{MUSEUMS_CSS}
</style>
</head><body class="museums-page">
<div class="map-topbar">
  <a href="index.html" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>

<header class="museums-hero">
  <h1><span class="icon-map-header" aria-hidden="true"></span> Карта музеев</h1>
  <p class="museums-stats">{stats}</p>
</header>

<div class="museums-toolbar">
  <label class="visually-hidden" for="museum-search">Поиск по музеям</label>
  <input type="search" id="museum-search" class="search-box" autocomplete="off"
         placeholder="Музей, город или страна…">
  <label class="visually-hidden" for="museum-sort">Сортировка</label>
  <select id="museum-sort" class="museum-sort">
    <option value="count">Сначала где больше картин</option>
    <option value="name">По названию</option>
    <option value="country">По стране</option>
  </select>
  <span id="museum-found" class="results-count" role="status" aria-live="polite"></span>
</div>

<div class="museums-layout">
  <div class="museums-map-col">
    <div class="map-shell">
      <div id="map"></div>
      <button type="button" class="map-expand" onclick="toggleMapFullscreen(this)"
              aria-label="Развернуть карту" title="Развернуть карту">⛶</button>
    </div>
  </div>
  <div class="museums-list-col" id="museum-list">
{chr(10).join(cards)}
    <p class="no-results" id="museums-empty" hidden>Ничего не найдено.</p>
  </div>
</div>

{scroll_top_button()}
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin></script>
<script src="map-config.js"></script>
{SCROLL_TOP_JS}
{COMMON_JS}
<script>
const MUSEUMS = {json.dumps(map_data, ensure_ascii=False)};
{MUSEUMS_JS}
</script>
</body></html>"""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "museums.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    logger.info(f"✅ Карта музеев сохранена: {output_path}")
    logger.info(f"   Всего музеев: {len(museums_dict)}")
    logger.info(f"   На карте: {found_locations}")
    approx = [m for m, l in locations.items() if l.get('precision') == 'approx']
    if approx:
        logger.info(f"   Приблизительно (по городу/стране): {len(approx)}")
    if not_found:
        logger.warning(f"   Без координат: {len(not_found)} — добавьте их в {OVERRIDES_FILE}:")
        for m in not_found:
            logger.warning(f'     "{m}": {{"lat": 0.0, "lon": 0.0}},')
    logger.info(f"   Не найдено: {missing}")


if __name__ == "__main__":
    import sys
    # --regeocode   заново искать музеи, которые в прошлый раз не нашлись
    # --no-geocode  вообще не ходить в сеть, взять только готовые координаты
    generate_museums_page(
        retry_failed="--regeocode" in sys.argv,
        offline="--no-geocode" in sys.argv,
    )
    print("\nГотово! Откройте docs/museums.html в браузере.")