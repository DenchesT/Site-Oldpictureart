# -*- coding: utf-8 -*-
"""Проверки исправления афиши: python test_afisha_favorite_scroll.py"""
import ast
from pathlib import Path
import subprocess
import tempfile
from fix_afisha_favorite_scroll import (
    make_patch, MARKER, OLD_LISTENER, NEW_LISTENER, OLD_SORT,
    NEW_SORT, OLD_SHOW, NEW_SHOW,
)

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'sitebuild' / 'afisha.py'


def check(name, condition):
    assert condition, name
    print('OK:', name)


def main():
    # Fake module with the same three code anchors as the current live repo.
    fixture = ('AFISHA_JS = """\n' + OLD_LISTENER + '\n' + OLD_SHOW + '\n' +
               OLD_SORT + '\n"""\n')
    changed, yes = make_patch(fixture)
    check('точечная правка по исходной версии', yes and MARKER in changed)
    again, no = make_patch(changed)
    check('повторное применение не дублирует код', not no and again == changed)
    ast.parse(changed)
    check('Python синтаксис после исправления', True)
    check('убрано полное обновление страницы при обычном лайке',
          'state.status !== \'favorites\'' in changed and 'return;\n    }' in changed)
    check('в избранном обновление без сортировки', 'show(true);' in changed and NEW_SORT in changed)
    try:
        make_patch('AFISHA_JS = "неизвестная версия"')
    except RuntimeError:
        check('отказ от неизвестной версии без частичной правки', True)
    else:
        raise AssertionError('Должна быть ошибка совместимости')

    if SOURCE.exists():
        actual = SOURCE.read_text('utf-8')
        check('установленное исправление в исходниках', MARKER in actual and NEW_LISTENER in actual)
        tree = ast.parse(actual)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'AFISHA_JS' for t in node.targets):
                js = node.value
                while isinstance(js, ast.Call) and isinstance(js.func, ast.Attribute):
                    js = js.func.value
                if isinstance(js, ast.Constant) and isinstance(js.value, str) and '<script>' in js.value:
                    source_js = js.value.replace('<script>', '').replace('</script>', '')
                    try:
                        with tempfile.TemporaryDirectory() as d:
                            file = Path(d) / 'afisha_script.js'
                            file.write_text(source_js, encoding='utf-8')
                            p = subprocess.run(['node', '--check', str(file)], capture_output=True, text=True)
                        check('синтаксис JavaScript (Node.js)', p.returncode == 0)
                        if p.returncode: print(p.stderr)
                    except FileNotFoundError:
                        print('SKIP: Node.js не найден, синтаксис JS не проверен')
                break
    print('OK: все проверки завершены')


if __name__ == '__main__':
    main()
