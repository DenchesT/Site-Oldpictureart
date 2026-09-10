// Раздел «Посещения»: список с переключателем и страница одного похода.
//
// Раздел появляется только при наличии visits_meta.json, поэтому проверки
// начинаются с него: без файла всё зелёное и ничего не запускается —
// иначе сборка без посещений валила бы весь прогон.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const DOCS = path.join(ROOT, 'docs');
const f = n => 'file://' + DOCS + '/' + encodeURIComponent(n).replace(/%2F/g, '/');
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

function readVisits() {
  try {
    return JSON.parse(fs.readFileSync(path.join(ROOT, 'visits_meta.json'), 'utf8'));
  } catch (e) {
    return [];
  }
}

(async () => {
  const visits = readVisits();
  if (!visits.length) {
    console.log('\n============ ПОСЕЩЕНИЯ ============');
    console.log('OK    посещений в базе нет — раздел не собирается, проверять нечего');
    console.log('\nВсего: 1, провалено: 0');
    process.exit(0);
  }

  const shows = visits.filter(v => v.kind === 'выставка').length;
  const museums = visits.length - shows;
  const ONE = visits.find(v => (v.images || []).length) || visits[0];

  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 950 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message.slice(0, 120)));

  // ---------- список ----------
  ok('visits.html собран', fs.existsSync(path.join(DOCS, 'visits.html')));
  await page.goto(f('visits.html'));
  await page.waitForTimeout(400);

  const list = await page.evaluate(() => ({
    h1: document.querySelector('h1').textContent.trim(),
    cards: document.querySelectorAll('#visits .visit-card').length,
    buttons: [...document.querySelectorAll('.visit-switch button')].map(b => b.getAttribute('data-kind')),
    counts: [...document.querySelectorAll('.visit-switch .visit-count')].map(s => +s.textContent),
    kinds: [...document.querySelectorAll('#visits .visit-card')].map(c => c.getAttribute('data-kind')),
    links: [...document.querySelectorAll('#visits .card-link')].map(a => a.getAttribute('href')),
    dates: [...document.querySelectorAll('#visits .card-facts div')]
      .filter(d => d.querySelector('span').textContent.trim() === 'Побывал')
      .map(d => d.querySelector('b').textContent.trim()),
  }));
  ok('заголовок раздела', list.h1 === 'Посещения', list.h1);
  ok('карточек столько же, сколько посещений', list.cards === visits.length, `${list.cards} из ${visits.length}`);
  ok('три кнопки переключателя', list.buttons.join(',') === 'all,выставка,музей', list.buttons.join(','));
  ok('числа на кнопках сходятся',
    list.counts[0] === visits.length && list.counts[1] === shows && list.counts[2] === museums,
    list.counts.join('/'));
  ok('у каждой карточки есть вид', list.kinds.every(k => k === 'выставка' || k === 'музей'));
  ok('ссылки ведут на страницы посещений', list.links.every(h => /^visit-/.test(h)));
  ok('свежие сверху', list.dates.length < 2 || list.dates.every((d, i, a) => {
    if (!i) return true;
    const key = s => s.split('.').reverse().join('');
    return key(a[i - 1]) >= key(d);
  }), list.dates.join(' → '));

  // ---------- переключатель ----------
  if (shows) {
    await page.click('.visit-switch button[data-kind="выставка"]');
    await page.waitForTimeout(150);
    const onlyShows = await page.evaluate(() => [...document.querySelectorAll('#visits .visit-card')]
      .filter(c => c.offsetParent !== null).map(c => c.getAttribute('data-kind')));
    ok('фильтр «выставки» оставляет только выставки',
      onlyShows.length === shows && onlyShows.every(k => k === 'выставка'), `${onlyShows.length} шт.`);
  }
  if (museums) {
    await page.click('.visit-switch button[data-kind="музей"]');
    await page.waitForTimeout(150);
    const onlyMuseums = await page.evaluate(() => [...document.querySelectorAll('#visits .visit-card')]
      .filter(c => c.offsetParent !== null).map(c => c.getAttribute('data-kind')));
    ok('фильтр «музеи» оставляет только музеи',
      onlyMuseums.length === museums && onlyMuseums.every(k => k === 'музей'), `${onlyMuseums.length} шт.`);
    // Скрытая карточка обязана исчезнуть совсем, а не стать пустой строкой:
    // у .card раскладка задана через display, и он бьёт [hidden].
    const ghost = await page.evaluate(() => [...document.querySelectorAll('#visits .visit-card[hidden]')]
      .some(c => c.getBoundingClientRect().height > 0));
    ok('скрытые карточки не занимают место', !ghost);
  }
  const saved = await page.evaluate(() => localStorage.getItem('visitFilter'));
  ok('выбор запоминается', saved === 'музей' || saved === 'выставка', String(saved));

  await page.reload();
  await page.waitForTimeout(300);
  const pressed = await page.evaluate(() =>
    document.querySelector('.visit-switch button[aria-pressed="true"]').getAttribute('data-kind'));
  ok('после перезагрузки фильтр тот же', pressed === saved, pressed);

  await page.click('.visit-switch button[data-kind="all"]');
  await page.waitForTimeout(150);
  const allShown = await page.evaluate(() => [...document.querySelectorAll('#visits .visit-card')]
    .filter(c => c.offsetParent !== null).length);
  ok('«все» возвращает весь список', allShown === visits.length, `${allShown} шт.`);

  // ---------- страница одного посещения ----------
  await page.goto(f(ONE.filename));
  await page.waitForTimeout(400);
  const one = await page.evaluate(() => ({
    eyebrow: (document.querySelector('.post-head .eyebrow') || {}).textContent,
    h1: document.querySelector('h1').textContent.trim(),
    shots: document.querySelectorAll('.painting').length,
    spec: [...document.querySelectorAll('.spec-table div')]
      .map(d => d.querySelector('span').textContent.trim()),
    back: (document.querySelector('.topbar-back') || {}).getAttribute
      ? document.querySelector('.topbar-back').getAttribute('href') : '',
    download: !!document.querySelector('.topbar-btn[download]'),
    lupa: typeof window.openLupa === 'function' || !!document.querySelector('.painting-link'),
  }));
  ok('шапка подписана видом похода', /Выставка|Музей/.test(one.eyebrow || ''), (one.eyebrow || '').trim());
  ok('заголовок не пустой', one.h1.length > 2, one.h1);
  ok('все снимки на странице', one.shots === (ONE.images || []).length, `${one.shots} из ${(ONE.images || []).length}`);
  ok('в сведениях есть «Что»', one.spec.includes('Что'), one.spec.join(', '));
  ok('назад ведёт в раздел', one.back === 'visits.html', one.back);
  ok('есть кнопка «скачать»', one.download);
  ok('снимок открывается лупой', one.lupa);

  // Ссылка на карту появляется, только когда место совпало с музеем
  // из собрания, — проверяем, что она хотя бы никуда не врёт.
  const mapLink = await page.evaluate(() => {
    const a = document.querySelector('.spec-table a[href^="museums.html#museum-"]');
    return a ? a.getAttribute('href') : '';
  });
  if (mapLink) {
    const museums = fs.readFileSync(path.join(DOCS, 'museums.html'), 'utf8');
    ok('ссылка на карту ведёт к настоящей метке',
      museums.includes('id="' + mapLink.split('#')[1] + '"'), mapLink);
  }

  ok('нет ошибок JS', errs.length === 0, errs.join(' | '));

  // ---------- телефон ----------
  const m = await ctx.newPage();
  await m.setViewportSize({ width: 390, height: 844 });
  await m.goto(f('visits.html'));
  await m.waitForTimeout(300);
  const over = await m.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok('на телефоне нет горизонтальной прокрутки', over <= 1, over + 'px');
  const fits = await m.evaluate(() => {
    const box = document.querySelector('.visit-switch').getBoundingClientRect();
    return box.width <= document.documentElement.clientWidth + 1;
  });
  ok('переключатель помещается в экран', fits);
  await m.close();

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ ПОСЕЩЕНИЯ ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
