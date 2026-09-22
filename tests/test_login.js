// Вход через Яндекс ID и VK ID и облачное избранное — целиком, без сети.
//
// Страницы сайта раздаёт местный сервер, а вместо облака работает сама
// функция из cloud/auth/index.py (tests/_auth_server.py): подменены только
// ответы Яндекса и VK и база. Так проверяется настоящий путь: кнопка →
// страница Яндекса или VK → auth.html → функция → пропуск → отметки.
//
// Настройки входа в собранных страницах пустые (вход ещё не заведён),
// поэтому сервер на лету вписывает в страницы тестовые client_id.
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const http = require('http');
const net = require('net');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DOCS = path.join(__dirname, '..', 'docs');
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const META = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'posts_meta.json'), 'utf8'));
const POST = META.find(p => p.images && p.images.length).filename;
const PID = String(META.find(p => p.filename === POST).id);
// три картины, которые «уже отметил» другой посетитель, — для «Популярного»
const SEEDED = [PID].concat(META.filter(p => String(p.id) !== PID && p.thumbs && p.thumbs.length).slice(0, 2).map(p => String(p.id)));

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });
const freePort = () => new Promise(r => { const s = net.createServer().listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => r(p)); }); });
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'application/javascript',
                '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.json': 'application/json' };

