#!/usr/bin/env python3
"""Fetch, crop, and apply verified founder photos for Labyu.

Downloads verified founder portrait photos from reputable public sources
(Wikimedia Commons, Tatler Asia, university spotlights, official press kits,
and local repo assets), crops them to clean square 400x400 headshots,
saves to labyu/p/<slug>.jpg, updates labyu/founders.json, and rebuilds labyu/.

Usage:
  python3 tools/fetch-founder-photos.py
"""
import io
import json
import pathlib
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from PIL import Image, ImageOps

ROOT = pathlib.Path(__file__).resolve().parents[1]
LABYU = ROOT / "labyu"
P_DIR = LABYU / "p"
FOUNDERS_JSON = LABYU / "founders.json"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LabyuDirectory/1.0 (https://alieninc.tech/labyu)"}

# Curated verified sources
VERIFIED_SOURCES = {
    "patrick-neil-alcantara": "local:founder.jpeg",
    "francis-plaza": "https://cdn.tatlerasia.com/generationt/i/ap/2021/08/30155513-francis-1-1_cover_2000x2000.png",
    "brian-cu": "https://alter.vc/uploads/entrepreneurs/cover-photos/_galleryPhoto/7978/Sarisuki-Brian-Cu.jpg",
    "rexy-dorado": "https://cdn.tatlerasia.com/generationt/i/ap/2021/08/30170914-batch-final-image-rexy-dorado_cover_1280x1920.jpg",
    "nix-nolledo": "https://cdn.tatlerasia.com/generationt/i/ap/2019/09/04133737-screen-shot-2019-09-04-at-13717-pm_cover_539x545.png",
    "king-alandy-dy": "https://cdn.tatlerasia.com/generationt/i/ap/2021/09/07150946-batch-king-portrait-02_cover_1280x1920.jpg",
    "luis-buenaventura": "https://cdn.tatlerasia.com/generationt/i/ap/2019/09/03172536-luis-buenaventura_cover_2000x1333.jpg",
    "carmina-bayombong": "https://cdn.tatlerasia.com/generationt/i/ap/2020/10/13231519-carmina-bayombong-edited_cover_1333x2000.jpg",
    "anna-meloto-wilk": "https://cdn.tatlerasia.com/generationt/i/ap/2019/09/05155030-anna-meloto-wilk_cover_300x430.jpg",
    "dan-matutina": "https://cdn.tatlerasia.com/generationt/i/ap/2020/10/13232408-batch-dan-matutina-photo-by-charles-buenconsejo-edited_cover_1280x1920.jpg",
    "kimberly-yao": "https://cdn.tatlerasia.com/generationt/i/ap/2021/03/04155347-kimberly-yao_cover_1333x2000.jpg",
    "chow-paredes": "https://cdn.tatlerasia.com/generationt/i/ap/2019/09/04103455-chow-paredes-credit-security-bank_cover_2000x1335.jpg",
    "maynard-ngu": "https://cdn.tatlerasia.com/generationt/i/ap/2019/09/03172811-maynard-ngu_cover_2000x1333.jpg",
    "paolo-bugayong": "https://cdn.tatlerasia.com/generationt/i/ap/2019/06/19152807-paolo-bugayong-2-photo_cover_1333x2000.png",
    "roland-ros": "https://www.alumni.ucsb.edu/sites/default/files/images/spotlights/2022-12/roland-ros-headshot.jpeg",
    "maria-ressa": "wiki:File:Maria Ressa in 2022 (cropped).jpg",
    "anne-curtis": "wiki:File:Anne Curtis, 2009 (cropped).jpg",
    "dado-banatao": "wiki:File:Dado Banatao 2021 stamp of Philippines.jpg",
    "vice-ganda": "wiki:File:Vice Ganda in Tarlac.jpg",
    "sheila-lirio-marcelo": "wiki:File:Sheila Lirio Marcelo headshot-2013.jpg",
    "georgina-wilson": "wiki:File:Georgina Wilson.jpg",
    "alodia-gosiengfiao": "wiki:File:Alodia Gosiengfiao, 2012 (cropped).jpg",
    "edwin-lacierda": "wiki:File:Edwin Lacierda (crop).jpg",
    "dennis-anthony-uy": "wiki:File:Dennis Anthony Uy 2023 (cropped).jpg",
    "winston-damarillo": "wiki:File:Photo of Winston Damarillo.jpg",
}


def crop_to_square(im, slug):
    w, h = im.size
    if slug == "brian-cu":
        return im.crop((560, 20, 1020, 480))
    if slug == "francis-plaza":
        box = int(h * 0.7)
        left = (w - box) // 2
        return im.crop((left, 0, left + box, box))

    if h > w:
        size = w
        top = 0
        return im.crop((0, top, size, top + size))
    elif w > h:
        size = h
        left = (w - size) // 2
        return im.crop((left, 0, left + size, size))
    return im


def process_and_save(data_or_path, slug):
    P_DIR.mkdir(parents=True, exist_ok=True)
    out_path = P_DIR / f"{slug}.jpg"
    try:
        if isinstance(data_or_path, (bytes, bytearray)):
            im = Image.open(io.BytesIO(data_or_path))
        else:
            im = Image.open(data_or_path)
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        im = crop_to_square(im, slug)
        im = im.resize((400, 400), Image.Resampling.LANCZOS)
        im.save(out_path, "JPEG", quality=85)
        print(f"  [OK] Saved {out_path.name}")
        return True
    except Exception as e:
        print(f"  [FAIL] {slug}: {e}")
        return False


def resolve_wiki_file(title):
    api = f"https://commons.wikimedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}&prop=imageinfo&iiprop=url&iiurlwidth=600&format=json"
    req = urllib.request.Request(api, headers=UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        doc = json.loads(r.read())
        pages = doc.get("query", {}).get("pages", {})
        for pid, p in pages.items():
            info = p.get("imageinfo", [{}])[0]
            return info.get("thumburl") or info.get("url")
    return None


def fetch_all():
    founders = json.loads(FOUNDERS_JSON.read_text(encoding="utf-8"))
    f_by_slug = {f["slug"]: f for f in founders}

    count = 0
    for slug, src in VERIFIED_SOURCES.items():
        if slug not in f_by_slug:
            continue
        out_file = P_DIR / f"{slug}.jpg"
        if out_file.exists():
            count += 1
            continue

        print(f"Processing {slug} from {src[:50]}...")
        if src.startswith("local:"):
            rel = src.split(":", 1)[1]
            local_path = ROOT / rel
            if local_path.exists() and process_and_save(local_path, slug):
                count += 1
        elif src.startswith("wiki:"):
            wiki_title = src.split("wiki:", 1)[1]
            try:
                img_url = resolve_wiki_file(wiki_title)
                if img_url:
                    req = urllib.request.Request(img_url, headers=UA)
                    with urllib.request.urlopen(req, timeout=15) as r:
                        data = r.read()
                    if process_and_save(data, slug):
                        count += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"  [ERR] {slug}: {e}")
        else:
            try:
                req = urllib.request.Request(src, headers=UA)
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = r.read()
                if process_and_save(data, slug):
                    count += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"  [ERR] {slug}: {e}")

    # Wire into founders.json
    updated = 0
    for f in founders:
        slug = f["slug"]
        p_file = P_DIR / f"{slug}.jpg"
        if p_file.exists():
            f["photo"] = f"p/{slug}.jpg"
            updated += 1

    FOUNDERS_JSON.write_text(json.dumps(founders, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nUpdated {updated} founders with photos in labyu/founders.json")

    # Run build-founders.py
    print("Rebuilding labyu/ directory...")
    subprocess.run([sys.executable, str(ROOT / "tools" / "build-founders.py")], check=True)
    print("Done!")


if __name__ == "__main__":
    fetch_all()
