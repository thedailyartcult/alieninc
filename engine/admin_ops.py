"""
Alien.Inc Admin Operations
NDA-safe manual data entry for the ecosystem.
All operations are audit-logged and require authentication.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db'))
from schema import get_connection, DB_PATH


def _audit(conn, actor, action, entity_type, entity_id=None, old_value=None, new_value=None, metadata=None, ip=None, ua=None):
    conn.execute("""
        INSERT INTO audit_log
        (actor, action, entity_type, entity_id, old_value, new_value, metadata, ip_address, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        actor, action, entity_type, entity_id,
        json.dumps(old_value) if old_value is not None else None,
        json.dumps(new_value) if new_value is not None else None,
        json.dumps(metadata) if metadata else None,
        ip, ua,
    ))


def update_client(client_id, actor, updates, ip=None, ua=None):
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if not existing:
            return {"error": "Client not found: %s" % client_id}

        old = dict(existing)
        allowed = ['status', 'annual_contract_value', 'renewal_date', 'industry', 'country', 'segment', 'satisfaction_score', 'retention_probability', 'notes']
        applied = {}
        for key, value in updates.items():
            if key in allowed:
                if key == 'status' and value not in ('active', 'renewal_due', 'pipeline', 'paused', 'closed_won', 'closed_lost'):
                    continue
                applied[key] = value

        if not applied:
            return {"error": "No valid fields to update"}

        set_clauses = []
        set_values = []
        for key, value in applied.items():
            set_clauses.append("%s = ?" % key)
            set_values.append(value)
        set_clauses.append("updated_at = ?")
        set_values.append(datetime.now(timezone.utc).isoformat())
        set_values.append(client_id)

        conn.execute("UPDATE clients SET %s WHERE id = ?" % ", ".join(set_clauses), set_values)
        _audit(conn, actor, "update_client", "client", client_id, old, applied, ip=ip, ua=ua)
        conn.commit()
        return {"success": True, "client_id": client_id, "updated_fields": list(applied.keys())}
    finally:
        conn.close()


def add_client(actor, client_data, ip=None, ua=None):
    conn = get_connection()
    try:
        required = ['company_id', 'client_name']
        for field in required:
            if field not in client_data:
                return {"error": "Missing required field: %s" % field}

        existing_count = conn.execute("SELECT COUNT(*) as cnt FROM clients").fetchone()["cnt"]
        client_id = client_data.get('client_id') or ("C-MAN-%03d" % (existing_count + 1))

        existing = conn.execute("SELECT id FROM clients WHERE id = ?", (client_id,)).fetchone()
        if existing:
            return {"error": "Client ID already exists: %s" % client_id}

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO clients
            (id, company_id, client_name, industry, country, segment,
             service_line_id, annual_contract_value, status,
             start_date, renewal_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_id,
            client_data['company_id'],
            client_data['client_name'],
            client_data.get('industry'),
            client_data.get('country'),
            client_data.get('segment'),
            client_data.get('service_line_id'),
            client_data.get('annual_contract_value', 0),
            client_data.get('status', 'active'),
            client_data.get('start_date'),
            client_data.get('renewal_date'),
            client_data.get('notes'),
            now, now,
        ))

        _audit(conn, actor, "add_client", "client", client_id, None, client_data, ip=ip, ua=ua)

        conn.execute("UPDATE companies SET client_count = (SELECT COUNT(*) FROM clients WHERE company_id = ? AND status = 'active'), updated_at = ? WHERE id = ?",
                     (client_data['company_id'], now, client_data['company_id']))

        conn.commit()
        return {"success": True, "client_id": client_id}
    finally:
        conn.close()


