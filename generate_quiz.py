# -*- coding: utf-8 -*-
"""
Генератор страницы квиза для Old Picture Art.
Запуск: python generate_quiz.py
"""

import json
import os
import random
from html import escape as h

META_FILE = "posts_meta.json"
OUTPUT_DIR = "docs"

def generate_quiz_page():
    if not os.path.exists(META_FILE):
        print(f"Файл {META_FILE} не найден!")
        return
    
    with open(META_FILE, "r", encoding="utf-8") as f:
        all_posts = json.load(f)
    
    # Отбираем посты с изображениями
    valid_posts = [p for p in all_posts if p.get("images") and len(p["images"]) > 0]
    
    if len(valid_posts) < 4:
        print("Недостаточно постов для квиза")
        return
    
    html = f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a1a2e" media="(prefers-color-scheme: dark)">
<title>Квиз — Old Picture Art</title>
<link rel="stylesheet" href="style.css">
<style>
* {{ box-sizing: border-box; }}

.quiz-wrapper {{
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}}

.quiz-container {{
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  text-align: center;
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
}}

.quiz-painting {{
  max-width: 100%;
  max-height: 40vh;
  height: auto;
  width: auto;
  border-radius: 8px;
  box-shadow: 0 4px 20px var(--shadow);
  margin: 0.5rem auto;
  display: block;
  object-fit: contain;
}}

.quiz-answers {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
  margin: 0.75rem 0;
}}

.quiz-btn {{
  background: var(--card-bg);
  border: 2px solid var(--border);
  padding: 0.75rem 1rem;
  border-radius: 12px;
  cursor: pointer;
  font-size: 1rem;
  color: var(--text);
  transition: all .2s;
  font-family: inherit;
  white-space: normal;
  word-break: break-word;
  min-height: 3.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  line-height: 1.3;
}}

.quiz-btn:hover {{ border-color: var(--active); background: var(--border); }}
.quiz-btn.correct {{ border-color: #27ae60; background: rgba(39,174,96,.15); color: #27ae60; font-weight: 700; }}
.quiz-btn.wrong {{ border-color: var(--like-color); background: rgba(231,76,60,.15); color: var(--like-color); }}
.quiz-btn:disabled {{ pointer-events: none; opacity: 0.8; }}

.quiz-score {{
  font-size: 1.3rem;
  font-weight: 700;
  margin: 0.5rem 0;
  color: var(--active);
}}

.quiz-next {{ 
  display: none;
  background: var(--active);
  color: #fff;
  border: none;
  padding: .7rem 2rem;
  border-radius: 25px;
  cursor: pointer;
  font-size: 1rem;
  font-family: inherit;
  margin: 0.75rem auto;
  transition: opacity .2s;
}}

.quiz-next:hover {{ opacity: .8; }}

.quiz-result {{
  margin-top: 0.5rem;
  font-size: 1rem;
  color: var(--muted);
  min-height: 1.5rem;
}}

.quiz-reset-btn {{
  background: var(--reset-bg);
  color: var(--reset-text);
  border: none;
  padding: .5rem 1.5rem;
  border-radius: 20px;
  cursor: pointer;
  font-size: 0.95rem;
  font-family: inherit;
  margin: 0.75rem 0.5rem;
  transition: opacity .2s;
}}

.quiz-reset-btn:hover {{ opacity: .8; }}

.quiz-title {{
  font-style: italic;
  color: var(--muted);
  margin: 0.4rem 0;
  font-size: 0.95rem;
}}

.quiz-buttons {{
  margin-top: 0.5rem;
}}

/* Десктоп: большие экраны */
@media (min-width: 769px) {{
  .quiz-painting {{
    max-height: 45vh;
  }}
  
  .quiz-answers {{
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
  }}
  
  .quiz-btn {{
    font-size: 1.1rem;
    padding: 1rem;
  }}
  
  .quiz-score {{
    font-size: 1.5rem;
  }}
}}

/* Планшеты */
@media (max-width: 768px) {{
  .quiz-wrapper {{
    padding: 0.75rem;
  }}
  
  .quiz-painting {{
    max-height: 35vh;
  }}
  
  .quiz-answers {{
    grid-template-columns: repeat(2, 1fr);
    gap: 0.6rem;
  }}
  
  .quiz-btn {{
    font-size: 0.9rem;
    padding: 0.6rem;
    min-height: 3rem;
  }}
}}

/* Телефоны */
@media (max-width: 480px) {{
  .quiz-wrapper {{
    padding: 0.5rem;
  }}
  
  .quiz-container h1 {{
    font-size: 1.3rem;
    margin: 0.3rem 0;
  }}
  
  .quiz-painting {{
    max-height: 30vh;
    margin: 0.3rem auto;
  }}
  
  .quiz-answers {{
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }}
  
  .quiz-btn {{
    font-size: 0.85rem;
    padding: 0.6rem 0.8rem;
    min-height: 2.8rem;
    border-radius: 8px;
  }}
  
  .quiz-score {{
    font-size: 1.1rem;
  }}
  
  .quiz-title {{
    font-size: 0.85rem;
  }}
  
  .quiz-next {{
    padding: 0.6rem 1.5rem;
    font-size: 0.9rem;
  }}
  
  .quiz-reset-btn {{
    font-size: 0.8rem;
    padding: 0.4rem 1rem;
  }}
}}

/* Очень маленькие экраны */
@media (max-width: 360px) {{
  .quiz-painting {{
    max-height: 25vh;
  }}
  
  .quiz-btn {{
    font-size: 0.8rem;
    padding: 0.5rem;
    min-height: 2.5rem;
  }}
}}
</style>
</head><body>
<a href="index.html" class="back" style="padding:1rem;display:inline-flex;align-items:center;gap:4px"><span class="icon-back"></span> На главную</a>
<div class="quiz-wrapper">
  <div class="quiz-container">
    <h1>Квиз: Угадай художника</h1>
    <p class="quiz-score">Счёт: <span id="score">0</span> / <span id="total">0</span></p>
    <img id="quiz-image" class="quiz-painting" src="" alt="Картина" style="display:none">
    <p id="quiz-title" class="quiz-title"></p>
    <div id="quiz-answers" class="quiz-answers"></div>
    <p id="quiz-feedback" class="quiz-result"></p>
    <button id="quiz-next" class="quiz-next" onclick="newQuestion()">Следующий вопрос</button>
    <div class="quiz-buttons">
      <button class="random-btn" onclick="startNewGame()">Новая игра</button>
      <button class="quiz-reset-btn" onclick="resetQuiz()">Сбросить счёт</button>
    </div>
  </div>
</div>
<script>
const ALL_POSTS = {json.dumps(valid_posts, ensure_ascii=False)};

// Восстановление прогресса квиза
let saved = JSON.parse(localStorage.getItem('quizProgress') || '{{"score":0,"total":0}}');
let score = saved.score || 0;
let total = saved.total || 0;
let currentPost = null;

document.getElementById('score').textContent = score;
document.getElementById('total').textContent = total;

function shuffle(arr) {{
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {{
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
    }}
    return a;
}}

function newQuestion() {{
    document.getElementById('quiz-feedback').textContent = '';
    document.getElementById('quiz-next').style.display = 'none';
    document.querySelectorAll('.quiz-btn').forEach(b => b.disabled = false);
    
    const available = ALL_POSTS.filter(p => p.artist && p.images && p.images.length > 0);
    if (available.length < 4) {{
        document.getElementById('quiz-feedback').textContent = 'Недостаточно картин для игры';
        return;
    }}
    
    currentPost = available[Math.floor(Math.random() * available.length)];
    const artists = new Set([currentPost.artist]);
    
    while (artists.size < 4) {{
        const r = available[Math.floor(Math.random() * available.length)];
        artists.add(r.artist);
    }}
    
    const shuffledArtists = shuffle([...artists]);
    
    document.getElementById('quiz-image').src = currentPost.images[0];
    document.getElementById('quiz-image').style.display = 'block';
    document.getElementById('quiz-title').textContent = currentPost.title || '';
    
    const answersDiv = document.getElementById('quiz-answers');
    answersDiv.innerHTML = shuffledArtists.map(artist => 
        '<button class="quiz-btn" onclick="checkAnswer(this, \\'' + artist.replace(/'/g, "\\'") + '\\')">' + artist + '</button>'
    ).join('');
}}

