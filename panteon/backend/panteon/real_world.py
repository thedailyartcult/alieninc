"""
Real-world anchoring for the War Ontology — pulls OFFICIAL statistics so the
digital twin carries actual quantities, not just percentages:

  world_country objects: population, armed forces personnel, military
  expenditure (World Bank API, key-less) + capital coordinates (REST Countries).

  Parties mapping links nations to the canonical Kriegspiel theaters so sims
  can translate percentage casualties into ABSOLUTE soldier estimates.
"""
import asyncio
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panteon.core.auth import SupabaseUser  # noqa: F401  (type re-export convenience)
from panteon.war_ontology import ensure_war_ontology

WORLD_BANK_BASE = "https://api.worldbank.org/v2"

IND_POPULATION = "SP.POP.TOTL"
IND_TROOPS = "MS.MIL.TOTL.P1"             # Armed forces personnel, total (IISS)
IND_MILSPEND = "MS.MIL.XPND.CD"           # Military expenditure (current US$)

WB_LOOKBACK_YEARS = 18                    # IISS troop data can lag several years
HTTP_TIMEOUT = httpx.Timeout(20.0, connect=8.0)

# Canonical theaters -> party countries (ISO3, ordered: first=red, second=blue).
# Editorial but factual about who the belligerent parties ARE in each theater.
THEATER_PARTIES = {
    "South China Sea": ["CHN", "VNM", "TW", "PHL", "MYS", "BRN", "USA"],
    "Taiwan Strait":   ["CHN", "TW", "USA", "JPN"],
    "Eastern Europe":  ["RUS", "UKR", "BLR", "POL", "ROU", "MDA", "EST", "LVA", "LTU"],
    "Levant":          ["ISR", "SYR", "LBN", "IRN", "JOR", "IRQ"],
    "Korean Peninsula": ["PRK", "KOR", "USA", "JPN", "CHN"],
    "Persian Gulf":    ["IRN", "SAU", "IRQ", "ARE", "QAT", "KWT", "BHR", "OMN", "USA"],
    "Sahel":           ["MLI", "BFA", "NER", "TCD", "MRT", "FRA"],
    "Andes":           ["PER", "BOL", "ECU", "COL", "VEN", "CHL"],
}

ALL_PARTIES = sorted({c for cs in THEATER_PARTIES.values() for c in cs})

# Curated offline geography for every party nation (capital coords) so object
# placement never depends on a third-party geo API that can rot or rate-limit.
# `fallback_*` values fill economies absent from World Bank (e.g. TWN); they are
# clearly labeled with source="curated_fallback" when used.
COUNTRY_GEO = {
    "CHN": ("China", [39.9042, 116.4074]),
    "TW":  ("Taiwan", [25.0330, 121.5654], {"population": 23400000,
                                            "armed_forces_personnel": 169000}),
    "USA": ("United States", [38.8951, -77.0364]),
    "JPN": ("Japan", [35.6762, 139.6503]),
    "RUS": ("Russia", [55.7558, 37.6173]),
    "UKR": ("Ukraine", [50.4501, 30.5234]),
    "BLR": ("Belarus", [53.9006, 27.5590]),
    "POL": ("Poland", [52.2297, 21.0122]),
    "ROU": ("Romania", [44.4268, 26.1025]),
    "MDA": ("Moldova", [47.0105, 28.8638]),
    "EST": ("Estonia", [59.4370, 24.7536]),
    "LVA": ("Latvia", [56.9496, 24.1052]),
    "LTU": ("Lithuania", [54.6872, 25.2797]),
    "ISR": ("Israel", [31.7683, 35.2137]),
    "SYR": ("Syria", [33.5138, 36.2765]),
    "LBN": ("Lebanon", [33.8938, 35.5018]),
    "IRN": ("Iran", [35.6892, 51.3890]),
    "JOR": ("Jordan", [31.9454, 35.9284]),
    "IRQ": ("Iraq", [33.3152, 44.3661]),
    "PRK": ("North Korea", [39.0392, 125.7625]),
    "KOR": ("South Korea", [37.5665, 126.9780]),
    "SAU": ("Saudi Arabia", [24.7136, 46.6753]),
    "ARE": ("UAE", [24.4539, 54.3773]),
    "QAT": ("Qatar", [25.2854, 51.5310]),
    "KWT": ("Kuwait", [29.3759, 47.9774]),
    "BHR": ("Bahrain", [26.2285, 50.5860]),
    "OMN": ("Oman", [23.5880, 58.3829]),
    "MLI": ("Mali", [12.6392, -8.0029]),
    "BFA": ("Burkina Faso", [12.3714, -1.5197]),
    "NER": ("Niger", [13.5127, 2.1128]),
    "TCD": ("Chad", [12.1348, 15.0557]),
    "MRT": ("Mauritania", [18.0735, -15.9582]),
    "FRA": ("France", [48.8566, 2.3522]),
    "PER": ("Peru", [-12.0464, -77.0428]),
    "BOL": ("Bolivia", [-16.4897, -68.1193]),
    "ECU": ("Ecuador", [-0.1807, -78.4678]),
    "COL": ("Colombia", [4.7110, -74.0721]),
    "VEN": ("Venezuela", [10.4806, -66.9036]),
    "CHL": ("Chile", [-33.4489, -70.6693]),
    "VNM": ("Vietnam", [21.0278, 105.8342]),
    "PHL": ("Philippines", [14.5995, 120.9842]),
    "MYS": ("Malaysia", [3.1390, 101.6869]),
    "BRN": ("Brunei", [4.9031, 114.9398]),
}

