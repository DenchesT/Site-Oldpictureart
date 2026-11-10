#!/usr/bin/env python3
"""Audited local-only changes, never accesses GitHub, network or git.

Run with --dir REPO to preview. Use --export FOLDER to write ready-to-use JSON
copies into a separate folder or --apply to write changes into the LOCAL
repository with backups. Unconfirmed archiving requires --include-unconfirmed.
"""
import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

PATCH = Path(__file__).with_name('proposal.json')


def sha_git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def json_file(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.'+path.name+'.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def matches_by_title(items, title):
    return [x for x in items if x.get('title') == title]


def safe_one(items, title, what, errors):
    candidates = matches_by_title(items, title)
    if len(candidates) > 1:
        errors.append(f'Неоднозначная запись в {what}: {title}')
        return None
    if not candidates:
        errors.append(f'Нет в {what}: {title}')
        return None
    return candidates[0]


def compute(main, archive, proposal, include_unconfirmed=False):
    orig_main = copy.deepcopy(main)
    orig_archive = copy.deepcopy(archive)
    main = copy.deepcopy(main)
    archive = copy.deepcopy(archive)
    info = {'new': [], 'updated': [], 'archive_added': [], 'archive_overlap_removed': [],
            'unconfirmed_left': [], 'source_updated': [], 'skipped': [], 'warnings': []}
    ex = main.get('exhibitions')
    arch = archive.get('exhibitions')
    sources = main.get('sources')
    if not isinstance(ex, list) or not isinstance(arch, list) or not isinstance(sources, list):
        raise ValueError('Неверная структура JSON: нужны списки exhibitions и sources')
    other_main = {k: copy.deepcopy(v) for k,v in main.items() if k not in ('exhibitions','sources','updated')}
    other_archive = {k: copy.deepcopy(v) for k,v in archive.items() if k not in ('exhibitions','updated')}

    for change in proposal['existing_exhibition_fixes']:
        target = safe_one(ex, change['title'], 'основной афише', info['warnings'])
        if target is None:
            continue
        before = copy.deepcopy(target)
        target.update(change['set'])
        if before != target:
            info['updated'].append(change['title'])

    # Only move known, uniquely identified entries. The archived content is a
    # clone of the full original record with all fields preserved.
    for move in proposal['archive_candidates']:
        title = move['title']
        candidate = safe_one(ex, title, 'основной афише', info['warnings'])
        if not candidate:
            continue
        if candidate.get('end', '9999-99-99') >= proposal['as_of']:
            info['warnings'].append(f'ПРОПУСК, дата окончания изменена или выставка продлена: {title}')
            continue
        existing_arch = matches_by_title(arch, title)
        if len(existing_arch) > 1:
            info['warnings'].append(f'ПРОПУСК, несколько архивных записей: {title}')
            continue
        # Already archived overlaps are removed from the main list regardless
        # of separate verification status; do not overwrite archive records.
        if existing_arch:
            ex.remove(candidate)
            info['archive_overlap_removed'].append(title)
            continue
        if not move.get('verified') and not include_unconfirmed:
            info['unconfirmed_left'].append(title)
            continue
        archived_record = copy.deepcopy(candidate)
        archived_record.update(move.get('set', {}))
        arch.append(archived_record)
        ex.remove(candidate)
        info['archive_added'].append(title)

    for candidate in proposal['new_exhibitions']:
        title = candidate['title']
        matches = matches_by_title(ex, title) + matches_by_title(arch, title)
        if matches:
            info['skipped'].append(f'Уже есть: {title}')
            continue
        ex.append(copy.deepcopy(candidate))
        info['new'].append(title)

    for fix in proposal['source_fixes']:
        candidates = [x for x in sources if x.get('museum') == fix['museum']]
        if len(candidates) != 1:
            info['warnings'].append(f'ПРОПУСК источника, имя неоднозначно/не найдено: {fix["museum"]}')
            continue
        item = candidates[0]
        changed = False
        for key, value in fix['set'].items():
            old = item.get(key)
            # Do not overwrite a user's custom working URL, except known
            # outdated GitHub versions explicitly identified by exact museum.
            expected_old = (
                (fix['index'] == 103 and key == 'url' and old == 'https://new.yarartmuseum.ru/exhibitions/') or
                (fix['index'] == 125 and key in ('url', 'site') and old == 'https://tretyakov.ru/')
            )
            if old and old != value and not expected_old:
                info['warnings'].append(f'ПРОПУСК настроенной ссылки {fix["museum"]}/{key}: {old}')
                continue
            if old != value:
                item[key] = value
                changed = True
        if changed:
            info['source_updated'].append(fix['museum'])

    assert len(sources) == len(orig_main['sources']), 'Длина списка источников изменена!'
    assert other_main == {k: v for k,v in main.items() if k not in ('exhibitions','sources','updated')}
    assert other_archive == {k: v for k,v in archive.items() if k not in ('exhibitions','updated')}
    if main['exhibitions'] != orig_main['exhibitions'] or main['sources'] != orig_main['sources']:
        main['updated'] = proposal['as_of']
    if archive['exhibitions'] != orig_archive['exhibitions']:
        archive['updated'] = proposal['as_of']
    return main, archive, info


def audit_sources(sources, patch, path):
    problems = {x['index']: x for x in patch['direct_url_failures']}
    found = {x['index']: x for x in patch['source_fixes']}
    pending = {x['index']: x for x in patch['pending_source_sites']}
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=[
            'index','museum','original_source_url','source_city','source_country',
            'attempted_method','fetch_status','proposed_replacement','evidence_url',
            'next_action','note'])
        writer.writeheader()
        for i, source in enumerate(sources, start=1):
            url = source.get('url') or source.get('site') or ''
            problem = problems.get(i)
            fix = found.get(i)
            potential = pending.get(i)
            if not url:
                method = 'Поиск официального сайта по названию'
                state = 'not_confirmed_without_direct_url'
                next_action = 'Найти официальный сайт и проверить текущие выставки'
            else:
                method = 'Попытка открытия указанной ссылки'
                state = 'page_opened_not_full_exhibition_audit'
                next_action = 'Проверить все разделы выставок и анонсы'
            if problem:
                state = problem['code']
                next_action = 'Повторить запрос; проверить зеркало, официальные соцсети или каталог учредителя'
            if fix:
                next_action = 'Проверить и добавить предложенную ссылку, затем проверить выставки'
            if potential:
                next_action = 'Дополнительно подтвердить найденную ссылку'
            writer.writerow({
                'index':i,'museum':source.get('museum',''), 'original_source_url':url,
                'source_city':source.get('city',''),'source_country':source.get('country',''),
                'attempted_method':method,'fetch_status':state,
                'proposed_replacement':json.dumps(fix['set'],ensure_ascii=False) if fix else (potential['candidate_site'] if potential else ''),
                'evidence_url':fix.get('evidence','') if fix else '',
                'next_action':next_action,
                'note':problem['details'] if problem else (potential['reason'] if potential else (fix.get('note','') if fix else ''))})


