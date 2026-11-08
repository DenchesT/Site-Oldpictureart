# -*- coding: utf-8 -*-
"""Apply Art Passport v3 to an already installed cloud-sync passport.

Does not push, access the network, change secrets, or create YDB schema.
Commands: python apply_passport_upgrade_v3.py --check | --apply
Assets live in upgrade_payload/, so --check never partially installs them.
"""
from __future__ import annotations
import argparse
import ast
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'upgrade_payload'
MARK = 'OPA PASSPORT V3 2026-11-08'
SOURCE_FILES = (
    'cloud/auth/index.py',
    'sitebuild/artists.py',
    'sitebuild/museums.py',
    'sitebuild/posts.py',
    'sitebuild/static.py',
)
ASSETS = (
    'docs/passport-actions.js', 'docs/passport.js', 'docs/passport.css',
    'sitebuild/passport.py', 'sitebuild/passport_ids.py',
)


def one(content: str, before: str, after: str, description: str) -> str:
    if content.count(before) != 1:
        raise RuntimeError(f'{description}: expected one occurrence, found {content.count(before)}')
    return content.replace(before, after, 1)


VALIDATOR = '''def validate_passport_changes(changes):
    """Validate every key/payload before it reaches YDB.

    Collections use per-artwork keys, so editing distinct artworks on two
    devices no longer overwrites a whole collection JSON document.
    """
    if not isinstance(changes, list) or len(changes) > 40:
        raise Fail(400, "Паспорт: слишком много изменений")
    result = []
    for item in changes:
        if not isinstance(item, dict):
            raise Fail(400, "Паспорт: неверная запись")
        key, value = item.get("key"), item.get("value")
        if not isinstance(key, str) or "|" not in key or len(key.encode("utf-8")) > 700:
            raise Fail(400, "Паспорт: неверный ключ")
        if value is not None and (not isinstance(value, str) or len(value.encode("utf-8")) > 180000):
            raise Fail(400, "Паспорт: неверное значение")
        kind, ident = key.split("|", 1)
        if kind in ("artists", "museums"):
            if not ident or len(ident) > 300 or value not in ("1", None):
                raise Fail(400, "Паспорт: неверная отметка")
        elif kind == "originals":
            if not POST_ID_RE.fullmatch(ident) or value not in ("1", None):
                raise Fail(400, "Паспорт: неверная картина")
        elif kind == "collections":
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,70}", ident):
                raise Fail(400, "Паспорт: неверная коллекция")
            if value is not None:
                try:
                    d = json.loads(value)
                except (TypeError, ValueError):
                    raise Fail(400, "Паспорт: неверный JSON коллекции")
                works = d.get("works", []) if isinstance(d, dict) else None
                if (not isinstance(d, dict) or not isinstance(d.get("name"), str)
                    or not 1 <= len(d["name"].strip()) <= 60
                    or not isinstance(d.get("description", ""), str)
                    or len(d.get("description", "")) > 500
                    or not isinstance(d.get("cover", ""), str)
                    or (d.get("cover") and not POST_ID_RE.fullmatch(d["cover"]))
                    or not isinstance(works, list) or len(works) > 3000
                    or any(not isinstance(w, str) or not POST_ID_RE.fullmatch(w) for w in works)):
                    raise Fail(400, "Паспорт: неверная коллекция")
        elif kind == "collection_work":
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,70}\\|[A-Za-z0-9_-]{1,40}", ident):
                raise Fail(400, "Паспорт: неверная связь картины и коллекции")
            if value is not None and (not re.fullmatch(r"[1-9][0-9]{0,4}", value)
                                      or int(value) > 3000):
                raise Fail(400, "Паспорт: неверный порядок картины")
        elif kind in ("visits", "sightings", "exhibitions"):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,70}", ident):
                raise Fail(400, "Паспорт: неверный идентификатор события")
            if value is not None:
                if len(value.encode("utf-8")) > 10000:
                    raise Fail(400, "Паспорт: заметка слишком длинная")
                try:
                    d = json.loads(value)
                except (TypeError, ValueError):
                    raise Fail(400, "Паспорт: неверный JSON события")
                if not isinstance(d, dict):
                    raise Fail(400, "Паспорт: неверное событие")
                date = d.get("date", "")
                if not isinstance(date, str) or (date and not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", date)):
                    raise Fail(400, "Паспорт: неверная дата")
                if kind == "visits":
                    if (not isinstance(d.get("museum"), str) or len(d["museum"]) > 300
                        or not isinstance(d.get("exhibition", ""), str)
                        or len(d.get("exhibition", "")) > 160
                        or not isinstance(d.get("note", ""), str)
                        or len(d.get("note", "")) > 2000):
                        raise Fail(400, "Паспорт: неверное посещение")
                elif kind == "sightings":
                    if (not isinstance(d.get("work"), str) or not POST_ID_RE.fullmatch(d["work"])
                        or not isinstance(d.get("museum", ""), str)
                        or len(d.get("museum", "")) > 300
                        or not isinstance(d.get("note", ""), str)
                        or len(d.get("note", "")) > 2000):
                        raise Fail(400, "Паспорт: неверный оригинал")
                else:
                    if (not isinstance(d.get("status"), str)
                        or d["status"] not in ("want", "visited")
                        or not isinstance(d.get("note", ""), str)
                        or len(d.get("note", "")) > 1000):
                        raise Fail(400, "Паспорт: неверный статус выставки")
        else:
            raise Fail(400, "Паспорт: неизвестный тип записи")
        result.append((key, value))
    return result


'''


