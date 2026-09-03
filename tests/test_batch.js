const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const DOCS = require('path').join(__dirname, '..', 'docs');
const f = n => 'file://' + DOCS + '/' + encodeURIComponent(n).replace(/%2F/g, '/');
// Страница работы для проверок выбирается из базы, а не задана жёстко:
// конкретный пост могут удалить из канала, и проверки посыпались бы.
function pickPost() {
  const meta = JSON.parse(require('fs').readFileSync(
    require('path').join(__dirname, '..', 'posts_meta.json'), 'utf8'));
  const good = meta.filter(p => (p.hires || []).length && p.description && p.creation_year);
  return good.find(p => /Левитан/.test(p.artist)) || good[0] || meta[0];
}
const PICKED = pickPost();
const POST = PICKED.filename;

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};
const SURNAME = PICKED.artist.split(' ').pop();

// Копия карты с локальным Leaflet — в песочнице нет сети
const TMP = require('path').join(require('os').tmpdir(), 'museums-test');
fs.mkdirSync(TMP, { recursive: true });
let mh = fs.readFileSync(path.join(DOCS, 'museums.html'), 'utf8')
  .replace(/<link rel="stylesheet" href="https:\/\/unpkg\.com\/leaflet[^>]*>/, '<link rel="stylesheet" href="leaflet.css">')
  .replace(/<script src="https:\/\/unpkg\.com\/leaflet@[^>]*><\/script>/, '<script src="leaflet.js"></script>')
  .replace(/<link rel="stylesheet" href="https:\/\/unpkg\.com\/leaflet\.markercluster[^>]*>/, '<link rel="stylesheet" href="MarkerCluster.css">')
  .replace(/<script src="https:\/\/unpkg\.com\/leaflet\.markercluster[^>]*><\/script>/, '<script src="markercluster.js"></script>');
fs.writeFileSync(path.join(TMP, 'museums.html'), mh);
for (const [src, dst] of [
  [require.resolve('leaflet/dist/leaflet.js'), 'leaflet.js'],
  [require.resolve('leaflet/dist/leaflet.css'), 'leaflet.css'],
  [require.resolve('leaflet.markercluster/dist/leaflet.markercluster.js'), 'markercluster.js'],
  [require.resolve('leaflet.markercluster/dist/MarkerCluster.css'), 'MarkerCluster.css'],
  [path.join(DOCS, 'style.css'), 'style.css'],
  [path.join(DOCS, 'map-config.js'), 'map-config.js'],
]) fs.copyFileSync(src, path.join(TMP, dst));

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

(async () => {
  const browser = await chromium.launch(LAUNCH);

  // ============ 1. Материал вместо Основы, со строчной ============
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(f(POST));
    await page.waitForTimeout(600);
    const rows = await page.evaluate(() =>
      [...document.querySelectorAll('.spec-table div')].map(d => [
        d.querySelector('span').textContent.trim(), d.querySelector('b').textContent.trim()]));
    const mat = rows.find(r => r[0] === 'Материал');
    ok('поле называется «Материал»', !!mat, rows.map(r => r[0]).join(', '));
    ok('значение материала со строчной', mat && mat[1][0] === mat[1][0].toLowerCase(), mat && mat[1]);
    ok('«Основы» больше нет', !rows.some(r => r[0] === 'Основа'));

    await page.goto(f('index.html'));
    await page.waitForTimeout(600);
    const cardMat = await page.evaluate(() => {
      const d = [...document.querySelectorAll('.card-facts div')]
        .find(x => x.querySelector('span').textContent.trim() === 'Материал');
      return d ? d.querySelector('b').textContent.trim() : null;
    });
    ok('в описи тоже «Материал» со строчной', cardMat && cardMat[0] === cardMat[0].toLowerCase(), cardMat);
    await ctx.close();
  }

  // ============ 2. Таймлайн по возрастанию годов ============
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(f('timeline.html'));
    await page.waitForTimeout(700);
    const bad = await page.evaluate(() => {
      const wrong = [];
      Object.keys(timelineData).forEach(d => {
        const ys = timelineData[d].map(p => p.year);
        for (let i = 1; i < ys.length; i++) if (ys[i] < ys[i - 1]) wrong.push(d);
      });
      return [...new Set(wrong)];
    });
    ok('во всех десятилетиях годы по возрастанию', bad.length === 0, bad.join(', '));
    const shown = await page.evaluate(() =>
      [...document.querySelectorAll('.timeline-card-year')].map(e => +e.textContent));
    const sorted = [...shown].sort((a, b) => a - b);
    ok('на экране карточки тоже по возрастанию', JSON.stringify(shown) === JSON.stringify(sorted), shown.join(' '));
    await ctx.close();
  }

  // ============ 3. Кнопка «наверх» ============
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(f('index.html'));
    await page.waitForTimeout(600);
    ok('в начале страницы кнопка скрыта', !(await page.locator('.scroll-top').isVisible()));
    await page.evaluate(() => window.scrollTo(0, 2000));
    await page.waitForTimeout(500);
    ok('после прокрутки кнопка появляется', await page.locator('.scroll-top').isVisible());
    const p1 = await page.locator('.scroll-top').evaluate(el => el.style.getPropertyValue('--progress'));
    // ленивые картинки догружаются на ходу и страница растёт, поэтому
    // доезжаем до низа дважды и меряем, когда высота устоялась
    for (let i = 0; i < 3; i++) {
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await page.waitForTimeout(700);
    }
    const p2 = await page.locator('.scroll-top').evaluate(el => el.style.getPropertyValue('--progress'));
    ok('кольцо показывает прогресс', +p2 > +p1 && +p2 >= 99, `${p1}% → ${p2}%`);
    const box = await page.locator('.scroll-top').boundingBox();
    ok('кнопка компактная', box.width <= 44, Math.round(box.width) + 'px');
    await ctx.close();
  }
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 800 }, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    await page.goto(f('index.html'));
    await page.waitForTimeout(600);
    await page.evaluate(() => window.scrollTo(0, 3000));
    await page.waitForTimeout(500);
    ok('на телефоне кнопки «наверх» нет', !(await page.locator('.scroll-top').isVisible()));
    await ctx.close();
  }

  // ============ 4. Фильтр по годам и порядок записей ============
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(f('index.html'));
    await page.waitForTimeout(700);
    const total = await page.locator('.card').count();

    ok('гистограмма построена', await page.locator('.hbar').count() > 3, await page.locator('.hbar').count() + ' столбиков');
    ok('подпись про все годы', (await page.locator('#year-caption').textContent()).includes('Все годы'));

    // клик по самому высокому столбику
    const idx = await page.evaluate(() => {
      const bars = [...document.querySelectorAll('.hbar')];
      let best = 0, bestH = -1;
      bars.forEach((b, i) => { const hh = parseFloat(b.style.getPropertyValue('--h')); if (hh > bestH) { bestH = hh; best = i; } });
      return best;
    });
    await page.locator('.hbar').nth(idx).click();
    await page.waitForTimeout(400);
    let vis = await page.locator('.card:not([hidden])').count();
    ok('клик по столбику фильтрует', vis > 0 && vis < total, `${vis} из ${total}`);
    const cap = (await page.locator('#year-caption').textContent()).trim();
    ok('подпись показывает выбранный диапазон', /^\d{4}—\d{4}$/.test(cap), cap);
    ok('невыбранные столбики приглушены', await page.locator('.hbar.dim').count() > 0);
    const inRange = await page.evaluate(() => {
      const from = +document.getElementById('year-from').value, to = +document.getElementById('year-to').value;
      return [...document.querySelectorAll('.card:not([hidden])')]
        .every(c => { const y = +c.dataset.cyear; return y >= from && y <= to; });
    });
    ok('показаны только работы из диапазона', inRange);

    // повторный клик снимает
    await page.locator('.hbar').nth(idx).click();
    await page.waitForTimeout(400);
    ok('повторный клик снимает фильтр', (await page.locator('.card:not([hidden])').count()) === total);

    // диапазон селектами
    await page.selectOption('#year-from', { index: 1 });
    await page.waitForTimeout(300);
    await page.selectOption('#year-to', { index: 3 });
    await page.waitForTimeout(400);
    vis = await page.locator('.card:not([hidden])').count();
    ok('диапазон селектами работает', vis > 0 && vis < total, `${vis} из ${total}`);

    await page.click('#reset-filter');
    await page.waitForTimeout(400);
    ok('сброс возвращает все годы', (await page.locator('.card:not([hidden])').count()) === total &&
      (await page.locator('#year-caption').textContent()).includes('Все годы'));

    // порядок записей
    const firstOf = () => page.locator('.card .card-artist').first().textContent();
    const a0 = (await firstOf()).trim();
    await page.selectOption('#sort', 'cyear');
    await page.waitForTimeout(400);
    const years = await page.evaluate(() => [...document.querySelectorAll('.card')].map(c => +c.dataset.cyear || 0));
    ok('по году создания — по возрастанию', years.every((v, i, a) => i === 0 || a[i - 1] <= v), years.slice(0, 6).join(' '));
    await page.selectOption('#sort', 'artist');
    await page.waitForTimeout(400);
    const names = await page.evaluate(() => [...document.querySelectorAll('.card')].map(c => c.dataset.artist));
    ok('по художнику — по алфавиту', names.every((v, i, a) => i === 0 || a[i - 1].localeCompare(v, 'ru') <= 0), names.slice(0, 3).join(' | '));
    await page.selectOption('#sort', 'title');
    await page.waitForTimeout(400);
    const titles = await page.evaluate(() => [...document.querySelectorAll('.card')].map(c => c.dataset.title));
    ok('по названию — по алфавиту', titles.every((v, i, a) => i === 0 || a[i - 1].localeCompare(v, 'ru') <= 0), titles.slice(0, 2).join(' | '));
    await page.selectOption('#sort', 'new');
    await page.waitForTimeout(400);
    ok('«сначала новые» возвращает исходный порядок', (await firstOf()).trim() === a0, a0);

    // фильтр по годам + поиск вместе
    await page.fill('#search', 'холст');
    await page.waitForTimeout(400);
    await page.locator('.hbar').nth(idx).click();
    await page.waitForTimeout(400);
    const both = await page.locator('.card:not([hidden])').count();
    ok('поиск и годы работают вместе', both >= 0 && both < total, `${both} из ${total}`);
    await ctx.close();
  }

  // ============ 5. Кликабельные музеи ============
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(f('index.html'));
    await page.waitForTimeout(700);

    ok('карточка — это <article>', (await page.locator('.card').first().evaluate(el => el.tagName)) === 'ARTICLE');
    ok('вложенных ссылок в ссылку нет', (await page.locator('a a').count()) === 0);

    const href = await page.locator('.card-museum a').first().getAttribute('href');
    ok('музей ведёт на карту с якорем', /^museums\.html#museum-/.test(href || ''), href);

    // карточка всё ещё открывает картину
    const cardHref = await page.locator('.card .card-link').first().getAttribute('href');
    await page.locator('.card').first().click({ position: { x: 400, y: 20 } });
    await page.waitForTimeout(700);
    ok('клик по карточке открывает картину', decodeURIComponent(page.url()).includes(decodeURIComponent(cardHref)),
      page.url().split('/').pop().slice(0, 40));

    // на странице картины собрание — ссылка
    const collHref = await page.evaluate(() => {
      const d = [...document.querySelectorAll('.spec-table div')]
        .find(x => x.querySelector('span').textContent.trim() === 'Собрание');
      const a = d && d.querySelector('a');
      return a ? a.getAttribute('href') : null;
    });
    ok('«Собрание» на странице картины — ссылка', /^museums\.html#museum-/.test(collHref || ''), collHref);
    await ctx.close();
  }
  {
    // карта: приход по якорю подсвечивает музей
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push(e.message.slice(0, 120)));
    const anchor = await page.evaluate(() => null);
    await page.goto('file://' + TMP + '/museums.html#museum-государственная-третьяковская-галерея-москва');
    await page.waitForTimeout(1800);
    ok('музей из якоря подсвечен', (await page.locator('.museum-card.active').count()) === 1);
    ok('ссылки на сайты музеев есть', await page.locator('.museum-site a').count() > 20,
      (await page.locator('.museum-site a').count()) + ' шт.');
    const site = await page.locator('.museum-site a').first().getAttribute('href');
    ok('ссылка на сайт внешняя и по https', /^https:\/\//.test(site || ''), site);
    ok('нет ошибок на карте', errs.length === 0, errs.join('|'));
    await ctx.close();
  }

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ ПРАВКИ ПО СПИСКУ ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
