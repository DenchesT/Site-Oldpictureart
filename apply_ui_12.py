# -*- coding: utf-8 -*-
"""Apply the 12 incremental usability refinements to Old Picture Art generators.
No Git operations or network requests. Run at repository root.
"""
from pathlib import Path
import shutil,sys,ast

ROOT=Path.cwd()

def once(src, old, new, label, optional=False):
    n=src.count(old)
    if n==1:return src.replace(old,new,1)
    if optional and n==0:return src
    raise RuntimeError(f'{label}: expected one match; got {n}. No files changed. Update was made for a different revision.')

def main():
    if not (ROOT/'sitebuild/visits.py').is_file():
        raise SystemExit('Run inside project root (where sitebuild/ exists).')
    edits={}
    def read(path):return (ROOT/path).read_text(encoding='utf-8')
    v=read('sitebuild/visits.py')
    if 'def visit_cover(' not in v:
        helper="""def visit_cover_index(v):
    # Offline score; use cover_index (zero-based) for manual override.
    pictures = v.get('images') or []
    if not pictures:return 0
    try:
        override=int(v.get('cover_index'))
        if 0 <= override < len(pictures):return override
    except (TypeError,ValueError):pass
    try:
        from PIL import Image,ImageStat,ImageFilter
        from functools import lru_cache
    except ImportError:
        return 1 if len(pictures)>1 else 0
    def score(path):
        try:
            with Image.open(path) as im:
                im.thumbnail((180,180)); im=im.convert('RGB')
                stat=ImageStat.Stat(im)
                colour=sum(stat.stddev)/3
                hist=im.convert('L').histogram(); total=sum(hist)
                import math
                entropy=-sum((n/total)*math.log2(n/total) for n in hist if n) if total else 0
                edges=ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).mean[0]
                # Many wall labels are nearly monochrome and low in texture.
                return colour*0.5 + entropy*4 + min(edges,35)*0.4
        except (OSError,ValueError):return -1
    candidates=[]
    for idx,rel in enumerate(pictures[:8]):
        path=__import__('os').path.join(OUTPUT_DIR,rel)
        candidates.append((score(path),idx))
    if max(s for s,_ in candidates)<0:return 1 if len(pictures)>1 else 0
    return max(candidates)[1]


def visit_cover(v):
    images=v.get('images') or []
    thumbs=v.get('thumbs') or []
    index=visit_cover_index(v)
    return thumbs[index] if index<len(thumbs) else images[index] if index<len(images) else ''


"""
        v=once(v,'def visit_card(v, show_place=True, place_text=None):',helper+'def visit_card(v, show_place=True, place_text=None):','visit helper')
    v=once(v,'    cover = (v.get("thumbs") or v.get("images") or [""])[0]','    cover = visit_cover(v)','visit thumbnail')
    v=once(v,'f\'<div class="card-img"><img src="{h(cover)}" alt="{h(typo_ru(heading))}"{size_attrs(cover)}\'','f\'<a class="card-img" href="{h(v["filename"])}" aria-label="Открыть посещение: {h(typo_ru(heading))}"><img src="{h(cover)}" alt="{h(typo_ru(heading))}"{size_attrs(cover)}\'','visit image start')
    v=once(v,'f\' loading="lazy" decoding="async"></div>\') if cover else', 'f\' loading="lazy" decoding="async"></a>\') if cover else','visit image end')
    v=once(v,'f\'<div class="card-museum visit-kind">{h(visit_kind_label(v["kind"]))}</div>\'','f\'<div class="card-museum visit-kind">{h(visit_kind_label(v["kind"]))}</div>\'\n        f\'<span class="visit-shot-count">{shots} {plural_ru(shots, "фотография", "фотографии", "фотографий")}</span>\'','visit photo count')
    v=once(v,'("f-when", "<span>Побывал</span>", v.get("visited", ""))','("f-when", "<span>Дата посещения</span>", v.get("visited", ""))','visit date')
    v=once(v,'<button type="button" data-view="grid" aria-pressed="true">Плитки</button>','<button type="button" data-view="grid" aria-pressed="true">Карточки</button>','visit view grid')
    v=once(v,'<button type="button" data-view="list" aria-pressed="false">Опись</button>','<button type="button" data-view="list" aria-pressed="false">Подробный список</button>','visit view list')
    v=once(v,'    for i, src in enumerate(photos):','    cover_order = list(range(len(photos)))\n    if photos:\n        chosen = visit_cover_index(visit)\n        if 0 <= chosen < len(photos):\n            cover_order.remove(chosen)\n            cover_order.insert(0, chosen)\n    for i in cover_order:\n        src = photos[i]','visit gallery cover first')
    # Photo captions for screenreader and discoverable photography order.
    v=once(v,'alt="{h(typo_ru(heading))}, снимок {i + 1}"','alt="{h(typo_ru(heading))}, фотография {i + 1} из {len(photos)}"','visit photo alt')
    # Include UI JS on both visits overview and detail page via common end marker.
    v=once(v,'{COMMON_JS}\n{RUN_STATUS_JS}','{COMMON_JS}\n<script src="opa-ui.js" defer></script>\n{RUN_STATUS_JS}','visits overview UI JS')
    v=once(v,'{LUPA_JS}\n{TOAST_JS}','{LUPA_JS}\n<script src="opa-ui.js" defer></script>\n{TOAST_JS}','visits detail UI JS')
    # All symbols publicly defined here need __all__ for project structure tests.
    v=once(v,"    'visit_card',", "    'visit_cover_index', 'visit_cover',\n    'visit_card',",'visits exports')
    edits['sitebuild/visits.py']=v

    p=read('sitebuild/posts.py')
    p=once(p,'f\'<div class="card-img"><img src="{cv}" alt="{artist_name} — {title_name}"{size_attrs(cv)} loading="lazy" decoding="async"></div>\'','f\'<a class="card-img" href="{h(p["filename"])}" aria-label="Открыть картину: {artist_name} — {title_name}"><img src="{cv}" alt="{artist_name} — {title_name}"{size_attrs(cv)} loading="lazy" decoding="async"></a>\'','catalogue image')
    p=once(p,'<div class="card-img"><img src="{cv}" alt="{artist_name} — {title_name}"{size_attrs(cv)} loading="lazy" decoding="async"></div>','<a class="card-img" href="{h(p[\'filename\'])}" aria-label="Открыть картину: {artist_name} — {title_name}"><img src="{cv}" alt="{artist_name} — {title_name}"{size_attrs(cv)} loading="lazy" decoding="async"></a>','home image')
    p=once(p,'id="view-list" aria-pressed="true" onclick="setView(\'list\')">Опись','id="view-list" aria-pressed="true" onclick="setView(\'list\')">Подробный список','home list name')
    p=once(p,'id="view-grid" aria-pressed="false" onclick="setView(\'grid\')">Плитки','id="view-grid" aria-pressed="false" onclick="setView(\'grid\')">Карточки','home grid name')
    # Include filtering chips on main page, using delegated listeners in external JS.
    p=once(p,'<div class="grid list" id="cards">','<div class="active-filter-chips" id="opa-active-filters" aria-label="Выбранные фильтры" hidden></div>\n<div class="grid list" id="cards">','filter chips')
    p=once(p,'<button type="button" class="menu-toggle"','<button type="button" class="menu-toggle"','menu hook',optional=True)
    # Insert script before render_index closing html, not earlier page renderer.
    start=p.index('def render_index(');stop=p.find('\ndef ',start+4);stop=len(p) if stop<0 else stop
    section=p[start:stop]
    section=once(section,'</body></html>', '<script src="opa-ui.js" defer></script>\n</body></html>','home JS')
    p=p[:start]+section+p[stop:]
    edits['sitebuild/posts.py']=p

    m=read('sitebuild/museums.py')
    m=once(m,'f\'<a href="{card_link}">Карта собраний</a> · \'','f\'<a href="{card_link}" class="museum-map-link">Показать на карте собраний</a> · \'','museum map link')
    m=once(m,'<a href="museums.html" class="back">Карта собраний</a>','<a href="{card_link}" class="back">Показать на карте</a>','museum top nav')
    edits['sitebuild/museums.py']=m

    a=read('sitebuild/afisha.py')
    a=once(a,'f\'<p class="afisha-dates"><span class="afisha-range">{h(date_range(item))}</span>\'','f\'<p class="afisha-dates"><span class="afisha-range">Сроки: {h(date_range(item))}</span>\'','afisha date label')
    a=once(a,'<span class="now-when afisha-when"></span>','<span class="now-when afisha-when" role="status"></span>','afisha status')
    edits['sitebuild/afisha.py']=a

    css=read('docs/style.css')
    css+="""
/* OPA UX enhancements: inherited palette and typographic scale unchanged. */
.card-img[href] { text-decoration:none; color:inherit; cursor:pointer; }
.card-img[href]:focus-visible { outline:2px solid var(--active); outline-offset:3px; }
.visit-shot-count { display:block; margin:.35rem 0 0; color:var(--muted); font-size:var(--fs-xs); font-family:var(--ff-data); }
.grid:not(.list) .visit-card .visit-shot-count { padding:0 var(--s3) var(--s2); }
.visit-view button { white-space:normal; }
.visit-page .shots .shot:focus-visible { outline:2px solid var(--active); outline-offset:3px; }
.active-filter-chips { display:flex; flex-wrap:wrap; gap:var(--s2); margin:0 0 var(--s3); }
.active-filter-chips[hidden] { display:none; }
.opa-chip { background:var(--accent-soft); color:var(--link); border:1px solid var(--border); border-radius:2px; font:inherit; font-size:var(--fs-xs); padding:.4rem .6rem; cursor:pointer; }
.opa-chip:hover, .opa-chip:focus-visible { outline:1px solid var(--active); }
.opa-filter-status { font:var(--fs-xs) var(--ff-data); color:var(--muted); margin:.4rem 0; }
.visit-page .shots { align-items:start; }
.visit-card .card-img:focus-visible, .card-img[href]:focus-visible { outline:2px solid var(--active); outline-offset:2px; }
.afisha-item .afisha-dates { display:flex; align-items:baseline; flex-wrap:wrap; gap:.4rem; }
.afisha-item .afisha-when:not(:empty) { font-weight:700; color:var(--active); }
.museum-map-link { font-weight:700; }
.post-topbar-right .topbar-btn { min-width:36px; min-height:36px; }
@media(max-width:760px) {
 .active-filter-chips { padding:0 var(--s2); }
 .opa-filter-status { padding:0 var(--s2); }
 .post-topbar-right .topbar-btn { min-width:42px; min-height:42px; }
 .visit-view button { min-height:40px; }
 .menu-toggle { min-height:42px; }
}
"""
    edits['docs/style.css']=css
    files={key:ROOT/key for key in edits}
    for key,path in files.items():
        if not path.is_file():raise RuntimeError('Missing '+key)
        bak=path.with_name(path.name+'.ux12.bak')
        if bak.exists():raise RuntimeError('Backup already exists: '+str(bak))
        if key.endswith('.py'):compile(edits[key],key,'exec')
    # Copy JS after all replacement validation; no partial patch on mismatch.
    js=(Path(__file__).resolve().parent/'opa-ui.js').read_text(encoding='utf-8')
    if (ROOT/'docs/opa-ui.js').exists():raise RuntimeError('docs/opa-ui.js already exists; refusing overwrite')
    if '--check' in sys.argv:
        print('PASS: all snippets match, Python sources compile; no writes made.');return
    for key,path in files.items():
        shutil.copy2(path,path.with_name(path.name+'.ux12.bak'))
        path.write_text(edits[key],encoding='utf-8')
        print('Updated',key)
    (ROOT/'docs/opa-ui.js').write_text(js,encoding='utf-8')
    print('Added docs/opa-ui.js. Rebuild pages before publishing.')

if __name__=='__main__':
    try:main()
    except (RuntimeError, OSError, SyntaxError) as e:
        print('ERROR:',e,file=sys.stderr);sys.exit(1)
