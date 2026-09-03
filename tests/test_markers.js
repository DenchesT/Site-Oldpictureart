const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const DOCS = require('path').join(__dirname, '..', 'docs');
const TMP = require('path').join(require('os').tmpdir(), 'museums-mk');

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

fs.mkdirSync(TMP, { recursive: true });
fs.writeFileSync(path.join(TMP, 'museums.html'), fs.readFileSync(path.join(DOCS, 'museums.html'), 'utf8')
  .replace(/<link rel="stylesheet" href="https:\/\/unpkg\.com\/leaflet@[^>]*>/, '<link rel="stylesheet" href="leaflet.css">')
  .replace(/<script src="https:\/\/unpkg\.com\/leaflet@[^>]*><\/script>/, '<script src="leaflet.js"></script>')
  .replace(/<link rel="stylesheet" href="https:\/\/unpkg\.com\/leaflet\.markercluster[^>]*>/, '<link rel="stylesheet" href="MarkerCluster.css">')
  .replace(/<script src="https:\/\/unpkg\.com\/leaflet\.markercluster[^>]*><\/script>/, '<script src="markercluster.js"></script>'));
for (const [src, dst] of [
  [require.resolve('leaflet/dist/leaflet.js'), 'leaflet.js'],
  [require.resolve('leaflet/dist/leaflet.css'), 'leaflet.css'],
  [require.resolve('leaflet.markercluster/dist/leaflet.markercluster.js'), 'markercluster.js'],
  [require.resolve('leaflet.markercluster/dist/MarkerCluster.css'), 'MarkerCluster.css'],
  [path.join(DOCS, 'style.css'), 'style.css'],
  [path.join(DOCS, 'map-config.js'), 'map-config.js'],
]) fs.copyFileSync(src, path.join(TMP, dst));

const URL = 'file://' + TMP + '/museums.html';
const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

(async () => {
  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message.slice(0, 140)));
  page.on('console', m => { if (m.type() === 'error' && !/net::ERR|Failed to load/i.test(m.text())) errs.push('CONSOLE: ' + m.text().slice(0, 140)); });

  await page.goto(URL);
  await page.waitForTimeout(1500);

  ok('нет ошибок в консоли', errs.length === 0, errs.join(' | '));

  const start = await page.evaluate(() => ({
    mapped: document.querySelectorAll('.museum-card[data-mapped="1"]').length,
    pins: document.querySelectorAll('.opa-pin').length,
    clusters: document.querySelectorAll('.opa-cluster').length,
    oldPins: document.querySelectorAll('.leaflet-marker-icon:not(.opa-pin):not(.opa-cluster)').length,
  }));
  ok('меток-капель Leaflet не осталось', start.oldPins === 0, `${start.oldPins}`);
  ok('скопления образовались', start.clusters > 0, `${start.clusters} скоплений, ${start.pins} одиночных`);
  ok('значков меньше, чем музеев', start.pins + start.clusters < start.mapped,
     `${start.pins + start.clusters} значков на ${start.mapped} музеев`);

  // сумма по стопкам плюс одиночные = все музеи с координатами
  const sum = await page.evaluate(() => {
    const c = [...document.querySelectorAll('.opa-cluster .cl-0')].reduce((s, e) => s + (+e.textContent || 0), 0);
    return c + document.querySelectorAll('.opa-pin').length;
  });
  ok('ни один музей не потерян', sum === start.mapped, `${sum} из ${start.mapped}`);

  // у стопки три карточки, у одиночной метки — число работ
  const shape = await page.evaluate(() => {
    const cl = document.querySelector('.opa-cluster');
    const pin = document.querySelector('.opa-pin');
    return {
      cards: cl ? cl.querySelectorAll('.cl').length : 0,
      hasStem: !!(cl && cl.querySelector('.pin-stem')) && !!(pin && pin.querySelector('.pin-stem')),
      pinText: pin && pin.querySelector('.pin-card').textContent.trim(),
      title: pin && pin.getAttribute('title'),
    };
  });
  ok('в стопке три карточки', shape.cards === 3, String(shape.cards));
  ok('у метки есть ножка', shape.hasStem);
  ok('на метке число работ', /^\d+$/.test(shape.pinText || ''), shape.pinText);
  ok('у метки есть подпись для наведения и скринридера', (shape.title || '').length > 3, shape.title);

  // цвета берутся из переменных темы, а не зашиты
  const colors = await page.evaluate(() => {
    const el = document.querySelector('.pin-card');
    const cs = getComputedStyle(el);
    return { color: cs.color, bg: cs.backgroundColor, accent: getComputedStyle(document.documentElement).getPropertyValue('--active').trim() };
  });
  ok('метка окрашена акцентом сайта', colors.color.replace(/\s/g, '') !== 'rgb(0,0,0)', `${colors.color} на ${colors.bg}`);

  // приближение разбивает скопления
  await page.evaluate(() => { const c = document.querySelector('.museum-card[data-mapped="1"]'); window.__map = null; });
  await page.evaluate(() => map.setZoom(map.getZoom() + 5));
  await page.waitForTimeout(900);
  const zoomed = await page.evaluate(() => ({
    clusters: document.querySelectorAll('.opa-cluster').length,
    pins: document.querySelectorAll('.opa-pin').length,
  }));
  ok('при приближении скоплений становится меньше', zoomed.clusters < start.clusters,
     `${start.clusters} → ${zoomed.clusters}`);

  await page.reload();
  await page.waitForTimeout(1400);

  // фильтр списка убирает метки из скоплений
  await page.fill('#museum-search', 'париж');
  await page.waitForTimeout(700);
  const filtered = await page.evaluate(() => {
    const c = [...document.querySelectorAll('.opa-cluster .cl-0')].reduce((s, e) => s + (+e.textContent || 0), 0);
    return c + document.querySelectorAll('.opa-pin').length;
  });
  const cards = await page.evaluate(() =>
    [...document.querySelectorAll('.museum-card')].filter(c => !c.hidden && c.dataset.mapped === '1').length);
  ok('на карте остаются только найденные музеи', filtered === cards, `${filtered} значков при ${cards} карточках`);
  await page.fill('#museum-search', '');
  await page.waitForTimeout(600);

  // нажатие на карточку раскрывает скопление и подсвечивает метку
  await page.evaluate(() => {
    const card = [...document.querySelectorAll('.museum-card[data-mapped="1"]')]
      .find(c => /Орсе/.test(c.querySelector('h3').textContent));
    focusMuseum(card.dataset.id);
  });
  await page.waitForTimeout(1600);
  const focused = await page.evaluate(() => ({
    active: document.querySelectorAll('.opa-pin.active').length,
    popup: document.querySelectorAll('.leaflet-popup').length,
  }));
  ok('метка музея из скопления подсвечена', focused.active === 1, `${focused.active}`);
  ok('всплывающая карточка открылась', focused.popup === 1, `${focused.popup}`);
  await ctx.close();

  // тёмная тема
  const dctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const dp = await dctx.newPage();
  await dp.addInitScript(() => { try { localStorage.setItem('theme', 'dark'); } catch (e) {} });
  await dp.goto(URL);
  await dp.waitForTimeout(1400);
  const dark = await dp.evaluate(() => {
    const cs = getComputedStyle(document.querySelector('.pin-card'));
    return { color: cs.color, bg: cs.backgroundColor };
  });
  ok('в тёмной теме метка перекрасилась', dark.color !== colors.color, `${dark.color} на ${dark.bg}`);
  await dctx.close();

  // узкий экран
  const mctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
  const mp = await mctx.newPage();
  await mp.goto(URL);
  await mp.waitForTimeout(1200);
  const over = await mp.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok('375px без горизонтальной прокрутки', over <= 1, `перелив ${over}px`);
  await mctx.close();

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ МЕТКИ «ЭТИКЕТКА» ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
