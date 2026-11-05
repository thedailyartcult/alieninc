"""
Panteon Ontology — Semantic Layer
Maps raw ingested entities to real-world business concepts.
Enriches entities with risk scores, business context, and cross-company relationships.

This is Layer 2 of the Palantir-like architecture:
  Raw entities → business concepts → risk scoring → cross-company graph
"""

import json
import os
import sys
import re
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db'))
from schema import get_connection, DB_PATH

ENTITY_BUSINESS_CONTEXT = {
    "cloud_service": {
        "category": "infrastructure",
        "risk_indicators": ["cost_spike", "unusual_usage", "deprecated_service"],
        "business_translation": "Cloud infrastructure dependency",
    },
    "cloud_account": {
        "category": "infrastructure",
        "risk_indicators": ["shared_credentials", "no_mfa", "excess_permissions"],
        "business_translation": "Cloud infrastructure account",
    },
    "code_repository": {
        "category": "intellectual_property",
        "risk_indicators": ["public_exposure", "no_branch_protection", "stale_dependencies"],
        "business_translation": "Software intellectual property",
    },
    "developer": {
        "category": "human_capital",
        "risk_indicators": ["single_point_of_failure", "no_backup", "excess_access"],
        "business_translation": "Engineering team member",
    },
    "code_asset": {
        "category": "intellectual_property",
        "risk_indicators": ["sensitive_data", "no_tests", "deprecated_library"],
        "business_translation": "Software code asset",
    },
    "work_item": {
        "category": "operations",
        "risk_indicators": ["overdue", "blocked", "scope_creep"],
        "business_translation": "Operational work item",
    },
    "team_member": {
        "category": "human_capital",
        "risk_indicators": ["flight_risk", "overallocated", "single_skill"],
        "business_translation": "Organization team member",
    },
    "financial_metric": {
        "category": "financial",
        "risk_indicators": ["budget_overrun", "unusual_spend", "trend_reversal"],
        "business_translation": "Financial performance metric",
    },
    "financial_account": {
        "category": "financial",
        "risk_indicators": ["reconciliation_gap", "unauthorized_access", "dormant"],
        "business_translation": "Financial account",
    },
    "server": {
        "category": "infrastructure",
        "risk_indicators": ["unpatched", "public_facing", "critical_role"],
        "business_translation": "Production server",
    },
    "network_address": {
        "category": "infrastructure",
        "risk_indicators": ["known_malicious", "tor_exit", "unusual_geo"],
        "business_translation": "Network endpoint",
    },
    "security_alert": {
        "category": "security",
        "risk_indicators": ["high_severity", "repeated", "lateral_movement"],
        "business_translation": "Security incident",
    },
    "system_user": {
        "category": "identity",
        "risk_indicators": ["privilege_escalation", "dormant_account", "shared_credentials"],
        "business_translation": "System identity",
    },
    "running_process": {
        "category": "infrastructure",
        "risk_indicators": ["unknown_binary", "high_resource", "network_callback"],
        "business_translation": "Running system process",
    },
    "business_client": {
        "category": "revenue",
        "risk_indicators": ["concentration_risk", "churn_signal", "payment_delay"],
        "business_translation": "Revenue-generating client",
    },
    "person": {
        "category": "human_capital",
        "risk_indicators": ["key_contact", "departure_risk"],
        "business_translation": "Business contact",
    },
    "organizational_unit": {
        "category": "organizational",
        "risk_indicators": ["understaffed", "high_turnover"],
        "business_translation": "Organizational department",
    },
    "job_role": {
        "category": "organizational",
        "risk_indicators": ["critical_role", "hard_to_fill"],
        "business_translation": "Position/role in organization",
    },
    "sprint": {
        "category": "operations",
        "risk_indicators": ["velocity_drop", "carryover_high"],
        "business_translation": "Development sprint cycle",
    },
    "project": {
        "category": "operations",
        "risk_indicators": ["over_budget", "behind_schedule", "scope_change"],
        "business_translation": "Business project",
    },
    "expense_category": {
        "category": "financial",
        "risk_indicators": ["over_budget", "unusual_pattern"],
        "business_translation": "Expense classification",
    },
    "tag": {
        "category": "metadata",
        "risk_indicators": [],
        "business_translation": "Classification label",
    },
    "code_branch": {
        "category": "intellectual_property",
        "risk_indicators": ["long_lived", "conflict_risk"],
        "business_translation": "Development branch",
    },
    "network_port": {
        "category": "infrastructure",
        "risk_indicators": ["unusual_port", "known_vulnerable"],
        "business_translation": "Network service port",
    },
    "communication_channel": {
        "category": "operations",
        "risk_indicators": [],
        "business_translation": "Client interaction record",
    },
}


