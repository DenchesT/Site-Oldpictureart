# -*- coding: utf-8 -*-
"""Browser smoke test without any network or real user credentials."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
js_core=(ROOT/'docs/passport-actions.js').read_text('utf-8')
js_page=(ROOT/'docs/passport.js').read_text('utf-8')
css=(ROOT/'docs/passport.css').read_text('utf-8')
items={
  'works':[{'id':'p001','title':'Лунная ночь','artist':'Иван Айвазовский','museum':'Русский музей','year':'1850','thumb':'','href':'p001.html'},
           {'id':'p002','title':'Вечер','artist':'Иван Айвазовский','museum':'Эрмитаж','year':'1860','thumb':'','href':'p002.html'}],
  'artists':[{'id':'a_art','name':'Иван Айвазовский','href':'artist.html'}],
  'museums':[{'id':'m_russian','name':'Русский музей','href':'museum.html','lat':59.93,'lon':30.33,'city':'Санкт-Петербург','country':'Россия'},
             {'id':'m_hermitage','name':'Эрмитаж','href':'hermitage.html','lat':59.94,'lon':30.31,'city':'Санкт-Петербург','country':'Россия'}],
  'exhibitions':[{'id':'a-test','key':'exh_abcd','title':'Встреча с живописью','venue':'Русский музей','city':'Санкт-Петербург','end':'2027-02-08'}],
  'aliases':{'artists':{'Иван Айвазовский':'a_art'},'museums':{'Русский музей':'m_russian','Эрмитаж':'m_hermitage'}}
}
tabs=[('overview','Обзор'),('visits','Дневник'),('artists','Художники'),('museums','Музеи'),('originals','Оригиналы'),('collections','Коллекции'),('exhibitions','Выставки'),('map','Карта'),('timeline','Хронология'),('stats','Статистика')]
nav=''.join(f'<button data-tab="{k}" type="button" aria-pressed="false">{v}</button>' for k,v in tabs)
html=f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{{--text:#222;--text-2:#555;--muted:#666;--border:#bbb;--card-bg:#fff;--panel:#eee;--active:#9d7440;--on-active:#fff;--shadow:#aaa;--shadow-strong:#999;--history-bg:#faf5ed;--accent-soft:#f4ead8;--link:#785026;--rule-soft:#ddd;--ff-text:Georgia;--ff-data:Arial;--fs-sm:14px;--fs-xs:12px;--fs-base:16px;--error:red}}
body{{margin:0;font-family:Arial;background:#f7f7f7}}{css}</style></head><body class="passport-page">
<main class="passport-main"><header class="passport-header"><div><h1>Мой арт-паспорт</h1><p id="passport-owner"></p></div></header>
<div class="passport-info passport-syncbar"><span id="passport-sync-text"></span><button id="passport-sync-button">Синхронизировать</button></div>
<section id="passport-stats" class="passport-stats"></section><nav class="passport-tabs">{nav}</nav>
<section id="passport-panel" class="passport-panel"></section><button id="passport-export">Экспорт JSON</button>
<input type="file" id="passport-import"><p id="passport-feedback"></p></main>
<script>history.replaceState=function(){{}}; Object.defineProperty(window,'localStorage',{{configurable:true,value:(function(){{let d={{}};return {{getItem:k=>d[k]??null,setItem:(k,v)=>d[k]=String(v),removeItem:k=>delete d[k]}};}})()}});
window.OPA_PASSPORT_DATA={json.dumps(items,ensure_ascii=False)};
window.cloudSync=function(){{return Promise.resolve(false)}};window.syncAfishaFavorites=function(){{return Promise.resolve(false)}};
</script><script>{js_core}</script><script>{js_page}</script></body></html>'''

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for mobile,width in [(False,1280),(True,390)]:
        page=browser.new_page(viewport={'width':width,'height':900})
        errors=[]
        page.on('pageerror', lambda error:errors.append(str(error)))
        page.set_content(html,wait_until='load')
        assert page.locator('#passport-stats .passport-stat').count()==6,errors
        page.locator('button[data-tab="visits"]').click()
        page.locator('button:has-text("Добавить посещение")').click()
        page.locator('dialog select').first.select_option('m_russian')
        page.locator('dialog button:has-text("Сохранить")').click()
        assert 'Русский музей' in page.locator('#passport-panel').inner_text(),errors
        page.locator('button[data-tab="collections"]').click()
        page.locator('text=Создать коллекцию').click()
        page.locator('dialog input[type="text"]').fill('Мои пейзажи')
        page.locator('dialog button:has-text("Сохранить")').click()
        assert 'Мои пейзажи' in page.locator('#passport-panel').inner_text(),errors
        page.locator('button:has-text("+ Картины")').click()
        page.locator('dialog button:has-text("+ Добавить")').first.click()
        page.locator('dialog button[aria-label="Закрыть"]').click()
        assert page.locator('.passport-work-card').count()==1,errors
        page.locator('button[data-tab="exhibitions"]').click()
        page.locator('text=+ В планы').click()
        page.locator('dialog button:has-text("Сохранить")').click()
        assert 'Встреча с живописью' in page.locator('#passport-panel').inner_text(),errors
        page.locator('button[data-tab="stats"]').click()
        assert page.locator('.passport-chart').count()==5,errors
        page.locator('button[data-tab="timeline"]').click()
        assert 'Русский музей' in page.locator('#passport-panel').inner_text(),errors
        page.locator('button[data-tab="map"]').click()
        assert 'Карта моих музеев' in page.locator('#passport-panel').inner_text(),errors
        page.locator('button[data-tab="museums"]').click()
        search=page.locator('.passport-search')
        search.fill('Эрм')
        assert page.locator('.passport-dir-row').count()==1,errors
        assert search.input_value()=='Эрм'
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),errors
        assert not errors,errors
        outfile=ROOT/('preview_mobile_v3.png' if mobile else 'preview_desktop_v3.png')
        page.screenshot(path=str(outfile),full_page=True)
        print('PASS browser viewport',width)
        page.close()
    browser.close()
