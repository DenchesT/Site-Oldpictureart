// Квиз: варианты ответа из той же школы и того же времени,
// и второй вопрос — «когда написано».
//
// Раньше три неверных варианта брались наугад из всех художников, и к
// французскому пейзажу 1870-х рядом стояли Репин, Пуссен и Бирштадт —
// лишнее отпадало само, угадывать было нечего. Здесь проверяется, что
// варианты подобраны со смыслом, не повторяются одной тройкой и что
// картины идут колодой, без повторов.
const { chromium } = require('playwright');
const path = require('path');
const DOCS = path.join(__dirname, '..', 'docs');
const URL = 'file://' + DOCS + '/quiz.html';
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

(async () => {
  const browser = await chromium.launch(LAUNCH);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message.slice(0, 140)));
  await page.goto(URL);
  await page.waitForTimeout(500);

  const btns = await page.$$eval('.quiz-btn', b => b.map(x => x.textContent));
  ok('четыре разных варианта', btns.length === 4 && new Set(btns).size === 4, btns.join(' · '));
  ok('верный ответ среди них', await page.evaluate(() =>
    [...document.querySelectorAll('.quiz-btn')].some(b => b.textContent === currentPost.artist)));

  ok('записи с несколькими авторами в квиз не попали', await page.evaluate(() =>
    !ALL_POSTS.some(p => p.artist.includes(',')) && !Object.keys(ARTISTS).some(a => a.includes(','))));
  ok('у каждого художника известна школа', await page.evaluate(() =>
    Object.values(ARTISTS).every(v => v[0])),
    await page.evaluate(() => Object.keys(ARTISTS).filter(a => !ARTISTS[a][0]).join(', ')));

  // доля вариантов из своей школы на сотне подборов
  const share = await page.evaluate(() => {
    const out = {};
    for (const school of ['fr', 'ru', 'north', 'de']) {
      const post = ALL_POSTS.find(p => ARTISTS[p.artist][0] === school && p.y);
      let same = 0, n = 0;
      for (let i = 0; i < 100; i++)
        for (const a of pickOthers(post)) { n++; if (ARTISTS[a][0] === school) same++; }
      out[school] = [post.artist, Math.round(100 * same / n)];
    }
    return out;
  });
  for (const [school, [artist, pct]] of Object.entries(share))
    ok(`${school}: варианты из той же школы`, pct >= 90, `${artist} — ${pct}%`);

  // британцев трое: двое своих и один из близкой школы, а не случайный
  const gb = await page.evaluate(() => {
    const post = ALL_POSTS.find(p => ARTISTS[p.artist][0] === 'gb');
    const seen = new Set();
    for (let i = 0; i < 100; i++) pickOthers(post).forEach(a => seen.add(ARTISTS[a][0]));
    return [post.artist, [...seen].sort()];
  });
  ok('малой школе добирают из соседней', gb[1].every(s => s === 'gb' || s === 'us'),
    `${gb[0]}: ${gb[1].join(', ')}`);

  // к одной картине — не одна и та же тройка каждый раз
  const variety = await page.evaluate(() => {
    const post = ALL_POSTS.find(p => ARTISTS[p.artist][0] === 'fr' && p.y);
    const s = new Set();
    for (let i = 0; i < 30; i++) s.add(pickOthers(post).sort().join('|'));
    return s.size;
  });
  ok('тройки вариантов меняются', variety >= 5, `${variety} разных из 30`);

  // время тоже учитывается: к картине XIX века не приставляют Пуссена
  const era = await page.evaluate(() => {
    const post = ALL_POSTS.find(p => ARTISTS[p.artist][0] === 'fr' && p.y > 1860 && p.y < 1900);
    let far = 0;
    for (let i = 0; i < 200; i++)
      for (const a of pickOthers(post)) if (Math.abs((ARTISTS[a][1] || post.y) - post.y) > 100) far++;
    return [post.artist, post.y, far];
  });
  ok('к XIX веку не подмешивают XVII', era[2] === 0, `${era[0]}, ${era[1]}: ${era[2]} раз`);

  // колода: пока не прошли все картины, ни одна не повторилась
  const deckOk = await page.evaluate(() => {
    decks.artist = [];
    const n = ALL_POSTS.length, seen = new Set();
    for (let i = 0; i < n; i++) { newQuestion(); seen.add(currentPost.filename); }
    return [seen.size, n];
  });
  ok('за круг картины не повторяются', deckOk[0] === deckOk[1], `${deckOk[0]} из ${deckOk[1]}`);

  // ответ засчитывается
  await page.evaluate(() => resetScore());
  await page.evaluate(() => [...document.querySelectorAll('.quiz-btn')]
    .find(b => b.textContent === currentPost.artist).click());
  ok('верный ответ засчитан', await page.textContent('#score') === '1' && await page.textContent('#total') === '1');
  ok('после ответа — ссылка на картину', await page.locator('.quiz-link').count() === 1);

  // ============================================ «когда написано»
  await page.click('.quiz-modes [data-mode="year"]');
  await page.waitForTimeout(200);
  ok('переключатель ведёт в вопрос «когда»',
     /десятилетие/.test(await page.textContent('#quiz-heading')) &&
     await page.getAttribute('.quiz-modes [data-mode="year"]', 'aria-pressed') === 'true');
  ok('адрес меняется на #year — вопрос можно дать ссылкой', page.url().endsWith('#year'));
  const yq = await page.evaluate(() => ({
    opts: [...document.querySelectorAll('.quiz-btn')].map(b => b.textContent),
    correct: correctLabel,
    title: document.getElementById('quiz-title').textContent,
    artist: document.getElementById('quiz-artist').textContent,
    artistShown: !document.getElementById('quiz-artist').hidden,
    real: currentPost.artist,
  }));
  const decs = yq.opts.map(o => parseInt(o, 10));
  ok('четыре десятилетия подряд', yq.opts.length === 4 && yq.opts.every(o => /^\d{4}-е$/.test(o)) &&
     decs.every((d, i) => i === 0 || d - decs[i - 1] === 10), yq.opts.join(' · '));
  ok('верное среди них', yq.opts.includes(yq.correct), yq.correct);
  ok('под картиной нет даты — иначе ответ написан', !/\d{4}/.test(yq.title), yq.title);
  ok('художник показан как подсказка', yq.artistShown && yq.artist === yq.real, yq.artist);

  const pos = await page.evaluate(() => {
    const seen = new Set();
    for (let i = 0; i < 60; i++) {
      newQuestion();
      seen.add([...document.querySelectorAll('.quiz-btn')].findIndex(b => b.textContent === correctLabel));
    }
    return [...seen].sort();
  });
  ok('верный ответ стоит на разных местах', pos.length === 4, pos.join(','));

  const yDeck = await page.evaluate(() => {
    decks.year = [];
    const eligible = ALL_POSTS.filter(p => p.dec).length, seen = new Set();
    for (let i = 0; i < eligible; i++) { newQuestion(); seen.add(currentPost.filename); }
    return [seen.size, eligible, ALL_POSTS.filter(p => p.dec && /\d{4}/.test(p.t)).length];
  });
  ok('за круг ни одна картина не повторилась', yDeck[0] === yDeck[1], `${yDeck[0]} из ${yDeck[1]}`);
  ok('картины с годом в названии в вопрос «когда» не попали', yDeck[2] === 0);

  await page.evaluate(() => resetScore());
  await page.evaluate(() => [...document.querySelectorAll('.quiz-btn')]
    .find(b => b.textContent === correctLabel).click());
  const fb = await page.textContent('#quiz-feedback');
  ok('верное десятилетие засчитано, точная дата показана',
     await page.textContent('#score') === '1' && /Написана:/.test(fb), fb.slice(0, 80));

  await page.click('.quiz-modes [data-mode="artist"]');
  await page.waitForTimeout(200);
  ok('у «художника» свой счёт', await page.textContent('#score') === '1' && await page.textContent('#total') === '1');
  ok('в «художнике» строка с именем скрыта', await page.locator('#quiz-artist').isHidden());

  const p2 = await ctx.newPage();
  await p2.goto(URL + '#year');
  await p2.waitForTimeout(400);
  ok('ссылка quiz.html#year открывает сразу вопрос «когда»',
     await p2.evaluate(() => mode === 'year' && /^\d{4}-е$/.test(document.querySelector('.quiz-btn').textContent)));
  ok('счёт «когда» сохранился', await p2.textContent('#score') === '1');
  await p2.close();

  ok('нет ошибок JS', errs.length === 0, errs.join(' | '));
  await browser.close();

  const fails = results.filter(r => !r.pass);
  console.log('\n============ КВИЗ ============');
  for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
  console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
  process.exit(fails.length ? 1 : 0);
})();
