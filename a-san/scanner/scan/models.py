"""Data models shared across the scanner."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SourceRef:
    label: str
    url: str

    def to_dict(self):
        return {"label": self.label, "url": self.url}


@dataclass
class CatalogEntry:
    designation: str
    category: str            # canonical display name (e.g. "Aircraft")
    description: str = ""
    alt_names: list[str] = field(default_factory=list)
    country: str = ""
    manufacturer: str = ""
    specs: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    fetched_at: str = ""

    def to_dict(self):
        return {
            "designation": self.designation,
            "alt_names": list(self.alt_names),
            "country": self.country,
            "manufacturer": self.manufacturer,
            "category": self.category,
            "description": self.description,
            "specs": list(self.specs),
            "sources": [s.to_dict() for s in self.sources],
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CatalogEntry":
        return cls(
            designation=d.get("designation", ""),
            category=d.get("category", ""),
            description=d.get("description", ""),
            alt_names=list(d.get("alt_names", [])),
            country=d.get("country", ""),
            manufacturer=d.get("manufacturer", ""),
            specs=list(d.get("specs", [])),
            sources=[SourceRef(s.get("label", ""), s.get("url", "")) for s in d.get("sources", [])],
            fetched_at=d.get("fetched_at", ""),
        )

    def fingerprint(self) -> str:
        """Content-stable fingerprint: normalized designation + spec hash."""
        norm = " ".join(self.designation.lower().split())
        spec_blob = "|".join(" ".join(s.lower().split()) for s in sorted(self.specs))
        return hashlib.sha256(f"{norm}::{spec_blob}".encode()).hexdigest()

    def designation_key(self) -> str:
        """Merge key: lower-case, spaces collapsed."""
        return " ".join(self.designation.lower().split())


def entry_to_json(e: CatalogEntry) -> str:
    return json.dumps(e.to_dict(), ensure_ascii=False, sort_keys=True)
