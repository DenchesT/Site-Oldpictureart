#!/usr/bin/env node
// Все проверки из корня и tests/, независимо от текущей рабочей папки.
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function discover(root) {
  return ['', 'tests'].flatMap(dir => fs.readdirSync(path.join(root, dir))
    .filter(f => /^test_.*\.(js|py)$/.test(f) && fs.statSync(path.join(root, dir, f)).isFile())
    .map(f => path.join(dir, f))).sort();
}

function runFile(root, file) {
  const command = file.endsWith('.js') ? process.execPath
    : (process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'));
  const result = spawnSync(command, [path.join(root, file)], {
    cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 5 * 60 * 1000, maxBuffer: 10 * 1024 * 1024,
  });
  // unittest пишет результат в stderr даже при успехе; его тоже показываем.
  const output = (result.stdout || '') + (result.stderr || '')
    + (result.error ? `\n${result.error.message}\n` : '');
  return { ok: !result.error && result.status === 0, output };
}

function main() {
  const root = path.resolve(__dirname, '..');
  const results = [];
  for (const file of discover(root)) {
    process.stdout.write(`\n──────── ${file} ────────\n`);
    const result = runFile(root, file);
    process.stdout.write(result.output);
    results.push([file, result.ok]);
  }
  console.log('\n════════════ ИТОГ ════════════');
  for (const [file, ok] of results) console.log(`${ok ? 'OK  ' : 'FAIL'}  ${file}`);
  const bad = results.filter(([, ok]) => !ok).length;
  console.log(`\nФайлов: ${results.length}, с ошибками: ${bad}`);
  process.exitCode = bad ? 1 : 0;
}

module.exports = { discover, runFile };
if (require.main === module) main();
