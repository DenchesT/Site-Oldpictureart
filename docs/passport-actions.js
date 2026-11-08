/* Old Picture Art — Art Passport v3. Keep v1 local records and v2 YDB keys. */
(function (root) {
  'use strict';
  var BASE='opaPassport:v1:', PENDING='opaPassport:pending:v2:', READY='opaPassport:synced:v2:';
  var CLAIM='opaPassport:guestClaimed:v2', LAST='opaPassport:lastSync:v3:';
  var KINDS=['artists','museums','originals'];
  var EMPTY={artists:[],museums:[],originals:[],collections:[],visits:[],sightings:[],exhibitions:[]};
  var catalog={artists:[],museums:[],aliases:{artists:{},museums:{}}};
  var busy=null, timer=null, status='local', lastError='';
  var API={};
  function get(k){try{return localStorage.getItem(k);}catch(e){return null;}}
  function set(k,v){try{localStorage.setItem(k,v);return true;}catch(e){return false;}}
  function parse(v,def){try{return JSON.parse(v);}catch(e){return def;}}
  function emit(name){if(root.dispatchEvent && typeof Event==='function')root.dispatchEvent(new Event(name));}
  function owner(){
    try{
      var s=parse(get('session'),null);
      if(!s||!s.token||!(s.exp*1000>Date.now()))return 'guest';
      var part=s.token.split('.')[0].replace(/-/g,'+').replace(/_/g,'/');
      part+='='.repeat((4-part.length%4)%4);
      var d=JSON.parse(atob(part));
      return d.u && s.provider ? 'account:'+s.provider+':'+String(d.u) : 'guest';
    }catch(e){return 'guest';}
  }
  function storageKey(){return BASE+owner();}
  function str(v,max){return typeof v==='string'?v.trim().slice(0,max):'';}
  function id(v){return typeof v==='string'&&/^[A-Za-z0-9_-]{1,70}$/.test(v)?v:'';}
  function cleanArray(a,cap){
    var seen=new Set(),out=[];
    if(!Array.isArray(a))return out;
    a.forEach(function(v){if(typeof v==='string'&&v&&v.length<=300&&!seen.has(v)&&out.length<cap){seen.add(v);out.push(v);}});
    return out;
  }
  function cleanDate(v){return /^\d{4}-\d{2}-\d{2}$/.test(v||'')?v:'';}
  function canonical(kind,v){
    var label=str(v,300), aliases=catalog.aliases&&catalog.aliases[kind]||{};
    return Object.prototype.hasOwnProperty.call(aliases,label) ? aliases[label] : label;
  }
  function normalize(raw){
    var d=raw&&typeof raw==='object'&&!Array.isArray(raw)?raw:{};
    var out={artists:cleanArray(d.artists,1000).map(function(v){return canonical('artists',v);}),
      museums:cleanArray(d.museums,1000).map(function(v){return canonical('museums',v);}),
      originals:cleanArray(d.originals,3000),collections:[],visits:[],sightings:[],exhibitions:[]};
    out.artists=cleanArray(out.artists,1000);out.museums=cleanArray(out.museums,1000);
    if(Array.isArray(d.collections))d.collections.slice(0,50).forEach(function(c){
      if(!c||!id(c.id)||!str(c.name,60)||out.collections.some(function(x){return x.id===c.id;}))return;
      out.collections.push({id:c.id,name:str(c.name,60),description:str(c.description,500),
        cover:id(c.cover),works:cleanArray(c.works,3000)});
    });
    if(Array.isArray(d.visits))d.visits.slice(0,2000).forEach(function(v){
      if(!v||!id(v.id))return;
      out.visits.push({id:v.id,museum:canonical('museums',v.museum),date:cleanDate(v.date),
        exhibition:str(v.exhibition,160),note:str(v.note,2000)});
    });
    if(Array.isArray(d.sightings))d.sightings.slice(0,3000).forEach(function(v){
      if(!v||!id(v.id)||!id(v.work))return;
      out.sightings.push({id:v.id,work:v.work,date:cleanDate(v.date),
        museum:canonical('museums',v.museum),note:str(v.note,2000)});
    });
    if(Array.isArray(d.exhibitions))d.exhibitions.slice(0,1500).forEach(function(v){
      if(!v||!id(v.id)||!['want','visited'].includes(v.status))return;
      out.exhibitions.push({id:v.id,status:v.status,date:cleanDate(v.date),note:str(v.note,1000)});
    });
    return out;
  }
  function readKey(k){return normalize(parse(get(k),{}));}
  function read(){return readKey(storageKey());}
  function records(raw){
    var d=normalize(raw),m=Object.create(null);
    KINDS.forEach(function(k){d[k].forEach(function(v){m[k+'|'+v]='1';});});
    d.collections.forEach(function(c){
      m['collections|'+c.id]=JSON.stringify({name:c.name,description:c.description,cover:c.cover});
      c.works.forEach(function(w,i){m['collection_work|'+c.id+'|'+w]=String(i+1);});
    });
    ['visits','sightings','exhibitions'].forEach(function(k){d[k].forEach(function(v){
      var doc=Object.assign({},v);delete doc.id;m[k+'|'+v.id]=JSON.stringify(doc);
    });});
    return m;
  }
  function fromRecords(map){
    var o={artists:[],museums:[],originals:[],collections:[],visits:[],sightings:[],exhibitions:[]};
    var byColl=Object.create(null),parts=[],ranks=Object.create(null);
    Object.keys(map||{}).forEach(function(k){
      var pos=k.indexOf('|');if(pos<1||map[k]===null||map[k]===undefined)return;
      var kind=k.slice(0,pos),ident=k.slice(pos+1),value=map[k];
      if(KINDS.includes(kind)&&value==='1'){o[kind].push(ident);return;}
      if(kind==='collection_work'){parts.push([ident,value]);return;}
      if(kind==='collections'){
        var c=parse(value,{});if(!id(ident)||!c||!c.name)return;
        var col={id:ident,name:c.name,description:c.description||'',cover:c.cover||'',works:cleanArray(c.works,3000)};
        byColl[ident]=col;o.collections.push(col);return;
      }
      if(['visits','sightings','exhibitions'].includes(kind)){
        var e=parse(value,null);if(e&&typeof e==='object'&&id(ident))o[kind].push(Object.assign({id:ident},e));
      }
    });
    parts.forEach(function(part){
      if(!/^\d{1,5}$/.test(part[1]))return;
      var i=part[0].indexOf('|');if(i<1)return;
      var c=byColl[part[0].slice(0,i)],w=part[0].slice(i+1);
      if(c&&w){ranks[c.id+'|'+w]=Number(part[1]);if(!c.works.includes(w))c.works.push(w);}
    });
    o.collections.forEach(function(c){c.works.sort(function(a,b){return (ranks[c.id+'|'+a]||99999)-(ranks[c.id+'|'+b]||99999) || a.localeCompare(b);});});
    return normalize(o);
  }
  function pending(who){var d=parse(get(PENDING+who),{});return d&&typeof d==='object'&&!Array.isArray(d)?d:{};}
  function storePending(who,p){return set(PENDING+who,JSON.stringify(p));}
  function setStatus(next,error){status=next;lastError=error||'';API.status=next;API.lastError=lastError;emit('opa:passport-sync');}
  function syncLater(){if(timer!==null||owner()==='guest'||typeof setTimeout!=='function')return;timer=setTimeout(function(){timer=null;sync();},450);}
  function write(raw){
    var data=normalize(raw),who=owner(),before=records(read()),after=records(data);
    var changes=pending(who);
    if(!set(BASE+who,JSON.stringify(data)))return false;
    if(who!=='guest'){
      new Set(Object.keys(before).concat(Object.keys(after))).forEach(function(k){
        if(before[k]!==after[k])changes[k]=Object.prototype.hasOwnProperty.call(after,k)?after[k]:null;
      });
      if(!storePending(who,changes))return false;
      syncLater();
    }
    emit('opa:passport-change');return true;
  }
  function toggle(kind, value){
    if(!KINDS.includes(kind)||!value)return false;
    var d=read(),key=kind==='artists'||kind==='museums'?canonical(kind,value):String(value);
    var i=d[kind].indexOf(key);if(i<0)d[kind].push(key);else d[kind].splice(i,1);
    return write(d);
  }
  function selected(kind,value){
    if(!KINDS.includes(kind))return false;
    var key=kind==='artists'||kind==='museums'?canonical(kind,value):String(value);
    return read()[kind].includes(key);
  }
  function setCatalog(next){
    var old=read();
    catalog=next||catalog;
    // Re-key old local labels without discarding unknown historical entries.
    var upgraded=normalize(old);
    if(JSON.stringify(old)!==JSON.stringify(upgraded)){
      var who=owner(),oldRows=Object.create(null),newRows=Object.create(null),pendingRows=pending(who);
      // Re-key only artist/museum records. Do NOT rewrite legacy collection
      // metadata here: its embedded works are migrated separately and safely.
      ['artists','museums'].forEach(function(k){
        old[k].forEach(function(v){oldRows[k+'|'+v]='1';});
        upgraded[k].forEach(function(v){newRows[k+'|'+v]='1';});
      });
      if(set(BASE+who,JSON.stringify(upgraded))&&who!=='guest'){
        Object.keys(oldRows).forEach(function(k){if(!newRows[k])pendingRows[k]=null;});
        Object.keys(newRows).forEach(function(k){if(!oldRows[k])pendingRows[k]=newRows[k];});
        storePending(who,pendingRows);syncLater();
      }
      emit('opa:passport-change');
    }
  }
  function seed(who){
    if(get(READY+who))return;
    var prior=readKey(BASE+who);
    if(get(CLAIM)!=='1'){
      var guest=readKey(BASE+'guest'),a=records(prior),b=records(guest);
      if(Object.keys(b).length){
        Object.keys(b).forEach(function(k){if(!Object.prototype.hasOwnProperty.call(a,k))a[k]=b[k];});
        prior=fromRecords(a);set(BASE+who,JSON.stringify(prior));set(CLAIM,'1');emit('opa:passport-change');
      }
    }
    var p=pending(who),all=records(prior);
    Object.keys(all).forEach(function(k){if(!Object.prototype.hasOwnProperty.call(p,k))p[k]=all[k];});
    storePending(who,p);
  }
  function migration(remote,waiting){
    // Migration of old cloud JSON collection. Unlike replacing a whole collection,
    // distinct collection_work records merge concurrent edits from two devices.
    Object.keys(remote).forEach(function(k){
      var pos=k.indexOf('|'),kind=k.slice(0,pos),old=k.slice(pos+1);
      if((kind==='artists'||kind==='museums')&&old){
        var stable=canonical(kind,old);
        if(stable!==old&&remote[k]==='1'){
          var dest=kind+'|'+stable;
          if(!Object.prototype.hasOwnProperty.call(remote,dest)&&!Object.prototype.hasOwnProperty.call(waiting,dest))waiting[dest]='1';
          if(!Object.prototype.hasOwnProperty.call(waiting,k))waiting[k]=null;
        }
      }
      if(kind==='collections'){
        var v=parse(remote[k],null);
        if(v&&Array.isArray(v.works)){
          v.works.forEach(function(w,i){
            var dest='collection_work|'+old+'|'+w;
            if(!Object.prototype.hasOwnProperty.call(remote,dest)&&!Object.prototype.hasOwnProperty.call(waiting,dest))waiting[dest]=String(i+1);
          });
          // Set membership records first: if the next request fails, legacy
          // embedded works still allow recovery on the following sync.
          var member=Object.keys(waiting).some(function(x){return x.indexOf('collection_work|'+old+'|')===0;});
          if(!member&&!Object.prototype.hasOwnProperty.call(waiting,k))
            waiting[k]=JSON.stringify({name:v.name,description:v.description||'',cover:v.cover||''});
        }
      }
    });
  }
  function toMap(rows){var map=Object.create(null);
    (Array.isArray(rows)?rows:[]).forEach(function(r){if(Array.isArray(r)&&typeof r[0]==='string'&&typeof r[1]==='string')map[r[0]]=r[1];});
    return map;
  }
  function merge(remote,waiting){var m=Object.assign(Object.create(null),remote);
    Object.keys(waiting).forEach(function(k){if(waiting[k]===null)delete m[k];else m[k]=waiting[k];});
    return fromRecords(m);
  }
  function cloudAvailable(){return owner()!=='guest'&&typeof cloudCall==='function'&&typeof getSession==='function'&&
    !!getSession()&&typeof CLOUD!=='undefined'&&!!CLOUD.on;}
  function sync(){
    if(!cloudAvailable()){setStatus('local');return Promise.resolve(false);}
    if(busy)return busy;
    var who=owner();seed(who);setStatus('syncing');
    busy=(async function(){
      for(var iteration=0;iteration<180;iteration++){
        if(owner()!==who)return false;
        var current=pending(who),keys=Object.keys(current).slice(0,40);
        var payload=keys.map(function(k){return {key:k,value:current[k]};});
        var response=await cloudCall('passport_sync',{changes:payload});
        if(owner()!==who)return false;
        if(!Array.isArray(response.entries))throw Error('Облако вернуло неверный ответ');
        var remote=toMap(response.entries),waiting=pending(who);
        keys.forEach(function(k){if(Object.prototype.hasOwnProperty.call(waiting,k)&&waiting[k]===current[k])delete waiting[k];});
        migration(remote,waiting);
        storePending(who,waiting);
        // Do not overwrite unseen local changes still waiting for upload.
        var updated=merge(remote,waiting);
        set(BASE+who,JSON.stringify(updated));emit('opa:passport-change');
        set(READY+who,'1');
        if(!Object.keys(waiting).length){
          set(LAST+who,new Date().toISOString());setStatus('saved');return true;
        }
      }
      throw Error('Слишком много изменений для синхронизации');
    })().catch(function(e){setStatus('error',e.message);if(root.console)console.warn('Арт-паспорт:',e.message);return false;})
      .finally(function(){busy=null;if(owner()!==who&&cloudAvailable())syncLater();});
    return busy;
  }
  function stateInfo(){return {status:status,error:lastError,pending:Object.keys(pending(owner())).length,lastSync:get(LAST+owner())||''};}
  function newId(prefix){
    if(root.crypto&&root.crypto.randomUUID)return prefix+root.crypto.randomUUID().replace(/-/g,'');
    return prefix+Date.now().toString(36)+Math.random().toString(36).slice(2,12);
  }
  function openDialog(title, content){
    var dialog=root.document.createElement('dialog');dialog.className='passport-modal';
    var header=root.document.createElement('div');header.className='passport-modal-header';
    var h=root.document.createElement('h2');h.textContent=title;
    var close=root.document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Закрыть');
    header.append(h,close);dialog.append(header,content);root.document.body.append(dialog);
    function dismiss(){if(dialog.open&&dialog.close)dialog.close();dialog.remove();}
    close.addEventListener('click',dismiss);
    dialog.addEventListener('click',function(e){if(e.target===dialog)dismiss();});
    dialog.addEventListener('close',function(){dialog.remove();});
    if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
    return {dialog:dialog,close:dismiss};
  }
  function collectionPicker(work,title){
    var body=root.document.createElement('div'),tip=root.document.createElement('p');
    tip.textContent='Добавить «'+(title||'картину')+'» в коллекцию:';body.append(tip);
    var list=root.document.createElement('div');list.className='passport-modal-choices';body.append(list);
    var form=root.document.createElement('form');form.className='passport-inline-form';
    var input=root.document.createElement('input');input.placeholder='Новая коллекция';input.maxLength=60;input.required=true;
    var create=root.document.createElement('button');create.type='submit';create.textContent='Создать и добавить';
    form.append(input,create);body.append(form);
    var modal=openDialog('Мои коллекции',body);
    function draw(){
      list.replaceChildren();var cols=read().collections;
      cols.forEach(function(c){
        var b=root.document.createElement('button');b.type='button';
        var active=c.works.includes(work);b.textContent=(active?'✓ ':'+ ')+c.name;
        b.setAttribute('aria-pressed',String(active));
        b.addEventListener('click',function(){var d=read(),target=d.collections.find(function(x){return x.id===c.id;});
          if(!target)return;var i=target.works.indexOf(work);
          if(i<0)target.works.push(work);else target.works.splice(i,1);
          if(write(d))draw();});
        list.appendChild(b);
      });
      if(!cols.length){var p=root.document.createElement('p');p.textContent='Коллекций пока нет. Создайте первую ниже.';list.appendChild(p);}
    }
    form.addEventListener('submit',function(e){e.preventDefault();var name=str(input.value,60);if(!name)return;
      var d=read();if(d.collections.length>=50)return;
      d.collections.unshift({id:newId('c-'),name:name,description:'',cover:work,works:[work]});
      if(write(d)){input.value='';draw();}
    });
    draw();return modal;
  }
  function syncButtons(){
    root.document.querySelectorAll('[data-opa-passport][data-passport-key]').forEach(function(b){
      var k=b.getAttribute('data-opa-passport'),v=b.getAttribute('data-passport-key');
      if(!KINDS.includes(k)||!v)return;
      var chosen=selected(k,v);b.setAttribute('aria-pressed',String(chosen));
      b.textContent=chosen?(b.getAttribute('data-label-on')||'Убрать отметку'):
        (b.getAttribute('data-label-off')||'Отметить');b.title=b.textContent;
    });
  }
  Object.assign(API,{owner:owner,storageKey:storageKey,normalize:normalize,read:read,write:write,
    toggle:toggle,selected:selected,sync:sync,setCatalog:setCatalog,records:records,fromRecords:fromRecords,
    stateInfo:stateInfo,newId:newId,openDialog:openDialog,collectionPicker:collectionPicker,status:status,lastError:lastError});
  root.OPAArtPassport=API;
  function setup(){
    root.document.addEventListener('click',function(e){
      var b=e.target.closest&&e.target.closest('[data-opa-passport][data-passport-key]');
      if(b){if(toggle(b.getAttribute('data-opa-passport'),b.getAttribute('data-passport-key')))syncButtons();return;}
      var a=e.target.closest&&e.target.closest('[data-passport-add-work]');
      if(a){collectionPicker(a.getAttribute('data-passport-add-work'),a.getAttribute('data-work-title')||root.document.title);}
    });
    root.addEventListener('opa:passport-change',syncButtons);
    root.addEventListener('storage',function(e){if(!e.key||e.key.startsWith('opaPassport:')||e.key==='session'){syncButtons();sync();}});
    root.addEventListener('online',sync);root.addEventListener('focus',sync);
    root.document.addEventListener('visibilitychange',function(){if(!root.document.hidden)sync();});
    syncButtons();sync();
  }
  if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',setup);else setup();
})(window);
