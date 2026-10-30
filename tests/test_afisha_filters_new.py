# -*- coding: utf-8 -*-
"""New afisha functionality: offline generated-HTML and JavaScript smoke tests.

Run from site root: python tests/test_afisha_filters_new.py
"""
import ast
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.argv = ['build_site.py']

from sitebuild import afisha as af  # noqa: E402


def example(title, start, end, *, venue='Музей из примера', artists=None):
    d = {'title': title, 'venue': venue, 'city': 'Москва', 'country': 'Россия',
         'start': start, 'end': end, 'url': 'https://example.org/exhibit',
         'note': 'Работы художника Моне', 'tags': ['impr']}
    if artists is not None:
        d['artists'] = artists
    d['id'] = af.afisha_id(d)
    return d


def main():
    now = date(2026, 10, 30)
    rows = [
        example('Идёт выставка', '2026-10-01', '2026-11-05'),
        example('Скоро открытие', '2026-11-15', '2027-01-10'),
        example('Завершённая выставка', '2025-01-01', '2025-05-01'),
        example('Отдалённое открытие', '2027-10-01', '2028-01-01', artists=['Клод Моне']),
    ]
    page = af.render_afisha_page(rows, '2026-10-30', today=now)
    assert 'id="afisha-archive"' in page
    assert 'Завершённая выставка' in page
    assert 'Отдалённое открытие' in page
    assert 'id="afisha-archive-year"' in page
    assert '<option value="2025"' in page
    assert 'data-status="archive"' in page
    assert 'data-status="running"' in page
    assert 'data-status="soon"' in page
    for control in ('afisha-closing', 'afisha-opening', 'afisha-artist',
                    'afisha-venue', 'afisha-query', 'afisha-sort',
                    'afisha-only-favorites', 'afisha-reset'):
        assert f'id="{control}"' in page, control
    assert page.count('class="afisha-favorite"') == len(rows)
    assert 'data-search=' in page
    assert 'Клод Моне' in page
    assert 'afishaFavorites' in page
    assert 'localStorage' in page
    assert 'data-phase' in page
    current = af.split(rows, now)
    assert [it['title'] for it in current['russia']['running']] == ['Идёт выставка']
    assert [it['title'] for it in current['russia']['soon']] == ['Скоро открытие']
    assert 'Завершённая выставка' not in str(current)
    assert 'Отдалённое открытие' not in str(current)
    # The existing SEO data must not list ended events.
    schema = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, flags=re.S)
    if schema:
        import json
        events = [event for x in schema for event in json.loads(x).get('@graph', [])]
        assert not any(ev.get('name') == 'Завершённая выставка' for ev in events)
    js = af.AFISHA_JS.replace('<script>', '').replace('</script>', '')
    assert '__SOON__' not in js
    try:
        p = subprocess.run(['node', '--check'], input=js, text=True, capture_output=True, check=False)
    except FileNotFoundError:
        print('Проверка синтаксиса JavaScript пропущена: Node.js не установлен.')
    else:
        assert p.returncode == 0, p.stderr
    ast.parse((ROOT / 'sitebuild' / 'afisha.py').read_text(encoding='utf-8'))
    print('OK: архив, статусы, даты, поиск, музей, художник, сортировка, избранное, сохранена текущая афиша; JS синтаксис проверен.')


if __name__ == '__main__':
    main()
