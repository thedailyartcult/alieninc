"""
Module B: transform_gdelt_to_ontology
The pure computational Transform layer. Maps raw dataset strings into
structural system primitives with schema validation and isolation of poisoned rows.
"""

import uuid
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("magritte.transform.gdelt")


class ObjectType:
    """System-defined object type definitions (schema metadata)."""

    GDELT_ARTICLE = "gdelt_article"

    _type_definitions: Dict[str, Dict[str, Any]] = {
        "gdelt_article": {
            "fields": [
                {"name": "url", "type": "str", "required": True},
                {"name": "title", "type": "str", "required": True},
                {"name": "seendate", "type": "str", "required": True},
                {"name": "sourcecountry", "type": "str", "required": False},
                {"name": "domain", "type": "str", "required": False},
            ],
            "relationships": [
                {"name": "ARTICLE_PUBLISHED_IN_COUNTRY", "cardinality": "1..*", "target": "geo_country"},
            ],
        }
    }

    @classmethod
    def get_type_definition(cls, obj_type: str) -> Optional[Dict[str, Any]]:
        return cls._type_definitions.get(obj_type)

    @classmethod
    def get_all_types(cls) -> Dict[str, Dict[str, Any]]:
        return cls._type_definitions


@dataclass
class ProcessedRecord:
    """Parsed and validated record with metadata."""

    url: str
    title: str
    seendate: str
    sourcecountry: str
    domain: str
    payload: Dict[str, Any]
    parsed_at: str
    is_valid: bool
    error_code: Optional[str] = None
    error_detail: Optional[str] = None


@dataclass
class PipelineState:
    """Runtime state for the Transform pipeline."""

    valid_records: List[ProcessedRecord] = field(default_factory=list)
    poisoned_records: List[Dict[str, Any]] = field(default_factory=list)
    schema_version: str = "1.0.0"
    migration_hook: Optional[callable] = None


