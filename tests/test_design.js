const { chromium } = require('playwright');
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
const SURNAME = PICKED.artist.split(' ').pop();
// Подборка по тегу берётся с диска: теги меняются вместе с собранием.
const SOME_TAG = require('fs').readdirSync(require('path').join(__dirname, '..', 'docs'))
  .find(x => x.startsWith('tag-') && x.endsWith('.html')) || 'index.html';
const PAGES = ['index.html', POST, SOME_TAG, 'quiz.html', 'timeline.html', 'museums.html', '404.html'];

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

(async () => {
  const browser = await chromium.launch(LAUNCH);

  // ---------- переключатель «опись / плитки» ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(f('index.html'));
    await page.waitForTimeout(600);

    ok('по умолчанию опись', await page.locator('#cards').evaluate(el => el.classList.contains('list')));
    ok('у записей есть каталожный номер', await page.locator('.card-no').first().textContent().then(t => /^\d+$/.test(t.trim())));
    ok('у записей есть таблица сведений', await page.locator('.card-facts div').count() > 0);

    // рамка миниатюры должна облегать картину: пустое место внутри неё
    // читается как светлые полосы сверху и снизу.
    const thumbs = await page.evaluate(() => {
      return [...document.querySelectorAll('.grid.list .card-img')].slice(0, 20).map(box => {
        const img = box.querySelector('img');
        if (!img || !img.complete || !img.naturalWidth) return null;
        const b = box.getBoundingClientRect(), i = img.getBoundingClientRect();
        if (i.height < 1) return null;
        return { dh: Math.abs(b.height - i.height), dw: Math.abs(b.width - i.width), w: Math.round(i.width) };
      }).filter(Boolean);
    });
    ok('в описи вокруг миниатюр нет пустых полос',
      thumbs.length > 5 && thumbs.every(t => t.dh <= 2),
      `${thumbs.filter(t => t.dh > 2).length} из ${thumbs.length} с полосами`);
    ok('узкие работы не растянуты на всю колонку',
      thumbs.some(t => t.w < 130), `минимальная ширина ${Math.min(...thumbs.map(t => t.w))}px`);

    // в описи сведения идут столбцом с ярлыками
    const labelShown = await page.locator('.card-facts span').first().isVisible();
    ok('в описи ярлыки полей видны', labelShown);

    await page.click('#view-grid');
    await page.waitForTimeout(300);
    ok('переключение на плитки', await page.locator('#cards').evaluate(el => !el.classList.contains('list')));
    ok('в плитках ярлыки скрыты', !(await page.locator('.card-facts span').first().isVisible()));
    ok('aria-pressed переставлен', (await page.locator('#view-grid').getAttribute('aria-pressed')) === 'true');

    await page.reload();
    await page.waitForTimeout(700);
    ok('вид запоминается после перезагрузки', await page.locator('#cards').evaluate(el => !el.classList.contains('list')));

    await page.click('#view-list');
    await page.waitForTimeout(300);
    ok('возврат к описи', await page.locator('#cards').evaluate(el => el.classList.contains('list')));

    // фильтры продолжают работать в обоих видах
    const total = await page.locator('.card').count();
    await page.fill('#search', 'левитан');
    await page.waitForTimeout(400);
    const vis = await page.locator('.card:not([hidden])').count();
    ok('поиск работает в описи', vis > 0 && vis < total, `${vis} из ${total}`);
    await ctx.close();
  }

  // ---------- каталожный номер один и тот же на главной и на теге ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(f('index.html'));
    await page.waitForTimeout(500);
    // Берём первую работу со страницы тега и ищем её же на главной:
    // номер обязан совпасть, иначе он ничего не значит.
    await page.goto(f(SOME_TAG));
    await page.waitForTimeout(500);
    const onTag = await page.evaluate(() => {
      const a = document.querySelector('.card .card-link');
      const c = a && a.closest('.card');
      return c ? { href: a.getAttribute('href'), no: c.querySelector('.card-no').textContent.trim() } : null;
    });
    await page.goto(f('index.html'));
    await page.waitForTimeout(600);
    const onIndex = await page.evaluate(href => {
      const a = [...document.querySelectorAll('.card .card-link')]
        .find(x => x.getAttribute('href') === href);
      const c = a && a.closest('.card');
      return c ? c.querySelector('.card-no').textContent.trim() : null;
    }, onTag && onTag.href);
    ok('номер работы совпадает на главной и на странице тега', onTag && onIndex && onIndex === onTag.no, `${onTag && onTag.no} / ${onIndex}`);
    await ctx.close();
  }

  // ---------- страница картины: сведения отдельной таблицей ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await ctx.newPage();
    await page.goto(f(POST));
    await page.waitForTimeout(700);
    ok('две колонки на широком экране',
      (await page.locator('.post-layout').evaluate(el => getComputedStyle(el).gridTemplateColumns)).split(' ').length === 2);
    ok('таблица сведений на месте', await page.locator('.spec-table div').count() >= 4);
    ok('боковая колонка закреплена',
      (await page.locator('.post-aside').evaluate(el => getComputedStyle(el).position)) === 'sticky');
    const measure = await page.locator('.description p').first().evaluate(el => el.getBoundingClientRect().width);
    ok('строка текста не слишком длинная', measure < 760, Math.round(measure) + 'px');
    await ctx.close();
  }

  // ---------- шрифты подключены ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.goto(f('index.html'));
    await page.waitForTimeout(500);
    const ff = await page.evaluate(() => ({
      body: getComputedStyle(document.body).fontFamily,
      data: getComputedStyle(document.querySelector('.card-no')).fontFamily,
    }));
    ok('текст набран Old Standard TT', /Old Standard TT/.test(ff.body), ff.body.slice(0, 40));
    ok('данные набраны IBM Plex Mono', /IBM Plex Mono/.test(ff.data), ff.data.slice(0, 40));
    await ctx.close();
  }

  // ---------- ширины ----------
  for (const w of [320, 375, 414, 768, 1024, 1280, 1600]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: 900 }, isMobile: w < 900, hasTouch: w < 900 });
    const page = await ctx.newPage();
    for (const p of PAGES) {
      await page.goto(f(p));
      await page.waitForTimeout(350);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      ok(`${w}px без горизонтальной прокрутки: ${p}`, over <= 1, `перелив ${over}px`);
    }
    await ctx.close();
  }

  // ---------- контраст текста к фону в обеих темах ----------
  for (const theme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await ctx.newPage();
    await page.addInitScript(t => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme);
    await page.goto(f('index.html'));
    await page.waitForTimeout(600);
    const c = await page.evaluate(() => {
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
        muted: ratio(getComputedStyle(document.querySelector('.card-museum')).color, bg),
      };
    });
    ok(`${theme}: основной текст читаем`, c.text >= 7, c.text.toFixed(1) + ':1');
    ok(`${theme}: приглушённый текст читаем`, c.muted >= 4.5, c.muted.toFixed(1) + ':1');
    await ctx.close();
  }

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ ОФОРМЛЕНИЕ «КАТАЛОГ» ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
