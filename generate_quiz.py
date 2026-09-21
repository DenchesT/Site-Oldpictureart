# -*- coding: utf-8 -*-
"""
Генератор страницы квиза для Old Picture Art.
Запуск: python generate_quiz.py
"""

import json
import os
import re
import statistics

from site_common import head_common, theme_button, site_footer, COMMON_JS, BASE_URL

META_FILE = "posts_meta.json"
OUTPUT_DIR = "docs"

# ------------------------------------------------------------ школы
# Варианты ответа раньше брались наугад из всех художников, и вопрос
# решался без знания живописи: к французскому пейзажу 1870-х рядом
# стояли Репин, Пуссен и Бирштадт, и лишнее отпадало само. Теперь
# варианты подбираются из той же школы и того же времени.
#
# Страны в записях канала нет, поэтому она записана здесь — по фамилии
# (слово из имени художника, как на сайте; «ё» можно писать как «е»).
# Новый художник: допишите фамилию в нужную строку. Забыли — не беда:
# русского узнаем по отчеству, а остальных квиз подберёт по годам и
# напомнит о себе строкой при сборке.
SCHOOLS = {
    # Франция — и те, кто стал французским художником (Сислей, Луар)
    "fr": """Сислей Дега Писсарро Кайботт Базиль Курбе Форен Гийомен Мане
             Ренуар Пуссен Брюн Луар Мартен Делакруа Тройон Лотрек Эллё
             Латур Дюриваж Буден Руар Милле Детай Моризо Ангран Пьетт""",
    "ru": """Репин Тархов Морозов Кузнецов Куинджи Юон Грабарь Серов
             Савицкий Левитан Брюллов Кустодиев Жуковский Сверчков
             Маковский Коровин""",
    # Германия, Австрия, Швейцария
    "de": "Фридрих Штук Либерман Слефогт Ходлер Альт Штерль",
    # Скандинавия и Финляндия
    "north": "Таулов Даль Петерссен Юхансен Каллела Цорн Осслунд",
    "us": "Гассам Бирштадт Кент Сарджент",
    "gb": "Гловер Каделл Констебл",
    "es": "Беруэте Мейфрен Рузиньол",
    "it": "Дзандоменеги",
    # Нидерланды и Бельгия
    "nl": "Сегерс Гог Бош",
}

# Если своей школы на три варианта не хватает (британцев всего трое),
# добираем из близкой, а не из первой попавшейся.
NEAR = {
    "gb": ["us"], "us": ["gb"],
    "es": ["it", "fr"], "it": ["es", "fr"],
    "nl": ["de", "fr"], "de": ["north", "nl"], "north": ["de", "ru"],
    "fr": ["nl", "it", "es"], "ru": ["north"],
}

_SURNAME_SCHOOL = {w.lower().replace("ё", "е"): code
                   for code, names in SCHOOLS.items() for w in names.split()}
_PATRONYMIC = re.compile(r"(ович|евич|ьич|ична|овна|евна)$")


def _words(name):
    return re.findall(r"[а-яa-z]+", name.lower().replace("ё", "е"))


def school_of(artist):
    """Код школы художника или None, если он не записан и не узнаётся."""
    words = _words(artist)
    for w in words:
        if w in _SURNAME_SCHOOL:
            return _SURNAME_SCHOOL[w]
    if any(_PATRONYMIC.search(w) for w in words):
        return "ru"
    return None


def year_of(post):
    m = re.search(r"\d{4}", str(post.get("creation_year") or ""))
    return int(m.group()) if m else None


def quiz_data(all_posts):
    """Посты для квиза и сведения о художниках для подбора вариантов.

    Записи, где авторов несколько («Анонимные художники, Феликс Милиус…»),
    в квиз не идут: ответ в них угадывается по длине кнопки, а вариантом
    к чужой картине такая строчка выглядит нелепо.
    """
    posts = [p for p in all_posts
             if p.get("images") and p.get("artist") and "," not in p["artist"]]
    years = {}
    for p in posts:
        y = year_of(p)
        if y:
            years.setdefault(p["artist"], []).append(y)

    artists, unknown = {}, []
    for a in sorted({p["artist"] for p in posts}):
        code = school_of(a)
        if code is None:
            unknown.append(a)
        ys = years.get(a)
        artists[a] = [code, int(statistics.median(ys)) if ys else None]

    items = [{"artist": p["artist"],
              "title": p.get("title", ""),
              "filename": p.get("filename", ""),
              "images": p["images"][:1],
              "y": year_of(p)}
             for p in posts]
    return items, artists, unknown

