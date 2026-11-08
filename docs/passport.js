/* Old Picture Art — art passport. Personal records sync to the account cloud; offline edits remain local. */
(function () {
  'use strict';
  var API = window.OPAArtPassport, catalog = window.OPA_PASSPORT_DATA || {};
  var panel = document.getElementById('passport-panel');
  if (!API || !panel) return;
  var works = Array.isArray(catalog.works) ? catalog.works : [];
  var artists = Array.isArray(catalog.artists) ? catalog.artists : [];
  var museums = Array.isArray(catalog.museums) ? catalog.museums : [];
  var byId = Object.create(null);
  works.forEach(function (w) { byId[String(w.id)] = w; });
  var view = 'overview', query = '', showAll = false, limit = 48;
  var initialTab = location.hash.replace(/^#/, '');
  if (['overview', 'artists', 'museums', 'originals', 'collections'].includes(initialTab)) view = initialTab;
  var addId = (new URLSearchParams(location.search)).get('add') || '';
  if (addId && byId[addId]) view = 'collections';

  function dom(tag, klass, contents) {
    var e = document.createElement(tag);
    if (klass) e.className = klass;
    if (contents !== undefined && contents !== null) e.textContent = String(contents);
    return e;
  }
  function append(parent) {
    Array.prototype.slice.call(arguments, 1).forEach(function (c) { if (c) parent.appendChild(c); });
    return parent;
  }
  function link(label, href, klass) {
    var a = dom('a', klass || '', label);
    a.href = href;
    return a;
  }
  function button(label, cb, klass) {
    var b = dom('button', klass || '', label);
    b.type = 'button'; b.addEventListener('click', cb);
    return b;
  }
  function paragraph(text) { return dom('p', 'passport-small', text); }
  function title(text) { return dom('h2', 'passport-section-title', text); }
  function note(text) { var p = paragraph(text); p.classList.add('passport-note'); return p; }
  function readLikes() {
    try {
      var m = JSON.parse(localStorage.getItem('likes') || '{}');
      return m && typeof m === 'object' && !Array.isArray(m) ? m : {};
    } catch (e) { return {}; }
  }
  function readExhibits() {
    try { return typeof readAfishaFavorites === 'function' ? readAfishaFavorites() : {}; }
    catch (e) { return {}; }
  }
  function selectedWorks(map) { return works.filter(function (w) { return !!map[w.id]; }); }
  function nameMatch(text, needle) { return String(text || '').toLocaleLowerCase('ru').replace(/ё/g, 'е').includes(needle.toLocaleLowerCase('ru').replace(/ё/g, 'е')); }
  function changeTab(next) {
    view = next; query = ''; showAll = false; limit = 48;
    if (!addId) history.replaceState({}, '', location.pathname + '#' + next);
    render();
  }
  function feedback(text) { document.getElementById('passport-feedback').textContent = text; }
  function tile(w, actions) {
    var card = dom('article', 'passport-work-card');
    var a = link('', w.href, 'passport-work-art');
    if (w.thumb) {
      var im = dom('img'); im.src = w.thumb; im.alt = ''; im.loading = 'lazy'; im.decoding = 'async';
      append(a, im);
    } else { a.textContent = 'Изображение'; }
    var body = dom('div', 'passport-work-body');
    append(body, link(w.title || 'Без названия', w.href, 'passport-work-title'));
    append(body, dom('p', 'passport-work-meta', [w.artist, w.year, w.museum].filter(Boolean).join(' · ')));
    if (actions) append(body, actions);
    return append(card, a, body);
  }
  function tiles(rows, actions) {
    var grid = dom('div', 'passport-work-grid');
    rows.forEach(function (w) { grid.appendChild(tile(w, actions ? actions(w) : null)); });
    return grid;
  }
  function empty(text, href, label) {
    var p = dom('div', 'passport-empty'); append(p, paragraph(text));
    if (href) p.appendChild(link(label, href, 'passport-text-link'));
    return p;
  }
  function stats(data, liked, exhibits) {
    var statsEl = document.getElementById('passport-stats');
    var counts = [
      ['Избранных картин', liked.length],
      ['Любимых художников', data.artists.length],
      ['Посещённых музеев', data.museums.length],
      ['Увиденных оригиналов', data.originals.length],
      ['Моих коллекций', data.collections.length],
      ['Избранных выставок', Object.keys(exhibits).filter(function(k){return !!exhibits[k];}).length]
    ];
    statsEl.replaceChildren();
    counts.forEach(function (item) {
      var div = dom('div', 'passport-stat');
      append(div, dom('strong', 'passport-stat-number', item[1]), dom('span', '', item[0]));
      statsEl.appendChild(div);
    });
    var session = typeof getSession === 'function' ? getSession() : null;
    var holder = document.getElementById('passport-owner');
    holder.textContent = session ? ('Аккаунт: ' + (session.name || 'пользователь')) : 'Гостевой арт-паспорт';
  }
  function overview(data, liked, exhibits) {
    append(panel, title('Любимые картины'));
    if (liked.length) {
      append(panel, paragraph('Картины с сердечком на сайте. При входе отметки синхронизируются между устройствами.'), tiles(liked.slice(0, 12)));
      if (liked.length > 12) append(panel, paragraph('Показаны первые 12 из ' + liked.length + '. Все отметки доступны в избранном на главной.'));
    } else append(panel, empty('Пока ни одной картины в избранном.', './', 'Открыть галерею'));
    append(panel, title('Мой маршрут'));
    var route = dom('div', 'passport-shortcuts');
    append(route,
      button('Художники: ' + data.artists.length, function(){changeTab('artists');}),
      button('Музеи: ' + data.museums.length, function(){changeTab('museums');}),
      button('Оригиналы: ' + data.originals.length, function(){changeTab('originals');}),
      button('Коллекции: ' + data.collections.length, function(){changeTab('collections');})
    );
    append(panel, route);
    var favored = artists.filter(function (a) { return data.artists.includes(a.name); });
    append(panel, title('Любимые художники'));
    if (favored.length) {
      var list = dom('div', 'passport-link-list');
      favored.forEach(function (a) { list.appendChild(link(a.name, a.href)); });
      append(panel, list);
    } else append(panel, empty('Добавьте художников в арт-паспорт на их страницах или в разделе «Художники».'));
    append(panel, title('Выставки из избранного'));
    var eventCatalog = window.OPA_AFISHA_CATALOG || {};
    var events = Object.keys(exhibits).filter(function(k){return exhibits[k] && eventCatalog[k];});
    if (events.length) {
      var el = dom('div', 'passport-link-list');
      events.slice(0, 10).forEach(function(k) {
        var e = eventCatalog[k];
        var a = link(e.title, 'afisha.html?favorites=1#' + encodeURIComponent(k));
        a.title = [e.venue, e.city].filter(Boolean).join(', ');
        el.appendChild(a);
      });
      append(panel, el);
    } else append(panel, empty('Отметьте понравившиеся выставки звёздочкой в афише.', 'afisha.html', 'Перейти к афише'));
    append(panel, note('Дневник посещений на сайте описывает поездки автора. В статистику вашего паспорта входят только отметки, которые вы сделали сами.'));
  }
  function searchField(placeholder) {
    var input = dom('input', 'passport-search');
    input.type = 'search'; input.placeholder = placeholder; input.value = query;
    input.setAttribute('aria-label', placeholder);
    input.addEventListener('input', function() {
      query = input.value;
      var selStart = input.selectionStart;
      render();
      var next = panel.querySelector('.passport-search');
      if (next) { next.focus(); try { next.setSelectionRange(selStart, selStart); } catch (e) {} }
    });
    return input;
  }
  function directory(kind, data) {
    var source = kind === 'artists' ? artists : museums;
    var chosen = data[kind];
    append(panel, title(kind === 'artists' ? 'Любимые художники' : 'Мои музеи'));
    append(panel, paragraph(kind === 'artists'
      ? 'Отмечайте интересных вам авторов. Избранные картины не ставят отметку художнику автоматически.'
      : 'Отметьте музеи, в которых вы действительно были. Отметки не зависят от дневника автора.'));
    append(panel, searchField(kind === 'artists' ? 'Найти художника' : 'Найти музей'));
    var found = source.filter(function (a) { return nameMatch(a.name, query); });
    found.sort(function(a,b) { return (+chosen.includes(b.name))-(+chosen.includes(a.name)) || a.name.localeCompare(b.name, 'ru'); });
    var list = dom('div', 'passport-directory');
    found.slice(0, limit).forEach(function (entry) {
      var row = dom('div', 'passport-dir-row');
      var isSet = chosen.includes(entry.name);
      var text = link(entry.name, entry.href);
      var toggle = button(isSet ? '✓ Отмечено' : (kind === 'artists' ? '+ Любимый' : '+ Был здесь'), function() {
        if (API.toggle(kind, entry.name)) render();
        else feedback('Не удалось сохранить отметку в браузере.');
      }, 'passport-toggle' + (isSet ? ' is-checked' : ''));
      toggle.setAttribute('aria-pressed', String(isSet));
      append(row, text, toggle); append(list, row);
    });
    append(panel, list);
    if (!found.length) append(panel, empty('Ничего не найдено. Можно попробовать другое название.'));
    if (found.length > limit) append(panel, button('Показать ещё (' + (found.length - limit) + ')', function(){limit += 48;render();}, 'passport-more'));
  }
  function originals(data) {
    append(panel, title('Картины, увиденные вживую'));
    append(panel, paragraph('Отметьте оригиналы, которые вы лично видели в музее или на выставке. Это не счётчик просмотров страниц.'));
    var wrap = dom('div', 'passport-search-row');
    append(wrap, searchField('Название, художник, музей'));
    append(wrap, button(showAll ? 'Только отмеченные' : 'Показать все картины', function(){showAll=!showAll;limit=48;render();}));
    append(panel, wrap);
    var selected = data.originals;
    var found = works.filter(function(w){
      return (showAll || selected.includes(w.id)) && nameMatch([w.artist,w.title,w.museum].join(' '), query);
    });
    found.sort(function(a,b){return (+selected.includes(b.id))-(+selected.includes(a.id));});
    if (!found.length) {
      append(panel, empty(showAll ? 'Ничего не найдено.' : 'Пока нет отметок. Нажмите «Показать все картины», чтобы добавить первую.'));
      return;
    }
    append(panel, tiles(found.slice(0, limit), function(w) {
      var checked = selected.includes(w.id);
      return button(checked ? '✓ Видел оригинал' : '+ Видел оригинал', function(){
        if (API.toggle('originals', w.id)) render();
      }, 'passport-toggle' + (checked ? ' is-checked' : ''));
    }));
    if (found.length > limit) append(panel, button('Показать ещё', function(){limit += 48;render();}, 'passport-more'));
  }
  function saveCollection(modifier) {
    var data = API.read(); modifier(data); if (!API.write(data)) feedback('Не удалось сохранить коллекцию.'); else render();
  }
  function collections(data) {
    append(panel, title('Мои коллекции'));
    append(panel, paragraph('Создавайте тематические подборки: «Зимние пейзажи», «Париж», «Что хочу увидеть» — с любыми картинами из каталога.'));
    append(panel, button('+ Новая коллекция', function() {
      var name = prompt('Название коллекции (до 60 символов):');
      if (name === null) return;
      name = name.trim().slice(0, 60);
      if (!name) { feedback('Введите название коллекции.'); return; }
      if (API.read().collections.length >= 50) { feedback('Можно сохранить не больше 50 коллекций.'); return; }
      saveCollection(function(state) {
        state.collections.unshift({id: 'c-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10), name: name, works: []});
      });
    }, 'passport-primary'));
    if (addId && byId[addId]) append(panel, note('Вы выбрали «' + byId[addId].title + '». Добавьте картину в одну из коллекций ниже.'));
    if (!data.collections.length) append(panel, empty('Коллекций ещё нет. Создайте первую, затем добавьте в неё работы.'));
    data.collections.forEach(function (collection) {
      var box = dom('section', 'passport-collection');
      var head = dom('div', 'passport-collection-head');
      append(head, dom('h3', '', collection.name), dom('span', 'passport-work-meta', collection.works.length + ' картин'));
      var actions = dom('div', 'passport-collection-actions');
      append(actions,
        button('Добавить картины', function(){chooseWork(collection);}),
        button('Переименовать', function(){
          var name = prompt('Название коллекции:', collection.name);
          if (name === null) return;
          name = name.trim().slice(0,60);
          if (!name) return;
          saveCollection(function(s){var c=s.collections.find(function(x){return x.id===collection.id;});if(c)c.name=name;});
        }),
        button('Удалить', function(){
          if (!confirm('Удалить коллекцию «' + collection.name + '»? Картины на сайте и лайки останутся без изменений.')) return;
          saveCollection(function(s){s.collections=s.collections.filter(function(x){return x.id!==collection.id;});});
        }, 'passport-danger')
      );
      append(box, head, actions);
      var found = collection.works.map(function(id){return byId[id];}).filter(Boolean);
      if (found.length) {
        var list = dom('div', 'passport-collection-list');
        found.forEach(function(w) {
          var item = dom('div', 'passport-collection-item');
          append(item, link(w.title + (w.artist ? ' — ' + w.artist : ''), w.href),
            button('Убрать', function(){
              saveCollection(function(s){var c=s.collections.find(function(x){return x.id===collection.id;});if(c)c.works=c.works.filter(function(id){return id!==w.id;});});
            }, 'passport-remove'));
          append(list, item);
        });
        append(box, list);
      } else append(box, paragraph('Пока пусто — добавьте работы из каталога.'));
      append(panel, box);
    });
  }
  function chooseWork(collection) {
    var overlay = dom('div', 'passport-dialog-overlay');
    var modal = dom('div', 'passport-dialog');
    modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-label','Добавить картину в коллекцию');
    var close = button('×', dismiss, 'passport-dialog-close');close.setAttribute('aria-label','Закрыть');
    append(modal, close, dom('h2', '', 'Добавить в «' + collection.name + '»'));
    var input = dom('input','passport-search');input.type='search';input.placeholder='Художник, название или музей';
    append(modal,input);
    var results = dom('div','passport-picker-results');append(modal, results);append(overlay,modal);
    function dismiss() {overlay.remove();document.removeEventListener('keydown',onKey);}
    function onKey(e){if(e.key==='Escape')dismiss();}
    function draw(){
      results.replaceChildren();
      var q=input.value.trim();
      var pool=works.filter(function(w){return !collection.works.includes(w.id) && (!q || nameMatch([w.title,w.artist,w.museum].join(' '),q));});
      if (addId && byId[addId] && !q) pool.sort(function(a,b){return (a.id===addId?-1:0)-(b.id===addId?-1:0);});
      pool.slice(0,35).forEach(function(w){
        var row=dom('div','passport-dir-row');
        append(row, dom('span','',w.artist+' — '+w.title),button('Добавить',function(){
          saveCollection(function(s){
            var c=s.collections.find(function(x){return x.id===collection.id;});
            if(c && !c.works.includes(w.id))c.works.push(w.id);
          });
          dismiss();addId='';history.replaceState({},'',location.pathname+'#collections');
        },'passport-toggle'));append(results,row);
      });
      if (!pool.length)append(results,paragraph('Нет подходящих работ.'));
    }
    input.addEventListener('input',draw);overlay.addEventListener('click',function(e){if(e.target===overlay)dismiss();});
    document.addEventListener('keydown',onKey);
    document.body.appendChild(overlay);input.focus();draw();
  }
  function render() {
    var data = API.read(), likes = readLikes(), events = readExhibits(), liked = selectedWorks(likes);
    stats(data, liked, events);
    document.querySelectorAll('.passport-tabs button').forEach(function (b){ b.setAttribute('aria-pressed',String(b.dataset.tab===view)); });
    panel.replaceChildren();
    if(view==='overview')overview(data, liked, events);
    if(view==='artists')directory('artists', data);
    if(view==='museums')directory('museums', data);
    if(view==='originals')originals(data);
    if(view==='collections')collections(data);
  }
  document.querySelectorAll('.passport-tabs button').forEach(function (b){b.addEventListener('click',function(){changeTab(b.dataset.tab);});});
  if (addId && byId[addId]) history.replaceState({},'',location.pathname+'?add='+encodeURIComponent(addId)+'#collections');
  function exportPassport() {
    var paintingLikes = readLikes(), exhibitionLikes = readExhibits();
    var content = {
      format: 'OldPictureArtPassport', version: 1, exportedAt: new Date().toISOString(),
      passport: API.read(),
      paintingLikes: Object.keys(paintingLikes).filter(function(id){return paintingLikes[id] && byId[id];}),
      exhibitionLikes: Object.keys(exhibitionLikes).filter(function(id){return exhibitionLikes[id];})
    };
    var blob = new Blob([JSON.stringify(content,null,2)],{type:'application/json'});
    var url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href=url;a.download='oldpictureart-passport.json';document.body.appendChild(a);a.click();a.remove();
    setTimeout(function(){URL.revokeObjectURL(url);},5000);
    feedback('Файл паспорта сохранён на ваше устройство.');
  }
  document.getElementById('passport-export').addEventListener('click',exportPassport);
  document.getElementById('passport-import').addEventListener('change',function(e){
    var input=e.currentTarget, file=input.files && input.files[0];if(!file)return;
    if(file.size>2*1024*1024){feedback('Файл слишком большой (максимум 2 МБ).');input.value='';return;}
    file.text().then(function(text){
      var d=JSON.parse(text);
      if(!d || d.format!=='OldPictureArtPassport' || d.version!==1 || !d.passport || typeof d.passport!=='object')throw Error('Неверный формат');
      if(!confirm('Заменить личные отметки и коллекции из этого браузера данными из файла? Существующие лайки будут дополнены.'))return;
      var state=API.normalize(d.passport);
      // Exclude stale IDs: import/export remain usable when catalogue changes.
      state.artists=state.artists.filter(function(id){return artists.some(function(a){return a.name===id;});});
      state.museums=state.museums.filter(function(id){return museums.some(function(a){return a.name===id;});});
      state.originals=state.originals.filter(function(id){return !!byId[id];});
      state.collections.forEach(function(c){c.works=c.works.filter(function(id){return !!byId[id];});});
      if(!API.write(state))throw Error('Нет доступа к localStorage');
      var likes=readLikes(), pending={};
      (Array.isArray(d.paintingLikes)?d.paintingLikes:[]).forEach(function(id){
        if(typeof id==='string' && byId[id]){likes[id]=true;pending[id]=true;}
      });
      localStorage.setItem('likes',JSON.stringify(likes));
      var oldPending=JSON.parse(localStorage.getItem('likes-pending')||'{}');
      Object.assign(oldPending,pending);localStorage.setItem('likes-pending',JSON.stringify(oldPending));
      var favs=readExhibits(), favPending={};
      var ec=window.OPA_AFISHA_CATALOG||{};
      (Array.isArray(d.exhibitionLikes)?d.exhibitionLikes:[]).forEach(function(id){
        if(typeof id==='string' && ec[id]){favs[id]=true;favPending[id]=true;}
      });
      localStorage.setItem('afishaFavorites',JSON.stringify(favs));
      var oldFavPending=JSON.parse(localStorage.getItem('afishaFavoritesPending')||'{}');
      Object.assign(oldFavPending,favPending);localStorage.setItem('afishaFavoritesPending',JSON.stringify(oldFavPending));
      // Mark imported data as intentionally belonging to the active account.
      if(typeof afishaAccountKey==='function' && afishaAccountKey())localStorage.setItem('afishaFavoritesAccount',afishaAccountKey());
      feedback('Паспорт импортирован. Новые отметки и коллекции отправятся в облако при подключении.');
      if (API.sync) API.sync().then(render);
      render();
      if(typeof cloudSync==='function')cloudSync('force').then(render);
      if(typeof syncAfishaFavorites==='function')syncAfishaFavorites().then(render);
    }).catch(function(err){feedback('Не удалось импортировать: '+err.message);}).finally(function(){input.value='';});
  });
  var info = document.getElementById('passport-save-info');
  function syncStatus() {
    if (!info || !API) return;
    var messages = {
      local: 'Гостевой режим: данные хранятся только в этом браузере. Войдите, чтобы синхронизировать арт-паспорт между устройствами.',
      syncing: 'Синхронизация арт-паспорта с аккаунтом…',
      saved: 'Арт-паспорт синхронизирован с аккаунтом. Изменения на других устройствах появятся при открытии или возврате к странице.',
      error: 'Нет связи с облаком или сервер не обновлён. Изменения сохранены локально и будут отправлены при следующем подключении.'
    };
    info.textContent = messages[API.status] || messages.local;
  }
  window.addEventListener('opa:passport-sync', syncStatus);
  window.addEventListener('opa:passport-change', render);
  window.addEventListener('opa:afisha-favorites', render);
  window.addEventListener('storage', function(e){if(e.key && (/^(opaPassport:v1:|likes$|afishaFavorites$|session$)/).test(e.key))render();});
  render();
  syncStatus();
  if (API.sync) API.sync().then(function(){render();syncStatus();});
  if (typeof cloudSync === 'function') cloudSync('force').then(function(){render();});
  if (typeof syncAfishaFavorites === 'function') syncAfishaFavorites().then(function(){render();});
})();
