// «Идёт до 4 октября» — плашка срока работы выставки.
//
// Сайт статический: собранная сегодня страница не знает, в какой день её
// откроют. Поэтому в разметке только даты выставки, а «идёт / последние
// дни / закрылась» решает скрипт в браузере по сегодняшней дате. Здесь
// «сегодня» подставляется — проверяется каждая граница: до открытия,
// середина, последняя неделя, последний день, после закрытия.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const DOCS = path.join(ROOT, 'docs');
const f = n => 'file://' + DOCS + '/' + encodeURIComponent(n).replace(/%2F/g, '/');
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
                'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const RUN = /(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[—–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})/;

function dates(run) {
  const m = RUN.exec(run || '');
  if (!m) return null;
  return { start: new Date(+m[3], +m[2] - 1, +m[1]), end: new Date(+m[6], +m[5] - 1, +m[4]) };
}
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T12:00:00`;
const shift = (d, days) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);
const human = (d, year) => `${d.getDate()} ${MONTHS[d.getMonth()]}` + (d.getFullYear() !== year ? ` ${d.getFullYear()}` : '');

// «Сегодня» подменяется до загрузки страницы. Через Date, а не page.clock:
// так проверка работает и на старом Playwright.
async function openAt(ctx, file, today) {
  const page = await ctx.newPage();
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
  return page;
}

async function badge(page, sel = '.run-status') {
  return page.$eval(sel, el => ({ hidden: el.hidden, text: el.textContent.trim(), state: el.dataset.state || '' }))
    .catch(() => null);
}

(async () => {
  let visits = [];
  try { visits = JSON.parse(fs.readFileSync(path.join(ROOT, 'visits_meta.json'), 'utf8')); } catch (e) {}
  const withRun = visits.filter(v => dates(v.run));
  if (!withRun.length) {
    console.log('\n====== ВЫСТАВКА ЕЩЁ ИДЁТ ======');
    console.log('OK    выставок со сроком работы нет — проверять нечего');
    console.log('\nВсего: 1, провалено: 0');
    process.exit(0);
  }

  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });

  const V = withRun[0];
  const { start, end } = dates(V.run);
  const cases = [
    ['до открытия — «Откроется …»', shift(start, -10), 'soon', `Откроется ${human(start, shift(start, -10).getFullYear())}`],
    ['идёт — «Идёт до …»', shift(start, 1), 'on', `Идёт до ${human(end, shift(start, 1).getFullYear())}`],
    ['последняя неделя — «Последние дни — до …»', shift(end, -3), 'last', `Последние дни — до ${human(end, end.getFullYear())}`],
    ['последний день', end, 'last', 'Последний день'],
    ['после закрытия — «Закрылась …»', shift(end, 5), 'off', `Закрылась ${human(end, shift(end, 5).getFullYear())}`],
    ['через год — с годом', new Date(end.getFullYear() + 1, 5, 1), 'off', `Закрылась ${human(end, end.getFullYear() + 1)}`],
  ];
  // Выставка, открытая меньше недели, сразу попадает в «последние дни» —
  // середину берём только у тех, что шли дольше.
  const long = (end - start) / 864e5 > 10;
  for (const [name, today, state, text] of cases) {
    if (state === 'on' && !long) continue;
    const page = await openAt(ctx, V.filename, iso(today));
    const b = await badge(page);
    ok(`страница похода: ${name}`, b && !b.hidden && b.state === state && b.text === text,
      b ? `${b.state}: ${b.text}` : 'нет плашки');
    await page.close();
  }

  // Без скрипта плашки нет вовсе: в разметке она спрятана.
  const html = fs.readFileSync(path.join(DOCS, V.filename), 'utf8');
  ok('без скрипта плашка спрятана', /<p class="run-status"[^>]*\shidden>/.test(html));

  const museum = visits.find(v => !dates(v.run));
  if (museum) {
    const page = await openAt(ctx, museum.filename, iso(new Date()));
    ok('у похода в музей без срока плашки нет', !(await page.$('.run-status')));
    await page.close();
  }

  // Список: в выбранный день горят ровно те выставки, что тогда шли,
  // а закрытые молчат — иначе «закрылась» стояло бы на каждой второй.
  const today = shift(start, 1);
  const expected = withRun.filter(v => { const d = dates(v.run); return d.start <= today && today <= d.end; })
    .map(v => v.filename).sort();
  const page = await openAt(ctx, 'visits.html', iso(today));
  const shown = await page.$$eval('.visit-card', cards => cards
    .filter(c => { const b = c.querySelector('.run-status'); return b && !b.hidden && /^(on|last)$/.test(b.dataset.state); })
    .map(c => c.querySelector('a.card-link').getAttribute('href')).sort());
  ok('список: «идёт» — ровно у тех выставок, что шли в тот день', JSON.stringify(shown) === JSON.stringify(expected),
    `${shown.length} из ожидаемых ${expected.length}`);
  const closedTexts = await page.$$eval('.visit-card .run-status:not([hidden])', els => els.map(e => e.textContent));
  ok('список: «Закрылась» не пишется', !closedTexts.some(t => /Закрылась/.test(t)));
  await page.close();

  await browser.close();
  console.log('\n====== ВЫСТАВКА ЕЩЁ ИДЁТ ======');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  const fails = results.filter(r => !r.pass);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
