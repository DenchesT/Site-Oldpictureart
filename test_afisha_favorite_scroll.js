// Проверка на настоящем docs/afisha.html в Playwright.
// После python rebuild_pages.py --offline: node test_afisha_favorite_scroll.js
'use strict';
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const target = path.resolve(__dirname, 'docs', 'afisha.html');
if (!fs.existsSync(target)) {
  console.error('Не найден docs/afisha.html. Сначала запустите python rebuild_pages.py --offline');
  process.exit(2);
}
const url = 'file:///' + target.replace(/\\/g, '/');
(async function () {
  const opt = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};
  const browser = await chromium.launch(opt);
  try {
    for (const width of [390, 1366]) {
      const ctx = await browser.newContext({viewport:{width,height:844}});
      const page = await ctx.newPage();
      try {
        await page.goto(url, {waitUntil:'domcontentloaded'});
        await page.waitForFunction(() => document.querySelectorAll('.afisha-item[data-phase]').length > 20);
        await page.locator('.afisha-status-switch [data-status="all"]').click();
        const rows = page.locator('.afisha-item:not([hidden])');
        const count = await rows.count();
        if (count < 20) throw new Error(`Недостаточно выставок для теста: ${count}`);
        const star = rows.nth(Math.min(30, count - 2)).locator('.afisha-favorite');
        await star.scrollIntoViewIfNeeded();
        const before = await star.evaluate(el => ({scroll:window.scrollY, top:el.getBoundingClientRect().top,
          pressed:el.getAttribute('aria-pressed')}));
        if (before.scroll < 100) throw new Error('Тест не удалось прокрутить до удалённой выставки');
        await star.click();
        await page.waitForTimeout(150);
        const after = await star.evaluate(el => ({scroll:window.scrollY, top:el.getBoundingClientRect().top,
          pressed:el.getAttribute('aria-pressed')}));
        if (before.pressed === after.pressed) throw new Error('Звёздочка не изменила состояние');
        const shift = Math.abs(after.top - before.top);
        const scrollShift = Math.abs(after.scroll - before.scroll);
        if (shift > 8 || scrollShift > 32 || after.scroll < 100) throw new Error(`Позиция изменилась: y=${scrollShift}, top=${shift}`);
        console.log(`OK ${width}px: отметка сохранена, позиция выставки на экране не изменилась`);
      } finally {
        await ctx.close();
      }
    }
  } finally { await browser.close(); }
})().catch(e => { console.error('FAIL:', e.message); process.exitCode = 1; });