def patch_backend(content: str) -> str:
    if MARK in content:
        return content
    if 'OPA PASSPORT CLOUD SYNC' not in content:
        raise RuntimeError('Cloud sync v2 is not installed in cloud/auth/index.py')
    start = content.find('def validate_passport_changes(changes):')
    end = content.find('def clean_ids(values, limit=MAX_LIKES):', start)
    if start < 0 or end < 0:
        raise RuntimeError('Passport validator not found in cloud/auth/index.py')
    content = content[:start] + VALIDATOR + content[end:]
    return '# ' + MARK + '\n' + content


def patch_artist(content: str) -> str:
    if MARK in content:
        return content
    content = one(content, 'from .posts import card_html',
        'from .posts import card_html\nfrom .passport_ids import get_passport_id', 'Artists import')
    content = one(content, 'data-passport-key="{h(artist)}"',
        'data-passport-key="{get_passport_id(\'artists\', artist)}"', 'Artists stable key')
    return '# ' + MARK + '\n' + content


def patch_museum(content: str) -> str:
    if MARK in content:
        return content
    content = one(content, 'from .posts import card_html',
        'from .posts import card_html\nfrom .passport_ids import get_passport_id', 'Museums import')
    content = one(content, 'data-passport-key="{h(name)}"',
        'data-passport-key="{get_passport_id(\'museums\', name)}"', 'Museums stable key')
    content = one(content, '<a href="passport.html#museums">Мой арт-паспорт</a>',
        '<a href="passport.html#museums">Мой арт-паспорт</a><a href="passport.html#visits">Дневник</a>',
        'Museum diary link')
    return '# ' + MARK + '\n' + content


def patch_posts(content: str) -> str:
    if MARK in content:
        return content
    content = one(content, '<a href="passport.html?add={h(post_id)}#collections">В мою коллекцию</a>',
        '<button type="button" data-passport-add-work="{h(post_id)}" '
        'data-work-title="{h(post.get(\'title\') or \'\')}">В мою коллекцию</button>',
        'In-page add to collection button')
    return '# ' + MARK + '\n' + content


