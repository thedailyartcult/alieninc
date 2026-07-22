"""
Alien.Inc Ecosystem — Database Schema & Initialization
SQLite-backed living data store for the group operating system.
"""

import sqlite3
import os
import json
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ecosystem.db')
JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'alieninc-ecosystem.json')

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS simulation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_day INTEGER NOT NULL DEFAULT 0,
    current_date TEXT NOT NULL,
    last_run TEXT,
    status TEXT NOT NULL DEFAULT 'initialized',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS group_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    founded TEXT,
    description TEXT,
    history TEXT,
    operating_thesis TEXT,
    management_cadence TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    legal_name TEXT NOT NULL,
    brand_name TEXT NOT NULL,
    category TEXT,
    year_founded INTEGER,
    founding_date TEXT,
    ownership_status TEXT,
    mission TEXT,
    vision TEXT,
    headcount_2026f INTEGER,
    headcount_full_time INTEGER,
    headcount_contractors INTEGER,
    leadership_team TEXT,
    service_offerings TEXT,
    digital_presence TEXT,
    current_cash REAL DEFAULT 0,
    current_health REAL DEFAULT 100,
    current_momentum REAL DEFAULT 0,
    daily_revenue REAL DEFAULT 0,
    daily_costs REAL DEFAULT 0,
    daily_ebitda REAL DEFAULT 0,
    client_count INTEGER DEFAULT 0,
    active_project_count INTEGER DEFAULT 0,
    last_simulation_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS company_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id TEXT NOT NULL REFERENCES companies(id),
    year INTEGER NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'forecast',
    revenue REAL DEFAULT 0,
    operating_costs REAL DEFAULT 0,
    ebitda REAL DEFAULT 0,
    cash_ending REAL DEFAULT 0,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(company_id, year, confidence)
);

CREATE TABLE IF NOT EXISTS company_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id TEXT NOT NULL REFERENCES companies(id),
    period TEXT NOT NULL DEFAULT '2026F',
    kpi_key TEXT NOT NULL,
    kpi_value REAL,
    kpi_label TEXT,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(company_id, period, kpi_key)
);

CREATE TABLE IF NOT EXISTS revenue_breakdown (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id TEXT NOT NULL REFERENCES companies(id),
    period TEXT NOT NULL DEFAULT '2026F',
    service_line_id TEXT NOT NULL,
    amount REAL DEFAULT 0,
    share REAL DEFAULT 0,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(company_id, period, service_line_id)
);

CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    client_name TEXT NOT NULL,
    industry TEXT,
    country TEXT,
    segment TEXT,
    service_line_id TEXT,
    annual_contract_value REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    start_date TEXT,
    renewal_date TEXT,
    satisfaction_score REAL,
    retention_probability REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    name TEXT NOT NULL,
    client_id TEXT REFERENCES clients(id),
    stage TEXT NOT NULL DEFAULT 'discovery',
    expected_revenue REAL DEFAULT 0,
    gross_margin_target REAL DEFAULT 0,
    probability REAL DEFAULT 0,
    start_date TEXT,
    expected_close_date TEXT,
    actual_close_date TEXT,
    actual_revenue REAL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS intercompany_transactions (
    id TEXT PRIMARY KEY,
    from_company_id TEXT NOT NULL REFERENCES companies(id),
    to_company_id TEXT NOT NULL REFERENCES companies(id),
    tx_type TEXT NOT NULL DEFAULT 'service_fee',
    description TEXT,
    amount REAL DEFAULT 0,
    billing_cadence TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    last_billed_date TEXT,
    next_billing_date TEXT,
    total_billed REAL DEFAULT 0,
    total_outstanding REAL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subsidiary_investments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_company_id TEXT NOT NULL REFERENCES companies(id),
    instrument TEXT NOT NULL,
    amount REAL DEFAULT 0,
    date TEXT,
    purpose TEXT,
    interest_rate REAL DEFAULT 0,
    principal_outstanding REAL,
    status TEXT NOT NULL DEFAULT 'funded',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dividends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_company_id TEXT NOT NULL REFERENCES companies(id),
    to_company_id TEXT NOT NULL REFERENCES companies(id),
    year INTEGER NOT NULL,
    amount REAL DEFAULT 0,
    basis TEXT,
    status TEXT NOT NULL DEFAULT 'paid',
    paid_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS capital_structure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_type TEXT NOT NULL,
    holder TEXT,
    ownership_pct REAL,
    instrument TEXT,
    principal_outstanding REAL,
    interest_rate REAL,
    maturity TEXT,
    policy TEXT,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS funds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    inception_date TEXT,
    nav_latest REAL,
    nav_currency TEXT DEFAULT 'EUR',
    ytd_return REAL,
    annualised_return REAL,
    aum REAL,
    benchmark TEXT,
    risk_rating TEXT,
    ter REAL,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fund_share_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id TEXT NOT NULL REFERENCES funds(id),
    name TEXT NOT NULL,
    isin TEXT,
    nav REAL DEFAULT 0,
    nav_date TEXT,
    annualised_return REAL DEFAULT 0,
    inception_date TEXT,
    ytd_return REAL DEFAULT 0,
    one_year_return REAL DEFAULT 0,
    three_year_return REAL DEFAULT 0,
    five_year_return REAL DEFAULT 0,
    ten_year_return REAL,
    volatility_3y REAL DEFAULT 0,
    aum REAL DEFAULT 0,
    aum_formatted TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS debt_instruments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    instrument_type TEXT NOT NULL DEFAULT 'note',
    principal_outstanding REAL DEFAULT 0,
    interest_rate REAL DEFAULT 0,
    maturity_date TEXT,
    holder TEXT,
    covenants TEXT,
    covenant_threshold REAL,
    covenant_metric TEXT,
    covenant_status TEXT DEFAULT 'compliant',
    covenant_headroom_pct REAL,
    last_checked TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS risk_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    simulation_day INTEGER,
    debt_service_coverage_months REAL DEFAULT 0,
    parent_runway_months REAL DEFAULT 0,
    avg_subsidiary_runway_months REAL DEFAULT 0,
    min_subsidiary_runway_months REAL DEFAULT 0,
    min_runway_company_id TEXT,
    contagion_count INTEGER DEFAULT 0,
    total_intercompany_exposure REAL DEFAULT 0,
    intercompany_to_parent_cash_pct REAL DEFAULT 0,
    fund_centre_nav_index REAL DEFAULT 0,
    fund_centre_aum_eur REAL DEFAULT 0,
    covenant_headroom_pct REAL DEFAULT 0,
    covenant_status TEXT DEFAULT 'compliant',
    risk_score INTEGER DEFAULT 0,
    alerts TEXT
);

