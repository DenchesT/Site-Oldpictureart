#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe, repeatable fixes for Old Picture Art (data + non-fast-forward push).

Usage: python apply_verified_fixes.py --check|--apply
Does not touch .git, run git commands, or publish anything.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

# Real visitor entrances (never substitute legal/administrative address).
# Only venues confirmed on their institutions' sites or municipal culture portals.
AFISHA_ADDRESSES = [
    ("Музей изящных искусств Бостона", "Бостон", "465 Huntington Avenue, Boston, MA 02115, USA", "https://www.mfa.org/visit/getting-here"),
    ("Музей Мармоттан-Моне", "Париж", "2 rue Louis-Boilly, 75016 Paris, France", "https://www.marmottan.fr/preparer-sa-visite/informations-pratiques/"),
    ("Национальная галерея искусства, Западное здание", "Вашингтон", "6th Street and Constitution Avenue NW, Washington, DC 20565, USA", "https://www.nga.gov/visit"),
    ("Национальная галерея искусства, Восточное здание", "Вашингтон", "4th Street and Constitution Avenue NW, Washington, DC 20565, USA", "https://www.nga.gov/visit"),
    ("Музей Академии художеств, музей-квартира А. И. Куинджи", "Санкт-Петербург", "Биржевой переулок, 1/10, кв. 11, Санкт-Петербург, Россия", "https://artsacademymuseum.org/branches/muzei-kvartira-a-i-kuindzhi/"),
    ("Музей «Новый Иерусалим»", "Истра", "Ново-Иерусалимская набережная, 1, Истра, Московская область, Россия", "https://njerusalem.ru/kontakty/kontaktnaya-informaciya/"),
    ("Курская картинная галерея им. А. А. Дейнеки, выставочный зал", "Курск", "улица Радищева, 85, Курск, Россия", "https://deinekagallery.ru/contacts/"),
    ("Альбертина", "Вена", "Albertinaplatz 1, 1010 Wien, Austria", "https://albertina.at/en/contact-us/"),
    ("Ленбаххаус", "Мюнхен", "Luisenstraße 33, 80333 München, Germany", "https://www.lenbachhaus.de/impressum"),
    ("Палаццо Питти, Сокровищница великих герцогов", "Флоренция", "Piazza de' Pitti, Firenze, Italia", "https://www.uffizi.it/en/pitti-palace"),
    ("Волгоградский музей изобразительных искусств им. Машкова, Выставочный зал", "Волгоград", "улица Маршала Чуйкова, 37, Волгоград, Россия", "https://mashkovmuseum.ru/kontakty-i-adresa"),
    ("ГМИИ Республики Татарстан, Галерея современного искусства", "Казань", "улица Карла Маркса, 57, Казань, Россия", "https://collections.museum.tatar.ru/entity/MUSEUM/240"),
    ("ГМИИ Республики Татарстан, усадьба Сандецкого", "Казань", "улица Карла Маркса, 64, Казань, Россия", "https://go.kzn.ru/places/usadba-sandeckogo"),
    ("Дом-музей Павла Кузнецова (филиал Радищевского музея)", "Саратов", "улица Октябрьская, 56, Саратов, Россия", "https://radmuseumart.ru/branches/kuznetsov/visitors.php"),
    ("Звенигородский музей-заповедник, Звенигородский манеж", "Звенигород", "улица Московская, 31/2, Звенигород, Московская область, Россия", "https://zvenmuseum.ru/o-muzee/manezh/"),
    ("Дом русского зарубежья им. А. Солженицына", "Москва", "улица Нижняя Радищевская, 2, Москва, Россия", "https://www.domrz.ru/visit/"),
]

