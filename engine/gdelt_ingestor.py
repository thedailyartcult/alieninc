"""
Alien.Inc GDELT News Ingestion Pipeline
Pulls real-time global news from GDELT and maps events to company impacts.
Free, open API — no key required for basic access.
"""

import json
import os
import sys
import time
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db'))
from schema import get_connection, DB_PATH

log = logging.getLogger('ecosystem.gdelt')

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_ARTLIST_URL = "https://api.gdeltproject.org/api/v2/doc/artlist"

COMPANY_CONTEXT = {
    "rousseau": {
        "name": "Rousseau",
        "sector": "capital allocation, investment management, private equity, wealth management, financial services",
        "keywords": ["capital allocation", "private equity", "asset management", "wealth management",
                      "hedge fund", "investment", "portfolio", "capital markets", "alternative investment",
                      "family office", "holding company", "financial advisory"],
        "regions": ["Europe", "Monaco", "United Kingdom", "Switzerland", "Luxembourg"],
    },
    "tdac": {
        "name": "The Daily Art Cult",
        "sector": "digital media, publishing, cultural media, editorial, arts, independent publishing",
        "keywords": ["digital media", "publishing", "cultural media", "editorial", "art media",
                      "independent publishing", "cultural journalism", "arts journalism",
                      "philosophy", "creative writing", "membership media"],
        "regions": ["global"],
    },
    "panteon": {
        "name": "Panteon",
        "sector": "cybersecurity, cyber defense, managed detection, threat intelligence, vulnerability management",
        "keywords": ["cybersecurity", "cyber defense", "ransomware", "data breach", "vulnerability",
                      "threat intelligence", "managed detection", "SOC", "security operations",
                      "cyber attack", "malware", "phishing", "incident response", "zero-day"],
        "regions": ["global"],
    },
    "exosphere": {
        "name": "Exosphere",
        "sector": "acquisition advisory, succession planning, M&A, buy-side search, business transitions",
        "keywords": ["merger", "acquisition", "M&A", "succession planning", "buy-side",
                      "business acquisition", "deal flow", "due diligence", "business succession",
                      "lower middle market", "private equity deal"],
        "regions": ["North America", "Canada", "United States"],
    },
    "kmt": {
        "name": "KMT Consulting Group",
        "sector": "strategy consulting, AI consulting, management consulting, operational improvement, digital transformation",
        "keywords": ["management consulting", "strategy consulting", "AI transformation",
                      "operational improvement", "digital transformation", "AI consulting",
                      "business strategy", "process optimization", "enterprise AI", "agentic AI"],
        "regions": ["global"],
    },
    "alcantara": {
        "name": "Alcantara Art Foundation",
        "sector": "cultural preservation, art conservation, nonprofit, heritage, museum, digitization",
        "keywords": ["cultural preservation", "art conservation", "heritage", "museum",
                      "digitization", "cultural heritage", "endangered culture", "preservation",
                      "nonprofit arts", "cultural foundation", "archive", "conservation"],
        "regions": ["global"],
    },
    "statute": {
        "name": "Statute & Precedent",
        "sector": "legal services, compliance, governance, AI policy, regulatory, contract law",
        "keywords": ["legal services", "compliance", "governance", "AI regulation", "AI policy",
                      "regulatory", "contract law", "legal tech", "data protection",
                      "GDPR", "AI Act", "corporate governance", "M&A legal"],
        "regions": ["United Kingdom", "Europe", "global"],
    },
    "immanuel": {
        "name": "Immanuel",
        "sector": "crisis management, security, risk management, medical evacuation, travel security, intelligence",
        "keywords": ["crisis management", "security risk", "travel security", "medical evacuation",
                      "risk management", "geopolitical risk", "kidnapping", "hostage",
                      "security threat", "political risk", "emergency response",
                      "critical event", "executive protection", "duty of care"],
        "regions": ["global"],
    },
}

