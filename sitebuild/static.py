# -*- coding: utf-8 -*-
"""Служебные страницы и файлы: 404, конфиденциальность, вход, карта сайта, RSS, иконки.

Часть сборки сайта (build_site.py), вынесена в отдельный модуль.
"""

import os
import json
from datetime import datetime, timezone
from email.utils import format_datetime
import urllib.parse
from urllib.parse import quote
from html import escape as h
from site_common import (
    head_common, theme_button, site_footer, mark_svg, TELEGRAM_NAME, SITE_DOMAIN, COMMON_JS,
    CLOUD_JS, BASE_URL, METRIKA_ID, SITE_OWNER, PRIVACY_CONTACT, PRIVACY_CONTACT_TEXT,
    PRIVACY_DATE, AUTH_API_URL, YANDEX_CLIENT_ID, VK_CLIENT_ID, museum_page, has_afisha,
)
import logging
from .config import IMAGES_DIR, OUTPUT_DIR
from .slugs import artist_slug, tag_slug
from .html import tidy
from .images import Image, PIL_AVAILABLE
from .places import museum_names

logger = logging.getLogger("build_site")

def generate_cname():
    """Файл CNAME — то, по чему GitHub Pages понимает, что у сайта свой домен.

    Пишем его сборкой, а не руками: иначе однажды он потеряется при
    очередной пересборке или переносе, и сайт молча вернётся на github.io
    вместе со всеми ссылками. Если домена нет, ничего не трогаем — в том
    числе не удаляем файл, который мог быть создан через настройки GitHub.
    """
    if not SITE_DOMAIN:
        return
    with open(os.path.join(OUTPUT_DIR, "CNAME"), "w", encoding="utf-8", newline="\n") as f:
        f.write(SITE_DOMAIN + "\n")
    logger.info(f"CNAME → {SITE_DOMAIN}")


