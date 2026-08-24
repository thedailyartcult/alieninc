"""
Arsenal Store — structured, versioned copy of the a-san catalog inside
panteon.db. ADDITIVE ONLY: these tables never alter existing ones and rows
are never deleted (retired items get active=0).

The a-san dataset stays the single source of truth:
  - one-way sync (a-san -> here) via panteon.arsenal_sync
  - every sync run writes an ArsSnapshot audit row
  - real-time operational numbers do NOT live here; they come from the
    live connectors (OpenSky/adsb.fi, GDELT, ...). This store is catalog
    reference data only.

ArsOntologyLink maps catalog items onto Spinal Cracker ontology objects so
MAVEN tasks/assets/detections can reference real systems by stable ID.
"""
import hashlib
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, ForeignKey,
    UniqueConstraint, Index, Integer
)

from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


def fingerprint(cat_key: str, designation: str) -> str:
    """Stable content-independent ID for one catalog entry."""
    raw = f"{cat_key}|{(designation or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ontology_pk(cat_key: str, designation: str) -> str:
    """Spinal Cracker pk convention used by curated_flagships."""
    return f"arsenal:{cat_key}:{(designation or '').strip().lower()[:80]}"


class ArsCategory(Base):
    __tablename__ = "ars_categories"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    key = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    icon_path = Column(String(500))
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ArsItem(Base):
    __tablename__ = "ars_items"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    fingerprint = Column(String(200), nullable=False, unique=True)
    ontology_pk = Column(String(300), index=True)   # "arsenal:<cat>:<slug>" sc_objects PK
    designation = Column(String(500), nullable=False)
    alt_names = Column(JSONB, default=list)
    country_raw = Column(String(255))
    country_norm = Column(String(255), index=True)
    manufacturer = Column(String(500))
    category_key = Column(
        String(100), ForeignKey("ars_categories.key"), nullable=False, index=True)
    description = Column(Text)
    specs = Column(JSONB, default=list)
    sources = Column(JSONB, default=list)
    source_url = Column(String(1000))
    fetched_at = Column(String(64))
    content_hash = Column(String(64), nullable=False)
    active = Column(Boolean, default=True, index=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    retired_at = Column(DateTime)

    __table_args__ = (
        Index("ix_ars_items_cat_country", "category_key", "country_norm"),
    )


class ArsSnapshot(Base):
    __tablename__ = "ars_snapshots"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    imported_at = Column(DateTime, default=datetime.utcnow)
    source_path = Column(String(1000), nullable=False)
    source_sha256 = Column(String(64))
    source_mtime = Column(String(64))
    total_entries = Column(Integer, nullable=False)
    added = Column(Integer, default=0)
    updated = Column(Integer, default=0)
    unchanged = Column(Integer, default=0)
    retired = Column(Integer, default=0)
    dry_run = Column(Boolean, default=False)
    duration_ms = Column(Integer)
    note = Column(Text)


class ArsOntologyLink(Base):
    __tablename__ = "ars_ontology_links"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    ars_item_id = Column(UUID_COL(), ForeignKey("ars_items.id"), nullable=False)
    sc_object_id = Column(UUID_COL(), ForeignKey("sc_objects.id"), nullable=False)
    relation = Column(String(100), default="materialized_from")
    linked_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ars_item_id", "sc_object_id", name="uq_ars_obj_link"),
        Index("ix_ars_link_item", "ars_item_id"),
    )