def generate_quiz_page():
    if not os.path.exists(META_FILE):
        print(f"Файл {META_FILE} не найден!")
        return
    
    with open(META_FILE, "r", encoding="utf-8") as f:
        all_posts = json.load(f)
    
    # В страницу кладём только то, чем квиз пользуется. Раньше сюда
    # целиком уезжала база постов — со всеми описаниями, ссылками на
    # источники, размерами, тегами и путями к оригиналам: 286 КБ из 473 КБ
    # веса страницы ради имени художника и адреса одной картинки.
    valid_posts, artists, unknown = quiz_data(all_posts)
    for a in unknown:
        print(f"Квиз: не знаю, из какой школы «{a}» — допишите фамилию в SCHOOLS "
              f"в generate_quiz.py (пока варианты к нему подбираются по годам)")

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

.quiz-stage {{
  /* Постоянная высота. Раньше картина просто меняла размер от вопроса
     к вопросу, и вместе с ней прыгали вверх-вниз кнопки ответов: палец
     уже летел к нужной, а под ним оказывалась соседняя. */
  height: 35vh;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;
}}

.quiz-painting {{
  max-width: 100%;
  max-height: 100%;
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
  
  .quiz-stage {{
    height: 40vh;
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
  .quiz-stage {{
    height: 30vh;
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
  
  .quiz-stage {{
    height: 25vh;
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
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
<div class="quiz-wrapper">
  <div class="quiz-container">
    <h1>Квиз: угадай художника</h1>
    <p class="quiz-score">Счёт: <span id="score">0</span> / <span id="total">0</span></p>
    <div class="quiz-stage"><img id="quiz-image" class="quiz-painting" alt="" hidden src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"></div>
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
{site_footer()}
{COMMON_JS}
<script>
const ALL_POSTS = {json.dumps(valid_posts, ensure_ascii=False)};
// художник → [школа, год середины его работ на сайте]
const ARTISTS = {json.dumps(artists, ensure_ascii=False)};
const NEAR = {json.dumps(NEAR)};

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

// Картины идут колодой: пока не показаны все, ни одна не повторяется.
// Раньше каждая бралась наугад заново, и одна и та же могла выпасть
// дважды подряд, пока другие не выпадали ни разу.
let deck = [];
function nextPost(available) {{
    if (!deck.length) {{
        deck = shuffle(available);
        // новая колода не начинается с картины, которой кончилась старая
        if (currentPost && deck.length > 1 && deck[deck.length - 1] === currentPost) deck.unshift(deck.pop());
    }}
    return deck.pop();
}}

// Три неверных варианта: сначала художники той же школы и близкого
// времени, потом соседней школы. Щепотка случайности — чтобы к одной
// картине не выпадала каждый раз одна и та же тройка.
function pickOthers(post) {{
    const own = ARTISTS[post.artist] || [null, null];
    const school = own[0];
    const year = post.y || own[1];
    return Object.keys(ARTISTS)
        .filter(a => a !== post.artist)
        .map(a => {{
            const [s, y] = ARTISTS[a];
            let score = (school && s) ? (s === school ? 0 : (NEAR[school] || []).includes(s) ? 60 : 150) : 80;
            score += (year && y) ? Math.min(Math.abs(y - year), 150) * 0.6 : 40;
            score += Math.random() * 40;
            return [score, a];
        }})
        .sort((p, q) => p[0] - q[0])
        .slice(0, 3)
        .map(x => x[1]);
}}

function newQuestion() {{
    const feedback = document.getElementById('quiz-feedback');
    feedback.textContent = '';
    document.getElementById('quiz-next').style.display = 'none';

    const available = ALL_POSTS.filter(p => p.artist && p.images && p.images.length > 0);
    if (available.length < 4 || Object.keys(ARTISTS).length < 4) {{
        feedback.textContent = 'Недостаточно картин для игры';
        return;
    }}

    currentPost = nextPost(available);
    const options = shuffle([currentPost.artist].concat(pickOthers(currentPost)));

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
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    
    print(f"Квиз сохранён: {output_path}")

if __name__ == "__main__":
    generate_quiz_page()