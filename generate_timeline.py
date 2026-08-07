"""
Генератор страницы таймлайна для Old Picture Art.
Запуск: python generate_timeline.py
"""

import json
import os
from collections import defaultdict
from html import escape as h

META_FILE = "posts_meta.json"
OUTPUT_DIR = "docs"

def generate_timeline_page():
    if not os.path.exists(META_FILE):
        print(f"Файл {META_FILE} не найден!")
        return
    
    with open(META_FILE, "r", encoding="utf-8") as f:
        all_posts = json.load(f)
    
    # Группируем по десятилетиям
    decades = defaultdict(list)
    for p in all_posts:
        cy = p.get("creation_year")
        if cy:
            decade = (cy // 10) * 10
            decades[decade].append(p)
    
    sorted_decades = sorted(decades.keys())
    
    # Данные для JavaScript
    timeline_data = {}
    for decade, posts in decades.items():
        timeline_data[str(decade)] = [
            {
                "artist": p["artist"],
                "title": p["title"],
                "year": p.get("creation_year", decade),
                "file": p["filename"],
                "thumb": p["thumbs"][0] if p.get("thumbs") else (p["images"][0] if p.get("images") else "")
            }
            for p in posts
        ]
    
    min_year = min(sorted_decades) if sorted_decades else 1400
    max_year = max(sorted_decades) + 9 if sorted_decades else 2024
    
    html = f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a2e" media="(prefers-color-scheme: dark)">
<title>Таймлайн — Old Picture Art</title>
<link rel="stylesheet" href="style.css">
<style>
.timeline-container {{ max-width: 1200px; margin: 0 auto; padding: 1.5rem; }}
.timeline-slider {{
  width: 100%; margin: 1.5rem 0; -webkit-appearance: none;
  height: 8px; border-radius: 4px; background: var(--border); outline: none;
}}
.timeline-slider::-webkit-slider-thumb {{
  -webkit-appearance: none; width: 24px; height: 24px;
  border-radius: 50%; background: var(--active); cursor: pointer; border: 2px solid var(--bg);
}}
.timeline-labels {{ display: flex; justify-content: space-between; font-size: .85rem; color: var(--muted); margin-bottom: .5rem; }}
.timeline-current {{ text-align: center; font-size: 2rem; font-weight: 700; color: var(--active); margin: 1rem 0; }}
.timeline-grid {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem; margin-top: 1.5rem;
}}
.timeline-card {{
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; text-decoration: none; color: var(--text);
  transition: transform .1s;
}}
.timeline-card:hover {{ transform: translateY(-3px); }}
.timeline-card img {{ width: 100%; aspect-ratio: 4/3; object-fit: cover; display: block; }}
.timeline-card-body {{ padding: .7rem; }}
.timeline-card-artist {{ font-weight: 700; font-size: .9rem; }}
.timeline-card-title {{ font-style: italic; color: var(--muted); font-size: .8rem; margin-top: .2rem; }}
.timeline-card-year {{ font-size: .75rem; color: var(--active); margin-top: .2rem; }}
.timeline-empty {{ text-align: center; color: var(--muted); padding: 2rem; font-size: 1.1rem; }}
</style>
</head><body>
<a href="index.html" class="back" style="padding:1rem;display:inline-flex;align-items:center;gap:4px"><span class="icon-back"></span> На главную</a>
<div class="timeline-container">
  <h1 style="text-align:center">Таймлайн картин</h1>
  <div class="timeline-labels"><span>{min_year}</span><span>{max_year}</span></div>
  <input type="range" class="timeline-slider" id="timeline-slider" min="{min_year}" max="{max_year}" value="{(min_year+max_year)//2}" step="10">
  <div class="timeline-current" id="timeline-current">{(min_year+max_year)//2}-е</div>
  <div class="timeline-grid" id="timeline-grid"></div>
</div>
<script>
const timelineData = {json.dumps(timeline_data, ensure_ascii=False)};

function getDecade(year) {{
    return Math.floor(year / 10) * 10;
}}

function updateTimeline(decade) {{
    document.getElementById('timeline-current').textContent = decade + '-е';
    
    const grid = document.getElementById('timeline-grid');
    const posts = timelineData[decade] || [];
    
    if (posts.length === 0) {{
        grid.innerHTML = '<div class="timeline-empty">Нет картин для этого десятилетия</div>';
        return;
    }}
    
    grid.innerHTML = posts.map(p => 
        '<a href="' + p.file + '" class="timeline-card">' +
        '<img src="' + (p.thumb || '') + '" alt="" loading="lazy">' +
        '<div class="timeline-card-body">' +
        '<div class="timeline-card-artist">' + p.artist + '</div>' +
        '<div class="timeline-card-title">' + p.title + '</div>' +
        '<div class="timeline-card-year">' + p.year + '</div>' +
        '</div></a>'
    ).join('');
}}

document.getElementById('timeline-slider').addEventListener('input', function() {{
    const year = parseInt(this.value);
    const decade = getDecade(year);
    updateTimeline(decade);
}});

// Инициализация
updateTimeline(getDecade({(min_year+max_year)//2}));
</script>
</body></html>"""
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "timeline.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"Таймлайн сохранён: {output_path}")

if __name__ == "__main__":
    generate_timeline_page()