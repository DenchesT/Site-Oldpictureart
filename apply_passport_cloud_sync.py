# -*- coding: utf-8 -*-
"""Install YDB passport sync after the original art passport; no git or network.

Usage: python apply_passport_cloud_sync.py --check / --apply
The package includes the original art-passport installer for a clean checkout.
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
MARK = 'OPA PASSPORT CLOUD SYNC 2026-11-08'
FILES = ('cloud/auth/index.py', 'sitebuild/artists.py', 'sitebuild/museums.py', 'sitebuild/static.py', 'site_common.py')
ASSETS = ('docs/passport.js', 'docs/passport-actions.js', 'sitebuild/passport.py')


def one(s, before, after, reason):
    matches = s.count(before)
    if matches != 1:
        raise RuntimeError(f'{reason}: expected one match, found {matches}; nothing was changed.')
    return s.replace(before, after, 1)


VALIDATION = '''
# Passport records are private to the authenticated account. No user-supplied
# SQL identifiers or table names are accepted. A null payload removes a record.
def validate_passport_changes(changes):
    if not isinstance(changes, list) or len(changes) > 40:
        raise Fail(400, "Паспорт: слишком много изменений")
    result = []
    for item in changes:
        if not isinstance(item, dict):
            raise Fail(400, "Паспорт: неверная запись")
        key, value = item.get("key"), item.get("value")
        if not isinstance(key, str) or "|" not in key or len(key.encode("utf-8")) > 700:
            raise Fail(400, "Паспорт: неверный ключ")
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
                if not isinstance(value, str) or len(value.encode("utf-8")) > 150000:
                    raise Fail(400, "Паспорт: коллекция слишком велика")
                try:
                    doc = json.loads(value)
                except (ValueError, TypeError):
                    raise Fail(400, "Паспорт: неверное содержимое коллекции")
                if (not isinstance(doc, dict) or not isinstance(doc.get("name"), str)
                        or not 1 <= len(doc["name"].strip()) <= 60
                        or not isinstance(doc.get("works"), list)
                        or len(doc["works"]) > 3000
                        or any(not isinstance(p, str) or not POST_ID_RE.fullmatch(p)
                               for p in doc["works"])):
                    raise Fail(400, "Паспорт: неверные картины коллекции")
        else:
            raise Fail(400, "Паспорт: неизвестный тип записи")
        if value is not None and not isinstance(value, str):
            raise Fail(400, "Паспорт: неверное значение")
        result.append((key, value))
    return result

'''

STORAGE_METHODS = '''    # Private passport data uses a separate table, not the public likes counts.
    def passport_list(self, user):
        res = self._run([("DECLARE $u AS Utf8; "
                          "SELECT entry_key, payload FROM passport WHERE user_id = $u;",
                          {"$u": user})])
        rows = res[0][0].rows if res and res[0] else []
        return [[r.entry_key, r.payload] for r in rows]

    def passport_apply(self, user, changes):
        upsert = ("DECLARE $u AS Utf8; DECLARE $k AS Utf8; DECLARE $v AS Utf8; "
                  "UPSERT INTO passport (user_id, entry_key, payload, updated_at) "
                  "VALUES ($u, $k, $v, CurrentUtcTimestamp());")
        remove = ("DECLARE $u AS Utf8; DECLARE $k AS Utf8; "
                  "DELETE FROM passport WHERE user_id = $u AND entry_key = $k;")
        statements = []
        for key, value in changes:
            if value is None:
                statements.append((remove, {"$u": user, "$k": key}))
            else:
                statements.append((upsert, {"$u": user, "$k": key, "$v": value}))
        if statements:
            self._run(statements)

    def passport_clear(self, user):
        self._run([("DECLARE $u AS Utf8; DELETE FROM passport WHERE user_id = $u;",
                    {"$u": user})])

'''


def patch_backend(text):
    if MARK in text:
        return text
    text = one(text, '    def counts(self):', STORAGE_METHODS + '    def counts(self):', 'YDB methods')
    text = one(text, 'def clean_ids(values, limit=MAX_LIKES):',
               VALIDATION + 'def clean_ids(values, limit=MAX_LIKES):', 'Passport data validation')
    text = one(text, '    if action not in ("sync", "like", "unlike", "delete"):',
               '    if action not in ("sync", "like", "unlike", "delete", "passport_sync"):',
               'API action dispatch')
    text = one(text, '    if action == "sync":\n        cloud = db.list(who)',
               '    if action == "passport_sync":\n'
               '        changes = validate_passport_changes(req.get("changes", []))\n'
               '        db.passport_apply(who, changes)\n'
               '        return {"entries": db.passport_list(who)}\n'
               '    if action == "sync":\n        cloud = db.list(who)',
               'API passport sync')
    text = one(text, '    db.clear(who)            # delete',
               '    db.clear(who)            # delete\n    if hasattr(db, "passport_clear"):\n        db.passport_clear(who)',
               'Account deletion')
    return f'# {MARK}\n' + text


def patch_pages(text, path):
    if MARK in text:
        return text
    text = one(text, 'site_footer, COMMON_JS, SCROLL_TOP_JS,',
               'site_footer, COMMON_JS, CLOUD_JS, SCROLL_TOP_JS,', 'CLOUD_JS import '+path)
    if path.endswith('artists.py'):
        text = one(text, '{COMMON_JS}\n<script src="passport-actions.js" defer></script>',
                   '{COMMON_JS}\n{CLOUD_JS}\n<script src="passport-actions.js" defer></script>',
                   'Cloud script for artists')
    else:
        text = one(text, '{map_js}\n<script src="passport-actions.js" defer></script>',
                   '{map_js}\n{CLOUD_JS}\n<script src="passport-actions.js" defer></script>',
                   'Cloud script for museums')
    return f'# {MARK}\n' + text



def patch_privacy(text):
    if MARK in text:
        return text
    text = one(text,
        'Нужен только для одного — чтобы отмеченные картины были на всех ваших устройствах.',
        'Нужен для синхронизации между устройствами лайков, любимых художников, музеев, просмотренных оригиналов и личных коллекций.',
        'Privacy account description')
    text = one(text,
        '    <li>имя — только в вашем браузере, чтобы показать его на кнопке; на сервер оно не записывается.</li>',
        '    <li>избранные художники, отмеченные посещённые музеи, просмотренные оригиналы и личные коллекции (названия и состав) — отдельно, в защищённых для каждого аккаунта строках YDB;</li>\n'
        '    <li>имя — только в вашем браузере, чтобы показать его на кнопке; на сервер оно не записывается.</li>',
        'Privacy list of stored records')
    text = one(text,
        '    <li>номер аккаунта у Яндекса или VK и список отмеченных картин со временем отметки —',
        '    <li>номер аккаунта у Яндекса или VK и список отмеченных картин и выставок со временем отметки —',
        'Privacy favorites')
    text = one(text,
        'Отметки вошедших дублируются в облако (см. выше), остальное',
        'Отметки вошедших, любимые художники, музеи, оригиналы и коллекции дублируются в облако (см. выше), остальное',
        'Privacy local copies')
    return f'# {MARK}\n' + text



def patch_account_dialog(text):
    if MARK in text:
        return text
    text=one(text,
        'Чтобы избранные картины и выставки были доступны на телефоне и компьютере.',
        'Чтобы избранное и личный арт-паспорт были доступны на телефоне и компьютере.',
        'Login modal explanation')
    text=one(text,
        ". Избранные картины и выставки видны на всех ваших устройствах.',",
        ". Избранное и арт-паспорт синхронизируются между устройствами.',",
        'Account modal explanation')
    text=one(text,
        "      actionButton(box, 'auth-provider', 'Выйти', function () {",
        "      actionButton(box, 'auth-provider', 'Мой арт-паспорт', function () {\n"
        "        location.href = 'passport.html';\n"
        "      });\n"
        "      actionButton(box, 'auth-provider', 'Выйти', function () {",
        'Profile shortcut')
    text=one(text,
        "'Удалить мои отметки из облака'",
        "'Удалить мои данные из облака'",
        'Cloud deletion label')
    text=one(text,
        "toast('Отметки удалены из облака; в этом браузере они остались');",
        "toast('Облачные отметки и паспорт удалены; локальная копия осталась');",
        'Cloud deletion confirmation')
    return f'# {MARK}\n'+text


def prepare():
    if not (ROOT/'sitebuild/passport.py').is_file() or not (ROOT/'apply_art_passport.py').is_file():
        raise RuntimeError('Unzip the complete package into the repository root.')
    for asset in ASSETS:
        if not (ROOT/asset).is_file():
            raise RuntimeError('Missing asset: '+asset)
    plans = {}
    for name in FILES:
        path = ROOT/name
        if not path.is_file():
            raise RuntimeError('Missing repository source: '+name)
        original = path.read_text(encoding='utf-8')
        if name.endswith('index.py'):
            updated = patch_backend(original)
        elif name.endswith('static.py'):
            updated = patch_privacy(original)
        elif name == 'site_common.py':
            updated = patch_account_dialog(original)
        else:
            if 'OPA PERSONAL ART PASSPORT' not in original:
                raise RuntimeError(name+' not modified by the first art passport installer. Run that installer first.')
            updated = patch_pages(original,name)
        ast.parse(updated,filename=name)
        plans[name] = original, updated
    ast.parse((ROOT/'sitebuild/passport.py').read_text('utf-8'), filename='sitebuild/passport.py')
    return plans


def apply(plans):
    changed={k:v for k,v in plans.items() if v[0]!=v[1]}
    if not changed:
        print('Cloud passport sync is already installed.')
        return
    backup=ROOT.parent/(ROOT.name+'_backup_passport_cloud_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False)
    for name in changed:
        target=backup/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,target)
    written=[]
    try:
        for name,(_before,after) in changed.items():
            dest=ROOT/name
            fd,tmp=tempfile.mkstemp(prefix='.passport_cloud_',suffix='.tmp',dir=dest.parent)
            try:
                with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:f.write(after)
                os.replace(tmp,dest)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
            written.append(name)
    except Exception:
        for name in written:shutil.copy2(backup/name,ROOT/name)
        raise
    print('Cloud sync enabled in:',', '.join(changed))
    print('Backup:',backup)
    print('Next: create YDB passport table and deploy cloud/auth/index.py; see README.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check',action='store_true')
    g.add_argument('--apply',action='store_true')
    opts=p.parse_args()
    try:
        plans=prepare()
        if opts.check:
            for path, (before,after) in plans.items():print(('Installed: ' if before==after else 'Ready: ')+path)
            print('No files changed; no network requests.')
        else:apply(plans)
    except (OSError,ValueError,RuntimeError,SyntaxError) as e:
        print('ERROR:',e)
        return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
