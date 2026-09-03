// Знак сайта, значки для вкладки и телефона, подвал со ссылкой на канал.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const DOCS = require('path').join(__dirname, '..', 'docs');
const f = n => 'file://' + DOCS + '/' + encodeURIComponent(n).replace(/%2F/g, '/');

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

// По одной странице каждого вида. Имена берём с диска, а не наугад:
// подборки по тегам и художникам меняются вместе с собранием.
const someFile = prefix => (fs.readdirSync(DOCS).find(x => x.startsWith(prefix) && x.endsWith('.html')) || '');
const meta = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'posts_meta.json'), 'utf8'));
const PAGES = ['index.html', 'museums.html', 'stats.html', 'ukazatel.html', 'quiz.html',
  'timeline.html', '404.html', someFile('artist-'), someFile('tag-'),
  meta[0].filename].filter(Boolean);

(async () => {
  // ---------- файлы значков ----------
  for (const [file, min] of [['favicon.svg', 100], ['favicon.ico', 300],
                             ['apple-touch-icon.png', 300],
                             ['images/icon-192.png', 300], ['images/icon-512.png', 500],
                             ['images/icon-192-maskable.png', 300], ['images/icon-512-maskable.png', 500]]) {
    const p = path.join(DOCS, file);
    const exists = fs.existsSync(p) && fs.statSync(p).size >= min;
    ok(`файл ${file} на месте`, exists, exists ? fs.statSync(p).size + ' Б' : 'нет');
  }

  const svg = fs.readFileSync(path.join(DOCS, 'favicon.svg'), 'utf8');
  ok('в favicon.svg цвета сайта', /#1f3a6b/.test(svg) && /#c9a35e/.test(svg) && /#f2ede3/.test(svg));
  ok('favicon.svg — квадрат 32×32', /viewBox='0 0 32 32'/.test(svg));

  const mf = JSON.parse(fs.readFileSync(path.join(DOCS, 'manifest.json'), 'utf8'));
  ok('в манифесте четыре значка', mf.icons.length === 4, `${mf.icons.length}`);
  ok('есть значок для маски Android', mf.icons.some(i => i.purpose === 'maskable'));
  ok('цвет манифеста совпадает с сайтом', mf.theme_color === '#eceef1', mf.theme_color);

  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message.slice(0, 120)));

  // ---------- ссылки в <head> и подвал на каждой странице ----------
  let missingHead = [], missingFooter = [], missingTg = [];
  for (const name of PAGES) {
    await page.goto(f(name));
    await page.waitForTimeout(250);
    const st = await page.evaluate(() => ({
      svg: !!document.querySelector('link[rel="icon"][type="image/svg+xml"]'),
      ico: !!document.querySelector('link[rel="icon"][href="favicon.ico"]'),
      apple: !!document.querySelector('link[rel="apple-touch-icon"]'),
      manifest: !!document.querySelector('link[rel="manifest"]'),
      footer: !!document.querySelector('.site-footer'),
      tg: !!document.querySelector('.site-footer a[href*="t.me/oldpictureart"]'),
      dataUriIcon: !!document.querySelector('link[rel="icon"][href^="data:"]'),
    }));
    if (!(st.svg && st.ico && st.apple && st.manifest) || st.dataUriIcon) missingHead.push(name);
    if (!st.footer) missingFooter.push(name);
    if (!st.tg) missingTg.push(name);
  }
  ok('значки объявлены на всех страницах', missingHead.length === 0, missingHead.join(', '));
  ok('подвал на всех страницах', missingFooter.length === 0, missingFooter.join(', '));
  ok('ссылка на канал в подвале везде', missingTg.length === 0, missingTg.join(', '));

  // ---------- знак в шапке ----------
  await page.goto(f('index.html'));
  await page.waitForTimeout(700);
  const logoLight = await page.evaluate(() => {
    const el = document.querySelector('.icon-logo');
    if (!el) return null;
    const bg = getComputedStyle(el).backgroundImage;
    const r = el.getBoundingClientRect();
    return { bg, w: Math.round(r.width), h: Math.round(r.height) };
  });
  ok('знак в шапке есть', !!logoLight);
  ok('знак — не старый синий квадрат', logoLight && !/0366d6/.test(logoLight.bg),
    logoLight && (/1f3a6b/.test(logoLight.bg) ? 'цвета сайта' : logoLight.bg.slice(0, 60)));
  ok('знак заметного размера', logoLight && logoLight.w >= 24 && logoLight.h >= 24,
    logoLight && `${logoLight.w}×${logoLight.h}`);

  // ---------- канал в сайдбаре ----------
  const side = await page.evaluate(() => {
    const a = document.querySelector('.sidebar-section a[href*="t.me/oldpictureart"]');
    if (!a) return null;
    const nav = [...document.querySelectorAll('.sidebar-section > a.sidebar-title')];
    const left = nav.map(x => Math.round(x.getBoundingClientRect().left));
    return {
      text: a.textContent.trim(),
      blank: a.getAttribute('target') === '_blank' && /noopener/.test(a.getAttribute('rel') || ''),
      icon: getComputedStyle(a, '::before').backgroundImage !== 'none',
      aligned: new Set(left).size === 1,
      count: nav.length,
    };
  });
  ok('канал есть в сайдбаре', !!side, side && side.text);
  ok('канал открывается в новой вкладке безопасно', side && side.blank);
  ok('у канала есть свой значок', side && side.icon);
  ok('канал выровнен с остальными разделами', side && side.aligned, side && `${side.count} пунктов`);

  ok('нет ошибок JS', errs.length === 0, errs.join(' | '));
  await ctx.close();

  // ---------- тёмная тема: знак перекрашивается ----------
  const d = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const dp = await d.newPage();
  await dp.addInitScript(() => { try { localStorage.setItem('theme', 'dark'); } catch (e) {} });
  await dp.goto(f('index.html'));
  await dp.waitForTimeout(600);
  const logoDark = await dp.evaluate(() => getComputedStyle(document.querySelector('.icon-logo')).backgroundImage);
  ok('в тёмной теме знак другой', logoDark !== (logoLight && logoLight.bg),
    /3a5c96/.test(logoDark) ? 'поле светлее' : logoDark.slice(0, 50));
  const footDark = await dp.evaluate(() => {
    const lum = s => {
      const [r, g, b] = s.match(/\d+/g).map(Number).map(v => {
        v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4);
      });
      return .2126 * r + .7152 * g + .0722 * b;
    };
    const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + .05) / (y + .05); };
    const el = document.querySelector('.footer-source');
    return ratio(getComputedStyle(el).color, getComputedStyle(document.body).backgroundColor);
  });
  ok('подвал читается в тёмной теме', footDark >= 4.5, footDark.toFixed(1) + ':1');
  await d.close();

  // ---------- узкий экран ----------
  const m = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
  const mp = await m.newPage();
  await mp.goto(f('index.html'));
  await mp.waitForTimeout(700);
  const over = await mp.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok('375px без горизонтальной прокрутки', over <= 1, `перелив ${over}px`);
  await m.close();

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ ЗНАК, ЗНАЧКИ, ПОДВАЛ ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
