// Карта не должна превращаться в серое поле ни при сохранённом «Яндексе»,
// ни если библиотека группировки не доехала с CDN.
const { chromium } = require('playwright');
const fs = require('fs');
const DOCS = require('path').join(__dirname, '..', 'docs');
const LIB = {
  'leaflet.js':  fs.readFileSync(require.resolve('leaflet/dist/leaflet.js'), 'utf8'),
  'leaflet.css': fs.readFileSync(require.resolve('leaflet/dist/leaflet.css'), 'utf8'),
  'mc.js':       fs.readFileSync(require.resolve('leaflet.markercluster/dist/leaflet.markercluster.js'), 'utf8'),
  'mc.css':      fs.readFileSync(require.resolve('leaflet.markercluster/dist/MarkerCluster.css'), 'utf8'),
};
const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

async function state(browser, { blockCluster, savedLayer, noKey }) {
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 800 } });
  await ctx.route('**/unpkg.com/**', route => {
    const u = route.request().url();
    if (u.includes('markercluster') && u.endsWith('.js'))
      return blockCluster ? route.abort() : route.fulfill({ status: 200, contentType: 'application/javascript', body: LIB['mc.js'] });
    if (u.endsWith('MarkerCluster.css')) return route.fulfill({ status: 200, contentType: 'text/css', body: LIB['mc.css'] });
    if (u.endsWith('leaflet.js'))  return route.fulfill({ status: 200, contentType: 'application/javascript', body: LIB['leaflet.js'] });
    if (u.endsWith('leaflet.css')) return route.fulfill({ status: 200, contentType: 'text/css', body: LIB['leaflet.css'] });
    return route.abort();
  });
  await ctx.route('**/*.png', r => r.abort());
  await ctx.route('**/tiles.api-maps.yandex.ru/**', r => r.abort());
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message.slice(0, 110)));
  await p.addInitScript(([v, nk]) => {
    try { if (v) localStorage.setItem('mapLayer', v); } catch (e) {}
    if (nk) Object.defineProperty(window, 'MAP_KEYS', { value: { yandex: '' }, writable: true });
  }, [savedLayer, noKey]);
  await p.goto('file://' + DOCS + '/museums.html');
  await p.waitForTimeout(1800);
  const st = await p.evaluate(() => ({
    tiles: document.querySelectorAll('.leaflet-tile-pane .leaflet-layer').length,
    markers: document.querySelectorAll('.leaflet-marker-icon').length,
    mapped: document.querySelectorAll('.museum-card[data-mapped="1"]').length,
  }));
  st.errs = errs;
  await ctx.close();
  return st;
}

(async () => {
  const b = await chromium.launch(LAUNCH);

  const base = await state(b, {});
  ok('обычная загрузка: подложка есть', base.tiles === 1, `слоёв ${base.tiles}`);
  ok('обычная загрузка: метки сгруппированы', base.markers > 0 && base.markers < base.mapped, `${base.markers} значков`);
  ok('обычная загрузка: без ошибок', base.errs.length === 0, base.errs.join(' ; '));

  const ya = await state(b, { savedLayer: 'yandex' });
  ok('сохранён «Яндекс»: подложка есть', ya.tiles === 1, `слоёв ${ya.tiles}`);
  ok('сохранён «Яндекс»: метки на месте', ya.markers > 0, `${ya.markers} значков`);
  ok('сохранён «Яндекс»: без ошибок', ya.errs.length === 0, ya.errs.join(' ; '));

  const noMc = await state(b, { blockCluster: true });
  ok('без библиотеки группировки: подложка есть', noMc.tiles === 1, `слоёв ${noMc.tiles}`);
  ok('без библиотеки группировки: метки всё равно показаны', noMc.markers === noMc.mapped, `${noMc.markers} из ${noMc.mapped}`);

  const worst = await state(b, { blockCluster: true, savedLayer: 'yandex', noKey: true });
  ok('худший случай: карта не пустая', worst.tiles === 1 && worst.markers > 0,
     `слоёв ${worst.tiles}, меток ${worst.markers}`);

  await b.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ УСТОЙЧИВОСТЬ КАРТЫ ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
