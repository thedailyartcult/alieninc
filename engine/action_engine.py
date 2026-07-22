"""
Panteon Action Engine — Automated Intelligence Platform (AIP)
Auto-triggers actions across companies based on detected patterns,
risk conditions, and ontology relationships.

This is Layer 3 of the Palantir-like architecture:
  Risk patterns → evaluate rules → trigger actions → log results
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db'))
from schema import get_connection, DB_PATH

DEFAULT_RULES = [
    {
        "id": "panteon-critical-security-response",
        "name": "Critical Security Alert Response",
        "description": "When a critical security alert is detected at any subsidiary, auto-notify Panteon SOC and raise company risk score.",
        "trigger_condition": "ontology_entities.entity_type = 'security_alert' AND ontology_entities.risk_score >= 40",
        "action_type": "notify_and_escalate",
        "action_config": json.dumps({
            "notify": ["panteon"],
            "escalation_level": "critical",
            "message_template": "CRITICAL: Security incident detected at {company_id}. Alert: {entity_name}. Immediate SOC review required.",
        }),
        "severity": "critical",
    },
    {
        "id": "panteon-cost-spike-alert",
        "name": "Cloud Cost Spike Alert",
        "description": "When cloud service costs spike above threshold, notify Rousseau finance and the affected company.",
        "trigger_condition": "ontology_entities.entity_type = 'cloud_service' AND ontology_entities.risk_score >= 15",
        "action_type": "notify",
        "action_config": json.dumps({
            "notify": ["rousseau", "{company_id}"],
            "message_template": "Cloud cost alert at {company_id}: {entity_name} flagged for cost monitoring. Review AWS/GCP billing.",
        }),
        "severity": "high",
    },
    {
        "id": "panteon-spoF-warning",
        "name": "Single Point of Failure Warning",
        "description": "When a developer has sole repository access, warn about bus factor risk.",
        "trigger_condition": "ontology_entities.entity_type = 'developer' AND risk_pattern = 'single_point_of_failure'",
        "action_type": "notify",
        "action_config": json.dumps({
            "notify": ["{company_id}"],
            "message_template": "Bus factor risk at {company_id}: Developer '{entity}' has sole repository access. Recommend knowledge transfer and backup assignment.",
        }),
        "severity": "high",
    },
    {
        "id": "panteon-client-concentration",
        "name": "Client Revenue Concentration Alert",
        "description": "When a subsidiary has high revenue dependency on a single client, alert Rousseau and KMT.",
        "trigger_condition": "ontology_entities.entity_type = 'business_client' AND ontology_entities.risk_score >= 15",
        "action_type": "notify",
        "action_config": json.dumps({
            "notify": ["rousseau", "kmt"],
            "message_template": "Revenue concentration risk: {company_id} has significant dependency on client '{entity}'. Recommend diversification strategy.",
        }),
        "severity": "medium",
    },
    {
        "id": "panteon-cross-company-threat",
        "name": "Cross-Company Threat Correlation",
        "description": "When the same threat indicator appears at multiple subsidiaries, escalate to group-wide response.",
        "trigger_condition": "ontology_relationships.relationship_type = 'shared_across_companies' AND from_entity_type IN ('security_alert', 'network_address')",
        "action_type": "escalate",
        "action_config": json.dumps({
            "notify": ["panteon", "rousseau"],
            "escalation_level": "high",
            "message_template": "Cross-company threat detected: {entity_name} appears across multiple subsidiaries. Coordinated response required.",
        }),
        "severity": "high",
    },
    {
        "id": "panteon-financial-anomaly",
        "name": "Financial Anomaly Detection",
        "description": "When unusual financial patterns detected, notify Rousseau and Statute & Precedent.",
        "trigger_condition": "ontology_entities.entity_type = 'financial_metric' AND ontology_entities.risk_score >= 20",
        "action_type": "notify",
        "action_config": json.dumps({
            "notify": ["rousseau", "statute"],
            "message_template": "Financial anomaly at {company_id}: {entity_name} flagged. Amount: {amount}. Review recommended.",
        }),
        "severity": "medium",
    },
    {
        "id": "panteon-deployment-policy",
        "name": "Security Policy Deployment",
        "description": "When a new security policy is approved, deploy to all subsidiary servers simultaneously.",
        "trigger_condition": "manual_trigger",
        "action_type": "deploy_policy",
        "action_config": json.dumps({
            "targets": "all_subsidiaries",
            "policy_type": "security_baseline",
            "message_template": "Security policy update deployed to all subsidiaries. Policy: {policy_name}. Effective: {effective_date}.",
        }),
        "severity": "high",
    },
    {
        "id": "panteon-covenant-monitor",
        "name": "Debt Covenant Monitor",
        "description": "When fund centre NAV approaches covenant threshold, alert Rousseau and Statute immediately.",
        "trigger_condition": "risk_metrics.covenant_headroom_pct < 20",
        "action_type": "escalate",
        "action_config": json.dumps({
            "notify": ["rousseau", "statute"],
            "escalation_level": "critical",
            "message_template": "COVENANT WARNING: Fund centre NAV headroom at {headroom_pct}%. Threshold breach at 0%. Immediate treasurer review required.",
        }),
        "severity": "critical",
    },
]


def initialize_rules():
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM action_rules").fetchall()
        existing_ids = set(r["id"] for r in existing)

        created = 0
        now = datetime.now(timezone.utc).isoformat()
        for rule in DEFAULT_RULES:
            if rule["id"] not in existing_ids:
                conn.execute("""
                    INSERT INTO action_rules
                    (id, name, description, trigger_condition, action_type, action_config,
                     severity, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """, (
                    rule["id"], rule["name"], rule.get("description", ""),
                    rule["trigger_condition"], rule["action_type"],
                    rule["action_config"], rule.get("severity", "medium"),
                    now, now,
                ))
                created += 1

        conn.commit()
        return {"created": created, "total": len(DEFAULT_RULES)}
    finally:
        conn.close()


def evaluate_rules(alerts=None):
    conn = get_connection()
    try:
        rules = conn.execute("SELECT * FROM action_rules WHERE enabled = 1").fetchall()
        executions = []
        now = datetime.now(timezone.utc).isoformat()

        for rule in rules:
            if rule["trigger_condition"] == "manual_trigger":
                continue

            triggered = _evaluate_condition(conn, rule["trigger_condition"], alerts)
            if not triggered:
                continue

            action_config = json.loads(rule["action_config"]) if rule["action_config"] else {}
            result = _execute_action(rule, action_config, triggered, now, conn)

            conn.execute("""
                INSERT INTO action_executions
                (rule_id, trigger_event, trigger_data, action_taken, target_company_ids, status, result, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule["id"],
                json.dumps([t.get("entity_name", "") for t in triggered[:3]]),
                json.dumps(triggered[0]) if triggered else None,
                rule["action_type"],
                json.dumps(action_config.get("notify", [])),
                result.get("status", "executed"),
                json.dumps(result),
                now,
            ))

            conn.execute(
                "UPDATE action_rules SET execution_count = execution_count + 1, last_executed = ?, updated_at = ? WHERE id = ?",
                (now, now, rule["id"])
            )

            executions.append({
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "action_type": rule["action_type"],
                "triggered_by": len(triggered),
                "result": result,
            })

        conn.commit()
        return {"executions": len(executions), "details": executions}
    finally:
        conn.close()