function checkAnswer(btn, answer) {{
    total++;
    document.getElementById('total').textContent = total;
    
    const correct = answer === currentPost.artist;
    const allBtns = document.querySelectorAll('.quiz-btn');
    allBtns.forEach(b => b.disabled = true);
    
    if (correct) {{
        score++;
        document.getElementById('score').textContent = score;
        btn.classList.add('correct');
        document.getElementById('quiz-feedback').innerHTML = '✓ Правильно! <a href="' + currentPost.filename + '" style="color:var(--active)">Посмотреть картину</a>';
    }} else {{
        btn.classList.add('wrong');
        allBtns.forEach(b => {{ if (b.textContent === currentPost.artist) b.classList.add('correct'); }});
        document.getElementById('quiz-feedback').innerHTML = '✗ Неправильно. Правильный ответ: ' + currentPost.artist + ' <a href="' + currentPost.filename + '" style="color:var(--active)">Посмотреть картину</a>';
    }}
    
    localStorage.setItem('quizProgress', JSON.stringify({{score: score, total: total}}));
    document.getElementById('quiz-next').style.display = 'inline-block';
}}

function startNewGame() {{
    score = 0;
    total = 0;
    document.getElementById('score').textContent = '0';
    document.getElementById('total').textContent = '0';
    document.getElementById('quiz-feedback').textContent = '';
    localStorage.removeItem('quizProgress');
    newQuestion();
}}

function resetQuiz() {{
    score = 0;
    total = 0;
    document.getElementById('score').textContent = '0';
    document.getElementById('total').textContent = '0';
    document.getElementById('quiz-feedback').textContent = '';
    localStorage.removeItem('quizProgress');
    document.getElementById('quiz-next').style.display = 'none';
    document.getElementById('quiz-image').style.display = 'none';
    document.getElementById('quiz-title').textContent = '';
    document.getElementById('quiz-answers').innerHTML = '';
}}

newQuestion();
</script>
</body></html>"""
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "quiz.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"Квиз сохранён: {output_path}")

if __name__ == "__main__":
    generate_quiz_page()