CREATE TABLE IF NOT EXISTS allocation_summary (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_equity_pct REAL DEFAULT 1.0,
    total_debt_outstanding REAL DEFAULT 0,
    weighted_avg_debt_rate REAL DEFAULT 0,
    total_capital_deployed REAL DEFAULT 0,
    dividends_received_2025 REAL DEFAULT 0,
    dividends_forecast_2026 REAL DEFAULT 0,
    subsidiary_cash_position REAL DEFAULT 0,
    parent_cash_position REAL DEFAULT 0,
    consolidated_cash_position REAL DEFAULT 0,
    fund_centre_aum_eur REAL DEFAULT 0,
    fund_centre_avg_ytd_return REAL DEFAULT 0,
    fund_centre_avg_annualised_return REAL DEFAULT 0,
    liquidity_months REAL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS group_rollup (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    standalone_revenue_total REAL DEFAULT 0,
    intercompany_revenue REAL DEFAULT 0,
    external_revenue REAL DEFAULT 0,
    standalone_ebitda_total REAL DEFAULT 0,
    largest_external_revenue_company TEXT,
    highest_recurring_revenue_company TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS company_revenue_rollup (
    company_id TEXT PRIMARY KEY REFERENCES companies(id),
    standalone_revenue_2026f REAL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    source TEXT,
    title TEXT,
    description TEXT,
    affected_company_ids TEXT,
    impact_severity TEXT DEFAULT 'low',
    impact_description TEXT,
    financial_impact REAL,
    url TEXT,
    published_date TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed INTEGER DEFAULT 0,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    old_value TEXT,
    new_value TEXT,
    metadata TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS board_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_date TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    affected_company_ids TEXT,
    financial_impact REAL,
    status TEXT NOT NULL DEFAULT 'approved',
    recorded_by TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS simulation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    simulation_day INTEGER NOT NULL,
    companies_processed INTEGER DEFAULT 0,
    events_generated INTEGER DEFAULT 0,
    revenue_generated REAL DEFAULT 0,
    costs_incurred REAL DEFAULT 0,
    ebitda_generated REAL DEFAULT 0,
    intercompany_flows REAL DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'success',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS data_sources (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    connection_config TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    last_ingested_at TEXT,
    records_ingested INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS raw_ingested_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES data_sources(id),
    company_id TEXT NOT NULL,
    data_type TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed INTEGER DEFAULT 0,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS ontology_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    company_id TEXT REFERENCES companies(id),
    raw_source_id INTEGER REFERENCES raw_ingested_data(id),
    properties TEXT,
    risk_score REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ontology_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_entity_id INTEGER NOT NULL REFERENCES ontology_entities(id),
    to_entity_id INTEGER NOT NULL REFERENCES ontology_entities(id),
    relationship_type TEXT NOT NULL,
    properties TEXT,
    strength REAL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS action_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    trigger_condition TEXT NOT NULL,
    action_type TEXT NOT NULL,
    action_config TEXT NOT NULL,
    target_company_ids TEXT,
    severity TEXT NOT NULL DEFAULT 'medium',
    enabled INTEGER NOT NULL DEFAULT 1,
    execution_count INTEGER DEFAULT 0,
    last_executed TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS action_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT NOT NULL REFERENCES action_rules(id),
    trigger_event TEXT,
    trigger_data TEXT,
    action_taken TEXT,
    target_company_ids TEXT,
    status TEXT NOT NULL DEFAULT 'executed',
    result TEXT,
    executed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ontology_entity_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES ontology_entities(id),
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    company_id TEXT,
    properties TEXT,
    risk_score REAL DEFAULT 0,
    changed_at TEXT NOT NULL DEFAULT (datetime('now')),
    change_reason TEXT
);

CREATE TABLE IF NOT EXISTS notification_channels (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    channel_type TEXT NOT NULL CHECK(channel_type IN ('webhook', 'slack', 'email', 'pagerduty')),
    webhook_url TEXT,
    config TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_scopes (
    email TEXT NOT NULL,
    company_id TEXT NOT NULL REFERENCES companies(id),
    scope TEXT NOT NULL DEFAULT 'viewer' CHECK(scope IN ('viewer', 'analyst', 'admin', 'superadmin')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (email, company_id)
);

CREATE INDEX IF NOT EXISTS idx_financials_company ON company_financials(company_id);
CREATE INDEX IF NOT EXISTS idx_kpis_company ON company_kpis(company_id);
CREATE INDEX IF NOT EXISTS idx_clients_company ON clients(company_id);
CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
CREATE INDEX IF NOT EXISTS idx_projects_company ON projects(company_id);
CREATE INDEX IF NOT EXISTS idx_projects_stage ON projects(stage);
CREATE INDEX IF NOT EXISTS idx_transactions_from ON intercompany_transactions(from_company_id);
CREATE INDEX IF NOT EXISTS idx_transactions_to ON intercompany_transactions(to_company_id);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(published_date);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_processed ON events(processed);
CREATE INDEX IF NOT EXISTS idx_sim_log_date ON simulation_log(run_date);
CREATE INDEX IF NOT EXISTS idx_revenue_breakdown_company ON revenue_breakdown(company_id);
CREATE INDEX IF NOT EXISTS idx_fund_sc_fund ON fund_share_classes(fund_id);
CREATE INDEX IF NOT EXISTS idx_debt_status ON debt_instruments(covenant_status);
CREATE INDEX IF NOT EXISTS idx_risk_date ON risk_metrics(recorded_at);
CREATE INDEX IF NOT EXISTS idx_risk_day ON risk_metrics(simulation_day);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_board_date ON board_decisions(decision_date);
CREATE INDEX IF NOT EXISTS idx_board_type ON board_decisions(decision_type);
CREATE INDEX IF NOT EXISTS idx_data_sources_company ON data_sources(company_id);
CREATE INDEX IF NOT EXISTS idx_data_sources_status ON data_sources(status);
CREATE INDEX IF NOT EXISTS idx_raw_data_source ON raw_ingested_data(source_id);
CREATE INDEX IF NOT EXISTS idx_raw_data_processed ON raw_ingested_data(processed);
CREATE INDEX IF NOT EXISTS idx_ontology_type ON ontology_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_ontology_company ON ontology_entities(company_id);
CREATE INDEX IF NOT EXISTS idx_ontology_name ON ontology_entities(entity_name);
CREATE INDEX IF NOT EXISTS idx_ontology_rel_from ON ontology_relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_ontology_rel_to ON ontology_relationships(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_action_rules_enabled ON action_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_action_exec_rule ON action_executions(rule_id);
CREATE INDEX IF NOT EXISTS idx_action_exec_date ON action_executions(executed_at);
CREATE INDEX IF NOT EXISTS idx_entity_history_entity ON ontology_entity_history(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_history_date ON ontology_entity_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_channels_company ON notification_channels(company_id);
CREATE INDEX IF NOT EXISTS idx_user_scopes_email ON user_scopes(email);
"""


def get_connection(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path=None):
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.close()
    return db_path or DB_PATH


def is_initialized(db_path=None):
    path = db_path or DB_PATH
    if not os.path.exists(path):
        return False
    conn = get_connection(path)
    try:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='companies'").fetchone()
        conn.close()
        return row is not None
    except Exception:
        conn.close()
        return False


if __name__ == '__main__':
    path = init_db()
    print(f"Database initialized at {path}")