# World Bank lacks a few economies (e.g. TWN) — COUNTRY_GEO fallbacks fill in.
_WB_MISSING_FALLBACK = {"TW"}


async def _wb_indicator(client: httpx.AsyncClient, iso3: str, indicator: str):
    """Most recent non-empty World Bank value -> (value, year) | (None, None)."""
    url = (f"{WORLD_BANK_BASE}/country/{iso3}/indicator/{indicator}")
    try:
        resp = await client.get(url, params={
            "format": "json", "per_page": WB_LOOKBACK_YEARS,
            "date": f"{datetime.now(timezone.utc).year - WB_LOOKBACK_YEARS}:"
                    f"{datetime.now(timezone.utc).year}",
        })
        if resp.status_code != 200:
            return None, None
        payload = resp.json()
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        for row in rows:
            if row.get("value") is not None:
                return float(row["value"]), int(row["date"])
    except (httpx.HTTPError, ValueError, IndexError, TypeError):
        pass
    return None, None


async def fetch_real_country(client: httpx.AsyncClient, iso: str) -> dict:
    """Assemble one nation's REAL dossier: World Bank live + curated fallbacks."""
    geo = COUNTRY_GEO.get(iso)
    name = geo[0] if geo else None
    latlng = (geo[1] if geo and len(geo) > 1 else [None, None]) or [None, None]
    fallback = ((geo[2] if len(geo) > 2 else {}) if geo else {}) or {}

    pop, pop_y = await _wb_indicator(client, iso, IND_POPULATION)
    troops, troops_y = await _wb_indicator(client, iso, IND_TROOPS)
    spend, spend_y = await _wb_indicator(client, iso, IND_MILSPEND)

    sources = ["world_bank"]
    if pop is None and fallback.get("population") is not None:
        pop, pop_y = fallback["population"], None
        sources = ["curated_fallback"]
    if troops is None and fallback.get("armed_forces_personnel") is not None:
        troops, troops_y = fallback["armed_forces_personnel"], None
        if "curated_fallback" not in sources:
            sources.append("curated_fallback")

    props = {
        "iso3": iso,
        "name": name or iso,
        "lat": round(float(latlng[0]), 5), "lng": round(float(latlng[1]), 5),
        "population": pop, "population_year": pop_y,
        "armed_forces_personnel": troops, "troops_year": troops_y,
        "military_expenditure_usd": spend, "milspend_year": spend_y,
        "source": "+".join(sources),
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return {k: v for k, v in props.items() if v is not None}


async def ingest_real_countries(db, isos=None) -> dict:
    """
    Pull official stats for the given ISO3 list (default: every theater party),
    upsert world_country ontology objects at capital coordinates, and link
    each nation to its theaters via parties_to.
    """
    from panteon.spinal_craker.models import LinkType, Object, ObjectType
    from panteon.war_ontology import (
        THEATER_TYPE, WORLD_COUNTRY_TYPE, _slug, _upsert_war_object, _ensure_link,
        ensure_war_ontology,
    )

    await ensure_war_ontology(db)
    isos = [i.upper() for i in (isos or ALL_PARTIES)]

    # Ensure every canonical theater EXISTS as an object (real-world skeleton),
    # enriched from the sims gateway when it is reachable.
    ttype_id = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(6.0)) as client:
            bf_resp = await client.get("http://localhost:8090/api/kriegspiel/battlefields")
            battlefields = {b["name"]: b for b in bf_resp.json()} if bf_resp.status_code == 200 else {}
    except Exception:
        battlefields = {}
    ttype_row = (await db.execute(
        select(ObjectType.id).where(ObjectType.name == THEATER_TYPE))).scalar_one_or_none()
    if ttype_row is not None:
        ttype_id = ttype_row
        from panteon.war_ontology import AT_RUN_BATTLE  # noqa: F401
        for t_name in THEATER_PARTIES:
            b = battlefields.get(t_name) or {}
            props = {"name": t_name}
            if b.get("terrain"):
                props["terrain"] = b["terrain"]
            if b.get("center"):
                props["lat"], props["lng"] = b["center"][0], b["center"][1]
            if b.get("bounds"):
                props["bounds"] = list(b["bounds"])
            if b.get("area_km2"):
                props["area_km2"] = b["area_km2"]
            prev = (await db.execute(
                select(Object).where(Object.primary_key_value == f"ks-theater:{_slug(t_name)}")
            )).scalar_one_or_none()
            base_props = dict(props)
            if prev is not None:
                base_props.update({k: v for k, v in (prev.properties or {}).items()
                                   if k in ("assessments", "last_assessed_at")})
            await _upsert_war_object(db, ttype_id, f"ks-theater:{_slug(t_name)}", base_props)

    results, errors = [], []
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        sem = asyncio.Semaphore(5)

        async def one(iso):
            async with sem:
                return iso, await fetch_real_country(client, iso)

        dossiers = await asyncio.gather(*(one(i) for i in isos))

    ctype_id = (
        await db.execute(select(ObjectType.id).where(ObjectType.name == WORLD_COUNTRY_TYPE))
    ).scalar_one()
    lt_row = (await db.execute(select(LinkType).where(LinkType.name == "ks_parties_to"))).scalar_one_or_none()

    theater_ids = {}
    for t_name in set(THEATER_PARTIES):
        pk = f"ks-theater:{_slug(t_name)}"
        row = (await db.execute(
            select(Object.id).where(Object.primary_key_value == pk))).scalar_one_or_none()
        if row is not None:
            theater_ids[t_name] = row

    for iso, props in dossiers:
        if not props.get("population") and not props.get("armed_forces_personnel"):
            errors.append({"iso3": iso, "error": "no official values returned"})
            continue
        obj, created = await _upsert_war_object(
            db, ctype_id, f"ks-country:{iso.lower()}", props)
        entry = {
            "iso3": iso, "name": props.get("name"), "object_id": str(obj.id),
            "created": created, "population": props.get("population"),
            "armed_forces_personnel": props.get("armed_forces_personnel"),
            "theaters_linked": 0,
        }
        if lt_row is not None:
            for t_name, party_list in THEATER_PARTIES.items():
                if iso in party_list and t_name in theater_ids:
                    if await _ensure_link(db, lt_row.id, obj.id, theater_ids[t_name],
                                          {"role": "party"}):
                        entry["theaters_linked"] += 1
        results.append(entry)

    return {
        "ingested": len(results), "errors": errors,
        "source": "world_bank+restcountries",
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "countries": sorted(results, key=lambda r: -(r.get("armed_forces_personnel") or 0)),
    }


