// Страницы художников, указатель, статистика и блок «рядом в собрании».
const { chromium } = require('playwright');
const fs = require('fs');
const DOCS = require('path').join(__dirname, '..', 'docs');
const f = n => 'file://' + DOCS + '/' + encodeURIComponent(n).replace(/%2F/g, '/');
// Страница работы для проверок выбирается из базы, а не задана жёстко:
// конкретный пост могут удалить из канала, и проверки посыпались бы.
function pickPost() {
  const meta = JSON.parse(require('fs').readFileSync(
    require('path').join(__dirname, '..', 'posts_meta.json'), 'utf8'));
  const good = meta.filter(p => (p.hires || []).length && p.description && p.creation_year);
  return good.find(p => /Левитан/.test(p.artist)) || good[0] || meta[0];
}
const PICKED = pickPost();
const POST = PICKED.filename;

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};
const SURNAME = PICKED.artist.split(' ').pop();
// Берём художника с наибольшим числом работ — у него точно есть
// что показать, и он не исчезнет из собрания первым.
const _meta = JSON.parse(require('fs').readFileSync(require('path').join(__dirname, '..', 'posts_meta.json'), 'utf8'));
const _byArtist = {};
for (const p of _meta) if (p.artist) (_byArtist[p.artist.trim()] = _byArtist[p.artist.trim()] || []).push(p);
const TOP_ARTIST = Object.entries(_byArtist).sort((a, b) => b[1].length - a[1].length)[0];
const ARTIST_NAME = TOP_ARTIST[0];
const ARTIST_COUNT = TOP_ARTIST[1].length;
// Имя файла страницы художника собирается питоном, поэтому не гадаем,
// а находим ту страницу, в заголовке которой стоит нужное имя.
const ARTIST = require('fs').readdirSync(require('path').join(__dirname, '..', 'docs'))
  .filter(x => x.startsWith('artist-') && x.endsWith('.html'))
  .find(x => require('fs').readFileSync(require('path').join(__dirname, '..', 'docs', x), 'utf8')
    .includes('<h1>' + ARTIST_NAME + '</h1>'));

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

