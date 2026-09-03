const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const DOCS = require('path').join(__dirname, '..', 'docs');
const TMP = require('path').join(require('os').tmpdir(), 'museums-test');

// Готовим копию страницы с локальным Leaflet: в песочнице нет сети,
// с CDN он бы не загрузился и проверить карту было бы нечем.

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};
fs.mkdirSync(TMP, { recursive: true });
let html = fs.readFileSync(path.join(DOCS, 'museums.html'), 'utf8');
html = html
  .replace(/<link rel="stylesheet" href="https:\/\/unpkg\.com\/leaflet[^>]*>/, '<link rel="stylesheet" href="leaflet.css">')
  .replace(/<script src="https:\/\/unpkg\.com\/leaflet@[^>]*><\/script>/, '<script src="leaflet.js"></script>')
  .replace(/<link rel="stylesheet" href="https:\/\/unpkg\.com\/leaflet\.markercluster[^>]*>/, '<link rel="stylesheet" href="MarkerCluster.css">')
  .replace(/<script src="https:\/\/unpkg\.com\/leaflet\.markercluster[^>]*><\/script>/, '<script src="markercluster.js"></script>')
  .replace(/href="style\.css"/, 'href="style.css"');
fs.writeFileSync(path.join(TMP, 'museums.html'), html);
fs.copyFileSync(require.resolve('leaflet/dist/leaflet.js'), path.join(TMP, 'leaflet.js'));
fs.copyFileSync(require.resolve('leaflet/dist/leaflet.css'), path.join(TMP, 'leaflet.css'));
fs.copyFileSync(require.resolve('leaflet.markercluster/dist/leaflet.markercluster.js'), path.join(TMP, 'markercluster.js'));
fs.copyFileSync(require.resolve('leaflet.markercluster/dist/MarkerCluster.css'), path.join(TMP, 'MarkerCluster.css'));
fs.copyFileSync(path.join(DOCS, 'style.css'), path.join(TMP, 'style.css'));
fs.copyFileSync(path.join(DOCS, 'map-config.js'), path.join(TMP, 'map-config.js'));

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

(async () => {
  const browser = await chromium.launch(LAUNCH);

  // ---------- десктоп ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push(e.message.slice(0, 140)));
    page.on('console', m => { if (m.type() === 'error' && !/net::ERR|Failed to load/i.test(m.text())) errs.push('CONSOLE: ' + m.text().slice(0, 140)); });

    await page.goto('file://' + TMP + '/museums.html');
    await page.waitForTimeout(1500);

    ok('нет ошибок в консоли', errs.length === 0, errs.join(' | '));
    ok('карта создана', await page.locator('.leaflet-container').count() === 1);

    const markers = await page.locator('.leaflet-marker-icon').count();
    ok('метки на карте', markers > 0, markers + ' шт.');

    const cards = await page.locator('.museum-card').count();
    ok('карточки музеев', cards === 50, cards + ' шт.');

    const thumbs = await page.locator('.museum-thumb img').count();
    ok('миниатюры картин в карточках', thumbs > 0, thumbs + ' шт.');

    // переключатель слоёв
    ok('переключатель слоёв есть', await page.locator('.leaflet-control-layers').count() === 1);
    const layerCount = await page.locator('.leaflet-control-layers-base input[type=radio]').count();
    const layerNames = await page.evaluate(() => Object.keys(window.layers));
    ok('слои в переключателе', layerCount === 5, layerNames.join(', '));
    ok('CARTO больше не используется', !(await page.content()).includes('cartocdn'));

    // карта закреплена (sticky) на широком экране
    const pos = await page.locator('.museums-map-col').evaluate(el => getComputedStyle(el).position);
    ok('карта закреплена на десктопе', pos === 'sticky', pos);

    // поиск
    await page.fill('#museum-search', 'париж');
    await page.waitForTimeout(400);
    let visible = await page.locator('.museum-card:not([hidden])').count();
    ok('поиск фильтрует карточки', visible > 0 && visible < 50, visible + ' из 50');
    const markersAfter = await page.locator('.leaflet-marker-icon').count();
    ok('метки на карте фильтруются вместе со списком', markersAfter < markers, markersAfter + ' из ' + markers);
    const counter = await page.locator('#museum-found').textContent();
    ok('счётчик найденного', counter.trim().length > 0, counter.trim());

    // пустой результат
    await page.fill('#museum-search', 'ззззз');
    await page.waitForTimeout(400);
    ok('сообщение «ничего не найдено»', await page.locator('#museums-empty').isVisible());

    await page.fill('#museum-search', '');
    await page.waitForTimeout(400);
    visible = await page.locator('.museum-card:not([hidden])').count();
    ok('очистка поиска возвращает всё', visible === 50, visible + '/50');

    // сортировка
    const firstByCount = (await page.locator('.museum-card h3').first().textContent()).trim();
    await page.selectOption('#museum-sort', 'name');
    await page.waitForTimeout(300);
    const firstByName = (await page.locator('.museum-card h3').first().textContent()).trim();
    ok('сортировка по названию меняет порядок', firstByName !== firstByCount, `${firstByCount} → ${firstByName}`);
    await page.selectOption('#museum-sort', 'country');
    await page.waitForTimeout(300);
    ok('сортировка по стране работает', (await page.locator('.museum-card').count()) === 50);
    await page.selectOption('#museum-sort', 'count');
    await page.waitForTimeout(300);

    // клик по карточке ведёт к метке
    const mapped = page.locator('.museum-card[data-mapped="1"]').first();
    const beforeCenter = await page.evaluate(() => map.getCenter().lat + ',' + map.getCenter().lng);
    // кликаем по заголовку: в центре карточки лежат миниатюры-ссылки на картины
    await mapped.locator('h3').click();
    await page.waitForTimeout(1400);
    const afterCenter = await page.evaluate(() => map.getCenter().lat + ',' + map.getCenter().lng);
    ok('клик по карточке двигает карту', beforeCenter !== afterCenter);
    ok('карточка подсвечивается', await mapped.evaluate(el => el.classList.contains('active')));
    ok('попап метки открылся', await page.locator('.leaflet-popup').count() === 1);

    // клик по метке подсвечивает карточку
    await page.evaluate(() => { document.querySelectorAll('.museum-card.active').forEach(c => c.classList.remove('active')); });
    // кликаем по объекту метки, а не по пикселю: меток много и они
    // перекрывают друг друга, попасть мышью в конкретную ненадёжно
    await page.evaluate(() => { markers[MUSEUMS[0].id].fire('click'); });
    await page.waitForTimeout(500);
    ok('клик по метке подсвечивает карточку', await page.locator('.museum-card.active').count() === 1);

    // раскрытие списка картин
    const toggle = page.locator('.museum-toggle').first();
    const listId = await toggle.getAttribute('aria-controls');
    await toggle.click();
    await page.waitForTimeout(300);
    ok('список картин раскрывается', await page.locator(`#${listId}`).isVisible());
    ok('aria-expanded выставлен', (await toggle.getAttribute('aria-expanded')) === 'true');
    await toggle.click();
    await page.waitForTimeout(300);
    ok('список картин сворачивается', !(await page.locator(`#${listId}`).isVisible()));

    // полноэкранная карта
    await page.click('.map-expand');
    await page.waitForTimeout(600);
    ok('карта разворачивается на весь экран', await page.locator('.map-shell.fullscreen').count() === 1);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(600);
    ok('Escape сворачивает карту', await page.locator('.map-shell.fullscreen').count() === 0);

    // тёмная тема переключает слой карты
    await page.click('[data-theme-toggle]');
    await page.waitForTimeout(600);
    ok('в тёмной теме карта затемняется фильтром',
       await page.locator('#map').evaluate(el => el.classList.contains('map-dark')));
    await page.evaluate(() => { map.eachLayer(l => {}); Object.keys(layers).forEach(n => { if (map.hasLayer(layers[n])) map.removeLayer(layers[n]); }); map.addLayer(layers['Спутник']); map.fire('baselayerchange', {layer: layers['Спутник']}); });
    await page.waitForTimeout(300);
    ok('на спутнике фильтр не применяется',
       !(await page.locator('#map').evaluate(el => el.classList.contains('map-dark'))));

    ok('нет ошибок за весь сценарий', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // ---------- слой Яндекса ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push(e.message.slice(0, 120)));
    await page.goto('file://' + TMP + '/museums.html');
    await page.waitForTimeout(1200);
    const names = await page.evaluate(() => Object.keys(window.layers));
    const hasKey = await page.evaluate(() => !!(window.MAP_KEYS && window.MAP_KEYS.yandex));
    ok('ключ Яндекса подхватился из map-config.js', hasKey);
    ok('слой Яндекса добавлен в переключатель', names.some(n => n.includes('Яндекс')), names.join(', '));
    const yUrl = await page.evaluate(() => window.layers['Яндекс'] && window.layers['Яндекс']._url);
    ok('слой указывает на Tiles API', /tiles\.api-maps\.yandex\.ru/.test(yUrl || ''), (yUrl||'').slice(0,80));
    ok('страница не падает при недоступных тайлах', errs.length === 0, errs.join('|'));
    await ctx.close();
  }

  // ---------- адаптивность ----------
  for (const vp of [{ w: 320, h: 640 }, { w: 375, h: 667 }, { w: 768, h: 1024 }, { w: 1024, h: 800 }, { w: 1440, h: 900 }]) {
    const ctx = await browser.newContext({ viewport: { width: vp.w, height: vp.h }, isMobile: vp.w < 900, hasTouch: vp.w < 900 });
    const page = await ctx.newPage();
    await page.goto('file://' + TMP + '/museums.html');
    await page.waitForTimeout(900);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    ok(`${vp.w}px — нет горизонтальной прокрутки`, overflow <= 1, `перелив ${overflow}px`);
    if (vp.w <= 1000) {
      const cols = await page.locator('.museums-layout').evaluate(el => getComputedStyle(el).gridTemplateColumns);
      ok(`${vp.w}px — одна колонка`, cols.split(' ').length === 1, cols);
    }
    await ctx.close();
  }

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ КАРТА МУЗЕЕВ ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