RISK_PATTERNS = {
    "single_point_of_failure": {
        "condition": "entity_type == 'developer' AND outgoing_relationships <= 1",
        "severity": "high",
        "description": "Single developer with sole repository access",
    },
    "cost_spike": {
        "condition": "entity_type == 'cloud_service' AND properties.cost > 2x historical_average",
        "severity": "high",
        "description": "Cloud service cost spike detected",
    },
    "unpatched_server": {
        "condition": "entity_type == 'server' AND no recent security alert resolution",
        "severity": "critical",
        "description": "Server may be unpatched",
    },
    "client_concentration": {
        "condition": "entity_type == 'business_client' AND company has < 5 active clients",
        "severity": "medium",
        "description": "Revenue concentration risk",
    },
    "overdue_work": {
        "condition": "entity_type == 'work_item' AND properties.status == 'overdue'",
        "severity": "medium",
        "description": "Work item overdue",
    },
    "excess_permissions": {
        "condition": "entity_type == 'system_user' AND multiple high-privilege relationships",
        "severity": "high",
        "description": "Excessive system permissions",
    },
}


def enrich_entities(limit=200):
    conn = get_connection()
    try:
        entities = conn.execute("""
            SELECT * FROM ontology_entities
            ORDER BY updated_at DESC LIMIT ?
        """, (limit,)).fetchall()

        enriched = 0
        now = datetime.now(timezone.utc).isoformat()

        for entity in entities:
            context = ENTITY_BUSINESS_CONTEXT.get(entity["entity_type"])
            if not context:
                continue

            props = json.loads(entity["properties"]) if entity["properties"] else {}

            if "business_context" not in props:
                props["business_context"] = context["business_translation"]
                props["category"] = context["category"]

            risk_score = _calculate_entity_risk(entity, props, context)
            if abs(risk_score - (entity["risk_score"] or 0)) > 0.5:
                _record_enrichment_history(conn, entity, now)
                conn.execute(
                    "UPDATE ontology_entities SET properties = ?, risk_score = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(props), risk_score, now, entity["id"])
                )
                enriched += 1

        conn.commit()
        return {"enriched": enriched, "total": len(entities)}
    finally:
        conn.close()


def _record_enrichment_history(conn, entity, changed_at):
    conn.execute("""
        INSERT INTO ontology_entity_history (entity_id, entity_type, entity_name, company_id, properties, risk_score, changed_at, change_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'enrichment')
    """, (entity["id"], entity["entity_type"], entity["entity_name"], entity["company_id"], entity["properties"], entity["risk_score"] or 0, changed_at))


def _calculate_entity_risk(entity, props, context):
    score = 0

    if entity["entity_type"] == "security_alert":
        severity = props.get("severity", "medium")
        sev = severity.lower()
        if sev == "critical":
            score += 40
        elif sev == "high":
            score += 25
        elif sev == "medium":
            score += 10
        else:
            score += 5

    if entity["entity_type"] == "cloud_service":
        cost = props.get("cost", 0)
        if cost > 10000:
            score += 15
        elif cost > 5000:
            score += 10
        elif cost > 1000:
            score += 5

    if entity["entity_type"] == "financial_metric":
        amount = abs(props.get("amount", 0))
        direction = props.get("direction", "")
        if direction == "expense" and amount > 50000:
            score += 20
        elif direction == "expense" and amount > 20000:
            score += 10

    if entity["entity_type"] in ("developer", "team_member"):
        score += 5

    if entity["entity_type"] == "server":
        score += 10

    if entity["entity_type"] == "business_client":
        score += 15

    return min(100, score)


def detect_cross_company_relationships():
    conn = get_connection()
    try:
        entities_by_name = {}
        rows = conn.execute("SELECT * FROM ontology_entities ORDER BY entity_name").fetchall()
        for r in rows:
            key = (r["entity_type"], r["entity_name"])
            if key not in entities_by_name:
                entities_by_name[key] = []
            entities_by_name[key].append(r)

        cross_links = 0
        now = datetime.now(timezone.utc).isoformat()

        for key, entity_list in entities_by_name.items():
            if len(entity_list) < 2:
                continue

            companies = set(e["company_id"] for e in entity_list)
            if len(companies) < 2:
                continue

            for i in range(len(entity_list)):
                for j in range(i + 1, len(entity_list)):
                    if entity_list[i]["company_id"] != entity_list[j]["company_id"]:
                        existing = conn.execute("""
                            SELECT id FROM ontology_relationships
                            WHERE from_entity_id = ? AND to_entity_id = ? AND relationship_type = 'shared_across_companies'
                        """, (entity_list[i]["id"], entity_list[j]["id"])).fetchone()

                        if not existing:
                            conn.execute("""
                                INSERT INTO ontology_relationships
                                (from_entity_id, to_entity_id, relationship_type, properties, created_at)
                                VALUES (?, ?, 'shared_across_companies', ?, ?)
                            """, (
                                entity_list[i]["id"],
                                entity_list[j]["id"],
                                json.dumps({"entity_type": key[0], "entity_name": key[1], "companies": list(companies)}),
                                now,
                            ))
                            cross_links += 1

        conn.commit()
        return {"cross_links_created": cross_links}
    finally:
        conn.close()


