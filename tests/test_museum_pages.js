// Страницы музеев: у каждого места своя страница — картины, походы,
// адрес, сайт, кусок карты. На неё ведут «Собрание» у картины, карточки,
// опись, страницы походов и карта собраний.
//
// Проверяется то, что может тихо сломаться: страница есть у каждого места
// и адрес у неё один; все ссылки на музеи ведут на существующие файлы;
// частные собрания страниц не получают и ведут на карту; разметка для
// поисковиков разбирается; мини-карта поднимается, приближается колесом
// и двигается пальцем; шапка — сведения и карта рядом, на телефоне карта
// сразу за сведениями, а не под всеми картинами.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const DOCS = path.join(ROOT, 'docs');
const f = n => 'file://' + DOCS + '/' + encodeURIComponent(n).replace(/%2F/g, '/');
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};
const read = n => fs.readFileSync(path.join(DOCS, n), 'utf8');
const exists = n => fs.existsSync(path.join(DOCS, decodeURIComponent(n)));

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

const meta = JSON.parse(fs.readFileSync(path.join(ROOT, 'posts_meta.json'), 'utf8'));
const overrides = JSON.parse(fs.readFileSync(path.join(ROOT, 'museum_overrides.json'), 'utf8'));
const pages = fs.readdirSync(DOCS).filter(n => /^museum-.*\.html$/.test(n));

function ldOf(html) {
  return [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)]
    .map(m => { try { return JSON.parse(m[1]); } catch (e) { return { bad: m[1].slice(0, 80) }; } });
}

