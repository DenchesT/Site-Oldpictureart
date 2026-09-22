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
import re

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


# ------------------------------------------------ дата в названии работы
# В канале название пишется так: «Les Fiancés (Пара), около 1868» — дата
# идёт последней, после запятой. Раньше год брался как первое четырёхзначное
# число в названии, и у «Парада на Красной площади 7 ноября 1941 года, 1949»
# годом создания становился 1941, у «Открытия Парижской оперы, 5 января
# 1875 года, 1878» — 1875: год события вместо года картины.
_YEAR_RE = re.compile(r"(\d{4})(?:\s*[-–—]\s*(\d{2,4})(?!\d))?")
_CENTURY_RE = re.compile(r"\b[IVXLC]+\s*(?:век|в\.)", re.I)


def split_title_date(title):
    """«Les Fiancés (Пара), около 1868» → («Les Fiancés (Пара)», «около 1868»).

    Дата — последний кусок после запятой, если в нём есть год или век и нет
    закрывающей скобки (иначе это запятая внутри названия). Даты нет —
    вторым элементом идёт пустая строка.
    """
    t = (title or "").strip()
    head, comma, tail = t.rpartition(",")
    tail = tail.strip()
    if comma and ")" not in tail and (re.search(r"\d{3,4}", tail) or _CENTURY_RE.search(tail)):
        return head.strip(), tail
    return t, ""


def date_years(date):
    """Первый и последний год даты: «1805–06» → (1805, 1806),
    «между 1887 и 1890 годами» → (1887, 1890), «XIX век» → (None, None)."""
    years = []
    for m in _YEAR_RE.finditer(date or ""):
        first = int(m.group(1))
        years.append(first)
        if m.group(2):
            tail = m.group(2)
            second = int(str(first)[:4 - len(tail)] + tail)
            if second >= first:
                years.append(second)
    if not years:
        return None, None
    return years[0], max(years)


def work_year(title):
    """Год создания работы по её названию или None."""
    _, date = split_title_date(title)
    if date:
        return date_years(date)[0]
    # Даты после запятой нет — как раньше, первый год в названии.
    m = re.search(r"\d{4}", title or "")
    return int(m.group()) if m else None


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

# ------------------------------------------------ страница о данных
# Кто ведёт сайт и куда писать с вопросами о данных — показывается на
# странице privacy.html. Имя по закону о персональных данных положено
# указывать (оператор — тот, кто решает, зачем собираются данные), но
# вписывать его или нет — решать вам: пустая строка — строки с именем
# на странице просто не будет.
SITE_OWNER = ""
# Куда писать: почта ("mailto:имя@почта.ru") или ссылка. Пока адреса
# нет, ведёт на канал.
PRIVACY_CONTACT = TELEGRAM_URL
PRIVACY_CONTACT_TEXT = "через телеграм-канал " + TELEGRAM_NAME
# Дата текста. Меняйте, когда меняете сам текст, а не при каждой сборке:
# дата редакции говорит, с какого дня действуют эти условия.
PRIVACY_DATE = "21 сентября 2026 г."

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

