// Афиша в браузере: что идёт «сегодня», решает скрипт, и «сегодня» здесь
// подставляется. Проверяется страница afisha.html (вкладки, порядок,
// «последние дни», «откроется …», закончившиеся исчезают, переход по
// ссылке на запись, фильтры города, страны и эпохи, «Успеть на этой
// неделе», «Рядом со мной», карта и её подсказки, «На сайте: …», «Был»)
// и раздел в панели главной.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const DOCS = path.join(ROOT, 'docs');
const f = n => 'file://' + DOCS + '/' + n;
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

async function openAt(ctx, file, today) {
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // «Сегодня» сдвинуто, но часы идут: анимациям карты нужно время.
  await page.addInitScript(t => {
    const Real = Date, shift = new Real(t).getTime() - Real.now();
    function FakeDate(...a) { return a.length ? new Real(...a) : new Real(Real.now() + shift); }
    FakeDate.prototype = Real.prototype;
    FakeDate.now = () => Real.now() + shift;
    FakeDate.UTC = Real.UTC;
    FakeDate.parse = Real.parse;
    window.Date = FakeDate;
  }, today);
  await page.goto(f(file));
  await page.waitForTimeout(200);
  page.errors = errors;
  return page;
}

const state = page => page.evaluate(() => {
  const vis = sel => [...document.querySelectorAll(sel)].filter(li => !li.hidden);
  const row = li => ({ id: li.id, title: li.querySelector('.afisha-title').textContent.trim(),
                       start: li.dataset.start, end: li.dataset.end, region: li.dataset.region,
                       when: li.querySelector('.now-when').textContent.trim(), last: li.classList.contains('now-last') });
  return {
    running: vis('#afisha-running .afisha-item').map(row),
    soon: vis('#afisha-soon .afisha-item').map(row),
    all: vis('.afisha-item').map(row),
    pressed: (document.querySelector('.afisha-switch [aria-pressed="true"]') || {}).dataset?.region,
    counts: [...document.querySelectorAll('.afisha-switch .visit-count')].map(e => +e.textContent),
    runningBox: !document.getElementById('afisha-running-box').hidden,
    soonBox: !document.getElementById('afisha-soon-box').hidden,
  };
});