(async () => {
  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 950 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message.slice(0, 120)));

  // ---------- сколько страниц вообще сгенерировано ----------
  const files = fs.readdirSync(DOCS);
  const artistPages = files.filter(x => x.startsWith('artist-') && x.endsWith('.html'));
  ok('страницы художников созданы', artistPages.length >= 60, `${artistPages.length} шт.`);
  ok('указатель и статистика на месте',
    files.includes('ukazatel.html') && files.includes('stats.html'));

  // ---------- страница художника ----------
  await page.goto(f(ARTIST));
  await page.waitForTimeout(600);
  const art = await page.evaluate(() => ({
    h1: document.querySelector('h1').textContent.trim(),
    cards: document.querySelectorAll('.card').length,
    years: [...document.querySelectorAll('.card-facts div')]
      .filter(d => d.querySelector('span').textContent.trim() === 'Год')
      .map(d => +d.querySelector('b').textContent.trim()),
    nos: [...document.querySelectorAll('.card-no')].map(x => x.textContent.trim()),
    museums: document.querySelectorAll('.post-aside .plain-list li').length,
    facts: [...document.querySelectorAll('.artist-facts div')].map(d => d.querySelector('span').textContent.trim()),
    firstHead: document.querySelector('.card-artist a').textContent.trim(),
    hasTitleLine: !!document.querySelector('.card-title'),
  }));
  ok('заголовок — имя художника', art.h1.length > 3, art.h1);
  ok('все работы художника собраны', art.cards === ARTIST_COUNT, `${art.cards} из ${ARTIST_COUNT}`);
  ok('работы по возрастанию годов',
    art.years.every((y, i) => i === 0 || art.years[i - 1] <= y), art.years.join(', '));
  ok('каталожные номера проставлены', art.nos.every(n => /^\d+$/.test(n)), art.nos.join(' '));
  ok('в карточке заголовок — название работы, а не имя',
    art.firstHead !== 'Альфред Сислей' && !art.hasTitleLine, art.firstHead);
  ok('сведения о художнике заполнены',
    art.facts.includes('Годы') && art.facts.includes('Работ'), art.facts.join(', '));
  ok('собрания перечислены', art.museums >= 1, `${art.museums}`);

  // номер тот же, что на главной
  const noOnArtist = await page.evaluate(() => {
    const a = [...document.querySelectorAll('.card')]
      .find(c => c.querySelector('.card-link'));
    return a ? { href: a.querySelector('.card-link').getAttribute('href'), no: a.querySelector('.card-no').textContent.trim() } : null;
  });
  await page.goto(f('index.html'));
  await page.waitForTimeout(700);
  const noOnIndex = await page.evaluate(href => {
    const a = [...document.querySelectorAll('.card .card-link')].find(x => x.getAttribute('href') === href);
    return a ? a.closest('.card').querySelector('.card-no').textContent.trim() : null;
  }, noOnArtist && noOnArtist.href);
  ok('номер работы совпадает с главной', noOnArtist && noOnIndex === noOnArtist.no,
    `${noOnArtist && noOnArtist.no} / ${noOnIndex}`);

  // ---------- ссылки с главной и со страницы картины ----------
  const sidebar = await page.evaluate(() => ({
    ukaz: !!document.querySelector('a[href="ukazatel.html"]'),
    stats: !!document.querySelector('a[href="stats.html"]'),
  }));
  ok('с главной есть ссылки на указатель и статистику', sidebar.ukaz && sidebar.stats);

  await page.goto(f(POST));
  await page.waitForTimeout(700);
  const post = await page.evaluate(() => {
    const h1a = document.querySelector('.post-head h1 a');
    const near = document.querySelector('.near');
    return {
      artistLink: h1a && h1a.getAttribute('href'),
      nearCards: near ? near.querySelectorAll('.near-card').length : 0,
      whys: near ? [...near.querySelectorAll('.near-why')].map(x => x.textContent.trim()) : [],
      selfLinked: near ? [...near.querySelectorAll('.near-card')]
        .some(a => decodeURIComponent(a.getAttribute('href')) === decodeURIComponent(location.pathname.split('/').pop())) : false,
    };
  });
  ok('имя художника на странице картины — ссылка',
    (post.artistLink || '').startsWith('artist-'), post.artistLink);
  ok('блок «рядом в собрании» заполнен', post.nearCards > 0 && post.nearCards <= 6, `${post.nearCards} карточек`);
  ok('сама картина в подборку не попала', !post.selfLinked);
  ok('у каждой подсказки есть причина', post.whys.every(w => w.length > 3), post.whys[0]);

  // ---------- указатель ----------
  await page.goto(f('ukazatel.html'));
  await page.waitForTimeout(600);
  const idx = await page.evaluate(() => {
    const cols = [...document.querySelectorAll('.idx-col')];
    const artistCol = cols[0];
    const links = [...artistCol.querySelectorAll('li a')];
    return {
      cols: cols.length,
      titles: cols.map(c => c.querySelector('h2').firstChild.textContent.trim()),
      artists: links.length,
      allArtistLinks: links.every(a => a.getAttribute('href').startsWith('artist-')),
      hasLetters: artistCol.querySelectorAll('.idx-letter').length > 3,
      counted: [...artistCol.querySelectorAll('.idx-n')].every(n => /^\d+$/.test(n.textContent.trim())),
    };
  });
  ok('в указателе четыре раздела', idx.cols === 4, idx.titles.join(' · '));
  ok('художники ведут на свои страницы', idx.allArtistLinks && idx.artists >= 60, `${idx.artists}`);
  ok('есть буквенные разделители', idx.hasLetters);
  ok('у каждой строки есть число работ', idx.counted);

  // ---------- статистика ----------
  await page.goto(f('stats.html'));
  await page.waitForTimeout(600);
  const st = await page.evaluate(() => {
    const fills = [...document.querySelectorAll('.stat-fill')];
    const rows = [...document.querySelectorAll('.stat-row')];
    return {
      tiles: document.querySelectorAll('.stat-tile').length,
      total: document.querySelector('.stat-tile b').textContent.trim(),
      blocks: document.querySelectorAll('.stat-block').length,
      decCols: document.querySelectorAll('.dec-col').length,
      decLabelled: !!document.querySelector('.dec-chart').getAttribute('aria-label'),
      widest: Math.max(...fills.map(x => parseFloat(getComputedStyle(x).width))),
      allNumbersVisible: rows.every(r => /^\d+$/.test(r.querySelector('.stat-n').textContent.trim())),
      zeroWidth: fills.filter(x => parseFloat(getComputedStyle(x).width) < 1).length,
    };
  });
  ok('плитки со сводкой на месте', st.tiles === 5, `${st.tiles}`);
  ok('всего работ посчитано верно', st.total === '81', st.total);
  ok('разделы построены', st.blocks >= 5, `${st.blocks}`);
  ok('столбцы по десятилетиям нарисованы', st.decCols > 20, `${st.decCols} десятилетий`);
  ok('у графика есть подпись для скринридера', st.decLabelled);
  ok('число рядом с каждой полосой', st.allNumbersVisible);
  ok('полосы имеют ненулевую длину', st.zeroWidth === 0, `${st.zeroWidth} пустых`);

  ok('нет ошибок JS ни на одной странице', errs.length === 0, errs.join(' | '));
  await ctx.close();

  // ---------- узкие экраны ----------
  for (const w of [375, 768]) {
    const c = await browser.newContext({ viewport: { width: w, height: 850 }, isMobile: w < 900, hasTouch: w < 900 });
    const p = await c.newPage();
    for (const file of ['ukazatel.html', 'stats.html', ARTIST, POST]) {
      await p.goto(f(file));
      await p.waitForTimeout(400);
      const over = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      ok(`${w}px без горизонтальной прокрутки: ${file.slice(0, 22)}`, over <= 1, `перелив ${over}px`);
    }
    await c.close();
  }

  // ---------- контраст в тёмной теме ----------
  const d = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const dp = await d.newPage();
  await dp.addInitScript(() => { try { localStorage.setItem('theme', 'dark'); } catch (e) {} });
  await dp.goto(f('stats.html'));
  await dp.waitForTimeout(500);
  const dark = await dp.evaluate(() => {
    const lum = s => {
      const [r, g, b] = s.match(/\d+/g).map(Number).map(v => {
        v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4);
      });
      return .2126 * r + .7152 * g + .0722 * b;
    };
    const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + .05) / (y + .05); };
    const bg = getComputedStyle(document.body).backgroundColor;
    return {
      text: ratio(getComputedStyle(document.body).color, bg),
      bar: ratio(getComputedStyle(document.querySelector('.stat-fill')).backgroundColor, bg),
    };
  });
  ok('тёмная тема: текст читаем', dark.text >= 7, dark.text.toFixed(1) + ':1');
  ok('тёмная тема: полоса отличима от фона', dark.bar >= 3, dark.bar.toFixed(1) + ':1');
  await d.close();

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ НОВЫЕ СТРАНИЦЫ ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
