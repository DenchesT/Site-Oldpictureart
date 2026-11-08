# -*- coding: utf-8 -*-
"""Backend validation and account-isolation checks (offline, no YDB connection)."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / 'cloud/auth/index.py'


class FakeStore:
    def __init__(self):
        self.records = {}
        self.likes = {}
    def passport_apply(self, who, changes):
        own = self.records.setdefault(who,{})
        for k,v in changes:
            if v is None: own.pop(k,None)
            else:own[k]=v
    def passport_list(self, who):
        return list(self.records.get(who,{}).items())
    def passport_clear(self, who):
        self.records.pop(who,None)
    def clear(self, who):
        self.likes.pop(who,None)


@unittest.skipUnless(TARGET.exists(), 'Install cloud/auth/index.py before running tests')
class PassportBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('opa_passport_backend_for_test',TARGET)
        cls.server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.server)
    def test_change_validation(self):
        validate=self.server.validate_passport_changes
        valid=[{'key':'artists|Клод Моне','value':'1'},
               {'key':'museums|Эрмитаж','value':None},
               {'key':'originals|42','value':'1'},
               {'key':'collections|c-abc','value':'{"name":"Моя коллекция","works":["42"]}'}]
        self.assertEqual(4,len(validate(valid)))
        for invalid in ([{'key':'originals|45','value':'oops'}],
                        [{'key':'bogus|42','value':'1'}],
                        [{'key':'collections|bad','value':'{"name":"","works":[]}'}],
                        [{'key':'originals|123','value':'1'}]*41):
            with self.subTest(invalid=str(invalid)[:80]):
                with self.assertRaises(self.server.Fail):validate(invalid)
    def test_cloud_action_is_isolated_and_deletions_work(self):
        backend = self.server
        fake = FakeStore()
        actor='alice'
        with patch.object(backend,'store',return_value=fake),patch.object(backend,'read_token',side_effect=lambda t:{'u':t}):
            result=backend.act({'action':'passport_sync','token':actor,'changes':[
                {'key':'artists|Моне','value':'1'},
                {'key':'collections|c-1','value':'{"name":"Море","works":["42"]}'}]})
            self.assertEqual(len(result['entries']),2)
            self.assertEqual(backend.act({'action':'passport_sync','token':'bob','changes':[]})['entries'],[])
            backend.act({'action':'passport_sync','token':actor,'changes':[{'key':'artists|Моне','value':None}]})
            self.assertNotIn('artists|Моне',dict(backend.act({'action':'passport_sync','token':actor,'changes':[]})['entries']))
            backend.act({'action':'delete','token':actor})
            self.assertEqual(backend.act({'action':'passport_sync','token':actor,'changes':[]})['entries'],[])


if __name__ == '__main__':unittest.main()
