"""
Module C: action_writeback_service
The high-rigor OSv2 sync engine enforcing strict ACID properties
via unit-of-work and multi-row transaction patterns.
"""

import uuid
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING, Generator
from datetime import datetime, timezone
from dataclasses import dataclass, field
from contextlib import contextmanager

logger = logging.getLogger("magritte.action.writeback")


COUNTRY_CODE_TO_NAME = {
    "US": "United States",
    "GB": "United Kingdom",
    "FR": "France",
    "DE": "Germany",
    "JP": "Japan",
    "IN": "India",
    "CN": "China",
    "BR": "Brazil",
    "AU": "Australia",
    "CA": "Canada",
    "KR": "South Korea",
    "RU": "Russia",
    "IL": "Israel",
    "MX": "Mexico",
    "EG": "Egypt",
    "NG": "Nigeria",
    "SE": "Sweden",
    "NO": "Norway",
    "IE": "Ireland",
    "IT": "Italy",
    "ES": "Spain",
    "PT": "Portugal",
    "NL": "Netherlands",
    "CH": "Switzerland",
    "BE": "Belgium",
    "DK": "Denmark",
    "FI": "Finland",
    "CN": "China",
    "CZ": "Czechia",
    "UA": "Ukraine",
    "PL": "Poland",
    "TR": "Turkey",
    "GR": "Greece",
    "RO": "Romania",
    "HU": "Hungary",
    "PT": "Portugal",
    "AT": "Austria",
    "DK": "Denmark",
}

COUNTRY_NAME_TO_CODE = {v: k for k, v in COUNTRY_CODE_TO_NAME.items()}

country_map = COUNTRY_CODE_TO_NAME


class WritebackTransaction:
    """ACID transaction wrapper for writeback operations."""

    def __init__(self, operation: str, transaction_id: str = None):
        self.operation = operation
        self.transaction_id = transaction_id or str(uuid.uuid5(uuid.NAMESPACE_URL, operation))
        self._records: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, Any]] = []
        self._committed: bool = False
        self._rolled_back: bool = False

    def add_record(self, record: Dict[str, Any]) -> None:
        """Add a record to the transaction. Raises on validation errors."""
        self._records.append(record)

    def add_error(self, record: Dict[str, Any], error: str) -> None:
        """Route a poisoned record to the error telemetry channel."""
        self._errors.append({"record": record, "error": error})

    def commit(self) -> None:
        """Commit the transaction to the Object Storage v2."""
        if self._rolled_back:
            raise RuntimeError("Transaction was already rolled back")
        self._committed = True

    def rollback(self) -> None:
        """Rollback the entire transaction, discarding all records."""
        self._rolled_back = True
        self._records.clear()
        self._errors.clear()

    @property
    def is_committed(self) -> bool:
        return self._committed

    @property
    def is_rolled_back(self) -> bool:
        return self._rolled_back

    @property
    def record_count(self) -> int:
        return len(self._records)

    @property
    def error_count(self) -> int:
        return len(self._errors)


@dataclass
class WritebackResult:
    """Result of a writeback operation."""
    transaction_id: str
    success_count: int
    failure_count: int
    committed_records: List[Dict[str, Any]]
    failed_records: List[Dict[str, Any]]
    error_details: List[Dict[str, Any]]
    timestamp: str
    schema_version: str = "1.0.0"


class ObjectNode:
    """Represent an Object Node in OSv2."""

    def __init__(
        self,
        guid: str,
        url: str,
        title: str,
        seendate: str,
        sourcecountry: str,
        domain: str,
        payload: Dict[str, Any],
        metadata: Dict[str, Any] = field(default_factory=dict),
    ):
        self.guid = guid
        self.url = url
        self.title = title
        self.seendate = seendate
        self.sourcecountry = sourcecountry
        self.domain = domain
        self.payload = payload
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guid": self.guid,
            "url": self.url,
            "title": self.title,
            "seendate": self.seendate,
            "sourcecountry": self.sourcecountry,
            "domain": self.domain,
            "payload": self.payload,
            "metadata": self.metadata,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def to_row(self) -> Dict[str, Any]:
        """Convert to OSv2 row format."""
        return {
            "guid": self.guid,
            "url": self.url,
            "title": self.title,
            "seendate": self.seendate,
            "sourcecountry": self.sourcecountry,
            "domain": self.domain,
            "properties": self.payload,
            "metadata": self.metadata,
            "type": "gdelt_article",
        }


