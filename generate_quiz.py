# -*- coding: utf-8 -*-
"""
Генератор страницы квиза для Old Picture Art.
Запуск: python generate_quiz.py
"""

import json
import os
import random
from html import escape as h

from site_common import head_common, theme_button, COMMON_JS, BASE_URL

META_FILE = "posts_meta.json"
OUTPUT_DIR = "docs"

def generate_quiz_page():
    if not os.path.exists(META_FILE):
        print(f"Файл {META_FILE} не найден!")
        return
    
    with open(META_FILE, "r", encoding="utf-8") as f:
        all_posts = json.load(f)
    
    valid_posts = [p for p in all_posts if p.get("images") and len(p["images"]) > 0]
    
    if len(valid_posts) < 4:
        print("Недостаточно постов для квиза")
        return
    
    head = head_common(
        title="Квиз — Old Picture Art",
        description="Угадайте художника по картине: небольшая игра по коллекции Old Picture Art.",
        canonical=f"{BASE_URL}/quiz.html",
    )

    html = f"""<!DOCTYPE html>
<html lang="ru" data-theme="light"><head>
{head}
<style>
* {{ box-sizing: border-box; }}

.quiz-wrapper {{
  max-width: 900px;
  margin: 0 auto;
  padding: 0 1rem 0.5rem;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}}

.quiz-container {{
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  text-align: center;
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
  gap: 0.4rem;
}}

.quiz-container h1 {{
  font-size: 1.4rem;
  margin: 0;
}}

.quiz-painting {{
  max-width: 100%;
  max-height: 35vh;
  height: auto;
  width: auto;
  border-radius: 8px;
  box-shadow: 0 4px 20px var(--shadow);
  margin: 0 auto;
  display: block;
  object-fit: contain;
}}

.quiz-answers {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
  margin: 0;
}}

.quiz-btn {{
  background: var(--card-bg);
  border: 2px solid var(--border);
  padding: 0.5rem 0.8rem;
  border-radius: 10px;
  cursor: pointer;
  font-size: 0.9rem;
  color: var(--text);
  transition: all .2s;
  font-family: inherit;
  white-space: normal;
  word-break: break-word;
  min-height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  line-height: 1.2;
}}

.quiz-btn:hover {{ border-color: var(--active); background: var(--border); }}
.quiz-btn.correct {{ border-color: #27ae60; background: rgba(39,174,96,.15); color: #27ae60; font-weight: 700; }}
.quiz-btn.wrong {{ border-color: var(--like-color); background: rgba(231,76,60,.15); color: var(--like-color); }}
.quiz-btn:disabled {{ pointer-events: none; opacity: 0.8; }}

.quiz-score {{
  font-size: 1rem;
  font-weight: 700;
  margin: 0;
  color: var(--active);
}}

.quiz-next {{ 
  display: none;
  background: var(--active);
  color: #fff;
  border: none;
  padding: 0.4rem 1.5rem;
  border-radius: 20px;
  cursor: pointer;
  font-size: 0.9rem;
  font-family: inherit;
  margin: 0 auto;
  transition: opacity .2s;
}}

.quiz-next:hover {{ opacity: .8; }}

.quiz-result {{
  font-size: 0.85rem;
  color: var(--muted);
  min-height: 1.2rem;
  margin: 0;
}}

.quiz-reset-btn {{
  background: var(--reset-bg);
  color: var(--reset-text);
  border: none;
  padding: 0.3rem 1rem;
  border-radius: 20px;
  cursor: pointer;
  font-size: 0.8rem;
  font-family: inherit;
  margin: 0 0.3rem;
  transition: opacity .2s;
}}

.quiz-reset-btn:hover {{ opacity: .8; }}

.quiz-title {{
  font-style: italic;
  color: var(--muted);
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.2;
}}

.quiz-buttons {{
  margin: 0;
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0.3rem;
}}

.quiz-buttons .random-btn {{
  font-size: 0.85rem;
  padding: 0.3rem 1rem;
  margin: 0;
}}

/* Десктоп */
@media (min-width: 769px) {{
  .quiz-container {{
    justify-content: center;
  }}
  
  .quiz-painting {{
    max-height: 40vh;
  }}
  
  .quiz-answers {{
    gap: 0.75rem;
  }}
  
  .quiz-btn {{
    font-size: 1rem;
    padding: 0.75rem 1rem;
    min-height: 3rem;
  }}
  
  .quiz-container h1 {{
    font-size: 1.8rem;
  }}
  
  .quiz-score {{
    font-size: 1.2rem;
  }}
}}

/* Планшеты */
@media (max-width: 768px) {{
  .quiz-painting {{
    max-height: 30vh;
  }}
  
  .quiz-answers {{
    gap: 0.5rem;
  }}
  
  .quiz-btn {{
    font-size: 0.85rem;
    padding: 0.5rem 0.7rem;
    min-height: 2.5rem;
  }}
}}

/* Телефоны */
@media (max-width: 480px) {{
  .quiz-wrapper {{
    padding: 0 0.5rem 0.5rem;
  }}
  
  .quiz-container h1 {{
    font-size: 1.1rem;
  }}
  
  .quiz-painting {{
    max-height: 25vh;
  }}
  
  .quiz-answers {{
    grid-template-columns: 1fr;
    gap: 0.35rem;
  }}
  
  .quiz-btn {{
    font-size: 0.8rem;
    padding: 0.4rem 0.6rem;
    min-height: 2.2rem;
    border-radius: 8px;
  }}
  
  .quiz-score {{
    font-size: 0.9rem;
  }}
  
  .quiz-title {{
    font-size: 0.75rem;
  }}
  
  .quiz-next {{
    padding: 0.35rem 1.2rem;
    font-size: 0.8rem;
  }}
  
  .quiz-result {{
    font-size: 0.75rem;
  }}
  
  .quiz-reset-btn {{
    font-size: 0.7rem;
    padding: 0.25rem 0.7rem;
  }}
  
  .quiz-buttons .random-btn {{
    font-size: 0.75rem;
    padding: 0.25rem 0.8rem;
  }}
}}
.quiz-topbar {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; padding: .4rem 1rem; }}
</style>
</head><body class="quiz-page">
<div class="quiz-topbar">
  <a href="index.html" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
<div class="quiz-wrapper">
  <div class="quiz-container">
    <h1>Квиз: угадай художника</h1>
    <p class="quiz-score">Счёт: <span id="score">0</span> / <span id="total">0</span></p>
    <img id="quiz-image" class="quiz-painting" alt="" hidden src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7">
    <p id="quiz-title" class="quiz-title"></p>
    <div id="quiz-answers" class="quiz-answers"></div>
    <p id="quiz-feedback" class="quiz-result" role="status" aria-live="polite"></p>
    <button type="button" id="quiz-next" class="quiz-next" onclick="newQuestion()">Следующий вопрос</button>
    <div class="quiz-buttons">
      <button type="button" class="random-btn" onclick="startNewGame()">Новая игра</button>
      <button type="button" class="quiz-reset-btn" onclick="resetQuiz()">Сбросить счёт</button>
    </div>
  </div>
</div>
{COMMON_JS}
<script>
const ALL_POSTS = {json.dumps(valid_posts, ensure_ascii=False)};

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
    const feedback = document.getElementById('quiz-feedback');
    feedback.textContent = '';
    document.getElementById('quiz-next').style.display = 'none';

    const available = ALL_POSTS.filter(p => p.artist && p.images && p.images.length > 0);
    const uniqueArtists = new Set(available.map(p => p.artist));
    if (available.length < 4 || uniqueArtists.size < 2) {{
        feedback.textContent = 'Недостаточно картин для игры';
        return;
    }}

    currentPost = available[Math.floor(Math.random() * available.length)];

    // Варианты ответа. Раньше цикл крутился, пока не наберётся 4 разных
    // художника — при малом числе авторов это был вечный цикл и зависание.
    const others = shuffle([...uniqueArtists].filter(a => a !== currentPost.artist));
    const options = shuffle([currentPost.artist].concat(others.slice(0, 3)));

    const img = document.getElementById('quiz-image');
    img.src = currentPost.images[0];
    img.alt = 'Картина: ' + (currentPost.title || 'без названия');
    img.hidden = false;
    document.getElementById('quiz-title').textContent = currentPost.title || '';

    // Кнопки строим через DOM, а не склейкой HTML: имя художника с кавычкой
    // или угловой скобкой раньше ломало разметку и обработчик клика.
    const answersDiv = document.getElementById('quiz-answers');
    answersDiv.textContent = '';
    options.forEach(artist => {{
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'quiz-btn';
        b.textContent = artist;
        b.addEventListener('click', function() {{ checkAnswer(b, artist); }});
        answersDiv.appendChild(b);
    }});
}}

function checkAnswer(btn, answer) {{
    if (btn.disabled) return;
    total++;
    document.getElementById('total').textContent = total;

    const correct = answer === currentPost.artist;
    const allBtns = document.querySelectorAll('.quiz-btn');
    allBtns.forEach(b => b.disabled = true);

    const feedback = document.getElementById('quiz-feedback');
    feedback.textContent = '';
    if (correct) {{
        score++;
        document.getElementById('score').textContent = score;
        btn.classList.add('correct');
        feedback.appendChild(document.createTextNode('✓ Правильно! '));
    }} else {{
        btn.classList.add('wrong');
        allBtns.forEach(b => {{ if (b.textContent === currentPost.artist) b.classList.add('correct'); }});
        feedback.appendChild(document.createTextNode('✗ Неправильно. Правильный ответ: ' + currentPost.artist + '. '));
    }}
    const link = document.createElement('a');
    link.href = currentPost.filename;
    link.className = 'quiz-link';
    link.textContent = 'Посмотреть картину';
    feedback.appendChild(link);

    try {{ localStorage.setItem('quizProgress', JSON.stringify({{score: score, total: total}})); }} catch (e) {{}}
    document.getElementById('quiz-next').style.display = 'inline-block';
    document.getElementById('quiz-next').focus();
}}

function resetScore() {{
    score = 0;
    total = 0;
    document.getElementById('score').textContent = '0';
    document.getElementById('total').textContent = '0';
    document.getElementById('quiz-feedback').textContent = '';
    try {{ localStorage.removeItem('quizProgress'); }} catch (e) {{}}
}}

function startNewGame() {{
    resetScore();
    newQuestion();
}}

// «Сбросить счёт» обнуляет счёт, но оставляет игру идти.
// Раньше кнопка стирала картинку и варианты и оставляла пустой экран,
// с которого можно было выйти только через «Новую игру».
function resetQuiz() {{
    resetScore();
    newQuestion();
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