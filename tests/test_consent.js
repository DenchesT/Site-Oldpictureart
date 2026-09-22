// Яндекс Метрика — только с согласия.
//
// Счётчик раньше стоял на каждой странице и начинал считать сразу, а о
// нём нигде не было ни слова. Теперь внизу плашка: пока посетитель не
// нажал «Принять», tag.js не загружается вовсе. Здесь проверяется
// именно это — по сетевым запросам, а не по виду плашки, — а ещё что
// отказ запоминается, что передумать можно на странице о данных и что
// после отказа cookie Метрики на сайте стираются.
//
// Cookie на file:// не живут, поэтому страницы отдаёт маленький сервер.
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const DOCS = path.join(__dirname, '..', 'docs');
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'application/javascript',
                '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp' };
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p.endsWith('/')) p += 'index.html';
  const file = path.join(DOCS, p);
  if (!file.startsWith(DOCS) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const BASE = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch(LAUNCH);

  // Сеть наружу в проверках закрыта; запросы к Метрике считаем и
  // отвечаем пустым скриптом, остальное внешнее просто обрываем.
  async function open(ctx, url) {
    const page = await ctx.newPage();
    const hits = [];
    const errs = [];
    page.on('pageerror', e => errs.push(e.message.slice(0, 140)));
    await page.route('**/*', r => {
      const u = r.request().url();
      if (u.startsWith(BASE)) return r.continue();
      if (u.includes('mc.yandex.ru')) { hits.push(u); return r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }); }
      return r.abort();
    });
    await page.goto(BASE + url);
    await page.waitForTimeout(400);
    return { page, hits, errs };
  }

  // ------------------------------------------------ первый заход
  const c1 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  let { page, hits, errs } = await open(c1, '/');
  ok('при первом заходе плашка видна', await page.locator('#consent').isVisible());
  ok('до ответа счётчик не загружается', hits.length === 0, hits.join(' '));
  ok('в плашке ссылка на подробности', await page.getAttribute('#consent a', 'href') === 'privacy.html#metrika');

  const styles = await page.$$eval('#consent .consent-btn', bs => bs.map(b => {
    const cs = getComputedStyle(b);
    return [cs.backgroundColor, cs.color, cs.borderColor, cs.fontSize].join(' ');
  }));
  ok('«Принять» и «Отклонить» выглядят одинаково', styles.length === 2 && styles[0] === styles[1], styles.join(' | '));

  const box = await page.locator('#consent').boundingBox();
  ok('плашка не заслоняет кнопку «наверх» справа', box.x + box.width < 1280 - 80,
     `${Math.round(box.x)}…${Math.round(box.x + box.width)}`);
  ok('плашка небольшая', box.height <= 80 && box.width <= 540,
     `${Math.round(box.width)}×${Math.round(box.height)}`);

  await page.click('#consent [data-consent="no"]');
  await page.waitForTimeout(200);
  ok('после отказа плашка исчезает', await page.locator('#consent').count() === 0);
  ok('после отказа счётчик так и не загрузился', hits.length === 0);
  ok('отказ записан', await page.evaluate(() => localStorage.getItem('consent-metrika')) === 'no');
  await page.goto(BASE + '/quiz.html');
  await page.waitForTimeout(300);
  ok('отказ помнится на других страницах', await page.locator('#consent').count() === 0 && hits.length === 0);
  ok('нет ошибок JS', errs.length === 0, errs.join(' | '));
  await c1.close();

  // ------------------------------------------------ согласие
  const c2 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  ({ page, hits } = await open(c2, '/stats.html'));
  await page.click('#consent [data-consent="yes"]');
  await page.waitForTimeout(300);
  ok('после «Принять» счётчик загружается сразу', hits.some(u => u.includes('/metrika/tag.js')), hits.join(' '));
  ok('номер счётчика верный', hits.some(u => u.includes('id=112760205')));
  hits.length = 0;
  await page.goto(BASE + '/ukazatel.html');
  await page.waitForTimeout(300);
  ok('на следующей странице — без вопросов и со счётчиком',
     await page.locator('#consent').count() === 0 && hits.some(u => u.includes('tag.js')));

  // ------------------------------------------------ передумал
  await page.evaluate(() => {
    document.cookie = '_ym_uid=123; path=/';
    document.cookie = '_ym_d=456; path=/';
    localStorage.setItem('_ym112760205_lsid', 'x');
  });
  await page.goto(BASE + '/privacy.html');
  await page.waitForTimeout(300);
  ok('на странице о данных плашки нет — там свои кнопки', await page.locator('#consent').count() === 0);
  ok('страница говорит, что статистика разрешена',
     /разрешена/.test(await page.textContent('#consent-state')), await page.textContent('#consent-state'));
  await Promise.all([
    page.waitForEvent('load'),
    page.click('#consent-controls [data-consent="no"]'),
  ]);
  await page.waitForTimeout(300);
  ok('после отказа — «отключена»', /отключена/.test(await page.textContent('#consent-state')));
  const left = await page.evaluate(() => ({
    cookies: document.cookie,
    ls: Object.keys(localStorage).filter(k => k.startsWith('_ym')),
  }));
  ok('cookie Метрики стёрты', !/_ym/.test(left.cookies), left.cookies || 'пусто');
  ok('записи Метрики в хранилище стёрты', left.ls.length === 0, left.ls.join(', '));
  hits.length = 0;
  await page.goto(BASE + '/');
  await page.waitForTimeout(300);
  ok('после отказа счётчик больше не грузится', hits.length === 0);
  await c2.close();

  // ------------------------------------------------ разметка
  const c3 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  ({ page } = await open(c3, '/'));
  ok('в подвале есть ссылка на страницу о данных',
     await page.locator('.site-footer a[href="privacy.html"]').count() === 1);
  ok('картинки-пикселя без согласия нет', await page.locator('noscript').evaluateAll(
     ns => !ns.some(n => /mc\.yandex/.test(n.innerHTML))));
  // Кнопка входа есть на страницах картин. Без Firebase она со страницы
  // убирается, поэтому смотрим исходник.
  const meta = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'posts_meta.json'), 'utf8'));
  ok('имя в кнопке входа скрыто от Вебвизора',
     /id="auth-btn" class="[^"]*ym-hide-content/.test(fs.readFileSync(path.join(DOCS, meta[0].filename), 'utf8')));
  await c3.close();

  // ------------------------------------------------ телефон
  const m = await browser.newContext({ viewport: { width: 375, height: 740 }, isMobile: true, hasTouch: true });
  ({ page } = await open(m, '/'));
  const mb = await page.locator('#consent').boundingBox();
  ok('на телефоне плашка внизу во всю ширину, с отступами',
     mb && mb.width >= 350 && mb.x >= 4 && Math.round(mb.y + mb.height) >= 725,
     mb ? `${Math.round(mb.width)}×${Math.round(mb.height)} @ x=${Math.round(mb.x)}, y=${Math.round(mb.y)}` : 'нет');
  ok('на телефоне плашка невысокая', mb && mb.height <= 100, mb && `${Math.round(mb.height)}px`);
  const tap = await page.$$eval('#consent .consent-btn', bs => bs.map(b => Math.round(b.getBoundingClientRect().height)));
  ok('кнопки на телефоне не мельче 32 px — попасть пальцем', tap.every(h => h >= 32), tap.join(', '));
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok('без горизонтальной прокрутки', over <= 1, `${over}px`);
  ({ page } = await open(m, '/privacy.html'));
  const overP = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok('страница о данных на телефоне без прокрутки вбок', overP <= 1, `${overP}px`);
  await m.close();

  await browser.close();
  server.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n====== СОГЛАСИЕ НА МЕТРИКУ ======');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