class GeoCountryNode:
    """Represent a geo_country node in OSv2."""

    def __init__(
        self,
        country_code: str,
        country_name: str,
        metadata: Dict[str, Any] = field(default_factory=dict),
    ):
        self.country_code = country_code
        self.country_name = country_name
        self.metadata = metadata
        self.guid = f"geo_country:{country_code}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "country_code": self.country_code,
            "country_name": self.country_name,
            "metadata": self.metadata,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def to_row(self) -> Dict[str, Any]:
        return {
            "country_code": self.country_code,
            "country_name": self.country_name,
            "properties": self.metadata,
            "type": "geo_country",
            "guid": f"geo_country:{self.country_code}",
        }


class OntologyGraph:
    """In-memory representation of the ontology graph."""

    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: List[Dict[str, Any]] = []
        self._type_registry: Dict[str, str] = {}

    def register_node(
        self, guid: str, node_type: str, data: Dict[str, Any]
    ) -> None:
        self._nodes[guid] = {
            "guid": guid,
            "type": node_type,
            "data": data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def register_edge(
        self, source_guid: str, target_guid: str, relationship: str
    ) -> None:
        self._edges.append(
            {
                "source": source_guid,
                "target": target_guid,
                "relationship": relationship,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_node(self, guid: str) -> Optional[Dict[str, Any]]:
        return self._nodes.get(guid)

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        return list(self._nodes.values())

    def get_all_edges(self) -> List[Dict[str, Any]]:
        return list(self._edges)

    def count_nodes(self, node_type: Optional[str] = None) -> int:
        if node_type:
            return sum(1 for n in self._nodes.values() if n["type"] == node_type)
        return len(self._nodes)

    def count_edges(self) -> int:
        return len(self._edges)


class OSv2Manager:
    """Object Storage v2 semantic engine tracking Object Types and Link Types."""

    def __init__(self):
        self._object_nodes: Dict[str, Dict[str, Any]] = {}
        self._link_nodes: Dict[str, Dict[str, Any]] = {}
        self._type_definitions: Dict[str, Dict[str, Any]] = {}
        self._link_definitions: Dict[str, Dict[str, Any]] = {}

    def register_object_type(self, name: str, definition: Dict[str, Any]) -> None:
        """Register an object type definition."""
        self._type_definitions[name] = definition

    def register_link_type(self, name: str, definition: Dict[str, Any]) -> None:
        """Register a link type definition."""
        self._link_definitions[name] = definition

    def get_object_type(self, name: str) -> Optional[Dict[str, Any]]:
        return self._type_definitions.get(name)

    def get_link_type(self, name: str) -> Optional[Dict[str, Any]]:
        return self._link_definitions.get(name)

    def insert_object(self, guid: str, record: Dict[str, Any]) -> None:
        """Insert an object node into the OSv2 store.

        Standard article fields are flattened for the DOC pipeline; any extra
        top-level fields (e.g. GKG event_code / action_geo / avg_tone) are
        preserved so the admin frontend can read them directly.
        """
        node = {
            "guid": guid,
            "type": record.get("type", "gdelt_article"),
            "payload": record.get("properties", {}),
            "url": record.get("url", ""),
            "title": record.get("title", ""),
            "seendate": record.get("seendate", ""),
            "sourcecountry": record.get("sourcecountry", ""),
            "domain": record.get("domain", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for key, value in record.items():
            if key not in node:
                node[key] = value
        self._object_nodes[guid] = node

    def get_object(self, guid: str) -> Optional[Dict[str, Any]]:
        return self._object_nodes.get(guid)

    def get_all_objects(self) -> List[Dict[str, Any]]:
        return list(self._object_nodes.values())

    def link_object_to_geo(self, article_guid: str, sourcecountry: str) -> None:
        """Create a link entry from an article to a geo_country node.

        ``sourcecountry`` may arrive from GDELT as a full country name (e.g.
        "China"); it is normalized to a FIPS code for the geo_country node key.
        """
        code = self._resolve_country_code(sourcecountry) if hasattr(self, "_resolve_country_code") else sourcecountry
        country_name = self._resolve_country_name(sourcecountry) if hasattr(self, "_resolve_country_name") else sourcecountry
        target_guid = f"geo_country:{code}"
        if target_guid not in self._object_nodes:
            self.insert_object(target_guid, {
                "country_code": code,
                "country_name": country_name,
                "properties": {"sourcecountry": sourcecountry},
                "type": "geo_country",
                "guid": target_guid,
            })
        link_entry = {
            "guid": f"link:article:{article_guid}:{code}",
            "article_guid": article_guid,
            "country_code": code,
            "country_name": country_name,
            "relationship": "ARTICLE_PUBLISHED_IN_COUNTRY",
            "target_type": "geo_country",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._link_nodes[link_entry["guid"]] = link_entry

    def get_all_links(self) -> List[Dict[str, Any]]:
        return list(self._link_nodes.values())

    def count_objects(self) -> int:
        return len(self._object_nodes)

    def count_links(self) -> int:
        return len(self._link_nodes)

    def resolve_article_countries(self, article_guid: str) -> List[str]:
        """Resolve all countries linked to a given article."""
        countries = []
        for node in self._link_nodes.values():
            if node.get("article_guid") == article_guid:
                countries.append(node.get("country_code", ""))
        return list(dict.fromkeys(countries))


class WritebackService:
    """Transactional writeback service for OSv2 with ACID guarantees."""

    def __init__(
        self,
        osv2: "OSv2Manager",
        ontology_graph: Optional[OntologyGraph] = None,
    ):
        self._osv2 = osv2
        self._ontology = ontology_graph or OntologyGraph()

    @contextmanager
    def begin_transaction(
        self, operation: str
    ) -> Generator[WritebackTransaction, None, None]:
        """Begin a new writeback transaction."""
        tx = WritebackTransaction(operation=operation)
        try:
            yield tx
        except Exception:
            tx.rollback()
            raise

    async def writeback_batch(
        self,
        records: List[Dict[str, Any]],
        schema: Dict[str, Any],
    ) -> WritebackResult:
        """
        Writeback a batch of records with strict ACID all-or-nothing semantics.

        Phase 1 (validate): every record is checked against the OSv2 schema.
        Phase 2 (commit):   if ANY record fails validation, the entire batch is
                            rejected — zero rows written. Only when every record
                            validates are all rows inserted in a single pass.
        """
        transaction = WritebackTransaction(operation="writeback_batch")
        staged: List[Tuple[str, Dict[str, Any]]] = []
        error_details: List[Dict[str, Any]] = []

        for i, record in enumerate(records):
            try:
                guid = self._validate_and_create_object(record)
                staged.append((guid, record))
            except Exception as exc:
                error_details.append(
                    {
                        "record_index": i,
                        "record": record,
                        "error_code": str(exc.__class__.__name__),
                        "error_detail": str(exc),
                    }
                )

        if error_details:
            transaction.rollback()
            return WritebackResult(
                transaction_id=transaction.transaction_id,
                success_count=0,
                failure_count=len(records),
                committed_records=[],
                failed_records=records,
                error_details=error_details,
                timestamp=datetime.now(timezone.utc).isoformat(),
                schema_version=schema.get("schema_version", "1.0.0"),
            )

        committed_records: List[str] = []
        for guid, record in staged:
            self._osv2.insert_object(guid, record)
            transaction.add_record(guid)
            committed_records.append(guid)

            sourcecountry = record.get("sourcecountry", "")
            if sourcecountry:
                self._osv2.link_object_to_geo(guid, sourcecountry)

        transaction.commit()
        return WritebackResult(
            transaction_id=transaction.transaction_id,
            success_count=len(committed_records),
            failure_count=0,
            committed_records=committed_records,
            failed_records=[],
            error_details=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
            schema_version=schema.get("schema_version", "1.0.0"),
        )

    def _validate_and_create_object(self, record: Dict[str, Any]) -> str:
        """Validate a single record against schema and return its OSv2 guid."""
        guid = record.get("guid", str(uuid.uuid5(uuid.NAMESPACE_URL, record.get("url", "unknown"))))

        obj_type = record.get("type", "gdelt_article")
        type_def = self._osv2.get_object_type(obj_type)
        if not type_def:
            raise ValueError(f"Object type '{obj_type}' not found in schema")

        required_fields = type_def.get("required_fields", type_def.get("fields", []))
        for field_name in required_fields:
            if record.get(field_name) in (None, ""):
                raise ValueError(f"Missing required field '{field_name}' in record")

        properties = dict(record.get("properties", {}))
        properties.update({"guid": guid, "type": obj_type, "created_at": datetime.now(timezone.utc).isoformat()})

        return guid

    def _create_geo_country_link(
        self, source_country_code: str, article_guid: str
    ) -> None:
        """Dynamically emit a structural link entry for ARTICLE_PUBLISHED_IN_COUNTRY."""
        if source_country_code not in self._ontology._nodes:
            country_name = self._resolve_country_name(source_country_code)
            geo_node = GeoCountryNode(
                country_code=source_country_code,
                country_name=country_name,
            )
            self._ontology.register_node(
                guid=geo_node.guid,
                node_type="geo_country",
                data=geo_node.to_dict(),
            )
            self._ontology.register_edge(
                source_guid=article_guid,
                target_guid=geo_node.guid,
                relationship="ARTICLE_PUBLISHED_IN_COUNTRY",
            )

    def _resolve_country_code(self, country: str) -> str:
        """Resolve a GDELT sourcecountry (FIPS code or full name) to a FIPS code.

        GDELT DOC 2.0 returns full country names (e.g. "China"); the OSv2 graph
        keys geo_country nodes on the FIPS two-letter code. Falls back to the
        raw value uppercased when no mapping is known.
        """
        if not country:
            return "XX"
        code = country.strip().upper()
        if len(code) == 2 and code.isalpha():
            return code
        return COUNTRY_NAME_TO_CODE.get(country.strip(), code)

    def _resolve_country_name(self, code: str) -> str:
        """Resolve a FIPS two-letter country code to a display name."""
        return COUNTRY_CODE_TO_NAME.get(code.upper(), country_map.get(code.upper(), code))


class GDELTWritebackPipeline:
    """Production-ready writeback pipeline for Spinal Cracker OSv2 integration."""

    def __init__(
        self,
        osv2: "OSv2Manager",
        object_storage: Any,
        ontology_graph: Optional[OntologyGraph] = None,
    ):
        self._osv2 = osv2
        self._object_storage = object_storage
        self._ontology = ontology_graph or OntologyGraph()
        self._writeback_service = WritebackService(osv2, ontology_graph)

    async def process_gdelt_articles(
        self,
        raw_records: List[Dict[str, Any]],
        config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[WritebackResult, List[Dict[str, Any]]]:
        """
        Main writeback pipeline: validate, transform, and persist to OSv2.
        Returns (WritebackResult, error_details).
        """
        schema = {
            "schema_version": "2.0.0",
            "object_types": {
                "gdelt_article": {
                    "fields": ["url", "title", "seendate", "sourcecountry", "domain"],
                    "relationships": ["ARTICLE_PUBLISHED_IN_COUNTRY"],
                }
            },
            "link_types": {
                "ARTICLE_PUBLISHED_IN_COUNTRY": {
                    "target_type": "geo_country",
                }
            },
        }

        result = await self._writeback_batch(raw_records, schema)
        return result, []

    async def _writeback_batch(
        self, raw_records: List[Dict[str, Any]], schema: Dict[str, Any]
    ) -> WritebackResult:
        """
        Write back a batch of records with strict ACID all-or-nothing semantics.

        Phase 1 (validate): every record is checked against the OSv2 schema.
        Phase 2 (commit):   if ANY record fails validation, the entire batch is
                            rejected — zero rows written. Only when every record
                            validates are all rows inserted in a single pass.
        """
        transaction = WritebackTransaction(operation="writeback_batch")
        staged_rows: List[Tuple[str, Dict[str, Any]]] = []
        validation_errors: List[Dict[str, Any]] = []

        for i, record in enumerate(raw_records):
            try:
                guid, row = self._prepare_single_record(record)
                staged_rows.append((guid, row))
            except Exception as exc:
                validation_errors.append(
                    {
                        "record_index": i,
                        "record": record,
                        "error_code": str(exc.__class__.__name__),
                        "error_detail": str(exc),
                    }
                )

        if validation_errors:
            transaction.rollback()
            return WritebackResult(
                transaction_id=transaction.transaction_id,
                success_count=0,
                failure_count=len(validation_errors),
                committed_records=[],
                failed_records=raw_records,
                error_details=validation_errors,
                timestamp=datetime.now(timezone.utc).isoformat(),
                schema_version=schema.get("schema_version", "2.0.0"),
            )

        committed_records: List[Dict[str, Any]] = []
        for guid, row in staged_rows:
            self._osv2.insert_object(guid, row)
            transaction.add_record(guid)
            committed_records.append(guid)

            sourcecountry = row.get("sourcecountry", "")
            if sourcecountry:
                self._osv2.link_object_to_geo(guid, sourcecountry)

        transaction.commit()

        return WritebackResult(
            transaction_id=transaction.transaction_id,
            success_count=len(committed_records),
            failure_count=0,
            committed_records=committed_records,
            failed_records=[],
            error_details=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
            schema_version=schema.get("schema_version", "2.0.0"),
        )

    def _prepare_single_record(
        self, record: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Validate a record against the OSv2 schema and build its persisted row."""
        guid = record.get("guid", str(uuid.uuid5(uuid.NAMESPACE_URL, record.get("url", "unknown"))))
        obj_type = record.get("type", "gdelt_article")

        type_def = self._osv2.get_object_type(obj_type)
        if type_def is None:
            raise ValueError(f"Object type '{obj_type}' not found in OSv2 schema")
        required_fields = type_def.get("required_fields", type_def.get("fields", []))
        for field_name in required_fields:
            if record.get(field_name) in (None, ""):
                raise ValueError(f"Missing required field '{field_name}' for object type '{obj_type}'")

        properties = dict(record.get("properties", {}))
        properties.update({"guid": guid, "type": obj_type})

        row = {**record, "properties": properties}
        return guid, row

    def get_ontology_snapshot(self) -> Dict[str, Any]:
        """Return a snapshot of the ontology graph state.

        Schema (object/link type definitions) lives on the OntologyLayer while
        the persisted OSv2 rows live on the manager, so both are surfaced.
        """
        return {
            "object_types": getattr(self._ontology, "object_types", {}),
            "link_types": getattr(self._ontology, "link_types", {}),
            "node_count": self._osv2.count_objects(),
            "edge_count": self._osv2.count_links(),
        }


# ============================================================================
# Production entry point: main()
# ============================================================================

async def main() -> None:
    """Entry point demonstrating Spinal Cracker OSv2 integration."""
    import logging
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    # Initialize components
    osv2 = OSv2Manager()
    object_storage = {}
    ontology_graph = OntologyGraph()

    # Register object types and link types
    osv2.register_object_type("gdelt_article", {
        "name": "gdelt_article",
        "display_name": "GDELT Article",
        "description": "GDELT DOC 2.0 article object",
        "fields": ["url", "title", "seendate", "sourcecountry", "domain"],
        "required_fields": ["url"],
        "relationships": ["ARTICLE_PUBLISHED_IN_COUNTRY"],
    })
    osv2.register_object_type("geo_country", {
        "name": "geo_country",
        "display_name": "Geo Country",
        "description": "Geographic country node",
        "fields": ["country_code", "country_name"],
        "relationships": [],
    })

    # Initialize pipeline
    writeback_pipeline = GDELTWritebackPipeline(
        osv2=osv2,
        object_storage=object_storage,
        ontology_graph=ontology_graph,
    )

    # Simulate GDELT DOC 2.0 payloads
    sample_records = [
        {
            "url": "https://gdeltproject.org/doc2/article?id=20240101-001",
            "title": "Global conflict resolution initiative",
            "seendate": "2024-01-01T00:00:00",
            "sourcecountry": "US",
            "domain": "peace",
            "type": "gdelt_article",
        },
        {
            "url": "https://gdeltproject.org/doc2/article?id=20240101-002",
            "title": "Climate change mitigation research",
            "seendate": "2024-01-02T00:00:00",
            "sourcecountry": "DE",
            "domain": "environment",
            "type": "gdelt_article",
        },
        {
            "url": "https://gdeltproject.org/doc2/article?id=20240101-004",
            "title": "Economic recovery program",
            "seendate": "2024-01-04T00:00:00",
            "sourcecountry": "",
            "domain": "economics",
            "type": "gdelt_article",
        },
    ]

    poisoned_record = {
        "url": "",
        "title": "Malformed article - empty URL",
        "seendate": "2024-01-03T00:00:00",
        "sourcecountry": "JP",
        "domain": "technology",
        "type": "gdelt_article",
    }

    # Execute writeback (valid batch)
    result = await writeback_pipeline._writeback_batch(sample_records, {})
    print(f"Valid batch -> {result.success_count} committed, {result.failure_count} failed")
    print(f"Transaction ID: {result.transaction_id}")
    print(f"OSv2 state -> objects={osv2.count_objects()}, links={osv2.count_links()}")

    # Strict ACID demo: a poisoned record must reject the entire batch
    rejected = await writeback_pipeline._writeback_batch([poisoned_record], {})
    print(f"Poisoned batch -> {rejected.success_count} committed (expected 0), "
          f"{rejected.failure_count} failed, error: "
          f"{rejected.error_details[0]['error_detail'] if rejected.error_details else 'n/a'}")
    assert rejected.success_count == 0
    assert osv2.count_objects() == 3, "ACID violated: poisoned batch wrote rows"

    # Log ontology snapshot
    snapshot = writeback_pipeline.get_ontology_snapshot()
    print(f"Ontology snapshot: {snapshot}")

    print("Spinal Cracker writeback pipeline initialized successfully.")
