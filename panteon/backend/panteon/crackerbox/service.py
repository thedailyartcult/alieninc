import uuid
import math
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from panteon.crackerbox.models import (
    Investigation, Finding, Evidence, ThreatEntity, GeoEvent,
    PatternAlert, TimelineEvent, CountryRiskProfile,
)
from panteon.core.database import is_sqlite
import structlog

logger = structlog.get_logger()


def _uid(val) -> str:
    if is_sqlite and val is not None:
        return str(val)
    return val


class CrackerboxService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    # INVESTIGATION / CASE MANAGEMENT
    # ================================================================

    async def create_investigation(
        self,
        title: str,
        description: Optional[str] = None,
        classification: str = "confidential",
        workspace_id: Optional[str] = None,
        created_by: Optional[str] = None,
        priority: str = "medium",
        tags: Optional[list] = None,
    ) -> Investigation:
        case_number = f"GC-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        inv = Investigation(
            case_number=case_number,
            title=title,
            description=description,
            classification=classification,
            workspace_id=workspace_id,
            created_by=created_by,
            priority=priority,
            tags=tags or [],
        )
        self.db.add(inv)
        await self.db.flush()

        await self._add_timeline_event(inv.id, "investigation_created", f"Investigation {case_number} opened", created_by)
        return inv

    async def update_investigation(
        self,
        investigation_id: str,
        updates: dict,
        updated_by: Optional[str] = None,
    ) -> Optional[Investigation]:
        result = await self.db.execute(
            select(Investigation).where(Investigation.id == _uid(investigation_id))
        )
        inv = result.scalar_one_or_none()
        if not inv:
            return None

        old_status = inv.status
        for key, val in updates.items():
            if hasattr(inv, key) and key not in ("id", "case_number", "created_at"):
                setattr(inv, key, val)

        if updates.get("status") and updates["status"] != old_status:
            await self._add_timeline_event(
                inv.id, "status_change",
                f"Status changed from {old_status} to {updates['status']}",
                updated_by,
            )
            if updates["status"] in ("closed", "archived"):
                inv.closed_at = datetime.utcnow()

        await self.db.flush()
        return inv

    async def get_investigation(self, investigation_id: str) -> Optional[dict]:
        result = await self.db.execute(
            select(Investigation)
            .options(selectinload(Investigation.findings), selectinload(Investigation.timeline_events))
            .where(Investigation.id == _uid(investigation_id))
        )
        inv = result.scalar_one_or_none()
        if not inv:
            return None
        return self._investigation_to_dict(inv)

    async def list_investigations(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = select(Investigation)
        if workspace_id:
            query = query.where(Investigation.workspace_id == workspace_id)
        if status:
            query = query.where(Investigation.status == status)
        query = query.order_by(desc(Investigation.created_at)).limit(limit)

        result = await self.db.execute(query)
        return [self._investigation_to_dict(inv) for inv in result.scalars().all()]

    async def assign_analyst(self, investigation_id: str, analyst_email: str) -> bool:
        result = await self.db.execute(
            select(Investigation).where(Investigation.id == _uid(investigation_id))
        )
        inv = result.scalar_one_or_none()
        if not inv:
            return False
        analysts = inv.assigned_analysts or []
        if analyst_email not in analysts:
            analysts.append(analyst_email)
            inv.assigned_analysts = analysts
            await self._add_timeline_event(
                inv.id, "analyst_assigned",
                f"Analyst {analyst_email} assigned to case",
                analyst_email,
            )
            await self.db.flush()
        return True

    # ================================================================
    # FINDINGS & EVIDENCE
    # ================================================================

    async def create_finding(
        self,
        investigation_id: str,
        title: str,
        summary: Optional[str] = None,
        analysis: Optional[str] = None,
        confidence: float = 0.0,
        finding_type: str = "observation",
        classification: str = "confidential",
        linked_entities: Optional[list] = None,
        linked_objects: Optional[list] = None,
        created_by: Optional[str] = None,
    ) -> Finding:
        finding = Finding(
            investigation_id=_uid(investigation_id),
            title=title,
            summary=summary,
            analysis=analysis,
            confidence=confidence,
            finding_type=finding_type,
            classification=classification,
            linked_entities=linked_entities or [],
            linked_objects=linked_objects or [],
            created_by=created_by,
        )
        self.db.add(finding)
        await self.db.flush()

        await self._add_timeline_event(
            _uid(investigation_id), "finding_added",
            f"Finding: {title}", created_by,
        )
        return finding

    async def add_evidence(
        self,
        finding_id: str,
        evidence_type: str,
        source: Optional[str] = None,
        content: Optional[str] = None,
        classification: str = "confidential",
        metadata: Optional[dict] = None,
    ) -> Evidence:
        content_hash = hashlib.sha256((content or "").encode()).hexdigest() if content else None
        evidence = Evidence(
            finding_id=_uid(finding_id),
            evidence_type=evidence_type,
            source=source,
            content=content,
            content_hash=content_hash,
            classification=classification,
            metadata_json=metadata or {},
            collected_at=datetime.utcnow(),
        )
        self.db.add(evidence)
        await self.db.flush()
        return evidence

    # ================================================================
    # GRAPH ANALYSIS
    # ================================================================

    async def analyze_entity_graph(
        self,
        entity_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        depth: int = 2,
    ) -> dict:
        query = select(ThreatEntity)
        if entity_id:
            query = query.where(ThreatEntity.id == _uid(entity_id))
        if workspace_id:
            query = query.where(ThreatEntity.workspace_id == workspace_id)

        result = await self.db.execute(query)
        entities = result.scalars().all()

        if not entities:
            return {"nodes": [], "edges": [], "stats": {"node_count": 0, "edge_count": 0}}

        nodes = []
        edges = []
        edge_set = set()

        for entity in entities:
            nodes.append({
                "id": str(entity.id),
                "type": entity.entity_type,
                "name": entity.name,
                "threat_level": entity.threat_level,
                "risk_score": entity.risk_score,
                "aliases": entity.aliases or [],
            })

            for conn in (entity.connections or []):
                target_id = conn.get("entity_id") or conn.get("target_id")
                conn_type = conn.get("type", "related")
                if target_id:
                    edge_key = tuple(sorted([str(entity.id), str(target_id)]))
                    if edge_key not in edge_set:
                        edge_set.add(edge_key)
                        edges.append({
                            "source": str(entity.id),
                            "target": str(target_id),
                            "type": conn_type,
                            "weight": conn.get("weight", 1.0),
                        })

        centrality = self._compute_centrality(nodes, edges)
        clusters = self._detect_clusters(nodes, edges)

        for node in nodes:
            node["centrality"] = centrality.get(node["id"], 0.0)
            node["cluster"] = clusters.get(node["id"], 0)

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "avg_centrality": sum(centrality.values()) / max(len(centrality), 1),
                "cluster_count": max(clusters.values()) + 1 if clusters else 0,
                "highest_risk": max((n["risk_score"] for n in nodes), default=0),
            },
        }

    def _compute_centrality(self, nodes: list, edges: list) -> dict:
        adjacency = defaultdict(set)
        for edge in edges:
            adjacency[edge["source"]].add(edge["target"])
            adjacency[edge["target"]].add(edge["source"])

        centrality = {}
        node_count = len(nodes)
        for node in nodes:
            nid = node["id"]
            degree = len(adjacency.get(nid, set()))
            centrality[nid] = degree / max(node_count - 1, 1)
        return centrality

    def _detect_clusters(self, nodes: list, edges: list) -> dict:
        adjacency = defaultdict(set)
        for edge in edges:
            adjacency[edge["source"]].add(edge["target"])
            adjacency[edge["target"]].add(edge["source"])

        visited = set()
        clusters = {}
        cluster_id = 0

        for node in nodes:
            nid = node["id"]
            if nid in visited:
                continue
            queue = [nid]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                clusters[current] = cluster_id
                for neighbor in adjacency.get(current, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            cluster_id += 1

        return clusters

    # ================================================================
    # THREAT ENTITY MANAGEMENT
    # ================================================================

    async def create_threat_entity(
        self,
        name: str,
        entity_type: str = "person",
        aliases: Optional[list] = None,
        description: Optional[str] = None,
        threat_level: str = "low",
        workspace_id: Optional[str] = None,
        attributes: Optional[dict] = None,
        classification: str = "confidential",
    ) -> ThreatEntity:
        entity = ThreatEntity(
            name=name,
            entity_type=entity_type,
            aliases=aliases or [],
            description=description,
            threat_level=threat_level,
            risk_score=self._threat_level_to_score(threat_level),
            workspace_id=workspace_id,
            attributes=attributes or {},
            classification=classification,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
        )
        self.db.add(entity)
        await self.db.flush()
        return entity

    async def link_entities(self, source_id: str, target_id: str, connection_type: str = "related", weight: float = 1.0) -> bool:
        result = await self.db.execute(select(ThreatEntity).where(ThreatEntity.id == _uid(source_id)))
        source = result.scalar_one_or_none()
        if not source:
            return False

        connections = source.connections or []
        connections.append({
            "entity_id": str(target_id),
            "type": connection_type,
            "weight": weight,
            "created_at": datetime.utcnow().isoformat(),
        })
        source.connections = connections
        await self.db.flush()
        return True

    async def list_threat_entities(
        self,
        workspace_id: Optional[str] = None,
        threat_level: Optional[str] = None,
        entity_type: Optional[str] = None,
        min_risk_score: Optional[float] = None,
        limit: int = 100,
    ) -> list[dict]:
        query = select(ThreatEntity)
        if workspace_id:
            query = query.where(ThreatEntity.workspace_id == workspace_id)
        if threat_level:
            query = query.where(ThreatEntity.threat_level == threat_level)
        if entity_type:
            query = query.where(ThreatEntity.entity_type == entity_type)
        if min_risk_score is not None:
            query = query.where(ThreatEntity.risk_score >= min_risk_score)
        query = query.order_by(desc(ThreatEntity.risk_score)).limit(limit)

        result = await db.execute(query) if False else await self.db.execute(query)
        return [
            {
                "id": str(e.id),
                "name": e.name,
                "entity_type": e.entity_type,
                "threat_level": e.threat_level,
                "risk_score": e.risk_score,
                "aliases": e.aliases,
                "description": e.description,
                "first_seen": e.first_seen.isoformat() if e.first_seen else None,
                "last_seen": e.last_seen.isoformat() if e.last_seen else None,
                "connection_count": len(e.connections or []),
            }
            for e in result.scalars().all()
        ]

    # ================================================================
    # GEOSPATIAL
    # ================================================================

    async def create_geo_event(
        self,
        title: str,
        event_type: str,
        occurred_at: datetime,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        country: Optional[str] = None,
        region: Optional[str] = None,
        severity: str = "moderate",
        description: Optional[str] = None,
        threat_entity_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        investigation_id: Optional[str] = None,
        classification: str = "confidential",
    ) -> GeoEvent:
        event = GeoEvent(
            title=title,
            event_type=event_type,
            occurred_at=occurred_at,
            latitude=latitude,
            longitude=longitude,
            country=country,
            region=region,
            severity=severity,
            description=description,
            threat_entity_id=_uid(threat_entity_id) if threat_entity_id else None,
            workspace_id=workspace_id,
            investigation_id=_uid(investigation_id) if investigation_id else None,
            classification=classification,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_geo_events(
        self,
        workspace_id: Optional[str] = None,
        country: Optional[str] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        days_back: int = 30,
        limit: int = 200,
    ) -> list[dict]:
        since = datetime.utcnow() - timedelta(days=days_back)
        query = select(GeoEvent).where(GeoEvent.occurred_at >= since)
        if workspace_id:
            query = query.where(GeoEvent.workspace_id == workspace_id)
        if country:
            query = query.where(GeoEvent.country == country)
        if event_type:
            query = query.where(GeoEvent.event_type == event_type)
        if severity:
            query = query.where(GeoEvent.severity == severity)
        query = query.order_by(desc(GeoEvent.occurred_at)).limit(limit)

        result = await self.db.execute(query)
        return [
            {
                "id": str(e.id),
                "title": e.title,
                "event_type": e.event_type,
                "severity": e.severity,
                "latitude": e.latitude,
                "longitude": e.longitude,
                "country": e.country,
                "region": e.region,
                "occurred_at": e.occurred_at.isoformat(),
                "threat_entity_id": str(e.threat_entity_id) if e.threat_entity_id else None,
            }
            for e in result.scalars().all()
        ]

    async def get_country_risk(self, country: Optional[str] = None) -> list[dict]:
        query = select(CountryRiskProfile).order_by(desc(CountryRiskProfile.overall_risk_score))
        if country:
            query = query.where(CountryRiskProfile.country == country)
        query = query.limit(50)
        result = await self.db.execute(query)
        return [
            {
                "country": p.country,
                "country_code": p.country_code,
                "overall_risk_score": p.overall_risk_score,
                "political_risk": p.political_risk,
                "security_risk": p.security_risk,
                "health_risk": p.health_risk,
                "infrastructure_risk": p.infrastructure_risk,
                "natural_disaster_risk": p.natural_disaster_risk,
                "travel_advisory_level": p.travel_advisory_level,
            }
            for p in result.scalars().all()
        ]

    async def compute_country_risk_from_events(self) -> dict:
        severity_weights = {"informational": 0.1, "minor": 0.3, "moderate": 0.5, "major": 0.8, "critical": 1.0}
        since = datetime.utcnow() - timedelta(days=90)
        result = await self.db.execute(
            select(GeoEvent.country, GeoEvent.severity, func.count(GeoEvent.id))
            .where(GeoEvent.occurred_at >= since, GeoEvent.country.isnot(None))
            .group_by(GeoEvent.country, GeoEvent.severity)
        )

        country_scores = defaultdict(lambda: {"events": 0, "weighted": 0.0, "severities": defaultdict(int)})
        for country, severity, count in result.all():
            weight = severity_weights.get(severity, 0.5)
            country_scores[country]["events"] += count
            country_scores[country]["weighted"] += weight * count
            country_scores[country]["severities"][severity] += count

        updated = 0
        for country, data in country_scores.items():
            max_possible = data["events"]
            risk_score = min(data["weighted"] / max(max_possible * 0.5, 1), 10.0)

            result2 = await self.db.execute(
                select(CountryRiskProfile).where(CountryRiskProfile.country == country)
            )
            profile = result2.scalar_one_or_none()
            if not profile:
                profile = CountryRiskProfile(
                    country=country,
                    overall_risk_score=round(risk_score, 2),
                    security_risk=round(risk_score, 2),
                    last_updated=datetime.utcnow(),
                    recent_events=data["severities"],
                )
                self.db.add(profile)
            else:
                profile.overall_risk_score = round(risk_score, 2)
                profile.security_risk = round(risk_score, 2)
                profile.last_updated = datetime.utcnow()
                profile.recent_events = data["severities"]
            updated += 1

        await self.db.flush()
        return {"countries_computed": updated}

    # ================================================================
    # PATTERN DETECTION / ANOMALY SCORING
    # ================================================================

    async def detect_anomalies(self, workspace_id: Optional[str] = None) -> list[dict]:
        alerts = []

        entity_result = await self.db.execute(
            select(ThreatEntity).where(ThreatEntity.risk_score >= 7.0)
        )
        high_risk_entities = entity_result.scalars().all()
        for entity in high_risk_entities:
            alert = PatternAlert(
                alert_type="high_risk_entity",
                title=f"High-risk entity: {entity.name}",
                description=f"Entity '{entity.name}' ({entity.entity_type}) has risk score {entity.risk_score}",
                severity="critical" if entity.risk_score >= 9.0 else "high",
                confidence=min(entity.risk_score / 10.0, 1.0),
                workspace_id=entity.workspace_id,
                affected_entities=[{"id": str(entity.id), "name": entity.name, "type": entity.entity_type}],
                anomaly_details={"risk_score": entity.risk_score, "threat_level": entity.threat_level},
            )
            self.db.add(alert)
            alerts.append({"type": "high_risk_entity", "entity": entity.name, "score": entity.risk_score})

        since_24h = datetime.utcnow() - timedelta(hours=24)
        geo_result = await self.db.execute(
            select(GeoEvent.country, func.count(GeoEvent.id))
            .where(GeoEvent.occurred_at >= since_24h, GeoEvent.severity.in_(["major", "critical"]))
            .group_by(GeoEvent.country)
        )
        for country, count in geo_result.all():
            if count >= 3:
                alert = PatternAlert(
                    alert_type="event_cluster",
                    title=f"Critical event cluster in {country}",
                    description=f"{count} major/critical events in {country} within 24 hours",
                    severity="high",
                    confidence=min(count / 5.0, 1.0),
                    workspace_id=workspace_id,
                    anomaly_details={"country": country, "event_count": count, "window_hours": 24},
                )
                self.db.add(alert)
                alerts.append({"type": "event_cluster", "country": country, "count": count})

        entity_geo = await self.db.execute(
            select(ThreatEntity, func.count(GeoEvent.id))
            .join(GeoEvent, GeoEvent.threat_entity_id == ThreatEntity.id)
            .where(GeoEvent.occurred_at >= since_24h)
            .group_by(ThreatEntity.id)
            .having(func.count(GeoEvent.id) >= 3)
        )
        for entity, event_count in entity_geo.all():
            alert = PatternAlert(
                alert_type="entity_activity_spike",
                title=f"Activity spike: {entity.name}",
                description=f"Entity '{entity.name}' linked to {event_count} geo events in 24h",
                severity="high",
                confidence=min(event_count / 5.0, 1.0),
                workspace_id=entity.workspace_id,
                affected_entities=[{"id": str(entity.id), "name": entity.name}],
                anomaly_details={"event_count": event_count, "window_hours": 24},
            )
            self.db.add(alert)
            alerts.append({"type": "entity_activity_spike", "entity": entity.name, "events": event_count})

        await self.db.flush()
        return alerts

    async def get_active_alerts(
        self,
        workspace_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = select(PatternAlert).where(PatternAlert.status == "active")
        if workspace_id:
            query = query.where(PatternAlert.workspace_id == workspace_id)
        if severity:
            query = query.where(PatternAlert.severity == severity)
        query = query.order_by(desc(PatternAlert.created_at)).limit(limit)

        result = await self.db.execute(query)
        return [
            {
                "id": str(a.id),
                "alert_type": a.alert_type,
                "title": a.title,
                "description": a.description,
                "severity": a.severity,
                "confidence": a.confidence,
                "affected_entities": a.affected_entities,
                "anomaly_details": a.anomaly_details,
                "created_at": a.created_at.isoformat(),
            }
            for a in result.scalars().all()
        ]

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        result = await self.db.execute(select(PatternAlert).where(PatternAlert.id == _uid(alert_id)))
        alert = result.scalar_one_or_none()
        if not alert:
            return False
        alert.status = "acknowledged"
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = acknowledged_by
        await self.db.flush()
        return True

    # ================================================================
    # DASHBOARD STATS
    # ================================================================

    async def get_dashboard_stats(self, workspace_id: Optional[str] = None) -> dict:
        base = select(func.count(Investigation.id))
        if workspace_id:
            base = base.where(Investigation.workspace_id == workspace_id)

        open_count = (await self.db.execute(base.where(Investigation.status == "open"))).scalar() or 0
        in_progress = (await self.db.execute(base.where(Investigation.status == "in_progress"))).scalar() or 0
        closed_count = (await self.db.execute(base.where(Investigation.status.in_(["closed", "archived"])))).scalar() or 0

        entity_count = (await self.db.execute(
            select(func.count(ThreatEntity.id))
            .where(ThreatEntity.workspace_id == workspace_id if workspace_id else True)
        )).scalar() or 0

        critical_entities = (await self.db.execute(
            select(func.count(ThreatEntity.id))
            .where(ThreatEntity.threat_level.in_(["critical", "imminent"]))
        )).scalar() or 0

        active_alerts = (await self.db.execute(
            select(func.count(PatternAlert.id)).where(PatternAlert.status == "active")
        )).scalar() or 0

        geo_24h = (await self.db.execute(
            select(func.count(GeoEvent.id))
            .where(GeoEvent.occurred_at >= datetime.utcnow() - timedelta(hours=24))
        )).scalar() or 0

        high_risk_countries = await self.get_country_risk()
        top_risk = high_risk_countries[:5] if high_risk_countries else []

        return {
            "investigations": {"open": open_count, "in_progress": in_progress, "closed": closed_count, "total": open_count + in_progress + closed_count},
            "threat_entities": {"total": entity_count, "critical": critical_entities},
            "active_alerts": active_alerts,
            "geo_events_24h": geo_24h,
            "top_risk_countries": top_risk,
        }

    # ================================================================
    # HELPERS
    # ================================================================

    def _threat_level_to_score(self, level: str) -> float:
        return {"low": 2.0, "elevated": 4.0, "high": 6.5, "critical": 8.5, "imminent": 9.5}.get(level, 2.0)

    def _investigation_to_dict(self, inv: Investigation) -> dict:
        return {
            "id": str(inv.id),
            "case_number": inv.case_number,
            "title": inv.title,
            "description": inv.description,
            "classification": inv.classification,
            "status": inv.status,
            "priority": inv.priority,
            "workspace_id": inv.workspace_id,
            "assigned_analysts": inv.assigned_analysts or [],
            "tags": inv.tags or [],
            "created_by": inv.created_by,
            "created_at": inv.created_at.isoformat(),
            "updated_at": inv.updated_at.isoformat(),
            "closed_at": inv.closed_at.isoformat() if inv.closed_at else None,
            "finding_count": len(inv.findings) if inv.findings else 0,
            "timeline_count": len(inv.timeline_events) if inv.timeline_events else 0,
        }

    async def _add_timeline_event(
        self,
        investigation_id: str,
        event_type: str,
        description: str,
        created_by: Optional[str] = None,
    ):
        event = TimelineEvent(
            investigation_id=_uid(investigation_id),
            title=description[:200],
            description=description,
            event_type=event_type,
            occurred_at=datetime.utcnow(),
            created_by=created_by,
        )
        self.db.add(event)
        await self.db.flush()
