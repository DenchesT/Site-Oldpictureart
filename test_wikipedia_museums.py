# -*- coding: utf-8 -*-
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("opa_museums",ROOT/"import_wikipedia_museums.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_data():
    seed=m.seeds()
    assert len(seed)==113, len(seed)
    assert len({m.identity(i['museum']) for i in seed})==113
    assert all(x['wikipedia_url'].startswith('https://ru.wikipedia.org/wiki/') for x in seed)
    reviewed=m.apply_reviewed(seed)
    assert len(reviewed)==115 # 113 direct + Tretyakov + Russian Museum
    assert sum(bool(x.get('address')) for x in reviewed)==18
    assert all(x['url'].startswith('https://') and x['address_source'].startswith('https://') for x in reviewed if x.get('address'))
    sources,a,u=m.merge_sources([{'museum':'Музей Академии художеств','url':'https://museum.example/','priority':'high'}],reviewed)
    assert a==114 and u==1 and len(sources)==115
    assert next(x for x in sources if x['museum']=='Музей Академии художеств')['url']=='https://museum.example/'
    ev=json.loads((ROOT/'verified_exhibitions.json').read_text(encoding='utf-8'))
    assert len(ev)==5
    old=[{'title':ev[0]['title'],'venue':ev[0]['venue'],'city':ev[0]['city']}, {'title':'Старая выставка','venue':'А','city':'Москва'}]
    merged,added,skip=m.merge_exhibitions(old,ev)
    assert len(merged)==6 and len(added)==4 and len(skip)==1
    for item in ev:
        from datetime import date
        assert date.fromisoformat(item['start'])<=date.fromisoformat(item['end'])
        assert set(['title','venue','city','country','start','end','url']).issubset(item)
        assert item['source'].startswith('https://')
    print('OK: источник, 113 статей, 18 проверенных адресов, 5 выставок, отсутствие дублей')


def test_installer():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'afisha.json'
        original={'_как':'test','updated':'2026-10-30','sources':[{'museum':'Музей Академии художеств','url':'https://museum.example/','priority':'high'}],
                  'exhibitions':[{'title':'Старая выставка','venue':'Музей','city':'Москва','country':'Россия','start':'2026-01-01','end':'2026-12-31','url':'https://museum.example/old'}]}
        path.write_text(json.dumps(original,ensure_ascii=False),encoding='utf-8')
        command=[sys.executable,str(ROOT/'import_wikipedia_museums.py'),'--file',str(path)]
        pre=path.read_bytes()
        check=subprocess.run(command+['--check'],capture_output=True,text=True)
        assert check.returncode==0,check.stderr
        assert path.read_bytes()==pre
        res=subprocess.run(command+['--apply'],capture_output=True,text=True)
        assert res.returncode==0,res.stderr
        data=json.loads(path.read_text(encoding='utf-8'))
        assert data['updated']=='2026-10-31'
        assert len(data['sources'])==115 # 113 + 2 verified extras, one alias duplicates existing
        assert len(data['exhibitions'])==6
        assert data['_как']==original['_как']
        assert path.with_name(path.name+'.pre_wikipedia_museums.bak').read_bytes()==pre
        after=path.read_bytes()
        res=subprocess.run(command+['--apply'],capture_output=True,text=True)
        assert res.returncode==0,res.stderr
        assert path.read_bytes()==after, 'Повторное применение изменило файл'
        print('OK: --check не пишет, --apply обновляет, бэкап, повторное применение безопасно')

if __name__=='__main__':
    test_data();test_installer()
