// Вёрстка служебных страниц, найденная при осмотре сайта 23.10.2026:
//   • 404: подвал стоял сбоку от сообщения, а не под ним;
//   • указатель: шапка главной (во всю ширину, вразбивку) по ошибке
//     доставалась и указателю — «Собрание», заголовок и подпись в ряд;
//   • карта, хронология, квиз: шапка без полей и линии, не как везде;
//   • статистика на телефоне: график прокручивался вбок и показывал
//     пустые 1610–1790-е, а основное было за краем;
//   • длинный хэштег музея раздвигал страницу вбок на телефоне.
// Запуск: node tests/test_layout.js
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const DOCS = path.join(__dirname, '..', 'docs');
const f = n => 'file://' + DOCS + '/' + encodeURIComponent(n);
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

(async () => {
  const browser = await chromium.launch(LAUNCH);
  const ctxOf = (w, h, mob) => browser.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob });

  for (const [label, w, h, mob] of [['компьютер', 1280, 800, false], ['телефон', 390, 760, true]]) {
    const ctx = await ctxOf(w, h, mob);
    const page = await ctx.newPage();

    // ---------- 404 ----------
    await page.goto(f('404.html'));
    const e = await page.evaluate(() => {
      const box = document.querySelector('.error-box').getBoundingClientRect();
      const foot = document.querySelector('.site-footer').getBoundingClientRect();
      return { boxBottom: box.bottom, footTop: foot.top, boxMid: (box.left + box.right) / 2, W: innerWidth, footW: foot.width };
    });
    ok(`404 (${label}): подвал под сообщением, а не сбоку`, e.footTop >= e.boxBottom - 1 && e.footW > e.W * 0.8, JSON.stringify(e));
    ok(`404 (${label}): сообщение посередине`, Math.abs(e.boxMid - e.W / 2) < 8, JSON.stringify(e));

    // ---------- указатель ----------
    await page.goto(f('ukazatel.html'));
    const u = await page.evaluate(() => {
      const r = s => document.querySelector(s).getBoundingClientRect();
      const eb = r('.artist-head .eyebrow'), h1 = r('.artist-head h1'), lede = r('.idx-lede');
      return { ebBottom: eb.bottom, h1Top: h1.top, ebLeft: eb.left, h1Left: h1.left, ledeTop: lede.top, h1Bottom: h1.bottom };
    });
    ok(`указатель (${label}): «Собрание» над заголовком, подпись под ним, всё с левого края`,
       u.ebBottom <= u.h1Top + 1 && u.ledeTop >= u.h1Bottom - 1 && Math.abs(u.ebLeft - u.h1Left) < 2, JSON.stringify(u));

    // ---------- шапки как у остальных ----------
    await page.goto(f('afisha.html'));
    const ref = await page.evaluate(() => {
      const t = document.querySelector('.tag-topbar'), b = t.querySelector('.back').getBoundingClientRect();
      return { left: Math.round(b.left), line: getComputedStyle(t).borderBottomStyle };
    });
    for (const [file, sel] of [['museums.html', '.map-topbar'], ['timeline.html', '.timeline-topbar'], ['quiz.html', '.quiz-topbar']]) {
      await page.goto(f(file));
      const t = await page.evaluate(s => {
        const el = document.querySelector(s), b = el.querySelector('.back').getBoundingClientRect();
        return { left: Math.round(b.left), line: getComputedStyle(el).borderBottomStyle };
      }, sel);
      ok(`${file} (${label}): шапка с теми же полями и линией, что у остальных страниц`,
         Math.abs(t.left - ref.left) <= 2 && t.line === 'solid', `${JSON.stringify(t)} / ждали ${JSON.stringify(ref)}`);
    }

    // ---------- без прокрутки вбок ----------
    const longTag = fs.readdirSync(DOCS).filter(x => x.startsWith('tag-') && x.endsWith('.html'))
      .sort((a, b) => b.length - a.length)[0];
    for (const file of [longTag, 'stats.html', 'ukazatel.html', '404.html']) {
      await page.goto(f(file));
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      ok(`${file} (${label}): страница не шире экрана`, over <= 1, `шире на ${over}px`);
    }

    // ---------- график десятилетий целиком ----------
    await page.goto(f('stats.html'));
    const c = await page.evaluate(() => { const ch = document.querySelector('.dec-chart'); return ch ? { sw: ch.scrollWidth, cw: ch.clientWidth } : null; });
    ok(`статистика (${label}): график десятилетий виден целиком, без прокрутки`, c && c.sw <= c.cw + 1, JSON.stringify(c));
    await ctx.close();
  }

  // ---------- происхождение ----------
  {
    const ctx = await ctxOf(1280, 800, false);
    const page = await ctx.newPage();
    const withHist = fs.readdirSync(DOCS).find(x => x.endsWith('.html')
      && fs.readFileSync(path.join(DOCS, x), 'utf8').includes('class="history"'));
    if (withHist) {
      await page.goto(f(withHist));
      const hs = await page.evaluate(() => {
        const l = document.querySelector('.history ol, .history ul');
        return { tag: l.tagName, first: l.querySelector('li').textContent.trim() };
      });
      ok('происхождение: нумерует список, в тексте нет «1)»', hs.tag === 'OL' && !/^\d+[).]/.test(hs.first), JSON.stringify(hs));
    }
    await ctx.close();
  }

  await browser.close();
  console.log('\n====== ВЁРСТКА СЛУЖЕБНЫХ СТРАНИЦ ======');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra && !r.pass ? '  — ' + r.extra : ''}`);
  const fails = results.filter(r => !r.pass).length;
  console.log(`\nВсего: ${results.length}, провалено: ${fails}`);
  process.exit(fails ? 1 : 0);
})();
