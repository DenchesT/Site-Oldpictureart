"""Tests for local-only patch logic; run with python test_local_update.py."""
import copy
import json
from pathlib import Path
from apply_local_update import compute

p=json.loads(Path(__file__).with_name('proposal.json').read_text(encoding='utf-8'))
ends={'Иван Шишкин. Русский лес':'2026-11-09', 'Виктор Борисов-Мусатов. Гармония образа':'2026-11-08',
      'Хрупкое искусство. Пастель из фондов графики XVIII — начала XX века':'2026-11-01',
      'Елизаветинская Библия':'2026-11-01',
      'Семь историй сотворения мира. К 50-летию реставрации Гатчинского дворца':'2026-11-08',
      'Сказка рядом':'2026-11-08',
      'От Возрождения до Модерна. Шедевры художественного серебра из собрания Исторического музея':'2026-11-08',
      'Алмазная колесница. Буддийское искусство России':'2026-11-01',
      'Я, Гюстав Курбе. Художник и бунтарь':'2026-11-08',
      '78-я выставка сокровищ Сёсоина':'2026-11-09',
      'Николай Хохряков. Поэзия природы':'2026-11-07',
      'Окрестности Санкт-Петербурга в гравюрах и литографиях XIX века':'2026-11-02'}
ex=[{'title':k,'start':'2026-01-01','end':v,'custom':{'unchanged':True}} for k,v in ends.items()]
ex += [{'title':c['title'],'start':'2026-11-06','end':'2027-06-06'} for c in p['existing_exhibition_fixes']]
ex += [{'title':f'Дополнительная запись {i}','end':'2027-12-31'} for i in range(191-len(ex))]
src=[{'museum':f'Other {i}'} for i in range(1,127)]
for c in p['source_fixes']:
    src[c['index']-1]['museum']=c['museum']
    if c['index']==103: src[c['index']-1]['url']='https://new.yarartmuseum.ru/exhibitions/'
    if c['index']==125:src[c['index']-1].update({'url':'https://tretyakov.ru/','site':'https://tretyakov.ru/'})
main={'exhibitions':ex,'sources':src,'untouched_data':['keep']}
arc={'exhibitions':[copy.deepcopy(x) for x in ex if x['title'] in {y['title'] for y in p['archive_candidates'] if y.get('already_in_archive')}],'untouched_data':'keep'}
new,archive,res=compute(main,arc,p)
assert len(new['exhibitions'])==186 and len(archive['exhibitions'])==9
assert len(res['new'])==4 and len(res['updated'])==5 and len(res['source_updated'])==14
assert len(res['archive_added'])==6 and len(res['archive_overlap_removed'])==3
assert len(res['unconfirmed_left'])==3 and len(new['sources'])==126
assert new['untouched_data']==['keep'] and archive['untouched_data']=='keep'
assert len(res['warnings'])==0, res['warnings']
assert next(x for x in archive['exhibitions'] if x['title'].startswith('Семь историй'))['start']=='2026-06-07'
n2,a2,r2=compute(new,archive,p)
assert n2==new and a2==archive, 'Repeated processing must be idempotent'
full,full_arc,res3=compute(main,arc,p,include_unconfirmed=True)
assert len(full['exhibitions'])==183 and len(full_arc['exhibitions'])==12
print('OK: 4 new, 5 changed, 6 confirmed new archives, 3 duplicate removals, 14 sources, 126 intact, idempotence')
