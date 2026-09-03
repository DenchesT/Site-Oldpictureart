const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const DOCS = require('path').join(__dirname, '..', 'docs');
const TMP = require('path').join(require('os').tmpdir(), 'museums-addr');

// В песочнице нет сети, поэтому подменяем Leaflet с CDN на локальную копию:
// иначе карта не построится и метки нечем будет считать.

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};
fs.mkdirSync(TMP, { recursive: true });
fs.writeFileSync(path.join(TMP, 'museums.html'), fs.readFileSync(path.join(DOCS, 'museums.html'), 'utf8')
  .replace(/<link rel="stylesheet" href="https:\/\/unpkg\.com\/leaflet[^>]*>/, '<link rel="stylesheet" href="leaflet.css">')
  .replace(/<script src="https:\/\/unpkg\.com\/leaflet@[^>]*><\/script>/, '<script src="leaflet.js"></script>')
  .replace(/<link rel="stylesheet" href="https:\/\/unpkg\.com\/leaflet\.markercluster[^>]*>/, '<link rel="stylesheet" href="MarkerCluster.css">')
  .replace(/<script src="https:\/\/unpkg\.com\/leaflet\.markercluster[^>]*><\/script>/, '<script src="markercluster.js"></script>'));
fs.copyFileSync(require.resolve('leaflet/dist/leaflet.js'), path.join(TMP, 'leaflet.js'));
fs.copyFileSync(require.resolve('leaflet/dist/leaflet.css'), path.join(TMP, 'leaflet.css'));
fs.copyFileSync(require.resolve('leaflet.markercluster/dist/leaflet.markercluster.js'), path.join(TMP, 'markercluster.js'));
fs.copyFileSync(require.resolve('leaflet.markercluster/dist/MarkerCluster.css'), path.join(TMP, 'MarkerCluster.css'));
fs.copyFileSync(path.join(DOCS, 'style.css'), path.join(TMP, 'style.css'));
fs.copyFileSync(path.join(DOCS, 'map-config.js'), path.join(TMP, 'map-config.js'));

const f = () => 'file://' + TMP + '/museums.html';

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

(async () => {
  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(f());
  await page.waitForTimeout(1200);

  const info = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.museum-card')];
    const withAddr = cards.filter(c => c.querySelector('.museum-address'));
    return {
      cards: cards.length,
      withAddr: withAddr.length,
      empty: withAddr.filter(c => !c.querySelector('.museum-address').textContent.trim()).length,
      sample: withAddr[0] && withAddr[0].querySelector('.museum-address').textContent.trim(),
      // адрес должен стоять после строки с городом и до ссылки на сайт
      orderOk: withAddr.every(c => {
        const kids = [...c.children].map(x => x.className);
        const loc = kids.findIndex(k => /museum-location/.test(k));
        const adr = kids.findIndex(k => /museum-address/.test(k));
        const site = kids.findIndex(k => /museum-site/.test(k));
        return adr > loc && (site === -1 || site > adr);
      }),
      visible: withAddr[0] && withAddr[0].querySelector('.museum-address').getBoundingClientRect().height > 0,
      // адрес не должен сливаться с названием города по цвету
      muted: withAddr[0] && getComputedStyle(withAddr[0].querySelector('.museum-address')).color,
    };
  });

  ok('адреса отрисованы', info.withAddr === 45, `${info.withAddr} из ${info.cards} карточек`);
  ok('пустых абзацев с адресом нет', info.empty === 0, `${info.empty}`);
  ok('адрес идёт после города и до ссылки', info.orderOk);
  ok('адрес виден на странице', info.visible, info.sample);

  // поиск по улице
  await page.fill('#museum-search', 'getty center dr');
  await page.waitForTimeout(400);
  const found = await page.evaluate(() => {
    const vis = [...document.querySelectorAll('.museum-card')].filter(c => !c.hidden);
    return { n: vis.length, name: vis[0] && vis[0].querySelector('h3').textContent.trim() };
  });
  ok('поиск по улице находит музей', found.n === 1 && /Гетти/.test(found.name), `${found.n}: ${found.name}`);

  await page.fill('#museum-search', 'Волхонка');
  await page.waitForTimeout(400);
  const volh = await page.evaluate(() => [...document.querySelectorAll('.museum-card')].filter(c => !c.hidden).length);
  ok('поиск по русской улице находит оба музея на Волхонке', volh === 2, String(volh));

  await page.fill('#museum-search', '');
  await page.waitForTimeout(300);

  // метки на карте не потерялись
  const mapped = await page.evaluate(() => document.querySelectorAll('.museum-card[data-mapped="1"]').length);
  const markers = await page.evaluate(() => document.querySelectorAll('.leaflet-marker-icon').length);
  ok('метки на карте на месте', markers > 0 && markers <= mapped, `${markers} значков при ${mapped} музеях с координатами`);
  ok('нет ошибок JS', errors.length === 0, errors.join(' | '));

  // мобильная ширина: адрес не ломает карточку
  const m = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
  const mp = await m.newPage();
  await mp.goto(f());
  await mp.waitForTimeout(900);
  const over = await mp.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok('375px без горизонтальной прокрутки', over <= 1, `перелив ${over}px`);
  await m.close();

  await ctx.close();
  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ АДРЕСА МУЗЕЕВ ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