# Historically inherited aliases; active map entities already have real locations.
MUSEUM_CORRECTIONS = {
    'Государственный музей-заповедник "Ростовский Кремль"': (
        'территория Кремль, Ростов, Ярославская область, Россия',
        'https://www.rostmuseum.ru/contacts/'),
    'Новгородский музей заповедник': (
        'Кремль, 11, Великий Новгород, Россия',
        'https://novgorodmuseum.ru/o-muzee-zapovednike/kontakty'),
    'Лондонская национальная галерея, Лондон': (
        'Trafalgar Square, London WC2N 5DN, United Kingdom',
        'https://www.nationalgallery.org.uk/visiting'),
}

OLD_PUSH = '''    git("push")
    logging.getLogger("build_site").info("GitHub: отправлено")'''
NEW_PUSH = '''    _push_reconciling_remote()
    logging.getLogger("build_site").info("GitHub: отправлено")'''
HELPER = '''

def _push_reconciling_remote():
    """Retry non-fast-forward without force; abort a conflicting rebase safely.

    At this point publish_generated() has committed all local changes, so
    rebasing does not discard an uncommitted worktree. A conflict is never
    resolved automatically. The original local commit is retained.
    """
    log = logging.getLogger("build_site")
    try:
        git("push")
        return
    except RuntimeError as exc:
        message = str(exc).lower()
        if not ("non-fast-forward" in message or "fetch first" in message):
            raise
    log.warning("GitHub: main обновился на сервере; синхронизирую коммиты без force push")
    try:
        git("fetch", "origin", "main")
        git("rebase", "origin/main")
    except RuntimeError as exc:
        try:
            git("rebase", "--abort")
        except RuntimeError:
            pass
        raise RuntimeError(
            "GitHub: автоматическая синхронизация не удалась (возможен конфликт). "
            "Исходный локальный коммит сохранён. Проверьте 'git status', "
            "затем выполните 'git fetch origin' и 'git rebase origin/main' "
            "вручную; при конфликте используйте 'git rebase --abort'. "
            "Не применяйте git push --force."
        ) from exc
    # Second push may still fail if the branch moved again; leave a clear
    # error instead of looping endlessly or rewriting remote history.
    git("push")
'''


