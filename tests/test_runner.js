'use strict';
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { discover, runFile } = require('./run');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'opa-runner-'));
try {
  fs.mkdirSync(path.join(root, 'tests'));
  fs.mkdirSync(path.join(root, 'test_directory.js'));
  fs.writeFileSync(path.join(root, 'test_root.js'), 'console.error("visible stderr");');
  fs.writeFileSync(path.join(root, 'tests/test_fail.js'), 'process.exit(7);');
  fs.writeFileSync(path.join(root, 'tests/helper.js'), 'throw Error("not a test");');
  assert.deepStrictEqual(discover(root), ['test_root.js', path.join('tests', 'test_fail.js')]);
  const pass = runFile(root, 'test_root.js');
  assert(pass.ok);
  assert(pass.output.includes('visible stderr'));
  assert(!runFile(root, 'tests/test_fail.js').ok);
  assert(!runFile(root, 'tests/missing.js').ok);
  console.log('OK: root tests discovered, stderr shown, failed commands fail the suite');
} finally { fs.rmSync(root, { recursive: true, force: true }); }
