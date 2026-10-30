# -*- coding: utf-8 -*-
"""Offline regression tests for installer and push recovery."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installer', BASE / 'apply_verified_fixes.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'sitebuild').mkdir()
        self.safety = self.root/'sitebuild/safety.py'
        self.safety.write_text('import logging\n\ndef publish_generated(root):\n'+installer.OLD_PUSH+'\n', encoding='utf-8')
        (self.root/'docs').mkdir()
        self.afisha_py = self.root/'sitebuild/afisha.py'
        # Realistic adjacent f-strings: reproduces SyntaxError from old ZIP.
        self.afisha_py.write_text("""from html import escape as h

def afisha_item(item, coords):
    return (
        f'<li class="afisha-item">'
        + f'<p class="afisha-where"><span>{h(item["venue"])}</span>'
        + ('<button type="button" class="afisha-pin">на карте</button>' if coords else '') + '</p>'
        f'<p class="afisha-dates"><span class="afisha-range">Сроки: {h(item["start"])}</span>'
        f'<span class="now-when afisha-when"></span></p>'
        + ('<p class="afisha-note">Примечание</p>' if item.get("note") else '')
        + '</li>'
    )

def check_afisha_links(items, today, offline=False, path=''):
    state = load_json(path, {})
    urls = sorted({it["url"] for it in items})
    return urls
