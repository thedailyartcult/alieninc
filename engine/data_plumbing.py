"""
Panteon Data Plumbing — Unified Ingestion Pipeline
Ingests chaotic, unstructured data from subsidiary systems and normalizes
it into a standardized format for the ontology layer.

This is Layer 1 of the Palantir-like architecture:
  Raw subsidiary data → standardize → store → feed ontology layer
"""

import json
import os
import sys
import re
import hashlib
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db'))
from schema import get_connection, DB_PATH

log = logging.getLogger('panteon.data_plumbing')

DATA_TYPES = {
    "aws_bill": {
        "parser": "_parse_aws_bill",
        "entity_map": {"service": "cloud_service", "account": "cloud_account", "cost": "financial_metric"},
    },
    "github_commit": {
        "parser": "_parse_github_commit",
        "entity_map": {"repo": "code_repository", "author": "developer", "branch": "code_branch", "files": "code_asset"},
    },
    "jira_ticket": {
        "parser": "_parse_jira_ticket",
        "entity_map": {"project": "project", "assignee": "team_member", "sprint": "sprint", "label": "tag"},
    },
    "financial_sheet": {
        "parser": "_parse_financial_sheet",
        "entity_map": {"account": "financial_account", "category": "expense_category", "period": "reporting_period"},
    },
    "security_alert": {
        "parser": "_parse_security_alert",
        "entity_map": {"host": "server", "ip": "network_address", "user": "system_user", "process": "running_process"},
    },
    "network_log": {
        "parser": "_parse_network_log",
        "entity_map": {"source_ip": "network_address", "dest_ip": "network_address", "port": "network_port", "protocol": "network_protocol"},
    },
    "hr_record": {
        "parser": "_parse_hr_record",
        "entity_map": {"employee": "team_member", "department": "organizational_unit", "role": "job_role"},
    },
    "client_interaction": {
        "parser": "_parse_client_interaction",
        "entity_map": {"client": "business_client", "contact": "person", "channel": "communication_channel"},
    },
}


def register_source(company_id, source_type, source_name, connection_config=None):
    conn = get_connection()
    try:
        source_id = "%s-%s-%s" % (company_id, source_type, source_name.lower().replace(' ', '-'))
        existing = conn.execute("SELECT id FROM data_sources WHERE id = ?", (source_id,)).fetchone()
        if existing:
            return {"source_id": source_id, "status": "already_registered"}

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO data_sources (id, company_id, source_type, source_name, connection_config, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            source_id, company_id, source_type, source_name,
            json.dumps(connection_config) if connection_config else None,
            now, now,
        ))
        conn.commit()
        return {"source_id": source_id, "status": "registered"}
    finally:
        conn.close()


def ingest_raw(source_id, company_id, data_type, raw_payload):
    if data_type not in DATA_TYPES:
        return {"error": "Unknown data type: %s. Valid types: %s" % (data_type, ", ".join(DATA_TYPES.keys()))}

    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute("""
            INSERT INTO raw_ingested_data (source_id, company_id, data_type, raw_payload, ingested_at)
            VALUES (?, ?, ?, ?, ?)
        """, (source_id, company_id, data_type, json.dumps(raw_payload) if isinstance(raw_payload, (dict, list)) else str(raw_payload), now))

        record_id = cursor.lastrowid

        conn.execute("""
            UPDATE data_sources SET last_ingested_at = ?, records_ingested = records_ingested + 1, updated_at = ?
            WHERE id = ?
        """, (now, now, source_id))

        conn.commit()
        return {"record_id": record_id, "status": "ingested"}
    finally:
        conn.close()


def ingest_batch(source_id, company_id, data_type, records):
    results = []
    for record in records:
        result = ingest_raw(source_id, company_id, data_type, record)
        results.append(result)
    ingested = sum(1 for r in results if r.get("status") == "ingested")
    return {"total": len(records), "ingested": ingested, "results": results}