def update_company_financials(company_id, actor, year, updates, confidence='actual', ip=None, ua=None):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM company_financials WHERE company_id = ? AND year = ? AND confidence = ?",
            (company_id, year, confidence)
        ).fetchone()

        old = dict(existing) if existing else None

        allowed = ['revenue', 'operating_costs', 'ebitda', 'cash_ending']
        applied = {}
        for key, value in updates.items():
            if key in allowed:
                applied[key] = float(value)

        if not applied:
            return {"error": "No valid fields to update"}

        if existing:
            set_clauses = []
            set_values = []
            for key, value in applied.items():
                set_clauses.append("%s = ?" % key)
                set_values.append(value)
            set_values.extend([company_id, year, confidence])
            conn.execute("UPDATE company_financials SET %s WHERE company_id = ? AND year = ? AND confidence = ?" % ", ".join(set_clauses), set_values)
        else:
            conn.execute("""
                INSERT INTO company_financials (company_id, year, confidence, revenue, operating_costs, ebitda, cash_ending)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                company_id, year, confidence,
                applied.get('revenue', 0),
                applied.get('operating_costs', 0),
                applied.get('ebitda', 0),
                applied.get('cash_ending', 0),
            ))

        if 'cash_ending' in applied:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE companies SET current_cash = ?, updated_at = ? WHERE id = ?",
                         (applied['cash_ending'], now, company_id))

        _audit(conn, actor, "update_financials", "company_financials", "%s-%d-%s" % (company_id, year, confidence), old, applied,
               metadata={"year": year, "confidence": confidence}, ip=ip, ua=ua)
        conn.commit()
        return {"success": True, "company_id": company_id, "year": year, "updated_fields": list(applied.keys())}
    finally:
        conn.close()


def confirm_intercompany_payment(transaction_id, actor, amount, ip=None, ua=None):
    conn = get_connection()
    try:
        tx = conn.execute("SELECT * FROM intercompany_transactions WHERE id = ?", (transaction_id,)).fetchone()
        if not tx:
            return {"error": "Transaction not found: %s" % transaction_id}

        amount = float(amount)
        old_outstanding = tx['total_outstanding'] or 0
        old_billed = tx['total_billed'] or 0
        new_outstanding = old_outstanding + amount
        new_billed = old_billed + amount

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            UPDATE intercompany_transactions
            SET total_billed = ?, total_outstanding = ?, last_billed_date = ?, updated_at = ?
            WHERE id = ?
        """, (new_billed, new_outstanding, now, now, transaction_id))

        from_cash = conn.execute("SELECT current_cash FROM companies WHERE id = ?", (tx['from_company_id'],)).fetchone()
        to_cash = conn.execute("SELECT current_cash FROM companies WHERE id = ?", (tx['to_company_id'],)).fetchone()

        if from_cash and to_cash:
            conn.execute("UPDATE companies SET current_cash = ?, updated_at = ? WHERE id = ?",
                         (from_cash['current_cash'] - amount, now, tx['from_company_id']))
            conn.execute("UPDATE companies SET current_cash = ?, updated_at = ? WHERE id = ?",
                         (to_cash['current_cash'] + amount, now, tx['to_company_id']))

        _audit(conn, actor, "confirm_payment", "intercompany_transaction", transaction_id,
               {"total_billed": old_billed, "total_outstanding": old_outstanding},
               {"total_billed": new_billed, "total_outstanding": new_outstanding, "amount": amount},
               ip=ip, ua=ua)
        conn.commit()
        return {"success": True, "transaction_id": transaction_id, "amount": amount}
    finally:
        conn.close()


def update_fund_nav(actor, fund_id, share_class_name, nav, nav_date=None, ip=None, ua=None):
    conn = get_connection()
    try:
        fund = conn.execute("SELECT id FROM funds WHERE id = ?", (fund_id,)).fetchone()
        if not fund:
            return {"error": "Fund not found: %s" % fund_id}

        sc = conn.execute(
            "SELECT * FROM fund_share_classes WHERE fund_id = ? AND name = ?",
            (fund_id, share_class_name)
        ).fetchone()

        if not sc:
            return {"error": "Share class not found: %s / %s" % (fund_id, share_class_name)}

        old_nav = sc['nav']
        nav = float(nav)
        nav_date = nav_date or datetime.now(timezone.utc).date().isoformat()
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            "UPDATE fund_share_classes SET nav = ?, nav_date = ?, updated_at = ? WHERE fund_id = ? AND name = ?",
            (nav, nav_date, now, fund_id, share_class_name)
        )

        conn.execute(
            "UPDATE funds SET nav_latest = ?, updated_at = ? WHERE id = ?",
            (nav, now, fund_id)
        )

        _audit(conn, actor, "update_fund_nav", "fund_share_class", "%s/%s" % (fund_id, share_class_name),
               {"nav": old_nav}, {"nav": nav, "nav_date": nav_date}, ip=ip, ua=ua)
        conn.commit()
        return {"success": True, "fund_id": fund_id, "share_class": share_class_name, "nav": nav}
    finally:
        conn.close()


