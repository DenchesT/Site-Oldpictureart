// Кнопка «Поделиться», окно входа и избранное без аккаунта.
//
// Обе части раньше молча ломались, и заметить это было нечем: «Поделиться»
// на компьютере просто копировала адрес без единого знака, что нажатие
// принято, а окно входа показывало коды Firebase по-английски и выпускало
// клавиатуру на страницу под собой.
//
// Сети в проверках нет, и это нарочно: так видно, что страница работает
// и без облака — отметки ложатся в память браузера.
const { chromium } = require('playwright');
const path = require('path');
const DOCS = path.join(__dirname, '..', 'docs');

function pickPost() {
  const meta = JSON.parse(require('fs').readFileSync(
    path.join(__dirname, '..', 'posts_meta.json'), 'utf8'));
  return meta.find(p => p.description && p.creation_year) || meta[0];
}
const POST = pickPost().filename;
const f = n => 'file://' + DOCS + '/' + encodeURIComponent(n).replace(/%2F/g, '/');
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
  await page.waitForTimeout(600);

  // ---------------------------------------------------------- поделиться
  await page.click('[data-share-btn]');
  await page.waitForTimeout(150);

  ok('список «Поделиться» открывается', await page.locator('.share-menu').count() === 1);
  ok('в списке пять пунктов', await page.locator('.share-item').count() === 5,
    String(await page.locator('.share-item').count()));

  const href = await page.getAttribute('.share-item', 'href');
  ok('ссылка построена от canonical, а не от file://',
    href.includes('oldpictureart.ru') || href.includes('github.io'), href.slice(0, 70));
  ok('в ссылку не попал якорь страницы', !href.includes('%23'), href.slice(0, 70));

  ok('фокус переходит в список', await page.evaluate(
    () => document.activeElement.classList.contains('share-item')));
  await page.keyboard.press('ArrowDown');
  ok('стрелки ведут по пунктам',
    await page.evaluate(() => document.activeElement.textContent) === 'ВКонтакте');

  await page.keyboard.press('Escape');
  await page.waitForTimeout(120);
  ok('Escape закрывает список', await page.locator('.share-menu').count() === 0);
  ok('фокус возвращается на кнопку',
    await page.evaluate(() => document.activeElement.hasAttribute('data-share-btn')));

  await page.click('[data-share-btn]');
  await page.waitForTimeout(120);
  // Нарочно у самого края: щелчок по картине открыл бы лупу и перехватил
  // дальнейшие нажатия, и проверка встала бы не на своей ошибке.
  await page.mouse.click(1275, 400);
  await page.waitForTimeout(150);
  ok('щелчок мимо закрывает список', await page.locator('.share-menu').count() === 0);
  ok('щелчок мимо не открыл ничего другого',
    await page.locator('.lupa').count() === 0);

  // ------------------------------------------------------------ окно входа
  // Здесь проверяется только сама рамка окна; путь входа целиком — в
  // test_login.js.
  await page.evaluate(() => showAuthForm());
  await page.waitForTimeout(200);

  ok('окно объявлено диалогом', await page.getAttribute('.auth-modal', 'role') === 'dialog');
  ok('окно модальное для чтения с экрана',
    await page.getAttribute('.auth-modal', 'aria-modal') === 'true');
  ok('поле ошибки объявлено как сообщение',
    await page.getAttribute('#auth-error', 'role') === 'alert');
  ok('ни почты, ни пароля, ни входа через Google',
    await page.locator('.auth-modal input, #google-login-btn, .auth-btn-google').count() === 0);

  await page.evaluate(() => document.getElementById('auth-close-btn').focus());
  await page.keyboard.down('Shift');
  await page.keyboard.press('Tab');
  await page.keyboard.up('Shift');
  ok('клавиатура не уходит из окна на страницу под ним', await page.evaluate(
    () => document.querySelector('.auth-modal').contains(document.activeElement)));

  await page.keyboard.press('Escape');
  await page.waitForTimeout(150);
  ok('Escape закрывает окно входа', await page.locator('.auth-modal').count() === 0);

  // ------------------------------------------------- избранное без аккаунта
  await page.evaluate(() => localStorage.clear());
  const pid = await page.getAttribute('#like-btn', 'data-post-id');

  await page.click('#like-btn');
  await page.waitForTimeout(200);
  ok('отметка ложится в память браузера без входа', await page.evaluate(
    id => JSON.parse(localStorage.getItem('likes') || '{}')[id] === true, pid));
  ok('кнопка отмечена для чтения с экрана',
    await page.getAttribute('#like-btn', 'aria-pressed') === 'true');

  await page.click('#like-btn');
  await page.waitForTimeout(200);
  // Прежняя версия писала liked:false и оставляла запись навсегда.
  ok('снятая отметка удаляется, а не остаётся записью', await page.evaluate(
    id => !(id in JSON.parse(localStorage.getItem('likes') || '{}')), pid));

  // Кнопка «Войти» есть, только если вход настроен (адрес функции и
  // client_id в site_common.py); а если нет — её нет совсем. Оба случая
  // проверяет test_login.js; здесь — что страница не зависит от входа.
  ok('кнопка «Войти» либо работает, либо её нет — не висит мёртвой',
    await page.evaluate(() => !document.getElementById('auth-btn') ||
      (CLOUD.on && typeof document.getElementById('auth-btn').onclick === 'function')));
  ok('Firebase на странице больше нет', await page.evaluate(
    () => typeof firebase === 'undefined' && ![...document.scripts].some(s => /firebase/.test(s.src))));

  ok('нет ошибок JS', errs.length === 0, errs.join(' | '));

  // ------------------------------------------------------------- телефон
  const m = await browser.newContext({
    viewport: { width: 390, height: 780 }, isMobile: true, hasTouch: true
  });
  const mp = await m.newPage();
  await mp.goto(f(POST));
  await mp.waitForTimeout(600);
  // На телефоне открывается системное меню; чтобы проверить свой список,
  // делаем вид, что системного нет.
  await mp.evaluate(() => {
    try { Object.defineProperty(navigator, 'share', { value: undefined, configurable: true }); }
    catch (e) {}
  });
  await mp.click('[data-share-btn]');
  await mp.waitForTimeout(200);
  const box = await mp.locator('.share-menu').boundingBox();
  ok('на телефоне список ложится полосой снизу',
    box && box.width > 380 && box.y + box.height > 760,
    box ? `${Math.round(box.width)}×${Math.round(box.height)} @ y=${Math.round(box.y)}` : 'нет');
  await m.close();

  await browser.close();
  const fails = results.filter(r => !r.pass);
  console.log('\n====== ПОДЕЛИТЬСЯ И ВХОД ======');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
