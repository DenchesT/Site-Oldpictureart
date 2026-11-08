/* Deterministic browser+cloud emulation. Run node tests/test_passport_cloud.js */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('docs/passport-actions.js','utf8');
const remote = new Map();
const token = (id) => Buffer.from(JSON.stringify({u:'yandex:'+id})).toString('base64url')+'.sig';
function device(id, online = true) {
  const values = new Map(), listeners = {};
  const storage = {getItem:k=>values.has(k)?values.get(k):null,
    setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k)};
  const ses = {token:token(id),provider:'yandex',name:'User',exp:Math.floor(Date.now()/1000)+5000};
  values.set('session',JSON.stringify(ses));
  const events=[];
  const win = {localStorage:storage,
    document:{readyState:'loading',addEventListener:(n,cb)=>{listeners['doc:'+n]=cb},querySelectorAll:()=>[]},
    addEventListener:(n,cb)=>{listeners[n]=cb},dispatchEvent:(e)=>{events.push(e.type)},
    Event:class {constructor(type){this.type=type}},
    atob:s=>Buffer.from(s,'base64').toString('binary')};
  const context={window:win,localStorage:storage,Event:win.Event,atob:win.atob,
    setTimeout:()=>1,clearTimeout:()=>{},JSON,Date,Math,Array,String,Promise,Map,Set,
    CLOUD:{on:true},getSession:()=>JSON.parse(values.get('session')||'null'),
    cloudCall:async(action, req)=>{
      assert.equal(action,'passport_sync');
      if (!online) throw Error('offline');
      const account = JSON.parse(Buffer.from(JSON.parse(values.get('session')).token.split('.')[0], 'base64url').toString()).u;
      let rows=remote.get(account);
      if (!rows) remote.set(account,rows=new Map());
      for(const row of req.changes) {
        if(row.value===null) rows.delete(row.key);else rows.set(row.key,row.value);
      }
      return {entries:Array.from(rows.entries())};
    }};
  vm.runInNewContext(code,context,{filename:'passport-actions.js'});
  return {api:win.OPAArtPassport,values,events,
          online:v=>{online=v},signIn:(n)=>values.set('session',JSON.stringify({...ses,token:token(n)})),
          signOut:()=>values.delete('session')};
}
(async()=>{
  const a=device('A');
  a.api.toggle('artists','Клод Моне');
  a.api.toggle('museums','Эрмитаж');
  a.api.toggle('originals','123');
  a.api.write({...a.api.read(),collections:[{id:'c-abc',name:'Избранное море',works:['123','456']}]});
  assert.equal(await a.api.sync(),true);
  const b=device('A');
  assert.equal(await b.api.sync(),true);
  assert.equal(b.api.selected('artists','Клод Моне'),true);
  assert.equal(b.api.selected('originals','123'),true);
  assert.equal(b.api.read().collections[0].name,'Избранное море');
  b.api.toggle('museums','Эрмитаж'); // delete propagated
  let changed=b.api.read(); changed.collections[0].name='Море и берег';
  changed.collections[0].works=['456'];
  b.api.write(changed);
  assert.equal(await b.api.sync(),true);
  assert.equal(await a.api.sync(),true);
  assert.equal(a.api.read().museums.includes('Эрмитаж'),false);
  assert.equal(a.api.read().collections[0].works[0],'456');
  assert.equal(a.api.read().collections[0].name,'Море и берег');
  b.online(false);
  b.api.toggle('artists','Клод Моне'); // remove offline
  b.api.toggle('originals','789'); // mark offline
  assert.equal(await b.api.sync(),false);
  assert.equal(b.api.status,'error');
  assert.equal(b.api.selected('originals','789'),true);
  b.online(true);
  assert.equal(await b.api.sync(),true);
  assert.equal(await a.api.sync(),true);
  assert.equal(a.api.selected('artists','Клод Моне'),false);
  assert.equal(a.api.selected('originals','789'),true);
  // guest data claims only the first logged-in account.
  const c=device('C');
  c.signOut();c.api.toggle('artists','Серов');
  c.signIn('C');
  assert.equal(await c.api.sync(),true);
  assert.equal(c.api.selected('artists','Серов'),true);
  c.signIn('D');
  assert.equal(await c.api.sync(),true);
  assert.equal(c.api.selected('artists','Серов'),false);
  const d=device('D');
  assert.equal(await d.api.sync(),true);
  assert.equal(d.api.selected('artists','Серов'),false);
  // Collections are removed from the cloud rather than reappearing on another device.
  a.api.write({...a.api.read(),collections:[]});
  assert.equal(await a.api.sync(),true);
  assert.equal(await b.api.sync(),true);
  assert.equal(b.api.read().collections.length,0);
  console.log('Art passport cloud sync (2 devices/offline/delete/accounts): OK');
})().catch(e=>{console.error(e);process.exitCode=1});
