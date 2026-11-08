# -*- coding: utf-8 -*-
"""Registry stability and explicit rename alias behavior."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('passport_ids',ROOT/'sitebuild/passport_ids.py')
ids=importlib.util.module_from_spec(spec);spec.loader.exec_module(ids)

class RegistryTests(unittest.TestCase):
 def test_persistent_ids_and_manual_alias(self):
  oldpath,oldcache,olddirty=ids.PATH,ids._cache,ids._dirty
  try:
   with tempfile.TemporaryDirectory() as d:
    ids.PATH=Path(d)/'passport_registry.json';ids._cache=None;ids._dirty=False
    a=ids.get_passport_id('artists','Иван Иванов');m=ids.get_passport_id('museums','Эрмитаж')
    self.assertNotEqual(a,m);ids.save_passport_registry()
    self.assertTrue(ids.PATH.exists())
    original=json.loads(ids.PATH.read_text('utf-8'))
    self.assertEqual(original['artists']['Иван Иванов'],a)
    # Rename: explicitly assign immutable ID of the old record to its new name.
    original['artists']['И. Иванов']=a
    ids.PATH.write_text(json.dumps(original,ensure_ascii=False),'utf-8')
    ids._cache=None
    self.assertEqual(ids.get_passport_id('artists','И. Иванов'),a)
    self.assertEqual(ids.get_passport_id('artists','Иван Иванов'),a)
  finally:
   ids.PATH,ids._cache,ids._dirty=oldpath,oldcache,olddirty

if __name__=='__main__':unittest.main()
