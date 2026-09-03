#!/usr/bin/env node
// Прогоняет все проверки по очереди и печатает итог.
// Запуск из корня проекта:  node tests/run.js
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const FILES = fs.readdirSync(__dirname)
  .filter(f => f.startsWith('test_') && f.endsWith('.js'))
  .sort();

const results = [];
for (const f of FILES) {
  process.stdout.write(`\n──────── ${f} ────────\n`);
  try {
    const out = execFileSync(process.execPath, [path.join(__dirname, f)], {
      encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 5 * 60 * 1000,
    });
    process.stdout.write(out);
    results.push([f, true, (out.match(/Всего: (\d+)/) || [])[1] || '?']);
  } catch (e) {
    process.stdout.write((e.stdout || '') + (e.stderr || ''));
    results.push([f, false, (String(e.stdout).match(/провалено: (\d+)/) || [])[1] || '?']);
  }
}

console.log('\n════════════ ИТОГ ════════════');
let bad = 0;
for (const [f, ok, n] of results) {
  console.log(`${ok ? 'OK  ' : 'FAIL'}  ${f.padEnd(22)} ${ok ? n + ' проверок' : 'провалено ' + n}`);
  if (!ok) bad++;
}
console.log(bad ? `\n✕ файлов с ошибками: ${bad}` : '\n✓ всё зелёное');
process.exit(bad ? 1 : 0);
