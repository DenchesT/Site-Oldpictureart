/* Progressive enhancement for Old Picture Art. Existing UI works without JS. */
(function () {
  'use strict';
  function setup() {
    var chips = document.getElementById('opa-active-filters');
    var sidebar = document.getElementById('sidebar');
    if (chips && sidebar) {
      function update() {
        var active = Array.prototype.slice.call(sidebar.querySelectorAll('.filter-link.active, .filter-link[aria-current="true"], .dec-row[aria-pressed="true"]'));
        var search = document.getElementById('search');
        chips.replaceChildren();
        active.slice(0,12).forEach(function (link) {
          var label = (link.textContent || link.getAttribute('title') || '').trim().replace(/\s*\(\d+\)$/,'');
          if (!label) return;
          var b = document.createElement('button');b.type='button';b.className='opa-chip';
          b.textContent=label+' ×';b.title='Снять фильтр '+label;
          b.addEventListener('click',function(){link.click();setTimeout(update,0);});chips.appendChild(b);
        });
        if (search && search.value.trim()) {
          var q=document.createElement('button');q.type='button';q.className='opa-chip';
          q.textContent='Поиск: '+search.value.trim().slice(0,35)+' ×';
          q.addEventListener('click',function(){search.value='';search.dispatchEvent(new Event('input',{bubbles:true}));update();});
          chips.appendChild(q);
        }
        chips.hidden = chips.childElementCount===0;
        var menu=document.getElementById('menu-toggle');
        if(menu){menu.setAttribute('aria-label',chips.childElementCount?'Фильтры, выбрано '+chips.childElementCount:'Фильтры и разделы');}
      }
      // OPA MAIN PAGE POLISH: visit details visibility and live chips
      document.addEventListener('opa:filters-changed', update);
      sidebar.addEventListener('click',function(){setTimeout(update,0);});
      sidebar.addEventListener('change',function(){setTimeout(update,0);});
      var search=document.getElementById('search');if(search)search.addEventListener('input',update);
      var reset=document.getElementById('reset-filter');if(reset)reset.addEventListener('click',function(){setTimeout(update,0);});
      update();
    }
    // The full visits list remains in the DOM for dates/accessibility; avoid an empty teaser.
    var nowBox = document.getElementById('now-on');
    var nowWrap = document.querySelector('.opa-now-collapsible');
    if (nowWrap && nowBox) nowWrap.hidden = nowBox.hidden;
    // Clearer action names for assistive technology, without changing toolbar structure.
    var actions = {'[data-share-btn]':'Поделиться ссылкой на картину',
      '[aria-label="Случайная картина"]':'Открыть случайную картину',
      '[aria-label="Скачать картину"]':'Скачать картину в полном размере'};
    Object.keys(actions).forEach(function (selector) {
      document.querySelectorAll(selector).forEach(function(el){el.title=actions[selector];el.setAttribute('aria-label',actions[selector]);});
    });
    // Visit gallery: selected cover is already rendered first by the generator.
    document.querySelectorAll('.visit-page .shots a.shot').forEach(function(a,i){
      if(i===0)a.setAttribute('aria-label','Открыть главную фотографию посещения');
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);
  else setup();
})();
