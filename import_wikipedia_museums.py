# -*- coding: utf-8 -*-
"""Дополняет afisha.json источниками из двух категорий Википедии.

Без --online использует сохранённые прямые страницы двух категорий,
не доверяя им как источникам адресов, сайтов и выставочных дат.
С --online делает актуальный обход категорий и подкатегорий MediaWiki API
и берёт дополнительные сведения из Wikidata с пометкой происхождения.

Скрипт не удаляет музейные источники или выставки и не запускает публикацию.
"""

import argparse
from collections import deque
from copy import deepcopy
import difflib
import json
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
WIKI_API = "https://ru.wikipedia.org/w/api.php"
DATA_API = "https://www.wikidata.org/w/api.php"
ROOT_CATEGORIES = (
    "Категория:Художественные музеи России",
    "Категория:Художественные музеи",
)
EXCLUDED_PAGE_PREFIXES = (
    "Список ", "Списки ", "Категория:", "Художественные музеи (",
)
EXCLUDED_SUBCATEGORIES = ("Экспонаты", "Категории художественных", "Коллекции", "Списки")
ALIASES = {"музей российской академии художеств": "музей академии художеств"}


def norm(value):
    return re.sub(r"\s+", " ", re.sub(r"[\.,«»\-—]", " ", str(value or "").casefold())).strip()


def identity(title):
    n = norm(title)
    return ALIASES.get(n, n)


def wiki_url(title):
    return "https://ru.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="():")


def seeds(path=BASE / "museum_seeds.txt"):
    origin = ""
    out = []
    for text in path.read_text(encoding="utf-8-sig").splitlines():
        text = text.strip()
        if not text:
            continue
        if text.startswith("#"):
            origin = ROOT_CATEGORIES[0] if "России" in text else ROOT_CATEGORIES[1]
            continue
        if text.startswith(EXCLUDED_PAGE_PREFIXES):
            continue
        out.append({"museum": text, "wikipedia_url": wiki_url(text),
                    "wikipedia_category": wiki_url(origin), "review_status": "нужно проверить официальный сайт"})
    return out


def request_json(url, params, retries=3):
    full = url + "?" + urlencode(params)
    last = None
    for i in range(retries):
        try:
            req = Request(full, headers={"User-Agent": "OldPictureArt-MuseumIndexer/1.0 (research; noncommercial)",
                                         "Accept": "application/json"})
            with urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError("Не удалось обратиться к Wikimedia: " + str(last))


def members(category):
    """Перебор всех страниц категории с продолжениями MediaWiki API."""
    cont = {}
    while True:
        params = {"action": "query", "format": "json", "list": "categorymembers",
                  "cmtitle": category, "cmlimit": "max", "cmprop": "title|type", "cmtype": "page|subcat", **cont}
        data = request_json(WIKI_API, params)
        for x in data.get("query", {}).get("categorymembers", []):
            yield x
        cont = data.get("continue", {})
        if not cont:
            break


def discover(depth=4, max_categories=1000):
    """Не игнорируем страны/города: они лежат в подкатегориях."""
    queue = deque((x, 0) for x in ROOT_CATEGORIES)
    categories, pages = set(), {}
    truncated = False
    while queue:
        category, level = queue.popleft()
        if category in categories:
            continue
        if len(categories) >= max_categories:
            truncated = True
            break
        categories.add(category)
        for m in members(category):
            title = m["title"]
            if m.get("ns") == 14:
                if level < depth and not any(k.casefold() in title.casefold() for k in EXCLUDED_SUBCATEGORIES):
                    queue.append((title, level + 1))
            elif m.get("ns") == 0 and not title.startswith(EXCLUDED_PAGE_PREFIXES):
                pages.setdefault(title, {"museum": title, "wikipedia_url": wiki_url(title),
                                         "wikipedia_category": wiki_url(category),
                                         "review_status": "нужно проверить официальный сайт"})
        print(f"  Категорий просмотрено: {len(categories)}, найдено статей: {len(pages)}", file=sys.stderr)
    return list(pages.values()), {"categories_scanned": len(categories), "categories_truncated": truncated,
                                  "depth": depth, "items_discovered": len(pages)}


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i+n]


