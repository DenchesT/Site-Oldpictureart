/* Old Picture Art art passport v2 — local-first, per-account YDB synchronization.
   The creator's published visits are never treated as a reader's visits. */
(function (root) {
  'use strict';
  var BASE = 'opaPassport:v1:'; // Keep v1 data: no migration or data loss.
  var PENDING = 'opaPassport:pending:v2:';
  var READY = 'opaPassport:synced:v2:';
  var EMPTY = {artists: [], museums: [], originals: [], collections: []};
  var KINDS = ['artists', 'museums', 'originals'];
  var busy = null, schedule = null, status = 'local';
  function storeGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function storeSet(key, value) { try { localStorage.setItem(key, value); return true; } catch (e) { return false; } }
  function owner() {
    try {
      var s = JSON.parse(storeGet('session') || 'null');
      if (!s || !s.token || !(s.exp * 1000 > Date.now())) return 'guest';
      var part = s.token.split('.')[0].replace(/-/g, '+').replace(/_/g, '/');
      part += '='.repeat((4 - part.length % 4) % 4);
      var d = JSON.parse(atob(part));
      if (!d.u || !s.provider) return 'guest';
      return 'account:' + s.provider + ':' + String(d.u);
    } catch (e) { return 'guest'; }
  }
  function storageKey() { return BASE + owner(); }
  function cleanArray(data, limit) {
    if (!Array.isArray(data)) return [];
    var out = [];
    data.forEach(function (item) {
      if (typeof item !== 'string' || !item || item.length > 300 || out.includes(item)) return;
      if (out.length < limit) out.push(item);
    });
    return out;
  }
  function normalize(raw) {
    var src = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
    var cols = [];
    if (Array.isArray(src.collections)) src.collections.slice(0, 50).forEach(function (c) {
      if (!c || typeof c !== 'object' || typeof c.name !== 'string' || typeof c.id !== 'string') return;
      var name = c.name.trim().slice(0, 60), id = c.id.slice(0, 70);
      if (!name || !/^[\w-]{1,70}$/.test(id) || cols.some(function(x){return x.id === id;})) return;
      cols.push({id: id, name: name, works: cleanArray(c.works, 3000)});
    });
    return {
      artists: cleanArray(src.artists, 1000),
      museums: cleanArray(src.museums, 1000),
      originals: cleanArray(src.originals, 3000),
      collections: cols
    };
  }
  function readKey(key) {
    try { return normalize(JSON.parse(storeGet(key) || '{}')); }
    catch (e) { return normalize(EMPTY); }
  }
  function read() { return readKey(storageKey()); }
  function records(data) {
    var m = Object.create(null), d = normalize(data);
    KINDS.forEach(function (kind) { d[kind].forEach(function (v) { m[kind + '|' + v] = '1'; }); });
    d.collections.forEach(function (c) {
      m['collections|' + c.id] = JSON.stringify({name:c.name, works:c.works});
    });
    return m;
  }
  function fromRecords(recordsMap) {
    var d = {artists:[], museums:[], originals:[], collections:[]};
    Object.keys(recordsMap || {}).forEach(function (k) {
      var pos = k.indexOf('|'); if (pos < 1) return;
      var kind = k.slice(0, pos), id = k.slice(pos + 1), raw = recordsMap[k];
      if (!raw || !id) return;
      if (KINDS.includes(kind)) { if (raw === '1') d[kind].push(id); }
      else if (kind === 'collections') {
        try { var val = JSON.parse(raw); d.collections.push({id:id, name:val.name, works:val.works}); }
        catch (e) { /* Skip malformed records. */ }
      }
    });
    return normalize(d);
  }
  function loadPending(who) {
    try {
      var v = JSON.parse(storeGet(PENDING + who) || '{}');
      return v && typeof v === 'object' && !Array.isArray(v) ? v : {};
    } catch (e) { return {}; }
  }
  function savePending(who, state) { return storeSet(PENDING + who, JSON.stringify(state)); }
  function notify() { root.dispatchEvent(new Event('opa:passport-change')); }
  function state(next) { status = next; root.OPAArtPassport.status = next; root.dispatchEvent(new Event('opa:passport-sync')); }
  function syncLater() {
    if (schedule !== null || owner() === 'guest' || typeof setTimeout !== 'function') return;
    schedule = setTimeout(function () { schedule = null; sync(); }, 350);
  }
  function write(data) {
    var clean = normalize(data), key = storageKey(), who = owner();
    var old = records(read()), current = records(clean), changes = loadPending(who);
    if (!storeSet(key, JSON.stringify(clean))) return false;
    if (who !== 'guest') {
      Object.keys(old).concat(Object.keys(current)).forEach(function(k) {
        if (old[k] !== current[k]) changes[k] = Object.prototype.hasOwnProperty.call(current,k) ? current[k] : null;
      });
      savePending(who, changes); syncLater();
    }
    notify(); return true;
  }
  function toggle(kind, id) {
    if (!KINDS.includes(kind) || !id) return false;
    id = String(id);
    var d = read(), i = d[kind].indexOf(id);
    if (i < 0) d[kind].push(id); else d[kind].splice(i,1);
    return write(d);
  }
  function selected(kind, id) { return KINDS.includes(kind) && read()[kind].includes(String(id)); }
  function seed(who) {
    if (storeGet(READY + who)) return;
    var original = readKey(BASE + who);
    // A guest passport is claimed just once and never copied to another account.
    if (storeGet('opaPassport:guestClaimed:v2') !== '1') {
      var guest = readKey(BASE + 'guest');
      var own = records(original), gl = records(guest);
      if (Object.keys(gl).length) {
        Object.keys(gl).forEach(function (k) { if (!Object.prototype.hasOwnProperty.call(own,k)) own[k]=gl[k]; });
        original = fromRecords(own);
        storeSet(BASE+who, JSON.stringify(original));
        storeSet('opaPassport:guestClaimed:v2', '1');
        notify();
      }
    }
    var pending = loadPending(who), all = records(original);
    Object.keys(all).forEach(function (k) {
      if (!Object.prototype.hasOwnProperty.call(pending,k)) pending[k] = all[k];
    });
    savePending(who,pending);
  }
  function mergeRows(rows, pending) {
    var m = Object.create(null);
    (Array.isArray(rows) ? rows : []).forEach(function(r) {
      if (Array.isArray(r) && typeof r[0] === 'string' && typeof r[1] === 'string') m[r[0]] = r[1];
    });
    Object.keys(pending).forEach(function(k) {
      if (pending[k] === null) delete m[k]; else m[k] = pending[k];
    });
    return fromRecords(m);
  }
  function cloudAvailable() {
    return owner() !== 'guest' && typeof cloudCall === 'function' &&
      typeof getSession === 'function' && !!getSession() &&
      typeof CLOUD !== 'undefined' && !!CLOUD.on;
  }
  function sync() {
    if (!cloudAvailable()) { state('local'); return Promise.resolve(false); }
    if (busy) return busy;
    var who = owner();
    seed(who);
    state('syncing');
    busy = (async function () {
      var steps=0, response=null;
      while (steps++ < 200) {
        if (owner() !== who) return false;
        var pending = loadPending(who);
        var keys = Object.keys(pending).slice(0, 40);
        var changes = keys.map(function(k){return {key:k, value:pending[k]};});
        response = await cloudCall('passport_sync', {changes:changes});
        if (owner() !== who) return false;
        var refreshed = loadPending(who);
        keys.forEach(function(k) {
          if (Object.prototype.hasOwnProperty.call(refreshed,k) && refreshed[k] === pending[k]) delete refreshed[k];
        });
        savePending(who,refreshed);
        if (!Array.isArray(response.entries)) throw Error('Облако вернуло неверный ответ');
        storeSet(BASE + who, JSON.stringify(mergeRows(response.entries, refreshed)));
        notify();
        // First successful read migrates existing v1 entries and marks account initialized.
        storeSet(READY + who, '1');
        if (!Object.keys(refreshed).length) { state('saved'); return true; }
      }
      throw Error('Слишком много изменений для одной синхронизации');
    })().catch(function(e) {
      state('error');
      if (typeof console !== 'undefined') console.warn('Арт-паспорт: облако недоступно:',e.message);
      return false;
    }).finally(function(){busy=null; if (owner() !== who && cloudAvailable()) syncLater();});
    return busy;
  }
  function syncButtons() {
    root.document.querySelectorAll('[data-opa-passport][data-passport-key]').forEach(function (btn) {
      var kind=btn.getAttribute('data-opa-passport'), id=btn.getAttribute('data-passport-key');
      if (!KINDS.includes(kind) || !id) return;
      var checked=selected(kind,id);
      btn.setAttribute('aria-pressed',checked?'true':'false');
      btn.textContent=checked ? (btn.getAttribute('data-label-on') || 'Убрать отметку') :
                                  (btn.getAttribute('data-label-off') || 'Отметить');
      btn.title=btn.textContent;
    });
  }
  root.OPAArtPassport = {owner:owner,storageKey:storageKey,normalize:normalize,
     read:read,write:write,toggle:toggle,selected:selected,sync:sync,status:status};
  function setup() {
    root.document.addEventListener('click',function(e){
      var btn=e.target.closest('[data-opa-passport][data-passport-key]');
      if (!btn) return;
      if (toggle(btn.getAttribute('data-opa-passport'),btn.getAttribute('data-passport-key'))) syncButtons();
    });
    root.addEventListener('opa:passport-change',syncButtons);
    root.addEventListener('storage',function(e){ if (!e.key || e.key.indexOf('opaPassport:')===0 || e.key==='session') {syncButtons();sync();} });
    root.addEventListener('online',sync);
    root.addEventListener('focus',sync);
    root.document.addEventListener('visibilitychange',function(){if (!root.document.hidden)sync();});
    syncButtons(); sync();
  }
  if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',setup);
  else setup();
})(window);
