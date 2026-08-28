# -*- coding: utf-8 -*-
"""
Генератор страницы таймлайна для Old Picture Art.
Запуск: python generate_timeline.py
"""

import json
import os
from collections import defaultdict
from html import escape as h

from site_common import head_common, theme_button, COMMON_JS, BASE_URL

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
        # Внутри десятилетия работы идут по возрастанию года создания:
        # раньше порядок был случайным — как легли посты в канале.
        posts = sorted(posts, key=lambda x: (x.get("creation_year") or decade, x.get("title", "")))
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

    # Стартовое значение выравниваем по десятилетию: раньше подпись под
    # ползунком показывала «1877-е» — года, а не десятилетия.
    getdecade_mid = ((min_year + max_year) // 2 // 10) * 10
    if sorted_decades and getdecade_mid not in decades:
        getdecade_mid = min(sorted_decades, key=lambda d: abs(d - getdecade_mid))

    head = head_common(
        title="Таймлайн — Old Picture Art",
        description=f"Картины по десятилетиям: от {min_year} до {max_year} года. Двигайте ползунок, чтобы увидеть эпоху.",
        canonical=f"{BASE_URL}/timeline.html",
    )

    html = f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
{head}
<style>
.timeline-topbar {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; padding: .4rem 1rem; }}
.timeline-slider {{
  width: 100%; margin: 1.5rem 0; -webkit-appearance: none; appearance: none;
  height: 8px; border-radius: 4px; background: var(--border); outline: none;
  touch-action: pan-y;
}}
.timeline-slider:focus-visible {{ outline: 2px solid var(--active); outline-offset: 4px; }}
.timeline-slider::-webkit-slider-thumb {{
  -webkit-appearance: none; width: 28px; height: 28px;
  border-radius: 50%; background: var(--active); cursor: pointer; border: 2px solid var(--bg);
}}
/* Firefox рисовал ползунок системным стилем — раньше правил для -moz- не было */
.timeline-slider::-moz-range-thumb {{
  width: 24px; height: 24px; border-radius: 50%;
  background: var(--active); cursor: pointer; border: 2px solid var(--bg);
}}
.timeline-slider::-moz-range-track {{ height: 8px; border-radius: 4px; background: var(--border); }}
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
</head><body class="timeline-page">
<div class="timeline-topbar">
  <a href="index.html" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
<div class="timeline-container">
  <h1 class="timeline-h1">Таймлайн картин</h1>
  <div class="timeline-labels"><span>{min_year}</span><span>{max_year}</span></div>
  <label class="visually-hidden" for="timeline-slider">Десятилетие</label>
  <input type="range" class="timeline-slider" id="timeline-slider" min="{min_year}" max="{max_year}"
         value="{getdecade_mid}" step="10" aria-describedby="timeline-current">
  <div class="timeline-current" id="timeline-current" role="status" aria-live="polite">{getdecade_mid // 10 * 10}-е</div>
  <div class="timeline-grid" id="timeline-grid"></div>
</div>
{COMMON_JS}
<script>
const timelineData = {json.dumps(timeline_data, ensure_ascii=False)};
const DEFAULT_YEAR = {getdecade_mid};

function getDecade(year) {{
    return Math.floor(year / 10) * 10;
}}

function updateTimeline(decade) {{
    document.getElementById('timeline-current').textContent = decade + '-е';

    const grid = document.getElementById('timeline-grid');
    const posts = timelineData[decade] || [];
    grid.textContent = '';

    if (posts.length === 0) {{
        const empty = document.createElement('div');
        empty.className = 'timeline-empty';
        empty.textContent = 'Нет картин для этого десятилетия';
        grid.appendChild(empty);
        return;
    }}

    // Карточки собираем через DOM: раньше имена и названия склеивались
    // в строку HTML, и кавычка или < в данных ломали вёрстку страницы.
    const frag = document.createDocumentFragment();
    posts.forEach(p => {{
        const a = document.createElement('a');
        a.href = p.file;
        a.className = 'timeline-card';

        const img = document.createElement('img');
        img.src = p.thumb || '';
        img.alt = (p.artist || '') + ' — ' + (p.title || '');
        img.loading = 'lazy';
        img.decoding = 'async';
        a.appendChild(img);

        const body = document.createElement('div');
        body.className = 'timeline-card-body';
        [['timeline-card-artist', p.artist], ['timeline-card-title', p.title], ['timeline-card-year', p.year]]
            .forEach(([cls, val]) => {{
                const d = document.createElement('div');
                d.className = cls;
                d.textContent = val == null ? '' : String(val);
                body.appendChild(d);
            }});
        a.appendChild(body);
        frag.appendChild(a);
    }});
    grid.appendChild(frag);
}}

const slider = document.getElementById('timeline-slider');

let savedDecade = null;
try {{ savedDecade = localStorage.getItem('timelineDecade'); }} catch (e) {{}}

const startYear = savedDecade && !isNaN(parseInt(savedDecade, 10)) ? parseInt(savedDecade, 10) : DEFAULT_YEAR;
slider.value = startYear;
updateTimeline(getDecade(parseInt(slider.value, 10)));

slider.addEventListener('input', function() {{
    const decade = getDecade(parseInt(this.value, 10));
    try {{ localStorage.setItem('timelineDecade', decade); }} catch (e) {{}}
    updateTimeline(decade);
}});
</script>
</body></html>"""
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "timeline.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"Таймлайн сохранён: {output_path}")

if __name__ == "__main__":
    generate_timeline_page()