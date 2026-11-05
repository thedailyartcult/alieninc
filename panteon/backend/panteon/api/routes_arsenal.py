"""
Arsenal Store API — structured queries over the ars_* tables in panteon.db
(the versioned import of a-san's catalog). READ-ONLY, authenticated.

IMPORTANT: this is catalog REFERENCE data, not a source of truth for live
operations. Real-time positions/contacts come from the live connectors
(/opensky, /gkg, ...); every response here carries meta identifying the
snapshot it came from.
"""
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from panteon.core.auth import SupabaseUser, get_current_user
from panteon.core.database import get_db
from panteon.arsenal_store import ArsCategory, ArsItem, ArsSnapshot
from panteon import arsenal as arsenal_mod

router = APIRouter(prefix="/arsenal", tags=["Arsenal Store"])

# Category icon PNGs ported from the a-san catalog design (served read-only).
# panteon/api/routes_arsenal.py -> parents[3] == panteon repo root
ICON_DIR = str(Path(__file__).resolve().parents[3] / "assets" / "arsenal-icons")
ALLOWED_ICONS = {
    "aircraft.png", "air-launched-weapons.png",
    "armored-vehicles-and-equipment.png", "automotive-vehicles.png",
    "electronic-warfare-systems.png", "missile-and-rocket-weapons.png",
    "sea-launched-cruise-missiles.png", "small-arms.png",
    "unmanned-aerial-vehicles.png", "unmanned-ground-vehicles.png",
    "naval-vessels.png",
}

LIVE_NOTE = ("catalog reference data only - real-time numbers come from the "
             "live connectors (/api/v1/opensky, /api/v1/gkg), not this store")


async def _meta(db: AsyncSession) -> dict:
    snap = (await db.execute(
        select(ArsSnapshot).order_by(ArsSnapshot.imported_at.desc()).limit(1)
    )).scalars().first()
    return {
        "source": "a-san catalog (one-way import)",
        "snapshot_id": str(snap.id) if snap else None,
        "imported_at": snap.imported_at.isoformat() if snap else None,
        "source_sha256": snap.source_sha256 if snap else None,
        "live_note": LIVE_NOTE,
    }


@router.get("/icons/{fname}")
async def category_icon(fname: str):
    """Category glyph (ported from the a-san design). Allowlisted filenames
    only; public + cacheable — icons carry no catalog data."""
    if fname not in ALLOWED_ICONS:
        raise HTTPException(status_code=404, detail="unknown icon")
    path = os.path.join(ICON_DIR, fname)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="icon missing")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/categories")
