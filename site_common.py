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
  function upd(){
    var max = document.documentElement.scrollHeight - window.innerHeight;
    var y = window.scrollY;
    btn.classList.toggle('visible', y > 400);
    // Кольцо вокруг стрелки показывает долю пройденной страницы
    btn.style.setProperty('--progress', String(max > 0 ? Math.min(100, Math.round(y / max * 100)) : 0));
    ticking=false;
  }
  window.addEventListener('scroll', function(){
    if(!ticking){ ticking=true; window.requestAnimationFrame(upd); }
  }, {passive:true});
  window.addEventListener('resize', upd, {passive:true});
  upd();
})();
</script>"""


def style_version():
    """Короткий отпечаток содержимого style.css.

    GitHub Pages отдаёт css с заголовками кэширования, и браузер может
    держать старую версию файла ещё долго после публикации: разметка уже
    новая, а стили прежние — сайт выглядит сломанным ровно до Ctrl+F5.
    Отпечаток в адресе меняется вместе с файлом, поэтому браузер сам
    забирает свежий, а неизменившийся продолжает брать из кэша.
    """
    import hashlib, os
    path = os.path.join("docs", "style.css")
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:8]
    except OSError:
        return "0"


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
<link rel="stylesheet" href="style.css?v={style_version()}">{extra}
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


# Лупа: полноэкранный просмотр картины.
#
# Раньше клик по картине просто открывал JPEG в соседней вкладке — браузер
# показывал его как файл, без масштабирования по месту и без подписи. Для
# сайта о живописи это главный экран: сюда возвращаются, чтобы рассмотреть
# мазок. Ссылка на оригинал остаётся в разметке и работает без JS — скрипт
# только перехватывает клик.
LUPA_JS = """<script>
(function () {
  var links = [].slice.call(document.querySelectorAll('a.painting-link'));
  if (!links.length) return;

  var box = null, stage = null, img = null, capTitle = null, capMeta = null,
      scaleOut = null, btnPrev = null, btnNext = null, btnIn = null, btnOut = null;
  var idx = 0, scale = 1, fit = 1, tx = 0, ty = 0, natW = 0, natH = 0;
  var opener = null, pointers = {}, pinch = null, dragged = false;

  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function build() {
    box = document.createElement('div');
    box.className = 'lupa';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-label', 'Просмотр картины');
    box.hidden = true;
    box.innerHTML =
      '<div class="lupa-bar">' +
        '<div class="lupa-caption"><b></b><span></span></div>' +
        '<div class="lupa-tools">' +
          '<button type="button" class="lupa-btn" data-act="prev" aria-label="Предыдущая картина" title="Предыдущая">‹</button>' +
          '<button type="button" class="lupa-btn" data-act="next" aria-label="Следующая картина" title="Следующая">›</button>' +
          '<span class="lupa-scale"></span>' +
          '<button type="button" class="lupa-btn" data-act="out" aria-label="Уменьшить" title="Уменьшить">−</button>' +
          '<button type="button" class="lupa-btn" data-act="in" aria-label="Увеличить" title="Увеличить">+</button>' +
          '<button type="button" class="lupa-btn" data-act="fit" aria-label="Вписать целиком" title="Вписать целиком">⤢</button>' +
          '<button type="button" class="lupa-btn" data-act="close" aria-label="Закрыть" title="Закрыть (Esc)">✕</button>' +
        '</div>' +
      '</div>' +
      '<div class="lupa-stage"><img class="lupa-img" alt=""></div>' +
      '<p class="lupa-hint">Колесо — увеличение, перетаскивание — сдвиг, двойной щелчок — во всю величину, Esc — закрыть</p>';
    document.body.appendChild(box);

    stage = box.querySelector('.lupa-stage');
    img = box.querySelector('.lupa-img');
    capTitle = box.querySelector('.lupa-caption b');
    capMeta = box.querySelector('.lupa-caption span');
    scaleOut = box.querySelector('.lupa-scale');
    btnPrev = box.querySelector('[data-act="prev"]');
    btnNext = box.querySelector('[data-act="next"]');
    btnIn = box.querySelector('[data-act="in"]');
    btnOut = box.querySelector('[data-act="out"]');

    box.addEventListener('click', function (e) {
      var act = e.target.getAttribute && e.target.getAttribute('data-act');
      if (act === 'close') return close();
      if (act === 'in') return zoomAt(center(), 1.4);
      if (act === 'out') return zoomAt(center(), 1 / 1.4);
      if (act === 'fit') return apply(fitScale(), true);
      if (act === 'prev') return show(idx - 1);
      if (act === 'next') return show(idx + 1);
      // щелчок мимо картины закрывает — привычное поведение просмотрщиков
      if (e.target === stage && !dragged) close();
    });

    stage.addEventListener('wheel', function (e) {
      e.preventDefault();
      zoomAt({x: e.clientX, y: e.clientY}, e.deltaY < 0 ? 1.18 : 1 / 1.18);
    }, {passive: false});

    stage.addEventListener('dblclick', function (e) {
      if (Math.abs(scale - fit) < 0.01) zoomAt({x: e.clientX, y: e.clientY}, 1 / fit);
      else apply(fitScale(), true);
    });

    stage.addEventListener('pointerdown', onDown);
    stage.addEventListener('pointermove', onMove);
    stage.addEventListener('pointerup', onUp);
    stage.addEventListener('pointercancel', onUp);

    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', function () { if (!box.hidden) apply(fitScale(), false); });
  }

  function center() {
    var r = stage.getBoundingClientRect();
    return {x: r.left + r.width / 2, y: r.top + r.height / 2};
  }

  function fitScale() {
    var r = stage.getBoundingClientRect();
    if (!natW || !natH) return 1;
    fit = Math.min((r.width - 32) / natW, (r.height - 32) / natH);
    if (!isFinite(fit) || fit <= 0) fit = 1;
    return fit;
  }

  // Картину нельзя утащить за край: если она меньше окна — держим по центру,
  // если больше — не даём образоваться пустому полю.
  function clamp(s) {
    var r = stage.getBoundingClientRect();
    var w = natW * s, hgt = natH * s;
    tx = w <= r.width ? (r.width - w) / 2 : Math.min(0, Math.max(r.width - w, tx));
    ty = hgt <= r.height ? (r.height - hgt) / 2 : Math.min(0, Math.max(r.height - hgt, ty));
  }

  function paint() {
    img.style.transform = 'translate(' + tx.toFixed(1) + 'px,' + ty.toFixed(1) + 'px) scale(' + scale + ')';
    scaleOut.textContent = Math.round(scale * 100) + '%';
    var max = maxScale();
    btnIn.disabled = scale >= max - 0.001;
    btnOut.disabled = scale <= fit + 0.001;
    stage.classList.toggle('zoomable', Math.abs(scale - fit) < 0.01);
  }

  function maxScale() { return Math.max(1, fit * 8); }

  function apply(s, eased) {
    scale = Math.min(maxScale(), Math.max(fitScale(), s));
    clamp(scale);
    if (eased && !reduce) {
      img.classList.add('eased');
      setTimeout(function () { img.classList.remove('eased'); }, 240);
    }
    paint();
  }

  function zoomAt(pt, factor) {
    var r = stage.getBoundingClientRect();
    var px = pt.x - r.left, py = pt.y - r.top;
    var ix = (px - tx) / scale, iy = (py - ty) / scale;
    var s = Math.min(maxScale(), Math.max(fitScale(), scale * factor));
    tx = px - ix * s;
    ty = py - iy * s;
    scale = s;
    clamp(scale);
    paint();
  }

  function onDown(e) {
    pointers[e.pointerId] = {x: e.clientX, y: e.clientY};
    stage.setPointerCapture(e.pointerId);
    dragged = false;
    var ids = Object.keys(pointers);
    if (ids.length === 2) {
      pinch = {d: dist(pointers[ids[0]], pointers[ids[1]]), s: scale};
    } else {
      stage.classList.add('dragging');
    }
  }

  function onMove(e) {
    var p = pointers[e.pointerId];
    if (!p) return;
    var ids = Object.keys(pointers);
    if (ids.length === 2 && pinch) {
      pointers[e.pointerId] = {x: e.clientX, y: e.clientY};
      var a = pointers[ids[0]], b = pointers[ids[1]];
      var d = dist(a, b);
      if (pinch.d > 0) {
        var mid = {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
        var want = pinch.s * (d / pinch.d);
        zoomAt(mid, want / scale);
      }
      return;
    }
    var dx = e.clientX - p.x, dy = e.clientY - p.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) dragged = true;
    tx += dx; ty += dy;
    pointers[e.pointerId] = {x: e.clientX, y: e.clientY};
    clamp(scale);
    paint();
  }

  function onUp(e) {
    delete pointers[e.pointerId];
    if (Object.keys(pointers).length < 2) pinch = null;
    stage.classList.remove('dragging');
  }

  function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }

  function onKey(e) {
    if (!box || box.hidden) return;
    var k = e.key;
    if (k === 'Escape') { e.preventDefault(); return close(); }
    if (k === '+' || k === '=') { e.preventDefault(); return zoomAt(center(), 1.4); }
    if (k === '-' || k === '_') { e.preventDefault(); return zoomAt(center(), 1 / 1.4); }
    if (k === '0') { e.preventDefault(); return apply(fitScale(), true); }
    if (k === 'ArrowLeft') { e.preventDefault(); return links.length > 1 ? show(idx - 1) : pan(60, 0); }
    if (k === 'ArrowRight') { e.preventDefault(); return links.length > 1 ? show(idx + 1) : pan(-60, 0); }
    if (k === 'ArrowUp') { e.preventDefault(); return pan(0, 60); }
    if (k === 'ArrowDown') { e.preventDefault(); return pan(0, -60); }
    if (k === 'Tab') {                       // фокус не должен уходить на страницу под лупой
      var f = box.querySelectorAll('button:not([disabled])');
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }

  function pan(dx, dy) { tx += dx; ty += dy; clamp(scale); paint(); }

  function show(i) {
    if (i < 0) i = links.length - 1;
    if (i >= links.length) i = 0;
    idx = i;
    var a = links[idx];
    var thumb = a.querySelector('img');
    var hires = a.getAttribute('href');

    capTitle.textContent = a.getAttribute('data-title') || (thumb ? thumb.alt : '');
    capMeta.textContent = a.getAttribute('data-meta') || '';
    img.alt = thumb ? thumb.alt : '';
    btnPrev.hidden = btnNext.hidden = links.length < 2;

    // Сначала показываем ту же картинку, что уже на странице — она в кэше,
    // и лупа открывается мгновенно. Оригинал подгружаем следом и подменяем,
    // сохранив видимый размер.
    var small = (thumb && (thumb.currentSrc || thumb.src)) || hires;
    img.src = small;
    var ready = function () {
      natW = img.naturalWidth; natH = img.naturalHeight;
      apply(fitScale(), false);
      loadHires(hires);
    };
    if (img.complete && img.naturalWidth) ready();
    else img.onload = ready;
  }

  function loadHires(src) {
    if (!src || src === img.src) return;
    var big = new Image();
    big.onload = function () {
      if (!big.naturalWidth) return;
      var k = natW ? big.naturalWidth / natW : 1;
      img.src = src;
      natW = big.naturalWidth; natH = big.naturalHeight;
      // при подмене картинка не должна дёрнуться: пересчитываем масштаб
      scale = scale / k; fit = fit / k;
      clamp(scale); paint();
    };
    big.src = src;
  }

  function open(i, from) {
    if (!box) build();
    opener = from || document.activeElement;
    box.hidden = false;
    document.body.style.overflow = 'hidden';
    show(i);
    var close_ = box.querySelector('[data-act="close"]');
    if (close_) close_.focus();
  }

  function close() {
    if (!box || box.hidden) return;
    box.hidden = true;
    document.body.style.overflow = '';
    img.src = '';
    if (opener && opener.focus) opener.focus();
  }

  links.forEach(function (a, i) {
    a.addEventListener('click', function (e) {
      // Ctrl/Cmd/средняя кнопка — пусть браузер откроет оригинал, как обычно
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      open(i, a);
    });
  });
})();
</script>"""


SCROLL_TOP_JS = """<script>
function scrollToTop(){
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  window.scrollTo({top:0, behavior: reduce ? 'auto' : 'smooth'});
}
</script>"""
