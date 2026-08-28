# -*- coding: utf-8 -*-
"""
Общие части HTML для всех генераторов сайта (build_site.py, generate_quiz.py,
generate_timeline.py, generate_map.py).

Смысл файла: раньше <head>, переключатель темы и служебные скрипты были
скопированы в четырёх местах и разъезжались между страницами (например,
на квизе и таймлайне тема вообще не применялась). Теперь это одно место.

ВАЖНО: функции возвращают готовые строки, поэтому их результат можно
безопасно подставлять в f-строки генераторов — двойные фигурные скобки
экранировать не нужно.
"""

SITE_NAME = "Old Picture Art"
BASE_URL = "https://denchest.github.io/Site-Oldpictureart"

# Фавикон: рамка с картиной. Инлайн-SVG, отдельного файла не требует,
# поэтому браузер больше не долбится в несуществующий /favicon.ico.
FAVICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' rx='6' fill='%232f2f3a'/%3E"
    "%3Crect x='6' y='7' width='20' height='18' rx='2' fill='%23fafafa'/%3E"
    "%3Cpath d='M8 21l5-6 4 4 3-3 4 5z' fill='%236b8e6b'/%3E"
    "%3Ccircle cx='20' cy='12' r='2' fill='%23e0b050'/%3E"
    "%3C/svg%3E"
)

# Бутстрап темы. Обязан стоять в <head> ДО отрисовки body, иначе тёмная тема
# «моргает» белым на каждой загрузке. Если сохранённой темы нет — берём
# системную (prefers-color-scheme), она же объявлена в meta theme-color.
THEME_BOOT = (
    "<script>(function(){try{var t=localStorage.getItem('theme');"
    "if(t!=='light'&&t!=='dark'){t=(window.matchMedia&&"
    "window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';}"
    "document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>"
)

# Общий скрипт: переключение темы, кнопка «наверх», закрытие по Escape.
COMMON_JS = """<script>
function toggleTheme(){
  try{
    var r=document.documentElement;
    var n=r.getAttribute('data-theme')==='dark'?'light':'dark';
    r.setAttribute('data-theme',n);
    localStorage.setItem('theme',n);
    document.querySelectorAll('[data-theme-toggle]').forEach(function(b){
      b.setAttribute('aria-pressed', n==='dark'?'true':'false');
    });
  }catch(e){}
}
(function(){
  var btn=document.querySelector('.scroll-top');
  if(!btn) return;
  var ticking=false;
  function upd(){ btn.classList.toggle('visible', window.scrollY>400); ticking=false; }
  window.addEventListener('scroll', function(){
    if(!ticking){ ticking=true; window.requestAnimationFrame(upd); }
  }, {passive:true});
  upd();
})();
</script>"""


def head_common(title, description="", og_image="", canonical="", og_type="website", extra=""):
    """Единый <head> для всех страниц сайта."""
    desc = (description or f"{SITE_NAME} — галерея картин из старых музейных собраний.").strip()
    desc = desc.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    title_attr = title.replace('"', "&quot;")
    og_img_tag = f'\n<meta property="og:image" content="{og_image}">' if og_image else ""
    canon_tag = f'\n<link rel="canonical" href="{canonical}">' if canonical else ""
    return f"""<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#eceef1" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#14181c" media="(prefers-color-scheme: dark)">
<meta name="description" content="{desc}">
<meta name="color-scheme" content="light dark">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta property="og:title" content="{title_attr}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{SITE_NAME}">{og_img_tag}
<meta name="twitter:card" content="summary_large_image">{canon_tag}
<title>{title}</title>
<link rel="icon" href="{FAVICON}">
<link rel="apple-touch-icon" href="{FAVICON}">
<link rel="manifest" href="manifest.json">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Old+Standard+TT:ital,wght@0,400;0,700;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Old+Standard+TT:ital,wght@0,400;0,700;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="style.css">{extra}
{THEME_BOOT}"""


def scroll_top_button():
    """Кнопка «наверх». type=button обязателен, иначе внутри формы это submit."""
    return ('<button type="button" class="scroll-top" onclick="scrollToTop()" '
            'aria-label="Наверх" title="Наверх"><span class="icon-arrow-up" aria-hidden="true"></span></button>')


def theme_button(extra_class=""):
    """Кнопка переключения темы для страниц без сайдбара."""
    cls = ("theme-toggle " + extra_class).strip()
    return (f'<button type="button" class="{cls}" data-theme-toggle onclick="toggleTheme()" '
            'aria-label="Переключить тему" title="Светлая / тёмная тема">'
            '<span class="icon-theme-toggle" aria-hidden="true"></span></button>')


SCROLL_TOP_JS = """<script>
function scrollToTop(){
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  window.scrollTo({top:0, behavior: reduce ? 'auto' : 'smooth'});
}
</script>"""
