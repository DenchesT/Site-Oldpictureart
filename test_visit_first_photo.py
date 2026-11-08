# -*- coding: utf-8 -*-
"""Минимальные регрессионные проверки без сторонних зависимостей."""
import ast
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    if not (root / 'sitebuild' / 'visits.py').is_file():
        root = root.parent
    source = (root / 'sitebuild' / 'visits.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'visit_cover_index')
    code = compile(ast.fix_missing_locations(ast.Module(body=[func], type_ignores=[])), '<cover>', 'exec')
    ns = {}
    exec(code, ns)
    index = ns['visit_cover_index']
    for visit in (
        {'kind': 'выставка', 'images': ['one.jpg', 'two.jpg', 'three.jpg']},
        {'kind': 'музей', 'images': ['museum-one.jpg', 'museum-two.jpg']},
        {'kind': 'музей', 'images': ['only.jpg']},
        {'kind': 'выставка', 'images': []},
        {'kind': 'музей', 'images': ['first.jpg', 'second.jpg'], 'cover_index': 1},
    ):
        assert index(visit) == 0, ('Обложка должна быть первым фото', visit)
    assert source.count('def visit_cover_index(v):') == 1
    assert 'index=visit_cover_index(v)' in source
    print('OK: первая фотография для выставок и музеев; выбранный стиль карточек не затронут.')

if __name__ == '__main__':
    sys.exit(main() or 0)
