// Адреса страниц.
//
// Имена были кириллические, и при копировании ссылка раздувалась втрое:
// 2025-11-07-фрэнсис-кэмпбелл-буало-каделл.html превращалось в 341 знак
// процентов. Именно в таком виде ссылка уходит в переписку.
//
// Здесь проверяется не только то, что имена стали латинскими, но и то,
// что прежние адреса продолжают работать: ссылку на картину могли уже
// отправить, и превращать её в «страница не найдена» нельзя.
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const DOCS = path.join(ROOT, 'docs');

const results = [];
const ok = (name, cond, extra) => results.push({ name, pass: !!cond, extra: extra || '' });

const meta = JSON.parse(fs.readFileSync(path.join(ROOT, 'posts_meta.json'), 'utf8'));
const visits = (() => {
  try { return JSON.parse(fs.readFileSync(path.join(ROOT, 'visits_meta.json'), 'utf8')); }
  catch (e) { return []; }
})();
const files = new Set(fs.readdirSync(DOCS).filter(f => f.endsWith('.html')));
const read = f => fs.readFileSync(path.join(DOCS, f), 'utf8');
const isRedirect = f => read(f).slice(0, 600).includes('Страница переехала');
const redirects = [...files].filter(isRedirect);
const live = [...files].filter(f => !redirects.includes(f));

const ascii = s => /^[\x00-\x7F]*$/.test(s);

// ------------------------------------------------------------ имена
ok('имена страниц работ латинские',
  meta.every(p => ascii(p.filename)),
  (meta.find(p => !ascii(p.filename)) || {}).filename || '');

ok('имена страниц посещений латинские',
  visits.every(v => ascii(v.filename)),
  (visits.find(v => !ascii(v.filename)) || {}).filename || '');

ok('имена страниц художников латинские',
  live.filter(f => f.startsWith('artist-')).every(ascii));

ok('имена страниц тегов латинские',
  live.filter(f => f.startsWith('tag-')).every(ascii));

ok('ни одна действующая страница не осталась кириллической',
  live.every(ascii), live.filter(f => !ascii(f)).slice(0, 3).join(', '));

const longest = meta.reduce((a, p) => p.filename.length > a.length ? p.filename : a, '');
ok('адрес умещается в сотню знаков', longest.length < 100,
  `самый длинный ${longest.length}: ${longest}`);

ok('имена работ не повторяются',
  new Set(meta.map(p => p.filename)).size === meta.length);

// Фамилия в адресе должна быть той, какой её пишут в мире: тег канала
// #renoir лучше, чем обратная транслитерация «renuar».
const renoir = meta.find(p => /Ренуар/.test(p.artist || ''));
if (renoir) ok('западная фамилия взята из тега канала, а не переложена обратно',
  renoir.filename.startsWith('renoir-'), renoir.filename);

// ------------------------------------------- прежние адреса продолжают жить
ok('прежние адреса оставлены перенаправлениями', redirects.length > 0,
  `${redirects.length} шт.`);

// Прежний адрес работы был <дата>-<художник>.html. Восстанавливаем его
// по тем же данным, что и сборка, и требуем, чтобы на каждом лежало
// перенаправление. Проверять по old_filenames мало: это поле появляется
// только в тот прогон, который переименовывает, и на чистой базе
// проверка проходила бы впустую, ничего не проверив.
const slugifyRu = s => (s || '').toLowerCase()
  .replace(/[^\p{L}\p{N}\s-]/gu, '').replace(/\s+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
const seen = new Map();
const legacy = [];
for (const p of meta) {
  const base = `${p.date || ''}-${slugifyRu(p.artist)}`;
  const n = (seen.get(base) || 0) + 1;
  seen.set(base, n);
  legacy.push([n === 1 ? `${base}.html` : `${base}-${n}.html`, p.filename]);
}
const lost = legacy.filter(([o, n]) => o !== n && !files.has(o));
ok('на каждом прежнем адресе работы лежит перенаправление',
  lost.length === 0, `потеряно ${lost.length}: ` + lost.slice(0, 3).map(x => x[0]).join(', '));

ok('прежних адресов работ ровно столько же, сколько работ',
  legacy.filter(([o, n]) => o !== n).length === meta.length,
  `${legacy.filter(([o, n]) => o !== n).length} из ${meta.length}`);

const dead = redirects.filter(r => {
  const m = read(r).match(/url=([^"]+)"/);
  return !m || !files.has(decodeURIComponent(m[1]));
});
ok('перенаправления ведут в существующие страницы', dead.length === 0, dead.slice(0, 3).join(', '));

// noindex здесь напрашивается, но он рядом с canonical — это два
// противоречащих указания: «этой страницы в поиске быть не должно» и
// «перенеси всё накопленное вот на эту». Разбирая противоречие,
// поисковик может отнести запрет к странице, на которую мы переносим.
ok('перенаправления не запрещают себя индексировать',
  redirects.every(r => !/noindex/.test(read(r))),
  redirects.filter(r => /noindex/.test(read(r))).slice(0, 3).join(', '));

ok('перенаправления называют новый адрес каноническим',
  redirects.every(r => /<link rel="canonical"/.test(read(r))));

ok('перенаправление работает и без скриптов',
  redirects.every(r => /http-equiv="refresh"/.test(read(r))));

// ---------------------------------------------------- карта сайта и ссылки
const sm = fs.readFileSync(path.join(DOCS, 'sitemap.xml'), 'utf8');
const inSitemap = new Set([...sm.matchAll(/<loc>([^<]+)<\/loc>/g)]
  .map(m => decodeURIComponent(m[1].split('/').pop())));

ok('перенаправления не попадают в карту сайта',
  redirects.every(r => !inSitemap.has(r)),
  redirects.filter(r => inSitemap.has(r)).slice(0, 3).join(', '));

ok('всё из карты сайта есть на диске',
  [...inSitemap].every(u => !u.endsWith('.html') || files.has(u)),
  [...inSitemap].filter(u => u.endsWith('.html') && !files.has(u)).slice(0, 3).join(', '));

const broken = [];
for (const f of files) {
  const html = read(f);
  for (const m of html.matchAll(/href="([^"#?:]+\.html)(?:[#?][^"]*)?"/g)) {
    const t = decodeURIComponent(m[1]);
    if (!t.includes('/') && !files.has(t)) broken.push(`${f} → ${t}`);
  }
}
ok('внутренние ссылки никуда не потерялись', broken.length === 0, broken.slice(0, 3).join(' | '));

console.log('\n========== АДРЕСА СТРАНИЦ ==========');
for (const r of results) console.log(`${r.pass ? 'OK  ' : 'FAIL'}  ${r.name}${r.extra ? '  — ' + r.extra : ''}`);
const fails = results.filter(r => !r.pass);
console.log(`\nВсего: ${results.length}, провалено: ${fails.length}`);
process.exit(fails.length ? 1 : 0);