# Метрика включается только с согласия посетителя.
#
# Она ставит cookie, получает IP-адрес, а Вебвизор записывает действия
# на странице. Роскомнадзор считает это обработкой персональных данных,
# а для аналитики нужно согласие, данное до того, как счётчик заработал:
# строка «продолжая пользоваться сайтом, вы соглашаетесь» при уже
# работающем счётчике согласием не считается. Условия самой Метрики
# (п. 2.1 и 5.8) требуют того же: рассказать посетителям об обработке
# данных и о том, как её отключить.
#
# Поэтому внизу страницы — небольшая плашка с двумя равными кнопками
# «Принять» и «Отклонить». Пока человек не нажал «Принять», tag.js не
# загружается вовсе. Ответ хранится в
# браузере (localStorage, ключ consent-metrika); передумать можно на
# странице privacy.html.
#
# Цена честная: кто не разрешил или просто не нажал, в отчётах Метрики
# не появится, и цифры станут меньше. Зато это те, кто согласился.
#
# Картинка в <noscript> убрана: без JavaScript спросить согласия нечем,
# а считать молча — ровно то, от чего здесь уходим.
#
# Сам код счётчика — тот, что выдала Метрика, без ecommerce (магазина
# здесь нет); номер подставляется из METRIKA_ID. Строка с document.scripts
# — защита от второго подключения tag.js. Это обычная строка, не
# f-строка: в коде много фигурных скобок, а номер ставится .replace.
METRIKA_JS = "" if not METRIKA_ID else """<script>
(function () {
  var KEY = 'consent-metrika';
  var loaded = false;

  function load() {
    if (loaded) return;
    loaded = true;
    (function(m,e,t,r,i,k,a){
        m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=COUNTER', 'ym');
    ym(COUNTER, 'init', {ssr:true, webvisor:true, clickmap:true, referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
  }

  function read() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function write(v) { try { localStorage.setItem(KEY, v); } catch (e) {} }

  // Отказ после согласия: стираем то, что Метрика оставила на этом
  // сайте, — её cookie _ym* и записи _ym* в localStorage. Cookie на
  // домене yandex.ru отсюда не достать; о них и о блокировщике Метрики
  // сказано на странице privacy.html.
  function forget() {
    var parts = location.hostname.split('.');
    document.cookie.split(';').forEach(function (c) {
      var name = c.split('=')[0].trim();
      if (name.indexOf('_ym') !== 0) return;
      document.cookie = name + '=; Max-Age=0; path=/';
      for (var i = 0; i < parts.length - 1; i++) {
        document.cookie = name + '=; Max-Age=0; path=/; domain=.' + parts.slice(i).join('.');
      }
    });
    try {
      Object.keys(localStorage).forEach(function (k) {
        if (k.indexOf('_ym') === 0) localStorage.removeItem(k);
      });
    } catch (e) {}
  }

  function hideBanner() {
    var b = document.getElementById('consent');
    if (b) b.remove();
  }

  window.metrikaConsent = {
    state: read,
    allow: function () { write('yes'); hideBanner(); load(); },
    // true — счётчик на этой странице уже работал: чтобы он замолчал,
    // страницу надо перезагрузить (остановить tag.js на ходу нельзя).
    deny: function () { write('no'); hideBanner(); forget(); return loaded; }
  };

  function banner() {
    var b = document.createElement('section');
    b.id = 'consent';
    b.className = 'consent';
    b.setAttribute('aria-label', 'Статистика посещений');
    // Тон — как на обычных сайтах: спокойно и коротко, без перечня того,
    // что Метрика умеет. Всё подробно — IP-адрес, Вебвизор, как
    // отказаться — на странице по ссылке «Подробнее». Главное здесь не
    // текст, а то, что до «Принять» счётчик не загружается.
    b.innerHTML =
      '<p class="consent-text">Используются cookie и Яндекс Метрика, чтобы понимать, ' +
      'какие картины вам интересны. <a href="privacy.html#metrika">Подробнее</a></p>' +
      '<div class="consent-actions">' +
        '<button type="button" class="consent-btn" data-consent="yes">Принять</button>' +
        '<button type="button" class="consent-btn" data-consent="no">Отклонить</button>' +
      '</div>';
    b.addEventListener('click', function (e) {
      var v = e.target.getAttribute && e.target.getAttribute('data-consent');
      if (v === 'yes') window.metrikaConsent.allow();
      else if (v === 'no') window.metrikaConsent.deny();
    });
    document.body.appendChild(b);
  }

  var v = read();
  if (v === 'yes') load();
  // На странице о данных свои кнопки — плашка там только мешала бы.
  else if (v !== 'no' && !document.getElementById('consent-controls')) banner();
})();
</script>""".replace("COUNTER", METRIKA_ID)

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


