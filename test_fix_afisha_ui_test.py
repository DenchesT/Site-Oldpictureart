# -*- coding: utf-8 -*-
"""Offline regression tests for the one-line afisha Playwright fix."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('fix', Path(__file__).with_name('fix_afisha_ui_test.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

original = '''// OPA AFISHA UI TESTS 2026-10-31
  await page.locator('#afisha-more-filters').evaluate(d => d.open = true);
    await page.selectOption('#afisha-opening', '90');
  const openings = await page.$$eval('.afisha-item:not([hidden])', xs => xs.map(x => x.dataset.start));
'''
updated, status = mod.patch(original)
assert updated != original and 'soon' in updated and 'afisha-opening' in updated
assert updated.index('data-status="soon"') < updated.index("selectOption('#afisha-opening'")
assert mod.patch(updated)[0] == updated, 'повторный запуск должен быть безопасен'
assert updated.count(mod.MARKER) == 1
assert updated.count("selectOption('#afisha-opening'") == 1
try:
    mod.patch("await page.selectOption('#afisha-opening', '90');")
except RuntimeError:
    pass
else:
    raise AssertionError('чужую/старую версию менять нельзя')
print('OK: переключение на «Скоро» перед фильтром открытия')
print('OK: другие проверки сохраняются')
print('OK: повторное применение безопасно')
print('OK: чужую версию скрипт не меняет')