def generate_robots():
    """robots.txt со ссылкой на карту сайта.

    Без него поисковик находит sitemap.xml только случайно.
    """
    body = ("User-agent: *\n"
            "Allow: /\n"
            "\n"
            f"Sitemap: {BASE_URL}/sitemap.xml\n")
    with open(os.path.join(OUTPUT_DIR, "robots.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    logger.info("robots.txt")

@tidy
def render_404():
    """Раньше 404 была пустой страницей с meta refresh: без заголовка,
    без объяснения, и на вложенных адресах редирект вёл в никуда."""
    # base href="/" — обязательно. GitHub Pages показывает эту страницу
    # по любому несуществующему адресу, в том числе вложенному вроде
    # /старое/имя.html. Все адреса на странице относительные — стили,
    # значок, ссылки, — и без base они считались бы от /старое/: стили не
    # загрузились бы, а «В галерею» вело бы на ещё одну страницу 404.
    head = head_common(
        title="Страница не найдена — Old Picture Art",
        description="Такой страницы нет. Вернитесь в галерею Old Picture Art.",
    )
    # Сразу после кодировки, до всего остального: элементы, стоящие в
    # head раньше base, успевают разрешить свои адреса по адресу самой
    # страницы. Поставь base в конец — и стиль на вложенном адресе
    # всё равно бы не загрузился.
    head = head.replace('<meta charset="UTF-8">', '<meta charset="UTF-8">\n<base href="/">', 1)
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="error-page">
<main class="error-box">
  <p class="error-code">404</p>
  <h1>Страница не найдена</h1>
  <p class="error-text">Возможно, картину переименовали или ссылка устарела.</p>
  <p><a class="random-btn" href="./">В галерею</a></p>
  <p class="error-links"><a href="quiz.html">Квиз</a> · <a href="timeline.html">Таймлайн</a> · <a href="museums.html">Карта собраний</a></p>
</main>
{site_footer()}
{COMMON_JS}
</body></html>"""


@tidy
def render_privacy():
    """Страница о данных: что сайт узнаёт о посетителе, зачем и как отказаться.

    Написана для людей, а не для проверяющих: коротко, по разделам, без
    «настоящим уведомляем». Каждый раздел отвечает на три вопроса — что
    собирается, кем и как это выключить. Раздел о Метрике исчезает, если
    счётчик выключен (METRIKA_ID пуст), — не описывать того, чего нет.
    """
    auth_on = bool(AUTH_API_URL and (YANDEX_CLIENT_ID or VK_CLIENT_ID))
    # Оригиналы в облачном хранилище — это ещё один адрес, куда браузер
    # ходит (кнопка «Скачать» и лупа).
    import site_common
    hires_host = urllib.parse.urlsplit(site_common.HIRES_BASE_URL or "").netloc
    hires_li = (f'    <li>{hires_host} — оригиналы картин для скачивания и лупы;</li>'
                if hires_host else '')
    head = head_common(
        title="Конфиденциальность — Old Picture Art",
        description="Какие данные собирает сайт Old Picture Art, зачем и как от этого отказаться: "
                    + ("Яндекс Метрика, вход через Яндекс ID и VK ID, настройки в браузере."
                       if auth_on else "Яндекс Метрика и настройки в браузере."),
        canonical=f"{BASE_URL}/privacy.html",
    )
    contact = (f'<a href="{h(PRIVACY_CONTACT)}"'
               + ('' if PRIVACY_CONTACT.startswith("mailto:") else ' target="_blank" rel="noopener"')
               + f'>{h(PRIVACY_CONTACT_TEXT)}</a>')
    owner = f"Сайт ведёт {h(SITE_OWNER)}. " if SITE_OWNER else ""
    # Про вход рассказываем, только когда он настроен (AUTH_API_URL и хотя
    # бы один из YANDEX_CLIENT_ID / VK_CLIENT_ID в site_common.py):
    # описывать на странице о данных то, чего на сайте нет, — путать людей.
    # Пока входа нет, страница так и говорит: аккаунтов нет, отметки —
    # только в браузере. Входа через Google и Firebase больше нет совсем.
    account = f"""<section class="doc-block" id="account">
  <h2>Вход в аккаунт</h2>
  <p>Нужен только для одного — чтобы отмеченные картины были на всех ваших устройствах.
  Без входа отметки хранятся в вашем браузере и никуда не отправляются.</p>
  <h3>Как входят</h3>
  <p>Через Яндекс ID или VK ID. Пароль вы вводите на странице Яндекса или VK — сайт его
  не видит. Яндекс или VK сообщают сайту номер вашего аккаунта у них и имя.</p>
  <h3>Что хранится</h3>
  <ul>
    <li>номер аккаунта у Яндекса или VK и список отмеченных картин со временем отметки —
    в базе на серверах Yandex Cloud в России;</li>
    <li>имя — только в вашем браузере, чтобы показать его на кнопке; на сервер оно не записывается.</li>
  </ul>
  <p>Сколько раз отмечена картина, видят все посетители — только число, без имён и
  аккаунтов; из этих же чисел собран блок «Популярное у посетителей» на главной.</p>
  <p>Почту, телефон и список друзей сайт не запрашивает. Базу держит ООО «Яндекс.Облако»,
  вход проверяют ООО «ЯНДЕКС» (Яндекс ID) и ООО «ВК» (VK ID) — каждый по своим правилам.</p>
  <h3>Как удалить</h3>
  <p>Снятая отметка удаляется сразу. Все отметки разом — кнопкой «Удалить мои отметки из
  облака» в окне аккаунта (нажмите на своё имя вверху страницы картины). Выйти из аккаунта
  можно там же. Вопросы — {contact}.</p>
</section>"""

    metrika = "" if not METRIKA_ID else """
<section class="doc-block" id="metrika">
  <h2>Статистика посещений — Яндекс Метрика</h2>
  <p>Включается, только если вы нажали «Принять» на плашке внизу страницы. До этого
  счётчик не загружается и ничего не отправляет.</p>
  <div class="consent-controls" id="consent-controls">
    <p class="consent-state" id="consent-state" role="status">Статистика: вы пока не решили.</p>
    <p class="consent-actions">
      <button type="button" class="consent-btn" data-consent="yes">Разрешить статистику</button>
      <button type="button" class="consent-btn" data-consent="no">Отключить статистику</button>
    </p>
  </div>
  <h3>Что получает Метрика</h3>
  <ul>
    <li>cookie <code>_ym_uid</code>, <code>_ym_d</code>, <code>_ym_isad</code> и другие — чтобы отличить повторный визит от нового; самая долгая живёт год;</li>
    <li>IP-адрес, тип устройства, браузер, размер экрана, язык;</li>
    <li>адрес страницы и откуда вы на неё пришли;</li>
    <li>действия на странице — прокрутку, нажатия, движение указателя (это Вебвизор).</li>
  </ul>
  <p>Имени, почты и телефона Метрика не получает.</p>
  <h3>Зачем</h3>
  <p>Чтобы понимать, какие картины смотрят, откуда приходят и где на сайте неудобно.
  Рекламы здесь нет, и данные для неё не используются.</p>
  <h3>Кто обрабатывает</h3>
  <p>ООО «ЯНДЕКС» — по своим <a href="https://yandex.ru/legal/metrica_termsofuse/" target="_blank" rel="noopener">условиям
  использования Метрики</a> и <a href="https://yandex.ru/legal/confidential/" target="_blank" rel="noopener">политике
  конфиденциальности</a>.</p>
  <h3>Как отказаться</h3>
  <ul>
    <li>кнопкой «Отключить статистику» выше — сайт сотрёт cookie Метрики на своём адресе и больше её не загрузит;</li>
    <li>для всех сайтов сразу — <a href="https://yandex.ru/support/metrica/ru/general/opt-out" target="_blank" rel="noopener">блокировщиком
    Яндекс Метрики</a>, расширением для браузера от самого Яндекса;</li>
    <li>в настройках браузера — запретив cookie или очистив данные сайта.</li>
  </ul>
</section>"""

    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="tag-page doc-page">
<div class="tag-topbar">
  <a href="./" class="back"><span class="icon-back" aria-hidden="true"></span> На главную</a>
  {theme_button('theme-toggle-inline')}
</div>
<header class="artist-head">
  <p class="eyebrow">О сайте</p>
  <h1>Конфиденциальность</h1>
  <p class="doc-lede">Old Picture Art — некоммерческое собрание картин из телеграм-канала
  {h(TELEGRAM_NAME)}. {owner}Здесь коротко о том, что сайт узнаёт о посетителях, зачем и как от этого отказаться.</p>
  <p class="doc-date">Редакция от {h(PRIVACY_DATE)}</p>
</header>
<main class="doc-body">
<section class="doc-block" id="short">
  <h2>Коротко</h2>
  <ul>
    <li>Смотреть картины, искать, играть в квиз можно без регистрации и без согласия на статистику.</li>
    <li>Статистика посещений включается, только если вы её разрешили.</li>
{'    <li>Аккаунт нужен только для переноса отметок между устройствами; вход — через Яндекс ID или VK ID. Номер аккаунта хранится, только если вы сами вошли.</li>' if auth_on else '    <li>Аккаунтов на сайте нет: отмеченные картины хранятся только в вашем браузере.</li>'}
    <li>Данные не продаются и не передаются никому, кроме названных ниже сервисов.</li>
  </ul>
</section>
{metrika}
{account if auth_on else ""}
<section class="doc-block" id="browser">
  <h2>Что остаётся только в вашем браузере</h2>
  <p>В хранилище браузера (localStorage) сайт запоминает тему оформления, выбранную
  подложку карты, отмеченные картины, счёт в квизе и ваш ответ насчёт статистики{", а если вы вошли — ещё пропуск для входа и ваше имя" if auth_on else ""}.
  {"Отметки вошедших дублируются в облако (см. выше), остальное" if auth_on else "Это"} не уходит ни на какой сервер;
  стереть — очистить данные сайта в настройках браузера.</p>
</section>

<section class="doc-block" id="services">
  <h2>Откуда загружаются части страниц</h2>
  <p>Чтобы показать страницу, браузер обращается к этим сервисам и, как при любом запросе
  в интернете, сообщает им свой IP-адрес:</p>
  <ul>
    <li>GitHub Pages — хостинг сайта (<a href="https://docs.github.com/ru/site-policy/privacy-policies/github-general-privacy-statement" target="_blank" rel="noopener">политика GitHub</a>);</li>
{'    <li>functions.yandexcloud.net — отметки тех, кто вошёл в аккаунт;</li>' if auth_on else ''}
{hires_li}
    <li>на карте собраний и страницах музеев — подложки Яндекс Карт, OpenStreetMap и Esri.</li>
  </ul>
  <p>Шрифты, библиотека карты и код подбора цвета рамки лежат на самом сайте и
  ни с каких других серверов не загружаются.</p>
</section>

<section class="doc-block" id="contact">
  <h2>Вопросы</h2>
  <p>О данных{", об удалении отметок из облака" if auth_on else ""} и обо всём остальном — {contact}.</p>
</section>
</main>
{site_footer()}
{COMMON_JS}
<script>
// Кнопки согласия на этой странице и строка с текущим выбором.
(function () {{
  var box = document.getElementById('consent-controls');
  if (!box || !window.metrikaConsent) return;
  var state = document.getElementById('consent-state');
  function show() {{
    var v = window.metrikaConsent.state();
    state.textContent = v === 'yes' ? 'Статистика сейчас разрешена.'
                      : v === 'no' ? 'Статистика сейчас отключена.'
                      : 'Статистика: вы пока не решили — счётчик не загружается.';
    box.querySelectorAll('[data-consent]').forEach(function (b) {{
      b.setAttribute('aria-pressed', b.getAttribute('data-consent') === v ? 'true' : 'false');
    }});
  }}
  box.addEventListener('click', function (e) {{
    var v = e.target.getAttribute && e.target.getAttribute('data-consent');
    if (v === 'yes') window.metrikaConsent.allow();
    else if (v === 'no' && window.metrikaConsent.deny()) {{
      // счётчик уже работал на этой странице — остановить его можно только перезагрузкой
      location.reload();
      return;
    }}
    show();
  }});
  show();
}})();
</script>
</body></html>"""


@tidy
def render_auth_page():
    """auth.html — куда Яндекс ID и VK ID возвращают человека после входа.

    Страница служебная: забирает из адреса код входа, проверяет, что это
    ответ на наш же запрос (state), отдаёт код функции в Yandex Cloud,
    получает пропуск, сводит отметки и возвращает человека туда, откуда
    он нажал «Войти». Если что-то не так — говорит об этом словами и
    даёт вернуться. В поиск ей незачем, отсюда noindex.
    """
    head = head_common(
        title="Вход — Old Picture Art",
        description="Вход в аккаунт Old Picture Art.",
        extra='\n<meta name="robots" content="noindex">',
    )
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body class="error-page">
<main class="error-box">
  <h1 id="auth-status">Входим…</h1>
  <p class="error-text" id="auth-msg" role="status">Минуту — сверяемся с Яндексом или VK.</p>
  <p><a class="random-btn" id="auth-back" href="./">Вернуться на сайт</a></p>
</main>
{CLOUD_JS}
<script>
(function () {{
  var q = new URLSearchParams(location.search);
  var flow = null;
  try {{ flow = JSON.parse(sessionStorage.getItem('auth-flow') || 'null'); sessionStorage.removeItem('auth-flow'); }} catch (e) {{}}
  // Вернуть можно только на свой же сайт — чужой адрес в back не пройдёт.
  var back = './';
  try {{ if (flow && flow.back && new URL(flow.back).origin === location.origin) back = flow.back; }} catch (e) {{}}
  document.getElementById('auth-back').href = back;

  function fail(text) {{
    document.getElementById('auth-status').textContent = 'Войти не получилось';
    document.getElementById('auth-msg').textContent = text;
  }}
  if (!CLOUD.on) return fail('Вход на сайте сейчас выключен.');
  if (q.get('error')) {{
    return fail(q.get('error') === 'access_denied' ? 'Вход отменён.'
                : 'Ответ сервиса входа: ' + (q.get('error_description') || q.get('error')));
  }}
  if (!flow || !q.get('code') || q.get('state') !== flow.state) {{
    return fail('Не удалось проверить, что это ваш вход. Попробуйте войти ещё раз.');
  }}
  var data = {{provider: flow.provider, code: q.get('code'), state: q.get('state')}};
  if (flow.provider === 'vk') {{ data.code_verifier = flow.verifier; data.device_id = q.get('device_id'); }}
  cloudCall('login', data)
    .then(function (j) {{
      setSession({{token: j.token, name: j.name, provider: j.provider, exp: j.exp}});
      return cloudSync('merge');
    }})
    .then(function () {{
      try {{ sessionStorage.setItem('auth-greet', '1'); }} catch (e) {{}}
      location.replace(back);
    }})
    .catch(function (e) {{ fail(e.message || 'Сервер не ответил. Попробуйте позже.'); }});
}})();
</script>
</body></html>"""

def generate_sitemap(all_posts, visits=None):
    logger.info("Sitemap...")
    bu = BASE_URL
    # Кодирование оставлено, хотя имена страниц теперь латинские: в
    # карту попадают и адреса картинок, а те по-прежнему кириллические.
    # Страницы-перенаправления со старых адресов сюда не попадают —
    # список строится по нынешним именам, а не по содержимому папки.
    def u(path):
        return quote(path, safe="/")
    urls = [f"  <url><loc>{bu}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for p in all_posts: urls.append(f"  <url><loc>{bu}/{u(p['filename'])}</loc><lastmod>{p['date']}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>")
    urls.append(f"  <url><loc>{bu}/feed.xml</loc><changefreq>daily</changefreq><priority>0.6</priority></url>")
    urls.append(f"  <url><loc>{bu}/museums.html</loc><changefreq>monthly</changefreq><priority>0.4</priority></url>")
    urls.append(f"  <url><loc>{bu}/quiz.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    urls.append(f"  <url><loc>{bu}/timeline.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    urls.append(f"  <url><loc>{bu}/ukazatel.html</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>")
    urls.append(f"  <url><loc>{bu}/stats.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    urls.append(f"  <url><loc>{bu}/privacy.html</loc><changefreq>yearly</changefreq><priority>0.2</priority></url>")
    # Посещения — только если они есть: ссылка на несуществующую
    # страницу в карте сайта портит её целиком.
    if has_afisha():
        urls.append(f"  <url><loc>{bu}/afisha.html</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>")
    visits = visits or []
    if visits:
        urls.append(f"  <url><loc>{bu}/visits.html</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
        for v in visits:
            urls.append(f"  <url><loc>{bu}/{u(v['filename'])}</loc><lastmod>{v['date']}</lastmod><changefreq>monthly</changefreq><priority>0.5</priority></url>")
    # Страницы художников — то, что ищут чаще всего («Левитан картины»),
    # поэтому приоритет у них выше, чем у тегов.
    for a in sorted({p["artist"].strip() for p in all_posts if p.get("artist")}):
        urls.append(f"  <url><loc>{bu}/{u(artist_slug(a))}</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>")
    at = set()
    for p in all_posts:
        for t in p.get("tags",[]): at.add(t)
    for t in sorted(at): urls.append(f"  <url><loc>{bu}/{u('tag-' + tag_slug(t) + '.html')}</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    # Страницы музеев: «картины из Прадо» ищут не реже, чем художника.
    for name in museum_names(all_posts, visits):
        urls.append(f"  <url><loc>{bu}/{u(museum_page(name))}</loc><changefreq>monthly</changefreq><priority>0.6</priority></url>")
    with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + '\n</urlset>')
    logger.info(f"Sitemap ({len(urls)} URL)")

def _draw_mark(size, inset=0.0):
    """Знак сайта растром. inset — доля поля вокруг рисунка: для плиток
    Android (maskable) края обрезаются, поэтому там знак ужимаем внутрь."""
    from PIL import ImageDraw
    navy = (31, 58, 107, 255)
    cream = (242, 237, 227, 255)
    ochre = (201, 163, 94, 255)
    img = Image.new("RGBA", (size, size), navy)
    d = ImageDraw.Draw(img)
    pad = size * inset
    s = (size - 2 * pad) / 32.0

    def box(x0, y0, x1, y1, fill):
        d.rectangle([pad + x0 * s, pad + y0 * s, pad + x1 * s, pad + y1 * s], fill=fill)

    box(4, 6, 28, 26, cream)          # холст
    box(4, 20, 28, 26, ochre)         # земля
    r = 3 * s
    cx, cy = pad + 22 * s, pad + 12 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=navy)   # солнце
    return img


def generate_icons():
    """Значки сайта: svg для вкладки, ico для старых браузеров, png для
    телефона и манифеста. Раньше манифест ссылался на файлы, которых
    в репозитории не было, а фавикон был отдельной картинкой, ничем
    не связанной с оформлением."""
    # svg пишем всегда: он не требует PIL и именно его берут современные браузеры
    with open(os.path.join(OUTPUT_DIR, "favicon.svg"), "w", encoding="utf-8", newline="\n") as f:
        f.write(mark_svg())

    if not PIL_AVAILABLE:
        logger.warning("PIL не установлен — png и ico значки не обновлены")
        return []

    # ico собираем из отрисованных размеров, а не уменьшением одного:
    # у знака прямые границы, и пересчёт их размывает
    ico_sizes = [16, 32, 48]
    frames = [_draw_mark(n) for n in ico_sizes]
    frames[-1].save(os.path.join(OUTPUT_DIR, "favicon.ico"),
                    format="ICO", sizes=[(n, n) for n in ico_sizes],
                    append_images=frames[:-1])

    _draw_mark(180).save(os.path.join(OUTPUT_DIR, "apple-touch-icon.png"), "PNG")

    made = []
    for size in (192, 512):
        _draw_mark(size).save(os.path.join(IMAGES_DIR, f"icon-{size}.png"), "PNG")
        made.append((f"images/icon-{size}.png", size, "any"))
        # maskable Android обрезает по кругу — знак должен уместиться внутри
        _draw_mark(size, inset=0.18).save(os.path.join(IMAGES_DIR, f"icon-{size}-maskable.png"), "PNG")
        made.append((f"images/icon-{size}-maskable.png", size, "maskable"))
    return made


def generate_manifest():
    icons = [{"src": src, "sizes": f"{n}x{n}", "type": "image/png", "purpose": purpose}
             for src, n, purpose in generate_icons()]
    data = {
        "name": "Old Picture Art",
        "short_name": "OldPictureArt",
        "description": "Галерея картин из старых музейных собраний",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "lang": "ru",
        "background_color": "#eceef1",
        "theme_color": "#eceef1",
        "icons": icons,
    }
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"manifest.json ({len(icons)} иконок)")

def rfc822(date_str):
    """RSS 2.0 требует дату в формате RFC-822. Раньше отдавали 2025-11-26,
    и часть читалок такие записи отбрасывала или сортировала как попало."""
    try:
        return format_datetime(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc))
    except Exception:
        return format_datetime(datetime.now(timezone.utc))


def generate_rss(all_posts):
    logger.info("Генерация RSS...")
    base_url = BASE_URL
    items = []
    for p in sorted(all_posts, key=lambda x: x["date"], reverse=True)[:50]:
        desc = (p.get("description") or "")[:500]
        imgs = p.get("images") or [""]
        img = quote(imgs[0], safe="/") if imgs[0] else ""
        link = f"{base_url}/{quote(p['filename'], safe='/')}"
        img_tag = f'<img src="{base_url}/{img}" style="max-width:100%" alt=""/><br>' if img else ""
        items.append(f"""    <item>
      <title>{h(p['artist'])} — {h(p['title'])}</title>
      <link>{link}</link>
      <description><![CDATA[{img_tag}{h(desc)}]]></description>
      <pubDate>{rfc822(p['date'])}</pubDate>
      <guid isPermaLink="true">{link}</guid>
    </item>""")
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>Old Picture Art</title>
  <link>{base_url}</link>
  <description>Галерея картин из Telegram канала Old Picture Art</description>
  <language>ru</language>
  <atom:link href="{base_url}/feed.xml" rel="self" type="application/rss+xml"/>
{''.join(items)}
</channel>
</rss>"""
    with open(os.path.join(OUTPUT_DIR, "feed.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(rss)
    logger.info("RSS сгенерирован")

__all__ = [
    'generate_cname',
    'generate_robots',
    'render_404',
    'render_privacy',
    'render_auth_page',
    'generate_sitemap',
    '_draw_mark',
    'generate_icons',
    'generate_manifest',
    'rfc822',
    'generate_rss',
]