def process_pending(limit=100):
    conn = get_connection()
    try:
        pending = conn.execute("""
            SELECT * FROM raw_ingested_data WHERE processed = 0
            ORDER BY ingested_at ASC LIMIT ?
        """, (limit,)).fetchall()

        processed = 0
        for record in pending:
            data_type = record["data_type"]
            if data_type not in DATA_TYPES:
                continue

            parser_name = DATA_TYPES[data_type]["parser"]
            parser = globals().get(parser_name)
            if not parser:
                continue

            try:
                raw_payload = record["raw_payload"]
                try:
                    raw = json.loads(raw_payload)
                except (json.JSONDecodeError, TypeError, ValueError):
                    raw = {"raw": raw_payload}
                parsed = parser(raw, record["company_id"])

                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "UPDATE raw_ingested_data SET processed = 1, processed_at = ? WHERE id = ?",
                    (now, record["id"])
                )

                for entity in parsed.get("entities", []):
                    _upsert_entity(conn, entity, record["id"], record["company_id"])

                for rel in parsed.get("relationships", []):
                    _create_relationship(conn, rel, record["company_id"])

                processed += 1
            except Exception as e:
                log.warning("Failed to process record %d: %s", record["id"], e)

        conn.commit()
        return {"processed": processed, "total_pending": len(pending)}
    finally:
        conn.close()


def _upsert_entity(conn, entity, raw_source_id, company_id):
    entity_type = entity.get("type", "unknown")
    entity_name = entity.get("name", "unnamed")
    properties = json.dumps(entity.get("properties", {}))

    existing = conn.execute(
        "SELECT id, properties, risk_score FROM ontology_entities WHERE entity_type = ? AND entity_name = ? AND company_id = ?",
        (entity_type, entity_name, company_id)
    ).fetchone()

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        old_props = json.loads(existing["properties"]) if existing["properties"] else {}
        new_props = json.loads(properties) if properties else {}
        merged = {**old_props, **new_props}
        _record_entity_history(conn, existing["id"], entity_type, entity_name, company_id, existing["properties"], existing["risk_score"], now, "updated")
        conn.execute(
            "UPDATE ontology_entities SET properties = ?, updated_at = ? WHERE id = ?",
            (json.dumps(merged), now, existing["id"])
        )
    else:
        conn.execute("""
            INSERT INTO ontology_entities (entity_type, entity_name, company_id, raw_source_id, properties, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (entity_type, entity_name, company_id, raw_source_id, properties, now, now))


def _record_entity_history(conn, entity_id, entity_type, entity_name, company_id, properties, risk_score, changed_at, reason):
    conn.execute("""
        INSERT INTO ontology_entity_history (entity_id, entity_type, entity_name, company_id, properties, risk_score, changed_at, change_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (entity_id, entity_type, entity_name, company_id, properties, risk_score, changed_at, reason))


def _create_relationship(conn, rel, company_id):
    from_entity = conn.execute(
        "SELECT id FROM ontology_entities WHERE entity_type = ? AND entity_name = ? AND company_id = ?",
        (rel.get("from_type"), rel.get("from_name"), company_id)
    ).fetchone()
    to_entity = conn.execute(
        "SELECT id FROM ontology_entities WHERE entity_type = ? AND entity_name = ? AND company_id = ?",
        (rel.get("to_type"), rel.get("to_name"), company_id)
    ).fetchone()

    if from_entity and to_entity:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO ontology_relationships (from_entity_id, to_entity_id, relationship_type, properties, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            from_entity["id"], to_entity["id"],
            rel.get("type", "related_to"),
            json.dumps(rel.get("properties", {})),
            now,
        ))


