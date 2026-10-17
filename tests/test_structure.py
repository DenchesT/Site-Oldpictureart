# -*- coding: utf-8 -*-
"""Устройство кода: пакет sitebuild, модули питона, свои копии библиотек.

  • каждый модуль sitebuild/ импортируется сам по себе — без build_site;
  • всё, что модуль определяет, перечислено в его __all__ — иначе имя
    пропадёт из build_site, и rebuild_pages.py или проверка упадут;
  • все имена, к которым скрипты и проверки обращаются через build_site
    (bs.render_index, build_site.clean_url…), там есть;
  • у однофамильцев порядок в указателе один и тот же при каждой сборке;
  • ссылка «Пост в Telegram» ведёт на сам пост;
  • pyflakes не находит в коде неопределённых и забытых имён;
  • в requirements.txt все версии закреплены, а сборка ставит модули,
    только если чего-то нет;
  • страницы не тянут библиотеки и шрифты с чужих серверов, и всё, на что
    они ссылаются в vendor/ и fonts/, лежит на месте.

Запуск:  python tests/test_structure.py
"""

import ast
import glob
import importlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.argv = ["build_site.py"]

import build_site as bs  # noqa: E402

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# ---------- пакет sitebuild ----------
MODULES = sorted(os.path.splitext(os.path.basename(p))[0]
                 for p in glob.glob("sitebuild/*.py") if not p.endswith("__init__.py"))
ok("модулей в sitebuild — больше десяти", len(MODULES) > 10, ", ".join(MODULES))

alone = []
for m in MODULES:
    r = subprocess.run([sys.executable, "-c", f"import sitebuild.{m}"], capture_output=True, text=True, cwd=ROOT)
    if r.returncode:
        alone.append(f"{m}: {r.stderr.strip().splitlines()[-1][:120]}")
ok("каждый модуль импортируется сам по себе", not alone, "; ".join(alone))

missing_all = []
for m in MODULES:
    mod = importlib.import_module(f"sitebuild.{m}")
    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    defined = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
    public = {n for n in defined if not n.startswith("_") and n != "logger"}
    exported = set(getattr(mod, "__all__", []))
    lost = sorted(public - exported)
    if lost:
        missing_all.append(f"{m}: {', '.join(lost[:5])}")
    ghost = sorted(n for n in exported if not hasattr(mod, n))
    if ghost:
        missing_all.append(f"{m}: в __all__ нет такого — {', '.join(ghost)}")
ok("всё определённое в модулях — в их __all__", not missing_all, "; ".join(missing_all))

used = set()
for path in glob.glob("*.py") + glob.glob("tests/*.py"):
    used |= set(re.findall(r"\b(?:bs|build_site)\.([A-Za-z_][A-Za-z0-9_]*)\b", open(path, encoding="utf-8").read()))
absent = sorted(n for n in used - {"py"} if not hasattr(bs, n))   # «build_site.py» в тексте
ok("имена, которые зовут через build_site, на месте", not absent, ", ".join(absent))

# ---------- порядок однофамильцев ----------
NAMES = ["Анри Мартен", "Пьер-Огюст Мартен", "Жан Мартен", "Клод Моне"]
order = subprocess.run(
    [sys.executable, "-c", "import sys; sys.argv=['x']; from sitebuild.slugs import surname_key; "
     f"print('|'.join(sorted({NAMES!r}, key=surname_key)))"],
    capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED="1")).stdout.strip()
order2 = subprocess.run(
    [sys.executable, "-c", "import sys; sys.argv=['x']; from sitebuild.slugs import surname_key; "
     f"print('|'.join(sorted({list(reversed(NAMES))!r}, key=surname_key)))"],
    capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED="2")).stdout.strip()
ok("однофамильцы — всегда в одном порядке", order and order == order2, f"{order} / {order2}")
ok("…и по фамилии: Мартены перед Моне", order.split("|")[-1] == "Клод Моне", order)

# ---------- «Пост в Telegram» ----------
link = bs.telegram_post_link({"id": 1234})
ok("ссылка «Пост в Telegram» ведёт на пост", f'href="{bs.TELEGRAM_URL}/1234"' in link and "Пост в Telegram" in link, link)
ok("…открывается в новой вкладке", 'target="_blank"' in link and 'rel="noopener"' in link)
ok("без номера поста ссылки нет", bs.telegram_post_link({}) == "")
pages = glob.glob("docs/*.html")
old_label = [p for p in pages if "Обсудить в Telegram" in open(p, encoding="utf-8").read()]
ok("старой подписи «Обсудить в Telegram» на страницах нет", not old_label, ", ".join(old_label[:3]))

# ---------- pyflakes ----------
try:
    from pyflakes import api as pf_api, reporter as pf_reporter
except ImportError:
    pf_api = None
if pf_api is None:
    print("pyflakes не установлен — проверку кода пропускаю (pip install -r requirements-dev.txt)")
else:
    import io
    out, err = io.StringIO(), io.StringIO()
    files = glob.glob("*.py") + glob.glob("sitebuild/*.py") + glob.glob("tests/*.py") + glob.glob("cloud/*/*.py")
    for path in files:
        pf_api.checkPath(path, pf_reporter.Reporter(out, err))
    # build_site.py — фасад: импортирует имена, чтобы их было видно снаружи
    # (pyflakes считает их «неиспользованными»), и берёт свои через «*»
    # («может быть не определено»). Это не ошибки: что все нужные имена в
    # build_site есть, проверено выше.
    FACADE = ("imported but unused", "unable to detect undefined names", "defined from star imports")
    problems = [line for line in out.getvalue().splitlines()
                if not (line.startswith("build_site.py:") and any(f in line for f in FACADE))]
    ok("pyflakes: в коде нет забытых и неопределённых имён", not problems and not err.getvalue(),
       " | ".join(problems[:4]) + err.getvalue()[:200])

