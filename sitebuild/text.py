# -*- coding: utf-8 -*-
"""Разбор текста постов: картина, материал и техника; общие мелочи — slugify, склонения, JSON.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
import re
import json
from site_common import (work_year, typo_ru)
import logging
from .config import DICTIONARY_FILE

logger = logging.getLogger("build_site")

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

__all__ = [
    'typo_ru',
    'load_dictionary',
    'save_dictionary',
    'parse_medium_details',
    'SEPARATOR_RE',
    'URL_RE',
    'TAG_RE',
    'parse_post',
    'lower_first',
    'slugify',
    'plural_ru',
    'load_json',
    'save_json',
]
