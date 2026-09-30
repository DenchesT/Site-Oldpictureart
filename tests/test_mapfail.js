// Карта не должна превращаться в серое поле ни при сохранённом «Яндексе»,
// ни если библиотека группировки не доехала с CDN.
//
// Подложка по умолчанию — Яндекс, на карте собраний и на мини-картах
// страниц музеев; выбор посетителя общий для всех карт сайта. Если Яндекс
// не отдаёт тайлы, карта сама встаёт на Схему и этот выбор не запоминает.
const { chromium } = require('playwright');
const fs = require('fs');
const DOCS = require('path').join(__dirname, '..', 'docs');
const LIB = {
  'leaflet.js':  fs.readFileSync(require.resolve('leaflet/dist/leaflet.js'), 'utf8'),
  'leaflet.css': fs.readFileSync(require.resolve('leaflet/dist/leaflet.css'), 'utf8'),
  'mc.js':       fs.readFileSync(require.resolve('leaflet.markercluster/dist/leaflet.markercluster.js'), 'utf8'),
  'mc.css':      fs.readFileSync(require.resolve('leaflet.markercluster/dist/MarkerCluster.css'), 'utf8'),
};
// Тайл-заглушка 1×1: Leaflet считает его загруженным.
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
const MUSEUM_PAGE = fs.readdirSync(DOCS).find(n => /^museum-.*\.html$/.test(n) && /id="mini-map"/.test(fs.readFileSync(DOCS + '/' + n, 'utf8')));
const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

async function state(browser, { blockCluster, savedLayer, noKey, yaOk, legacy, page = 'museums.html' }) {
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
  await ctx.route('**/tiles.api-maps.yandex.ru/**', r => yaOk
    ? r.fulfill({ status: 200, contentType: 'image/png', body: PNG }) : r.abort());
  const p = await ctx.newPage();
  const errs = [], warns = [];
  p.on('pageerror', e => errs.push(e.message.slice(0, 110)));
  p.on('console', m => { if (m.type() === 'warning') warns.push(m.text()); });
  await p.addInitScript(([v, nk, old]) => {
    try { if (v) localStorage.setItem('mapBase', v); } catch (e) {}
    try { if (old) localStorage.setItem('mapLayer', old); } catch (e) {}
    // map-config.js присваивает window.MAP_KEYS — присваивание глотаем,
    // иначе ключ из файла вернулся бы на место.
    if (nk) Object.defineProperty(window, 'MAP_KEYS', { get: () => ({ yandex: '' }), set: () => {}, configurable: true });
  }, [savedLayer, noKey, legacy]);
  await p.goto('file://' + DOCS + '/' + page);
  await p.waitForTimeout(1800);
  const st = await p.evaluate(() => {
    const m = window.map && window.map.eachLayer ? window.map : (document.querySelector('#mini-map') || {}).miniMap;
    let base = null;
    if (m) m.eachLayer(l => { if (l._opaId) base = l._opaId; });
    let stored = null;
    try { stored = localStorage.getItem('mapBase'); } catch (e) {}
    return {
      tiles: document.querySelectorAll('.leaflet-tile-pane .leaflet-layer').length,
      markers: document.querySelectorAll('.leaflet-marker-icon').length,
      mapped: document.querySelectorAll('.museum-card[data-mapped="1"]').length,
      radios: document.querySelectorAll('.leaflet-control-layers-base input').length,
      base, stored,
    };
  });
  st.errs = errs;
  st.warns = warns;
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

  // ---- подложка по умолчанию и выбор
  const def = await state(b, { yaOk: true });
  ok('карта собраний: по умолчанию Яндекс', def.base === 'yandex', def.base);
  ok('карта собраний: переключатель — Яндекс, Схема, Минимальная, Спутник', def.radios === 4, `${def.radios} подложек`);
  const topo = await state(b, { yaOk: true, savedLayer: 'topo' });
  ok('сохранённый «Рельеф» (его больше нет) — снова Яндекс', topo.base === 'yandex', topo.base);
  const old = await state(b, { yaOk: true, legacy: 'osm' });
  ok('прежний сохранённый выбор («mapLayer») Яндекс не перебивает', old.base === 'yandex', old.base);
  const down = await state(b, {});
  ok('Яндекс не отвечает — карта сама встаёт на Схему', down.base === 'osm' && down.tiles === 1, `${down.base}, слоёв ${down.tiles}`);
  ok('…и этот вынужденный выбор не запоминается', down.stored === null, String(down.stored));
  ok('…а в консоли — подсказка, что проверить', down.warns.some(w => /Яндекс/.test(w) && /ключ/.test(w)), down.warns.join(' | '));
  const noKey = await state(b, { yaOk: true, noKey: true });
  ok('без ключа — Схема, Яндекса в списке нет', noKey.base === 'osm' && noKey.radios === 3, `${noKey.base}, ${noKey.radios} подложек`);

  if (MUSEUM_PAGE) {
    const mini = await state(b, { yaOk: true, page: MUSEUM_PAGE });
    ok('страница музея: по умолчанию тоже Яндекс', mini.base === 'yandex', mini.base);
    ok('страница музея: тот же переключатель подложек', mini.radios === 4, `${mini.radios} подложек`);
    ok('страница музея: без ошибок', mini.errs.length === 0, mini.errs.join(' ; '));
    const shared = await state(b, { yaOk: true, savedLayer: 'gray', page: MUSEUM_PAGE });
    ok('выбор подложки общий для всех карт сайта', shared.base === 'gray', shared.base);
    const miniDown = await state(b, { page: MUSEUM_PAGE });
    ok('страница музея: Яндекс не отвечает — Схема', miniDown.base === 'osm' && miniDown.stored === null,
       `${miniDown.base}, запомнено ${miniDown.stored}`);
  }

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