def prepare(root):
    safety = root / 'sitebuild/safety.py'
    afisha = root / 'afisha.json'
    overrides = root / 'museum_overrides.json'
    afisha_py = root / 'sitebuild/afisha.py'
    css = root / 'docs/style.css'
    required = (safety, afisha, overrides, afisha_py, css)
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise RuntimeError('Не найдены файлы проекта: ' + ', '.join(missing))
    originals = {p: p.read_text(encoding='utf-8') for p in required}
    changed = {}
    report = {'matched_exhibitions': 0, 'inherited_museum_addresses': 0, 'museum_records_updated': [], 'exhibition_records_updated': [],
              'unmatched_venues': [], 'notices': []}

    source = originals[safety]
    if '_push_reconciling_remote()' not in source:
        if source.count(OLD_PUSH) != 1 or 'def publish_generated(' not in source:
            raise RuntimeError('Структура sitebuild/safety.py изменилась: отказ от небезопасной замены')
        source = source.replace(OLD_PUSH, NEW_PUSH, 1)
        pos = source.find('\ndef publish_generated(')
        if pos < 0:
            raise RuntimeError('Не найдена точка вставки обработчика GitHub')
        source = source[:pos] + HELPER + source[pos:]
    compile(source, str(safety), 'exec')
    if source != originals[safety]:
        changed[safety] = source

    data = json.loads(originals[afisha]); assert isinstance(data.get('exhibitions'), list)
    museum = json.loads(originals[overrides]); assert isinstance(museum, dict)
    matched = set()
    for record in data['exhibitions']:
        venue, city = (record.get('venue') or '').strip(), (record.get('city') or '').strip()
        existing = museum.get((record.get('museum') or '').strip()) or {}
        if isinstance(existing, dict) and existing.get('address') and not record.get('address'):
            record['address'] = existing['address']
            report['inherited_museum_addresses'] += 1
        for name, town, address, ref in AFISHA_ADDRESSES:
            if venue == name and city == town:
                matched.add((name, town))
                # A new hint forces the existing geocoder to reconsider a
                # cached approximate position on the next *online* build.
                if record.get('query') != address: record['query'] = address
                if record.get('address') != address: record['address'] = address
                report['exhibition_records_updated'].append(record.get('title',''))
                break
        if record.get('title') == 'Русский Париж. 1814–1914' and 'domrz.ru/exhibition/70568' in record.get('url',''):
            # Current official press page confirmed available. Avoid a page
            # that the built-in link checker reported as HTTP 404.
            record['url'] = 'https://www.domrz.ru/press/news/70629_dom_russkogo_zarubezhya_otkryvaet_neizvestnye_shedevry_russkogo_parizha_iz_chastnykh_kollektsiy/'
            report['notices'].append('Русский Париж: URL заменён на действующую официальную страницу')
    report['matched_exhibitions'] = len(report['exhibition_records_updated'])
    report['unmatched_venues'] = [name + ', ' + city for name, city, *_ in AFISHA_ADDRESSES if (name, city) not in matched]
    updated_afisha = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if json.loads(updated_afisha) != json.loads(originals[afisha]): changed[afisha] = updated_afisha

    for name, (address, site) in MUSEUM_CORRECTIONS.items():
        entry = museum.get(name)
        # No new phantom museum: add info only for an existing entry.
        if not isinstance(entry, dict):
            report['notices'].append('Справочник не содержит: ' + name)
            continue
        if entry.get('skip'):
            continue
        if entry.get('address') != address:
            entry['address'] = address
            report['museum_records_updated'].append(name)
        if not entry.get('site'): entry['site'] = site
    new_museum = json.dumps(museum, ensure_ascii=False, indent=2) + '\n'
    if json.loads(new_museum) != json.loads(originals[overrides]): changed[overrides] = new_museum

    # Display an explicit street address on exhibition cards, while retaining
    # the existing museum/city line and card layout. Not every event has one.
    page_source = originals[afisha_py]
    if 'class="afisha-address"' not in page_source:
        needle = "        + ('<button type=\"button\" class=\"afisha-pin\">на карте</button>' if coords else '') + '</p>'"
        insert = needle + "\n        + (f'<p class=\"afisha-address\">Адрес: {h(item[\"address\"])}</p>' if item.get(\"address\") else \"\")"
        if page_source.count(needle) != 1:
            raise RuntimeError('Не найден ожидаемый блок афиши: нужен ручной анализ sitebuild/afisha.py')
        page_source = page_source.replace(needle, insert, 1)
    compile(page_source, str(afisha_py), 'exec')
    if page_source != originals[afisha_py]: changed[afisha_py] = page_source

    sheet = originals[css]
    if '.afisha-address {' not in sheet:
        sheet += ("\n/* Verified street addresses of exhibition venues; existing typography. */\n"
                  ".afisha-address { margin: .2rem 0 .55rem; font-family: var(--ff-data); "
                  "font-size: var(--fs-xs); color: var(--muted); line-height: 1.5; }\n")
    if sheet != originals[css]: changed[css] = sheet
    return changed, report


def write_safely(changed, root):
    """Prepare every replacement first, back up everything, roll back on IO error."""
    temp_files = {}
    backups = {}
    replaced = []
    try:
        for path, text in changed.items():
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n',
                                             dir=path.parent, prefix='.'+path.name+'.',
                                             suffix='.new', delete=False) as out:
                out.write(text)
                out.flush()
                os.fsync(out.fileno())
                temp_files[path] = Path(out.name)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        for path in changed:
            backup = root / 'output' / 'backups' / path.relative_to(root)
            backup = backup.with_name(backup.name + '.bak_' + stamp)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            backups[path] = backup
        for path, temp in temp_files.items():
            os.replace(temp, path)
            replaced.append(path)
    except Exception:
        for path in reversed(replaced):
            shutil.copy2(backups[path], path)
        raise
    finally:
        for p in temp_files.values():
            p.unlink(missing_ok=True)