def real_baselines_for_theater(theater_name: str) -> dict:
    """red/blue troop baselines from the curated parties map (first=red)."""
    parties = THEATER_PARTIES.get(theater_name) or []
    out = {"parties": parties}
    if len(parties) >= 2:
        out["red_iso"] = parties[0]
        out["blue_iso"] = parties[1]
    return out


async def resolve_baselines(db, theater_name: str) -> dict:
    """
    Real troop baselines for a theater from INGESTED world_country objects.
    Convention: first curated party = red, second = blue.
    """
    from panteon.spinal_craker.models import Object
    parties = (THEATER_PARTIES.get(theater_name) or [])[:2]
    out = {"parties": THEATER_PARTIES.get(theater_name) or []}
    for side, iso in zip(("red", "blue"), parties):
        obj = (await db.execute(
            select(Object).where(Object.primary_key_value == f"ks-country:{iso.lower()}")
        )).scalar_one_or_none()
        if obj is not None and (obj.properties or {}).get("armed_forces_personnel"):
            out[f"{side}_iso"] = iso
            out[f"{side}_personnel"] = float(obj.properties["armed_forces_personnel"])
            out[f"{side}_name"] = (obj.properties or {}).get("name")
    return out


DEFAULT_COMMITMENT_FRACTION = 0.10


def estimate_absolute_casualties(report: dict, baselines: dict,
                                 commitment: float = DEFAULT_COMMITMENT_FRACTION) -> dict | None:
    """
    Translate synthetic casualty percentages into ABSOLUTE soldier estimates
    using real armed-forces personnel of the theater's primary parties.
    Clearly labeled estimates — never presented as ground truth.
    """
    red_troops = baselines.get("red_personnel")
    blue_troops = baselines.get("blue_personnel")
    out = {}
    for side, troops in (("red", red_troops), ("blue", blue_troops)):
        pct = report.get(f"avg_{side}_casualties")
        if pct is not None and troops:
            out[f"est_{side}_casualties_soldiers"] = int(round(
                float(pct) / 100.0 * float(troops) * commitment))
    out["commitment_fraction"] = commitment
    return out if len(out) > 1 else None