def patch_privacy(content: str) -> str:
    if MARK in content:
        return content
    content = one(content,
        'Нужен для синхронизации между устройствами лайков, любимых художников, музеев, просмотренных оригиналов и личных коллекций.',
        'Нужен для синхронизации лайков, музейного дневника, любимых художников, посещённых музеев, оригиналов, планов выставок и личных коллекций.',
        'Privacy account description')
    content = one(content,
        '    <li>избранные художники, отмеченные посещённые музеи, просмотренные оригиналы и личные коллекции (названия и состав) — отдельно, в защищённых для каждого аккаунта строках YDB;</li>',
        '    <li>любимые художники, посещённые музеи, даты визитов, впечатления и заметки, увиденные оригиналы, статусы выставок и личные коллекции — отдельно, в строках YDB каждого аккаунта;</li>',
        'Privacy YDB description')
    if 'на карте собраний, страницах музеев и в афише — подложки Яндекс Карт, OpenStreetMap и Esri.' in content:
        content = content.replace(
            'на карте собраний, страницах музеев и в афише — подложки Яндекс Карт, OpenStreetMap и Esri.',
            'на карте собраний, страницах музеев, в афише и на карте арт-паспорта — подложки Яндекс Карт, OpenStreetMap и Esri.', 1)
    return '# ' + MARK + '\n' + content


def prepare():
    plans = {}
    for name in ASSETS:
        source = SRC / name
        if not source.is_file():
            raise RuntimeError('Missing packaged asset: ' + str(source))
        content = source.read_text('utf-8')
        if name.endswith('.py'):
            ast.parse(content, filename=name)
        plans[name] = content
    for name in SOURCE_FILES:
        target = ROOT/name
        if not target.is_file():
            raise RuntimeError('Missing repository file: ' + name)
        old = target.read_text('utf-8')
        if 'OPA PERSONAL ART PASSPORT' not in old and name not in ('sitebuild/static.py','cloud/auth/index.py'):
            raise RuntimeError('Old art passport is missing: ' + name)
        patch = {
            'cloud/auth/index.py':patch_backend,
            'sitebuild/artists.py':patch_artist,
            'sitebuild/museums.py':patch_museum,
            'sitebuild/posts.py':patch_posts,
            'sitebuild/static.py':patch_privacy,
        }[name]
        updated = patch(old)
        ast.parse(updated, filename=name)
        plans[name] = updated
    for name in ('docs/passport.js','docs/passport-actions.js'):
        if 'OPAArtPassport' not in plans['docs/passport-actions.js']:
            raise RuntimeError('Passport JS validation failed')
    return plans


def apply(plans):
    changes = {name: content for name,content in plans.items()
               if not (ROOT/name).exists() or (ROOT/name).read_text('utf-8') != content}
    if not changes:
        print('Art passport v3 is already installed.')
        return
    backup = ROOT.parent/(ROOT.name+'_backup_passport_v3_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False)
    existing = [name for name in changes if (ROOT/name).is_file()]
    for name in existing:
        dest = backup/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,dest)
    written=[]
    try:
        for name,content in changes.items():
            dest=ROOT/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            fd,tmp=tempfile.mkstemp(prefix='.passport_v3_',suffix='.tmp',dir=dest.parent)
            try:
                with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
                    f.write(content)
                os.replace(tmp,dest)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            written.append(name)
    except BaseException:
        for name in written:
            if name in existing:
                shutil.copy2(backup/name,ROOT/name)
            else:
                (ROOT/name).unlink(missing_ok=True)
        raise
    print('Updated:',', '.join(changes))
    print('Backup:',backup)
    print('NEXT: redeploy cloud/auth/index.py to existing opa-auth Cloud Function')
    print('Then: python rebuild_pages.py --offline')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true')
    mode.add_argument('--apply',action='store_true')
    opts=parser.parse_args()
    try:
        plans=prepare()
        if opts.check:
            print('OK: project compatible, '+str(len(plans))+' files ready; no changes made.')
        else:
            apply(plans)
    except (RuntimeError,SyntaxError,OSError) as exc:
        parser.exit(2,'ERROR: '+str(exc)+'\n')


if __name__=='__main__':
    main()
