// Карта не должна превращаться в серое поле ни при сохранённом «Яндексе»,
// ни если библиотека группировки не загрузилась.
//
// Подложка по умолчанию — Яндекс, на карте собраний и на мини-картах
// страниц музеев; выбор посетителя общий для всех карт сайта. Если Яндекс
// не отдаёт тайлы, карта сама встаёт на Схему и этот выбор не запоминает.
const { chromium } = require('playwright');
const fs = require('fs');
const DOCS = require('path').join(__dirname, '..', 'docs');
const { serve } = require('./_static');
// Тайл-заглушка 1×1: Leaflet считает его загруженным.
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
const MUSEUM_PAGE = fs.readdirSync(DOCS).find(n => /^museum-.*\.html$/.test(n) && /id="mini-map"/.test(fs.readFileSync(DOCS + '/' + n, 'utf8')));
const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

let SITE;
async function state(browser, { blockCluster, savedLayer, noKey, yaOk, legacy, switchTo, page = 'museums.html' }) {
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 800 } });
  // Библиотеки лежат в docs/vendor; «не загрузилась» — значит, запрос обрываем.
  if (blockCluster) await ctx.route('**/vendor/leaflet.markercluster/*.js', r => r.abort());
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
  // Логотип Яндекса: есть ли он, в каком углу и куда ведёт.
  await p.addInitScript(() => {
    window.logoState = () => {
      const all = document.querySelectorAll('.opa-ya-logo');
      const a = all[0];
      if (!a) return null;
      return { count: all.length, corner: !!a.closest('.leaflet-bottom.leaflet-left'), href: a.href,
               target: a.target, text: a.textContent.trim(), img: !!a.querySelector('img') };
    };
  });
  await p.goto(SITE.url + '/' + page);
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
      logo: logoState(),
      base, stored,
    };
  });
  // Переключить подложку руками и посмотреть на логотип после этого.
  for (const name of (switchTo || [])) {
    await p.evaluate(n => {
      const label = [...document.querySelectorAll('.leaflet-control-layers-base label')]
        .find(l => l.textContent.trim() === n);
      if (label) label.querySelector('input').click();
    }, name);
    await p.waitForTimeout(150);
    (st.after = st.after || []).push(await p.evaluate(() => logoState()));
  }
  st.errs = errs;
  st.warns = warns;
  await ctx.close();
  return st;
}

(async () => {
  SITE = await serve(DOCS);
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

  // ---- логотип Яндекса (условие Tiles API)
  const lg = def.logo || {};
  ok('логотип Яндекса на карте, пока выбран Яндекс', def.logo && lg.count === 1, JSON.stringify(def.logo));
  ok('…в левом нижнем углу', lg.corner);
  ok('…ссылкой на Яндекс Карты в новой вкладке', /^https:\/\/yandex\.ru\/maps\/?$/.test(lg.href || '') && lg.target === '_blank', lg.href);
  ok('…картинкой, если файл логотипа положен, иначе надписью «Яндекс Карты»',
     lg.img || lg.text === 'Яндекс Карты', JSON.stringify(lg));
  ok('Схема по умолчанию (Яндекс не ответил) — логотипа нет', down.logo === null, JSON.stringify(down.logo));
  ok('без ключа — логотипа нет', noKey.logo === null, JSON.stringify(noKey.logo));
  const sw = await state(b, { yaOk: true, switchTo: ['Схема', 'Яндекс', 'Спутник'] });
  ok('переключили на Схему — логотип ушёл', sw.after && sw.after[0] === null, JSON.stringify(sw.after));
  ok('вернули Яндекс — логотип снова на месте, один', sw.after && sw.after[1] && sw.after[1].count === 1, JSON.stringify(sw.after));
  ok('Спутник — логотипа нет', sw.after && sw.after[2] === null, JSON.stringify(sw.after));

  if (MUSEUM_PAGE) {
    const mini = await state(b, { yaOk: true, page: MUSEUM_PAGE });
    ok('страница музея: по умолчанию тоже Яндекс', mini.base === 'yandex', mini.base);
    ok('страница музея: тот же переключатель подложек', mini.radios === 4, `${mini.radios} подложек`);
    ok('страница музея: без ошибок', mini.errs.length === 0, mini.errs.join(' ; '));
    ok('страница музея: логотип Яндекса в углу мини-карты', mini.logo && mini.logo.corner, JSON.stringify(mini.logo));
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
  await SITE.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ УСТОЙЧИВОСТЬ КАРТЫ ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
