# -*- coding: utf-8 -*-
"""Post parsing and atomic JSON storage; public function names are unchanged."""
import os
import re
import json
import logging
from site_common import work_year, typo_ru
from .config import DICTIONARY_FILE
from .safety import atomic_json

logger = logging.getLogger("build_site")


def load_dictionary():
    default = {
        "materials": ["холст","бумага","картон","дерево","доска","металл","стекло","тонированная бумага","рифлёная бумага","тонированная рифлёная бумага","пергамент","шёлк","ткань","медь","цинк","алюминий","дуб","сосна","фанера","оргалит","двп","дсп","наждачная бумага","крафт-бумага","ватман","калька","береста","кожа","кость","слоновая кость","перламутр","мрамор","гранит","известняк","гипс","терракота","майолика"],
        "techniques": ["масло","акварель","гуашь","темпера","пастель","уголь","карандаш","графит","тушь","сепия","сангина","мел","акрил","чернила","белила","лак","золото","серебро","бронза","эмаль","керамика","фарфор","гобелен","мозаика","литография","офорт","гравюра","ксилография","шелкография","тушь-сепия","акварель-сепия","белая гуашь","чёрный мел","итальянский карандаш","свинцовый карандаш","серебряный штифт","соус","бистр","лавис","акватинта","меццо-тинто","сухая игла","резцовая гравюра","пунктир"],
        "unknown_words": []
    }
    # Preserve the original default technique vocabulary.
    default["techniques"].insert(default["techniques"].index("резцовая гравюра"), "монотипия")
    if os.path.exists(DICTIONARY_FILE):
        with open(DICTIONARY_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        for k in default:
            if k not in saved:
                saved[k] = default[k]
        return saved
    return default


def save_dictionary(d):
    atomic_json(DICTIONARY_FILE, d)


def parse_medium_details(medium_text):
    if not medium_text:
        return {"material":"","techniques":[],"size":""}
    d = load_dictionary()
    before = json.dumps(d, ensure_ascii=False, sort_keys=True)
    text = medium_text.strip().rstrip(".")
    size = ""
    for p in [r'(\d+[,.]?\d*\s*[xх×]\s*\d+[,.]?\d*\s*(?:см|mm|мм|m|м)?)', r'(\d+[,.]?\d*\s*(?:см|mm|мм|m|м)\s*[xх×]\s*\d+[,.]?\d*\s*(?:см|mm|мм|m|м)?)', r'(\d+[,.]?\d*\s*[xх×]\s*\d+[,.]?\d*)']:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            size = m.group(1).strip()
            text = text.replace(m.group(0), "").strip().rstrip(",.").strip()
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
    if json.dumps(d, ensure_ascii=False, sort_keys=True) != before:
        save_dictionary(d)
    return {"material":material,"techniques":techniques,"size":size}


SEPARATOR_RE = re.compile(r"\s*[⸻⸺]\s*")
URL_RE = re.compile(r"https?://(?:(?!https?://)[^\s⸻⸺])+")
TAG_RE = re.compile(r"#(\w+)@\w+")


def parse_post(text):
    """Парсит пост, разделяя поля строго по ⸻."""
    if not text: return {}
    try:
        urls = URL_RE.findall(text)
        raw_tags = TAG_RE.findall(text)
        tc = URL_RE.sub(" ", text)
        tc = TAG_RE.sub("", tc)
        parts = [p.strip() for p in SEPARATOR_RE.split(tc) if p.strip()]
        if len(parts) < 4: return {}
        artist = re.sub(r"\s+", " ", parts[0])
        title = re.sub(r"\s+", " ", parts[1])
        medium = re.sub(r"\s+", " ", parts[2])
        museum = re.sub(r"\s+", " ", parts[3])
        if not artist or not title: return {}
        hist, desc = [], ""
        def is_provenance(value):
            if not value: return False
            lines = [l.strip() for l in value.split('\n') if l.strip()]
            if not lines: return False
            numbered = sum(1 for l in lines if re.match(r'^\d+\s*\)', l))
            return numbered > 0 and numbered >= len(lines) * 0.5
        for extra in parts[4:]:
            if re.match(r'^https?://', extra) or extra.startswith('#'): continue
            if is_provenance(extra):
                hist = [l.strip() for l in extra.split('\n') if l.strip()]
            else:
                desc_part = re.sub(r"\s*\n\s*", " ", extra).strip()
                if desc_part:
                    desc = desc + "\n\n" + desc_part if desc else desc_part
        md = parse_medium_details(medium)
        return {
            "artist": artist, "title": title, "medium": medium,
            "material": md["material"], "techniques": md["techniques"],
            "size": md["size"], "museum": museum, "history": hist,
            "description": desc, "urls": urls, "tags": sorted(set(raw_tags)),
            "raw": text, "creation_year": work_year(title) if title else None
        }
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return {}


def lower_first(text):
    return (text[:1].lower() + text[1:]) if text else text


def slugify(text):
    t = text.lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t).strip("-")
    return t[:60] or "post"


def plural_ru(n, one, two, five):
    n = abs(n) % 100
    if 11 <= n <= 19: return five
    n = n % 10
    if n == 1: return one
    if 2 <= n <= 4: return two
    return five


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f: return json.load(f)
    return default


def save_json(path, data):
    atomic_json(path, data)


__all__ = [
    'typo_ru', 'load_dictionary', 'save_dictionary', 'parse_medium_details',
    'SEPARATOR_RE', 'URL_RE', 'TAG_RE', 'parse_post', 'lower_first',
    'slugify', 'plural_ru', 'load_json', 'save_json',
]
