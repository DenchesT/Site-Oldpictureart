"""Small source fixture that captures important main-template anchors from main@2d209a1."""

def render_index(all_posts, visits=None):
    cards = []
    p = {"filename": "a.html"}
    cat_no = {id(p): 1}
    cat_width = 3
    artist_name = title_name = "A"
    cards.append(f"""<article class="card">
    <span class="card-no">{cat_no[id(p)]:0{cat_width}d}</span>
    <a class="card-img" href="{p['filename']}"></a>
    <div class="card-body">
        <div class="card-title">{title_name}</div>
    </div></article>""")
    head = ""
    def section(icon, label, content):
        return f'<div>{label}</div>'
    return f"""<!DOCTYPE html><html lang="ru" data-theme="light"><head>
{head}
</head><body>
{now_on_block(visits if visits is not None else load_json(VISITS_FILE, []), all_posts)}
<div class="layout"><aside class="sidebar">
<div class="sidebar-section sidebar-search">
  <label class="visually-hidden" for="search">Поиск по галерее</label>
  <input type="search" class="search-box" placeholder="Поиск по художнику, картине, музею…" id="search" autocomplete="off">
</div>
<button type="button" id="reset-filter" class="filter-reset">Сбросить все фильтры</button>
{section('icon-archive', 'Архив', arh)}
{section('icon-technique', 'Техника', th)}
{afisha_html}
{fav_html}
{popular_html}
{theme_html}
{map_link_html}
{visits_link_html}
{index_link_html}
{stats_link_html}
{tg_link_html}
{quiz_link_html}
{timeline_link_html}
</aside><main class="main-content">
<div class="results-bar">
  <span id="results-count" class="results-count" role="status" aria-live="polite"></span>
  <div class="bar-controls">
  <span class="bar-label" id="sort-label">Порядок</span>
  <label class="visually-hidden" for="sort">Порядок записей</label>
  <select id="sort">
    <option value="new">Сначала новые</option>
    <option value="cyear">По году создания</option>
    <option value="cyear-desc">По году создания, новые сверху</option>
  </select></div></div></main></div>
<script>
let activeFilters = {{ search: '', type: null, val: null, year: null, from: null, to: null }};
function resetAllFilters() {{
    activeFilters = {{ search: '', type: null, val: null, year: null, from: null, to: null }};
    const searchBox = document.getElementById('search');
    if (searchBox) searchBox.value = '';
    document.querySelectorAll('.filter-link.active').forEach(l => {{}});
}}
function applyFilters() {{
    const hasActive = !!activeFilters.search;
    const visible = 1;
    const counter = document.getElementById('results-count');
    if (counter) counter.textContent = hasActive ? (visible + ' ' + plural(visible, 'картина', 'картины', 'картин')) : '';
    const empty = document.getElementById('no-results');
    if (empty) empty.hidden = visible !== 0;
}}

function plural(n, one, few, many) {{ return one; }}
document.addEventListener('DOMContentLoaded', function() {{
    const searchBox = document.getElementById('search');
    if (searchBox) {{
        let t = null;
        searchBox.addEventListener('input', function(e) {{
            const v = e.target.value.toLowerCase().trim();
            clearTimeout(t);
            t = setTimeout(function() {{ activeFilters.search = v; applyFilters(); }}, 120);
        }});
    }}
}});
</script></body></html>"""