def audit(root):
    """Full structural audit: don't pass approximate geocodes as exact."""
    o = json.loads((root/'museum_overrides.json').read_text(encoding='utf-8'))
    cpath = root/'museum_coordinates.json'
    coords = json.loads(cpath.read_text(encoding='utf-8')) if cpath.exists() else {}
    a = json.loads((root/'afisha.json').read_text(encoding='utf-8'))['exhibitions']
    private = []
    bad = []
    aliases = []
    for name in sorted(set(o)|set(coords)):
        if name.startswith('_'): continue
        v = o.get(name) or {}
        if not isinstance(v, dict): continue
        if name == 'ГРМ, Санкт-Петербург':
            aliases.append(name+' → Государственный Русский музей, Санкт-Петербург')
            continue
        if v.get('skip'):
            private.append(name)
            continue
        combined = dict(coords.get(name) or {}, **v)
        if not (combined.get('address') or '').strip():
            bad.append({'name':name,'problem':'адрес отсутствует'})
        if combined.get('precision') == 'approx' or combined.get('approx'):
            bad.append({'name':name,'problem':'координаты приблизительные'})
        lat, lon = combined.get('lat'), combined.get('lon')
        if (lat is None) != (lon is None): bad.append({'name':name,'problem':'неполная пара координат'})
    place_path = root/'afisha_places.json'
    places = json.loads(place_path.read_text(encoding='utf-8')) if place_path.exists() else {}
    approximate = []
    for name, v in places.items():
        if isinstance(v, dict) and (v.get('precision') == 'approx' or v.get('approx')):
            approximate.append({'name':name,'query':v.get('hint',''),'problem':'координаты по городу'})
    without_street = [{'title':it.get('title'),'venue':it.get('venue'),'city':it.get('city')}
                      for it in a if not it.get('address')]
    return {'museum_records_in_overrides':sum(not n.startswith('_') for n in o),
            'museum_coordinate_entries':len(coords), 'private_collections_without_pins':private, 'legacy_aliases':aliases,
            'museum_address_or_coordinates_problems':bad,
            'exhibition_count':len(a), 'afisha_records_without_street_address':without_street,
            'afisha_places_approximate':approximate,
            'note':'Внешняя проверка каждого из адресов требует отдельных источников; этот отчёт проверяет полноту и тип координат.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='только проверить; ничего не меняется')
    parser.add_argument('--apply', action='store_true', help='применить изменения с резервными копиями')
    parser.add_argument('--audit', action='store_true', help='проверить все записи и вывести отчёт')
    parser.add_argument('--root', default='.', help='корень проекта')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    changed, report = prepare(root)
    print('Подходящие файлы:', ', '.join(str(p.relative_to(root)) for p in changed) or 'нет изменений')
    print('Совпадения выставок:', report['matched_exhibitions'])
    print('Адресов дополнено из действующего справочника музеев:',report['inherited_museum_addresses'])
    print('Адреса музеев обновятся:', ', '.join(report['museum_records_updated']) or 'всё уже актуально')
    if report['unmatched_venues']:
        print('Не найдены в текущей афише:', '; '.join(report['unmatched_venues']))
    for item in report['notices']: print('Примечание:',item)
    if args.apply:
        write_safely(changed, root)
        print('Изменения применены, резервные копии сохранены.')
    else: print('Файлы не изменены. Для установки используйте --apply.')
    if args.audit or args.apply:
        result = audit(root)
        filename = root/'output'/'museum_address_audit.json'
        # Report is intentionally not staged by the website's publish code.
        if args.apply:
            filename.parent.mkdir(parents=True,exist_ok=True)
            filename.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print('Отчёт:',filename)
        else: print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    sys.exit(main())