def _parse_aws_bill(raw, company_id):
    entities = []
    relationships = []

    service = raw.get("service", raw.get("ServiceName", "unknown-service"))
    cost = raw.get("cost", raw.get("UnblendedCost", raw.get("amount", 0)))
    account = raw.get("account", raw.get("LinkedAccountId", "unknown-account"))
    period = raw.get("period", raw.get("BillingPeriod", "unknown"))

    try:
        cost = float(cost)
    except (ValueError, TypeError):
        cost = 0

    entities.append({
        "type": "cloud_service",
        "name": service,
        "properties": {"cost": cost, "account": account, "period": period, "provider": "aws"},
    })
    entities.append({
        "type": "cloud_account",
        "name": account,
        "properties": {"provider": "aws"},
    })
    entities.append({
        "type": "financial_metric",
        "name": "%s-spend-%s" % (service, period),
        "properties": {"amount": cost, "currency": "USD", "category": "cloud_infrastructure"},
    })

    relationships.append({
        "from_type": "cloud_account", "from_name": account,
        "to_type": "cloud_service", "to_name": service,
        "type": "uses",
    })
    relationships.append({
        "from_type": "cloud_service", "from_name": service,
        "to_type": "financial_metric", "to_name": "%s-spend-%s" % (service, period),
        "type": "generates_cost",
        "properties": {"amount": cost},
    })

    return {"entities": entities, "relationships": relationships}


def _parse_github_commit(raw, company_id):
    entities = []
    relationships = []

    repo = raw.get("repo", raw.get("repository", "unknown-repo"))
    author = raw.get("author", raw.get("committer", "unknown"))
    branch = raw.get("branch", raw.get("ref", "main"))
    message = raw.get("message", raw.get("commit_message", ""))
    sha = raw.get("sha", raw.get("hash", ""))
    files_changed = raw.get("files", raw.get("files_changed", []))
    timestamp = raw.get("timestamp", raw.get("date", ""))

    entities.append({
        "type": "code_repository",
        "name": repo,
        "properties": {"provider": "github"},
    })
    entities.append({
        "type": "developer",
        "name": author,
        "properties": {},
    })
    entities.append({
        "type": "code_branch",
        "name": "%s/%s" % (repo, branch),
        "properties": {"repository": repo},
    })

    if isinstance(files_changed, list):
        for f in files_changed[:10]:
            fname = f if isinstance(f, str) else f.get("filename", f.get("name", "unknown"))
            entities.append({
                "type": "code_asset",
                "name": "%s/%s" % (repo, fname),
                "properties": {"repository": repo, "file": fname},
            })
            relationships.append({
                "from_type": "code_branch", "from_name": "%s/%s" % (repo, branch),
                "to_type": "code_asset", "to_name": "%s/%s" % (repo, fname),
                "type": "modifies",
            })

    relationships.append({
        "from_type": "developer", "from_name": author,
        "to_type": "code_branch", "to_name": "%s/%s" % (repo, branch),
        "type": "committed_to",
        "properties": {"sha": sha[:8] if sha else "", "message": message[:100], "timestamp": timestamp},
    })
    relationships.append({
        "from_type": "developer", "from_name": author,
        "to_type": "code_repository", "to_name": repo,
        "type": "contributes_to",
    })

    return {"entities": entities, "relationships": relationships}


def _parse_jira_ticket(raw, company_id):
    entities = []
    relationships = []

    project = raw.get("project", raw.get("Project", "unknown-project"))
    key = raw.get("key", raw.get("ticket_id", "UNKNOWN-0"))
    summary = raw.get("summary", raw.get("title", raw.get("Summary", "")))
    assignee = raw.get("assignee", raw.get("Assignee", "unassigned"))
    status = raw.get("status", raw.get("Status", "open"))
    priority = raw.get("priority", raw.get("Priority", "medium"))
    sprint = raw.get("sprint", raw.get("Sprint", ""))
    labels = raw.get("labels", raw.get("Labels", []))
    story_points = raw.get("story_points", raw.get("StoryPoints", 0))

    entities.append({
        "type": "project",
        "name": project,
        "properties": {},
    })
    entities.append({
        "type": "work_item",
        "name": key,
        "properties": {
            "summary": summary[:200],
            "status": status,
            "priority": priority,
            "story_points": story_points,
        },
    })
    if assignee and assignee != "unassigned":
        entities.append({
            "type": "team_member",
            "name": assignee,
            "properties": {},
        })
    if sprint:
        entities.append({
            "type": "sprint",
            "name": "%s/%s" % (project, sprint),
            "properties": {"project": project},
        })
    if isinstance(labels, list):
        for label in labels:
            entities.append({
                "type": "tag",
                "name": label,
                "properties": {},
            })

    relationships.append({
        "from_type": "work_item", "from_name": key,
        "to_type": "project", "to_name": project,
        "type": "belongs_to",
    })
    if assignee and assignee != "unassigned":
        relationships.append({
            "from_type": "team_member", "from_name": assignee,
            "to_type": "work_item", "to_name": key,
            "type": "assigned_to",
        })
    if sprint:
        relationships.append({
            "from_type": "work_item", "from_name": key,
            "to_type": "sprint", "to_name": "%s/%s" % (project, sprint),
            "type": "scheduled_in",
        })

    return {"entities": entities, "relationships": relationships}