MACRO_EVENTS = [
    {
        "pattern": ["market crash", "stock crash", "financial crisis", "recession", "bear market",
                     "market collapse", "systemic risk", "banking crisis", "liquidity crisis"],
        "affected": ["rousseau", "kmt"],
        "severity": "critical",
        "event_type": "financial",
        "description_template": "Global financial market disruption detected — capital allocation and consulting demand impacted",
    },
    {
        "pattern": ["cyber attack", "ransomware", "data breach", "cybersecurity breach",
                     "major hack", "infrastructure cyber", "zero-day exploit", "supply chain attack"],
        "affected": ["panteon", "immanuel"],
        "severity": "high",
        "event_type": "cybersecurity",
        "description_template": "Major cybersecurity incident — Panteon demand surge, Immanuel crisis response activation",
    },
    {
        "pattern": ["war", "military conflict", "geopolitical crisis", "invasion",
                     "armed conflict", "terrorism", "coup", "sanctions", "trade war"],
        "affected": ["immanuel", "kmt"],
        "severity": "critical",
        "event_type": "geopolitical",
        "description_template": "Geopolitical crisis — Immanuel crisis management demand surge, KMT geopolitical advisory activation",
    },
    {
        "pattern": ["regulation", "new law", "compliance mandate", "regulatory change",
                     "AI regulation", "AI Act", "data protection law", "GDPR enforcement",
                     "antitrust", "monopoly investigation"],
        "affected": ["statute", "kmt"],
        "severity": "medium",
        "event_type": "regulatory",
        "description_template": "Regulatory change detected — Statute & Precedent compliance workload increase",
    },
    {
        "pattern": ["acquisition", "merger", "M&A deal", "takeover", "buyout",
                     "private equity acquisition", "strategic acquisition", "IPO"],
        "affected": ["exosphere", "rousseau"],
        "severity": "medium",
        "event_type": "market",
        "description_template": "M&A activity surge — Exosphere deal pipeline opportunity, Rousseau capital allocation review",
    },
    {
        "pattern": ["heritage", "cultural preservation", "museum funding", "endangered site",
                     "art conservation", "cultural heritage", "UNESCO", "archaeological discovery"],
        "affected": ["alcantara", "tdac"],
        "severity": "low",
        "event_type": "operational",
        "description_template": "Cultural preservation event — Alcantara Art Foundation engagement opportunity",
    },
    {
        "pattern": ["currency", "euro", "exchange rate", "forex", "dollar", "interest rate",
                     "central bank", "inflation", "deflation"],
        "affected": ["rousseau"],
        "severity": "low",
        "event_type": "financial",
        "description_template": "Currency/interest rate movement — Rousseau fund centre NAV impact",
    },
    {
        "pattern": ["AI breakthrough", "artificial intelligence", "generative AI", "AGI",
                     "AI safety", "AI governance", "AI regulation", "machine learning",
                     "deepfake", "AI misalignment"],
        "affected": ["kmt", "statute", "panteon"],
        "severity": "medium",
        "event_type": "operational",
        "description_template": "AI industry development — KMT advisory demand, Statute governance workload, Panteon AI security review",
    },
    {
        "pattern": ["pandemic", "epidemic", "outbreak", "virus", "health crisis",
                     "biological threat", "public health emergency"],
        "affected": ["immanuel", "panteon", "kmt"],
        "severity": "critical",
        "event_type": "pandemic",
        "description_template": "Health crisis detected — Immanuel medical response, Panteon biosecurity review, KMT operational continuity advisory",
    },
    {
        "pattern": ["earthquake", "hurricane", "typhoon", "flood", "wildfire", "tsunami",
                     "natural disaster", "extreme weather", "climate event"],
        "affected": ["immanuel", "alcantara"],
        "severity": "high",
        "event_type": "natural_disaster",
        "description_template": "Natural disaster — Immanuel emergency response activation, Alcantara heritage risk assessment",
    },
    {
        "pattern": ["supply chain", "logistics disruption", "shipping", "port closure",
                     "semiconductor shortage", "chip shortage", "manufacturing disruption"],
        "affected": ["kmt", "rousseau"],
        "severity": "high",
        "event_type": "operational",
        "description_template": "Supply chain disruption — KMT operational advisory, Rousseau portfolio risk review",
    },
    {
        "pattern": ["scandal", "fraud", "corruption", "embezzlement", "accounting fraud",
                     "executive misconduct", "governance failure"],
        "affected": ["statute", "kmt", "rousseau"],
        "severity": "high",
        "event_type": "reputational",
        "description_template": "Corporate governance scandal — Statute legal response, KMT governance advisory, Rousseau portfolio review",
    },
]


def _fetch_gdelt(query, timespan="1h", max_records=60, delay=6):
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "timespan": timespan,
        "sort": "date_desc",
    }
    url = f"{GDELT_DOC_URL}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'AlienInc-Ecosystem/1.0 (operating-system; contact: security@alieninc.tech)',
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('articles', [])
    except urllib.error.HTTPError as e:
        if e.code == 429:
            log.warning("GDELT rate limited — backing off %ds", delay)
            time.sleep(delay)
            return []
        log.warning("GDELT fetch failed for query '%s': %s", query[:50], e)
        return []
    except Exception as e:
        log.warning("GDELT fetch failed for query '%s': %s", query[:50], e)
        return []


def _score_relevance(article, company_id):
    ctx = COMPANY_CONTEXT.get(company_id, {})
    if not ctx:
        return 0

    title = (article.get('title') or '').lower()
    body_text = (article.get('body') or article.get('snippet') or '').lower()
    combined = title + ' ' + body_text

    score = 0
    for kw in ctx.get('keywords', []):
        if kw.lower() in title:
            score += 3
        elif kw.lower() in combined:
            score += 1

    for region in ctx.get('regions', []):
        if region.lower() in combined:
            score += 1

    if ctx['name'].lower() in combined:
        score += 10

    return score