def add_manual_event(actor, event_data, ip=None, ua=None):
    conn = get_connection()
    try:
        required = ['event_type', 'title']
        for field in required:
            if field not in event_data:
                return {"error": "Missing required field: %s" % field}

        affected = event_data.get('affected_company_ids', [])
        if isinstance(affected, list):
            affected = json.dumps(affected)

        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute("""
            INSERT INTO events
            (event_type, source, title, description, affected_company_ids,
             impact_severity, financial_impact, published_date, ingested_at, processed)
            VALUES (?, 'manual', ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            event_data['event_type'],
            event_data['title'],
            event_data.get('description', ''),
            affected,
            event_data.get('impact_severity', 'medium'),
            event_data.get('financial_impact', 0),
            event_data.get('published_date', now[:10]),
            now,
        ))

        event_id = cursor.lastrowid
        _audit(conn, actor, "add_manual_event", "event", str(event_id), None, event_data, ip=ip, ua=ua)
        conn.commit()
        return {"success": True, "event_id": event_id}
    finally:
        conn.close()


def record_board_decision(actor, decision_data, ip=None, ua=None):
    conn = get_connection()
    try:
        required = ['decision_type', 'title']
        for field in required:
            if field not in decision_data:
                return {"error": "Missing required field: %s" % field}

        affected = decision_data.get('affected_company_ids', [])
        if isinstance(affected, list):
            affected = json.dumps(affected)

        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute("""
            INSERT INTO board_decisions
            (decision_date, decision_type, title, description, affected_company_ids,
             financial_impact, status, recorded_by, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision_data.get('decision_date', now[:10]),
            decision_data['decision_type'],
            decision_data['title'],
            decision_data.get('description'),
            affected,
            decision_data.get('financial_impact', 0),
            decision_data.get('status', 'approved'),
            actor,
            json.dumps(decision_data.get('metadata')) if decision_data.get('metadata') else None,
            now,
        ))

        decision_id = cursor.lastrowid
        _audit(conn, actor, "record_board_decision", "board_decision", str(decision_id), None, decision_data, ip=ip, ua=ua)
        conn.commit()
        return {"success": True, "decision_id": decision_id}
    finally:
        conn.close()


def get_admin_state():
    conn = get_connection()
    try:
        companies = [dict(c) for c in conn.execute("SELECT id, brand_name, current_cash, client_count FROM companies ORDER BY id").fetchall()]
        clients = [dict(c) for c in conn.execute("SELECT id, company_id, client_name, status, annual_contract_value FROM clients ORDER BY id").fetchall()]
        transactions = [dict(t) for t in conn.execute("SELECT * FROM intercompany_transactions ORDER BY id").fetchall()]
        funds = conn.execute("""
            SELECT f.id, f.name, fsc.name as share_class, fsc.nav, fsc.nav_date, fsc.aum, fsc.aum_formatted
            FROM funds f JOIN fund_share_classes fsc ON f.id = fsc.fund_id ORDER BY f.id, fsc.name
        """).fetchall()
        debts = [dict(d) for d in conn.execute("SELECT * FROM debt_instruments ORDER BY id").fetchall()]
        recent_audit = [dict(a) for a in conn.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 20").fetchall()]

        return {
            "companies": companies,
            "clients": clients,
            "transactions": transactions,
            "funds": [dict(f) for f in funds],
            "debts": debts,
            "recent_audit": recent_audit,
        }
    finally:
        conn.close()


def get_audit_log(limit=50, actor=None, action=None, entity_type=None):
    conn = get_connection()
    try:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if actor:
            query += " AND actor = ?"
            params.append(actor)
        if action:
            query += " AND action = ?"
            params.append(action)
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
