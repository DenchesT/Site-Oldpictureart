/* Old Picture Art — Art Passport v3: diary, collections, map, chronology, stats. */
(function () {
  'use strict';
  var API=window.OPAArtPassport, data=window.OPA_PASSPORT_DATA||{};
  var panel=document.getElementById('passport-panel');if(!API||!panel)return;
  API.setCatalog(data);
  var works=Array.isArray(data.works)?data.works:[];
  var artists=Array.isArray(data.artists)?data.artists:[];
  var museums=Array.isArray(data.museums)?data.museums:[];
  var exhibitions=Array.isArray(data.exhibitions)?data.exhibitions:[];
  var all=Object.create(null),artistBy=Object.create(null),museumBy=Object.create(null),exBy=Object.create(null);
  works.forEach(function(w){all[w.id]=w;});
  artists.forEach(function(x){artistBy[x.id]=x;});
  museums.forEach(function(x){museumBy[x.id]=x;});
  exhibitions.forEach(function(x){exBy[x.key]=x;});
  var tabs=['overview','visits','artists','museums','originals','collections','exhibitions','map','timeline','stats'];
  var view=tabs.includes(location.hash.slice(1))?location.hash.slice(1):'overview';
  var addId=new URLSearchParams(location.search).get('add');if(addId&&all[addId])view='collections';
  var map=null,modal=null,originalsSearch='';
  function el(tag,cls,txt){var e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=String(txt);return e;}
  function append(parent){Array.prototype.slice.call(arguments,1).forEach(function(x){if(x)parent.appendChild(x);});return parent;}
  function link(t,url,cls){var e=el('a',cls||'',t);e.href=url;return e;}
  function btn(t,fn,cls){var e=el('button',cls||'',t);e.type='button';e.addEventListener('click',fn);return e;}
  function text(t){return el('p','passport-small',t);}
  function heading(t){return el('h2','passport-section-title',t);}
  function note(t){return el('p','passport-note',t);}
  function feedback(t){document.getElementById('passport-feedback').textContent=t;}
  function findMuseum(k){return museumBy[k]||{id:k,name:k,city:'',country:'',href:'#'};}
  function findArtist(k){return artistBy[k]||{id:k,name:k,href:'#'};}
  function findWork(k){return all[k]||{id:k,title:'Архивная запись № '+k,artist:'Картина больше не в каталоге',href:'#',thumb:''};}
  function findExhibition(k){return exBy[k]||{id:'',key:k,title:'Выставка из прежнего каталога',venue:'',city:'',end:''};}
  function displayDate(s){if(!s)return 'Дата не указана';var p=s.split('-');return p.length===3?p[2]+'.'+p[1]+'.'+p[0]:s;}
  function today(){var d=new Date(),p=function(x){return String(x).padStart(2,'0');};return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());}
  function safeSearch(s,q){return String(s||'').toLocaleLowerCase('ru').replace(/ё/g,'е').includes(String(q||'').toLocaleLowerCase('ru').replace(/ё/g,'е'));}
  function likes(){try{var d=JSON.parse(localStorage.getItem('likes')||'{}');return d&&typeof d==='object'?d:{};}catch(e){return {};}}
  function favorites(){try{return typeof readAfishaFavorites==='function'?readAfishaFavorites():{};}catch(e){return {};}}
  function labeledField(label,control){var box=el('label','passport-field');append(box,el('span','',label),control);return box;}
  function input(type,value,opts){var e=el(type==='textarea'?'textarea':type==='select'?'select':'input','passport-field-control');
    if(type!=='textarea'&&type!=='select')e.type=type;
    if(type==='select') (opts||[]).forEach(function(o){var opt=el('option','',o.label);opt.value=o.value;e.appendChild(opt);});
    e.value=value||'';return e;
  }
  // Native browser calendars differ significantly between Windows and Android.
  // Use one accessible, themed calendar and also permit typing DD.MM.YYYY.
  function isoDate(raw){
    var x=String(raw||'').trim();if(!x)return '';
    var m=/^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(x);
    if(!m){var ru=/^(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{4})$/.exec(x);
      if(ru)m=[x,ru[3],ru[2],ru[1]];}
    if(!m)return null;
    var y=+m[1],month=+m[2],day=+m[3];
    var d=new Date(Date.UTC(y,month-1,day));
    if(y<1500||y>2200||d.getUTCFullYear()!==y||d.getUTCMonth()+1!==month||d.getUTCDate()!==day)return null;
    return String(y).padStart(4,'0')+'-'+String(month).padStart(2,'0')+'-'+String(day).padStart(2,'0');
  }
  function dateWidget(value){
    var wrap=el('div','passport-date-widget');
    var display=input('text',value?displayDate(value):'');
    display.classList.add('passport-date-input');display.inputMode='numeric';
    display.placeholder='ДД.ММ.ГГГГ';display.autocomplete='off';
    var trigger=btn('▦',function(){if(pop.hidden)openCalendar();else closeCalendar();},'passport-date-trigger');
    trigger.setAttribute('aria-label','Открыть календарь');trigger.setAttribute('aria-expanded','false');
    var pop=el('div','passport-date-popup');pop.hidden=true;
    pop.setAttribute('role','group');pop.setAttribute('aria-label','Выбор даты');
    var now=new Date(),initial=isoDate(value),selected=initial?new Date(initial+'T12:00:00'):now;
    var month=selected.getMonth(),year=selected.getFullYear();
    function closeCalendar(){pop.hidden=true;trigger.setAttribute('aria-expanded','false');}
    function openCalendar(){
      // Inline calendar expands the form (not an absolutely positioned clipped overlay).
      // Dismiss mobile keyboard before measuring available space.
      display.blur();pop.hidden=false;draw();
      requestAnimationFrame(function(){
        if(pop.hidden)return;
        var dialog=wrap.closest('.passport-modal');
        if(!dialog)return;
        var box=dialog.getBoundingClientRect(),calendar=pop.getBoundingClientRect();
        // Scroll INSIDE the dialog, never jump the main document behind it.
        var bottom=box.bottom-18,top=box.top+70;
        if(calendar.bottom>bottom)dialog.scrollTop+=calendar.bottom-bottom;
        // On very short viewports the dialog remains scrollable; no day is cut off.
        else if(calendar.top<top)dialog.scrollTop-=top-calendar.top;
      });
    }
    function choose(day){var d=new Date(year,month,day);display.value=displayDate(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'));
      display.setCustomValidity('');closeCalendar();display.dispatchEvent(new Event('change',{bubbles:true}));}
    function draw(){
      trigger.setAttribute('aria-expanded',pop.hidden?'false':'true');pop.replaceChildren();
      var head=el('div','passport-date-nav');
      var prev=btn('‹',function(){month--;if(month<0){month=11;year--;}draw();});prev.setAttribute('aria-label','Предыдущий месяц');
      var next=btn('›',function(){month++;if(month>11){month=0;year++;}draw();});next.setAttribute('aria-label','Следующий месяц');
      append(head,prev,el('strong','',new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric'}).format(new Date(year,month,1))),next);pop.append(head);
      var grid=el('div','passport-calendar-grid');['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].forEach(function(w){grid.append(el('span','passport-calendar-weekday',w));});
      var offset=(new Date(year,month,1).getDay()+6)%7,days=new Date(year,month+1,0).getDate();
      for(var j=0;j<offset;j++)grid.append(el('span','passport-calendar-pad',''));
      for(var d=1;d<=days;d++){(function(day){var b=btn(String(day),function(){choose(day);},'passport-calendar-day');
        var v=isoDate(display.value),current=year+'-'+String(month+1).padStart(2,'0')+'-'+String(day).padStart(2,'0');
        if(v===current)b.setAttribute('aria-current','date');
        if(current===today())b.classList.add('is-today');grid.append(b);
      })(d);}pop.append(grid);
      var footer=el('div','passport-date-footer');append(footer,btn('Сегодня',function(){var d=new Date();year=d.getFullYear();month=d.getMonth();choose(d.getDate());}),
        btn('Очистить',function(){display.value='';display.setCustomValidity('');closeCalendar();}));pop.append(footer);
    }
    display.addEventListener('input',function(){display.setCustomValidity('');});
    display.addEventListener('blur',function(){if(!display.value.trim())return;
      var normalized=isoDate(display.value);if(normalized)display.value=displayDate(normalized);
    });
    display.addEventListener('keydown',function(e){if(e.key==='ArrowDown'){e.preventDefault();openCalendar();}
      if(e.key==='Escape')closeCalendar();});
    append(wrap,display,trigger,pop);return {node:wrap,control:display};
  }
  // Search narrows large native select menus, especially for paintings and museums.
  // The final control remains a normal <select>, keeping keyboard semantics.
  function searchedSelect(value,opts,placeholder){
    var wrapper=el('div','passport-select-search-wrap'),search=input('search','');
    search.classList.add('passport-select-search');search.placeholder=placeholder||'Поиск по названию';
    search.setAttribute('aria-label',search.placeholder);search.autocomplete='off';
    var select=input('select',value,[]),caption=el('span','passport-select-count','');
    select.setAttribute('aria-label','Выберите вариант из найденных');
    var full=Array.isArray(opts)?opts:[],picked=value||'';
    function draw(){
      var q=search.value.trim();var options=full.filter(function(o){return !o.value||safeSearch(o.label,q);});
      var filtered=options.filter(function(o){return !!o.value;});
      var visible=filtered.slice(0,q?45:24);
      var current=full.find(function(o){return o.value===picked;});
      if(q&&current&&!safeSearch(current.label,q)){picked='';current=null;}
      if(picked&&current&&!visible.some(function(o){return o.value===current.value;}))visible.unshift(current);
      select.replaceChildren();
      var placeholderOpt=el('option','','Выберите из найденных');placeholderOpt.value='';select.append(placeholderOpt);
      visible.forEach(function(o){var opt=el('option','',o.label);opt.value=o.value;select.append(opt);});
      select.value=visible.some(function(o){return o.value===picked;})?picked:'';
      // When exactly one result matches the query, select it automatically.
      if(q&&filtered.length===1){picked=filtered[0].value;select.value=picked;}
      caption.textContent='Найдено: '+filtered.length+(filtered.length>visible.length?' · уточните запрос':'');
    }
    search.addEventListener('input',draw);
    select.addEventListener('change',function(){picked=select.value;});
    append(wrapper,search,select,caption);draw();
    return {node:wrapper,control:select};
  }
  function formDialog(title,fields,onSave,caption){
    var form=el('form','passport-form');if(caption)form.append(text(caption));
    var controls={};fields.forEach(function(f){
      var widget,c;
      if(f.type==='date')widget=dateWidget(f.value||'');
      else if(f.type==='select'&&(f.options||[]).length>24)
        widget=searchedSelect(f.value||'',f.options,'Поиск: '+f.label.toLocaleLowerCase('ru'));
      else{c=input(f.type||'text',f.value||'',f.options);widget={node:c,control:c};}
      c=widget.control;
      if(f.max)c.maxLength=f.max;if(f.required)c.required=true;
      if(f.placeholder)c.placeholder=f.placeholder;
      if(f.type==='textarea')c.rows=4;
      controls[f.name]={control:c,type:f.type||'text'};
      form.append(labeledField(f.label,widget.node));
    });
    var footer=el('div','passport-form-actions');var submit=el('button','passport-primary','Сохранить');
    submit.type='submit';append(footer,submit);form.append(footer);
    var dialog=API.openDialog(title,form);
    form.addEventListener('submit',function(e){e.preventDefault();var values={},valid=true;
      Object.keys(controls).forEach(function(k){var field=controls[k],c=field.control,v=c.value.trim();
        if(field.type==='date'){
          var parsed=isoDate(v);
          if(parsed===null){c.setCustomValidity('Введите дату в формате ДД.ММ.ГГГГ');c.reportValidity();valid=false;}
          else v=parsed;
        }
        values[k]=v;
      });
      if(!valid)return;
      if(onSave(values)!==false){dialog.close();render();}
    });return dialog;
  }
  function confirmDialog(question,callback){
    var body=el('div');append(body,text(question));var actions=el('div','passport-form-actions');
    var dlg=API.openDialog('Подтвердите действие',body);
    append(actions,btn('Отмена',dlg.close),btn('Удалить',function(){dlg.close();callback();render();},'passport-danger'));
    body.append(actions);
  }
  function save(change){var state=API.read();change(state);if(!API.write(state)){feedback('Не удалось сохранить: проверьте доступ к хранилищу браузера.');return false;}return true;}
  function switchTab(tab){
    if(!tabs.includes(tab))return;
    view=tab;
    history.replaceState(null,'',location.pathname+'#'+tab);
    render();
    document.querySelector('.passport-tabs button[aria-pressed="true"]')?.scrollIntoView({block:'nearest',inline:'nearest'});
  }
  function workTile(w,controls){
    var card=el('article','passport-work-card'),a=link('',w.href||'#','passport-work-art');
    if(w.thumb){var img=el('img');img.src=w.thumb;img.alt='';img.loading='lazy';append(a,img);}else a.textContent='Нет изображения';
    var body=el('div','passport-work-body');append(body,link(w.title||w.id,w.href||'#','passport-work-title'),
      el('p','passport-work-meta',[w.artist,w.year,w.museum].filter(Boolean).join(' · ')));
    if(controls)append(body,controls);return append(card,a,body);
  }
  function gridWorks(ids,actionFn){var grid=el('div','passport-work-grid');ids.forEach(function(w){grid.append(workTile(w,actionFn?actionFn(w):null));});return grid;}
  function empty(title,subtitle,action){
    var box=el('div','passport-empty');append(box,el('strong','',title));if(subtitle)append(box,text(subtitle));if(action)append(box,action);return box;
  }
  function statsCards(d){
    var featured=[['Картины',Object.keys(likes()).filter(function(k){return likes()[k]&&all[k];}).length],
      ['Художники',d.artists.length],['Музеи',new Set(d.museums.concat(d.visits.map(function(v){return v.museum;}))).size],
      ['Оригиналы',new Set(d.originals.concat(d.sightings.map(function(v){return v.work;}))).size],
      ['Коллекции',d.collections.length],['Посещения',d.visits.length]];
    var holder=document.getElementById('passport-stats');holder.replaceChildren();
    featured.forEach(function(item){var b=btn('',function(){switchTab(({
      'Картины':'overview','Художники':'artists','Музеи':'museums','Оригиналы':'originals','Коллекции':'collections','Посещения':'visits'
    })[item[0]]);},'passport-stat');append(b,el('strong','passport-stat-number',item[1]),el('span','',item[0]));holder.append(b);});
    var s=typeof getSession==='function'?getSession():null;
    document.getElementById('passport-owner').textContent=s?'Аккаунт: '+(s.name||'пользователь'):'Гостевой арт-паспорт';
  }
  function recentRows(d){
    var rows=[];
    d.visits.forEach(function(v){rows.push({date:v.date,title:'Музей: '+findMuseum(v.museum).name,
      detail:[v.exhibition,v.note].filter(Boolean).join(' · '),tab:'visits'});});
    d.sightings.forEach(function(v){rows.push({date:v.date,title:'Оригинал: '+findWork(v.work).title,
      detail:[findMuseum(v.museum).name,v.note].filter(Boolean).join(' · '),tab:'originals'});});
    d.exhibitions.forEach(function(v){if(v.status==='visited')rows.push({date:v.date,
      title:'Выставка: '+findExhibition(v.id).title,detail:v.note,tab:'exhibitions'});});
    return rows.sort(function(a,b){return (b.date||'').localeCompare(a.date||'');});
  }
  function overview(d){
    var recent=recentRows(d);
    append(panel,heading('Моя история искусства'));
    var actions=el('div','passport-shortcuts passport-overview-actions');
    append(actions,btn('+ Посещение',function(){visitDialog();},'passport-primary'),
      btn('+ Увиденный оригинал',function(){sightingDialog();}),
      btn('+ Коллекция',function(){collectionDialog();}),
      btn('Моя карта',function(){switchTab('map');}));append(panel,actions);
    append(panel,heading('Последние впечатления'));
    if(recent.length)append(panel,historyList(recent.slice(0,5)));
    else append(panel,empty('Пока нет записей','Начните с посещённого музея или увиденного оригинала.'));
    if(recent.length>5)append(panel,btn('Вся хронология',function(){switchTab('timeline');},'passport-text-button'));
    append(panel,heading('Избранные картины'));
    var chosen=works.filter(function(w){return !!likes()[w.id];});
    if(chosen.length){
      append(panel,gridWorks(chosen.slice(0,12),function(w){return btn('+ В коллекцию',function(){API.collectionPicker(w.id,w.title);},'passport-toggle');}));
      if(chosen.length>12)append(panel,text('Показаны первые 12 из '+chosen.length+'. Все работы доступны во вкладке «Избранное» галереи.'));
    } else append(panel,empty('Пока нет понравившихся картин','Нажмите сердечко у картины в галерее.',link('В галерею','./')));
    append(panel,heading('Мои коллекции'));
    if(d.collections.length){var row=el('div','passport-album-grid');
      d.collections.slice(0,4).forEach(function(c){row.append(albumCard(c,true));});append(panel,row);
    }else append(panel,empty('Коллекции ещё не созданы','Создавайте тематические подборки из понравившихся картин.'));
    append(panel,heading('Выставки'));
    var count=d.exhibitions.filter(function(e){return e.status==='want';}).length;
    append(panel,text('Хочу посетить: '+count+'. Отмеченные и посещённые выставки — в отдельном разделе.'),
      btn('Открыть выставки',function(){switchTab('exhibitions');}));
  }
  function museumOptions(chosen){
    var options=[{label:'Выберите музей',value:''}];
    museums.forEach(function(m){options.push({label:m.name,value:m.id});});
    if(chosen&&!museumBy[chosen])options.push({label:'Старое название: '+chosen,value:chosen});
    return options;
  }
  function workOptions(chosen){var options=[{label:'Выберите картину',value:''}];
    works.forEach(function(w){options.push({label:[w.artist,w.title].filter(Boolean).join(' — '),value:w.id});});
    if(chosen&&!all[chosen])options.push({label:'Архивная работа №'+chosen,value:chosen});return options;
  }
  function visitDialog(existing,presetMuseum){
    existing=existing||{};
    formDialog(existing.id?'Редактировать посещение':'Новое посещение',[{
      name:'museum',label:'Музей',type:'select',value:existing.museum||presetMuseum||'',options:museumOptions(existing.museum),required:true
    },{name:'date',label:'Дата посещения',type:'date',value:existing.date||today()},
    {name:'exhibition',label:'Выставка (необязательно)',value:existing.exhibition,max:160,placeholder:'Название выставки'},
    {name:'note',label:'Впечатления',type:'textarea',value:existing.note,max:2000,placeholder:'Что запомнилось?'}],function(v){
      if(!v.museum)return false;
      return save(function(d){
        var item=d.visits.find(function(x){return x.id===existing.id;});
        if(!item){item={id:API.newId('v-')};d.visits.unshift(item);}
        Object.assign(item,v);
        if(!d.museums.includes(v.museum))d.museums.push(v.museum);
      });
    },'Повторное посещение создаётся отдельной записью.');
  }
  function visits(d){
    append(panel,heading('Дневник посещений'),text('Записывайте дату, музей, выставку и впечатления. Один музей можно посещать сколько угодно раз.'),
      btn('+ Добавить посещение',function(){visitDialog();},'passport-primary'));
    var arranged=d.visits.slice().sort(function(a,b){return (b.date||'').localeCompare(a.date||'');});
    if(!arranged.length){append(panel,empty('Записей ещё нет','Вы можете добавить визит даже если уже отметили музей как посещённый.'));return;}
    var list=el('div','passport-history');arranged.forEach(function(v){
      var card=el('article','passport-history-entry');
      append(card,el('time','passport-work-meta',displayDate(v.date)),
        el('h3','',findMuseum(v.museum).name));
      if(v.exhibition)append(card,text('Выставка: '+v.exhibition));
      if(v.note)append(card,text(v.note));
      var buttons=el('div','passport-inline-actions');append(buttons,
        btn('Изменить',function(){visitDialog(v);}),
        btn('Удалить',function(){confirmDialog('Удалить эту запись о посещении?',function(){save(function(s){s.visits=s.visits.filter(function(x){return x.id!==v.id;});});});},'passport-danger'));
      append(card,buttons);list.append(card);
    });append(panel,list);
  }
  function searchable(source,placeholder,makeRow,limit){
    var outer=el('div','passport-search-container'),search=input('search','');
    search.placeholder=placeholder;search.setAttribute('aria-label',placeholder);
    search.classList.add('passport-search');
    var results=el('div','passport-directory'),counter=text('');
    var count=limit||60;
    function draw(){
      var q=search.value,rows=source.filter(function(x){return safeSearch(makeRow.search(x),q);});
      results.replaceChildren();rows.slice(0,count).forEach(function(item){results.append(makeRow(item));});
      counter.textContent=rows.length>count?'Показано '+count+' из '+rows.length:'Найдено: '+rows.length;
      if(rows.length>count)results.append(btn('Показать ещё',function(){count+=60;draw();},'passport-more'));
    }
    search.addEventListener('input',function(){count=limit||60;draw();});
    append(outer,search,counter,results);draw();return outer;
  }
  function directory(kind,d){
    var source=kind==='artists'?artists:museums,chosen=d[kind],isMuseum=kind==='museums';
    append(panel,heading(isMuseum?'Мои музеи':'Любимые художники'),
      text(isMuseum?'Отметьте музеи, в которых бывали, или сразу добавьте посещение с датой.':
        'Отмечайте любимых художников. Их картины не добавляются в избранное автоматически.'));
    if(isMuseum)append(panel,btn('+ Новое посещение',function(){visitDialog();},'passport-primary'));
    var sorted=source.slice().sort(function(a,b){return Number(chosen.includes(b.id))-Number(chosen.includes(a.id))||a.name.localeCompare(b.name,'ru');});
    var renderRow=function(entry){
      var row=el('div','passport-dir-row'),buttons=el('div','passport-inline-actions');
      var active=chosen.includes(entry.id);
      append(buttons,btn(active?'✓ Отмечено':isMuseum?'+ Был здесь':'+ Любимый',function(){
        if(API.toggle(kind,entry.id)){var pos=window.scrollY;var query=panel.querySelector('.passport-search')?.value||'';
          render();var next=panel.querySelector('.passport-search');if(next){next.value=query;next.dispatchEvent(new Event('input'));}window.scrollTo(0,pos);}},'passport-toggle'+(active?' is-checked':'')));
      if(isMuseum)append(buttons,btn('+ В дневник',function(){visitDialog(null,entry.id);}));
      append(row,link(entry.name,entry.href||'#'),buttons);return row;
    };
    renderRow.search=function(entry){return [entry.name,entry.city,entry.country].filter(Boolean).join(' ');};
    append(panel,searchable(sorted,isMuseum?'Музей, город или страна':'Найти художника',renderRow,60));
    var ghosts=chosen.filter(function(k){return !source.some(function(x){return x.id===k;});});
    if(ghosts.length){append(panel,heading('Сохранённые архивные отметки'),
      note('Эти записи больше не находятся в каталоге, но остаются в вашем паспорте.'));
      ghosts.forEach(function(k){append(panel,append(el('div','passport-dir-row'),el('span','',k),
        btn('Убрать',function(){API.toggle(kind,k);render();},'passport-danger')));});}
  }
  function sightingDialog(existing,preset){
    existing=existing||{};
    formDialog(existing.id?'Изменить встречу с оригиналом':'Увиденный оригинал',[
      {name:'work',label:'Произведение',type:'select',options:workOptions(existing.work||preset),value:existing.work||preset||'',required:true},
      {name:'date',label:'Дата',type:'date',value:existing.date||today()},
      {name:'museum',label:'Музей (если известен)',type:'select',options:museumOptions(existing.museum),value:existing.museum||''},
      {name:'note',label:'Впечатления',type:'textarea',value:existing.note,max:2000}
    ],function(v){if(!v.work)return false;return save(function(d){
      var entry=d.sightings.find(function(x){return x.id===existing.id;});
      if(!entry){entry={id:API.newId('s-')};d.sightings.unshift(entry);}
      Object.assign(entry,v);
      if(!d.originals.includes(v.work))d.originals.push(v.work);
    });},'История просмотров оригинала сохраняется отдельно от сердечка у картины.');
  }
  function originals(d){
    append(panel,heading('Оригиналы, увиденные вживую'),
      text('Отмечайте только произведения, которые вы лично видели. Можно указать дату и впечатления.'),
      btn('+ Записать встречу с оригиналом',function(){sightingDialog();},'passport-primary'));
    var ids=Array.from(new Set(d.originals.concat(d.sightings.map(function(s){return s.work;}))));
    if(ids.length){
      var wrap=el('div','passport-search-container'),search=input('search',originalsSearch),row=el('div','passport-work-grid'),counter=text(''),more=el('div','passport-more-wrap');
      search.classList.add('passport-search');search.placeholder='Найти оригинал: название, художник, музей, год';
      search.setAttribute('aria-label',search.placeholder);
      var shown=36;
      function drawOriginals(){
        var found=ids.filter(function(k){var w=findWork(k);return safeSearch([w.title,w.artist,w.museum,w.year,w.id].join(' '),originalsSearch);});
        row.replaceChildren();more.replaceChildren();counter.textContent='Найдено: '+found.length;
        found.slice(0,shown).forEach(function(k){
          var w=findWork(k);
          row.append(workTile(w,append(el('div','passport-card-actions'),
            btn('+ Дата и заметка',function(){sightingDialog(null,w.id);},'passport-toggle'),
            btn('Снять отметку',function(){API.toggle('originals',w.id);render();},'passport-remove'))));
        });
        if(!found.length)more.append(empty('Картины не найдены','Измените поисковый запрос.'));
        if(found.length>shown)more.append(btn('Показать ещё ('+(found.length-shown)+')',function(){shown+=36;drawOriginals();},'passport-more'));
      }
      search.addEventListener('input',function(){originalsSearch=search.value;shown=36;drawOriginals();});
      append(wrap,search,counter,row,more);panel.append(wrap);drawOriginals();
    }else append(panel,empty('Пока нет увиденных оригиналов','Найдите картину и добавьте запись.',btn('Выбрать картину',function(){sightingDialog();})));
    if(d.sightings.length){append(panel,heading('История встреч'));
      var rows=d.sightings.slice().sort(function(a,b){return (b.date||'').localeCompare(a.date||'');});
      var list=el('div','passport-history');rows.forEach(function(s){
        var card=el('article','passport-history-entry');append(card,el('time','passport-work-meta',displayDate(s.date)),
          el('h3','',findWork(s.work).title),text([findMuseum(s.museum).name,s.note].filter(Boolean).join(' · ')));
        append(card,append(el('div','passport-inline-actions'),
          btn('Изменить',function(){sightingDialog(s);}),
          btn('Удалить запись',function(){confirmDialog('Удалить запись о просмотре оригинала?',function(){save(function(d){d.sightings=d.sightings.filter(function(x){return x.id!==s.id;});});});},'passport-danger')));
        list.append(card);
      });append(panel,list);
    }
  }
  function collectionDialog(existing){
    existing=existing||{};
    var fields=[{name:'name',label:'Название',value:existing.name||'',max:60,required:true},
      {name:'description',label:'Описание',type:'textarea',value:existing.description||'',max:500}];
    formDialog(existing.id?'Изменить коллекцию':'Новая коллекция',fields,function(v){
      if(!v.name)return false;
      return save(function(d){
        var c=d.collections.find(function(x){return x.id===existing.id;});
        if(!c){if(d.collections.length>=50)return;c={id:API.newId('c-'),works:[],cover:''};d.collections.unshift(c);}
        c.name=v.name;c.description=v.description;
      });
    });
  }
  function albumCard(c,mini){
    var card=el('div','passport-album'),cover=findWork(c.cover||c.works[0]);
    var img=el('div','passport-album-cover');
    if(cover.thumb){var image=el('img');image.src=cover.thumb;image.alt='';image.loading='lazy';img.append(image);}
    else img.textContent='Моя коллекция';
    append(card,img,el('strong','passport-album-title',c.name),
      el('span','passport-work-meta',c.works.length+' картин'));
    if(c.description&&!mini)append(card,text(c.description));
    if(mini)card.append(btn('Открыть',function(){switchTab('collections');}));
    return card;
  }
  function collections(d){
    append(panel,heading('Личные коллекции'),
      text('Тематические альбомы с обложками, описаниями и вашим порядком картин.'),
      btn('+ Создать коллекцию',function(){collectionDialog();},'passport-primary'));
    if(!d.collections.length){append(panel,empty('Коллекций пока нет','Создайте свой первый альбом.'));return;}
    d.collections.forEach(function(c){
      var section=el('section','passport-collection'),header=el('div','passport-collection-head');
      append(header,albumCard(c,false),el('span','passport-work-meta',c.works.length+' работ'));section.append(header);
      var actions=el('div','passport-collection-actions');
      append(actions,btn('+ Картины',function(){collectionWorkPicker(c);},'passport-primary'),
        btn('Изменить',function(){collectionDialog(c);}),
        btn('Удалить',function(){confirmDialog('Удалить коллекцию «'+c.name+'»? Лайки картин останутся.',function(){
          save(function(d){d.collections=d.collections.filter(function(x){return x.id!==c.id;});});
        });},'passport-danger'));
      section.append(actions);
      if(c.works.length){var items=el('div','passport-work-grid');c.works.forEach(function(k,i){
        var w=findWork(k),controls=el('div','passport-card-actions');
        append(controls,btn('Обложка',function(){save(function(d){var x=d.collections.find(function(x){return x.id===c.id;});if(x)x.cover=k;});render();},'passport-toggle'));
        var arrows=el('div','passport-order-actions');
        append(arrows,btn('↑',function(){moveWork(c.id,k,-1);},'passport-icon-button'),
          btn('↓',function(){moveWork(c.id,k,1);},'passport-icon-button'),
          btn('Убрать',function(){save(function(d){var x=d.collections.find(function(x){return x.id===c.id;});if(x){x.works=x.works.filter(function(y){return y!==k;});if(x.cover===k)x.cover='';}});render();},'passport-remove'));
        append(controls,arrows);items.append(workTile(w,controls));
      });section.append(items);}
      else section.append(text('В коллекции пока нет картин.'));
      panel.append(section);
    });
    if(addId&&all[addId]){
      append(panel,note('Вы выбрали «'+all[addId].title+'». Выберите коллекцию, чтобы добавить картину.'));
      API.collectionPicker(addId,all[addId].title);
      addId='';history.replaceState(null,'',location.pathname+'#collections');
    }
  }
  function moveWork(cid,k,by){save(function(d){var c=d.collections.find(function(x){return x.id===cid;});if(!c)return;
    var i=c.works.indexOf(k),to=i+by;if(i<0||to<0||to>=c.works.length)return;
    c.works.splice(i,1);c.works.splice(to,0,k);
  });render();}
  function collectionWorkPicker(c){
    var body=el('div');append(body,text('Выберите картины для «'+c.name+'». Можно добавлять и удалять без закрытия окна.'));
    var search=input('search','');search.classList.add('passport-search');search.placeholder='Название, художник, музей';
    var results=el('div','passport-picker-results');append(body,search,results);
    var dialog=API.openDialog('Добавить картины',body);
    function draw(){
      var state=API.read(),latest=state.collections.find(function(x){return x.id===c.id;});if(!latest)return;
      results.replaceChildren();var found=works.filter(function(w){return safeSearch([w.title,w.artist,w.museum].join(' '),search.value);}).slice(0,60);
      found.forEach(function(w){
        var row=el('div','passport-picker-row'),chosen=latest.works.includes(w.id);
        var thumb=el('div','passport-picker-thumb');if(w.thumb){var img=el('img');img.src=w.thumb;img.alt='';img.loading='lazy';thumb.append(img);}
        append(row,thumb,el('span','',w.title+' — '+w.artist),btn(chosen?'✓ Добавлено':'+ Добавить',function(){
          save(function(d){var x=d.collections.find(function(x){return x.id===c.id;});if(!x)return;
            var pos=x.works.indexOf(w.id);if(pos<0)x.works.push(w.id);else x.works.splice(pos,1);
          });draw();},'passport-toggle'));results.append(row);
      });
      if(!found.length)results.append(text('Ничего не найдено.'));
    }
    search.addEventListener('input',draw);draw();
    dialog.dialog.addEventListener('close',render,{once:true});
  }
  function editExhibition(entry,existing,status){
    var old=existing||{};
    formDialog('Выставка: '+entry.title,[{name:'status',label:'Статус',type:'select',value:status||old.status||'want',
      options:[{label:'Хочу посетить',value:'want'},{label:'Посетил',value:'visited'}]},
      {name:'date',label:'Дата посещения (если была)',type:'date',value:old.date||''},
      {name:'note',label:'Заметка',type:'textarea',value:old.note,max:1000}],function(v){
        return save(function(d){var r=d.exhibitions.find(function(x){return x.id===entry.key;});
          if(!r){r={id:entry.key};d.exhibitions.push(r);}Object.assign(r,v);
        });
      });
  }
  function exhibitionsSection(d){
    append(panel,heading('Мои выставки'),
      text('Планируйте посещения, отмечайте состоявшиеся и смотрите избранное из афиши.'));
    var favs=favorites(),picked=new Map(d.exhibitions.map(function(x){return [x.id,x];}));
    var allEntries=exhibitions.slice();d.exhibitions.forEach(function(x){if(!exBy[x.id])allEntries.push(findExhibition(x.id));});
    var selected='want',actions=el('div','passport-shortcuts'),container=el('div');
    var groups=[['want','Хочу посетить'],['visited','Посетил'],['favorite','Избранное']];
    function draw(){
      actions.querySelectorAll('button').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.kind===selected));});
      container.replaceChildren();var pool=allEntries.filter(function(x){
        if(selected==='favorite')return !!favs[x.id];
        return (picked.get(x.key)||{}).status===selected;
      });
      if(!pool.length){container.append(empty('Список пуст','Добавляйте выставки из афиши или списка ниже.'));return;}
      pool.forEach(function(x){
        var row=el('article','passport-exhibition-row');
        append(row,el('strong','',x.title),text([x.venue,x.city,x.end?'До '+displayDate(x.end):''].filter(Boolean).join(' · ')));
        var p=picked.get(x.key),bar=el('div','passport-inline-actions');
        append(bar,btn('Изменить статус',function(){editExhibition(x,p);}),
          btn('Убрать статус',function(){if(save(function(d){d.exhibitions=d.exhibitions.filter(function(r){return r.id!==x.key;});}))render();},'passport-remove'));
        if(x.id)append(bar,link('Открыть в афише','afisha.html#'+encodeURIComponent(x.id)));
        row.append(bar);container.append(row);
      });
    }
    groups.forEach(function(x){var b=btn(x[1],function(){selected=x[0];draw();});b.dataset.kind=x[0];actions.append(b);});
    append(panel,actions,container);draw();
    append(panel,heading('Добавить выставку из афиши'));
    var renderRow=function(entry){var row=el('div','passport-dir-row'),existing=picked.get(entry.key);
      append(row,el('span','',entry.title+' — '+entry.venue),
        btn(existing?'Изменить':'+ В планы',function(){editExhibition(entry,existing);},'passport-toggle'));
      return row;
    };
    renderRow.search=function(e){return [e.title,e.venue,e.city].join(' ');};
    append(panel,searchable(exhibitions,'Название выставки или музей',renderRow,40));
    append(panel,note('Звёздочки «Избранное» управляются афишей и синхронизируются отдельно от статусов «Хочу посетить» и «Посетил».'));
  }
  function mapSection(d){
    append(panel,heading('Карта моих музеев'),text('Здесь только отмеченные вами музеи. Точные координаты берутся из справочника сайта.'));
    var chosen=Array.from(new Set(d.museums.concat(d.visits.map(function(v){return v.museum;}))));
    var points=chosen.map(findMuseum).filter(function(m){return Number.isFinite(m.lat)&&Number.isFinite(m.lon);});
    var missing=chosen.map(findMuseum).filter(function(m){return !Number.isFinite(m.lat)||!Number.isFinite(m.lon);});
    if(!chosen.length){panel.append(empty('Нет посещённых музеев','Отметьте музей или создайте запись в дневнике.'));return;}
    if(points.length&&typeof L!=='undefined'){
      var toolbar=el('div','passport-map-toolbar');
      var toggle=btn('На весь экран',function(){
        var fullscreen=mapEl.classList.toggle('passport-map-fullscreen');
        toggle.textContent=fullscreen?'Свернуть карту':'На весь экран';
        document.body.classList.toggle('passport-map-is-fullscreen',fullscreen);
        if(map)setTimeout(function(){map.invalidateSize();},30);
      });
      append(toolbar,toggle);panel.append(toolbar);
      var mapEl=el('div','passport-map');mapEl.setAttribute('aria-label','Карта отмеченных музеев');panel.append(mapEl);
      map=L.map(mapEl,{scrollWheelZoom:true,worldCopyJump:true,zoomControl:true});
      if(typeof OPA_MAP!=='undefined'){
        OPA_MAP.attach(map,mapEl);
      }else{
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
          maxZoom:19,attribution:'&copy; OpenStreetMap contributors'
        }).addTo(map);
      }
      var bounds=[],markers=[];
      points.forEach(function(m){
        var count=d.visits.filter(function(v){return v.museum===m.id;}).length;
        var label=String(count||1),icon=L.divIcon({
          className:'opa-pin visit-only'+(m.approx?' approx':''),
          html:'<span class="pin-card">'+label+'</span><span class="pin-stem"></span><span class="pin-dot"></span>',
          iconSize:[46,32],iconAnchor:[23,32],popupAnchor:[0,-30]
        });
        var latlng=[m.lat,m.lon],marker=L.marker(latlng,{icon:icon}),wrap=document.createElement('div');
        append(wrap,el('strong','',m.name),el('p','passport-map-place',[m.city,m.country].filter(Boolean).join(', ')));
        var a=link('Страница музея',m.href||'#');wrap.append(a);marker.bindPopup(wrap);
        markers.push(marker);bounds.push(latlng);
      });
      if(typeof L.markerClusterGroup==='function'&&markers.length>5){
        var clusters=L.markerClusterGroup({showCoverageOnHover:false,maxClusterRadius:42,iconCreateFunction:function(cluster){
          var num=cluster.getChildCount();return L.divIcon({className:'opa-cluster',
            html:'<span class="cl-stack"><span class="cl cl-2"></span><span class="cl cl-1"></span><span class="cl cl-0">'+num+'</span></span><span class="pin-stem"></span><span class="pin-dot"></span>',iconSize:[46,38],iconAnchor:[23,38]});
        }});clusters.addLayers(markers);map.addLayer(clusters);
      }else markers.forEach(function(marker){marker.addTo(map);});
      if(points.length===1)map.setView(bounds[0],12);else map.fitBounds(bounds,{padding:[30,30],maxZoom:13});
      setTimeout(function(){if(map)map.invalidateSize();},100);
    }else if(points.length)panel.append(note('Карта не загрузилась. Ниже доступен список посещённых музеев.'));
    if(missing.length)append(panel,note('Без точных координат: '+missing.map(function(m){return m.name;}).join('; ')+'. Эти места остаются в вашем паспорте.'));
    var list=el('div','passport-directory');chosen.forEach(function(k){var m=findMuseum(k);
      append(list,append(el('div','passport-dir-row'),link(m.name,m.href||'#'),el('span','passport-work-meta',[m.city,m.country].filter(Boolean).join(', '))));
    });append(panel,list);
  }
  function historyList(rows){var container=el('div','passport-history');rows.forEach(function(e){
    var r=el('article','passport-history-entry');append(r,el('time','passport-work-meta',displayDate(e.date)),
      el('h3','',e.title),text(e.detail||''),btn('Открыть раздел',function(){switchTab(e.tab);},'passport-text-button'));
    container.append(r);
  });return container;}
  function timeline(d){
    append(panel,heading('Хронология впечатлений'),text('Посещения, выставки и встречи с оригиналами в порядке дат.'));
    var rows=recentRows(d);if(!rows.length){panel.append(empty('История пока пуста','Добавьте своё первое посещение.'));return;}
    var grouped=Object.create(null);rows.forEach(function(r){var key=r.date?r.date.slice(0,4):'Без даты';(grouped[key]||(grouped[key]=[])).push(r);});
    Object.keys(grouped).sort().reverse().forEach(function(year){append(panel,heading(year),historyList(grouped[year]));});
  }
  function chartBlock(name,map,top){var keys=Object.keys(map).sort(function(a,b){return map[b]-map[a];}).slice(0,top||8);
    var section=el('section','passport-chart');append(section,heading(name));
    if(!keys.length){section.append(text('Пока недостаточно данных.'));return section;}
    var maximum=Math.max.apply(Math,keys.map(function(k){return map[k];}));
    keys.forEach(function(k){var row=el('div','passport-chart-row'),top=el('div','passport-chart-header');
      append(top,el('span','',k),el('strong','',map[k]));var track=el('div','passport-chart-track'),fill=el('div','passport-chart-fill');
      fill.style.width=(100*map[k]/maximum)+'%';track.append(fill);append(row,top,track);section.append(row);
    });return section;
  }
  function statistics(d){
    append(panel,heading('Моя статистика'),text('Все показатели рассчитаны из ваших отметок. Ничего не публикуется для других посетителей.'));
    var byYear=Object.create(null),byCity=Object.create(null),byCountry=Object.create(null),byArtist=Object.create(null),byCentury=Object.create(null);
    d.visits.forEach(function(v){if(v.date){var y=v.date.slice(0,4);byYear[y]=(byYear[y]||0)+1;}});
    var used=new Set(d.museums.concat(d.visits.map(function(v){return v.museum;})));
    used.forEach(function(k){var m=findMuseum(k);if(m.city)byCity[m.city]=(byCity[m.city]||0)+1;
      if(m.country)byCountry[m.country]=(byCountry[m.country]||0)+1;
    });
    works.forEach(function(w){if(!likes()[w.id])return;
      if(w.artist)byArtist[w.artist]=(byArtist[w.artist]||0)+1;
      var y=Number(String(w.year).match(/\d{4}/)?.[0]);
      if(y>=1000&&y<=2100){var century=Math.floor((y-1)/100)+1,lab=century+' век';byCentury[lab]=(byCentury[lab]||0)+1;}
    });
    append(panel,chartBlock('Посещений по годам',byYear),chartBlock('Музеи по странам',byCountry),
      chartBlock('Музеи по городам',byCity),chartBlock('Художники среди любимых картин',byArtist),
      chartBlock('Эпохи любимых картин',byCentury));
    append(panel,note('Эпоха определяется приблизительно по году создания картины. Это не классификация по художественным направлениям.'));
  }
  function syncStatus(){
    var info=API.stateInfo(),holder=document.getElementById('passport-sync-text');
    if(!holder)return;
    var txt={
      local:'Гостевой режим: паспорт хранится только в этом браузере. Войдите, чтобы синхронизировать.',
      syncing:'Синхронизация с облаком…',
      saved:'Данные сохранены в облаке.',
      error:'Не удалось связаться с облаком; изменения сохранены на устройстве.'
    }[info.status]||'';
    if(info.lastSync&&info.status==='saved')txt+=' Последняя синхронизация: '+new Date(info.lastSync).toLocaleString('ru-RU')+'.';
    if(info.pending)txt+=' Ожидают отправки: '+info.pending+'.';
    if(info.error)txt+=' '+info.error;
    holder.textContent=txt;
    var b=document.getElementById('passport-sync-button');if(b){b.disabled=info.status==='syncing'||info.status==='local';}
  }
  function render(){
    var d=API.read();statsCards(d);
    document.querySelectorAll('.passport-tabs button').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.tab===view));});
    if(map){map.remove();map=null;}document.body.classList.remove('passport-map-is-fullscreen');
    panel.replaceChildren();
    if(view==='overview')overview(d);
    if(view==='visits')visits(d);
    if(view==='artists'||view==='museums')directory(view,d);
    if(view==='originals')originals(d);
    if(view==='collections')collections(d);
    if(view==='exhibitions')exhibitionsSection(d);
    if(view==='map')mapSection(d);
    if(view==='timeline')timeline(d);
    if(view==='stats')statistics(d);
    syncStatus();
  }
  function exportPassport(){
    var d={format:'OldPictureArtPassport',version:2,exportedAt:new Date().toISOString(),
      passport:API.read(),paintingLikes:Object.keys(likes()).filter(function(k){return !!likes()[k];}),
      exhibitionLikes:Object.keys(favorites()).filter(function(k){return !!favorites()[k];})};
    var blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');
    a.href=url;a.download='oldpictureart-passport.json';document.body.append(a);a.click();a.remove();
    setTimeout(function(){URL.revokeObjectURL(url);},1000);feedback('Резервная копия сохранена на устройство.');
  }
  function importPassport(file){
    if(file.size>3*1024*1024){feedback('Максимальный размер файла — 3 МБ.');return;}
    file.text().then(function(raw){var d=JSON.parse(raw);
      if(!d||d.format!=='OldPictureArtPassport'||![1,2].includes(d.version)||!d.passport)throw Error('Неверный формат паспорта');
      // Preserve IDs even when their works or entities disappeared from current catalog.
      confirmDialog('Импорт заменит текущий паспорт на этом устройстве и отправит изменения в облако. Продолжить?',function(){
        if(!API.write(API.normalize(d.passport))){feedback('Не удалось сохранить паспорт.');return;}
        var l=likes(),lp=JSON.parse(localStorage.getItem('likes-pending')||'{}');
        (Array.isArray(d.paintingLikes)?d.paintingLikes:[]).forEach(function(k){if(typeof k==='string'&&/^[\w-]{1,40}$/.test(k)){l[k]=true;lp[k]=true;}});
        localStorage.setItem('likes',JSON.stringify(l));localStorage.setItem('likes-pending',JSON.stringify(lp));
        var f=favorites(),fp=JSON.parse(localStorage.getItem('afishaFavoritesPending')||'{}');
        (Array.isArray(d.exhibitionLikes)?d.exhibitionLikes:[]).forEach(function(k){if(typeof k==='string'&&k.length<300){f[k]=true;fp[k]=true;}});
        localStorage.setItem('afishaFavorites',JSON.stringify(f));localStorage.setItem('afishaFavoritesPending',JSON.stringify(fp));
        if(typeof afishaAccountKey==='function'&&afishaAccountKey())localStorage.setItem('afishaFavoritesAccount',afishaAccountKey());
        if(typeof cloudSync==='function')cloudSync('force');
        if(typeof syncAfishaFavorites==='function')syncAfishaFavorites();
        API.sync();feedback('Паспорт импортирован. Архивные записи сохранены.');
      });
    }).catch(function(e){feedback('Ошибка импорта: '+e.message);});
  }
  document.querySelectorAll('.passport-tabs button').forEach(function(b){b.addEventListener('click',function(){switchTab(b.dataset.tab);});});
  document.getElementById('passport-sync-button').addEventListener('click',function(){API.sync().then(function(){render();syncStatus();});});
  document.getElementById('passport-export').addEventListener('click',exportPassport);
  document.getElementById('passport-import').addEventListener('change',function(e){var f=e.target.files&&e.target.files[0];if(f)importPassport(f);e.target.value='';});
  window.addEventListener('opa:passport-sync',syncStatus);
  window.addEventListener('opa:passport-change',render);
  window.addEventListener('opa:afisha-favorites',render);
  window.addEventListener('storage',function(e){if(e.key&&/^(opaPassport:v1:|likes$|afishaFavorites$|session$)/.test(e.key))render();});
  window.addEventListener('hashchange',function(){var h=location.hash.slice(1);if(tabs.includes(h)){view=h;render();}});
  render();syncStatus();
  API.sync().then(function(){render();syncStatus();});
  if(typeof cloudSync==='function')cloudSync('force').then(render);
  if(typeof syncAfishaFavorites==='function')syncAfishaFavorites().then(render);
})();