def _detect_macro_events(articles):
    events = []
    combined_text = ' '.join(
        ((a.get('title') or '') + ' ' + (a.get('body') or a.get('snippet') or '')).lower()
        for a in articles
    )

    for macro in MACRO_EVENTS:
        for pattern in macro["pattern"]:
            if pattern.lower() in combined_text:
                events.append({
                    "event_type": "macro_event",
                    "title": macro["description_template"],
                    "description": f"GDELT-detected pattern: '{pattern}' found in recent news coverage",
                    "affected_company_ids": json.dumps(macro["affected"]),
                    "impact_severity": macro["severity"],
                    "trigger_pattern": pattern,
                    "source_articles": len(articles),
                })
                break

    return events


def _classify_sentiment(article):
    tone = article.get('tone')
    if tone is not None:
        try:
            tone_val = float(tone)
            if tone_val > 4:
                return "positive"
            elif tone_val < -4:
                return "negative"
        except (ValueError, TypeError):
            pass
    return "neutral"


def ingest_once(db_path=None):
    db = db_path or DB_PATH
    conn = get_connection(db)
    now = datetime.now(timezone.utc)
    ingested = 0

    for company_id, ctx in COMPANY_CONTEXT.items():
        query = " OR ".join(ctx["keywords"][:5])
        articles = _fetch_gdelt(query, timespan="6h", max_records=30)
        time.sleep(2)

        if not articles:
            continue

        for article in articles:
            relevance = _score_relevance(article, company_id)
            if relevance < 2:
                continue

            existing = conn.execute(
                "SELECT id FROM events WHERE url = ? AND source = 'gdelt'",
                (article.get('url'),)
            ).fetchone()

            if existing:
                continue

            sentiment = _classify_sentiment(article)
            severity = "medium" if relevance >= 5 else "low"
            if sentiment == "negative":
                severity = "high" if relevance >= 5 else "medium"

            conn.execute("""
                INSERT INTO events
                (event_type, source, title, description, affected_company_ids,
                 impact_severity, financial_impact, url, published_date,
                 ingested_at, processed)
                VALUES (?, 'gdelt', ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                "news",
                article.get('title', ''),
                article.get('body') or article.get('snippet') or '',
                json.dumps([company_id]),
                severity,
                0,
                article.get('url'),
                article.get('date', now.isoformat())[:10],
                now.isoformat(),
            ))
            ingested += 1

    all_articles = _fetch_gdelt(
        "financial crisis OR cyber attack OR geopolitical OR regulation OR AI breakthrough OR merger acquisition",
        timespan="6h",
        max_records=60,
    )
    if all_articles:
        macro_events = _detect_macro_events(all_articles)
        for ev in macro_events:
            existing = conn.execute(
                "SELECT id FROM events WHERE title = ? AND source = 'gdelt' AND published_date = ?",
                (ev["title"], now.isoformat()[:10])
            ).fetchone()
            if not existing:
                conn.execute("""
                    INSERT INTO events
                    (event_type, source, title, description, affected_company_ids,
                     impact_severity, financial_impact, published_date, ingested_at, processed)
                    VALUES (?, 'gdelt', ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    ev["event_type"],
                    ev["title"],
                    ev["description"],
                    ev["affected_company_ids"],
                    ev["impact_severity"],
                    0,
                    now.isoformat()[:10],
                    now.isoformat(),
                ))
                ingested += 1

    conn.commit()
    conn.close()

    log.info("GDELT ingestion complete: %d new events stored", ingested)
    return ingested


def process_pending_events(db_path=None):
    db = db_path or DB_PATH
    conn = get_connection(db)

    pending = conn.execute(
        "SELECT * FROM events WHERE processed = 0 ORDER BY ingested_at ASC"
    ).fetchall()

    processed = 0
    for event in pending:
        if event["source"] == "gdelt":
            _apply_event_impact(conn, event)
            conn.execute(
                "UPDATE events SET processed = 1, processed_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), event["id"])
            )
            processed += 1

    conn.commit()
    conn.close()

    log.info("Processed %d pending events", processed)
    return processed


def _apply_event_impact(conn, event):
    affected_ids = json.loads(event["affected_company_ids"] or "[]")
    severity = event["impact_severity"] or "low"

    severity_multiplier = {
        "low": 1.01,
        "medium": 1.03,
        "high": 1.08,
        "critical": 1.15,
    }.get(severity, 1.0)

    if event["event_type"] == "news" and event["impact_severity"] in ("high", "critical"):
        severity_multiplier = 0.97

    for cid in affected_ids:
        company = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (cid,)
        ).fetchone()
        if not company:
            continue

        new_health = company["current_health"] or 100
        if event["impact_severity"] in ("high", "critical"):
            new_health -= {"high": 3, "critical": 8}.get(event["impact_severity"], 1)
        elif event["impact_severity"] == "low":
            new_health += 0.5

        new_health = max(0, min(100, new_health))

        conn.execute(
            "UPDATE companies SET current_health = ?, updated_at = ? WHERE id = ?",
            (new_health, datetime.now(timezone.utc).isoformat(), cid)
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    print("Running GDELT ingestion...")
    count = ingest_once()
    print(f"Ingested {count} new events")
    print("Processing pending events...")
    processed = process_pending_events()
    print(f"Processed {processed} events")
