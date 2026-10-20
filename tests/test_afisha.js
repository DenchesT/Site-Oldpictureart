// Афиша в браузере: что идёт «сегодня», решает скрипт, и «сегодня» здесь
// подставляется. Проверяется страница afisha.html (вкладки, порядок,
// «последние дни», «откроется …», закончившиеся исчезают, переход по
// ссылке на запись) и блок на главной (по три в колонке, ссылки на записи).
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
  await page.addInitScript(t => {
    const Real = Date, fixed = new Real(t).getTime();
    function FakeDate(...a) { return a.length ? new Real(...a) : new Real(fixed); }
    FakeDate.prototype = Real.prototype;
    FakeDate.now = () => fixed;
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
    all: [...document.querySelectorAll('.afisha-item')].map(row),
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
  ok('ничего закончившегося', st.all.every(r => r.end >= DAY), st.all.filter(r => r.end < DAY).map(r => r.title).join(', '));
  ok('идущие — по дате закрытия', st.running.every((r, i, a) => !i || a[i - 1].end <= r.end), st.running.map(r => r.end).join(' '));
  ok('будущие — по дате открытия, с «откроется …»',
     st.soon.every((r, i, a) => (!i || a[i - 1].start <= r.start) && /^откроется \d+ /.test(r.when)), st.soon.map(r => r.when).join(' | '));
  ok('у идущих — «до …»', st.running.every(r => /^(до|последние дни — до|последний день)/.test(r.when)), st.running.map(r => r.when).join(' | '));
  const expectRu = data.filter(x => x.country === 'Россия' && x.end >= DAY &&
    (x.start <= DAY || (new Date(x.start) - new Date(DAY)) / 864e5 <= 92)).length;
  ok('счётчик на вкладке — сколько записей на ней', st.counts[0] === expectRu && st.running.length + st.soon.length === expectRu,
     `${st.counts[0]} / ${st.running.length + st.soon.length} / ждали ${expectRu}`);

  // Города России.
  const areaOf = x => x.area || (['Москва', 'Абрамцево', 'Архангельское', 'Серпухов', 'Коломна', 'Сергиев Посад', 'Истра'].includes(x.city) ? 'moscow'
    : ['Санкт-Петербург', 'Петергоф', 'Пушкин', 'Павловск', 'Гатчина', 'Ломоносов', 'Кронштадт'].includes(x.city) ? 'spb' : 'regions');
  const live = data.filter(x => x.country === 'Россия' && x.end >= DAY && (x.start <= DAY || (new Date(x.start) - new Date(DAY)) / 864e5 <= 92));
  const areaHere = await page.evaluate(() => ({
    shown: !document.querySelector('.afisha-area').hidden,
    btns: [...document.querySelectorAll('.afisha-area button')].filter(b => !b.hidden)
      .map(b => [b.dataset.area, +b.querySelector('.visit-count').textContent]),
  }));
  ok('во вкладке «Россия» — переключатель городов', areaHere.shown, JSON.stringify(areaHere));
  const wantAreas = ['moscow', 'spb', 'regions'].filter(a => live.some(x => areaOf(x) === a));
  ok('…с числом выставок в каждом городе', wantAreas.every(a => (areaHere.btns.find(b => b[0] === a) || [])[1] === live.filter(x => areaOf(x) === a).length),
     JSON.stringify(areaHere.btns));
  if (wantAreas.includes('moscow')) {
    await page.click('.afisha-area [data-area="moscow"]');
    st = await state(page);
    const moscowIds = await page.evaluate(() => [...document.querySelectorAll('.afisha-item')].filter(li => !li.hidden).map(li => li.dataset.area));
    ok('«Москва» — только московские выставки', moscowIds.length && moscowIds.every(a => a === 'moscow'), moscowIds.join(','));
    await page.reload();
    await page.waitForTimeout(200);
    ok('…выбор города запоминается', await page.$eval('.afisha-area [data-area="moscow"]', b => b.getAttribute('aria-pressed')) === 'true');
    await page.click('.afisha-area [data-area="all"]');
  }
  await page.click('.afisha-switch [data-region="world"]');
  st = await state(page);
  ok('во вкладке «Мир» переключателя городов нет', await page.$eval('.afisha-area', e => e.hidden));
  ok('вкладка «Мир» переключает список', st.pressed === 'world' && st.running.length && st.running.every(r => r.region === 'world'));
  const lastDays = st.running.find(r => r.last);
  const inWeek = data.find(x => x.country !== 'Россия' && x.start <= DAY && x.end >= DAY &&
                               (new Date(x.end) - new Date(DAY)) / 864e5 <= 7);
  if (inWeek) ok('закрывается в ближайшую неделю — «последние дни»', lastDays && /^последние дни — до/.test(lastDays.when), lastDays && lastDays.when);
  await page.reload();
  await page.waitForTimeout(200);
  st = await state(page);
  ok('выбранная вкладка запоминается', st.pressed === 'world', st.pressed);
  await page.close();

  // Через месяц: закончившееся ушло, открывшееся переехало в «Идут сейчас».
  const LATER = plusDays(DAY, 36);
  const LAST = plusDays(data.map(x => x.end).sort().pop(), 1);
  page = await openAt(ctx, 'afisha.html', LATER + 'T12:00:00');
  await page.click('.afisha-switch [data-region="russia"]');
  st = await state(page);
  const closed = data.find(x => x.country === 'Россия' && x.end >= DAY && x.end < LATER);
  const opened = data.find(x => x.country === 'Россия' && x.start > DAY && x.start <= LATER && x.end >= LATER);
  if (closed) ok(`закрылась к ${LATER} — пропала («${closed.title}»)`, !st.all.some(r => r.title === closed.title));
  if (opened) ok(`открылась к ${LATER} — в «Идут сейчас» («${opened.title}»)`, st.running.some(r => r.title === opened.title));
  await page.close();

  // Всё закончилось — пусто, но вежливо.
  page = await openAt(ctx, 'afisha.html', LAST + 'T12:00:00');
  st = await state(page);
  const empty = await page.$eval('#afisha-empty', e => !e.hidden);
  ok('всё закончилось — «пусто», разделов нет', empty && !st.runningBox && !st.soonBox && st.all.length === 0);
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
  const blk = await page.evaluate(() => {
    const b = document.getElementById('afisha-block');
    if (!b) return null;
    return {
      hidden: b.hidden,
      cols: [...b.querySelectorAll('.afisha-col')].filter(c => !c.hidden).map(c => ({
        region: c.dataset.region,
        rows: [...c.querySelectorAll('.now-item')].filter(li => !li.hidden).map(li => ({
          href: li.querySelector('a').getAttribute('href'), end: li.dataset.end, start: li.dataset.start,
          when: li.querySelector('.now-when').textContent.trim() })),
      })),
      more: !!b.querySelector('a[href="afisha.html"]'),
    };
  });
  ok('на главной блок афиши виден', blk && !blk.hidden, JSON.stringify(blk && blk.hidden));
  ok('…две колонки: Россия и мир', blk && blk.cols.map(c => c.region).join() === 'russia,world');
  ok('…не больше трёх в колонке', blk && blk.cols.every(c => c.rows.length && c.rows.length <= 3));
  ok('…идущие, ближайшие к закрытию', blk && blk.cols.every(c => c.rows.every((r, i, a) => r.start <= DAY && (!i || a[i - 1].end <= r.end))),
     blk && JSON.stringify(blk.cols.map(c => c.rows.map(r => r.end))));
  const ids = new Set((fs.readFileSync(path.join(DOCS, 'afisha.html'), 'utf8').match(/id="a-[^"]+"/g) || []).map(s => s.slice(4, -1)));
  ok('…строки ведут на записи афиши', blk && blk.cols.every(c => c.rows.every(r => r.href.startsWith('afisha.html#') && ids.has(r.href.slice(12)))));
  ok('…и ссылка «Вся афиша»', blk && blk.more);
  ok('главная без ошибок скрипта', page.errors.length === 0, page.errors.join(' | '));
  await page.close();
  page = await openAt(ctx, 'index.html', LAST + 'T12:00:00');
  ok('всё закончилось — блока на главной нет', await page.$eval('#afisha-block', b => b.hidden).catch(() => true));
  await page.close();

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