def detect_risk_patterns():
    conn = get_connection()
    try:
        alerts = []

        developer_repos = conn.execute("""
            SELECT oe.company_id, oe.entity_name as developer,
                   COUNT(DISTINCT orel.to_entity_id) as repo_count
            FROM ontology_entities oe
            JOIN ontology_relationships orel ON oe.id = orel.from_entity_id
            WHERE oe.entity_type = 'developer' AND orel.relationship_type = 'contributes_to'
            GROUP BY oe.id
            HAVING repo_count <= 1
        """).fetchall()

        for dr in developer_repos:
            alerts.append({
                "pattern": "single_point_of_failure",
                "severity": "high",
                "company_id": dr["company_id"],
                "entity": dr["developer"],
                "description": "Developer '%s' at %s has sole repository access — single point of failure" % (dr["developer"], dr["company_id"]),
            })

        high_cost_services = conn.execute("""
            SELECT oe.company_id, oe.entity_name, oe.properties
            FROM ontology_entities oe
            WHERE oe.entity_type = 'cloud_service' AND oe.risk_score >= 15
        """).fetchall()

        for hcs in high_cost_services:
            props = json.loads(hcs["properties"]) if hcs["properties"] else {}
            alerts.append({
                "pattern": "cost_spike",
                "severity": "high" if props.get("cost", 0) > 5000 else "medium",
                "company_id": hcs["company_id"],
                "entity": hcs["entity_name"],
                "description": "Cloud service '%s' at %s flagged for cost monitoring ($%s)" % (
                    hcs["entity_name"], hcs["company_id"], "{:,.0f}".format(props.get("cost", 0))
                ),
            })

        critical_alerts = conn.execute("""
            SELECT oe.company_id, oe.entity_name, oe.properties, oe.risk_score
            FROM ontology_entities oe
            WHERE oe.entity_type = 'security_alert' AND oe.risk_score >= 25
        """).fetchall()

        for ca in critical_alerts:
            props = json.loads(ca["properties"]) if ca["properties"] else {}
            alerts.append({
                "pattern": "security_incident",
                "severity": "critical" if ca["risk_score"] >= 40 else "high",
                "company_id": ca["company_id"],
                "entity": ca["entity_name"],
                "description": "Security incident at %s: %s" % (ca["company_id"], props.get("alert_type", "unknown")),
            })

        return {"patterns_detected": len(alerts), "alerts": alerts}
    finally:
        conn.close()


def get_ontology_graph(company_id=None, entity_type=None, limit=100):
    conn = get_connection()
    try:
        conditions = []
        params = []
        if company_id:
            conditions.append("company_id = ?")
            params.append(company_id)
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        entities = conn.execute("""
            SELECT * FROM ontology_entities%s ORDER BY risk_score DESC LIMIT ?
        """ % where_clause, params + [limit]).fetchall()

        entity_ids = [e["id"] for e in entities]
        if entity_ids:
            placeholders = ",".join("?" * len(entity_ids))
            relationships = conn.execute("""
                SELECT r.*, fe.entity_name as from_name, fe.entity_type as from_type,
                       fe.company_id as from_company, te.entity_name as to_name,
                       te.entity_type as to_type, te.company_id as to_company
                FROM ontology_relationships r
                JOIN ontology_entities fe ON r.from_entity_id = fe.id
                JOIN ontology_entities te ON r.to_entity_id = te.id
                WHERE r.from_entity_id IN (%s) OR r.to_entity_id IN (%s)
                ORDER BY r.created_at DESC LIMIT ?
            """ % (placeholders, placeholders), entity_ids + entity_ids + [limit * 2]).fetchall()
        else:
            relationships = []

        return {
            "entities": [dict(e) for e in entities],
            "relationships": [dict(r) for r in relationships],
            "entity_count": len(entities),
            "relationship_count": len(relationships),
        }
    finally:
        conn.close()


def get_business_summary():
    conn = get_connection()
    try:
        categories = conn.execute("""
            SELECT json_extract(properties, '$.category') as category,
                   COUNT(*) as count,
                   AVG(risk_score) as avg_risk,
                   GROUP_CONCAT(DISTINCT company_id) as companies
            FROM ontology_entities
            WHERE properties IS NOT NULL AND properties != '' AND properties != '{}'
              AND json_valid(properties)
            GROUP BY category
            ORDER BY count DESC
        """).fetchall()

        top_risk = conn.execute("""
            SELECT * FROM ontology_entities
            WHERE risk_score > 0
            ORDER BY risk_score DESC LIMIT 20
        """).fetchall()

        cross_company = conn.execute("""
            SELECT COUNT(*) as count FROM ontology_relationships
            WHERE relationship_type = 'shared_across_companies'
        """).fetchone()

        return {
            "categories": [dict(c) for c in categories],
            "top_risk_entities": [dict(e) for e in top_risk],
            "cross_company_links": cross_company["count"] if cross_company else 0,
        }
    finally:
        conn.close()