# ------------------------------------------------ вход через Яндекс ID и VK ID
#
# Аккаунт нужен ровно для одного: чтобы отмеченные картины были видны и на
# телефоне, и на компьютере. Без него всё работает — отметки лежат в
# памяти браузера.
#
# Раньше вход шёл через Firebase — сервис Google. С 7 июля 2026 года за
# авторизацию через иностранные системы штрафуют владельцев сайтов
# (199-ФЗ, ст. 13.55 КоАП), да и почты людей хранились бы за рубежом.
# Теперь вход — через Яндекс ID и VK ID, а отметки хранит маленькая
# функция в Yandex Cloud (cloud/auth/index.py): она меняет код входа на
# номер пользователя, выдаёт сайту подписанный пропуск и держит отметки
# в базе YDB. Как всё это завести — AUTH_SETUP.md.
#
# Пока три строки ниже пустые, кнопки «Войти» на сайте просто нет:
# отметки работают в браузере, как и раньше.
AUTH_API_URL = "https://functions.yandexcloud.net/d4e2jv2t457u5oldt269"        # адрес функции: https://functions.yandexcloud.net/…
YANDEX_CLIENT_ID = "7a85cd4ed113494c82722380127c35f1"    # ClientID приложения на oauth.yandex.ru
VK_CLIENT_ID = "54785333"        # ID приложения на id.vk.ru
AUTH_REDIRECT = f"{BASE_URL}/auth.html"
# Адрес сервиса VK ID. Документация VK переехала на id.vk.ru; если VK
# снова сменит адрес, достаточно поправить здесь и в функции (VK_HOST).
VK_ID_HOST = "https://id.vk.ru"

# Общая часть: пропуск, запросы к функции и сведение отметок. Нужна и
# странице картины, и главной (там список «Избранное»), и странице
# возврата после входа.
CLOUD_JS = """<script>
var CLOUD = {api: 'AUTH_API_URL', yandex: 'YANDEX_CLIENT_ID', vk: 'VK_CLIENT_ID',
             redirect: 'AUTH_REDIRECT', vkHost: 'VK_ID_HOST'};
CLOUD.on = !!(CLOUD.api && (CLOUD.yandex || CLOUD.vk));

function readLocalLikes() {
  try { return JSON.parse(localStorage.getItem('likes') || '{}') || {}; } catch (e) { return {}; }
}
function writeLocalLikes(map) {
  try { localStorage.setItem('likes', JSON.stringify(map)); } catch (e) {}
}

// Пропуск от функции: {token, name, provider, exp}. Сам токен подписан
// на сервере, подделать его в браузере нельзя; здесь он только хранится.
function getSession() {
  try {
    var s = JSON.parse(localStorage.getItem('session') || 'null');
    if (s && s.token && s.exp * 1000 > Date.now()) return s;
  } catch (e) {}
  return null;
}
function setSession(s) {
  try {
    if (s) localStorage.setItem('session', JSON.stringify(s));
    else { localStorage.removeItem('session'); localStorage.removeItem('likes-synced'); }
  } catch (e) {}
}

// Все запросы — POST с Content-Type text/plain: так браузер не шлёт перед
// каждым предварительный OPTIONS-запрос, и функции не нужно его ждать.
function cloudCall(action, data) {
  var body = {action: action}, k, s = getSession();
  for (k in (data || {})) body[k] = data[k];
  if (s && action !== 'login') body.token = s.token;
  return fetch(CLOUD.api, {method: 'POST', body: JSON.stringify(body),
                           headers: {'Content-Type': 'text/plain;charset=UTF-8'}})
    .then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.status === 401) setSession(null);       // пропуск истёк — выходим
        if (!r.ok) { var e = new Error(j.error || ('Ошибка ' + r.status)); e.status = r.status; throw e; }
        return j;
      });
    });
}

// Отметки, которые не удалось отправить (не было сети), — отправим позже.
function readPending() {
  try { return JSON.parse(localStorage.getItem('likes-pending') || '{}') || {}; } catch (e) { return {}; }
}
function writePending(map) {
  try {
    if (Object.keys(map).length) localStorage.setItem('likes-pending', JSON.stringify(map));
    else localStorage.removeItem('likes-pending');
  } catch (e) {}
}

// Свести отметки браузера и облака.
//   merge — сразу после входа: всё, что отмечено в браузере, уходит в облако.
//   иначе — облако главное: снятая на телефоне отметка снимается и здесь.
//     Не чаще раза в пять минут, чтобы не дёргать функцию на каждой странице.
// Возвращает true, если список в браузере обновился.
function cloudSync(mode) {
  if (!CLOUD.on || !getSession()) return Promise.resolve(false);
  var last = 0;
  try { last = +localStorage.getItem('likes-synced') || 0; } catch (e) {}
  if (mode !== 'merge' && mode !== 'force' && Date.now() - last < 5 * 60 * 1000) return Promise.resolve(false);
  var local = readLocalLikes(), pending = readPending(), k, up = [], down = [];
  for (k in (mode === 'merge' ? local : {})) if (local[k]) up.push(k);
  for (k in pending) (pending[k] ? up : down).push(k);
  return Promise.all(down.map(function (id) { return cloudCall('unlike', {post_id: id}); }))
    .then(function () { return cloudCall('sync', {likes: up}); })
    .then(function (j) {
      var merged = {};
      (j.likes || []).forEach(function (id) { merged[id] = true; });
      writeLocalLikes(merged);
      writePending({});
      try { localStorage.setItem('likes-synced', String(Date.now())); } catch (e) {}
      return true;
    })
    .catch(function (e) { console.warn('Избранное из облака недоступно:', e.message); return false; });
}
</script>""".replace("AUTH_API_URL", AUTH_API_URL).replace("YANDEX_CLIENT_ID", YANDEX_CLIENT_ID) \
    .replace("VK_CLIENT_ID", VK_CLIENT_ID).replace("AUTH_REDIRECT", AUTH_REDIRECT) \
    .replace("VK_ID_HOST", VK_ID_HOST)

