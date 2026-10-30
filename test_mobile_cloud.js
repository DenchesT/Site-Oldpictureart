'use strict';
// Browser-independent behavior tests with an in-memory stand-in for the existing cloud API.
const fs = require('fs'), vm = require('vm'), path = require('path');
const { execFileSync } = require('child_process');
const base = path.join(__dirname, 'apply_mobile_favorites.py');
// The Python installer stores the exact shared JS to avoid code drift in tests.
const src = execFileSync('python', ['-c',
  "import sys;sys.path.insert(0,sys.argv[1]);import apply_mobile_favorites as x;print(x.SHARED_FAVORITES_JS)",
  __dirname], {encoding:'utf8'});
const assert = require('assert');
const remote = new Map();
const local = new Map();
let current = 'ya:111', connected = true, session = true;
const b64 = name => Buffer.from(JSON.stringify({u:name,n:'Проверка'}),'utf8').toString('base64url');
const ctx = {
  console, Promise, Set, Object, JSON, String, Date, atob,
  CLOUD: {on: true},
  localStorage: {
    getItem: k => local.has(k) ? local.get(k) : null,
    setItem: (k,v) => local.set(k,String(v)),
    removeItem: k => local.delete(k)
  },
  window: {OPA_AFISHA_CATALOG: {
      'a-one': {key:'exh_'+'a'.repeat(32),title:'Выставка A',venue:'Музей',end:'2026-12-01'},
      'a-two': {key:'exh_'+'b'.repeat(32),title:'Выставка B',venue:'Музей',end:'2026-12-31'},
  }, dispatchEvent:()=>{}},
  Event: class Event {constructor(name){this.type=name;}},
  getSession:()=>session ? {token:b64(current)+'.sig'} : null,
  cloudCall: async (action,data) => {
    if(!connected) throw Error('offline');
    let set = remote.get(current); if(!set){set = new Set(['123']);remote.set(current,set);}
    if(action==='like') set.add(data.post_id);
    if(action==='unlike') set.delete(data.post_id);
    if(action==='sync') {for(let k of data.likes||[]) set.add(k);return {likes:[...set]};}
    return {ok:true};
  }
};
vm.createContext(ctx);
vm.runInContext(src,ctx);
(async()=>{
  const click = async(id,liked)=>{ctx.setAfishaFavorite(id,liked);await ctx.syncAfishaFavorites();};
  await click('a-one',true);
  assert(ctx.readAfishaFavorites()['a-one']);
  assert(remote.get('ya:111').has('exh_'+'a'.repeat(32)));
  // Second device: an empty local browser reads the cloud and sees the saved star.
  local.delete('afishaFavorites');local.delete('afishaFavoritesPending');
  await ctx.syncAfishaFavorites();
  assert(ctx.readAfishaFavorites()['a-one']);
  await click('a-one',false);
  assert(!remote.get('ya:111').has('exh_'+'a'.repeat(32)));
  // Offline changes must remain in pending storage for a later sync.
  connected=false;await click('a-two',true);
  assert(ctx.readAfishaFavorites()['a-two']);
  assert(ctx.readAfishaFavoritePending()['a-two']);
  connected=true;await ctx.syncAfishaFavorites();
  assert(remote.get('ya:111').has('exh_'+'b'.repeat(32)));
  // Separate accounts cannot inherit favorites of another signed-in user.
  current='vk:222'; await ctx.syncAfishaFavorites();
  assert(!ctx.readAfishaFavorites()['a-two']);
  assert(!remote.get('vk:222').has('exh_'+'b'.repeat(32)));
  // Works without an account, still saved in browser.
  session=false;ctx.setAfishaFavorite('a-one',true);
  assert(ctx.readAfishaFavorites()['a-one']);
  console.log('OK  cloud: save → sync on other device → remove → retry offline → account isolation → guest');
})().catch(e=>{console.error(e);process.exit(1)});