def _evaluate_condition(conn, condition, alerts):
    triggered = []

    if "entity_type = 'security_alert'" in condition and "risk_score >= 40" in condition:
        rows = conn.execute("""
            SELECT * FROM ontology_entities
            WHERE entity_type = 'security_alert' AND risk_score >= 40 AND updated_at > datetime('now', '-1 day')
        """).fetchall()
        triggered = [dict(r) for r in rows]

    elif "entity_type = 'cloud_service'" in condition and "risk_score >= 15" in condition:
        rows = conn.execute("""
            SELECT * FROM ontology_entities
            WHERE entity_type = 'cloud_service' AND risk_score >= 15 AND updated_at > datetime('now', '-1 day')
        """).fetchall()
        triggered = [dict(r) for r in rows]

    elif "entity_type = 'developer'" in condition and "single_point_of_failure" in condition:
        rows = conn.execute("""
            SELECT oe.* FROM ontology_entities oe
            WHERE oe.entity_type = 'developer'
              AND (SELECT COUNT(*) FROM ontology_relationships
                   WHERE from_entity_id = oe.id AND relationship_type = 'contributes_to') <= 1
        """).fetchall()
        triggered = [dict(r) for r in rows]

    elif "entity_type = 'business_client'" in condition and "risk_score >= 15" in condition:
        rows = conn.execute("""
            SELECT * FROM ontology_entities
            WHERE entity_type = 'business_client' AND risk_score >= 15 AND updated_at > datetime('now', '-7 days')
        """).fetchall()
        triggered = [dict(r) for r in rows]

    elif "relationship_type = 'shared_across_companies'" in condition:
        rows = conn.execute("""
            SELECT DISTINCT oe.* FROM ontology_entities oe
            WHERE oe.id IN (
                SELECT from_entity_id FROM ontology_relationships
                WHERE relationship_type = 'shared_across_companies' AND created_at > datetime('now', '-1 day')
                UNION
                SELECT to_entity_id FROM ontology_relationships
                WHERE relationship_type = 'shared_across_companies' AND created_at > datetime('now', '-1 day')
            )
        """).fetchall()
        triggered = [dict(r) for r in rows]

    elif "entity_type = 'financial_metric'" in condition and "risk_score >= 20" in condition:
        rows = conn.execute("""
            SELECT * FROM ontology_entities
            WHERE entity_type = 'financial_metric' AND risk_score >= 20 AND updated_at > datetime('now', '-1 day')
        """).fetchall()
        triggered = [dict(r) for r in rows]

    elif "covenant_headroom_pct < 20" in condition:
        rows = conn.execute("""
            SELECT * FROM risk_metrics
            WHERE covenant_headroom_pct IS NOT NULL AND covenant_headroom_pct < 20
            ORDER BY recorded_at DESC LIMIT 1
        """).fetchall()
        if rows:
            triggered = [{"entity_name": "fund_centre_nav", "company_id": "rousseau", "properties": json.dumps({"headroom_pct": rows[0]["covenant_headroom_pct"]})}]

    if alerts:
        for alert in alerts:
            if alert.get("severity") in ("critical", "high"):
                triggered.append({
                    "entity_name": alert.get("entity", "unknown"),
                    "company_id": alert.get("company_id", "unknown"),
                    "properties": json.dumps({"alert_type": alert.get("pattern", "unknown"), "severity": alert.get("severity")}),
                })

    return triggered