(async () => {
  // ---------- страницы есть, адреса уникальны ----------
  const museums = [...new Set(meta.map(p => (p.museum || '').trim()).filter(Boolean))];
  const skipped = museums.filter(m => (overrides[m] || {}).skip);
  ok('страниц музеев не меньше, чем собраний в постах (кроме частных)',
    pages.length >= museums.length - skipped.length, `${pages.length} страниц, ${museums.length - skipped.length} собраний`);
  ok('имена страниц — латиница, без пробелов', pages.every(n => /^museum-[a-z0-9-]+\.html$/.test(n)),
    pages.filter(n => !/^museum-[a-z0-9-]+\.html$/.test(n)).join(', '));

  // ---------- «Собрание» у каждой картины ведёт на существующую страницу ----------
  let broken = [], toMap = [];
  for (const p of meta) {
    if (!p.museum || !fs.existsSync(path.join(DOCS, p.filename))) continue;
    const m = read(p.filename).match(/<span>Собрание<\/span><b><a href="([^"]+)"/);
    if (!m) { broken.push(p.filename + ' (нет строки)'); continue; }
    const href = m[1];
    if ((overrides[p.museum.trim()] || {}).skip) {
      if (!href.startsWith('museums.html#museum-')) toMap.push(p.filename);
    } else if (!href.startsWith('museum-') || !exists(href)) broken.push(p.filename + ' → ' + href);
  }
  ok('«Собрание» у картины ведёт на страницу музея', !broken.length, broken.slice(0, 3).join('; '));
  ok('у частных собраний — на карточку карты (своей страницы нет)', !toMap.length, toMap.join(', '));

  // ---------- карточки на главной, опись, статистика ----------
  for (const page of ['index.html', 'ukazatel.html', 'stats.html']) {
    const hrefs = [...read(page).matchAll(/href="(museum-[^"]+\.html)"/g)].map(m => m[1]);
    const dead = [...new Set(hrefs.filter(h => !exists(h)))];
    ok(`${page}: ссылки на музеи живые`, hrefs.length && !dead.length, dead.slice(0, 3).join(', ') || `${hrefs.length} ссылок`);
  }

  // ---------- карта собраний ----------
  const map = read('museums.html');
  const titleLinks = [...map.matchAll(/class="museum-page-link" href="([^"]+)"/g)].map(m => m[1]);
  ok('в карточке на карте собраний — ссылка на страницу музея', titleLinks.length >= pages.length - 1,
    `${titleLinks.length} ссылок`);
  ok('…и все такие ссылки живые', titleLinks.every(exists), titleLinks.filter(h => !exists(h)).join(', '));
  ok('в данных меток есть адрес страницы', /"page":\s*"museum-[a-z0-9-]+\.html"/.test(map));

  // ---------- каждая страница ----------
  let noLd = [], badLd = [], noMapLink = [];
  for (const n of pages) {
    const html = read(n);
    const lds = ldOf(html);
    const museum = lds.find(x => x['@type'] === 'Museum');
    if (!museum) noLd.push(n);
    else if (!museum.name || (museum.address && !museum.address.addressLocality && !museum.address.streetAddress)) badLd.push(n);
    if (!/href="museums\.html#museum-/.test(html)) noMapLink.push(n);
  }
  ok('на каждой странице разметка Museum', !noLd.length, noLd.slice(0, 3).join(', '));
  ok('разметка с названием и адресом', !badLd.length, badLd.slice(0, 3).join(', '));
  ok('с каждой страницы можно вернуться к карточке на карте', !noMapLink.length, noMapLink.slice(0, 3).join(', '));

  // ---------- разметка выставок у походов ----------
  let visits = [];
  try { visits = JSON.parse(fs.readFileSync(path.join(ROOT, 'visits_meta.json'), 'utf8')); } catch (e) {}
  const shows = visits.filter(v => v.kind === 'выставка' && /\d{1,2}\.\d{1,2}\.\d{4}\s*[—–-]/.test(v.run || ''));
  let evBad = [];
  for (const v of shows) {
    const ev = ldOf(read(v.filename)).find(x => x['@type'] === 'ExhibitionEvent');
    if (!ev || !/^\d{4}-\d{2}-\d{2}$/.test(ev.startDate || '') || !/^\d{4}-\d{2}-\d{2}$/.test(ev.endDate || '')
        || !ev.location || !ev.location.name || ev.endDate < ev.startDate) evBad.push(v.filename);
  }
  ok('у выставок со сроком — ExhibitionEvent с датами и местом', shows.length && !evBad.length,
    evBad.slice(0, 3).join(', ') || `${shows.length} выставок`);
  const noTrack = shows.every(v => !/ysclid|utm_/.test(read(v.filename)));
  ok('в ссылках на выставки нет меток слежения (ysclid, utm_…)', noTrack);
  const museumVisit = visits.find(v => v.kind !== 'выставка');
  if (museumVisit) {
    ok('у похода в музей событий не размечено',
      !ldOf(read(museumVisit.filename)).some(x => x['@type'] === 'ExhibitionEvent'));
  }

  // ---------- карта сайта ----------
  const sitemap = read('sitemap.xml');
  ok('страницы музеев в карте сайта', pages.every(n => sitemap.includes('/' + n)),
    pages.filter(n => !sitemap.includes('/' + n)).slice(0, 3).join(', '));

  // ---------- в браузере ----------
  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const NM = p => require.resolve(p);
  async function open(n, theme) {
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', r => r.fulfill({ path: NM('leaflet/dist/leaflet.js') }));
    await page.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css', r => r.fulfill({ path: NM('leaflet/dist/leaflet.css') }));
    await page.route(/tile\.openstreetmap\.org|tiles\.api-maps\.yandex\.ru/, r => r.abort());
    if (theme) await page.addInitScript(t => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme);
    await page.goto(f(n));
    await page.waitForTimeout(500);
    return { page, errors };
  }

  const withWorks = meta.find(p => p.museum && !(overrides[p.museum.trim()] || {}).skip);
  const workPage = read(withWorks.filename).match(/<span>Собрание<\/span><b><a href="([^"]+)"/)[1];
  let { page, errors } = await open(workPage);
  const info = await page.evaluate(() => ({
    h1: document.querySelector('h1').textContent,
    cards: document.querySelectorAll('.grid .card:not(.visit-card)').length,
    museumOnCards: document.querySelectorAll('.grid .card:not(.visit-card) .card-museum').length,
    map: !!document.querySelector('#mini-map.leaflet-container'),
    wheel: (() => { const m = document.querySelector('#mini-map'); return m && m._leaflet_id ? true : false; })(),
    back: !!document.querySelector('a[href="museums.html"]'),
  }));
  ok('страница музея: заголовок — название собрания', info.h1.trim() === withWorks.museum.trim(), info.h1);
  ok('картины собрания на месте', info.cards >= 1, info.cards + ' карточек');
  ok('в карточках собрание не повторяется', info.museumOnCards === 0);
  ok('мини-карта поднялась', info.map);
  ok('ошибок в консоли нет', !errors.length, errors.join('; '));
  const mm = await page.evaluate(() => {
    const m = document.querySelector('#mini-map').miniMap;
    return m ? { wheel: m.scrollWheelZoom.enabled(), drag: m.dragging.enabled(), zoom: m.getZoom() } : null;
  });
  ok('мини-карта: колесо и перетаскивание включены', mm && mm.wheel && mm.drag, JSON.stringify(mm));
  const box = await page.locator('#mini-map').boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -400);
  await page.waitForTimeout(700);
  const zoomed = await page.evaluate(() => document.querySelector('#mini-map').miniMap.getZoom());
  ok('колесо мыши над мини-картой приближает её', mm && zoomed > mm.zoom, `${mm && mm.zoom} → ${zoomed}`);

  // Шапка: сведения слева, карта справа на той же высоте; справа от
  // списка картин узкой колонки больше нет.
  const lay = await page.evaluate(() => {
    const r = el => el && el.getBoundingClientRect();
    const facts = r(document.querySelector('.museum-about .artist-facts'));
    const map = r(document.querySelector('.museum-hero #mini-map'));
    const rows = sel => [...document.querySelectorAll(sel + ' .artist-facts > div')]
      .map(d => [d.querySelector('span').textContent, d.querySelector('b')]);
    const about = rows('.museum-about'), here = rows('.museum-here');
    const artistRow = here.find(([k]) => /^Художник/.test(k));
    return {
      facts: facts && [Math.round(facts.top), Math.round(facts.right)],
      map: map && [Math.round(map.top), Math.round(map.left)],
      aside: !!document.querySelector('.post-aside'),
      captions: [...document.querySelectorAll('.museum-caption')].map(c => c.textContent),
      about: about.map(([k]) => k),
      here: here.map(([k]) => k),
      artistLinks: artistRow ? [...artistRow[1].querySelectorAll('a')].map(a => a.getAttribute('href')) : [],
      cardArtists: [...new Set([...document.querySelectorAll('.grid .card:not(.visit-card) .card-artist')]
        .map(e => e.textContent.trim()))].length,
      scope: (document.querySelector('.museum-here .museum-scope') || {}).textContent || '',
      bottomArtists: !!document.querySelector('.museum-artists'),
    };
  });
  ok('шапка: карта справа от сведений, вровень с ними',
    lay.facts && lay.map && Math.abs(lay.facts[0] - lay.map[0]) <= 2 && lay.map[1] > lay.facts[1], JSON.stringify(lay));
  ok('узкой колонки сбоку нет', !lay.aside);
  // Сведения двумя подписанными блоками, чтобы ни одна строка не читалась
  // двояко: сайт музея — отдельно от того, что есть на этом сайте.
  ok('блоки подписаны: «Адрес и сайт» / «На этом сайте» / «На карте»',
    lay.captions.includes('На этом сайте') && lay.captions.includes('На карте') &&
    lay.captions.some(c => /^(Адрес|Сайт|Где)/.test(c)), lay.captions.join(' | '));
  ok('сайт музея подписан «Официальный сайт» и стоит в блоке музея',
    !lay.about.includes('Сайт') && (!lay.about.some(k => /сайт/i.test(k)) || lay.about.includes('Официальный сайт')) &&
    !lay.here.some(k => /сайт/i.test(k)), lay.about.join(', ') + ' | ' + lay.here.join(', '));
  ok('город не повторяется отдельной строкой «Где», если есть адрес',
    !(lay.about.includes('Адрес') && lay.about.includes('Где')), lay.about.join(', '));
  ok('художники названы по именам и ведут на свои страницы',
    lay.artistLinks.length === lay.cardArtists && lay.artistLinks.every(h => /^artist-/.test(h) && exists(h)),
    `${lay.artistLinks.length} ссылок, в карточках ${lay.cardArtists} художников`);
  ok('понятно, какие это годы', lay.here.some(k => /^Годы? создания$/.test(k)) && !lay.here.includes('Годы'),
    lay.here.join(', '));
  ok('сказано, что это не всё собрание музея', /не всё собрание/.test(lay.scope), lay.scope);
  ok('отдельного списка художников внизу нет (он в шапке)', !lay.bottomArtists);
  await page.close();

  // место, где только походы
  const visitOnly = pages.find(n => !/class="card"/.test(read(n)) && /visit-card/.test(read(n)));
  if (visitOnly) {
    ({ page, errors } = await open(visitOnly, 'dark'));
    const v = await page.evaluate(() => ({
      visits: document.querySelectorAll('.visit-card').length,
      eyebrow: document.querySelector('.eyebrow').textContent,
      theme: document.documentElement.getAttribute('data-theme'),
      filter: (() => { const t = document.querySelector('#mini-map .leaflet-tile-pane'); return t ? getComputedStyle(t).filter : ''; })(),
    }));
    ok('место без картин: главное — походы', v.visits >= 1, v.visits + ' походов');
    ok('подпись «Место», а не «Собрание»', /Место/.test(v.eyebrow), v.eyebrow);
    ok('в тёмной теме подложка мини-карты затемнена', v.theme !== 'dark' || /invert/.test(v.filter), v.filter || v.theme);
    const sat = await page.evaluate(() => {
      const label = [...document.querySelectorAll('.leaflet-control-layers-base label')]
        .find(x => /Спутник/.test(x.textContent));
      if (!label) return null;
      label.querySelector('input').click();
      return document.querySelector('#mini-map').classList.contains('map-dark');
    });
    ok('на спутнике мини-карта не инвертируется', sat === false, String(sat));
    ok('ошибок в консоли нет (место без картин)', !errors.length, errors.join('; '));
    await page.close();
  }

  // телефон: ничего не вылезает за край
  const phone = await browser.newContext({ viewport: { width: 375, height: 800 }, isMobile: true, hasTouch: true });
  const pp = await phone.newPage();
  await pp.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', r => r.fulfill({ path: NM('leaflet/dist/leaflet.js') }));
  await pp.route('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css', r => r.fulfill({ path: NM('leaflet/dist/leaflet.css') }));
  await pp.route(/tile\.openstreetmap\.org|tiles\.api-maps\.yandex\.ru/, r => r.abort());
  await pp.goto(f(workPage));
  await pp.waitForTimeout(400);
  const over = await pp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok('375px без горизонтальной прокрутки', over <= 0, 'перелив ' + over + 'px');
  const ph = await pp.evaluate(() => {
    const top = s => { const el = document.querySelector(s); return el ? Math.round(el.getBoundingClientRect().top + scrollY) : null; };
    const m = document.querySelector('#mini-map').miniMap;
    const nav = [...document.querySelectorAll('.post-nav a')].map(a => a.getBoundingClientRect())
      .map(b => [Math.round(b.top), Math.round(b.left), Math.round(b.right)]);
    return { map: top('#mini-map'), card: top('.grid .card'), touch: L.Browser.mobile, drag: m && m.dragging.enabled(), nav };
  });
  ok('телефон: карта сразу за сведениями, до картин', ph.map !== null && ph.card !== null && ph.map < ph.card,
    `карта ${ph.map}, первая картина ${ph.card}`);
  ok('телефон: карту можно двигать пальцем', ph.touch && ph.drag, JSON.stringify({ touch: ph.touch, drag: ph.drag }));
  ok('телефон: «назад» слева, «вперёд» справа, в одну строку',
    ph.nav.length < 2 || (ph.nav[0][0] === ph.nav[1][0] && ph.nav[0][2] <= ph.nav[1][1]), JSON.stringify(ph.nav));
  await browser.close();

  console.log('\n====== СТРАНИЦЫ МУЗЕЕВ ======');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  const fails = results.filter(r => !r.pass);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
