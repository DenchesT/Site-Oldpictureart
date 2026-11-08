'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../docs/passport-actions.js'),'utf8');
function device(cloud,account='yandex:1'){
  const db=new Map();let fail=false;
  const payload=Buffer.from(JSON.stringify({u:account,exp:9999999999})).toString('base64url');
  db.set('session',JSON.stringify({token:payload+'.signature',provider:'yandex',exp:9999999999}));
  const ctx={
    Event:class{constructor(type){this.type=type;}},
    localStorage:{getItem(k){return db.has(k)?db.get(k):null;},setItem(k,v){db.set(k,String(v));},removeItem(k){db.delete(k);}},
    document:{readyState:'loading',addEventListener(){}},
    dispatchEvent(){},addEventListener(){},
    getSession(){return JSON.parse(db.get('session'));},
    CLOUD:{on:true},console:{warn(){}},setTimeout(fn){return 1;},clearTimeout(){},
    cloudCall(action,{changes}){
      if(fail)return Promise.reject(Error('network error'));
      assert.equal(action,'passport_sync');
      let table=cloud.get(account);if(!table){table=new Map();cloud.set(account,table);}
      changes.forEach(({key,value})=>{if(value===null)table.delete(key);else table.set(key,value);});
      return Promise.resolve({entries:[...table.entries()]});
    },
    atob(x){return Buffer.from(x,'base64').toString('utf8');}
  };
  ctx.window=ctx;
  vm.runInNewContext(code,ctx,{filename:'passport-actions.js'});
  return {api:ctx.OPAArtPassport,db,offline(x){fail=x;},ctx};
}
async function tests(){
 const cloud=new Map(),a=device(cloud),b=device(cloud);
 a.api.setCatalog({aliases:{artists:{'Старое имя':'a_fixed'},museums:{'Старый музей':'m_fixed'}}});
 // Import a legacy record; now migrating names does not lose it.
 a.db.set(a.api.storageKey(),JSON.stringify({artists:['Старое имя'],museums:['Старый музей'],originals:['p001'],
   collections:[{id:'c-first',name:'Пейзажи',works:['p001']}]}));
 let st=a.api.read();assert.equal(st.artists[0],'a_fixed');assert.equal(st.museums[0],'m_fixed');
 await a.api.sync();
 assert.ok(cloud.get('yandex:1').has('collections|c-first'));
 assert.ok(cloud.get('yandex:1').has('collection_work|c-first|p001'));
 await b.api.sync();assert.ok(b.api.read().collections[0].works.includes('p001'));
 // Two devices go offline and add separate paintings to the same collection.
 a.offline(true);b.offline(true);
 st=a.api.read();st.collections[0].works.push('p002');a.api.write(st);
 st=b.api.read();st.collections[0].works.push('p003');b.api.write(st);
 a.offline(false);b.offline(false);
 await a.api.sync();await b.api.sync();await a.api.sync();
 assert.deepEqual([...a.api.read().collections[0].works].sort(),['p001','p002','p003']);
 // New diary, originals, exhibition plans sync and stay account private.
 st=a.api.read();st.visits.push({id:'v-one',museum:'m_fixed',date:'2026-11-08',exhibition:'Осень',note:'Красиво'});
 st.sightings.push({id:'s-one',work:'p001',date:'2026-11-08',museum:'m_fixed',note:'Был там'});
 st.exhibitions.push({id:'exh_abc',status:'want',date:'',note:'Сходить'});
 a.api.write(st);await a.api.sync();await b.api.sync();
 assert.equal(b.api.read().visits[0].note,'Красиво');
 assert.equal(b.api.read().sightings[0].work,'p001');
 assert.equal(b.api.read().exhibitions[0].status,'want');
 // Remove one membership on device B, refresh from A.
 st=b.api.read();st.collections[0].works=st.collections[0].works.filter(x=>x!=='p003');b.api.write(st);
 await b.api.sync();await a.api.sync();assert.ok(!a.api.read().collections[0].works.includes('p003'));
 // Unknown archive entries survive normalization/import.
 st=a.api.read();st.artists.push('a_no_longer_catalog');st.originals.push('p_missing');
 a.api.write(st);await a.api.sync();await b.api.sync();
 assert.ok(b.api.read().artists.includes('a_no_longer_catalog'));
 assert.ok(b.api.read().originals.includes('p_missing'));
 const c=device(cloud,'vk:2');await c.api.sync();assert.equal(c.api.read().visits.length,0);
 // Migration of a legacy remote cloud collection with embedded works.
 const cloud2=new Map([['yandex:1',new Map([['collections|old',JSON.stringify({name:'Legacy',works:['p101','p102']})]])]]);
 const migrant=device(cloud2);await migrant.api.sync();
 assert.deepEqual([...migrant.api.read().collections[0].works].sort(),['p101','p102']);
 const entry=JSON.parse(cloud2.get('yandex:1').get('collections|old'));
 assert.ok(!Object.hasOwn(entry,'works'));
 assert.equal(cloud2.get('yandex:1').get('collection_work|old|p101'),'1');
 console.log('PASS passport v3 sync: migration, concurrent membership, deletion, diary, privacy, archive');
}
tests().catch(e=>{console.error(e);process.exit(1);});
