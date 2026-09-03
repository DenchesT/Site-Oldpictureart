const { chromium } = require('playwright');
const DOCS = require('path').join(__dirname, '..', 'docs');
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
const f = n => 'file://' + DOCS + '/' + encodeURIComponent(n).replace(/%2F/g, '/');

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

(async () => {
  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message.slice(0, 140)));
  await page.goto(f(POST));
  await page.waitForTimeout(800);

  ok('ссылка на оригинал осталась настоящей',
    await page.locator('a.painting-link').first().evaluate(a => /\.(jpe?g|png|webp)$/i.test(a.getAttribute('href')) || a.getAttribute('href').length > 4),
    await page.locator('a.painting-link').first().getAttribute('href'));

  ok('лупа заранее не построена', (await page.locator('.lupa').count()) === 0);

  // ---------- кнопка «скачать» ----------
  const dl = await page.evaluate(() => {
    const a = document.querySelector('.post-topbar-right a.topbar-btn[download]');
    if (!a) return null;
    const cs = getComputedStyle(a);
    const others = [...document.querySelectorAll('.post-topbar-right .topbar-btn')]
      .filter(x => x.offsetParent !== null);
    const h = others.map(x => Math.round(x.getBoundingClientRect().height));
    return {
      href: a.getAttribute('href'),
      name: a.getAttribute('download'),
      label: a.getAttribute('aria-label'),
      icon: !!a.querySelector('.icon-download'),
      deco: cs.textDecorationLine,
      sameHeight: new Set(h).size === 1,
      sameColor: cs.color === getComputedStyle(others[0]).color,
      iconPainted: a.querySelector('.icon-download')
        && getComputedStyle(a.querySelector('.icon-download')).backgroundColor === cs.color,
    };
  });
  ok('кнопка «скачать» есть в ряду', !!dl);
  ok('ведёт на оригинал', dl && /hires|images\//.test(dl.href), dl && dl.href);
  ok('файл получит осмысленное имя', dl && /^[^/]+\.(jpe?g|png|webp)$/i.test(dl.name) && new RegExp(SURNAME).test(dl.name), dl && dl.name);
  ok('подписана для скринридера', dl && dl.label === 'Скачать картину', dl && dl.label);
  ok('значок на месте и красится темой', dl && dl.icon && dl.iconPainted);
  ok('выглядит как остальные кнопки', dl && dl.deco === 'none' && dl.sameHeight && dl.sameColor,
    dl && `подчёркивание ${dl.deco}, одинаковая высота ${dl.sameHeight}`);

  await page.click('a.painting-link');
  await page.waitForTimeout(500);

  ok('лупа открылась', await page.locator('.lupa').isVisible());
  ok('это диалог для скринридера',
    (await page.locator('.lupa').getAttribute('role')) === 'dialog' &&
    (await page.locator('.lupa').getAttribute('aria-modal')) === 'true');
  ok('подпись заполнена', (await page.locator('.lupa-caption b').textContent()).includes(SURNAME),
    await page.locator('.lupa-caption b').textContent());
  ok('фон под лупой не прокручивается',
    (await page.evaluate(() => document.body.style.overflow)) === 'hidden');
  ok('фокус на кнопке закрытия',
    (await page.evaluate(() => document.activeElement.getAttribute('data-act'))) === 'close');

  const fit = await page.evaluate(() => {
    const i = document.querySelector('.lupa-img');
    const t = getComputedStyle(i).transform;
    const m = new DOMMatrix(t);
    const st = document.querySelector('.lupa-stage').getBoundingClientRect();
    const r = i.getBoundingClientRect();
    return { scale: m.a, w: r.width, h: r.height, sw: st.width, sh: st.height, pct: document.querySelector('.lupa-scale').textContent };
  });
  ok('картина вписана в окно', fit.w <= fit.sw + 1 && fit.h <= fit.sh + 1,
    `${Math.round(fit.w)}×${Math.round(fit.h)} в ${Math.round(fit.sw)}×${Math.round(fit.sh)}`);
  ok('масштаб подписан', /%$/.test(fit.pct), fit.pct);
  ok('уменьшать дальше некуда', await page.locator('[data-act="out"]').isDisabled());

  // кнопка «скачать» внутри лупы
  const lupaSave = await page.evaluate(() => {
    const a = document.querySelector('.lupa [data-act="save"]');
    if (!a) return null;
    return { href: a.getAttribute('href'), name: a.getAttribute('download'),
             icon: !!a.querySelector('.icon-download'),
             label: a.getAttribute('aria-label') };
  });
  ok('в лупе есть «скачать»', !!lupaSave);
  ok('лупа отдаёт оригинал', lupaSave && /hires|images\//.test(lupaSave.href), lupaSave && lupaSave.href);
  ok('имя файла осмысленное и в лупе', lupaSave && new RegExp(SURNAME).test(lupaSave.name), lupaSave && lupaSave.name);
  ok('у кнопки в лупе значок и подпись', lupaSave && lupaSave.icon && lupaSave.label === 'Скачать картину');

  // щелчок по ней не закрывает лупу.
  // Переход гасим сами: иначе браузер уйдёт на файл и проверять станет нечего.
  await page.evaluate(() => {
    const a = document.querySelector('.lupa [data-act="save"]');
    a.addEventListener('click', e => e.preventDefault(), { once: true });
    a.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
  await page.waitForTimeout(250);
  ok('скачивание не закрывает лупу', await page.locator('.lupa').isVisible());

  // увеличение кнопкой
  await page.click('[data-act="in"]');
  await page.waitForTimeout(300);
  const zoomed = await page.evaluate(() => new DOMMatrix(getComputedStyle(document.querySelector('.lupa-img')).transform).a);
  ok('кнопка увеличивает', zoomed > fit.scale * 1.2, `${fit.scale.toFixed(3)} → ${zoomed.toFixed(3)}`);

  // колесо увеличивает у курсора
  await page.mouse.move(500, 500);
  await page.mouse.wheel(0, -240);
  await page.waitForTimeout(300);
  const wheeled = await page.evaluate(() => new DOMMatrix(getComputedStyle(document.querySelector('.lupa-img')).transform).a);
  ok('колесо увеличивает', wheeled > zoomed, `${zoomed.toFixed(3)} → ${wheeled.toFixed(3)}`);

  // перетаскивание сдвигает
  const before = await page.evaluate(() => { const m = new DOMMatrix(getComputedStyle(document.querySelector('.lupa-img')).transform); return { x: m.e, y: m.f }; });
  await page.mouse.move(600, 500);
  await page.mouse.down();
  await page.mouse.move(500, 430, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(250);
  const after = await page.evaluate(() => { const m = new DOMMatrix(getComputedStyle(document.querySelector('.lupa-img')).transform); return { x: m.e, y: m.f }; });
  ok('перетаскивание двигает картину', Math.abs(after.x - before.x) > 10 || Math.abs(after.y - before.y) > 10,
    `сдвиг ${Math.round(after.x - before.x)}, ${Math.round(after.y - before.y)}`);

  // «вписать» возвращает к исходному
  await page.click('[data-act="fit"]');
  await page.waitForTimeout(400);
  const back = await page.evaluate(() => new DOMMatrix(getComputedStyle(document.querySelector('.lupa-img')).transform).a);
  ok('«вписать» возвращает масштаб', Math.abs(back - fit.scale) < 0.01, `${back.toFixed(3)} против ${fit.scale.toFixed(3)}`);

  // картину нельзя утащить за край
  await page.click('[data-act="in"]');
  await page.waitForTimeout(250);
  await page.mouse.move(600, 500);
  await page.mouse.down();
  await page.mouse.move(1200, 880, { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(250);
  const edge = await page.evaluate(() => {
    const r = document.querySelector('.lupa-img').getBoundingClientRect();
    const s = document.querySelector('.lupa-stage').getBoundingClientRect();
    return { left: r.left - s.left, top: r.top - s.top };
  });
  ok('картина не уезжает за край', edge.left <= 1 && edge.top <= 1, `отступ ${Math.round(edge.left)}, ${Math.round(edge.top)}`);

  // клавиатура
  await page.keyboard.press('0');
  await page.waitForTimeout(350);
  const zeroed = await page.evaluate(() => new DOMMatrix(getComputedStyle(document.querySelector('.lupa-img')).transform).a);
  ok('клавиша 0 вписывает', Math.abs(zeroed - fit.scale) < 0.01);

  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  ok('Escape закрывает', !(await page.locator('.lupa').isVisible()));
  ok('прокрутка страницы вернулась', (await page.evaluate(() => document.body.style.overflow)) === '');
  ok('фокус вернулся на картину',
    (await page.evaluate(() => document.activeElement.classList.contains('painting-link'))));

  ok('нет ошибок JS', errs.length === 0, errs.join(' | '));

  // Ctrl+клик по-прежнему отдаёт оригинал браузеру
  const opened = await page.evaluate(() => {
    const a = document.querySelector('a.painting-link');
    const ev = new MouseEvent('click', { bubbles: true, cancelable: true, ctrlKey: true });
    const prevented = !a.dispatchEvent(ev);
    return { prevented, lupaOpen: !!document.querySelector('.lupa:not([hidden])') };
  });
  ok('Ctrl+клик открывает оригинал, а не лупу', !opened.prevented && !opened.lupaOpen);

  await ctx.close();

  // телефон: щипок и открытие
  const m = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const mp = await m.newPage();
  await mp.goto(f(POST));
  await mp.waitForTimeout(700);
  await mp.locator('a.painting-link').first().dispatchEvent('click');
  await mp.waitForTimeout(500);
  ok('на телефоне лупа открывается', await mp.locator('.lupa').isVisible());
  const mfit = await mp.evaluate(() => {
    const r = document.querySelector('.lupa-img').getBoundingClientRect();
    const s = document.querySelector('.lupa-stage').getBoundingClientRect();
    return r.width <= s.width + 1 && r.height <= s.height + 1;
  });
  ok('на телефоне картина вписана', mfit);
  const over = await mp.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok('на телефоне нет горизонтальной прокрутки', over <= 1, `перелив ${over}px`);
  const bar = await mp.evaluate(() => {
    const row = document.querySelector('.post-topbar-right');
    const r = row.getBoundingClientRect();
    return { fits: r.right <= window.innerWidth + 1, dl: !!row.querySelector('a.topbar-btn[download]') };
  });
  ok('на телефоне ряд кнопок помещается', bar.fits);
  ok('на телефоне «скачать» на месте', bar.dl);
  await m.close();

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n============ ЛУПА ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
