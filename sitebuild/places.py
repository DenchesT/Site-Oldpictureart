# -*- coding: utf-8 -*-
"""Места: справочник музеев, страницы мест, сведение походов к карточкам карты.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

from site_common import (visit_places, museum_page)
import logging
from .text import load_json, plural_ru, slugify

logger = logging.getLogger("build_site")

def visit_museum_names(all_posts):
    """Собрания из постов о картинах — по ним узнаются музеи в строке места."""
    return sorted({p["museum"].strip() for p in (all_posts or []) if p.get("museum")})


def visit_map_names(visits, all_posts):
    """{место из поста: название карточки на карте}.

    Считается ровно тем же способом, что и на карте, иначе ссылка со
    страницы похода вела бы в никуда: якорь собирается из этого названия.
    """
    names = sorted({p["museum"].strip() for p in (all_posts or []) if p.get("museum")})
    return visit_places(visits or [], names)


# ======================================================================
#                        СТРАНИЦЫ МУЗЕЕВ
# ======================================================================
#
# Раньше музей был только карточкой на общей карте. Отдельная страница —
# это адрес, который можно отправить («все картины из Прадо»), и страница,
# которую находит поиск. На ней картины этого собрания, походы туда,
# адрес, сайт и кусок карты.

# Заполняется в prepare_museums(): у кого из музеев есть своя страница.
# Названия нужны в полудюжине мест — карточки, страница картины, опись,
# статистика, — и таскать множество через все вызовы было бы хуже.
_MUSEUM_PAGES = set()

# Свои копии Leaflet в docs/vendor (README, «Свои копии библиотек»): карта не
# зависит от unpkg.com, который бывает недоступен.
LEAFLET_CSS = '<link rel="stylesheet" href="vendor/leaflet/leaflet.css">'
LEAFLET_JS = '<script src="vendor/leaflet/leaflet.js"></script>'


def museum_directory():
    """Справочник музеев и найденные картой координаты."""
    ov = {k: v for k, v in load_json("museum_overrides.json", {}).items()
          if not k.startswith("_") and isinstance(v, dict)}
    return ov, load_json("museum_coordinates.json", {})


def museum_info(name, directory=None):
    """Всё, что известно о месте: адрес, сайт, город, страна, координаты.

    Координаты — из справочника (если вписаны руками) или из кэша карты.
    Город и страна считаются тем же правилом, что и подпись на карте.
    """
    import generate_map as gm
    ov, co = directory or museum_directory()
    manual = ov.get(name) or {}
    loc = co.get(name) or {}
    lat = manual.get("lat", loc.get("lat"))
    lon = manual.get("lon", loc.get("lon"))
    city, country = gm.museum_place(name, manual, loc if loc else None)
    return {
        "name": name,
        # Чего нет в справочнике, сборка находит сама (generate_map.enrich).
        "address": gm.place_address(manual, loc),
        "site": gm.place_site(manual, loc),
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "city": city, "country": country,
        "approx": "lat" not in manual and loc.get("precision") == "approx",
        "skip": bool(manual.get("skip")),
    }


def museum_names(all_posts, visits):
    """Места, у которых будет страница: собрания картин и места походов.

    Частные собрания («Частная коллекция, США») страницы не получают —
    это не место, туда не сходишь; для них остаётся карточка на карте.
    """
    ov, _ = museum_directory()
    names = {p["museum"].strip() for p in all_posts if p.get("museum")}
    names |= set(visit_map_names(visits, all_posts).values())
    return sorted(n for n in names if n and not (ov.get(n) or {}).get("skip"))


def map_reminder(all_posts, visits):
    """Метки, которые стоят не на здании, и страницы музеев без адреса —
    в самом конце сборки.

    Карта называет их и сама, но в середине длинного лога строка терялась:
    так «Коллекция Месдага» простояла в центре Гааги — автопоиск по
    русскому названию ничего не нашёл и поставил метку по городу.
    Сеть не нужна: судим по кэшу координат, как generate_map.py.
    """
    overrides = {}
    try:
        import generate_map as gm
        overrides = gm.load_overrides(quiet=True)
        doubts = gm.map_warnings(museum_names(all_posts, visits),
                                 gm.load_cache(), overrides)
    except Exception as e:
        logger.warning(f"Проверить метки на карте не вышло: {e}")
        return []
    if doubts:
        logger.warning(f"⚠ На карте {len(doubts)} {plural_ru(len(doubts), 'метка', 'метки', 'меток')} "
                       f"не на своём месте:")
        for museum, why in doubts:
            logger.warning(f"   • {museum}: {why}")
        logger.warning('   Поправить: впишите в museum_overrides.json адрес — '
                       '"Название": {"address": "улица дом, город"} — или готовые "lat" и "lon", '
                       'затем python rebuild_pages.py. Подробнее — README, «Если метка стоит не там».')
    # Страницы без адреса. Адрес, сайт и страну сборка ищет сама, но
    # находит не всегда — тогда на странице музея остаётся один город.
    try:
        directory = museum_directory()
        bare = [n for n in museum_names(all_posts, visits)
                if not (overrides.get(n) or {}).get("skip")
                and not museum_info(n, directory)["address"]]
    except Exception:
        bare = []
    if bare:
        logger.warning(f"⚠ Без адреса на странице ({len(bare)}): " + "; ".join(bare))
        logger.warning('   Сам адрес не нашёлся — впишите в museum_overrides.json: '
                       '"Название": {"address": "улица дом, город", "site": "https://…"}')
    return doubts


def prepare_museums(all_posts, visits):
    """Запоминает, у кого есть страница. Вызывать до записи страниц."""
    _MUSEUM_PAGES.clear()
    _MUSEUM_PAGES.update(museum_names(all_posts, visits))
    return _MUSEUM_PAGES


def museum_href(name):
    """Куда ведёт название музея: на его страницу, а если её нет — на карту."""
    name = (name or "").strip()
    if name in _MUSEUM_PAGES:
        return museum_page(name)
    return f"museums.html#museum-{slugify(name)}"


def postal_address(info):
    """Адрес для разметки Schema.org: улица отдельно, город и страна отдельно."""
    street = info.get("address", "")
    city = info.get("city", "")
    parts = [p.strip() for p in street.split(",") if p.strip()]
    if city and parts and parts[-1].lower() == city.lower():
        parts = parts[:-1]
    out = {"@type": "PostalAddress"}
    if parts:
        out["streetAddress"] = ", ".join(parts)
    if city:
        out["addressLocality"] = city
    if info.get("country"):
        out["addressCountry"] = info["country"]
    return out if len(out) > 1 else None


def place_jsonld(info, kind="Museum"):
    """Место для разметки: название, адрес, координаты, сайт."""
    place = {"@type": kind, "name": info["name"]}
    addr = postal_address(info)
    if addr:
        place["address"] = addr
    if info.get("lat") is not None and not info.get("approx"):
        place["geo"] = {"@type": "GeoCoordinates", "latitude": round(info["lat"], 6),
                        "longitude": round(info["lon"], 6)}
    if info.get("site"):
        place["url"] = info["site"]
    return place


def been_phrase_ru(n):
    """«Побывал однажды / 2 раза / 5 раз» — как на карте (been_phrase)."""
    if n == 1:
        return "Побывал однажды"
    return f"Побывал {n} {plural_ru(n, 'раз', 'раза', 'раз')}"

__all__ = [
    'visit_museum_names',
    'visit_map_names',
    '_MUSEUM_PAGES',
    'LEAFLET_CSS',
    'LEAFLET_JS',
    'museum_directory',
    'museum_info',
    'museum_names',
    'map_reminder',
    'prepare_museums',
    'museum_href',
    'postal_address',
    'place_jsonld',
    'been_phrase_ru',
]
