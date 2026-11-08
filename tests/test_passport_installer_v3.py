# -*- coding: utf-8 -*-
"""Smoke-test upgrade patching, idempotency and no partial writes on --check."""
import ast
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('upgrade',ROOT/'apply_passport_upgrade_v3.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)

class InstallerTests(unittest.TestCase):
 def test_patches_syntax(self):
  originals={
   'cloud/auth/index.py':'''# OPA PASSPORT CLOUD SYNC\nimport re\nimport json\ndef validate_passport_changes(changes):\n    return changes\n\ndef clean_ids(values, limit=MAX_LIKES):\n    return values\n''',
   'sitebuild/artists.py':'''# OPA PERSONAL ART PASSPORT\nfrom .posts import card_html\ndef r(artist):\n    return f\'''data-passport-key="{h(artist)}"\'''\n''',
   'sitebuild/museums.py':'''# OPA PERSONAL ART PASSPORT\nfrom .posts import card_html\ndef r(name):\n    return f\'''data-passport-key="{h(name)}" <a href="passport.html#museums">Мой арт-паспорт</a>\'''\n''',
   'sitebuild/posts.py':'''# OPA PERSONAL ART PASSPORT\ndef r(post, post_id):\n    return f\'''<a href="passport.html?add={h(post_id)}#collections">В мою коллекцию</a>\'''\n''',
   'sitebuild/static.py':'''# OPA PASSPORT CLOUD SYNC\ndef r():\n    return \'''Нужен для синхронизации между устройствами лайков, любимых художников, музеев, просмотренных оригиналов и личных коллекций.\n    <li>избранные художники, отмеченные посещённые музеи, просмотренные оригиналы и личные коллекции (названия и состав) — отдельно, в защищённых для каждого аккаунта строках YDB;</li>\'''\n'''
  }
  patches={'cloud/auth/index.py':u.patch_backend,'sitebuild/artists.py':u.patch_artist,
           'sitebuild/museums.py':u.patch_museum,'sitebuild/posts.py':u.patch_posts,'sitebuild/static.py':u.patch_privacy}
  for name,src in originals.items():
   with self.subTest(name=name):
    out=patches[name](src);ast.parse(out,filename=name)
    self.assertIn(u.MARK,out)
    self.assertEqual(out,patches[name](out))
    self.assertNotEqual(src,out)
  # Emulate a clean on-disk --check and --apply without a real repo.
  with tempfile.TemporaryDirectory() as t:
   before_root,before_src=u.ROOT,u.SRC
   try:
    u.ROOT=Path(t);u.SRC=u.ROOT/'upgrade_payload'
    for path,content in originals.items():
     target=u.ROOT/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,'utf-8')
    for path in u.ASSETS:
     target=u.SRC/path;target.parent.mkdir(parents=True,exist_ok=True)
     shutil.copy2(ROOT/path,target)
    plans=u.prepare();self.assertEqual(len(plans),10)
    self.assertEqual((u.ROOT/'sitebuild/posts.py').read_text('utf-8'),originals['sitebuild/posts.py'])
    u.apply(plans)
    self.assertIn(u.MARK,(u.ROOT/'sitebuild/posts.py').read_text('utf-8'))
    self.assertIn('collection_work',(u.ROOT/'cloud/auth/index.py').read_text('utf-8'))
    self.assertTrue((u.ROOT/'sitebuild/passport_ids.py').is_file())
    self.assertEqual(u.prepare(),plans)
   finally:
    u.ROOT,u.SRC=before_root,before_src

if __name__=='__main__':unittest.main()