def wikidata_enrich(entries):
    """Wikidata — сведения для проверки, НЕ подтверждение работы музея."""
    bytitle = {e["museum"]: e for e in entries if not e.get("website")}
    qids = {}
    for batch in chunks(list(bytitle), 40):
        data = request_json(WIKI_API, {"action":"query", "format":"json", "formatversion":2,
                            "prop":"pageprops", "ppprop":"wikibase_item", "redirects":1,
                            "titles":"|".join(batch)})
        for page in data.get("query", {}).get("pages", []):
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid and page.get("title") in bytitle:
                qids[qid] = bytitle[page["title"]]
    stats={"wikidata_ids":len(qids), "sites_from_wikidata":0, "addresses_from_wikidata":0}
    for batch in chunks(list(qids), 40):
        data=request_json(DATA_API, {"action":"wbgetentities", "format":"json", "ids":"|".join(batch),
                                     "props":"claims"})
        for qid, entity in data.get("entities", {}).items():
            entry=qids.get(qid)
            if not entry:continue
            entry["wikidata_id"] = qid
            claims=entity.get("claims", {})
            def vals(prop):
                for claim in claims.get(prop, []):
                    dv=claim.get("mainsnak", {}).get("datavalue", {}).get("value")
                    if dv is not None:
                        yield dv
            if not entry.get("website"):
                for url in vals("P856"):
                    if isinstance(url,str) and urlsplit(url).scheme=="https" and urlsplit(url).netloc:
                        entry["website"]=url; entry["url"]=url
                        entry["website_source"]="Wikidata P856 (не проверено вручную)"
                        entry["review_status"]="официальный сайт из Wikidata — проверить"
                        stats["sites_from_wikidata"]+=1
                        break
            if not entry.get("address"):
                for addr in list(vals("P6375"))+list(vals("P969")):
                    address=addr.get("text") if isinstance(addr,dict) else addr
                    if isinstance(address,str) and address.strip():
                        entry["address"]=address.strip()
                        entry["address_source"]="Wikidata P6375/P969 (не проверено вручную)"
                        stats["addresses_from_wikidata"]+=1
                        break
            for point in vals("P625"):
                if isinstance(point,dict) and point.get("latitude") is not None:
                    entry["location"]={"lat":point["latitude"], "lon":point["longitude"],
                                       "source":"Wikidata P625 — геоточка не гарантирует адрес входа"}
                    break
    return stats


def load_reviewed():
    return json.loads((BASE / "verified_museums.json").read_text(encoding="utf-8"))


def apply_reviewed(entries, reviewed=None):
    reviewed=reviewed if reviewed is not None else load_reviewed()
    byname={identity(x["museum"]):x for x in entries}
    for museum, data in reviewed.items():
        key=identity(museum)
        item=byname.get(key)
        if item is None:
            item={"museum": museum, "review_status":"официальные данные проверены вручную"}
            entries.append(item);byname[key]=item
        item.update({k:v for k,v in data.items() if k not in item or not item[k]})
        item["review_status"]="официальные данные проверены вручную 2026-10-31"
        item.setdefault("priority","medium")
    return entries


def merge_sources(old, new):
    merged=deepcopy(old)
    byname={identity(x.get("museum")): x for x in merged if isinstance(x,dict)}
    added=updated=0
    for entry in new:
        key=identity(entry.get("museum"))
        if not key:continue
        if key in byname:
            found=byname[key]
            change=False
            for k,v in entry.items():
                if k=="museum":continue
                if k not in found or not found[k]:found[k]=v;change=True
            if change:updated+=1
        else:
            merged.append(entry);byname[key]=entry;added+=1
    return merged,added,updated