(async () => {
  const WEB = await freePort(), API = await freePort();
  const BASE = `http://127.0.0.1:${WEB}`;
  const APIURL = `http://127.0.0.1:${API}/`;

  const py = spawn(PY, [path.join(__dirname, '_auth_server.py'), String(API), BASE, SEEDED.join(',')], { stdio: ['ignore', 'pipe', 'inherit'] });
  await new Promise((res, rej) => {
    py.stdout.on('data', d => { if (String(d).includes('READY')) res(); });
    py.on('exit', c => rej(new Error('функция не запустилась: ' + c)));
  });

  const CONFIG = `var CLOUD = {api: '${APIURL}', yandex: 'ya-app', vk: 'vk-app', redirect: '${BASE}/auth.html', vkHost: 'https://id.vk.ru'};`;
  // ?noauth — страница как до настройки входа: все настройки пустые
  const EMPTY = `var CLOUD = {api: '', yandex: '', vk: '', redirect: '${BASE}/auth.html', vkHost: 'https://id.vk.ru'};`;
  const web = http.createServer((req, res) => {
    const noauth = /[?&]noauth\b/.test(req.url);
    let p = decodeURIComponent(req.url.split('?')[0]);
    if (p.endsWith('/')) p += 'index.html';
    const file = path.join(DOCS, p);
    if (!file.startsWith(DOCS) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
    const ext = path.extname(file);
    res.writeHead(200, { 'Content-Type': TYPES[ext] || 'application/octet-stream' });
    if (ext === '.html') {
      res.end(fs.readFileSync(file, 'utf8').replace(/var CLOUD = \{api: '[^']*', yandex: '[^']*', vk: '[^']*',\s*redirect: '[^']*', vkHost: '[^']*'\};/, noauth ? EMPTY : CONFIG));
    } else fs.createReadStream(file).pipe(res);
  });
  await new Promise(r => web.listen(WEB, '127.0.0.1', r));
  const apiLog = () => new Promise(r => http.get(APIURL + '__log', res => { let b = ''; res.on('data', d => b += d); res.on('end', () => r(JSON.parse(b))); }));

  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const seen = { yandex: null, vk: null, external: [] };
  await ctx.route('**/*', route => {
    const u = route.request().url();
    if (u.startsWith(BASE) || u.startsWith(APIURL)) return route.continue();
    if (u.startsWith('https://oauth.yandex.ru/authorize')) {
      seen.yandex = new URL(u);
      return route.fulfill({ status: 302, headers: { Location: `${BASE}/auth.html?code=good&state=${seen.yandex.searchParams.get('state')}` } });
    }
    if (u.startsWith('https://id.vk.ru/authorize')) {
      seen.vk = new URL(u);
      const q = seen.vk.searchParams;
      return route.fulfill({ status: 302, headers: { Location: `${BASE}/auth.html?code=vk-${q.get('code_challenge')}&state=${q.get('state')}&device_id=dev&type=code_v2` } });
    }
    seen.external.push(u);
    return route.abort();
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message.slice(0, 140)));
  await page.addInitScript(() => { try { localStorage.setItem('consent-metrika', 'no'); } catch (e) {} });

  // ------------------------------------------------ до входа
  await page.goto(`${BASE}/${encodeURIComponent(POST)}`);
  await page.waitForTimeout(400);
  const pid = await page.getAttribute('#like-btn', 'data-post-id');
  ok('Firebase и скрипты Google не загружаются', !seen.external.some(u => /firebase|gstatic\.com\/firebasejs/.test(u)),
     seen.external.filter(u => /firebase/.test(u)).join(' '));
  ok('кнопка «Войти» на месте', /Войти/.test(await page.textContent('#auth-btn')));
  ok('у сердечка — сколько человек добавили картину в избранное',
     await page.isVisible('#like-count') && (await page.textContent('#like-count')).trim() === '1',
     await page.textContent('#like-count'));
  ok('число подписано и для чтения с экрана', /добавили: 1/.test(await page.getAttribute('#like-btn', 'aria-label')),
     await page.getAttribute('#like-btn', 'aria-label'));
  // отметка до входа — после входа она должна уехать в облако
  await page.click('#like-btn');
  await page.waitForTimeout(150);

  await page.click('#auth-btn');
  await page.waitForTimeout(200);
  ok('в окне входа — Яндекс ID и VK ID', await page.locator('.auth-yandex').count() === 1 && await page.locator('.auth-vk').count() === 1);
  ok('ни почты, ни пароля, ни Google', await page.locator('input, #google-login-btn').count() === 0);
  ok('фокус — на первой кнопке входа', await page.evaluate(() => document.activeElement.classList.contains('auth-yandex')));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(150);
  ok('Escape закрывает окно', await page.locator('.auth-modal').count() === 0);

  // ------------------------------------------------ вход через Яндекс ID
  await page.click('#auth-btn');
  await page.waitForTimeout(150);
  await Promise.all([page.waitForURL(`${BASE}/${encodeURIComponent(POST)}`, { timeout: 8000 }).catch(() => {}),
                     page.click('.auth-yandex')]);
  await page.waitForTimeout(500);
  const yq = seen.yandex && seen.yandex.searchParams;
  ok('на Яндекс уходит запрос кода для нашего приложения',
     yq && yq.get('response_type') === 'code' && yq.get('client_id') === 'ya-app' &&
     yq.get('redirect_uri') === `${BASE}/auth.html` && (yq.get('state') || '').length >= 32,
     seen.yandex ? seen.yandex.search.slice(0, 120) : 'не было');
  ok('после входа человек вернулся на ту же картину', page.url().endsWith(encodeURIComponent(POST)), page.url());
  ok('на кнопке — имя', /Денис/.test(await page.textContent('#auth-btn')));
  ok('поздоровались один раз', /Вы вошли как Денис/.test(await page.locator('.toast').first().textContent().catch(() => '')));
  const likesAfter = await page.evaluate(() => JSON.parse(localStorage.getItem('likes') || '{}'));
  ok('отметка из облака пришла в браузер', likesAfter['7'] === true, JSON.stringify(likesAfter));
  const log1 = await apiLog();
  ok('отметка, поставленная до входа, ушла в облако',
     log1.some(r => r.action === 'sync' && (r.likes || []).includes(pid)), JSON.stringify(log1.map(r => r.action)));
  ok('сердечко на картине горит', await page.getAttribute('#like-btn', 'aria-pressed') === 'true');
  ok('после входа своя отметка вошла в общее число', (await page.textContent('#like-count')).trim() === '2',
     await page.textContent('#like-count'));

  await page.reload();
  await page.waitForTimeout(400);
  ok('при перезагрузке не здороваемся снова', await page.locator('.toast').count() === 0);

  await page.click('#like-btn');
  await page.waitForTimeout(300);
  const log2 = await apiLog();
  const un = log2.filter(r => r.action === 'unlike').pop();
  ok('снятая отметка сразу видна в числе', (await page.textContent('#like-count')).trim() === '1',
     await page.textContent('#like-count'));
  ok('снятая отметка уходит в облако с пропуском', un && un.post_id === pid && typeof un.token === 'string' && un.token.includes('.'),
     JSON.stringify(un || {}).slice(0, 80));

  // ------------------------------------------------ главная
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(400);
  await page.waitForTimeout(300);
  const pop = await page.evaluate(() => ({
    shown: !document.getElementById('popular').hidden,
    items: [...document.querySelectorAll('#popular-list li a')].map(a => ({
      href: a.getAttribute('href'), n: a.querySelector('.popular-count').textContent.replace(/\D+/g, ''),
      img: !!a.querySelector('img'), name: a.querySelector('.popular-name').textContent })),
  }));
  ok('на главной — «Популярное у посетителей»', pop.shown && pop.items.length >= 3, `${pop.items.length} картин`);
  const seededFiles = SEEDED.map(id => META.find(p => String(p.id) === id).filename);
  ok('в «Популярном» — отмеченные картины со ссылками и картинками',
     pop.items.every(i => seededFiles.concat(['']).includes(i.href) || i.href) &&
     seededFiles.every(f => pop.items.some(i => i.href === f)) && pop.items.every(i => i.img && i.name && +i.n >= 1),
     pop.items.map(i => i.href + ':' + i.n).join(' '));
  await page.fill('#search', 'ренуар');
  await page.waitForTimeout(300);
  ok('во время поиска «Популярное» убирается', await page.evaluate(
     () => getComputedStyle(document.getElementById('popular')).display === 'none'));
  await page.fill('#search', '');
  await page.waitForTimeout(200);
  ok('на главной «Избранное» знает облачную отметку',
     await page.evaluate(() => /\(1\)/.test((document.getElementById('fav-count') || {}).textContent || '')),
     await page.evaluate(() => (document.getElementById('fav-count') || {}).textContent));

  // ------------------------------------------------ окно аккаунта
  await page.goto(`${BASE}/${encodeURIComponent(POST)}`);
  await page.waitForTimeout(300);
  await page.click('#auth-btn');
  await page.waitForTimeout(200);
  ok('в окне аккаунта сказано, через что вошли', /Яндекс ID/.test(await page.textContent('#auth-lede')));
  await page.click('.auth-danger');
  ok('удаление спрашивает второй раз', /Точно/.test(await page.textContent('.auth-danger')));
  await page.click('.auth-danger');
  await page.waitForTimeout(400);
  const log3 = await apiLog();
  ok('после второго нажатия отметки удалены из облака', log3.some(r => r.action === 'delete'));
  ok('и человек вышел', /Войти/.test(await page.textContent('#auth-btn')) &&
     await page.evaluate(() => localStorage.getItem('session') === null));

  // ------------------------------------------------ вход через VK ID
  await page.click('#auth-btn');
  await page.waitForTimeout(150);
  await Promise.all([page.waitForURL(`${BASE}/${encodeURIComponent(POST)}`, { timeout: 8000 }).catch(() => {}),
                     page.click('.auth-vk')]);
  await page.waitForTimeout(500);
  const vq = seen.vk && seen.vk.searchParams;
  ok('в VK уходит запрос с PKCE (S256) и нужными правами',
     vq && vq.get('client_id') === 'vk-app' && vq.get('code_challenge_method') === 'S256' &&
     /^[A-Za-z0-9_-]{43}$/.test(vq.get('code_challenge') || '') && vq.get('scope') === 'vkid.personal_info',
     seen.vk ? seen.vk.search.slice(0, 140) : 'не было');
  ok('VK ID: функция приняла code_verifier — на кнопке имя', /Анна/.test(await page.textContent('#auth-btn')),
     await page.textContent('#auth-btn'));
  const vkLogin = (await apiLog()).filter(r => r.action === 'login' && r.provider === 'vk').pop() || {};
  ok('code_verifier и отпечаток сходятся', vkLogin.code_verifier &&
     crypto.createHash('sha256').update(vkLogin.code_verifier).digest('base64url') === vq.get('code_challenge'));
  ok('code_verifier не уходил в VK вместе с отпечатком', vq && !vq.get('code_verifier'));

  // ------------------------------------------------ истёкший пропуск
  await page.evaluate(() => localStorage.setItem('session', JSON.stringify({ token: 'bad.token', name: 'Анна', provider: 'vk', exp: 9999999999 })));
  await page.reload();
  await page.waitForTimeout(300);
  await page.click('#like-btn');
  await page.waitForTimeout(400);
  ok('пропуск не принят — выходим и говорим об этом',
     await page.evaluate(() => localStorage.getItem('session') === null) &&
     /Срок входа истёк/.test(await page.locator('.toast').last().textContent().catch(() => '')));

  // ------------------------------------------------ auth.html без нашего запроса
  await page.evaluate(() => sessionStorage.setItem('auth-flow', JSON.stringify({ provider: 'yandex', state: 'a'.repeat(43), back: location.href })));
  await page.goto(`${BASE}/auth.html?code=good&state=${'b'.repeat(43)}`);
  await page.waitForTimeout(400);
  ok('чужой state — вход не засчитан', /не получилось/.test(await page.textContent('#auth-status')) &&
     await page.evaluate(() => localStorage.getItem('session') === null));
  await page.goto(`${BASE}/auth.html?error=access_denied&state=x`);
  await page.waitForTimeout(300);
  ok('отказ на странице Яндекса — «Вход отменён»', /отменён/.test(await page.textContent('#auth-msg')));
  ok('auth.html закрыта от поиска', await page.locator('meta[name="robots"][content="noindex"]').count() === 1);

  // ------------------------------------------------ вход не настроен
  await page.goto(`${BASE}/${encodeURIComponent(POST)}?noauth`);
  await page.waitForTimeout(400);
  ok('пока вход не настроен, кнопки «Войти» нет', await page.locator('#auth-btn').count() === 0);
  ok('и числа у сердечка тоже нет', await page.isHidden('#like-count'));
  await page.goto(`${BASE}/?noauth`);
  await page.waitForTimeout(400);
  ok('и «Популярного» на главной нет', await page.evaluate(() => document.getElementById('popular').hidden));

  ok('нет ошибок JS', errs.length === 0, errs.join(' | '));

  await browser.close();
  web.close();
  py.kill();
  const fails = results.filter(r => !r.pass);
  console.log('\n====== ВХОД ЧЕРЕЗ ЯНДЕКС ID И VK ID ======');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