async def list_categories(user: SupabaseUser = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Categories with display names, icon paths and active item counts."""
    rows = (await db.execute(
        select(ArsCategory, func.count(ArsItem.id))
        .outerjoin(ArsItem, (ArsItem.category_key == ArsCategory.key)
                   & (ArsItem.active.is_(True)))
        .group_by(ArsCategory.id)
        .order_by(ArsCategory.sort_order))).all()
    cats = [{
        "key": c.key, "display_name": c.display_name,
        "icon_path": c.icon_path, "count": n,
    } for c, n in rows]
    return {"categories": cats,
            "total_active": sum(c["count"] for c in cats),
            "meta": await _meta(db)}


@router.get("/items")
async def query_items(country: str | None = None, category: str | None = None,
                      q: str | None = None,
                      include_retired: bool = False,
                      limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0),
                      user: SupabaseUser = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """Structured catalog query. Filters combine with AND; q matches
    designation/manufacturer/description substrings.

    Response mirrors the legacy sims/ontology/arsenal shape (entries,
    total_matched_estimate, catalog_totals) so the admin Arsenal Browser
    consumes this store route directly — the store is the source of truth.
    """
    conds = []
    if not include_retired:
        conds.append(ArsItem.active.is_(True))
    if country:
        norm = arsenal_mod.normalize_country(country)
        if norm:
            conds.append(func.lower(ArsItem.country_norm) == norm.lower())
        else:
            conds.append(func.lower(func.coalesce(
                ArsItem.country_raw, "")) == country.lower())
    if category:
        conds.append(ArsItem.category_key == category)
    if q:
        like = f"%{q.lower()}%"
        conds.append(or_(
            func.lower(ArsItem.designation).like(like),
            func.lower(func.coalesce(ArsItem.manufacturer, "")).like(like),
            func.lower(func.coalesce(ArsItem.description, "")).like(like)))

    base = select(ArsItem).where(*conds) if conds else select(ArsItem)
    total = (await db.execute(
        select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(ArsItem.designation).limit(limit).offset(offset))
    ).scalars().all()

    cat_rows = (await db.execute(select(ArsCategory))).scalars().all()
    display_by_key = {c.key: c.display_name for c in cat_rows}
    active_total = (await db.execute(
        select(func.count()).select_from(ArsItem)
        .where(ArsItem.active.is_(True)))).scalar_one()

    entries = []
    for r in rows:
        specs_parsed, specs_extra = {}, []
        for s in (r.specs or []):
            parsed = arsenal_mod._parse_spec_value(s) if hasattr(
                arsenal_mod, "_parse_spec_value") else None
            if parsed:
                specs_parsed[parsed[0]] = parsed[1]
            elif s.strip():
                specs_extra.append(s.strip())
        entries.append({
            "id": str(r.id), "fingerprint": r.fingerprint[:16],
            "designation": r.designation, "alt_names": r.alt_names or [],
            "country": r.country_norm or r.country_raw,
            "manufacturer": r.manufacturer,
            "category": display_by_key.get(r.category_key, r.category_key or ""),
            "category_key": r.category_key,
            "description": r.description,
            "specs_parsed": specs_parsed,
            "specs_extra": specs_extra[:8],
            "sources": [{"label": s.get("label"), "url": s.get("url")}
                        for s in (r.sources or [])],
            "specs_count": len(r.specs or []),
            "sources_count": len(r.sources or []),
            "fetched_at": r.fetched_at, "active": bool(r.active),
            "ontology_pk": r.ontology_pk,
        })
    return {"entries": entries, "total_matched_estimate": total,
            "offset": offset, "limit": limit,
            "categories": [c.key for c in cat_rows],
            "catalog_totals": {"entries": active_total,
                               "categories": len(cat_rows)},
            "meta": await _meta(db)}


@router.get("/items/{item_id}")
async def get_item(item_id: str,
                   user: SupabaseUser = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    """Full profile for one catalog item by UUID."""
    row = (await db.execute(
        select(ArsItem).where(ArsItem.id == item_id))).scalars().first()
    if row is None:
        return {"error": "not found", "item_id": item_id}
    return {
        "id": str(row.id), "designation": row.designation,
        "alt_names": row.alt_names or [], "country": row.country_norm or row.country_raw,
        "country_raw": row.country_raw, "manufacturer": row.manufacturer,
        "category_key": row.category_key, "description": row.description,
        "specs": row.specs or [], "sources": row.sources or [],
        "fetched_at": row.fetched_at, "active": bool(row.active),
        "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "retired_at": row.retired_at.isoformat() if row.retired_at else None,
        "meta": await _meta(db),
    }


async def _country_matrix(db: AsyncSession, countries: list[str] | None = None):
    """count per (country_norm, category_key); optionally restrict countries."""
    stmt = (
        select(ArsItem.country_norm, ArsItem.category_key, func.count())
        .where(ArsItem.active.is_(True))
        .group_by(ArsItem.country_norm, ArsItem.category_key))
    if countries:
        low = {c.lower() for c in countries}
        stmt = stmt.where(func.lower(ArsItem.country_norm).in_(low))
    rows = (await db.execute(stmt)).all()
    matrix: dict[str, dict[str, int]] = {}
    for country, cat, n in rows:
        if not country:
            continue
        matrix.setdefault(country, {})[cat] = n
    return matrix


@router.get("/by-object/{object_id}")
async def by_ontology_object(object_id: str,
                             user: SupabaseUser = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """
    Resolve a Spinal Cracker arsenal_system object (fusion-map marker,
    MAVEN asset/task reference) back to its stable catalog profile.
    """
    from panteon.spinal_craker.models import Object
    from panteon.arsenal_store import ArsOntologyLink

    link = (await db.execute(
        select(ArsOntologyLink).where(
            ArsOntologyLink.sc_object_id == object_id))).scalars().first()
    if link is None:
        return {"error": "no catalog item linked to this object",
                "object_id": object_id}
    row = (await db.execute(
        select(ArsItem).where(ArsItem.id == link.ars_item_id))).scalars().first()
    if row is None:
        return {"error": "linked catalog item retired", "object_id": object_id}
    obj = (await db.execute(
        select(Object).where(Object.id == object_id))).scalars().first()
    return {
        "object_id": object_id,
        "ontology_pk": obj.primary_key_value if obj else None,
        "item": await get_item(str(row.id), user, db),
    }


@router.get("/capabilities/countries")
async def capabilities_countries(category: str | None = None, top: int = Query(50, ge=1, le=200),
                                 user: SupabaseUser = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """Nation -> {category: count} matrix across the whole active store."""
    matrix = await _country_matrix(db)
    out = {}
    for country, cats in matrix.items():
        if category:
            if category in cats:
                out[country] = {category: cats[category]}
        else:
            out[country] = dict(sorted(cats.items(),
                                       key=lambda kv: -kv[1]))
    ranked = sorted(out.items(), key=lambda kv: -sum(kv[1].values()))
    return {"countries": [{"country": c, "counts": cats, "total": sum(cats.values())}
                          for c, cats in ranked[:top]],
            "nations": len(out), "meta": await _meta(db)}


@router.get("/capabilities/compare")
async def capabilities_compare(countries: str,
                               user: SupabaseUser = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """
    Side-by-side comparison: ?countries=USA,Russia,China (comma-separated).
    Returns per-country category counts + per-category leaders.
    """
    wanted = [c.strip() for c in countries.split(",") if c.strip()]
    if not wanted:
        return {"error": "provide ?countries=A,B,C"}
    normed = [arsenal_mod.normalize_country(c) or c for c in wanted]
    matrix = await _country_matrix(db, normed)

    result = []
    for original, norm in zip(wanted, normed):
        cats = matrix.get(norm) or {}
        result.append({"requested": original, "country": norm,
                       "counts": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
                       "total": sum(cats.values())})
    all_cats = sorted({c for r in result for c in r["counts"]})
    leaders = {cat: max(result, key=lambda r: r["counts"].get(cat, 0))["country"]
               for cat in all_cats}
    return {"comparison": result, "categories": all_cats,
            "leader_per_category": leaders, "meta": await _meta(db)}