def merge_exhibitions(old, new):
    merged=deepcopy(old);added=[];skipped=[]
    for exhibition in new:
        city=norm(exhibition["city"]);title=norm(exhibition["title"])
        duplicate=False
        for existing in merged:
            if norm(existing.get("city")) != city:continue
            prev=norm(existing.get("title"))
            if prev==title or difflib.SequenceMatcher(None,prev,title).ratio() > .84:
                duplicate=True;break
        if duplicate: skipped.append(exhibition["title"])
        else:merged.append(exhibition);added.append(exhibition["title"])
    return merged,added,skipped


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check",action="store_true", help="вывести план, ничего не изменять")
    p.add_argument("--apply",action="store_true", help="записать изменения в afisha.json")
    p.add_argument("--online",action="store_true", help="считать также вложенные категории Википедии онлайн")
    p.add_argument("--wikidata",action="store_true", help="обогатить официальными сайтами/адресами из Wikidata; только с --online")
    p.add_argument("--depth",type=int,default=4,help="глубина обхода подкатегорий")
    p.add_argument("--max-categories",type=int,default=1000)
    p.add_argument("--no-exhibitions",action="store_true")
    p.add_argument("--file",type=Path,default=Path("afisha.json"),help="путь к текущему afisha.json")
    args=p.parse_args(argv)
    if not args.check and not args.apply:p.error("Выберите --check или --apply")
    if args.wikidata and not args.online:p.error("--wikidata используется только вместе с --online")
    if not args.file.is_file():p.error("Не найден afisha.json; запустите в корне проекта")
    obj=json.loads(args.file.read_text(encoding="utf-8-sig"))
    if not isinstance(obj,dict) or not isinstance(obj.get("exhibitions"),list) or not isinstance(obj.get("sources"),list):
        raise RuntimeError("Неверный формат afisha.json: нужны массивы exhibitions и sources")
    seed=seeds()
    discovery={"mode":"offline seed", "seed_direct_articles":len(seed)}
    if args.online:
        fresh,info=discover(depth=args.depth,max_categories=args.max_categories)
        seed,_,_=merge_sources(seed,fresh)
        discovery.update(info);discovery["mode"]="online category tree"
    if args.wikidata:
        discovery.update(wikidata_enrich(seed))
    apply_reviewed(seed)
    new_sources,a,u=merge_sources(obj["sources"],seed)
    reviewed=json.loads((BASE/"verified_exhibitions.json").read_text(encoding="utf-8"))
    new_exhib, added, skipped=merge_exhibitions(obj["exhibitions"],[] if args.no_exhibitions else reviewed)
    report={"discovery":discovery, "sources_before":len(obj["sources"]),"sources_after":len(new_sources),
            "new_sources":a,"enriched_sources":u,"exhibitions_before":len(obj["exhibitions"]),
            "exhibitions_after":len(new_exhib),"new_verified_exhibitions":added,
            "skipped_duplicate_exhibitions":skipped,
            "museum_sources_with_address":sum(bool(x.get("address")) for x in new_sources),
            "museum_sources_with_website":sum(bool(x.get("website") or x.get("url")) for x in new_sources),
            "sources_needing_review":sum("провер" in x.get("review_status","") and "вручную" not in x.get("review_status","") for x in new_sources)}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not args.apply:return 0
    original=args.file.read_bytes()
    backup=args.file.with_name(args.file.name+".pre_wikipedia_museums.bak")
    if not backup.exists():shutil.copy2(args.file,backup)
    obj["sources"]=new_sources;obj["exhibitions"]=new_exhib
    if added:
        obj["updated"]="2026-10-31"
    obj["source_selection_rule"]=(obj.get("source_selection_rule") or "")
    obj["wikipedia_museum_sources"]={"categories":[wiki_url(x) for x in ROOT_CATEGORIES],
                                      "seed_created":"2026-10-31", "seed_may_be_outdated":True,
                                      "note":"Снимок страниц Википедии может быть устаревшим. Полный актуальный обход — --online. Сведения из Wikipedia и Wikidata не подтверждают действующую выставку. События только по официальным источникам."}
    tmp=args.file.with_name(args.file.name+".tmp-wiki")
    try:
        tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8"))
        tmp.replace(args.file)
    except Exception:
        if tmp.exists():tmp.unlink()
        args.file.write_bytes(original)
        raise
    print("Обновлено:",args.file,"\nРезервная копия:",backup)
    return 0


if __name__=="__main__":
    sys.exit(main())