def _execute_action(rule_row, config, triggered_entities, now, conn):
    rule = dict(rule_row)
    notify_targets = config.get("notify", [])
    message_template = config.get("message_template", "")
    escalation_level = config.get("escalation_level", "")

    resolved_targets = []
    for target in notify_targets:
        if target.startswith("{"):
            field = target.strip("{}")
            if triggered_entities:
                resolved_targets.append(triggered_entities[0].get(field, target))
            else:
                resolved_targets.append(target)
        else:
            resolved_targets.append(target)

    messages = []
    for entity in triggered_entities[:5]:
        props = json.loads(entity.get("properties", "{}")) if entity.get("properties") else {}
        msg = message_template
        msg = msg.replace("{company_id}", entity.get("company_id", "unknown"))
        msg = msg.replace("{entity_name}", entity.get("entity_name", entity.get("entity", "unknown")))
        msg = msg.replace("{entity}", entity.get("entity_name", entity.get("entity", "unknown")))
        msg = msg.replace("{amount}", "{:,.0f}".format(props.get("amount", 0)))
        msg = msg.replace("{headroom_pct}", str(props.get("headroom_pct", "N/A")))
        msg = msg.replace("{policy_name}", config.get("policy_type", "security_baseline"))
        msg = msg.replace("{effective_date}", now[:10])
        messages.append(msg)

    dispatch_result = None
    if messages:
        dispatch_result = dispatch_notifications(config, messages, rule.get("severity", "medium"))

    _log_action(conn, rule["id"], rule["action_type"], resolved_targets, messages, now)

    return {
        "status": "executed",
        "action_type": rule["action_type"],
        "targets": resolved_targets,
        "messages_sent": len(messages),
        "notifications": dispatch_result,
        "escalation_level": escalation_level,
    }


