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

ok('у каждой переименованной работы есть перенаправление',
  meta.every(p => (p.old_filenames || []).every(o => files.has(o))),
  (meta.find(p => (p.old_filenames || []).some(o => !files.has(o))) || {}).filename || '');

const dead = redirects.filter(r => {
  const m = read(r).match(/url=([^"]+)"/);
  return !m || !files.has(decodeURIComponent(m[1]));
});
ok('перенаправления ведут в существующие страницы', dead.length === 0, dead.slice(0, 3).join(', '));

ok('перенаправления просят себя не индексировать',
  redirects.every(r => /noindex/.test(read(r))));

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