# ---------- модули питона ----------
from sitebuild import deps  # noqa: E402

pins = deps.read_requirements()
ok("requirements.txt читается", {"telethon", "Pillow", "TelethonFakeTLS", "boto3"} <= set(pins), str(pins))
loose = [line.strip() for line in open("requirements.txt", encoding="utf-8")
         if line.split("#")[0].strip() and "==" not in line]
ok("в requirements.txt все версии закреплены (==)", not loose, "; ".join(loose))
dev = deps.read_requirements(os.path.join(ROOT, "requirements-dev.txt"))
ok("requirements-dev.txt: moto и pyflakes закреплены", {"moto", "pyflakes"} <= set(dev), str(dev))

calls = []
ok("всё стоит — pip не зовётся", deps.ensure_requirements(run=calls.append, version_of=lambda n: pins[n]) == "ok"
   and not calls)
st = deps.ensure_requirements(run=calls.append, version_of=lambda n: None if n == "telethon" else pins[n])
ok("чего-то нет — ставит ровно по requirements.txt", st == "installed" and calls
   and calls[0][-4:-2] == ["-r", deps.REQUIREMENTS_FILE] and "--upgrade" not in calls[0], str(calls))


def broken(cmd):
    raise OSError("нет сети")


ok("pip не смог — сборка не падает", deps.ensure_requirements(run=broken, version_of=lambda n: "0") == "failed")
src = open("build_site.py", encoding="utf-8").read()
ok("сборка больше не делает pip install --upgrade", '"--upgrade"' not in src)

# ---------- свои копии библиотек и шрифтов ----------
FOREIGN = re.compile(r'(?:src|href)="https?://(?:unpkg\.com|cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|'
                     r'fonts\.googleapis\.com|fonts\.gstatic\.com)[^"]*"')
foreign = sorted({os.path.basename(p) for p in pages if FOREIGN.search(open(p, encoding="utf-8").read())})
ok("страницы не берут библиотеки и шрифты с чужих серверов", not foreign, ", ".join(foreign[:5]))

refs = set()
for p in pages:
    refs |= set(re.findall(r'(?:src|href)="((?:vendor|fonts)/[^"?#]+)', open(p, encoding="utf-8").read()))
gone = sorted(r for r in refs if not os.path.isfile(os.path.join("docs", r)))
ok("всё, на что ссылаются страницы в vendor/ и fonts/, на месте", refs and not gone, ", ".join(gone))
ok("Leaflet и группировка меток — свои копии",
   {"vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css",
    "vendor/leaflet.markercluster/leaflet.markercluster.js"} <= refs, ", ".join(sorted(refs)))

css = open("docs/fonts/fonts.css", encoding="utf-8").read()
font_urls = re.findall(r"url\(([^)]+)\)", css)
lost_fonts = [u for u in font_urls if not os.path.isfile(os.path.join("docs/fonts", u.strip("'\"")))]
ok("все шрифты из fonts.css лежат рядом", font_urls and not lost_fonts, ", ".join(lost_fonts))
ok("у шрифтов font-display: swap — текст виден сразу", css.count("font-display: swap") == css.count("@font-face"))
leaf_css = open("docs/vendor/leaflet/leaflet.css", encoding="utf-8").read()
lost_img = [u for u in re.findall(r"url\(([^)]+)\)", leaf_css)
            if not u.startswith(("data:", "#")) and not os.path.isfile(os.path.join("docs/vendor/leaflet", u.strip("'\"")))]
ok("картинки, которые просит leaflet.css, на месте", not lost_img, ", ".join(lost_img))
licenses = [p for p in ("docs/vendor/leaflet/LICENSE", "docs/vendor/leaflet.markercluster/LICENSE",
                        "docs/vendor/color-thief/LICENSE") if not os.path.isfile(p)]
ok("лицензии библиотек лежат рядом с ними", not licenses and glob.glob("docs/fonts/OFL-*.txt"), ", ".join(licenses))

# ---------- логотип Яндекса на карте ----------
import site_common as sc  # noqa: E402

ok("путь к логотипу подставлен в скрипт карты", "__YANDEX_LOGO__" not in sc.MAP_LAYERS_JS
   and f"var LOGO = '{sc.YANDEX_LOGO}';" in sc.MAP_LAYERS_JS)
_isfile = os.path.isfile
try:
    os.path.isfile = lambda p: p.replace("\\", "/").endswith("docs/vendor/yandex/logo.png") or _isfile(p)
    found = sc._yandex_logo()
finally:
    os.path.isfile = _isfile
ok("положили docs/vendor/yandex/logo.png — карта берёт его", found in ("vendor/yandex/logo.png", "vendor/yandex/logo.svg"), found)

print("\n====== УСТРОЙСТВО КОДА ======")
for name, passed, extra in results:
    print(f"{'OK  ' if passed else 'FAIL'}  {name}{('  — ' + extra) if extra and not passed else ''}")
fails = [r for r in results if not r[1]]
print(f"\nВсего: {len(results)}, провалено: {len(fails)}")
sys.exit(1 if fails else 0)
