"""
Arsenal Sync — one-way import a-san catalog-data.json -> ars_* tables in
panteon.db. Idempotent: running twice in a row changes nothing the second
time. Missing entries are RETIRED (active=0), never deleted. Every run
writes an ArsSnapshot audit row (unless --dry-run).

Usage:
    cd /home/alieninc/panteon/backend && python -m panteon.arsenal_sync
    python -m panteon.arsenal_sync --dry-run
    python -m panteon.arsenal_sync --note "post-crawl refresh"

Safety: reads the a-san file read-only; writes only the additive ars_*
tables; asserts count invariants before committing.
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import select, update, func

from panteon.core.database import engine, async_session
from panteon.arsenal_store import (
    ArsCategory, ArsItem, ArsSnapshot, ArsOntologyLink,
    fingerprint, ontology_pk,
)
from panteon import arsenal as arsenal_mod

CHUNK = 500


async def _ensure_ars_tables() -> None:
    """Create ONLY the additive ars_* tables if missing (idempotent,
    touches nothing else — same create_all semantics as app startup).
    sc_object_types/sc_objects are included solely so SQLAlchemy can
    resolve the ArsOntologyLink FKs; they already exist."""
    from panteon.core.database import Base
    from panteon.spinal_craker.models import Object, ObjectType
    tables = [ObjectType.__table__, Object.__table__,
              ArsCategory.__table__, ArsItem.__table__,
              ArsSnapshot.__table__, ArsOntologyLink.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=tables))

# key -> icon file under /api/v1/arsenal/icons/ (allowlisted FileResponse).
CATEGORY_ICONS = {    "aircraft": "aircraft.png",
    "uavs": "unmanned-aerial-vehicles.png",
    "air-launched-munitions": "air-launched-weapons.png",
    "rocket-and-missile-weapons": "missile-and-rocket-weapons.png",
    "sea-launched-cruise-missiles": "sea-launched-cruise-missiles.png",
    "ew-assets": "electronic-warfare-systems.png",
    "ugvs": "unmanned-ground-vehicles.png",
    "armored-vehicles-and-equipment": "armored-vehicles-and-equipment.png",
    "automotive-vehicles": "automotive-vehicles.png",
    "small-arms": "small-arms.png",
    "naval-vessels": "naval-vessels.png",
}


def content_hash(entry: dict) -> str:
    basis = json.dumps({
        "d": entry.get("designation"),
        "a": sorted(entry.get("alt_names") or []),
        "c": entry.get("country"),
        "m": entry.get("manufacturer"),
        "s": entry.get("description"),
        "sp": entry.get("specs"),
        "src": [(x.get("label"), x.get("url")) for x in (entry.get("sources") or [])],
        "f": entry.get("fetched_at"),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _first_source_url(entry: dict) -> str | None:
    src = entry.get("sources") or []
    return (src[0].get("url") if src else None)


async def sync_categories(db, cat_keys: list[str], cat_names: list[str]) -> int:
    name_by_key = {}
    if isinstance(cat_names, list):
        name_by_key = dict(zip(cat_keys, cat_names))
    existing = {
        c.key: c for c in (
            await db.execute(select(ArsCategory))).scalars().all()
    }
    changed = 0
    for i, key in enumerate(cat_keys):
        row = existing.get(key)
        display = name_by_key.get(key) or key.replace("-", " ").title()
        icon = CATEGORY_ICONS.get(key)
        icon_path = f"/api/v1/arsenal/icons/{icon}" if icon else None
        if row is None:
            db.add(ArsCategory(key=key, display_name=display,
                               icon_path=icon_path, sort_order=i))
            changed += 1
        elif row.display_name != display or row.icon_path != icon_path \
                or row.sort_order != i:
            row.display_name, row.icon_path = display, icon_path
            row.sort_order = i
            changed += 1
    return changed


async def run_sync(dry_run: bool = False, note: str | None = None) -> dict:
    t0 = time.monotonic()
    await _ensure_ars_tables()
    path = arsenal_mod.CATALOG_PATH
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return {"ok": False, "error": f"catalog missing at {path}"}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    sha256 = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            sha256.update(block)

    cat_keys = list(data.get("category_keys") or [])
    cat_names = list(data.get("categories") or [])
    entries_by_cat = data.get("entries") or {}

    # ---- flatten + validate -------------------------------------------------
    seen: dict[str, tuple[str, dict]] = {}   # fingerprint -> (cat_key, entry)
    skipped = 0
    for ck in cat_keys:
        for e in entries_by_cat.get(ck) or []:
            desig = (e.get("designation") or "").strip()
            if not desig:
                skipped += 1
                continue
            fp = fingerprint(ck, desig)
            seen[fp] = (ck, e)
    total = len(seen)

    stats = {"total": total, "skipped_no_designation": skipped,
             "added": 0, "updated": 0, "unchanged": 0, "retired": 0}

    async with async_session() as db:
        try:
            stats["categories_changed"] = await sync_categories(
                db, cat_keys, cat_names)

            # ---- load existing index in chunks -----------------------------
            fps = list(seen)
            existing: dict[str, ArsItem] = {}
            for i in range(0, len(fps), CHUNK):
                batch = fps[i:i + CHUNK]
                rows = (await db.execute(
                    select(ArsItem).where(ArsItem.fingerprint.in_(batch))
                )).scalars().all()
                existing.update({r.fingerprint: r for r in rows})

            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # ---- add / update ----------------------------------------------
            for fp, (ck, e) in seen.items():
                chash = content_hash(e)
                row = existing.get(fp)
                if row is None:
                    db.add(ArsItem(
                        fingerprint=fp,
                        ontology_pk=ontology_pk(ck, e.get("designation")),
                        designation=e.get("designation"),
                        alt_names=e.get("alt_names") or [],
                        country_raw=e.get("country") or None,
                        country_norm=arsenal_mod.normalize_country(
                            e.get("country")) or None,
                        manufacturer=e.get("manufacturer") or None,
                        category_key=ck,
                        description=e.get("description") or None,
                        specs=e.get("specs") or [],
                        sources=[{"label": s.get("label"), "url": s.get("url")}
                                 for s in (e.get("sources") or [])],
                        source_url=_first_source_url(e),
                        fetched_at=e.get("fetched_at"),
                        content_hash=chash,
                        active=True,
                        first_seen_at=now, last_seen_at=now,
                    ))
                    stats["added"] += 1
                elif row.content_hash != chash:
                    row.designation = e.get("designation")
                    row.alt_names = e.get("alt_names") or []
                    row.country_raw = e.get("country") or None
                    row.country_norm = arsenal_mod.normalize_country(
                        e.get("country")) or row.country_norm
                    row.manufacturer = e.get("manufacturer") or None
                    row.description = e.get("description") or None
                    row.specs = e.get("specs") or []
                    row.sources = [{"label": s.get("label"), "url": s.get("url")}
                                   for s in (e.get("sources") or [])]
                    row.source_url = _first_source_url(e)
                    row.fetched_at = e.get("fetched_at")
                    row.content_hash = chash
                    row.last_seen_at = now
                    if not row.active:
                        row.active = True
                        row.retired_at = None
                    stats["updated"] += 1
                else:
                    if row.active:
                        row.last_seen_at = now
                    stats["unchanged"] += 1

            # ---- retire missing (never delete) ------------------------------
            if not dry_run:
                await db.flush()
                active_fps = [r for r in (await db.execute(
                    select(ArsItem.fingerprint, ArsItem.id).where(
                        ArsItem.active.is_(True)))).all()]
                gone_ids = [rid for fpr, rid in active_fps if fpr not in seen]
                if gone_ids:
                    for i in range(0, len(gone_ids), CHUNK):
                        await db.execute(
                            update(ArsItem)
                            .where(ArsItem.id.in_(gone_ids[i:i + CHUNK]))
                            .values(active=False, retired_at=now))
                    stats["retired"] = len(gone_ids)

            # ---- invariants before commit ------------------------------------
            assert stats["added"] + stats["updated"] + stats["unchanged"] \
                == total, "add/update/unchanged must reconcile with input"
            if not dry_run:
                active_n = (await db.execute(
                    select(func.count()).select_from(ArsItem).where(
                        ArsItem.active.is_(True)))).scalar_one()
                assert active_n >= total, \
                    f"active count {active_n} below imported total {total}"

                db.add(ArsSnapshot(
                    source_path=path, source_sha256=sha256.hexdigest(),
                    source_mtime=str(mtime), total_entries=total,
                    added=stats["added"], updated=stats["updated"],
                    unchanged=stats["unchanged"], retired=stats["retired"],
                    dry_run=False, duration_ms=int((time.monotonic() - t0) * 1000),
                    note=note,
                ))
                await db.commit()
            else:
                await db.rollback()
        except Exception:
            await db.rollback()
            raise

    stats.update({
        "ok": True, "dry_run": dry_run, "source_sha256": sha256.hexdigest()[:16],
        "duration_ms": int((time.monotonic() - t0) * 1000),
    })
    return stats


async def link_ontology(db=None) -> dict:
    """
    Backfill ArsOntologyLink rows: join ars_items.ontology_pk onto existing
    arsenal_system sc_objects so every materialized object resolves to a
    stable catalog ID. Idempotent; existing links are never duplicated.
    """
    from panteon.spinal_craker.models import Object, ObjectType

    own = db is None
    if own:
        async with async_session() as s:
            return await link_ontology(s)
    tids = (await db.execute(
        select(ObjectType.id).where(ObjectType.name == "arsenal_system")
    )).scalars().all()
    if not tids:
        return {"linked": 0, "objects": 0, "note": "no arsenal_system type"}
    pairs = (await db.execute(
        select(ArsItem.id, Object.id)
        .join(Object, Object.primary_key_value == ArsItem.ontology_pk)
        .where(Object.object_type_id.in_([str(t) for t in tids]))
        .where(ArsItem.active.is_(True)))).all()
    have = set((await db.execute(
        select(ArsOntologyLink.ars_item_id, ArsOntologyLink.sc_object_id)
    )).all())
    new_rows = 0
    for item_id, obj_id in pairs:
        if (item_id, obj_id) in have:
            continue
        db.add(ArsOntologyLink(ars_item_id=item_id, sc_object_id=obj_id))
        new_rows += 1
    await db.commit()
    return {"linked": new_rows, "objects": len(pairs)}


def main() -> int:
    ap = argparse.ArgumentParser(description="a-san -> panteon arsenal sync")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute diff without writing")
    ap.add_argument("--link-ontology", action="store_true",
                    help="backfill ars_ontology_links after sync")
    ap.add_argument("--note", default=None, help="audit note for snapshot")
    args = ap.parse_args()
    result = asyncio.run(run_sync(dry_run=args.dry_run, note=args.note))
    if result.get("ok") and args.link_ontology:
        result["ontology_links"] = asyncio.run(link_ontology())
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
