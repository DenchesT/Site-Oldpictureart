# -*- coding: utf-8 -*-
"""Offline validation for the incremental upgrade and backend schema."""
import ast
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('upgrader', ROOT/'apply_passport_upgrade_v3.py')
upgrader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrader)


class BackendValidators(unittest.TestCase):
    def setUp(self):
        class Fail(Exception):
            def __init__(self, status, message):
                self.status = status
                super().__init__(message)
        self.Fail = Fail
        namespace = {'POST_ID_RE':re.compile(r'^[0-9A-Za-z_-]{1,40}$'),
                     'Fail':Fail,'json':json,'re':re}
        exec(upgrader.VALIDATOR, namespace)
        self.validate = namespace['validate_passport_changes']

    def test_collection_memberships_and_order(self):
        valid = [('collection_work|c-aa|p001','1'),('collection_work|c-aa|p002','2'),
                 ('collection_work|c-aa|p003',None)]
        rows = [{'key':k,'value':v} for k,v in valid]
        self.assertEqual(self.validate(rows),valid)
        for bad in ['0','-1','3001','hello','1;DROP TABLE','999999']:
            with self.assertRaises(self.Fail):
                self.validate([{'key':'collection_work|c-aa|p001','value':bad}])

    def test_visits_and_sightings(self):
        valid=[
          {'key':'visits|v-test','value':json.dumps({'museum':'m_1','date':'2026-11-08','exhibition':'Осень','note':'Музей'})},
          {'key':'sightings|s-test','value':json.dumps({'work':'p001','date':'2026-11-08','museum':'m_1','note':''})},
          {'key':'exhibitions|exh_abc','value':json.dumps({'status':'want','date':'','note':'Хочу'})}
        ]
        self.assertEqual(len(self.validate(valid)),3)
        invalid=[
          {'key':'visits|x','value':json.dumps({'museum':'m_1','date':'not a date'})},
          {'key':'sightings|x','value':json.dumps({'work':'invalid|id','date':''})},
          {'key':'exhibitions|x','value':json.dumps({'status':'injected','date':''})},
          {'key':'wat|x','value':'1'},
          {'key':'collections|c','value':json.dumps({'name':'','works':[]})},
        ]
        for row in invalid:
            with self.subTest(row=row),self.assertRaises(self.Fail):
                self.validate([row])

    def test_existing_legacy_collections_still_valid(self):
        val=json.dumps({'name':'Старая коллекция','works':['p001','p002']})
        self.assertEqual(len(self.validate([{'key':'collections|c-old','value':val}])),1)
        modern=json.dumps({'name':'Новая','description':'Тест','cover':'p001'})
        self.assertEqual(len(self.validate([{'key':'collections|c-new','value':modern}])),1)

    def test_python_sources_syntax(self):
        for f in (ROOT/'sitebuild/passport.py',ROOT/'sitebuild/passport_ids.py',ROOT/'apply_passport_upgrade_v3.py'):
            ast.parse(f.read_text('utf-8'),filename=str(f))


if __name__=='__main__':
    unittest.main()
