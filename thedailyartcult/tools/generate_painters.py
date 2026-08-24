#!/usr/bin/env python3
"""Generate assets/data/painters.json for play.html.

Pipeline:
  1. Wikidata SPARQL: humans with occupation painter (incl. subclasses),
     died <= 1965, born >= 1200, sitelinks >= floor.
  2. For each candidate, resolve a working Commons category (P373, then
     "Paintings_by_<name>", then "<name>") and validate it contains enough
     usable image files via the exact API call production code uses.
  3. Emit static JSON in the same shape as the embedded PAINTERS_MASTER
     fallback, plus era / sitelinks / img_count metadata.

Stdlib only. Manual rerun whenever you want fresh artists:
    python3 tools/generate_painters.py [--limit N] [--min-images N]
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

UA = ("thedailyartcult-painters-generator/1.0 "
      "(static art quiz site; contact: admin@thedailyartcult.lol)")
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

BIRTH_MIN_YEAR = 1200
DEATH_MAX_YEAR = 1965
MIN_SITELINKS = 8
POPULAR_SITELINKS = 40
MAX_PAINTERS = 1600
MIN_IMAGES = 8
MANIFEST_TARGET = 48      # max paintings kept per painter folder
MANIFEST_GOOD_ENOUGH = 24 # stop probing candidates at this size
MAX_SUBCAT_PROBES = 14    # per painter, across all candidate categories

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS_DIR)
OUT_PATH = os.path.join(ROOT, "assets", "data", "painters.json")
PAINTER_DIR = os.path.join(ROOT, "assets", "painters")
CACHE_PATH = os.path.join(TOOLS_DIR, ".commons_validation_cache.json")

COUNTRY_TAGS = {
    "france": "french", "netherlands": "dutch", "holland": "dutch",
    "spain": "spanish", "italy": "italian", "germany": "german",
    "united kingdom": "british", "england": "british",
    "great britain": "british", "united states of america": "american",
    "united states": "american", "russia": "russian",
    "russian empire": "russian", "soviet union": "russian",
    "austria": "austrian", "austria-hungary": "austrian",
    "belgium": "belgian", "flanders": "flemish", "poland": "polish",
    "japan": "japanese", "china": "chinese", "hungary": "hungarian",
    "czech republic": "czech", "czechoslovakia": "czech",
    "austrian silesia": "czech", "sweden": "swedish", "norway": "norwegian",
    "denmark": "danish", "finland": "finnish", "switzerland": "swiss",
    "portugal": "portuguese", "greece": "greek", "ireland": "irish",
    "scotland": "scottish", "wales": "welsh", "ukraine": "ukrainian",
    "canada": "canadian", "australia": "australian", "mexico": "mexican",
    "argentina": "argentine", "brazil": "brazilian", "romania": "romanian",
    "bulgaria": "bulgarian", "serbia": "serbian", "croatia": "croatian",
    "slovenia": "slovenian", "slovakia": "slovak", "latvia": "latvian",
    "lithuania": "lithuanian", "estonia": "estonian",
    "iceland": "icelandic", "turkey": "turkish",
    "ottoman empire": "ottoman", "iran": "persian", "persia": "persian",
    "india": "indian", "korea": "korean", "south korea": "korean",
    "vietnam": "vietnamese", "indonesia": "indonesian",
    "philippines": "filipino", "egypt": "egyptian", "morocco": "moroccan",
    "tunisia": "tunisian", "south africa": "south african",
    "israel": "israeli", "georgia": "georgian", "armenia": "armenian",
    "albania": "albanian", "bosnia and herzegovina": "bosnian",
}

MOVEMENT_TAGS = {
    "impressionism": "impressionist",
    "post-impressionism": "post-impressionist",
    "expressionism": "expressionist",
    "surrealism": "surrealist",
    "cubism": "cubist",
    "baroque": "baroque",
    "renaissance": "renaissance",
    "italian renaissance": "renaissance",
    "northern renaissance": "renaissance",
    "high renaissance": "renaissance",
    "early renaissance": "renaissance",
    "romanticism": "romantic",
    "realism": "realist",
    "realism (arts)": "realist",
    "symbolism": "symbolist",
    "fauvism": "fauvist",
    "abstract art": "abstract",
    "modern art": "modern",
    "modernism": "modern",
    "neoclassicism": "neoclassical",
    "rococo": "rococo",
    "mannerism": "mannerist",
    "pointillism": "pointillist",
    "neo-impressionism": "pointillist",
    "divisionism": "pointillist",
    "futurism": "futurist",
    "constructivism (art)": "constructivist",
    "suprematism": "suprematist",
    "dada": "dada",
    "art nouveau": "art-nouveau",
    "primitivism": "primitivist",
    "naive art": "naive",
    "academic art": "academic",
    "orientalism": "orientalist",
    "ashcan school": "realist",
    "hudson river school": "landscape",
    "landscape painting": "landscape",
    "portrait painting": "portrait",
    "genre painting": "genre",
    "still life": "still-life",
    "golden age of dutch painting": "baroque",
    "dutch golden age painting": "baroque",
}

OCCUPATION_QID = "Q1028181"  # painter (occupation)
MAX_SUBCLASSES = 80

BASE_SPARQL = """
SELECT ?item ?itemLabel ?birth ?death ?sitelinks ?p373 WHERE {
  ?item wdt:P106 ?occ .
  VALUES ?occ { %(occ_values)s }
  ?item wdt:P569 ?birth .
  ?item wdt:P570 ?death .
  FILTER(?death <= "%(death_max)d-12-31T00:00:00Z"^^xsd:dateTime)
  FILTER(?birth >= "%(birth_min)d-01-01T00:00:00Z"^^xsd:dateTime)
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= %(min_sitelinks)d)
  OPTIONAL { ?item wdt:P373 ?p373 . }
}
"""

SUBCLASS_SPARQL = """
SELECT ?sub WHERE { ?sub wdt:P279 wd:%s . }
"""

SPARQL_CHUNK = 10


def http_json(url, params=None, retries=3, timeout=60, backoff=2.0):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - retry any transport error
            last_err = exc
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"HTTP failed after {retries} tries: {url}: {last_err}")


def get_occupation_qids():
    """Q1028181 plus its direct subclasses (portrait painter, etc.)."""
    qids = [OCCUPATION_QID]
    try:
        data = http_json(SPARQL_ENDPOINT,
                         {"query": SUBCLASS_SPARQL % OCCUPATION_QID,
                          "format": "json"}, timeout=120, retries=4,
                         backoff=15)
        for row in data.get("results", {}).get("bindings", []):
            qid = row["sub"]["value"].rsplit("/", 1)[-1]
            if qid not in qids:
                qids.append(qid)
    except RuntimeError as exc:
        print(f"      WARN subclass lookup failed ({exc}); "
              f"using base occupation only")
    return qids[:MAX_SUBCLASSES]


def run_sparql():
    occ_qids = get_occupation_qids()
    print(f"[1/5] Querying Wikidata SPARQL "
          f"({len(occ_qids)} occupation classes, "
          f"chunks of {SPARQL_CHUNK}) ...")
    rows = []
    for start in range(0, len(occ_qids), SPARQL_CHUNK):
        chunk = occ_qids[start:start + SPARQL_CHUNK]
        query = BASE_SPARQL % {
            "occ_values": " ".join(f"wd:{q}" for q in chunk),
            "death_max": DEATH_MAX_YEAR,
            "birth_min": BIRTH_MIN_YEAR,
            "min_sitelinks": MIN_SITELINKS,
        }
        try:
            data = http_json(SPARQL_ENDPOINT,
                             {"query": query, "format": "json"},
                             retries=5, timeout=180, backoff=30)
            rows.extend(data.get("results", {}).get("bindings", []))
        except RuntimeError as exc:
            print(f"      WARN chunk {start // SPARQL_CHUNK} failed: "
                  f"{str(exc)[-140:]}; skipping")
        time.sleep(4)
    print(f"      got {len(rows)} raw rows")
    return rows


def year_of(dt_value):
    match = re.match(r"(-?\d{4})-", dt_value or "")
    return int(match.group(1)) if match else None


def slugify(name):
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "", text.lower())
    return text or "painter"


def build_candidates(rows):
    print("[2/5] Grouping candidates ...")
    painters = {}
    for row in rows:
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        painters.setdefault(qid, {
            "qid": qid,
            "born": year_of(row["birth"]["value"]),
            "died": year_of(row["death"]["value"]),
            "sitelinks": int(row["sitelinks"]["value"]),
            "p373": row.get("p373", {}).get("value"),
        })

    print(f"      resolving labels + claims for {len(painters)} items ...")
    qids = sorted(painters)
    label_ids = set()
    for start in range(0, len(qids), 50):
        batch = qids[start:start + 50]
        try:
            data = http_json(
                "https://www.wikidata.org/w/api.php",
                {"action": "wbgetentities", "ids": "|".join(batch),
                 "props": "labels|claims", "languages": "en",
                 "format": "json"}, timeout=90)
        except RuntimeError as exc:
            print(f"      WARN label batch lost: {exc.__class__.__name__}")
            continue
        for qid, entity in data.get("entities", {}).items():
            if qid not in painters:
                continue
            entry = painters[qid]
            entry["name"] = entity.get("labels", {}).get("en", {}).get("value")
            entry["country_qids"] = []
            entry["movement_qids"] = []
            claims = entity.get("claims", {})
            for prop, key in (("P27", "country_qids"),
                              ("P135", "movement_qids")):
                for claim in claims.get(prop, []):
                    target = claim.get("mainsnak", {}).get(
                        "datavalue", {}).get("value", {}).get("id")
                    if target:
                        entry[key].append(target)
                        label_ids.add(target)
        time.sleep(0.1)

    resolved = _resolve_labels(sorted(label_ids))
    # Drop entries without an English name, disambiguation-style labels,
    # and duplicates by normalized name.
    seen_names = set()
    result = []
    for entry in painters.values():
        label = entry.pop("name", None)
        if not label:
            continue
        if "(" in label and ")" in label.split(",")[-1]:
            continue
        norm = re.sub(r"\s+", " ", label.strip().lower())
        if norm in seen_names:
            continue
        seen_names.add(norm)
        entry["name"] = label
        entry["countries"] = sorted({resolved[q] for q in
                                     entry.pop("country_qids")
                                     if q in resolved})
        entry["movements"] = sorted({resolved[q] for q in
                                     entry.pop("movement_qids")
                                     if q in resolved})
        result.append(entry)

    result.sort(key=lambda e: (-e["sitelinks"], e["name"]))
    print(f"      {len(result)} unique candidates")
    return result


def _resolve_labels(qids):
    labels = {}
    for start in range(0, len(qids), 50):
        batch = qids[start:start + 50]
        try:
            data = http_json(
                "https://www.wikidata.org/w/api.php",
                {"action": "wbgetentities", "ids": "|".join(batch),
                 "props": "labels", "languages": "en", "format": "json"},
                timeout=90)
        except RuntimeError as exc:
            print(f"      WARN label-resolve batch lost: "
                  f"{exc.__class__.__name__}")
            continue
        for qid, entity in data.get("entities", {}).items():
            label = entity.get("labels", {}).get("en", {}).get("value")
            if label:
                labels[qid] = label
        time.sleep(0.1)
    return labels


def candidate_categories(entry):
    cands = []
    if entry["p373"]:
        cands.append(entry["p373"].replace(" ", "_"))
    cands.append("Paintings_by_" + entry["name"].replace(" ", "_"))
    cands.append(entry["name"].replace(" ", "_"))
    seen, out = set(), []
    for cand in cands:
        if cand and cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _fetch_cat_page(cat, gcmtype):
    params = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtitle": "Category:" + cat,
        "gcmtype": gcmtype,
        "gcmlimit": 50,
        "format": "json",
    }
    if gcmtype == "file":
        params.update({"prop": "imageinfo", "iiprop": "url|dimensions",
                       "iiurlwidth": 800})
    data = http_json(COMMONS_API, params)
    return list((data.get("query", {}) or {}).get("pages", {}).values())


def _usable_file(page):
    info = page.get("imageinfo", [{}])[0]
    if not (info.get("thumburl") and info.get("width", 0) > 220
            and info.get("height", 0) > 160):
        return None
    title = re.sub(r"^File:", "", page.get("title", ""))
    title = re.sub(r"\.(jpg|jpeg|png|tif|tiff)$", "", title,
                   flags=re.I).replace("_", " ")
    return {"title": title[:80], "url": info["thumburl"]}


def collect_manifest(category, cache, budget):
    """Recursively gather paintings: direct files first, then subcategory
    files (depth <= 2). Mirrors production image rules. Cached."""
    key = "m:" + urllib.parse.quote(category, safe="")
    cached = cache.get(key)
    if cached is not None:
        return cached
    manifest = []
    seen = set()
    subcat_queue = []
    probed = 0
    queue = [(category, 0)]
    while queue and probed < budget["probes"] \
            and len(manifest) < MANIFEST_TARGET:
        cat, depth = queue.pop(0)
        try:
            pages = _fetch_cat_page(cat, "file")
            time.sleep(0.12)
            for page in pages:
                item = _usable_file(page)
                if item and page["title"] not in seen:
                    seen.add(page["title"])
                    manifest.append(item)
            if depth == 0:
                subs = _fetch_cat_page(cat, "subcat")
                time.sleep(0.12)
                probed += 1
                names = [p["title"].replace("Category:", "").replace(" ", "_")
                         for p in subs][:10]
                queue.extend((n, 1) for n in names)
        except RuntimeError:
            pass  # category vanished or transient error; keep partial
        probed += 1
        if len(manifest) >= MANIFEST_TARGET:
            break
    budget["probes"] -= probed
    manifest = manifest[:MANIFEST_TARGET]
    cache[key] = manifest
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh)
    return manifest


def validate_all(candidates, min_images, stop_after):
    print(f"[3/5] Validating Commons categories + building manifests "
          f"(need >= {min_images} usable images each) ...")
    cache = load_cache()
    validated = []
    checked = hits = 0
    total = len(candidates)
    try:
        for idx, entry in enumerate(candidates):
            budget = {"probes": MAX_SUBCAT_PROBES}
            best_cat, best_manifest = None, []
            for cat in candidate_categories(entry):
                manifest = collect_manifest(cat, cache, budget)
                checked += 1
                if len(manifest) > len(best_manifest):
                    best_cat, best_manifest = cat, manifest
                if len(best_manifest) >= MANIFEST_GOOD_ENOUGH:
                    break
                if budget["probes"] <= 0:
                    break
            if len(best_manifest) >= min_images:
                entry["category"] = best_cat
                entry["manifest"] = best_manifest
                validated.append(entry)
                hits += 1
                if len(validated) >= stop_after:
                    print(f"      early stop: reached {stop_after} "
                          f"validated (notability-ordered)")
                    break
            if (idx + 1) % 25 == 0:
                print(f"      {idx + 1}/{total} scanned, {hits} validated")
    except KeyboardInterrupt:
        print("\n      interrupted - keeping partial results")
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        raise SystemExit(1)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh)
    print(f"      done: {hits}/{total} validated "
          f"({checked} candidate categories probed)")
    return validated


def derive_tags(entry):
    tags = ["full"]
    for country in entry["countries"]:
        tag = COUNTRY_TAGS.get(country.strip().lower())
        if tag and tag not in tags:
            tags.append(tag)
    for movement in entry["movements"]:
        tag = MOVEMENT_TAGS.get(movement.strip().lower())
        if tag and tag not in tags:
            tags.append(tag)
    if entry["sitelinks"] >= POPULAR_SITELINKS:
        tags.append("popular")
    return tags


def emit(validated, limit):
    print("[4/5] Emitting JSON + painter folders ...")
    validated.sort(key=lambda e: (-e["sitelinks"], e["name"]))
    kept = validated[:limit]

    used_ids = set()
    records = []
    for entry in kept:
        pid = slugify(entry["name"])
        while pid in used_ids:
            pid = f"{pid}{entry['born']}"
        used_ids.add(pid)
        raw_nationality = entry["countries"][0] if entry["countries"] else ""
        demonym = COUNTRY_TAGS.get(raw_nationality.strip().lower())
        if demonym:
            nationality = " ".join(w.capitalize() for w in demonym.split())
        else:
            nationality = raw_nationality
        records.append({
            "id": pid,
            "name": entry["name"],
            "category": entry["category"],
            "tags": derive_tags(entry),
            "nationality": nationality,
            "born": entry["born"],
            "died": entry["died"],
            "era": entry["born"] // 100,
            "sitelinks": entry["sitelinks"],
            "img_count": len(entry.get("manifest", [])),
            "qid": entry["qid"],
        })
        folder = os.path.join(PAINTER_DIR, pid)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "manifest.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({
                "id": pid,
                "name": entry["name"],
                "category": entry["category"],
                "paintings": entry.get("manifest", []),
            }, fh, ensure_ascii=False, separators=(",", ":"))

    # Prune stale per-painter folders from previous runs.
    if os.path.isdir(PAINTER_DIR):
        for name in os.listdir(PAINTER_DIR):
            if name not in used_ids:
                shutil.rmtree(os.path.join(PAINTER_DIR, name),
                              ignore_errors=True)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "Wikidata (occupation painter) validated against "
                  "Wikimedia Commons category contents; painting manifests "
                  "in assets/painters/<id>/manifest.json",
        "count": len(records),
        "painters": records,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))

    tag_hist = {}
    popular = 0
    for rec in records:
        if "popular" in rec["tags"]:
            popular += 1
        for tag in rec["tags"]:
            if tag not in ("full",):
                tag_hist[tag] = tag_hist.get(tag, 0) + 1
    size_kb = os.path.getsize(OUT_PATH) // 1024
    print(f"      wrote {OUT_PATH}")
    print(f"      {len(records)} painters ({size_kb} KB), "
          f"{popular} tagged popular")
    print(f"      top tags: "
          f"{sorted(tag_hist.items(), key=lambda kv: -kv[1])[:14]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=MAX_PAINTERS,
                        help=f"max painters to emit (default {MAX_PAINTERS})")
    parser.add_argument("--min-images", type=int, default=MIN_IMAGES,
                        help="minimum usable images per Commons category")
    args = parser.parse_args()

    rows = run_sparql()
    candidates = build_candidates(rows)
    validated = validate_all(candidates, args.min_images,
                             stop_after=args.limit + 200)
    if not validated:
        print("ERROR: nothing validated; aborting without writing output.",
              file=sys.stderr)
        sys.exit(1)
    emit(validated, args.limit)


if __name__ == "__main__":
    main()