""", encoding='utf8')
        self.css = self.root/'docs/style.css'
        self.css.write_text(':root { --ff-data: monospace; }\n',encoding='utf8')
        self.afisha = self.root/'afisha.json'
        names = [
            ('Музей Мармоттан-Моне','Париж'),
            ('Музей изящных искусств Бостона','Бостон'),
            ('ГМИИ Республики Татарстан, Галерея современного искусства','Казань'),
            ('Дом-музей Павла Кузнецова (филиал Радищевского музея)','Саратов'),
            ('Дом русского зарубежья им. А. Солженицына','Москва'),
        ]
        rows = [{'title':n, 'venue':n,'city':c,'country':'Россия','start':'2026-01-01','end':'2027-01-01',
                 'url':'https://example.org'} for n,c in names]
        rows[-1]['title']='Русский Париж. 1814–1914'
        rows[-1]['url']='https://www.domrz.ru/exhibition/70568_russkiy_parizh_1814_1914/'
        self.afisha.write_text(json.dumps({'updated':'2026-10-30','exhibitions':rows},ensure_ascii=False), encoding='utf8')
        self.museum = self.root/'museum_overrides.json'
        self.museum.write_text(json.dumps({
            'Государственный музей-заповедник "Ростовский Кремль"': {},
            'Новгородский музей заповедник':{},
            'Лондонская национальная галерея, Лондон':{},
            'Частная коллекция':{'skip':True}},ensure_ascii=False),encoding='utf8')
    def tearDown(self): self.tmp.cleanup()
    def test_dry_run_read_only(self):
        before = {p:p.read_bytes() for p in (self.safety,self.afisha,self.museum)}
        changed, report=installer.prepare(self.root)
        self.assertEqual(5,len(changed))
        self.assertEqual(5,report['matched_exhibitions'])
        self.assertEqual(before,{p:p.read_bytes() for p in before})
    def test_apply_idempotent_and_backups(self):
        changed,_=installer.prepare(self.root)
        installer.write_safely(changed,self.root)
        new, _=installer.prepare(self.root)
        self.assertFalse(new)
        self.assertTrue(list((self.root/'output'/'backups'/'sitebuild').glob('safety.py.bak_*')))
        d=json.loads(self.afisha.read_text(encoding='utf8'))
        self.assertEqual('2 rue Louis-Boilly, 75016 Paris, France',d['exhibitions'][0]['query'])
        self.assertEqual('https://www.domrz.ru/exhibition/70568_russkiy_parizh_1814_1914/', d['exhibitions'][-1]['url'])
        self.assertTrue(d['exhibitions'][-1]['skip_link_check'])
        scope = {'load_json': lambda path, default: default}
        exec(compile(self.afisha_py.read_text(encoding='utf8'), str(self.afisha_py), 'exec'), scope)
        self.assertIn('Адрес: 2 rue Louis-Boilly', scope['afisha_item'](d['exhibitions'][0], False))
        self.assertNotIn('domrz.ru', ' '.join(scope['check_afisha_links'](d['exhibitions'], None)))
        self.assertIn('afisha-address', self.afisha_py.read_text(encoding='utf8'))
        self.assertIn('.afisha-address', self.css.read_text(encoding='utf8'))
        o=json.loads(self.museum.read_text(encoding='utf8'))
        self.assertEqual('Кремль, 11, Великий Новгород, Россия',o['Новгородский музей заповедник']['address'])
    def test_status_role_variant_from_current_github(self):
        old = self.afisha_py.read_text(encoding='utf8')
        modified = old.replace(
            "f'<span class=\"now-when afisha-when\"></span></p>'",
            "f'<span class=\"now-when afisha-when\" role=\"status\"></span></p>'")
        self.assertNotEqual(old, modified)
        self.afisha_py.write_text(modified, encoding='utf8')
        changed, _ = installer.prepare(self.root)
        self.assertIn(self.afisha_py, changed)
        compile(changed[self.afisha_py], str(self.afisha_py), 'exec')
        installer.write_safely(changed, self.root)
        self.assertFalse(installer.prepare(self.root)[0])
        scope = {'load_json': lambda path, default: default}
        exec(compile(self.afisha_py.read_text(encoding='utf8'), str(self.afisha_py), 'exec'), scope)
        record = json.loads(self.afisha.read_text(encoding='utf8'))['exhibitions'][0]
        self.assertIn('Адрес:', scope['afisha_item'](record, False))

    def test_extra_status_attributes(self):
        old = self.afisha_py.read_text(encoding='utf8')
        modified = old.replace('class="now-when afisha-when"',
                               'class="now-when afisha-when" role="status" aria-live="polite"')
        self.afisha_py.write_text(modified, encoding='utf8')
        changed, _ = installer.prepare(self.root)
        self.assertIn('afisha-address', changed[self.afisha_py])
        compile(changed[self.afisha_py], str(self.afisha_py), 'exec')

    def test_unknown_page_structure_keeps_all_files_intact(self):
        old = self.afisha_py.read_text(encoding='utf8')
        self.afisha_py.write_text(old.replace('afisha-when', 'changed-by-user'), encoding='utf8')
        original = {p:p.read_bytes() for p in (self.safety, self.afisha,
                                                self.museum, self.afisha_py, self.css)}
        with self.assertRaisesRegex(RuntimeError, 'Не удалось безопасно'):
            installer.prepare(self.root)
        self.assertEqual(original, {p:p.read_bytes() for p in original})

    def test_refuse_unexpected_safety_version_without_writing(self):
        original='def publish_generated(root):\n    print("changed")\n'
        self.safety.write_text(original,encoding='utf8')
        with self.assertRaises(RuntimeError): installer.prepare(self.root)
        self.assertEqual(original,self.safety.read_text(encoding='utf8'))
    def test_complete_address_audit(self):
        ch,_=installer.prepare(self.root); installer.write_safely(ch,self.root)
        out=installer.audit(self.root)
        self.assertEqual([],out['museum_address_or_coordinates_problems'])
        self.assertIn('Частная коллекция',out['private_collections_without_pins'])

class PushRecoveryTests(unittest.TestCase):
    def test_real_git_non_fast_forward(self):
        # Real local bare remote: reproduce the user's rejected push offline.
        import logging
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); origin=root/'origin.git'; a=root/'one'; b=root/'two'
            def run(*args, cwd=None):
                return subprocess.run(['git',*args],cwd=cwd,check=True,stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,text=True).stdout.strip()
            run('init','-q','--bare','--initial-branch=main',str(origin))
            run('clone','-q',str(origin),str(a))
            run('config','user.name','Tester',cwd=a);run('config','user.email','a@example.invalid',cwd=a)
            (a/'init.txt').write_text('initial',encoding='utf8')
            run('add','init.txt',cwd=a);run('commit','-qm','initial',cwd=a);run('push','-q','origin','main',cwd=a)
            run('clone','-q',str(origin),str(b))
            run('config','user.name','Tester',cwd=b);run('config','user.email','b@example.invalid',cwd=b)
            (a/'remote.txt').write_text('remote commit',encoding='utf8')
            run('add','remote.txt',cwd=a);run('commit','-qm','remote edit',cwd=a);run('push','-q','origin','main',cwd=a)
            (b/'local.txt').write_text('local commit',encoding='utf8')
            run('add','local.txt',cwd=b);run('commit','-qm','local edit',cwd=b)
            calls=[]
            def git(*args):
                calls.append(args)
                try: return run(*args,cwd=b)
                except subprocess.CalledProcessError as exc:
                    raise RuntimeError('git '+str(args)+': '+exc.stderr) from exc
            scope={'logging':logging,'git':git,'RuntimeError':RuntimeError}
            exec(installer.HELPER,scope)
            scope['_push_reconciling_remote']()
            self.assertIn(('rebase','origin/main'),calls)
            self.assertEqual('local commit',(a.parent/'two'/'local.txt').read_text())
            self.assertIn('local.txt',run('--git-dir='+str(origin),'ls-tree','-r','--name-only','main'))
            self.assertIn('remote.txt',run('--git-dir='+str(origin),'ls-tree','-r','--name-only','main'))
    def test_retries_only_non_fast_forward(self):
        calls=[]
        def git(*args):
            calls.append(args)
            if args==('push',) and calls.count(('push',))==1:
                raise RuntimeError('non-fast-forward')
        import logging
        scope={'logging':logging,'git':git,'RuntimeError':RuntimeError}
        exec(installer.HELPER,scope)
        scope['_push_reconciling_remote']()
        self.assertEqual([('push',),('fetch','origin','main'),('rebase','origin/main'),('push',)],calls)
    def test_rebase_conflict_aborts_and_retains_commits(self):
        calls=[]
        def git(*args):
            calls.append(args)
            if args==('push',):raise RuntimeError('non-fast-forward')
            if args==('rebase','origin/main'):raise RuntimeError('conflict')
        import logging
        scope={'logging':logging,'git':git,'RuntimeError':RuntimeError}
        exec(installer.HELPER,scope)
        with self.assertRaisesRegex(RuntimeError,'Исходный локальный коммит сохранён'):
            scope['_push_reconciling_remote']()
        self.assertIn(('rebase','--abort'), calls)
    def test_other_push_errors_not_retried(self):
        calls=[]
        def git(*args):
            calls.append(args);raise RuntimeError('authentication failed')
        import logging
        scope={'logging':logging,'git':git,'RuntimeError':RuntimeError}
        exec(installer.HELPER,scope)
        with self.assertRaisesRegex(RuntimeError,'authentication failed'):scope['_push_reconciling_remote']()
        self.assertEqual([('push',)],calls)

if __name__=='__main__':unittest.main(verbosity=2)
