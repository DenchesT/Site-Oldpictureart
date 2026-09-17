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

import json
import os

SITE_NAME = "Old Picture Art"

# Посещения — выставки и музеи из постов #выставка и #галерея.
# Раздела может не быть вовсе (пока таких постов не нашлось), поэтому
# ссылки на него в подвале и в сайдбаре появляются только вместе с файлом.
VISITS_FILE = "visits_meta.json"


OVERRIDES_FILE = "museum_overrides.json"


def load_overrides():
    """Ручной справочник музеев. Нужен и карте, и страницам посещений:
    в нём же живут подсказки «это то же место, что вот этот музей»."""
    try:
        with open(OVERRIDES_FILE, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except Exception:
        return {}


def name_head(name):
    """Название до первой запятой: город и раздел дописывают через запятую
    и в посте о походе, и в сведениях о картине."""
    return (name or "").split(",")[0].strip()


def same_place(a, b):
    """Одно ли это место.

    Сравниваем только начало названия и только по целым словам. Простого
    вхождения мало: «Волго-Вятский филиал ГМИИ им. А.С. Пушкина» содержит
    название московского музея, но это другой город и другое собрание.
    А вот «Эрмитаж» и «Государственный Эрмитаж» — одно и то же.
    """
    a, b = name_head(a).lower(), name_head(b).lower()
    if not a or not b:
        return False
    if a == b:
        return True
    long_, short = (a, b) if len(a) > len(b) else (b, a)
    if len(short) < 5:
        return False
    return long_.startswith(short + " ") or long_.endswith(" " + short)


def match_place(place, names):
    """Ищет место среди известных названий. Длинные проверяем первыми,
    чтобы «ГМИИ им. А.С. Пушкина» не перехватил отдел личных коллекций."""
    for n in sorted(names, key=len, reverse=True):
        if same_place(place, n):
            return n
    return ""


def visit_places(visits, museum_names):
    """Сводит места из постов о походах к названиям карточек на карте.

    Возвращает {место, как написано в посте: название на карте}. Если место
    совпало с музеем из собрания — берётся его полное название с городом,
    чтобы карточка на карте была одна. Если нет — место становится своей
    карточкой, и следующие походы туда же к ней и приписываются.
    """
    overrides = load_overrides()
    known = list(museum_names)
    out = {}
    for v in sorted(visits, key=lambda x: len(x.get("place") or ""), reverse=True):
        place = (v.get("place") or "").strip()
        if not place or place in out:
            continue
        alias = (overrides.get(place) or {}).get("same_as")
        if alias:
            out[place] = alias
            continue
        hit = match_place(place, known)
        if not hit:
            hit = name_head(place)
            known.append(hit)
        out[place] = hit
    return out


def has_visits():
    """Есть ли в собрании посещения. Читается на каждой странице, но файл
    крошечный, а держать флаг в памяти нельзя: генераторы карты, квиза и
    таймлайна — отдельные процессы, и о состоянии сборки они не знают."""
    try:
        with open(VISITS_FILE, encoding="utf-8") as f:
            return bool(json.load(f))
    except Exception:
        return False

# Свой домен. Пока пусто — сайт живёт по адресу github.io.
#
# Купили домен? Впишите его сюда без «https://» и без косой черты в конце,
# например "oldpictureart.ru", и пересоберите сайт. Адрес сам подставится
# в canonical, карту сайта, RSS, превью ссылок и разметку для поисковиков,
# а сборка положит рядом файл CNAME, по которому GitHub Pages узнаёт домен.
# Менять адрес в других местах не нужно — он собирается только здесь.
CUSTOM_DOMAIN = ""


def _domain_from_cname():
    """Домен из docs/CNAME, если константа выше пуста.

    Подстраховка от потери домена. Файл CNAME пишет и сборка, и сам
    GitHub при настройке домена через интерфейс, и лежит он в
    репозитории — то есть переживает то, что константу могли случайно
    затереть при обновлении исходников. Без этой подстраховки одна
    перезаписанная строка молча возвращает весь сайт на github.io:
    адреса в canonical, карте сайта и RSS разъезжаются с настоящими,
    и поисковик считает сайт копией самого себя.

    Константа, если она задана, всегда важнее: именно ей меняют домен.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "CNAME")
    try:
        with open(path, encoding="utf-8") as f:
            name = f.read().strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return ""
    # Пустой файл, комментарий или невнятица — не домен.
    return name if name and "." in name and " " not in name and not name.startswith("#") else ""


SITE_DOMAIN = CUSTOM_DOMAIN or _domain_from_cname()

BASE_URL = (f"https://{SITE_DOMAIN}" if SITE_DOMAIN
            else "https://denchest.github.io/Site-Oldpictureart")


# Где лежат оригиналы для скачивания.
#
# Пусто — рядом с сайтом, в docs/images, как сейчас. Оригиналы занимают
# 91% веса всего сайта и растут быстрее всего остального: страницы,
# миниатюры и копии для показа вместе весят около 50 МБ, оригиналы — за
# полтерабайта пути. Когда упрётесь в предел хостинга, оригиналы
# переносят в объектное хранилище, а сюда вписывают его адрес без косой
# черты в конце, например:
#
#     HIRES_BASE_URL = "https://storage.yandexcloud.net/oldpictureart"
#
# После этого кнопка «Скачать картину» и лупа берут файл оттуда, а сам
# сайт остаётся маленьким и бесплатным. Имена файлов не меняются —
# достаточно скопировать папку images в хранилище как есть.
#
# Одна тонкость: атрибут download браузеры соблюдают только для файлов
# с того же домена. Как только оригиналы уедут в хранилище, кнопка станет
# открывать картинку вместо сохранения, и красивое имя файла потеряется.
# Лечится на стороне хранилища — заголовком Content-Disposition:
# attachment у объектов; у Yandex Object Storage это делается в свойствах
# объекта или параметром response-content-disposition в ссылке.
HIRES_BASE_URL = ""


def hires_url(path):
    """Адрес оригинала: локальный путь или ссылка в хранилище."""
    if not path:
        return path
    if not HIRES_BASE_URL or path.startswith(("http://", "https://")):
        return path
    return f"{HIRES_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
TELEGRAM_URL = "https://t.me/oldpictureart"
TELEGRAM_NAME = "@oldpictureart"

# ---------------------------------------------------------------- знак сайта
#
# Одна фигура на всё: вкладку браузера, плитку на телефоне и значок рядом
# с названием в шапке. Раньше это были две разные картинки — тёмный квадрат
# с зелёными холмами в фавиконе и синий кружок в рамке (цвет #0366d6 остался
# от вёрстки по умолчанию) в шапке. Ни одна не имела отношения к оформлению
# сайта и друг к другу.
#
# Знак — пейзаж в раме: тёмно-синее поле рамы, кремовое небо, охристая земля,
# солнце. Цвета те же, что у сайта. Фигуры нарочно простые: тот же набор
# прямоугольников и круг рисуется питоном для png и ico, поэтому сложную
# графику здесь позволить нельзя, да она и не нужна — во вкладке значок
# показывается размером 16 пикселей.
MARK_NAVY = "#1f3a6b"
MARK_NAVY_DARK = "#3a5c96"     # на тёмном фоне тёмно-синее поле сливается
MARK_CREAM = "#f2ede3"
MARK_OCHRE = "#c9a35e"


def mark_svg(field=MARK_NAVY):
    """Знак сайта в виде SVG. field — цвет рамы."""
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
        f"<rect width='32' height='32' fill='{field}'/>"
        f"<rect x='4' y='6' width='24' height='20' fill='{MARK_CREAM}'/>"
        f"<rect x='4' y='20' width='24' height='6' fill='{MARK_OCHRE}'/>"
        f"<circle cx='22' cy='12' r='3' fill='{field}'/>"
        "</svg>"
    )


def mark_data_uri(field=MARK_NAVY):
    """Тот же знак строкой для css. Кодируем только те символы, которые
    ломают значение css-свойства: # обязателен, остальное читается глазами."""
    svg = mark_svg(field).replace('"', "'").replace("#", "%23").replace("\n", "")
    return "data:image/svg+xml," + svg.replace("<", "%3C").replace(">", "%3E")


# Бутстрап темы. Обязан стоять в <head> ДО отрисовки body, иначе тёмная тема
# «моргает» белым на каждой загрузке. Если сохранённой темы нет — берём
# системную (prefers-color-scheme), она же объявлена в meta theme-color.
THEME_BOOT = (
    "<script>(function(){try{var t=localStorage.getItem('theme');"
    "if(t!=='light'&&t!=='dark'){t=(window.matchMedia&&"
    "window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';}"
    "document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>"
)


# ------------------------------------------------------------- счётчик
#
# Номер счётчика Яндекс.Метрики. Пусто — счётчика нет, и в страницы
# ничего не вставляется; сайт от этого только легче.
#
# Где взять новый: metrika.yandex.ru → Добавить счётчик. Номер видно в
# списке счётчиков и в выданном коде — это число после tag.js?id=.
METRIKA_ID = "112760205"

# Код взят тот, что выдала сама Метрика, слово в слово, — кроме двух
# мест:
#
#   • номер подставляется из METRIKA_ID, чтобы он стоял в одном месте,
#     а не в трёх (в адресе tag.js, в вызове ym и в картинке noscript);
#   • убран ecommerce: "dataLayer" — он велит Метрике следить за
#     корзиной интернет-магазина. Магазина здесь нет, следить не за чем.
#
# Параметры referrer и url оставлены, хотя Метрика подставляет их и
# сама: с ними код совпадает с тем, что показывает проверка счётчика в
# кабинете, и не приходится гадать, от чего расхождение.
#
# Ещё две мелочи против выданного кода — чтобы проверка разметки
# оставалась чистой: убран type="text/javascript" (в HTML5 он лишний и
# подразумевается) и косая черта в <img ... />. На работу счётчика ни то
# ни другое не влияет, а ошибки сыпались бы на всех 303 страницах.
# Прятать картинку-пиксель тоже отправлено в style.css классом ym-pixel:
# написанный прямо в разметке стиль давал ту же ошибку на каждой странице.
#
# Строка с document.scripts — защита от второго счётчика на странице:
# если tag.js уже подключён, второй раз он не подключится. Без неё
# повторная вставка удваивала бы все просмотры.
#
# Это обычная строка, не f-строка: в коде Метрики много фигурных скобок,
# и удваивать каждую ради подстановки номера — верный способ ошибиться
# в одной и не заметить.
METRIKA_JS = "" if not METRIKA_ID else """<!-- Yandex.Metrika counter -->
<script>
    (function(m,e,t,r,i,k,a){
        m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=COUNTER', 'ym');

    ym(COUNTER, 'init', {ssr:true, webvisor:true, clickmap:true, referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/COUNTER" class="ym-pixel" alt=""></div></noscript>
<!-- /Yandex.Metrika counter -->""".replace("COUNTER", METRIKA_ID)

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

# Счётчик приклеивается к общему скрипту: он подставляется на каждую
# страницу сайта, поэтому отдельного места для вставки не нужно.
COMMON_JS += METRIKA_JS


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
    # Размеры карточки нужны мессенджерам: без них Telegram и VK иногда
    # рисуют превью маленьким квадратом вместо широкой картинки.
    og_img_tag = ""
    if og_image:
        og_img_tag = f'\n<meta property="og:image" content="{og_image}">'
        if "/cards/" in og_image:
            og_img_tag += ('\n<meta property="og:image:width" content="1200">'
                           '\n<meta property="og:image:height" content="630">')
    # og:url — тот же адрес, что и canonical. Без него соцсети и парсеры
    # микроразметки не знают, на что ссылается карточка: Телеграм подставит
    # адрес, с которого пришёл, а валидатор Яндекса считает поле обязательным.
    canon_tag = f'\n<link rel="canonical" href="{canonical}">' if canonical else ""
    og_url_tag = f'\n<meta property="og:url" content="{canonical}">' if canonical else ""
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
<meta property="og:site_name" content="{SITE_NAME}">{og_url_tag}{og_img_tag}
<meta name="twitter:card" content="summary_large_image">{canon_tag}
<title>{title}</title>
<link rel="icon" href="favicon.ico" sizes="32x32">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
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


# Короткое уведомление внизу экрана: «Ссылка скопирована» и подобное.
# Живёт здесь, а не на странице картины, потому что нужно и странице
# посещения, и кнопке «Поделиться», которая теперь общая.
TOAST_JS = """<script>
function toast(text) {
  var old = document.querySelector('.toast');
  if (old) old.remove();
  var el = document.createElement('div');
  el.className = 'toast';
  el.setAttribute('role', 'status');
  el.textContent = text;
  document.body.appendChild(el);
  setTimeout(function () { el.classList.add('hide'); }, 1800);
  setTimeout(function () { el.remove(); }, 2200);
}
</script>"""


# Поделиться.
#
# Раньше кнопка вела себя по-разному и непредсказуемо: на телефоне
# открывала системное меню, а на компьютере молча копировала адрес в буфер
# — на странице посещения даже без уведомления, так что нажатие выглядело
# как «ничего не произошло». Плюс копировался location.href со всем, что к
# нему прилипло: якорь, метка перехода из рассылки.
#
# Теперь: на сенсорном экране — системное меню (оно там привычное и умеет
# больше, чем любой наш список), на компьютере — свой список рядом с
# кнопкой. Список текстовый, без чужих логотипов: их цветные пятна
# выбиваются из оформления, а название сервиса понятнее значка.
#
# Адрес берётся из canonical — это тот же адрес, что видит поисковик, без
# якорей и меток.
SHARE_JS = """<script>
(function () {
  var menu = null, opener = null;

  function shareUrl() {
    var c = document.querySelector('link[rel="canonical"]');
    return (c && c.href) || location.href.split('#')[0];
  }

  function shareTitle() {
    var t = document.querySelector('meta[property="og:title"]');
    return (t && t.getAttribute('content')) || document.title;
  }

  // Системное меню — только там, где оно действительно системное.
  // В настольном Chrome navigator.share тоже есть, но открывает
  // громоздкую панель Windows, из которой до Телеграма не дойти.
  function preferNative() {
    return !!navigator.share && window.matchMedia
        && window.matchMedia('(pointer: coarse)').matches;
  }

  function close(back) {
    if (!menu) return;
    menu.remove();
    menu = null;
    document.removeEventListener('keydown', onKey, true);
    document.removeEventListener('pointerdown', onOutside, true);
    if (back && opener) opener.focus();
    opener = null;
  }

  function onOutside(e) {
    if (menu && !menu.contains(e.target) && e.target !== opener) close(false);
  }

  function onKey(e) {
    if (!menu) return;
    if (e.key === 'Escape') { e.stopPropagation(); close(true); return; }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Tab') return;
    var items = [].slice.call(menu.querySelectorAll('[role="menuitem"]'));
    var i = items.indexOf(document.activeElement);
    if (e.key === 'Tab' && (i === -1 || (i === items.length - 1 && !e.shiftKey))) { close(false); return; }
    e.preventDefault();
    var step = (e.key === 'ArrowUp' || e.shiftKey) ? -1 : 1;
    items[(i + step + items.length) % items.length].focus();
  }

  function copyLink(url) {
    function ok() { toast('Ссылка скопирована'); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(ok, function () { window.prompt('Скопируйте ссылку:', url); });
    } else {
      window.prompt('Скопируйте ссылку:', url);
    }
  }

  function build(url, title) {
    var u = encodeURIComponent(url), t = encodeURIComponent(title);
    var links = [
      ['Телеграм',   'https://t.me/share/url?url=' + u + '&text=' + t],
      ['ВКонтакте',  'https://vk.com/share.php?url=' + u + '&title=' + t],
      ['WhatsApp',   'https://api.whatsapp.com/send?text=' + encodeURIComponent(title + ' ' + url)],
      ['Почта',      'mailto:?subject=' + t + '&body=' + u]
    ];
    var box = document.createElement('div');
    box.className = 'share-menu';
    box.setAttribute('role', 'menu');
    box.setAttribute('aria-label', 'Поделиться');
    links.forEach(function (pair) {
      var a = document.createElement('a');
      a.className = 'share-item';
      a.setAttribute('role', 'menuitem');
      a.href = pair[1];
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = pair[0];
      a.addEventListener('click', function () { close(false); });
      box.appendChild(a);
    });
    var copy = document.createElement('button');
    copy.type = 'button';
    copy.className = 'share-item share-copy';
    copy.setAttribute('role', 'menuitem');
    copy.textContent = 'Скопировать ссылку';
    copy.addEventListener('click', function () { close(true); copyLink(url); });
    box.appendChild(copy);
    return box;
  }

  function place(box, btn) {
    // На узком экране — полоса снизу, её не надо никуда вписывать.
    if (window.innerWidth <= 560) return;
    var r = btn.getBoundingClientRect(), m = box.getBoundingClientRect();
    var left = Math.min(r.right - m.width, window.innerWidth - m.width - 8);
    var top = r.bottom + 6;
    if (top + m.height > window.innerHeight - 8) top = Math.max(8, r.top - m.height - 6);
    box.style.left = Math.max(8, left) + 'px';
    box.style.top = top + 'px';
  }

  window.sharePage = function (btn) {
    var url = shareUrl(), title = shareTitle();

    if (preferNative()) {
      navigator.share({title: title, text: title, url: url}).catch(function () {});
      return;
    }
    if (menu) { close(true); return; }

    opener = (btn && btn.nodeType === 1) ? btn
           : document.querySelector('[data-share-btn]')
           || document.activeElement;
    menu = build(url, title);
    document.body.appendChild(menu);
    if (opener && opener.getBoundingClientRect) place(menu, opener);
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onOutside, true);
    var first = menu.querySelector('[role="menuitem"]');
    if (first) first.focus();
  };

  window.addEventListener('resize', function () { close(false); });
})();
</script>"""


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
      scaleOut = null, btnPrev = null, btnNext = null, btnIn = null, btnOut = null,
      countOut = null;
  var idx = 0, scale = 1, fit = 1, tx = 0, ty = 0, natW = 0, natH = 0, zoomed = false;
  var opener = null, pointers = {}, pinch = null, dragged = false;
  // Жест листания: вписанная картина никуда не двигается, поэтому её
  // перетаскивание свободно — вбок листает, вниз закрывает.
  var swipe = null, swipeX = 0;

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
          '<span class="lupa-count" aria-live="polite"></span>' +
          '<button type="button" class="lupa-btn" data-act="next" aria-label="Следующая картина" title="Следующая">›</button>' +
          '<span class="lupa-scale"></span>' +
          '<button type="button" class="lupa-btn" data-act="out" aria-label="Уменьшить" title="Уменьшить">−</button>' +
          '<button type="button" class="lupa-btn" data-act="in" aria-label="Увеличить" title="Увеличить">+</button>' +
          '<button type="button" class="lupa-btn" data-act="fit" aria-label="Вписать целиком" title="Вписать целиком">⤢</button>' +
          '<a class="lupa-btn" data-act="save" download aria-label="Скачать картину" title="Скачать картину"><span class="icon-download" aria-hidden="true"></span></a>' +
          '<button type="button" class="lupa-btn" data-act="close" aria-label="Закрыть" title="Закрыть (Esc)">✕</button>' +
        '</div>' +
      '</div>' +
      '<div class="lupa-stage"><img class="lupa-img" alt=""></div>' +
      '<p class="lupa-hint">Колесо — увеличение, перетаскивание — сдвиг, двойной щелчок — во всю величину, Esc — закрыть</p>' +
      '<p class="lupa-hint lupa-hint-touch">Листайте вбок · вниз — закрыть</p>';
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
    countOut = box.querySelector('.lupa-count');

    box.addEventListener('click', function (e) {
      var hit = e.target.closest ? e.target.closest('[data-act]') : null;
      var act = hit && hit.getAttribute('data-act');
      if (act === 'save') return;              // ссылка отработает сама
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
    // Отмена жеста (звонок, системный жест) не должна листать: сначала
    // забываем начатое движение, потом закрываем указатель как обычно.
    stage.addEventListener('pointercancel', function (e) { endSwipe(true); onUp(e); });

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
    img.style.transform = 'translate(' + (tx + swipeX).toFixed(1) + 'px,' + ty.toFixed(1) + 'px) scale(' + scale + ')';
    scaleOut.textContent = Math.round(scale * 100) + '%';
    var max = maxScale();
    btnIn.disabled = scale >= max - 0.001;
    btnOut.disabled = scale <= fit + 0.001;
    stage.classList.toggle('zoomable', Math.abs(scale - fit) < 0.01);
  }

  function maxScale() { return Math.max(1, fit * 8); }

  function apply(s, eased) {
    // fitScale() пересчитывает fit, а maxScale() на него опирается,
    // поэтому порядок обязателен: иначе предел берётся от прошлой картинки.
    var lo = fitScale(), hi = maxScale();
    scale = Math.min(hi, Math.max(lo, s));
    clamp(scale);
    if (eased && !reduce) {
      img.classList.add('eased');
      setTimeout(function () { img.classList.remove('eased'); }, 240);
    }
    paint();
  }

  function zoomAt(pt, factor) {
    // Пока картинка не загрузилась, размеров у неё нет: масштаб считался
    // от нуля, подпись показывала выдуманные проценты, а после загрузки
    // всё сбрасывалось. Со стороны это выглядело так, будто колесо не
    // работает — на странице похода со снимками это случалось чаще всего.
    if (!natW || !natH) return;
    var r = stage.getBoundingClientRect();
    var px = pt.x - r.left, py = pt.y - r.top;
    var ix = (px - tx) / scale, iy = (py - ty) / scale;
    var lo = fitScale(), hi = maxScale();
    var s = Math.min(hi, Math.max(lo, scale * factor));
    if (Math.abs(s - scale) > 0.0001) zoomed = true;
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
      endSwipe(false);
    } else {
      stage.classList.add('dragging');
      // Пока картина вписана целиком, тащить её некуда — clamp держит её
      // по центру. Значит, это движение можно отдать под жест.
      swipe = Math.abs(scale - fitScale()) < 0.01
        ? {x0: e.clientX, y0: e.clientY, dx: 0, dy: 0} : null;
    }
  }

  function hideHint() {
    // Подсказка нужна ровно до первого жеста, дальше она только занимает
    // место внизу экрана.
    var hint = box && box.querySelector('.lupa-hint-touch');
    if (hint) hint.hidden = true;
  }

  function endSwipe(eased) {
    swipe = null;
    if (!swipeX) return;
    swipeX = 0;
    if (eased && !reduce) {
      img.classList.add('eased');
      setTimeout(function () { img.classList.remove('eased'); }, 240);
    }
    paint();
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
    // Листание: картина едет за пальцем, чтобы жест был виден, а не
    // угадывался. Соседняя запись появится, когда палец отпустят.
    if (swipe) {
      swipe.dx = e.clientX - swipe.x0;
      swipe.dy = e.clientY - swipe.y0;
      if (Math.abs(swipe.dx) + Math.abs(swipe.dy) > 3) dragged = true;
      swipeX = links.length > 1 ? swipe.dx : 0;
      pointers[e.pointerId] = {x: e.clientX, y: e.clientY};
      paint();
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
    if (!swipe) return;
    var dx = swipe.dx, dy = swipe.dy;
    swipe = null;
    // Порог — доля ширины экрана, но не меньше пальца и не больше,
    // чем удобно смахнуть одной рукой на телефоне.
    var w = stage.getBoundingClientRect().width;
    var need = Math.max(48, Math.min(120, w * 0.18));
    if (links.length > 1 && Math.abs(dx) > need && Math.abs(dx) > Math.abs(dy)) {
      swipeX = 0;
      hideHint();
      return show(dx < 0 ? idx + 1 : idx - 1);
    }
    if (Math.abs(dy) > 120 && Math.abs(dy) > Math.abs(dx) * 1.5) {
      swipeX = 0;
      hideHint();
      return close();
    }
    endSwipe(true);
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
    // Лупа показывает копию до 2000 пикселей, если она есть: оригинал бывает
    // по нескольку мегабайт, а разглядеть на экране больше всё равно нельзя.
    // Кнопка «скачать» ниже по-прежнему указывает на оригинал.
    var viewSrc = a.getAttribute('data-view') || hires;

    var save = box.querySelector('[data-act="save"]');
    if (save) {
      // Ту же ссылку, что у кнопки на странице: оригинал и человеческое имя файла
      save.setAttribute('href', hires);
      save.setAttribute('download', a.getAttribute('data-download') || '');
    }
    capTitle.textContent = a.getAttribute('data-title') || (thumb ? thumb.alt : '');
    capMeta.textContent = a.getAttribute('data-meta') || '';
    img.alt = thumb ? thumb.alt : '';
    btnPrev.hidden = btnNext.hidden = links.length < 2;
    if (countOut) {
      countOut.hidden = links.length < 2;
      countOut.textContent = links.length > 1 ? (idx + 1) + '/' + links.length : '';
    }
    // Подсказка по делу: листать нечего, когда картина одна.
    var touchHint = box.querySelector('.lupa-hint-touch');
    if (touchHint) {
      touchHint.textContent = links.length > 1
        ? 'Листайте вбок · вниз — закрыть'
        : 'Щипок увеличивает · вниз — закрыть';
    }

    // Сначала показываем ту же картинку, что уже на странице — она в кэше,
    // и лупа открывается мгновенно. Оригинал подгружаем следом и подменяем,
    // сохранив видимый размер.
    var small = (thumb && (thumb.currentSrc || thumb.src)) || viewSrc;
    swipe = null; swipeX = 0;
    natW = natH = 0;
    zoomed = false;
    stage.classList.add('loading');
    scaleOut.textContent = '';
    img.src = small;
    var ready = function () {
      natW = img.naturalWidth; natH = img.naturalHeight;
      stage.classList.remove('loading');
      apply(fitScale(), false);
      loadHires(viewSrc);
    };
    if (img.complete && img.naturalWidth) ready();
    else img.onload = ready;
  }

  function loadHires(src) {
    // Сравниваем полные адреса: в разметке ссылка относительная, а img.src
    // браузер отдаёт абсолютным, и без этого оригинал грузился второй раз.
    if (!src) return;
    var abs = new URL(src, location.href).href;
    if (abs === img.src) return;
    var big = new Image();
    big.onload = function () {
      if (!big.naturalWidth) return;
      var k = natW ? big.naturalWidth / natW : 1;
      img.src = abs;
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


# Вход в аккаунт и избранное.
#
# Аккаунт нужен ровно для одного: чтобы отмеченные картины были видны и на
# телефоне, и на компьютере. Без него всё работает — лайки просто лежат в
# памяти браузера. Поэтому вся эта часть необязательная: если скрипты
# Google не загрузились (расширение, корпоративная сеть, самолёт),
# страница обязана работать дальше, а не падать целиком.
#
# Что здесь исправлено против прежней версии:
#   • ошибки показывались словами Firebase по-английски — теперь по-русски
#     и о деле («Неверный пароль», а не «auth/wrong-password»);
#   • кнопка не блокировалась на время запроса, и двойное нажатие уходило
#     двумя попытками входа;
#   • вход через Google открывался только всплывающим окном: если браузер
#     его блокировал, не происходило ничего — теперь есть переход;
#   • сброс пароля показывался системным alert посреди оформленной страницы;
#   • окно входа было вырвано из тёмной темы и светилось белым;
#   • с клавиатуры из окна можно было уйти табом на страницу под ним;
#   • лайки писались полем liked: true/false, а снятый лайк оставлял за
#     собой мусорную запись. Теперь снятый лайк — удаление записи, а её
#     состав в точности тот, что разрешают правила из FIRESTORE.md.
AUTH_JS = """<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-auth-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore-compat.js"></script>
<script src="firebase-config.js"></script>
<script>
var auth = null, db = null, currentUser = null, FIREBASE_OK = false;
try {
  if (typeof firebase !== 'undefined' && typeof firebaseConfig !== 'undefined') {
    firebase.initializeApp(firebaseConfig);
    auth = firebase.auth();
    db = firebase.firestore();
    FIREBASE_OK = true;
  }
} catch (e) { console.warn('Firebase недоступен, избранное работает локально:', e.message); }

// Коды Firebase человеческим языком. Пустая строка — молча промолчать:
// пользователь сам закрыл окно, сообщать не о чем.
var AUTH_ERRORS = {
  'auth/invalid-email':            'Похоже, адрес почты записан с ошибкой.',
  'auth/missing-password':         'Введите пароль.',
  'auth/user-not-found':           'Такой почты здесь нет. Проверьте адрес или создайте аккаунт.',
  'auth/wrong-password':           'Неверный пароль.',
  'auth/invalid-credential':       'Неверная почта или пароль.',
  'auth/email-already-in-use':     'На эту почту аккаунт уже есть — войдите в него.',
  'auth/weak-password':            'Пароль слишком простой: нужно хотя бы шесть знаков.',
  'auth/too-many-requests':        'Слишком много попыток подряд. Подождите пару минут.',
  'auth/network-request-failed':   'Не получилось связаться с сервером. Проверьте интернет.',
  'auth/user-disabled':            'Этот аккаунт отключён.',
  'auth/popup-closed-by-user':     '',
  'auth/cancelled-popup-request':  '',
  'auth/unauthorized-domain':      'Вход с этого адреса не разрешён в настройках Firebase.',
  'auth/operation-not-allowed':    'Этот способ входа выключен в настройках Firebase.'
};

function authMessage(err) {
  var code = err && err.code;
  if (code && AUTH_ERRORS.hasOwnProperty(code)) return AUTH_ERRORS[code];
  return 'Не получилось войти. ' + ((err && err.message) || '');
}

function authName(user) {
  if (!user) return '';
  if (user.displayName) return user.displayName.split(' ')[0];
  if (user.email) return user.email.split('@')[0];
  return 'Профиль';
}

// Поздороваться — только в ответ на действие человека.
//
// Firebase помнит вход между посещениями и при загрузке каждой страницы
// сообщает о нём тем же способом, что и о настоящем входе. Отличить одно
// от другого по событию нельзя, и «Вы вошли как Денис» выскакивало на
// каждой открытой картине — притом что человек ничего не нажимал.
// Поэтому здороваемся не в обработчике события, а там, где вход
// действительно произошёл: после формы, после окна Google и после
// возврата с его страницы.
function greet(user) {
  toast('Вы вошли как ' + authName(user));
}

if (FIREBASE_OK) {
  // Вход переходом (когда всплывающее окно заблокировано) возвращается
  // сюда: ошибку надо поймать, иначе она утечёт в консоль незаметно.
  auth.getRedirectResult().then(function (result) {
    // Вернулись со страницы Google — вот это вход, о нём и говорим.
    if (result && result.user) greet(result.user);
  }).catch(function (err) {
    var m = authMessage(err);
    if (m) toast(m);
  });

  auth.onAuthStateChanged(function (user) {
    currentUser = user;
    var btn = document.getElementById('auth-btn');
    if (btn) {
      if (user) {
        var name = authName(user);
        btn.innerHTML = '<span class="icon-user" aria-hidden="true"></span> ';
        btn.appendChild(document.createTextNode(name));
        btn.title = 'Выйти из аккаунта: ' + name;
        btn.setAttribute('aria-label', 'Выйти из аккаунта: ' + name);
        btn.onclick = function () {
          auth.signOut().then(function () { toast('Вы вышли из аккаунта'); });
        };
      } else {
        btn.innerHTML = '<span class="icon-login" aria-hidden="true"></span> Войти';
        btn.title = 'Войти';
        btn.setAttribute('aria-label', 'Войти');
        btn.onclick = showAuthForm;
      }
    }
    if (user) syncLikesWithCloud();
  });
} else {
  var authBtnOffline = document.getElementById('auth-btn');
  if (authBtnOffline) authBtnOffline.remove();
}

// ---------- Окно входа ----------
function showAuthForm() {
  var old = document.querySelector('.auth-modal-overlay');
  if (old) old.remove();

  var opener = document.activeElement;
  var overlay = document.createElement('div');
  overlay.className = 'auth-modal-overlay';
  overlay.innerHTML =
    '<div class="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">' +
      '<button type="button" class="auth-modal-close" id="auth-close-btn" aria-label="Закрыть">&times;</button>' +
      '<h3 id="auth-title">Вход в аккаунт</h3>' +
      '<p id="auth-lede">Чтобы отмеченные картины были и на телефоне, и на компьютере.</p>' +
      '<button type="button" class="auth-btn-google" id="google-login-btn">' +
        '<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">' +
        '<path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>' +
        '<path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>' +
        '<path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>' +
        '<path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>' +
        'Войти через Google' +
      '</button>' +
      '<div class="auth-divider">или</div>' +
      '<form id="auth-form" novalidate>' +
        '<input type="email" class="auth-input" id="auth-email" name="email" placeholder="Почта" autocomplete="email" required>' +
        '<input type="password" class="auth-input" id="auth-password" name="password" placeholder="Пароль" autocomplete="current-password" required>' +
        '<button type="submit" class="auth-submit" id="auth-submit-btn">Войти</button>' +
      '</form>' +
      '<div class="auth-error" id="auth-error" role="alert"></div>' +
      '<div class="auth-switch">' +
        '<span id="auth-switch-text">Нет аккаунта?</span> ' +
        '<button type="button" class="auth-link" id="auth-switch-link">Создать</button>' +
      '</div>' +
      '<div class="auth-switch auth-reset-row" id="auth-reset-container">' +
        '<button type="button" class="auth-link" id="auth-reset-link">Забыли пароль?</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(overlay);

  var modal = overlay.querySelector('.auth-modal');
  var emailInp = document.getElementById('auth-email');
  var passInp = document.getElementById('auth-password');
  var submitBtn = document.getElementById('auth-submit-btn');
  var googleBtn = document.getElementById('google-login-btn');
  var switchLink = document.getElementById('auth-switch-link');
  var switchText = document.getElementById('auth-switch-text');
  var resetRow = document.getElementById('auth-reset-container');
  var errorDiv = document.getElementById('auth-error');
  var isLogin = true, busy = false;

  function say(text) { errorDiv.textContent = text || ''; }

  function setBusy(on, label) {
    busy = on;
    submitBtn.disabled = on;
    googleBtn.disabled = on;
    submitBtn.textContent = on ? (label || 'Минуту…')
                               : (isLogin ? 'Войти' : 'Создать аккаунт');
  }

  function close(back) {
    overlay.remove();
    document.removeEventListener('keydown', onKey, true);
    if (back && opener && opener.focus) opener.focus();
  }

  // Пока окно открыто, клавиатура не должна уходить на страницу под ним.
  function onKey(e) {
    if (e.key === 'Escape') { e.stopPropagation(); close(true); return; }
    if (e.key !== 'Tab') return;
    var items = [].slice.call(modal.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), a[href]'));
    if (!items.length) return;
    var first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  document.addEventListener('keydown', onKey, true);
  document.getElementById('auth-close-btn').onclick = function () { close(true); };
  overlay.onclick = function (e) { if (e.target === overlay && !busy) close(true); };

  googleBtn.onclick = function () {
    if (busy) return;
    setBusy(true);
    say('');
    var provider = new firebase.auth.GoogleAuthProvider();
    auth.signInWithPopup(provider)
      .then(function (result) {
        close(false);
        if (result && result.user) greet(result.user);
      })
      .catch(function (err) {
        var code = err && err.code;
        // Всплывающее окно заблокировано — уводим на страницу Google
        // целиком. Раньше в этом месте просто ничего не происходило.
        if (code === 'auth/popup-blocked'
            || code === 'auth/operation-not-supported-in-this-environment') {
          auth.signInWithRedirect(provider).catch(function (e2) {
            setBusy(false);
            say(authMessage(e2));
          });
          return;
        }
        setBusy(false);
        say(authMessage(err));
      });
  };

  switchLink.onclick = function () {
    isLogin = !isLogin;
    document.getElementById('auth-title').textContent = isLogin ? 'Вход в аккаунт' : 'Создание аккаунта';
    document.getElementById('auth-lede').textContent = isLogin
      ? 'Чтобы отмеченные картины были и на телефоне, и на компьютере.'
      : 'Нужны только почта и пароль от шести знаков.';
    submitBtn.textContent = isLogin ? 'Войти' : 'Создать аккаунт';
    switchText.textContent = isLogin ? 'Нет аккаунта?' : 'Уже есть аккаунт?';
    switchLink.textContent = isLogin ? 'Создать' : 'Войти';
    passInp.setAttribute('autocomplete', isLogin ? 'current-password' : 'new-password');
    resetRow.style.display = 'none';
    say('');
  };

  document.getElementById('auth-reset-link').onclick = function () {
    var email = emailInp.value.trim();
    if (!email) { say('Введите почту — на неё придёт письмо.'); emailInp.focus(); return; }
    if (busy) return;
    busy = true;
    auth.sendPasswordResetEmail(email)
      .then(function () {
        close(true);
        toast('Письмо для смены пароля отправлено на ' + email);
      })
      .catch(function (err) { busy = false; say(authMessage(err)); });
  };

  document.getElementById('auth-form').onsubmit = function (e) {
    e.preventDefault();
    if (busy) return;
    var email = emailInp.value.trim(), pass = passInp.value;
    if (!email) { say('Введите почту.'); emailInp.focus(); return; }
    if (email.indexOf('@') < 1 || email.indexOf('.', email.indexOf('@')) < 0) {
      say('Похоже, адрес почты записан с ошибкой.'); emailInp.focus(); return;
    }
    if (pass.length < 6) { say('Пароль: не меньше шести знаков.'); passInp.focus(); return; }

    say('');
    setBusy(true, isLogin ? 'Входим…' : 'Создаём…');
    var go = isLogin ? auth.signInWithEmailAndPassword(email, pass)
                     : auth.createUserWithEmailAndPassword(email, pass);
    go.then(function (result) {
        close(false);
        if (result && result.user) greet(result.user);
      })
      .catch(function (err) {
        setBusy(false);
        say(authMessage(err));
        var code = err && err.code;
        // «Забыли пароль?» показываем там, где он к месту, и не показываем
        // там, где дело не в пароле.
        resetRow.style.display =
          (code === 'auth/wrong-password' || code === 'auth/invalid-credential'
           || code === 'auth/email-already-in-use') ? 'block' : 'none';
      });
  };

  setTimeout(function () { emailInp.focus(); }, 60);
}

// ---------- Избранное ----------
// Запись называется <uid>_<адрес страницы> и содержит ровно три поля:
// userId, postId, createdAt. Ровно это разрешают правила из FIRESTORE.md —
// лишнее поле в записи привело бы к отказу в доступе.
function likeDoc(postId) {
  return db.collection('likes').doc(currentUser.uid + '_' + postId);
}

function readLocalLikes() {
  try { return JSON.parse(localStorage.getItem('likes') || '{}'); } catch (e) { return {}; }
}

function writeLocalLikes(map) {
  try { localStorage.setItem('likes', JSON.stringify(map)); } catch (e) {}
}

async function syncLike(postId, liked) {
  var local = readLocalLikes();
  if (liked) local[postId] = true; else delete local[postId];
  writeLocalLikes(local);

  if (!FIREBASE_OK || !currentUser) return;
  try {
    if (liked) {
      await likeDoc(postId).set({
        userId: currentUser.uid,
        postId: postId,
        createdAt: firebase.firestore.FieldValue.serverTimestamp()
      });
    } else {
      await likeDoc(postId).delete();
    }
  } catch (e) {
    console.warn('Не удалось сохранить избранное в облако:', e.message);
    toast('Отметка сохранена только в этом браузере');
  }
}

// При входе списки сводятся в обе стороны: облачные отметки приходят в
// браузер, а те, что человек успел поставить до входа, уходят в облако.
// Раньше они просто терялись из виду при переходе на другое устройство.
async function syncLikesWithCloud() {
  if (!FIREBASE_OK || !currentUser) return;
  try {
    var snap = await db.collection('likes')
      .where('userId', '==', currentUser.uid).get();
    var cloud = {};
    snap.forEach(function (d) { cloud[d.data().postId] = true; });

    var local = readLocalLikes(), merged = {}, k;
    for (k in cloud) merged[k] = true;
    for (k in local) if (local[k]) merged[k] = true;
    writeLocalLikes(merged);

    var upload = [];
    for (k in merged) if (!cloud[k]) upload.push(k);
    await Promise.all(upload.slice(0, 200).map(function (postId) {
      return likeDoc(postId).set({
        userId: currentUser.uid,
        postId: postId,
        createdAt: firebase.firestore.FieldValue.serverTimestamp()
      });
    }));

    var btn = document.getElementById('like-btn');
    if (btn && merged[btn.dataset.postId]) {
      btn.classList.add('liked');
      btn.setAttribute('aria-pressed', 'true');
      btn.setAttribute('aria-label', 'Убрать из избранного');
    }
    if (typeof updateFavList === 'function') updateFavList();
  } catch (e) {
    console.warn('Избранное из облака недоступно:', e.message);
  }
}

// Работает и без аккаунта, и без Firebase вообще.
async function toggleLike() {
  var btn = document.getElementById('like-btn');
  if (!btn) return;
  var pid = btn.dataset.postId;
  var next = !readLocalLikes()[pid];
  btn.classList.toggle('liked', next);
  btn.setAttribute('aria-pressed', next ? 'true' : 'false');
  btn.setAttribute('aria-label', next ? 'Убрать из избранного' : 'В избранное');
  await syncLike(pid, next);
  try {
    if (window.opener && window.opener.updateFavList) window.opener.updateFavList();
  } catch (e) {}
}
</script>"""


SCROLL_TOP_JS = """<script>
function scrollToTop(){
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  window.scrollTo({top:0, behavior: reduce ? 'auto' : 'smooth'});
}
</script>"""


def site_footer(rss="feed.xml"):
    """Подвал, общий для всех страниц.

    Собрание целиком выросло из телеграм-канала, а ссылки на него на сайте
    не было ни одной. Подвал — её естественное место: он есть на каждой
    странице, не отвлекает от работ и заодно даёт понять, откуда всё это.
    """
    return (
        '<footer class="site-footer">'
        '<p class="footer-source">Собрано из канала '
        f'<a href="{TELEGRAM_URL}" target="_blank" rel="noopener">'
        f'<span class="icon-telegram" aria-hidden="true"></span>{TELEGRAM_NAME}</a>'
        '</p>'
        '<p class="footer-links">'
        '<a href="ukazatel.html">Указатель</a> · '
        '<a href="stats.html">Статистика</a> · '
        '<a href="museums.html">Карта собраний</a> · '
        + ('<a href="visits.html">Посещения</a> · ' if has_visits() else '')
        + f'<a href="{rss}">RSS</a>'
        '</p>'
        '</footer>'
    )