# Страница картины: кнопка «Войти», окно входа, окно аккаунта и «сердечко».
AUTH_JS = CLOUD_JS + """
<script>
var PROVIDERS = {yandex: 'Яндекс ID', vk: 'VK ID'};

function randomString(n) {
  var abc = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  var a = new Uint8Array(n), s = '';
  crypto.getRandomValues(a);
  for (var i = 0; i < n; i++) s += abc[a[i] % 64];
  return s;
}
function b64url(buf) {
  var s = '', b = new Uint8Array(buf);
  for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
  return btoa(s).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
}

// Уйти на страницу Яндекса или VK. Вернутся оттуда на auth.html с кодом;
// что проверить и куда потом вернуть человека, запоминаем здесь.
function startLogin(provider) {
  var flow = {provider: provider, state: randomString(43), back: location.href};
  var go = function (url) {
    try { sessionStorage.setItem('auth-flow', JSON.stringify(flow)); } catch (e) {}
    location.assign(url);
  };
  if (provider === 'yandex') {
    go('https://oauth.yandex.ru/authorize?' + new URLSearchParams({
      response_type: 'code', client_id: CLOUD.yandex,
      redirect_uri: CLOUD.redirect, state: flow.state}).toString());
    return;
  }
  // VK ID требует PKCE: случайная строка остаётся у нас, её отпечаток
  // уходит в VK, а при обмене кода функция предъявит саму строку.
  flow.verifier = randomString(64);
  crypto.subtle.digest('SHA-256', new TextEncoder().encode(flow.verifier)).then(function (d) {
    go(CLOUD.vkHost + '/authorize?' + new URLSearchParams({
      response_type: 'code', client_id: CLOUD.vk, redirect_uri: CLOUD.redirect,
      state: flow.state, code_challenge: b64url(d), code_challenge_method: 'S256',
      scope: 'vkid.personal_info'}).toString());
  });
}

function showAuthButton() {
  var btn = document.getElementById('auth-btn');
  if (!btn) return;
  if (!CLOUD.on) { btn.remove(); return; }       // вход не настроен — кнопки нет
  var s = getSession();
  if (s) {
    btn.innerHTML = '<span class="icon-user" aria-hidden="true"></span> ';
    btn.appendChild(document.createTextNode(s.name || 'Профиль'));
    btn.title = 'Аккаунт: ' + (s.name || '');
    btn.setAttribute('aria-label', 'Аккаунт: ' + (s.name || ''));
    btn.onclick = showAccount;
  } else {
    btn.innerHTML = '<span class="icon-login" aria-hidden="true"></span> Войти';
    btn.title = 'Войти';
    btn.setAttribute('aria-label', 'Войти');
    btn.onclick = showAuthForm;
  }
}

// Общая рамка для окна входа и окна аккаунта: затемнение, Escape,
// клавиатура не уходит на страницу под окном, фокус возвращается назад.
function openDialog(title, lede, build) {
  var old = document.querySelector('.auth-modal-overlay');
  if (old) old.remove();
  var opener = document.activeElement;
  var overlay = document.createElement('div');
  overlay.className = 'auth-modal-overlay';
  overlay.innerHTML =
    '<div class="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">' +
      '<button type="button" class="auth-modal-close" id="auth-close-btn" aria-label="Закрыть">&times;</button>' +
      '<h3 id="auth-title"></h3><p id="auth-lede"></p>' +
      '<div class="auth-actions" id="auth-actions"></div>' +
      '<div class="auth-error" id="auth-error" role="alert"></div>' +
    '</div>';
  document.body.appendChild(overlay);
  document.getElementById('auth-title').textContent = title;
  document.getElementById('auth-lede').textContent = lede;
  var modal = overlay.querySelector('.auth-modal');
  function close(back) {
    overlay.remove();
    document.removeEventListener('keydown', onKey, true);
    if (back && opener && opener.focus) opener.focus();
  }
  function onKey(e) {
    if (e.key === 'Escape') { e.stopPropagation(); close(true); return; }
    if (e.key !== 'Tab') return;
    var items = [].slice.call(modal.querySelectorAll('button:not([disabled]), a[href]'));
    if (!items.length) return;
    var first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
  document.addEventListener('keydown', onKey, true);
  document.getElementById('auth-close-btn').onclick = function () { close(true); };
  overlay.onclick = function (e) { if (e.target === overlay) close(true); };
  build(document.getElementById('auth-actions'), close, function (t) {
    document.getElementById('auth-error').textContent = t || '';
  });
  var firstBtn = modal.querySelector('.auth-actions button');
  setTimeout(function () { (firstBtn || document.getElementById('auth-close-btn')).focus(); }, 60);
}

function actionButton(box, cls, text, onclick) {
  var b = document.createElement('button');
  b.type = 'button';
  b.className = cls;
  b.textContent = text;
  b.onclick = onclick;
  box.appendChild(b);
  return b;
}

function showAuthForm() {
  openDialog('Вход', 'Чтобы отмеченные картины были и на телефоне, и на компьютере.',
    function (box) {
      if (CLOUD.yandex) {
        var y = actionButton(box, 'auth-provider auth-yandex', 'Войти с Яндекс ID', function () {
          y.disabled = true; startLogin('yandex'); });
      }
      if (CLOUD.vk) {
        var v = actionButton(box, 'auth-provider auth-vk', 'Войти с VK ID', function () {
          v.disabled = true; startLogin('vk'); });
      }
    });
}

function showAccount() {
  var s = getSession();
  if (!s) { showAuthButton(); showAuthForm(); return; }
  openDialog(s.name || 'Аккаунт', 'Вы вошли через ' + (PROVIDERS[s.provider] || 'аккаунт') +
             '. Отмеченные картины видны на всех ваших устройствах.',
    function (box, close, say) {
      actionButton(box, 'auth-provider', 'Выйти', function () {
        setSession(null);
        close(true);
        showAuthButton();
        toast('Вы вышли из аккаунта');
      });
      // Удаление — в два нажатия: первое спрашивает, второе удаляет.
      var sure = false;
      var del = actionButton(box, 'auth-link auth-danger', 'Удалить мои отметки из облака', function () {
        if (!sure) { sure = true; del.textContent = 'Точно удалить? Нажмите ещё раз'; return; }
        del.disabled = true;
        cloudCall('delete').then(function () {
          setSession(null);
          close(true);
          showAuthButton();
          toast('Отметки удалены из облака; в этом браузере они остались');
        }).catch(function (e) { del.disabled = false; say(e.message); });
      });
    });
}

// ---------- Избранное ----------
// Сколько посетителей добавили картину в избранное (по облаку — то есть
// те, кто вошёл). null — число ещё не пришло.
var likeCount = null;
function paintCount() {
  var el = document.getElementById('like-count'), btn = document.getElementById('like-btn');
  if (!el || !btn) return;
  var on = btn.getAttribute('aria-pressed') === 'true';
  var base = on ? 'Убрать из избранного' : 'В избранное';
  if (likeCount > 0) {
    el.textContent = likeCount;
    el.hidden = false;
    btn.title = base + ' · добавили: ' + likeCount;
    btn.setAttribute('aria-label', base + '. Уже добавили: ' + likeCount);
  } else {
    el.hidden = true;
    btn.title = base;
    btn.setAttribute('aria-label', base);
  }
}

function paintLike(on) {
  var btn = document.getElementById('like-btn');
  if (!btn) return;
  btn.classList.toggle('liked', on);
  btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  btn.setAttribute('aria-label', on ? 'Убрать из избранного' : 'В избранное');
  paintCount();
}

function syncLike(postId, liked) {
  var local = readLocalLikes();
  if (liked) local[postId] = true; else delete local[postId];
  writeLocalLikes(local);
  if (!CLOUD.on || !getSession()) return Promise.resolve();
  return cloudCall(liked ? 'like' : 'unlike', {post_id: postId}).then(function () {
    // своя отметка сразу видна в общем числе
    likeCount = Math.max(0, (likeCount || 0) + (liked ? 1 : -1));
    paintCount();
  }).catch(function (e) {
    if (e.status === 401) { showAuthButton(); toast('Срок входа истёк — войдите снова'); return; }
    var p = readPending(); p[postId] = liked; writePending(p);
    toast('Нет связи с облаком — отметка сохранится, когда связь появится');
  });
}

// Работает и без аккаунта: отметка всегда сначала ложится в браузер.
function toggleLike() {
  var btn = document.getElementById('like-btn');
  if (!btn) return;
  var pid = btn.dataset.postId;
  var next = !readLocalLikes()[pid];
  paintLike(next);
  var done = syncLike(pid, next);
  try {
    if (window.opener && window.opener.updateFavList) window.opener.updateFavList();
  } catch (e) {}
  return done;
}

showAuthButton();
(function () {
  var greet = null;
  try { greet = sessionStorage.getItem('auth-greet'); sessionStorage.removeItem('auth-greet'); } catch (e) {}
  var s = getSession();
  // Поздороваться — только сразу после входа, а не на каждой странице.
  if (greet && s) toast('Вы вошли как ' + (s.name || 'пользователь'));
  cloudSync().then(function (changed) {
    var btn = document.getElementById('like-btn');
    if (changed && btn) paintLike(!!readLocalLikes()[btn.dataset.postId]);
  });
  var lb = document.getElementById('like-btn');
  if (CLOUD.on && lb) {
    cloudCall('counts', {post_ids: [lb.dataset.postId]}).then(function (j) {
      likeCount = (j.counts || {})[lb.dataset.postId] || 0;
      paintCount();
    }).catch(function () {});
  }
})();
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
        + f'<a href="{rss}">RSS</a> · '
        '<a href="privacy.html">Конфиденциальность</a>'
        '</p>'
        '</footer>'
    )