def _parse_financial_sheet(raw, company_id):
    entities = []
    relationships = []

    account = raw.get("account", raw.get("Account", "unknown"))
    category = raw.get("category", raw.get("Category", "uncategorized"))
    amount = raw.get("amount", raw.get("Amount", 0))
    period = raw.get("period", raw.get("Period", "unknown"))
    description = raw.get("description", raw.get("Description", ""))
    direction = raw.get("direction", raw.get("type", "expense"))

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        amount = 0

    entities.append({
        "type": "financial_account",
        "name": account,
        "properties": {"category": category},
    })
    entities.append({
        "type": "expense_category",
        "name": category,
        "properties": {},
    })
    entities.append({
        "type": "reporting_period",
        "name": period,
        "properties": {"period": period},
    })
    entities.append({
        "type": "financial_metric",
        "name": "%s-%s-%s" % (account, category, period),
        "properties": {
            "amount": amount,
            "currency": raw.get("currency", "USD"),
            "direction": direction,
            "period": period,
            "description": description[:200],
        },
    })

    relationships.append({
        "from_type": "financial_account", "from_name": account,
        "to_type": "expense_category", "to_name": category,
        "type": "categorized_as",
    })
    relationships.append({
        "from_type": "financial_metric",
        "from_name": "%s-%s-%s" % (account, category, period),
        "to_type": "reporting_period", "to_name": period,
        "type": "recorded_in",
    })
    relationships.append({
        "from_type": "financial_account", "from_name": account,
        "to_type": "financial_metric", "to_name": "%s-%s-%s" % (account, category, period),
        "type": "generates",
        "properties": {"amount": amount, "direction": direction},
    })

    return {"entities": entities, "relationships": relationships}


def _parse_security_alert(raw, company_id):
    entities = []
    relationships = []

    alert_type = raw.get("type", raw.get("alert_type", "unknown"))
    severity = raw.get("severity", "medium")
    host = raw.get("host", raw.get("hostname", "unknown"))
    ip = raw.get("ip", raw.get("source_ip", ""))
    user = raw.get("user", raw.get("username", ""))
    process = raw.get("process", raw.get("process_name", ""))
    description = raw.get("description", raw.get("message", ""))
    timestamp = raw.get("timestamp", raw.get("detected_at", ""))

    entities.append({
        "type": "security_alert",
        "name": "%s-%s" % (alert_type, timestamp[:10] if timestamp else "unknown"),
        "properties": {
            "alert_type": alert_type,
            "severity": severity,
            "description": description[:300],
            "timestamp": timestamp,
        },
    })
    if host and host != "unknown":
        entities.append({
            "type": "server",
            "name": host,
            "properties": {},
        })
    if ip:
        entities.append({
            "type": "network_address",
            "name": ip,
            "properties": {"role": "source"},
        })
    if user:
        entities.append({
            "type": "system_user",
            "name": user,
            "properties": {},
        })
    if process:
        entities.append({
            "type": "running_process",
            "name": process,
            "properties": {},
        })

    relationships.append({
        "from_type": "security_alert",
        "from_name": "%s-%s" % (alert_type, timestamp[:10] if timestamp else "unknown"),
        "to_type": "server", "to_name": host,
        "type": "detected_on",
    })
    if ip:
        relationships.append({
            "from_type": "security_alert",
            "from_name": "%s-%s" % (alert_type, timestamp[:10] if timestamp else "unknown"),
            "to_type": "network_address", "to_name": ip,
            "type": "originated_from",
        })
    if user:
        relationships.append({
            "from_type": "system_user", "from_name": user,
            "to_type": "security_alert",
            "to_name": "%s-%s" % (alert_type, timestamp[:10] if timestamp else "unknown"),
            "type": "triggered",
        })

    return {"entities": entities, "relationships": relationships}


