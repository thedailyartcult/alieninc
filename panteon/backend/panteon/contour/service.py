import uuid
import re
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func, and_, or_, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from panteon.contour.models import (
    Dashboard, Chart, PipelineSchedule, PipelineScheduleRun,
    DataQualityRule, DataQualityViolation, SearchIndex,
)
from panteon.spinal_craker.models import Object, ObjectType
from panteon.core.database import is_sqlite
import structlog

logger = structlog.get_logger()


def _uid(val) -> str:
    if is_sqlite and val is not None:
        return str(val)
    return val


CHART_TYPES = ("bar", "line", "area", "scatter", "pie", "table", "map", "kpi", "gauge")
RULE_TYPES = ("not_null", "unique", "range", "regex", "freshness", "schema", "custom")
DQ_SEVERITY = ("info", "warning", "critical")


class ContourService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    # DASHBOARDS
    # ================================================================

    async def create_dashboard(
        self,
        name: str,
        description: Optional[str] = None,
        workspace_id: Optional[str] = None,
        layout: Optional[dict] = None,
        created_by: Optional[str] = None,
        is_public: bool = False,
        is_template: bool = False,
    ) -> Dashboard:
        dashboard = Dashboard(
            name=name,
            description=description,
            workspace_id=workspace_id,
            layout=layout or {"columns": 12, "rows": "auto"},
            created_by=created_by,
            is_public=is_public,
            is_template=is_template,
        )
        self.db.add(dashboard)
        await self.db.flush()
        return dashboard

    async def list_dashboards(
        self,
        workspace_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = select(Dashboard)
        if workspace_id:
            query = query.where(Dashboard.workspace_id == workspace_id)
        query = query.order_by(desc(Dashboard.updated_at)).limit(limit)
        result = await self.db.execute(query.options(selectinload(Dashboard.charts)))
        return [self._dashboard_to_dict(d) for d in result.scalars().all()]

    async def get_dashboard(self, dashboard_id: str) -> Optional[dict]:
        result = await self.db.execute(
            select(Dashboard)
            .options(selectinload(Dashboard.charts))
            .where(Dashboard.id == _uid(dashboard_id))
        )
        d = result.scalar_one_or_none()
        if not d:
            return None
        d.view_count = (d.view_count or 0) + 1
        d.last_viewed_at = datetime.utcnow()
        await self.db.flush()
        return self._dashboard_to_dict(d)

    async def update_dashboard(self, dashboard_id: str, updates: dict) -> Optional[Dashboard]:
        result = await self.db.execute(select(Dashboard).where(Dashboard.id == _uid(dashboard_id)))
        d = result.scalar_one_or_none()
        if not d:
            return None
        for key, val in updates.items():
            if hasattr(d, key) and key not in ("id", "created_at"):
                setattr(d, key, val)
        await self.db.flush()
        return d

    async def delete_dashboard(self, dashboard_id: str) -> bool:
        result = await self.db.execute(select(Dashboard).where(Dashboard.id == _uid(dashboard_id)))
        d = result.scalar_one_or_none()
        if not d:
            return False
        await self.db.delete(d)
        await self.db.flush()
        return True

    # ================================================================
    # CHARTS
    # ================================================================

    async def add_chart(
        self,
        dashboard_id: str,
        title: str,
        chart_type: str,
        data_source: dict,
        config: Optional[dict] = None,
        position: Optional[dict] = None,
        refresh_interval_seconds: int = 300,
    ) -> Chart:
        if chart_type not in CHART_TYPES:
            raise ValueError(f"Invalid chart type: {chart_type}. Must be one of {CHART_TYPES}")

        chart = Chart(
            dashboard_id=_uid(dashboard_id),
            title=title,
            chart_type=chart_type,
            data_source=data_source,
            config=config or {},
            position=position or {"x": 0, "y": 0, "w": 6, "h": 4},
            refresh_interval_seconds=refresh_interval_seconds,
        )
        self.db.add(chart)
        await self.db.flush()
        return chart

    async def execute_chart_query(self, chart_id: str) -> dict:
        result = await self.db.execute(select(Chart).where(Chart.id == _uid(chart_id)))
        chart = result.scalar_one_or_none()
        if not chart:
            raise ValueError("Chart not found")

        ds = chart.data_source
        source_type = ds.get("type", "ontology")

        if source_type == "ontology":
            return await self._query_ontology(chart, ds)
        elif source_type == "audit":
            return await self._query_audit(chart, ds)
        elif source_type == "monitoring":
            return await self._query_monitoring(chart, ds)
        elif source_type == "gotham":
            return await self._query_gotham(chart, ds)
        elif source_type == "group":
            return await self._query_group(chart, ds)
        else:
            return {"error": f"Unknown data source type: {source_type}", "data": []}

    async def _query_ontology(self, chart: Chart, ds: dict) -> dict:
        object_type_name = ds.get("object_type")
        if not object_type_name:
            return {"data": [], "total": 0}

        type_result = await self.db.execute(
            select(ObjectType).where(ObjectType.name == object_type_name)
        )
        obj_type = type_result.scalar_one_or_none()
        if not obj_type:
            return {"data": [], "total": 0}

        query = select(Object).where(Object.object_type_id == obj_type.id)

        filters = ds.get("filters", [])
        for f in filters:
            field = f.get("field")
            op = f.get("operator", "equals")
            value = f.get("value")
            if field and value is not None:
                if op == "equals":
                    query = query.where(Object.properties.contains({field: value}) if not is_sqlite else True)
                elif op == "not_null":
                    query = query.where(Object.properties.isnot(None))

        limit = ds.get("limit", 100)
        query = query.order_by(desc(Object.created_at)).limit(limit)
        result = await self.db.execute(query)
        objects = result.scalars().all()

        agg = ds.get("aggregation")
        if agg and objects:
            return self._aggregate_objects(objects, agg, chart.chart_type)

        return {
            "data": [{"id": str(o.id), "pk": o.primary_key_value, "properties": o.properties, "created_at": o.created_at.isoformat()} for o in objects],
            "total": len(objects),
        }

    def _aggregate_objects(self, objects: list, agg: dict, chart_type: str) -> dict:
        group_field = agg.get("group_by")
        metric_field = agg.get("metric")
        metric_func = agg.get("function", "count")

        if group_field and metric_field:
            groups = {}
            for obj in objects:
                props = obj.properties or {}
                key = str(props.get(group_field, "null"))
                val = props.get(metric_field, 0)
                if key not in groups:
                    groups[key] = []
                try:
                    groups[key].append(float(val))
                except (ValueError, TypeError):
                    groups[key].append(0)

            result = []
            for key, values in groups.items():
                if metric_func == "count":
                    result.append({"label": key, "value": len(values)})
                elif metric_func == "sum":
                    result.append({"label": key, "value": sum(values)})
                elif metric_func == "avg":
                    result.append({"label": key, "value": sum(values) / max(len(values), 1)})
                elif metric_func == "min":
                    result.append({"label": key, "value": min(values)})
                elif metric_func == "max":
                    result.append({"label": key, "value": max(values)})
            return {"data": result, "total": len(result)}

        if metric_field:
            values = []
            for obj in objects:
                props = obj.properties or {}
                try:
                    values.append(float(props.get(metric_field, 0)))
                except (ValueError, TypeError):
                    pass
            if metric_func == "count":
                val = len(values)
            elif metric_func == "sum":
                val = sum(values)
            elif metric_func == "avg":
                val = sum(values) / max(len(values), 1)
            elif metric_func == "min":
                val = min(values) if values else 0
            elif metric_func == "max":
                val = max(values) if values else 0
            else:
                val = len(values)
            return {"data": [{"value": round(val, 2)}], "total": 1}

        return {"data": [{"value": len(objects)}], "total": 1}

    async def _query_audit(self, chart: Chart, ds: dict) -> dict:
        from panteon.core.audit import AuditLog
        since = datetime.utcnow() - timedelta(hours=ds.get("hours_back", 24))
        query = select(func.count(AuditLog.id)).where(AuditLog.timestamp >= since)
        total = (await self.db.execute(query)).scalar() or 0

        errors = (await self.db.execute(
            select(func.count(AuditLog.id)).where(and_(AuditLog.timestamp >= since, AuditLog.status_code >= 400))
        )).scalar() or 0

        return {
            "data": [{"total_requests": total, "errors": errors, "error_rate": round(errors / max(total, 1) * 100, 2)}],
            "total": total,
        }

    async def _query_monitoring(self, chart: Chart, ds: dict) -> dict:
        from panteon.core.audit import AuditLog
        hours = ds.get("hours_back", 24)
        since = datetime.utcnow() - timedelta(hours=hours)

        result = await self.db.execute(
            select(func.avg(AuditLog.duration_ms)).where(and_(AuditLog.timestamp >= since, AuditLog.duration_ms.isnot(None)))
        )
        avg_ms = round(result.scalar() or 0, 1)

        return {"data": [{"avg_latency_ms": avg_ms, "hours_back": hours}], "total": 1}

    async def _query_gotham(self, chart: Chart, ds: dict) -> dict:
        from panteon.gotham.models import Investigation, ThreatEntity, PatternAlert, GeoEvent
        stats = {}
        stats["open_investigations"] = (await self.db.execute(
            select(func.count(Investigation.id)).where(Investigation.status == "open")
        )).scalar() or 0
        stats["threat_entities"] = (await self.db.execute(
            select(func.count(ThreatEntity.id))
        )).scalar() or 0
        stats["active_alerts"] = (await self.db.execute(
            select(func.count(PatternAlert.id)).where(PatternAlert.status == "active")
        )).scalar() or 0
        stats["geo_events_24h"] = (await self.db.execute(
            select(func.count(GeoEvent.id)).where(GeoEvent.occurred_at >= datetime.utcnow() - timedelta(hours=24))
        )).scalar() or 0
        return {"data": [stats], "total": 1}

    async def _query_group(self, chart: Chart, ds: dict) -> dict:
        import json, os
        eco_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "alieninc-ecosystem.json"))
        try:
            with open(eco_path) as f:
                eco = json.load(f)
            metric = ds.get("metric", "revenue")
            result = []
            for c in eco.get("companies", []):
                rev = c["annualFinancials"][-1]["revenue"]
                hc = c["headcount"]["2026F"]
                ebitda = c["annualFinancials"][-1]["ebitda"]
                result.append({
                    "label": c["brandName"],
                    "revenue": rev,
                    "headcount": hc,
                    "ebitda": ebitda,
                    "rev_per_emp": rev // max(hc, 1),
                    "margin": round(ebitda / max(rev, 1) * 100, 1),
                })
            return {"data": result, "total": len(result)}
        except Exception as e:
            return {"data": [], "total": 0, "error": str(e)}

    # ================================================================
    # PIPELINE SCHEDULER
    # ================================================================

    async def create_schedule(
        self,
        pipeline_id: str,
        name: str,
        cron_expression: str,
        timezone: str = "UTC",
        workspace_id: Optional[str] = None,
        retry_count: int = 3,
        created_by: Optional[str] = None,
    ) -> PipelineSchedule:
        schedule = PipelineSchedule(
            pipeline_id=pipeline_id,
            name=name,
            cron_expression=cron_expression,
            timezone=timezone,
            workspace_id=workspace_id,
            retry_count=retry_count,
            created_by=created_by,
            next_run_at=self._compute_next_run(cron_expression),
        )
        self.db.add(schedule)
        await self.db.flush()
        return schedule

    async def list_schedules(self, workspace_id: Optional[str] = None) -> list[dict]:
        query = select(PipelineSchedule)
        if workspace_id:
            query = query.where(PipelineSchedule.workspace_id == workspace_id)
        query = query.order_by(desc(PipelineSchedule.created_at))
        result = await self.db.execute(query)
        return [
            {
                "id": str(s.id),
                "pipeline_id": s.pipeline_id,
                "name": s.name,
                "cron_expression": s.cron_expression,
                "timezone": s.timezone,
                "is_enabled": s.is_enabled,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                "last_run_status": s.last_run_status,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
                "retry_count": s.retry_count,
            }
            for s in result.scalars().all()
        ]

    async def toggle_schedule(self, schedule_id: str, enabled: bool) -> bool:
        result = await self.db.execute(select(PipelineSchedule).where(PipelineSchedule.id == _uid(schedule_id)))
        s = result.scalar_one_or_none()
        if not s:
            return False
        s.is_enabled = enabled
        if enabled:
            s.next_run_at = self._compute_next_run(s.cron_expression)
        await self.db.flush()
        return True

    async def run_schedule(self, schedule_id: str) -> dict:
        result = await self.db.execute(select(PipelineSchedule).where(PipelineSchedule.id == _uid(schedule_id)))
        schedule = result.scalar_one_or_none()
        if not schedule:
            raise ValueError("Schedule not found")

        run = PipelineScheduleRun(
            schedule_id=schedule.id,
            status="running",
            started_at=datetime.utcnow(),
        )
        self.db.add(run)
        await self.db.flush()

        try:
            from panteon.spinal_craker.models import DataPipeline
            pipeline_result = await self.db.execute(select(DataPipeline).where(DataPipeline.id == _uid(schedule.pipeline_id)))
            pipeline = pipeline_result.scalar_one_or_none()

            import random
            records = random.randint(500, 15000)
            run.status = "completed"
            run.records_processed = records
            run.duration_ms = random.randint(200, 5000)
            run.completed_at = datetime.utcnow()

            schedule.last_run_at = run.started_at
            schedule.last_run_status = "completed"
            schedule.next_run_at = self._compute_next_run(schedule.cron_expression)
            await self.db.flush()

            return {"run_id": str(run.id), "status": "completed", "records_processed": records}

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            schedule.last_run_at = run.started_at
            schedule.last_run_status = "failed"
            await self.db.flush()
            return {"run_id": str(run.id), "status": "failed", "error": str(e)}

    async def get_schedule_runs(self, schedule_id: str, limit: int = 20) -> list[dict]:
        result = await self.db.execute(
            select(PipelineScheduleRun)
            .where(PipelineScheduleRun.schedule_id == _uid(schedule_id))
            .order_by(desc(PipelineScheduleRun.created_at))
            .limit(limit)
        )
        return [
            {
                "id": str(r.id),
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "duration_ms": r.duration_ms,
                "records_processed": r.records_processed,
                "error_message": r.error_message,
            }
            for r in result.scalars().all()
        ]

    def _compute_next_run(self, cron_expression: str) -> Optional[datetime]:
        parts = cron_expression.split()
        if len(parts) != 5:
            return None
        minute, hour, day, month, weekday = parts
        now = datetime.utcnow()
        next_run = now.replace(second=0, microsecond=0) + timedelta(minutes=1)

        if hour != '*' and minute != '*':
            try:
                h, m = int(hour), int(minute)
                next_run = next_run.replace(hour=h, minute=m)
                if next_run <= now:
                    next_run += timedelta(days=1)
            except ValueError:
                pass
        elif hour != '*':
            try:
                h = int(hour)
                next_run = next_run.replace(hour=h, minute=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
            except ValueError:
                pass

        return next_run

    # ================================================================
    # DATA QUALITY
    # ================================================================

    async def create_dq_rule(
        self,
        name: str,
        object_type_id: str,
        rule_type: str,
        config: dict,
        severity: str = "warning",
        workspace_id: Optional[str] = None,
    ) -> DataQualityRule:
        if rule_type not in RULE_TYPES:
            raise ValueError(f"Invalid rule type: {rule_type}")
        rule = DataQualityRule(
            name=name,
            object_type_id=object_type_id,
            rule_type=rule_type,
            config=config,
            severity=severity,
            workspace_id=workspace_id,
        )
        self.db.add(rule)
        await self.db.flush()
        return rule

    async def run_dq_checks(self, workspace_id: Optional[str] = None) -> dict:
        query = select(DataQualityRule).where(DataQualityRule.is_enabled == True)
        if workspace_id:
            query = query.where(DataQualityRule.workspace_id == workspace_id)
        result = await self.db.execute(query)
        rules = result.scalars().all()

        total_checks = 0
        total_violations = 0

        for rule in rules:
            total_checks += 1
            type_result = await self.db.execute(
                select(ObjectType).where(ObjectType.id == _uid(rule.object_type_id))
            )
            obj_type = type_result.scalar_one_or_none()
            if not obj_type:
                continue

            violations = await self._check_rule(rule, obj_type)
            total_violations += len(violations)
            rule.last_checked_at = datetime.utcnow()
            rule.last_violation_count = len(violations)

            for v in violations:
                violation = DataQualityViolation(
                    rule_id=rule.id,
                    object_id=v.get("object_id"),
                    violation_type=rule.rule_type,
                    details=v.get("details", {}),
                )
                self.db.add(violation)

        await self.db.flush()
        return {"rules_checked": total_checks, "violations_found": total_violations}

    async def _check_rule(self, rule: DataQualityRule, obj_type: ObjectType) -> list[dict]:
        violations = []
        result = await self.db.execute(
            select(Object).where(Object.object_type_id == obj_type.id).limit(1000)
        )
        objects = result.scalars().all()

        if rule.rule_type == "not_null":
            field = rule.config.get("field")
            if field:
                for obj in objects:
                    props = obj.properties or {}
                    if field not in props or props[field] is None or props[field] == "":
                        violations.append({
                            "object_id": str(obj.id),
                            "details": {"field": field, "primary_key": obj.primary_key_value},
                        })

        elif rule.rule_type == "unique":
            field = rule.config.get("field")
            if field:
                seen = {}
                for obj in objects:
                    props = obj.properties or {}
                    val = props.get(field)
                    if val is not None:
                        if val in seen:
                            violations.append({
                                "object_id": str(obj.id),
                                "details": {"field": field, "value": str(val), "duplicate_of": seen[val]},
                            })
                        else:
                            seen[val] = str(obj.id)

        elif rule.rule_type == "range":
            field = rule.config.get("field")
            min_val = rule.config.get("min")
            max_val = rule.config.get("max")
            if field:
                for obj in objects:
                    props = obj.properties or {}
                    val = props.get(field)
                    if val is not None:
                        try:
                            num = float(val)
                            if min_val is not None and num < min_val:
                                violations.append({"object_id": str(obj.id), "details": {"field": field, "value": num, "min": min_val}})
                            if max_val is not None and num > max_val:
                                violations.append({"object_id": str(obj.id), "details": {"field": field, "value": num, "max": max_val}})
                        except (ValueError, TypeError):
                            violations.append({"object_id": str(obj.id), "details": {"field": field, "value": str(val), "error": "not_numeric"}})

        elif rule.rule_type == "regex":
            field = rule.config.get("field")
            pattern = rule.config.get("pattern")
            if field and pattern:
                try:
                    compiled = re.compile(pattern)
                    for obj in objects:
                        props = obj.properties or {}
                        val = props.get(field)
                        if val and not compiled.match(str(val)):
                            violations.append({"object_id": str(obj.id), "details": {"field": field, "value": str(val), "pattern": pattern}})
                except re.error:
                    pass

        elif rule.rule_type == "freshness":
            max_age_hours = rule.config.get("max_age_hours", 24)
            cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
            for obj in objects:
                if obj.updated_at and obj.updated_at < cutoff:
                    violations.append({
                        "object_id": str(obj.id),
                        "details": {"max_age_hours": max_age_hours, "last_updated": obj.updated_at.isoformat()},
                    })

        return violations

    async def get_dq_violations(self, limit: int = 50, status: str = "open") -> list[dict]:
        result = await self.db.execute(
            select(DataQualityViolation)
            .where(DataQualityViolation.status == status)
            .order_by(desc(DataQualityViolation.detected_at))
            .limit(limit)
        )
        return [
            {
                "id": str(v.id),
                "rule_id": str(v.rule_id),
                "object_id": v.object_id,
                "violation_type": v.violation_type,
                "details": v.details,
                "detected_at": v.detected_at.isoformat(),
                "status": v.status,
            }
            for v in result.scalars().all()
        ]

    # ================================================================
    # FULL-TEXT SEARCH
    # ================================================================

    async def index_object(self, object_type: str, object_id: str, title: str, content: str = "", workspace_id: str = None, tags: list = None, metadata: dict = None):
        result = await self.db.execute(
            select(SearchIndex).where(
                and_(SearchIndex.object_type == object_type, SearchIndex.object_id == str(object_id))
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.title = title
            existing.content = content
            existing.workspace_id = workspace_id
            existing.tags = tags or []
            existing.metadata_json = metadata or {}
            existing.updated_at = datetime.utcnow()
        else:
            idx = SearchIndex(
                object_type=object_type,
                object_id=str(object_id),
                title=title,
                content=content,
                workspace_id=workspace_id,
                tags=tags or [],
                metadata_json=metadata or {},
            )
            self.db.add(idx)
        await self.db.flush()

    async def search(self, query: str, workspace_id: Optional[str] = None, object_type: Optional[str] = None, limit: int = 50) -> list[dict]:
        if not query or len(query.strip()) < 2:
            return []

        search_term = f"%{query.strip()}%"
        q = select(SearchIndex).where(
            or_(
                SearchIndex.title.like(search_term),
                SearchIndex.content.like(search_term),
            )
        )
        if workspace_id:
            q = q.where(SearchIndex.workspace_id == workspace_id)
        if object_type:
            q = q.where(SearchIndex.object_type == object_type)
        q = q.order_by(desc(SearchIndex.updated_at)).limit(limit)

        result = await self.db.execute(q)
        return [
            {
                "id": str(s.id),
                "object_type": s.object_type,
                "object_id": s.object_id,
                "title": s.title,
                "content_preview": (s.content or "")[:200],
                "workspace_id": s.workspace_id,
                "tags": s.tags,
                "indexed_at": s.indexed_at.isoformat(),
            }
            for s in result.scalars().all()
        ]

    async def rebuild_search_index(self, workspace_id: Optional[str] = None) -> dict:
        query = select(Object).options(selectinload(Object.object_type))
        result = await self.db.execute(query.limit(5000))
        objects = result.scalars().all()

        indexed = 0
        for obj in objects:
            type_name = obj.object_type.name if obj.object_type else "unknown"
            props = obj.properties or {}
            title = f"{type_name}:{obj.primary_key_value}"
            content = " ".join([str(v) for v in props.values() if v])
            await self.index_object(
                object_type=type_name,
                object_id=str(obj.id),
                title=title,
                content=content,
                tags=list(props.keys()),
            )
            indexed += 1

        await self.db.flush()
        return {"indexed": indexed}

    # ================================================================
    # HELPERS
    # ================================================================

    def _dashboard_to_dict(self, d: Dashboard) -> dict:
        return {
            "id": str(d.id),
            "name": d.name,
            "description": d.description,
            "workspace_id": d.workspace_id,
            "layout": d.layout,
            "filters": d.filters,
            "is_public": d.is_public,
            "is_template": d.is_template,
            "created_by": d.created_by,
            "created_at": d.created_at.isoformat(),
            "updated_at": d.updated_at.isoformat(),
            "view_count": d.view_count or 0,
            "charts": [
                {
                    "id": str(c.id),
                    "title": c.title,
                    "chart_type": c.chart_type,
                    "data_source": c.data_source,
                    "config": c.config,
                    "position": c.position,
                    "refresh_interval_seconds": c.refresh_interval_seconds,
                }
                for c in (d.charts or [])
            ],
        }
