/* node tests/test_passport_actions.js — no browser/network needed */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const values = new Map();
const storage = {getItem:k=>values.has(k)?values.get(k):null,
  setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k)};
const listeners = {};
const window = {
  localStorage:storage,
  document:{readyState:'loading',addEventListener:(event,fn)=>{listeners[event]=fn},querySelectorAll:()=>[]},
  addEventListener:()=>{},dispatchEvent:()=>{},Event:class{constructor(name){this.type=name;}},
  atob:s=>Buffer.from(s,'base64').toString('binary'),
};
const code=fs.readFileSync('docs/passport-actions.js','utf8');
vm.runInNewContext(code,{window,localStorage:storage,Event:window.Event,atob:window.atob,JSON,Date,Math,Array,String,Promise});
const passport=window.OPAArtPassport;
assert.equal(passport.owner(),'guest');
assert.equal(passport.selected('artists','Моне'),false);
assert.equal(passport.toggle('artists','Моне'),true);
assert.equal(passport.selected('artists','Моне'),true);
assert.equal(passport.toggle('artists','Моне'),true);
assert.equal(passport.selected('artists','Моне'),false);
passport.toggle('museums','Эрмитаж');
passport.toggle('originals','101');
let state=passport.read();
assert.deepEqual(Array.from(state.museums),['Эрмитаж']);
assert.deepEqual(Array.from(state.originals),['101']);
const token=Buffer.from(JSON.stringify({u:'person-1'})).toString('base64url')+'.signature';
values.set('session',JSON.stringify({token,provider:'yandex',exp:Math.floor(Date.now()/1000)+5000}));
assert.equal(passport.owner(),'account:yandex:person-1');
assert.equal(passport.read().museums.length,0,'visitor records must not leak between accounts');
passport.toggle('museums','Лувр');
values.delete('session');
assert.equal(passport.read().museums[0],'Эрмитаж');
const invalid=passport.normalize({artists:['A','A',1],museums:'not array',originals:['1','1'],collections:[
  {id:'c1',name:'test',works:['1','1',2]}, {id:'c1',name:'duplicate',works:['2']}]});
assert.deepEqual(Array.from(invalid.artists),['A']);
assert.deepEqual(Array.from(invalid.originals),['1']);
assert.equal(invalid.collections.length,1);
assert.deepEqual(Array.from(invalid.collections[0].works),['1']);
console.log('Art passport action tests: OK');