def main():
    p=argparse.ArgumentParser(description='Old Picture Art. Только локальное обновление, без GitHub и сети.')
    p.add_argument('--dir', type=Path, default=Path('.'), help='Папка локального репозитория, содержащая afisha.json')
    p.add_argument('--export', type=Path, help='Выгрузить готовые JSON и CSV в отдельную папку, оригинал не менять')
    p.add_argument('--apply', action='store_true', help='Изменить ТОЛЬКО локальные JSON с резервными копиями')
    p.add_argument('--include-unconfirmed', action='store_true', help='Дополнительно архивировать три выставки без нового официального подтверждения')
    args=p.parse_args()
    if args.apply and args.export:
        p.error('Нельзя указывать --apply и --export одновременно')
    folder = args.dir.resolve()
    src=folder/'afisha.json'
    hist=folder/'afisha_archive.json'
    if not src.is_file() or not hist.is_file():
        p.error('Не найдены afisha.json и/или afisha_archive.json в: ' + str(folder))
    raw_main=src.read_bytes()
    raw_arch=hist.read_bytes()
    original=json.loads(raw_main.decode('utf-8-sig'))
    old_hist=json.loads(raw_arch.decode('utf-8-sig'))
    prop=json_file(PATCH)
    updated, archived, summary=compute(original, old_hist, prop, args.include_unconfirmed)
    print('GitHub: СТРОГО БЕЗ ИЗМЕНЕНИЙ. Команды git, сеть и публикация не используются.')
    print('Афиша: {} -> {}'.format(len(original['exhibitions']),len(updated['exhibitions'])))
    print('Архив: {} -> {}'.format(len(old_hist['exhibitions']),len(archived['exhibitions'])))
    print('Источники: {} -> {}'.format(len(original['sources']),len(updated['sources'])))
    for key in ('new','updated','archive_added','archive_overlap_removed','unconfirmed_left','source_updated','skipped','warnings'):
        print(f'{key}: {len(summary[key])}')
        for msg in summary[key]: print('  - '+msg)
    if sha_git_blob(raw_main) != prop['base_afisha_git_blob_sha']:
        print('ВНИМАНИЕ: локальная версия afisha.json отличается от main во время аудита; записи проверяются индивидуально.')
    if sha_git_blob(raw_arch) != prop['base_archive_git_blob_sha']:
        print('ВНИМАНИЕ: локальный архив отличается от main; существующие записи сохраняются.')
    if args.export:
        dest=args.export.resolve()
        if dest == folder:
            p.error('--export должен указывать другую папку (не локальный проект)')
        dest.mkdir(parents=True,exist_ok=True)
        for f in ('afisha.json','afisha_archive.json','source_audit_126.csv'):
            if (dest/f).exists():
                p.error('В папке экспорта уже существует: '+str(dest/f))
        save_json(dest/'afisha.json',updated)
        save_json(dest/'afisha_archive.json',archived)
        audit_sources(original['sources'],prop,dest/'source_audit_126.csv')
        save_json(dest/'apply_summary.json',summary)
        print('Экспорт выполнен: '+str(dest))
    elif args.apply:
        backups=[]
        for path in (src,hist):
            dst=path.with_name(path.name+'.bak-2026-11-10')
            if dst.exists(): p.error('Отказ от перезаписи резервной копии: '+str(dst))
            backups.append((path,dst))
        for path,dst in backups:
            shutil.copy2(path,dst)
        save_json(src,updated)
        save_json(hist,archived)
        print('Обновлена только локальная копия. Резервные копии: '+', '.join(str(x[1]) for x in backups))
    else:
        print('Это только ПРЕДПРОСМОТР. Для создания файлов используйте --export <папка>.')

if __name__=='__main__':
    main()