class GDELTTransformEngine:
    """Pure computational transform block mapping raw strings to structural primitives."""

    def __init__(
        self,
        object_types: Optional[Dict[str, Any]] = None,
        schema_migration_hook: Optional[callable] = None,
    ):
        self._object_types = object_types or ObjectType.get_all_types()
        self._migration_hook = schema_migration_hook
        self._schema_registry: Dict[str, Dict[str, Any]] = {}
        self._bootstrapped = False
        self._bootstrap()

    def _bootstrap(self) -> None:
        """Bootstrap missing schemas via migration hook."""
        if self._bootstrapped:
            return
        if self._migration_hook:
            self._migration_hook()
        self._bootstrapped = True

    def _validate_schema(self, obj_type: str) -> bool:
        """Check that the object type schema exists."""
        return obj_type in self._object_types

    @staticmethod
    def _normalize_timestamp(seendate: str) -> Optional[str]:
        """Normalize a seendate to ISO-8601 UTC."""
        if not seendate:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(seendate, fmt)
                return dt.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                continue
        return None

    def _is_poisoned(self, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Check if a payload is poisoned (malformed or empty URL)."""
        url = payload.get("url")
        if not url or not isinstance(url, str) or not url.strip():
            return True, "Empty or missing URL"
        if not isinstance(payload, dict):
            return True, "Payload is not a dict"
        return False, None

    def transform(
        self, raw_records: List[Dict[str, Any]]
    ) -> Tuple[List[ProcessedRecord], List[Dict[str, Any]]]:
        """
        Transform raw GDELT records into validated structural primitives.
        Returns (valid_records, poisoned_records).
        """
        valid_records: List[ProcessedRecord] = []
        poisoned_records: List[Dict[str, Any]] = []

        if not self._validate_schema(ObjectType.GDELT_ARTICLE):
            self._bootstrap()
            if not self._validate_schema(ObjectType.GDELT_ARTICLE):
                poisoned_records.append({
                    "index": -1,
                    "raw": raw_records,
                    "reason": f"Schema '{ObjectType.GDELT_ARTICLE}' missing after bootstrap",
                })
                logger.error("Object type '%s' not present; all records routed to poison channel.", ObjectType.GDELT_ARTICLE)
                return valid_records, poisoned_records

        for i, raw in enumerate(raw_records):
            if not isinstance(raw, dict):
                poisoned_records.append({
                    "index": i,
                    "raw": raw,
                    "reason": "Non-dict payload",
                })
                continue

            is_poisoned, reason = self._is_poisoned(raw)
            if is_poisoned:
                poisoned_records.append({
                    "index": i,
                    "raw": raw,
                    "reason": reason,
                })
                continue

            url = raw.get("url", "")
            title = raw.get("title", "")
            seendate = raw.get("seendate", "")
            sourcecountry = raw.get("sourcecountry", "")
            domain = raw.get("domain", "")

            normalized = self._normalize_timestamp(seendate)
            if normalized is None:
                poisoned_records.append({
                    "index": i,
                    "raw": raw,
                    "reason": f"Unparseable seendate: '{seendate}'",
                })
                continue

            parsed_at = datetime.now(timezone.utc).isoformat()

            record = ProcessedRecord(
                url=url,
                title=title,
                seendate=normalized,
                sourcecountry=sourcecountry,
                domain=domain,
                payload=raw,
                parsed_at=parsed_at,
                is_valid=True,
            )
            valid_records.append(record)

        if valid_records:
            logger.info(
                f"Transform: {len(valid_records)} valid, {len(poisoned_records)} poisoned records processed."
            )
        else:
            logger.warning("Transform: zero valid records produced.")

        return valid_records, poisoned_records


class OntologyLayer:
    """Simulated ontology layer that tracks Object Types and Link Types."""

    def __init__(self):
        self.object_types: Dict[str, Dict[str, Any]] = {}
        self.link_types: Dict[str, Dict[str, Any]] = {}
        self._initialize_default()

    def _initialize_default(self) -> None:
        """Register default object and link type definitions."""
        self.object_types["gdelt_article"] = {
            "name": "gdelt_article",
            "display_name": "GDELT Article",
            "description": "GDELT DOC 2.0 article object",
            "fields": ["url", "title", "seendate", "sourcecountry", "domain"],
            "relationships": ["ARTICLE_PUBLISHED_IN_COUNTRY"],
        }
        self.link_types["ARTICLE_PUBLISHED_IN_COUNTRY"] = {
            "name": "ARTICLE_PUBLISHED_IN_COUNTRY",
            "description": "Link from article to geo_country via sourcecountry",
            "target_type": "geo_country",
        }

    def register_object_type(
        self, name: str, definition: Dict[str, Any]
    ) -> None:
        """Register a new object type definition."""
        self.object_types[name] = definition

    def register_link_type(self, name: str, definition: Dict[str, Any]) -> None:
        """Register a new link type definition."""
        self.link_types[name] = definition

    def get_object_type(self, name: str) -> Optional[Dict[str, Any]]:
        return self.object_types.get(name)

    def get_link_type(self, name: str) -> Optional[Dict[str, Any]]:
        return self.link_types.get(name)

    def list_all_types(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.object_types), dict(self.link_types)

    def evaluate_link_exists(self, sourcecountry: str) -> bool:
        """Check if a geo_country link exists for sourcecountry."""
        return sourcecountry in self.object_types


class GDELTTransformPipeline:
    """Orchestrates the transform pipeline with schema validation and poisoning isolation."""

    def __init__(
        self,
        ontology: OntologyLayer,
        schema_migration_hook: Optional[callable] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self._ontology = ontology
        self._migration_hook = schema_migration_hook
        self._config = config or {}
        object_types = getattr(ontology, "object_types", None)
        if object_types is None:
            object_types = ObjectType.get_all_types()
        self._transform_engine = GDELTTransformEngine(
            object_types=object_types,
            schema_migration_hook=self._migration_hook,
        )

    def run(
        self, raw_records: List[Dict[str, Any]]
    ) -> Tuple[List[ProcessedRecord], List[Dict[str, Any]]]:
        """Run the full transform pipeline."""
        valid, poisoned = self._transform_engine.transform(raw_records)
        return valid, poisoned

    def get_ontology_snapshot(self) -> Dict[str, Any]:
        """Return a snapshot of the current ontology state."""
        return {
            "object_types": getattr(self._ontology, "object_types", ObjectType.get_all_types()),
            "link_types": getattr(self._ontology, "link_types", {}),
            "schema_version": self._transform_engine.schema_version,
        }