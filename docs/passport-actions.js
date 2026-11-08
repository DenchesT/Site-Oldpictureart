/* Old Picture Art personal passport: locally scoped state and buttons.
   Never interpret a creator's visits as a visitor's personal visits. */
(function (root) {
  'use strict';
  var BASE = 'opaPassport:v1:';
  var EMPTY = {artists: [], museums: [], originals: [], collections: []};
  function owner() {
    try {
      var s = JSON.parse(localStorage.getItem('session') || 'null');
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
      if (!name || !id || cols.some(function(x){return x.id === id;})) return;
      cols.push({id: id, name: name, works: cleanArray(c.works, 3000)});
    });
    return {
      artists: cleanArray(src.artists, 1000),
      museums: cleanArray(src.museums, 1000),
      originals: cleanArray(src.originals, 3000),
      collections: cols
    };
  }
  function read() {
    try { return normalize(JSON.parse(localStorage.getItem(storageKey()) || '{}')); }
    catch(e) { return normalize(EMPTY); }
  }
  function write(data) {
    var clean = normalize(data);
    try { localStorage.setItem(storageKey(), JSON.stringify(clean)); }
    catch(e) { return false; }
    root.dispatchEvent(new Event('opa:passport-change'));
    return true;
  }
  function toggle(kind, id) {
    if (!['artists', 'museums', 'originals'].includes(kind) || !id) return false;
    id = String(id);
    var data = read(), pos = data[kind].indexOf(id);
    if (pos < 0) data[kind].push(id); else data[kind].splice(pos, 1);
    return write(data);
  }
  function selected(kind, id) { return read()[kind].includes(String(id)); }
  function syncButtons() {
    root.document.querySelectorAll('[data-opa-passport][data-passport-key]').forEach(function(btn){
      var kind = btn.getAttribute('data-opa-passport');
      var id = btn.getAttribute('data-passport-key');
      if (!['artists','museums','originals'].includes(kind) || !id) return;
      var checked = selected(kind, id);
      btn.setAttribute('aria-pressed', checked ? 'true' : 'false');
      var on = btn.getAttribute('data-label-on') || 'Убрать отметку';
      var off = btn.getAttribute('data-label-off') || 'Отметить';
      btn.textContent = checked ? on : off;
      btn.title = btn.textContent;
    });
  }
  root.OPAArtPassport = {owner: owner, storageKey: storageKey, normalize: normalize,
                         read: read, write: write, toggle: toggle, selected: selected};
  function setup() {
    root.document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-opa-passport][data-passport-key]');
      if (!btn) return;
      var kind = btn.getAttribute('data-opa-passport');
      if (toggle(kind, btn.getAttribute('data-passport-key'))) syncButtons();
    });
    root.addEventListener('opa:passport-change', syncButtons);
    root.addEventListener('storage', syncButtons);
    syncButtons();
  }
  if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', setup);
  else setup();
})(window);