def _parse_network_log(raw, company_id):
    entities = []
    relationships = []

    src_ip = raw.get("source_ip", raw.get("src", ""))
    dst_ip = raw.get("dest_ip", raw.get("dst", ""))
    port = raw.get("port", raw.get("dest_port", ""))
    protocol = raw.get("protocol", "unknown")
    action = raw.get("action", raw.get("verdict", "unknown"))
    timestamp = raw.get("timestamp", "")

    if src_ip:
        entities.append({"type": "network_address", "name": src_ip, "properties": {"role": "source"}})
    if dst_ip:
        entities.append({"type": "network_address", "name": dst_ip, "properties": {"role": "destination"}})
    if port:
        entities.append({"type": "network_port", "name": str(port), "properties": {"protocol": protocol}})
    entities.append({
        "type": "network_protocol",
        "name": protocol,
        "properties": {},
    })

    if src_ip and dst_ip:
        relationships.append({
            "from_type": "network_address", "from_name": src_ip,
            "to_type": "network_address", "to_name": dst_ip,
            "type": "communicated_with",
            "properties": {"port": str(port), "protocol": protocol, "action": action, "timestamp": timestamp},
        })

    return {"entities": entities, "relationships": relationships}


def _parse_hr_record(raw, company_id):
    entities = []
    relationships = []

    employee = raw.get("employee", raw.get("name", "unknown"))
    department = raw.get("department", raw.get("Department", "unknown"))
    role = raw.get("role", raw.get("title", raw.get("Title", "unknown")))
    status = raw.get("status", "active")

    entities.append({"type": "team_member", "name": employee, "properties": {"role": role, "status": status}})
    entities.append({"type": "organizational_unit", "name": department, "properties": {}})
    entities.append({"type": "job_role", "name": role, "properties": {}})

    relationships.append({
        "from_type": "team_member", "from_name": employee,
        "to_type": "organizational_unit", "to_name": department,
        "type": "belongs_to",
    })
    relationships.append({
        "from_type": "team_member", "from_name": employee,
        "to_type": "job_role", "to_name": role,
        "type": "holds",
    })

    return {"entities": entities, "relationships": relationships}


def _parse_client_interaction(raw, company_id):
    entities = []
    relationships = []

    client = raw.get("client", raw.get("company", "unknown"))
    contact = raw.get("contact", raw.get("person", ""))
    channel = raw.get("channel", raw.get("type", "unknown"))
    summary = raw.get("summary", raw.get("notes", ""))
    timestamp = raw.get("timestamp", raw.get("date", ""))

    entities.append({"type": "business_client", "name": client, "properties": {}})
    if contact:
        entities.append({"type": "person", "name": contact, "properties": {"client": client}})
    entities.append({
        "type": "communication_channel",
        "name": "%s-%s" % (channel, timestamp[:10] if timestamp else "unknown"),
        "properties": {"channel_type": channel, "summary": summary[:200], "timestamp": timestamp},
    })

    if contact:
        relationships.append({
            "from_type": "person", "from_name": contact,
            "to_type": "business_client", "to_name": client,
            "type": "represents",
        })
    relationships.append({
        "from_type": "business_client", "from_name": client,
        "to_type": "communication_channel",
        "to_name": "%s-%s" % (channel, timestamp[:10] if timestamp else "unknown"),
        "type": "interacted_via",
    })

    return {"entities": entities, "relationships": relationships}