def _log_action(conn, rule_id, action_type, targets, messages, now):
    conn.execute("""
        INSERT INTO audit_log (actor, action, entity_type, entity_id, new_value, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "panteon_aip",
        "action_triggered",
        "action_rule",
        rule_id,
        json.dumps({"action_type": action_type, "targets": targets}),
        json.dumps({"messages": messages[:3]}),
        now,
    ))


def deploy_security_policy(policy_name, target_companies=None):
    conn = get_connection()
    try:
        if target_companies is None:
            rows = conn.execute("SELECT id FROM companies WHERE category IS NULL OR category != 'parent'").fetchall()
            if not rows:
                rows = conn.execute("SELECT id FROM companies").fetchall()
            target_companies = [r["id"] for r in rows]

        now = datetime.now(timezone.utc).isoformat()
        executions = []

        for company_id in target_companies:
            conn.execute("""
                INSERT INTO action_executions
                (rule_id, trigger_event, trigger_data, action_taken, target_company_ids, status, result, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "panteon-deployment-policy",
                json.dumps({"policy_name": policy_name}),
                json.dumps({"policy": policy_name}),
                "deploy_policy",
                json.dumps([company_id]),
                "deployed",
                json.dumps({"policy": policy_name, "company": company_id, "deployed_at": now}),
                now,
            ))
            executions.append({"company_id": company_id, "status": "deployed"})

        conn.execute("""
            INSERT INTO audit_log (actor, action, entity_type, entity_id, new_value, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "panteon_aip",
            "policy_deployed",
            "security_policy",
            policy_name,
            json.dumps({"targets": target_companies}),
            json.dumps({"executions": len(executions)}),
            now,
        ))

        conn.commit()
        return {"policy": policy_name, "deployed_to": executions, "count": len(executions)}
    finally:
        conn.close()


def get_action_history(limit=50):
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT ae.*, COALESCE(ar.name, ae.rule_id) as rule_name, COALESCE(ar.severity, 'unknown') as severity
            FROM action_executions ae
            LEFT JOIN action_rules ar ON ae.rule_id = ar.id
            ORDER BY ae.executed_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_rules():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM action_rules ORDER BY severity DESC, name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def toggle_rule(rule_id, enabled):
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE action_rules SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, now, rule_id)
        )
        conn.commit()
        return {"rule_id": rule_id, "enabled": enabled}
    finally:
        conn.close()


# ── Real Notification Dispatch ──────────────────────────────────────

def register_channel(channel_id, company_id, channel_type, webhook_url=None, config=None):
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        existing = conn.execute("SELECT id FROM notification_channels WHERE id = ?", (channel_id,)).fetchone()
        if existing:
            conn.execute("""
                UPDATE notification_channels SET channel_type = ?, webhook_url = ?, config = ?, enabled = 1, updated_at = ?
                WHERE id = ?
            """, (channel_type, webhook_url, json.dumps(config) if config else None, now, channel_id))
            conn.commit()
            return {"channel_id": channel_id, "status": "updated"}
        conn.execute("""
            INSERT INTO notification_channels (id, company_id, channel_type, webhook_url, config, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """, (channel_id, company_id, channel_type, webhook_url, json.dumps(config) if config else None, now, now))
        conn.commit()
        return {"channel_id": channel_id, "status": "registered"}
    finally:
        conn.close()


def get_channels(company_id=None):
    conn = get_connection()
    try:
        if company_id:
            rows = conn.execute("SELECT * FROM notification_channels WHERE company_id = ? ORDER BY channel_type", (company_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notification_channels ORDER BY company_id, channel_type").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_channel(channel_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM notification_channels WHERE id = ?", (channel_id,))
        conn.commit()
        return {"channel_id": channel_id, "status": "deleted"}
    finally:
        conn.close()


def send_notification(channel, message, severity):
    channel_type = channel.get("channel_type", "webhook")
    url = channel.get("webhook_url")
    config = json.loads(channel.get("config", "{}")) if channel.get("config") else {}
    status = "undelivered"
    response_detail = ""

    if not url and channel_type != "email":
        return {"channel": channel.get("id", "unknown"), "status": "no_url", "note": "no webhook_url configured"}

    try:
        if channel_type == "slack":
            import urllib.request
            payload = json.dumps({
                "text": message,
                "attachments": [{"color": "danger" if severity == "critical" else "warning", "text": message}],
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method='POST')
            resp = urllib.request.urlopen(req, timeout=10)
            status = "sent" if resp.getcode() == 200 else "error"
            response_detail = str(resp.getcode())

        elif channel_type == "webhook":
            import urllib.request
            payload = json.dumps({
                "event": "panteon_alert",
                "severity": severity,
                "message": message,
                "source": "panteon_aip",
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method='POST')
            resp = urllib.request.urlopen(req, timeout=10)
            status = "sent" if resp.getcode() == 200 else "error"
            response_detail = str(resp.getcode())

        elif channel_type == "pagerduty":
            import urllib.request
            routing_key = config.get("routing_key", "")
            payload = json.dumps({
                "routing_key": routing_key,
                "event_action": "trigger",
                "payload": {
                    "summary": message[:120],
                    "severity": "critical" if severity == "critical" else "warning",
                    "source": "panteon_aip",
                },
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method='POST')
            resp = urllib.request.urlopen(req, timeout=10)
            status = "sent" if resp.getcode() == 202 else "error"
            response_detail = str(resp.getcode())

        elif channel_type == "email":
            status = "logged"
            response_detail = "email dispatch requires SMTP configuration"

    except Exception as e:
        status = "error"
        response_detail = str(e)[:200]

    return {"channel": channel.get("id", "unknown"), "status": status, "detail": response_detail}


def dispatch_notifications(action_config, messages, severity):
    conn = get_connection()
    try:
        notify_targets = action_config.get("notify", [])
        results = []
        for company_id in notify_targets:
            company = company_id.strip("{}") if company_id.startswith("{") else company_id
            channels = conn.execute(
                "SELECT * FROM notification_channels WHERE company_id = ? AND enabled = 1",
                (company,)
            ).fetchall()
            if not channels:
                results.append({"target": company, "status": "no_channels", "note": "no notification channels configured"})
                continue
            for ch in channels:
                for msg in messages[:3]:
                    result = send_notification(dict(ch), msg, severity)
                    results.append(result)
        return {"dispatched": len(results), "results": results}
    finally:
        conn.close()


# ── Custom Rule Builder ──────────────────────────────────────────────

def create_rule(rule_id, name, description, trigger_condition, action_type, action_config, severity="medium"):
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        existing = conn.execute("SELECT id FROM action_rules WHERE id = ?", (rule_id,)).fetchone()
        if existing:
            return {"error": "rule already exists", "rule_id": rule_id}
        conn.execute("""
            INSERT INTO action_rules (id, name, description, trigger_condition, action_type, action_config, severity, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (rule_id, name, description, trigger_condition, action_type, json.dumps(action_config) if isinstance(action_config, dict) else action_config, severity, now, now))
        conn.commit()
        return {"rule_id": rule_id, "status": "created"}
    finally:
        conn.close()


def update_rule(rule_id, **kwargs):
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        fields = []
        params = []
        for key in ("name", "description", "trigger_condition", "action_type", "severity", "enabled"):
            if key in kwargs:
                fields.append("%s = ?" % key)
                params.append(kwargs[key])
        if "action_config" in kwargs:
            fields.append("action_config = ?")
            params.append(json.dumps(kwargs["action_config"]) if isinstance(kwargs["action_config"], dict) else kwargs["action_config"])
        if not fields:
            return {"error": "no fields to update"}
        fields.append("updated_at = ?")
        params.append(now)
        params.append(rule_id)
        conn.execute("UPDATE action_rules SET %s WHERE id = ?" % ", ".join(fields), params)
        conn.commit()
        return {"rule_id": rule_id, "status": "updated"}
    finally:
        conn.close()


def delete_rule(rule_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM action_rules WHERE id = ?", (rule_id,))
        conn.commit()
        return {"rule_id": rule_id, "status": "deleted"}
    finally:
        conn.close()


def get_rule_detail(rule_id):
    conn = get_connection()
    try:
        rule = conn.execute("SELECT * FROM action_rules WHERE id = ?", (rule_id,)).fetchone()
        if not rule:
            return {"error": "rule not found"}
        executions = conn.execute(
            "SELECT * FROM action_executions WHERE rule_id = ? ORDER BY executed_at DESC LIMIT 20",
            (rule_id,)
        ).fetchall()
        return {"rule": dict(rule), "recent_executions": [dict(e) for e in executions]}
    finally:
        conn.close()
