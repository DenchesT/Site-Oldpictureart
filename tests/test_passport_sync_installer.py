# -*- coding: utf-8 -*-
"""Smoke test that patches are syntactically valid without touching the repository."""
import ast
import unittest
# The repository runner executes this file by path, not as a package.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apply_passport_cloud_sync import patch_backend,patch_pages,patch_privacy,patch_account_dialog

class InstallerTests(unittest.TestCase):
    def test_backend_patch(self):
        source='''import re
import json
class Fail(Exception):
    def __init__(self,*args):pass
POST_ID_RE = re.compile(r"^[0-9A-Za-z_-]{1,40}$")
MAX_LIKES=5000
class YdbStore:
    def counts(self):pass
def clean_ids(values, limit=MAX_LIKES):return values
def act(req):
    action=req.get('action')
    if action not in ("sync", "like", "unlike", "delete"):
        raise Fail(400,'bad')
    who = read_token(req.get("token"))["u"]
    db = store()
    if action == "sync":
        cloud = db.list(who)
    db.clear(who)            # delete
'''
        updated=patch_backend(source)
        ast.parse(updated)
        self.assertIn('passport_sync',updated)
        self.assertIn('db.passport_clear(who)',updated)
        self.assertEqual(updated,patch_backend(updated))
    def test_page_scripts(self):
        source='''# OPA PERSONAL ART PASSPORT 2026-11-08
from something import (site_footer, COMMON_JS, SCROLL_TOP_JS,)
content="""{COMMON_JS}
<script src="passport-actions.js" defer></script>"""
'''
        ast.parse(patch_pages(source,'sitebuild/artists.py'))
    def test_privacy(self):
        source='''S="""Нужен только для одного — чтобы отмеченные картины были на всех ваших устройствах.
    <li>имя — только в вашем браузере, чтобы показать его на кнопке; на сервер оно не записывается.</li>
    <li>номер аккаунта у Яндекса или VK и список отмеченных картин со временем отметки —
Отметки вошедших дублируются в облако (см. выше), остальное"""
'''
        ast.parse(patch_privacy(source))
    def test_account_text(self):
        source='''S="""Чтобы избранные картины и выставки были доступны на телефоне и компьютере.
. Избранные картины и выставки видны на всех ваших устройствах.',
      actionButton(box, 'auth-provider', 'Выйти', function () {
'Удалить мои отметки из облака'
toast('Отметки удалены из облака; в этом браузере они остались');"""
'''
        ast.parse(patch_account_dialog(source))

if __name__ == '__main__':unittest.main()
