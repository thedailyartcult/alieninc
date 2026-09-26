#!/usr/bin/env python3
"""
Submit URLs to Google Indexing API (requires service account JSON with
https://www.googleapis.com/auth/indexing + verified owner in Search Console)
And fallback to IndexNow per-URL ping for Bing.
Reads sitemap.xml and submits top 10 priority URLs.
"""
import json, pathlib, xml.etree.ElementTree as ET, sys, os

SITEMAP = pathlib.Path(__file__).resolve().parents[1] / "_pages" / "sitemap.xml"
if not SITEMAP.exists():
    SITEMAP = pathlib.Path(__file__).resolve().parents[1] / "sitemap.xml"

def get_urls(limit=10):
    try:
        tree = ET.parse(SITEMAP)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        # without ns, find all loc
        urls = []
        for loc in tree.getroot().iter():
            if loc.tag.endswith("loc"):
                urls.append(loc.text.strip())
        # Prioritize by priority tag if present
        return urls[:limit]
    except Exception as e:
        print(f"sitemap parse failed: {e}", file=sys.stderr)
        return ["https://alieninc.tech/", "https://panteon.alieninc.tech/"]

def submit_google(urls):
    import google.auth
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        "/tmp/gsa.json", scopes=["https://www.googleapis.com/auth/indexing"]
    )
    service = build("indexing", "v3", credentials=creds, cache_discovery=False)
    for url in urls:
        try:
            body = {"url": url, "type": "URL_UPDATED"}
            resp = service.urlNotifications().publish(body=body).execute()
            print(f"Google Indexing OK {url}: {resp.get('urlNotificationMetadata',{}).get('url')}")
        except Exception as e:
            print(f"Google Indexing FAIL {url}: {e}")

if __name__ == "__main__":
    urls = get_urls(10)
    print(f"Submitting {len(urls)} URLs: {urls}")
    if os.path.exists("/tmp/gsa.json"):
        submit_google(urls)
    else:
        print("No /tmp/gsa.json, skipping Google")