def get_sources():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM data_sources ORDER BY company_id, source_name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_entity_summary():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT entity_type, COUNT(*) as count, COUNT(DISTINCT company_id) as companies
            FROM ontology_entities
            GROUP BY entity_type
            ORDER BY count DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_relationship_summary():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT relationship_type, COUNT(*) as count
            FROM ontology_relationships
            GROUP BY relationship_type
            ORDER BY count DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_entities(query, company_id=None, entity_type=None, limit=50):
    conn = get_connection()
    try:
        sql = "SELECT * FROM ontology_entities WHERE entity_name LIKE ?"
        params = ["%" + query + "%"]
        if company_id:
            sql += " AND company_id = ?"
            params.append(company_id)
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_entity_history(entity_id, limit=50):
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM ontology_entity_history WHERE entity_id = ?
            ORDER BY changed_at DESC LIMIT ?
        """, (entity_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_entity_detail(entity_id):
    conn = get_connection()
    try:
        entity = conn.execute("SELECT * FROM ontology_entities WHERE id = ?", (entity_id,)).fetchone()
        if not entity:
            return {"error": "entity not found"}
        relationships_out = conn.execute("""
            SELECT r.*, te.entity_name as to_name, te.entity_type as to_type, te.company_id as to_company
            FROM ontology_relationships r
            JOIN ontology_entities te ON r.to_entity_id = te.id
            WHERE r.from_entity_id = ?
            ORDER BY r.relationship_type
        """, (entity_id,)).fetchall()
        relationships_in = conn.execute("""
            SELECT r.*, fe.entity_name as from_name, fe.entity_type as from_type, fe.company_id as from_company
            FROM ontology_relationships r
            JOIN ontology_entities fe ON r.from_entity_id = fe.id
            WHERE r.to_entity_id = ?
            ORDER BY r.relationship_type
        """, (entity_id,)).fetchall()
        history = conn.execute("""
            SELECT * FROM ontology_entity_history WHERE entity_id = ?
            ORDER BY changed_at DESC LIMIT 10
        """, (entity_id,)).fetchall()
        return {
            "entity": dict(entity),
            "relationships_out": [dict(r) for r in relationships_out],
            "relationships_in": [dict(r) for r in relationships_in],
            "recent_history": [dict(h) for h in history],
        }
    finally:
        conn.close()


def get_ingestion_stats():
    conn = get_connection()
    try:
        total_raw = conn.execute("SELECT COUNT(*) as c FROM raw_ingested_data").fetchone()["c"]
        pending = conn.execute("SELECT COUNT(*) as c FROM raw_ingested_data WHERE processed = 0").fetchone()["c"]
        processed = conn.execute("SELECT COUNT(*) as c FROM raw_ingested_data WHERE processed = 1").fetchone()["c"]
        total_sources = conn.execute("SELECT COUNT(*) as c FROM data_sources").fetchone()["c"]
        total_entities = conn.execute("SELECT COUNT(*) as c FROM ontology_entities").fetchone()["c"]
        total_relationships = conn.execute("SELECT COUNT(*) as c FROM ontology_relationships").fetchone()["c"]
        recent_ingest = conn.execute("""
            SELECT ingested_at, data_type, company_id FROM raw_ingested_data
            ORDER BY ingested_at DESC LIMIT 10
        """).fetchall()
        by_type = conn.execute("""
            SELECT data_type, COUNT(*) as count FROM raw_ingested_data GROUP BY data_type ORDER BY count DESC
        """).fetchall()
        return {
            "total_raw_records": total_raw,
            "pending_processing": pending,
            "processed": processed,
            "total_sources": total_sources,
            "total_entities": total_entities,
            "total_relationships": total_relationships,
            "recent_ingestions": [dict(r) for r in recent_ingest],
            "by_data_type": [dict(r) for r in by_type],
        }
    finally:
        conn.close()