(async () => {
  if (!fs.existsSync(path.join(DOCS, 'afisha.html'))) {
    console.log('afisha.html нет (нет afisha.json) — проверять нечего');
    console.log('\nВсего: 0, провалено: 0');
    process.exit(0);
  }
  const data = JSON.parse(fs.readFileSync(path.join(ROOT, 'afisha.json'), 'utf8')).exhibitions;
  // День проверки берём из самого списка — тот, когда идёт больше всего
  // выставок и в России, и в мире. Тогда проверка не зависит ни от
  // сегодняшнего дня, ни от того, как давно обновляли afisha.json.
  const runningOn = (d, ru) => data.filter(x => (x.country === 'Россия') === ru && x.start <= d && x.end >= d).length;
  const DAY = data.map(x => x.start).sort()
    .filter(d => runningOn(d, true) && runningOn(d, false))
    .sort((a, b) => (runningOn(b, true) + runningOn(b, false)) - (runningOn(a, true) + runningOn(a, false)) || (a < b ? -1 : 1))[0];
  if (!DAY) {
    console.log('В afisha.json нет дня, когда идут выставки и в России, и в мире');
    console.log('\nВсего: 1, провалено: 1');
    process.exit(1);
  }
  const plusDays = (d, n) => { const t = new Date(d + 'T12:00:00'); t.setDate(t.getDate() + n);
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`; };
  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });

  // ---------- страница ----------
  let page = await openAt(ctx, 'afisha.html', DAY + 'T12:00:00');
  let st = await state(page);
  ok('без ошибок скрипта', page.errors.length === 0, page.errors.join(' | '));
  ok('по умолчанию вкладка «Россия»', st.pressed === 'russia', st.pressed);
  ok('видно только Россию', st.running.length && st.running.concat(st.soon).every(r => r.region === 'russia'));
  ok('архив скрыт по умолчанию', st.all.every(r => r.end >= DAY), st.all.filter(r => r.end < DAY).map(r => r.title).join(', '));
  ok('идущие — по дате закрытия', st.running.every((r, i, a) => !i || a[i - 1].end <= r.end), st.running.map(r => r.end).join(' '));
  ok('будущие — по дате открытия, с «откроется …»',
     st.soon.every((r, i, a) => (!i || a[i - 1].start <= r.start) && /^откроется \d+ /.test(r.when)), st.soon.map(r => r.when).join(' | '));
  ok('у идущих — «до …»', st.running.every(r => /^(до|последние дни — до|последний день)/.test(r.when)), st.running.map(r => r.when).join(' | '));
  const expectRu = data.filter(x => x.country === 'Россия' && x.end >= DAY &&
    (x.start <= DAY || (new Date(x.start) - new Date(DAY)) / 864e5 <= 92)).length;
  ok('счётчик на вкладке — сколько записей на ней', st.counts[0] === expectRu && st.running.length + st.soon.length === expectRu,
     `${st.counts[0]} / ${st.running.length + st.soon.length} / ждали ${expectRu}`);

  // Дополнительные фильтры: используем реальные записи и подставленную дату.
  const archivedRu = data.filter(x => x.country === 'Россия' && x.end < DAY).length;
  await page.click('.afisha-status-switch [data-status="archive"]');
  const archiveCount = await page.$$eval('#afisha-archive .afisha-item:not([hidden])', xs => xs.length);
  ok('архив по России показывает завершившиеся выставки', archiveCount === archivedRu,
     `${archiveCount} из ${archivedRu}`);
  if (archiveCount) {
    const archiveYears = [...new Set(data.filter(x => x.country === 'Россия' && x.end < DAY).map(x => x.end.slice(0, 4)))];
    const year = archiveYears[0];
    await page.locator('#afisha-more-filters').evaluate(d => d.open = true);
    await page.selectOption('#afisha-archive-year', year);
    const years = await page.$$eval('#afisha-archive .afisha-item:not([hidden])', xs => xs.map(x => x.dataset.end.slice(0, 4)));
    ok('год архива оставляет только выставки выбранного года', years.length > 0 && years.every(y => y === year), years.join(', '));
    await page.locator('#afisha-more-filters').evaluate(d => d.open = true);
    await page.selectOption('#afisha-archive-year', 'all');
  }
  await page.click('.afisha-status-switch [data-status="current"]');

  const first = await page.$eval('#afisha-running .afisha-item:not([hidden])', li => ({
    id: li.id, title: li.querySelector('.afisha-title a').textContent.trim(),
    venue: li.querySelector('.afisha-place').textContent.split(' · ')[0]
  }));
  await page.fill('#afisha-query', first.title.slice(0, Math.min(6, first.title.length)));
  await page.waitForTimeout(200);
  const queryHit = await page.$eval('#' + first.id, li => !li.hidden);
  ok('поиск находит выставку по названию', queryHit);
  await page.fill('#afisha-query', '');
  await page.waitForTimeout(200);
  await page.selectOption('#afisha-venue', first.venue);
  const venues = await page.$$eval('.afisha-item:not([hidden])', xs => xs.map(x => x.querySelector('.afisha-place').textContent.split(' · ')[0]));
  ok('музей ограничивает список одним местом', venues.length > 0 && venues.every(v => v === first.venue));
  await page.selectOption('#afisha-venue', 'all');

  await page.click('#' + first.id + ' .afisha-favorite');
  await page.click('.afisha-status-switch [data-status="favorites"]');
  const liked = await page.$$eval('.afisha-item:not([hidden])', xs => xs.map(x => x.id));
  ok('избранное оставляет отмеченную выставку', liked.length === 1 && liked[0] === first.id, liked.join(', '));
  await page.reload();
  await page.waitForTimeout(200);
  ok('избранное сохраняется после перезагрузки', await page.$eval('#' + first.id + ' .afisha-favorite', b => b.getAttribute('aria-pressed') === 'true'));
  await page.click('.afisha-status-switch [data-status="current"]');
  await page.click('#' + first.id + ' .afisha-favorite');

  await page.locator('#afisha-more-filters').evaluate(d => d.open = true);
    await page.selectOption('#afisha-closing', '30');
  const closings = await page.$$eval('.afisha-item:not([hidden])', xs => xs.map(x => x.dataset.end));
  ok('закрытие за 30 дней показывает только действующие выставки', closings.every(d => d >= DAY && d <= plusDays(DAY, 30)));
  await page.locator('#afisha-more-filters').evaluate(d => d.open = true);
    await page.selectOption('#afisha-closing', 'all');
  await page.locator('#afisha-more-filters').evaluate(d => d.open = true);
    // OPA afisha UI: select the soon tab before testing the opening filter.
    await page.click('.afisha-status-switch [data-status="soon"]');
    await page.selectOption('#afisha-opening', '90');
  const openings = await page.$$eval('.afisha-item:not([hidden])', xs => xs.map(x => x.dataset.start));
  ok('открытие за 90 дней показывает только будущие выставки', openings.every(d => d > DAY && d <= plusDays(DAY, 90)));
  await page.click('#afisha-reset');
  await page.selectOption('#afisha-sort', 'title');
  const titles = await page.$$eval('#afisha-running .afisha-item:not([hidden])', xs => xs.map(x => x.querySelector('.afisha-title a').textContent.trim()));
  ok('сортировка по названию', titles.every((t, i) => i === 0 || titles[i - 1].localeCompare(t, 'ru') <= 0));
  await page.click('#afisha-reset');

  // Города России — выпадающий список.
  // Те же списки, что MOSCOW_AREA и SPB_AREA в sitebuild/afisha.py.
  const MOSCOW = ['Москва', 'Абрамцево', 'Архангельское', 'Серпухов', 'Коломна', 'Сергиев Посад', 'Истра', 'Новый Иерусалим',
    'Мелихово', 'Мураново', 'Подольск', 'Клин', 'Звенигород', 'Дмитров', 'Можайск', 'Бородино', 'Кусково', 'Коломенское', 'Царицыно', 'Ясенево'];
  const SPB = ['Санкт-Петербург', 'Петербург', 'Петергоф', 'Пушкин', 'Царское Село', 'Павловск', 'Гатчина', 'Ломоносов', 'Ораниенбаум',
    'Кронштадт', 'Стрельна', 'Репино'];
  const areaOf = x => x.area || (MOSCOW.includes(x.city) ? 'moscow' : SPB.includes(x.city) ? 'spb' : 'regions');
  const liveOf = ru => data.filter(x => (x.country === 'Россия') === ru && x.end >= DAY && (x.start <= DAY || (new Date(x.start) - new Date(DAY)) / 864e5 <= 92));
  const live = liveOf(true), liveWorld = liveOf(false);
  const opts = id => page.evaluate(i => [...document.querySelectorAll('#' + i + ' option')].filter(o => !o.hidden)
    .map(o => [o.value, +((o.textContent.match(/\((\d+)\)/) || [])[1])]), id);
  ok('во вкладке «Россия» — выбор города, страны нет',
     await page.$eval('#afisha-area-box', e => !e.hidden) && await page.$eval('#afisha-country-box', e => e.hidden));
  const areaOpts = await opts('afisha-area');
  const wantAreas = ['moscow', 'spb', 'regions'].filter(a => live.some(x => areaOf(x) === a));
  ok('…с числом выставок в каждом городе', wantAreas.every(a => (areaOpts.find(o => o[0] === a) || [])[1] === live.filter(x => areaOf(x) === a).length),
     JSON.stringify(areaOpts));
  if (wantAreas.includes('moscow')) {
    await page.selectOption('#afisha-area', 'moscow');
    const moscowIds = await page.evaluate(() => [...document.querySelectorAll('.afisha-item')].filter(li => !li.hidden).map(li => li.dataset.area));
    ok('«Москва» — только московские выставки', moscowIds.length && moscowIds.every(a => a === 'moscow'), moscowIds.join(','));
    await page.reload();
    await page.waitForTimeout(200);
    ok('…выбор города запоминается', await page.$eval('#afisha-area', s => s.value) === 'moscow');
    await page.selectOption('#afisha-area', 'all');
  }
  // Эпоха.
  const tagged = live.filter(x => (x.tags || []).includes('russian'));
  if (tagged.length && tagged.length < live.length) {
    await page.selectOption('#afisha-epoch', 'russian');
    const n = await page.evaluate(() => [...document.querySelectorAll('.afisha-item')].filter(li => !li.hidden).length);
    ok('эпоха «Русское искусство» — только помеченные ею', n === tagged.length, `${n} из ${tagged.length}`);
    const cnt = (await opts('afisha-area')).find(o => o[0] === 'all');
    ok('…и числа в списке городов — с учётом эпохи', cnt && cnt[1] === tagged.length, JSON.stringify(cnt));
    await page.selectOption('#afisha-epoch', 'all');
  }
  // «Успеть на этой неделе».
  const weekWant = live.filter(x => x.start <= DAY && (new Date(x.end) - new Date(DAY)) / 864e5 <= 7).length;
  const weekHave = await page.evaluate(() => { const w = document.getElementById('afisha-week'); return w.hidden ? 0 : w.querySelectorAll('li').length; });
  ok('«Успеть на этой неделе» — выставки в последние дни', weekHave === weekWant, `${weekHave} из ${weekWant}`);
  // «На сайте: …» и «Был».
  const works = await page.$$eval('.afisha-works', ws => ws.map(w => ({
    names: w.querySelectorAll('.afisha-works-title a').length, thumbs: w.querySelectorAll('.afisha-thumbs img').length,
    links: [...w.querySelectorAll('a')].every(a => /^(artist-|[a-z0-9-]+\.html$)/.test(a.getAttribute('href'))) })));
  ok('«На сайте: …» — художники ссылками и миниатюры работ',
     works.length && works.every(w => w.names && w.thumbs && w.thumbs <= 4 && w.links), JSON.stringify(works.slice(0, 3)));
  await page.click('.afisha-switch [data-region="world"]');
  st = await state(page);
  ok('во вкладке «Мир» — выбор страны, города нет',
     await page.$eval('#afisha-area-box', e => e.hidden) && await page.$eval('#afisha-country-box', e => !e.hidden));
  const countries = [...new Set(liveWorld.map(x => x.country))];
  if (countries.length > 1) {
    const top = countries.sort((a, b) => liveWorld.filter(x => x.country === b).length - liveWorld.filter(x => x.country === a).length)[0];
    await page.selectOption('#afisha-country', top);
    const shownC = await page.evaluate(() => [...document.querySelectorAll('.afisha-item')].filter(li => !li.hidden).map(li => li.dataset.country));
    ok(`страна «${top}» — только её выставки`, shownC.length === liveWorld.filter(x => x.country === top).length && shownC.every(c => c === top),
       `${shownC.length}`);
    await page.selectOption('#afisha-country', 'all');
  }
  ok('вкладка «Мир» переключает список', st.pressed === 'world' && st.running.length && st.running.every(r => r.region === 'world'));
  const lastDays = st.running.find(r => r.last);
  const inWeek = data.find(x => x.country !== 'Россия' && x.start <= DAY && x.end >= DAY &&
                               (new Date(x.end) - new Date(DAY)) / 864e5 <= 7);
  if (inWeek) ok('закрывается в ближайшую неделю — «последние дни»', lastDays && /^последние дни — до/.test(lastDays.when), lastDays && lastDays.when);
  await page.reload();
  await page.waitForTimeout(200);
  st = await state(page);
  ok('выбранная вкладка запоминается', st.pressed === 'world', st.pressed);

  // ---------- карта ----------
  const mapState = () => page.evaluate(() => {
    const el = document.getElementById('afisha-map');
    if (!el || !el.afishaCluster) return null;
    const want = [...document.querySelectorAll('.afisha-item[data-lat]')].filter(li => !li.hidden).length;
    return { shown: !el.hidden, markers: el.afishaCluster.getLayers().length, want };
  });
  let ms = await mapState();
  const hasCoords = /data-lat=/.test(fs.readFileSync(path.join(DOCS, 'afisha.html'), 'utf8'));
  if (hasCoords) {
    ok('на странице — карта выставок', ms && ms.shown, JSON.stringify(ms));
    ok('…метки — ровно те выставки, что сейчас в списке', ms && ms.markers === ms.want && ms.want > 0, JSON.stringify(ms));
    await page.click('.afisha-switch [data-region="russia"]');
    await page.waitForTimeout(150);
    const ru = await mapState();
    await page.click('.afisha-switch [data-region="world"]');
    await page.waitForTimeout(150);
    const wo = await mapState();
    ok('…вкладка меняет и метки', ru && wo && ru.markers === ru.want && wo.markers === wo.want && ru.want !== wo.want,
       JSON.stringify({ ru, wo }));
    // Приближение к метке — анимация, а ей нужны идущие часы: на странице
    // с подставленной датой время стоит. Поэтому здесь — настоящее «сегодня».
    const live = await ctx.newPage();
    await live.goto(f('afisha.html'));
    await live.waitForTimeout(400);
    const pinTitle = await live.$eval('.afisha-item:not([hidden]) .afisha-pin', b => b.closest('.afisha-item').querySelector('.afisha-title a').textContent.trim()).catch(() => null);
    if (pinTitle) {
      await live.click('.afisha-item:not([hidden]) .afisha-pin');
      await live.waitForSelector('.leaflet-popup-content', { timeout: 6000 }).catch(() => null);
      const pop = await live.$eval('.leaflet-popup-content', e => e.textContent).catch(() => '');
      ok('«на карте» открывает подсказку этой выставки', pop.includes(pinTitle), pop.slice(0, 80));
      const target = await live.$eval('.leaflet-popup-content b a', a => a.getAttribute('href')).catch(() => '');
      if (target) await live.click('.leaflet-popup-content b a');
      await live.waitForTimeout(300);
      ok('…ссылка в подсказке ведёт к записи и подсвечивает её',
         await live.evaluate(id => { const el = document.getElementById(id); return !!el && !el.hidden && el.classList.contains('afisha-target'); }, target.slice(1)),
         target);
    }
    await live.close();
  } else {
    ok('координат нет — карты нет', !ms);
  }
  await page.close();

  // ---------- «Рядом со мной» ----------
  const located = data.filter(x => x.lat !== undefined && x.country === 'Россия' && x.end >= DAY && x.start <= DAY);
  if (located.length && hasCoords) {
    const here = located[0];
    const geo = await browser.newContext({ viewport: { width: 1280, height: 900 }, permissions: ['geolocation'],
      geolocation: { latitude: here.lat + 0.001, longitude: here.lon } });
    page = await openAt(geo, 'afisha.html', DAY + 'T12:00:00');
    await page.click('.afisha-switch [data-region="world"]');
    await page.locator('#afisha-more-filters').evaluate(d => d.open = true);
    await page.click('#afisha-near-btn');
    await page.waitForFunction(() => document.getElementById('afisha-near-btn').getAttribute('aria-pressed') === 'true', null, { timeout: 5000 }).catch(() => null);
    const near = await page.evaluate(() => {
      const vis = [...document.querySelectorAll('#afisha-running .afisha-item')].filter(li => !li.hidden);
      return { note: document.getElementById('afisha-near').textContent, tab: document.querySelector('.afisha-switch [aria-pressed="true"]').dataset.region,
               dists: vis.filter(li => li.dataset.lat).map(li => +li.dataset.dist), label: (vis[0].querySelector('.afisha-dist') || {}).textContent || '' };
    });
    ok('«Рядом со мной»: ближайшая названа', /^Ближайшая — \d/.test(near.note), near.note);
    ok('…вкладка — там, где ближайшая', near.tab === 'russia', near.tab);
    ok('…список — по расстоянию', near.dists.length > 1 && near.dists.every((d, i, a) => !i || a[i - 1] <= d), near.dists.slice(0, 5).join(' '));
    ok('…у выставок — расстояние («100 м», «2,1 км»)', /^\d[\d\s,]* (м|км)$/.test(near.label), near.label);
    await page.locator('#afisha-more-filters').evaluate(d => d.open = true);
    await page.click('#afisha-near-btn');
    const off = await page.evaluate(() => ({ pressed: document.getElementById('afisha-near-btn').getAttribute('aria-pressed'),
      dist: document.querySelectorAll('.afisha-dist').length }));
    ok('…повторное нажатие — обычный порядок, расстояния убраны', off.pressed === 'false' && off.dist === 0, JSON.stringify(off));
    await page.close();
    await geo.close();
    const deny = await browser.newContext({ viewport: { width: 1280, height: 900 }, permissions: [] });
    page = await openAt(deny, 'afisha.html', DAY + 'T12:00:00');
    await page.locator('#afisha-more-filters').evaluate(d => d.open = true);
    await page.click('#afisha-near-btn');
    await page.waitForFunction(() => /Нет доступа|Не получилось/.test(document.getElementById('afisha-near').textContent), null, { timeout: 8000 }).catch(() => null);
    ok('нет разрешения — понятное объяснение, порядок прежний',
       /Нет доступа|Не получилось/.test(await page.$eval('#afisha-near', e => e.textContent)), await page.$eval('#afisha-near', e => e.textContent));
    await page.close();
    await deny.close();
  }

  // ---------- телефон: карта за кнопкой, подсказка не под кнопками ----------
  if (hasCoords) {
    const tel = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    page = await openAt(tel, 'afisha.html', DAY + 'T12:00:00');
    ok('на телефоне карта свёрнута, кнопка «Показать на карте»',
       await page.evaluate(() => getComputedStyle(document.getElementById('afisha-map')).display === 'none'
         && getComputedStyle(document.getElementById('afisha-map-toggle')).display !== 'none'));
    // Одиночная метка (без соседей в том же здании) — у верхнего края карты.
    const lone = located.find(x => located.filter(y => Math.abs(y.lat - x.lat) < 0.05 && Math.abs(y.lon - x.lon) < 0.05).length === 1);
    if (lone) {
      await page.evaluate(t => { const li = [...document.querySelectorAll('.afisha-item[data-lat]')].find(l => !l.hidden && l.querySelector('.afisha-title a').textContent === t);
        li.querySelector('.afisha-pin').click(); }, lone.title);
      await page.waitForSelector('#afisha-map .leaflet-popup-content', { timeout: 8000 }).catch(() => null);
      await page.waitForTimeout(600);           // карта ещё досдвигается, чтобы подсказка влезла
      const geom = await page.evaluate(() => {
        const r = s => { const e = document.querySelector('#afisha-map ' + s); return e ? e.getBoundingClientRect() : null; };
        const pop = r('.leaflet-popup-content-wrapper'), zoom = r('.leaflet-control-zoom'), lay = r('.leaflet-control-layers');
        const m = document.getElementById('afisha-map').getBoundingClientRect();
        const hit = (a, b) => a && b && !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
        return { open: !!pop, shown: getComputedStyle(document.getElementById('afisha-map')).display !== 'none',
                 zoom: hit(pop, zoom), layers: hit(pop, lay), inside: pop && pop.left >= m.left - 1 && pop.right <= m.right + 1 };
      });
      ok('«на карте» на телефоне раскрывает карту и подсказку', geom.open && geom.shown, JSON.stringify(geom));
      ok('…подсказка не налезает на кнопки карты и не вылезает за край', geom.open && !geom.zoom && !geom.layers && geom.inside, JSON.stringify(geom));
    }
    await page.close();
    await tel.close();
  }

  // Через месяц: закончившееся ушло, открывшееся переехало в «Идут сейчас».
  const LATER = plusDays(DAY, 36);
  const LAST = plusDays(data.map(x => x.end).sort().pop(), 1);
  page = await openAt(ctx, 'afisha.html', LATER + 'T12:00:00');
  await page.click('.afisha-switch [data-region="russia"]');
  st = await state(page);
  const closed = data.find(x => x.country === 'Россия' && x.end >= DAY && x.end < LATER);
  const opened = data.find(x => x.country === 'Россия' && x.start > DAY && x.start <= LATER && x.end >= LATER);
  if (closed) ok(`закрылась к ${LATER} — переехала в архив («${closed.title}»)`, !st.all.some(r => r.title === closed.title) && await page.evaluate(t => [...document.querySelectorAll('#afisha-archive .afisha-item')].some(li => li.querySelector('.afisha-title a').textContent === t), closed.title));
  if (opened) ok(`открылась к ${LATER} — в «Идут сейчас» («${opened.title}»)`, st.running.some(r => r.title === opened.title));
  await page.close();

  // Всё закончилось — пусто, но вежливо.
  page = await openAt(ctx, 'afisha.html', LAST + 'T12:00:00');
  st = await state(page);
  const empty = await page.$eval('#afisha-empty', e => !e.hidden);
  ok('всё закончилось — текущая афиша пуста, архив остаётся', empty && !st.runningBox && !st.soonBox && st.all.length === 0 && await page.$eval('#afisha-archive', e => e.children.length > 0));
  await page.close();

  // Ссылка на запись открывает её вкладку и подсвечивает.
  const worldId = (await (async () => {
    const p = await openAt(ctx, 'afisha.html', DAY + 'T12:00:00');
    const id = await p.$eval('.afisha-item[data-region="world"]', e => e.id).catch(() => null);
    await p.close();
    return id;
  })());
  if (worldId) {
    const p2 = await ctx.newPage();
    await p2.addInitScript(() => { try { localStorage.setItem('afishaRegion', 'russia'); } catch (e) {} });
    await p2.goto(f('afisha.html') + '#' + worldId);
    await p2.waitForTimeout(300);
    const hit = await p2.evaluate(id => {
      const el = document.getElementById(id);
      return { tab: document.querySelector('.afisha-switch [aria-pressed="true"]').dataset.region,
               shown: el && !el.hidden, mark: el && el.classList.contains('afisha-target') };
    }, worldId);
    ok('ссылка на запись мира открывает вкладку «Мир» и подсвечивает её', hit.tab === 'world' && hit.shown && hit.mark, JSON.stringify(hit));
    await p2.close();
  }

  // ---------- главная ----------
  page = await openAt(ctx, 'index.html', DAY + 'T12:00:00');
  // OPA AFISHA UI TESTS 2026-10-31
  const nav = await page.evaluate(() => ({
    link: !!document.querySelector('#sidebar a[href="afisha.html"]'),
    oldPreview: !!document.getElementById('afisha-block'),
    upperPreview: !!document.querySelector('.opa-now-collapsible')
  }));
  ok('на главной только ссылка «Выставки»', nav.link && !nav.oldPreview && !nav.upperPreview, JSON.stringify(nav));
  ok('главная без ошибок скрипта', page.errors.length === 0, page.errors.join(' | '));
  await page.close();
  page = await openAt(ctx, 'index.html', LAST + 'T12:00:00');
  ok('ссылка «Выставки» не зависит от сроков завершения',
     await page.$eval('#sidebar a[href="afisha.html"]', a => a.textContent.trim() === 'Выставки').catch(() => false));
  await page.close();

  // ---------- «Сейчас в афише» на странице музея ----------
  {
    const pages = fs.readdirSync(DOCS).filter(x => x.startsWith('museum-') && x.endsWith('.html'))
      .map(x => [x, (fs.readFileSync(path.join(DOCS, x), 'utf8').split('id="museum-afisha"')[1] || '').split('</section>')[0]])
      .filter(([, sec]) => sec).sort((a, b) => b[1].split('now-item').length - a[1].split('now-item').length);
    ok('на страницах музеев есть блок афиши (у музеев с выставками в afisha.json)', pages.length > 0, String(pages.length));
    if (pages.length) {
      const [file, sec] = pages[0];
      const rows = [...sec.matchAll(/data-start="([^"]+)" data-end="([^"]+)"/g)].map(m => ({ start: m[1], end: m[2] }));
      const days = (a, b) => (new Date(a) - new Date(b)) / 864e5;
      const run = rows.filter(r => r.start <= DAY && r.end >= DAY).sort((a, b) => a.end < b.end ? -1 : 1);
      const soon = rows.filter(r => r.start > DAY && days(r.start, DAY) <= 92).sort((a, b) => a.start < b.start ? -1 : 1);
      const ctxM = await browser.newContext({ viewport: { width: 1280, height: 900 } });
      const p = await openAt(ctxM, file, DAY + 'T12:00:00');
      const got = await p.evaluate(() => {
        const box = document.getElementById('museum-afisha');
        return { shown: !box.hidden, rows: [...box.querySelectorAll('.now-item')].filter(li => !li.hidden)
          .map(li => ({ start: li.dataset.start, end: li.dataset.end, when: li.querySelector('.now-when').textContent })) };
      });
      const want = run.concat(soon);
      ok(`${file}: видны идущие и открывающиеся в ближайшие 92 дня, закончившихся нет`,
         got.shown === (want.length > 0) && got.rows.length === want.length, `${got.rows.length} / ждали ${want.length}`);
      ok('…сначала идущие по дате закрытия, потом будущие по дате открытия',
         JSON.stringify(got.rows.map(r => r.start + r.end)) === JSON.stringify(want.map(r => r.start + r.end)));
      ok('…у идущих «до …», у будущих «откроется …»',
         got.rows.every(r => r.start > DAY ? /^откроется /.test(r.when) : /^(до |последний день)/.test(r.when)), got.rows.map(r => r.when).join(' | '));
      await p.close();
      await ctxM.close();
    }
  }

  // ---------- телефон ----------
  const phone = await browser.newContext({ viewport: { width: 375, height: 800 }, isMobile: true, hasTouch: true });
  for (const n of ['afisha.html', 'index.html']) {
    const p = await openAt(phone, n, DAY + 'T12:00:00');
    const over = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(`375px: ${n} без горизонтальной прокрутки`, over <= 0, 'перелив ' + over + 'px');
    await p.close();
  }

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ АФИША ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra && !r.pass ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
