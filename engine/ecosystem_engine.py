"""
Alien.Inc Living Ecosystem Engine — Python/SQLite
Processes daily operations across all group companies.
Reads/writes directly to the ecosystem database.
"""

import json
import math
import random
import time
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db'))
from schema import get_connection, DB_PATH


SEED_SALT = "alieninc.ecosystem.v1"

# Curated, public-safe network map data (nodes/districts/cities with PSA
# census populations). Merged into every ecosystem payload. No financial data.
_STATIC_NETWORK_MAP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'alieninc-ecosystem.json',
)

_static_data_cache = None

def _get_static_ecosystem():
    global _static_data_cache
    if _static_data_cache is not None:
        return _static_data_cache
    try:
        with open(_STATIC_NETWORK_MAP_PATH, 'r', encoding='utf-8') as f:
            _static_data_cache = json.load(f)
    except Exception:
        _static_data_cache = {}
    return _static_data_cache

def _get_static_network_map():
    return _get_static_ecosystem().get('networkMap')

def _get_static_bgc_directory():
    return _get_static_ecosystem().get('bgcDirectory')

_CLIENT_LOSS_REASONS = [
    "contract expired — not renewed",
    "lost to competitor bid",
    "client downsized operations",
    "budget cut — project suspended",
    "merger absorbed client entity",
    "dissatisfaction with delivery quality",
    "strategic pivot away from service area",
]

_CLIENT_WIN_SOURCES = [
    "inbound referral from portfolio company",
    "conference lead conversion",
    "RFP response — won",
    "existing client expansion",
    "partner channel introduction",
    "organic search conversion",
    "direct outreach — executive network",
]

_MARKET_CONDITIONS = {
    "bull": {"revenue_multiplier": 1.12, "win_prob_boost": 0.04, "client_loss_prob": 0.005, "risk_event_prob": 0.002},
    "neutral": {"revenue_multiplier": 1.0, "win_prob_boost": 0.0, "client_loss_prob": 0.01, "risk_event_prob": 0.005},
    "bear": {"revenue_multiplier": 0.88, "win_prob_boost": -0.03, "client_loss_prob": 0.018, "risk_event_prob": 0.012},
    "crisis": {"revenue_multiplier": 0.72, "win_prob_boost": -0.06, "client_loss_prob": 0.03, "risk_event_prob": 0.025},
}

_SECTOR_MARKET_SENSITIVITY = {
    "rousseau": {"bull": 1.15, "neutral": 1.0, "bear": 0.82, "crisis": 0.65},
    "tdac": {"bull": 1.05, "neutral": 1.0, "bear": 0.90, "crisis": 0.78},
    "panteon": {"bull": 1.10, "neutral": 1.0, "bear": 1.12, "crisis": 1.25},
    "centra": {"bull": 1.10, "neutral": 1.0, "bear": 1.12, "crisis": 1.25},
    "kmt": {"bull": 1.08, "neutral": 1.0, "bear": 0.85, "crisis": 0.72},
    "immanuel": {"bull": 1.05, "neutral": 1.0, "bear": 1.15, "crisis": 1.35},
}


class EcosystemEngine:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self.sim_date = None
        self.sim_day = 0
        self.market = "neutral"
        self.day_events = []
        self.day_log = {
            "revenue_generated": 0,
            "costs_incurred": 0,
            "ebitda_generated": 0,
            "intercompany_flows": 0,
            "events_generated": 0,
            "companies_processed": 0,
        }

    def _open(self):
        self.conn = get_connection(self.db_path)
        state = self.conn.execute("SELECT * FROM simulation_state WHERE id = 1").fetchone()
        if state:
            self.sim_day = state["current_day"]
            self.sim_date = datetime.strptime(state["current_date"], "%Y-%m-%d").date()
        else:
            self.sim_day = 0
            self.sim_date = datetime.now(timezone.utc).date()

    def _close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _seed_random(self, company_id):
        raw = f"{SEED_SALT}:{self.sim_date.isoformat()}:{company_id}"
        seed = int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)
        random.seed(seed)

    def _get_market_conditions(self):
        conn = self.conn
        last_30_events = conn.execute(
            "SELECT impact_severity, event_type, published_date FROM events WHERE processed = 1 ORDER BY ingested_at DESC LIMIT 30"
        ).fetchall()

        severity_scores = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        total_severity = sum(severity_scores.get(e["impact_severity"], 0) for e in last_30_events)

        event_type_weights = {
            "cybersecurity": 2.5, "financial": 2.0, "geopolitical": 2.2,
            "regulatory": 1.8, "market": 1.5, "operational": 1.2,
            "reputational": 1.0, "natural_disaster": 2.8, "pandemic": 3.0,
        }

        weighted_severity = 0
        for e in last_30_events:
            base = severity_scores.get(e["impact_severity"], 0)
            event_type = e["event_type"] if "event_type" in e.keys() else ""
            weight = event_type_weights.get(event_type, 1.0)
            weighted_severity += base * weight

        if weighted_severity > 45:
            self.market = "crisis"
        elif weighted_severity > 25:
            self.market = "bear"
        elif weighted_severity > 10:
            self.market = "neutral"
        else:
            self.market = "bull"

        return _MARKET_CONDITIONS[self.market]

    def _get_company_clients(self, company_id):
        return self.conn.execute(
            "SELECT * FROM clients WHERE company_id = ? AND status = 'active'",
            (company_id,)
        ).fetchall()

    def _get_daily_revenue(self, company_id, clients, market):
        total = 0
        sector_sensitivity = _SECTOR_MARKET_SENSITIVITY.get(company_id, {}).get(self.market, 1.0)
        for c in clients:
            acv = c["annual_contract_value"] or 0
            daily = acv / 365.0
            total += daily * market["revenue_multiplier"] * sector_sensitivity
        return total

    def _get_daily_costs(self, company_id):
        company = self.conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
        fin = self.conn.execute(
            "SELECT * FROM company_financials WHERE company_id = ? ORDER BY year DESC LIMIT 1",
            (company_id,)
        ).fetchone()

        if fin:
            annual_costs = fin["operating_costs"]
        else:
            annual_costs = 0

        return annual_costs / 365.0

    def _generate_client_win(self, company_id, company_name, market):
        base_prob = 0.02 + market["win_prob_boost"]
        if random.random() > base_prob:
            return None

        source = random.choice(_CLIENT_WIN_SOURCES)
        industries = ["Technology", "Healthcare", "Financial services", "Manufacturing",
                       "Energy", "Consumer goods", "Education", "Government", "Media", "Logistics"]
        countries = ["United States", "United Kingdom", "Canada", "Germany", "France",
                      "Australia", "Netherlands", "Switzerland", "Singapore", "UAE"]
        segments = ["enterprise", "middle_market", "lower_middle_market", "growth_company", "startup"]

        company = self.conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
        services = json.loads(company["service_offerings"] or "[]")
        service = random.choice(services) if services else {}

        existing = self.conn.execute("SELECT COUNT(*) as cnt FROM clients").fetchone()["cnt"]
        new_id = f"C-GEN-{existing + 1:03d}"

        acv = round(random.uniform(50000, 500000) / 1000) * 1000

        name_parts = [
            ("North", "South", "East", "West", "Clear", "Green", "Blue", "Red", "Iron", "Gold"),
            ("star", "field", "water", "stone", "ridge", "vale", "peak", "haven", "line", "mark"),
        ]
        suffixes = ["Group", "Corp", "Inc", "Systems", "Networks", "Partners", "Holdings", "Solutions"]

        name = f"{random.choice(name_parts[0])}{random.choice(name_parts[1]).lower()} {random.choice(suffixes)}"

        self.conn.execute("""
            INSERT INTO clients
            (id, company_id, client_name, industry, country, segment, service_line_id,
             annual_contract_value, status, start_date, renewal_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """, (
            new_id, company_id, name,
            random.choice(industries),
            random.choice(countries),
            random.choice(segments),
            service.get("id", f"{company_id}-general"),
            acv,
            self.sim_date.isoformat(),
            (self.sim_date + timedelta(days=365)).isoformat(),
        ))

        return {
            "type": "client_won",
            "company_id": company_id,
            "client_id": new_id,
            "client_name": name,
            "acv": acv,
            "source": source,
        }

    def _generate_client_loss(self, company_id, company_name, clients, market):
        if not clients or random.random() > market.get("client_loss_prob", 0.01):
            return None

        client = random.choice(clients)
        reason = random.choice(_CLIENT_LOSS_REASONS)

        self.conn.execute(
            "UPDATE clients SET status = 'closed_lost', updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), client["id"])
        )

        return {
            "type": "client_lost",
            "company_id": company_id,
            "client_id": client["id"],
            "client_name": client["client_name"],
            "acv_lost": client["annual_contract_value"],
            "reason": reason,
        }

    def _generate_risk_event(self, company_id, company_name, market):
        if random.random() > market.get("risk_event_prob", 0.005):
            return None

        market_risk_bias = {
            "bull": [("market", 0.3), ("operational", 0.2)],
            "neutral": [("compliance", 0.2), ("operational", 0.2)],
            "bear": [("financial", 0.3), ("market", 0.3), ("reputational", 0.2)],
            "crisis": [("security", 0.3), ("financial", 0.3), ("reputational", 0.2), ("legal", 0.2)],
        }

        risks = [
            ("security", "Potential vulnerability detected in production infrastructure"),
            ("compliance", "Regulatory filing deadline approaching — review required"),
            ("operational", "Key personnel availability risk — backup planning needed"),
            ("financial", "Cash flow timing mismatch — short-term bridge needed"),
            ("reputational", "Negative press mention detected — monitoring active"),
            ("technical", "Legacy system degradation detected — remediation planned"),
            ("market", "Competitor pricing shift detected — strategy review needed"),
            ("legal", "Contract ambiguity flagged by review — clarification needed"),
        ]

        bias = market_risk_bias.get(self.market, [])
        if bias and random.random() < 0.6:
            bias_types = [b[0] for b in bias]
            bias_weights = [b[1] for b in bias]
            risk_type = random.choices(bias_types, weights=bias_weights, k=1)[0]
            matching = [r for r in risks if r[0] == risk_type]
            if matching:
                risk_type, description = matching[0]
            else:
                risk_type, description = random.choice(risks)
        else:
            risk_type, description = random.choice(risks)

        severity_pool = ["low", "low", "medium", "medium", "high"]
        if self.market in ("bear", "crisis"):
            severity_pool = ["low", "medium", "medium", "high", "high", "critical"]
        severity = random.choice(severity_pool)

        return {
            "type": "risk",
            "company_id": company_id,
            "risk_type": risk_type,
            "description": description,
            "severity": severity,
        }

    def _process_intercompany_flows(self):
        txns = self.conn.execute(
            "SELECT * FROM intercompany_transactions WHERE status = 'active'"
        ).fetchall()

        total_flows = 0
        for tx in txns:
            daily_amount = tx["amount"] / 365.0 if tx["billing_cadence"] == "annual" else \
                           tx["amount"] / 91.25 if tx["billing_cadence"] == "quarterly" else \
                           tx["amount"] / 12 if tx["billing_cadence"] == "monthly" else \
                           tx["amount"] / 365.0

            from_company = self.conn.execute(
                "SELECT current_cash FROM companies WHERE id = ?", (tx["from_company_id"],)
            ).fetchone()
            to_company = self.conn.execute(
                "SELECT current_cash FROM companies WHERE id = ?", (tx["to_company_id"],)
            ).fetchone()

            if from_company and to_company:
                new_from_cash = from_company["current_cash"] - daily_amount
                new_to_cash = to_company["current_cash"] + daily_amount

                self.conn.execute(
                    "UPDATE companies SET current_cash = ?, updated_at = ? WHERE id = ?",
                    (new_from_cash, datetime.now(timezone.utc).isoformat(), tx["from_company_id"])
                )
                self.conn.execute(
                    "UPDATE companies SET current_cash = ?, updated_at = ? WHERE id = ?",
                    (new_to_cash, datetime.now(timezone.utc).isoformat(), tx["to_company_id"])
                )

                new_total = (tx["total_billed"] or 0) + daily_amount
                self.conn.execute(
                    "UPDATE intercompany_transactions SET total_billed = ?, last_billed_date = ?, updated_at = ? WHERE id = ?",
                    (new_total, self.sim_date.isoformat(), datetime.now(timezone.utc).isoformat(), tx["id"])
                )

                total_flows += daily_amount

        return total_flows

    def _update_company_state(self, company_id, daily_revenue, daily_costs, events):
        company = self.conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()

        new_cash = (company["current_cash"] or 0) + daily_revenue - daily_costs
        daily_ebitda = daily_revenue - daily_costs

        client_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM clients WHERE company_id = ? AND status = 'active'",
            (company_id,)
        ).fetchone()["cnt"]

        project_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM projects WHERE company_id = ? AND status = 'active'",
            (company_id,)
        ).fetchone()["cnt"]

        health = company["current_health"] or 100
        momentum = company["current_momentum"] or 0

        risk_events = [e for e in events if e.get("type") == "risk"]
        lost_events = [e for e in events if e.get("type") == "client_lost"]
        won_events = [e for e in events if e.get("type") == "client_won"]

        for r in risk_events:
            severity_penalty = {"low": -0.5, "medium": -1.5, "high": -3.0}.get(r["severity"], -0.5)
            health += severity_penalty

        health -= len(lost_events) * 2.0
        health += len(won_events) * 1.5
        health = max(0, min(100, health))

        if daily_ebitda > 0:
            momentum = min(10, momentum + 0.1)
        else:
            momentum = max(-10, momentum - 0.1)

        self.conn.execute("""
            UPDATE companies SET
                current_cash = ?,
                daily_revenue = ?,
                daily_costs = ?,
                daily_ebitda = ?,
                current_health = ?,
                current_momentum = ?,
                client_count = ?,
                active_project_count = ?,
                last_simulation_date = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            new_cash, daily_revenue, daily_costs, daily_ebitda,
            health, momentum, client_count, project_count,
            self.sim_date.isoformat(),
            datetime.now(timezone.utc).isoformat(),
            company_id,
        ))

        return {
            "cash": new_cash,
            "revenue": daily_revenue,
            "costs": daily_costs,
            "ebitda": daily_ebitda,
            "health": health,
            "momentum": momentum,
        }

    def _insert_event(self, event):
        affected = json.dumps([event["company_id"]]) if event.get("company_id") else "[]"
        severity = event.get("severity", "low")
        financial_impact = event.get("acv", 0) if event["type"] == "client_won" else \
                          -event.get("acv_lost", 0) if event["type"] == "client_lost" else 0

        self.conn.execute("""
            INSERT INTO events
            (event_type, source, title, description, affected_company_ids,
             impact_severity, financial_impact, published_date, processed, processed_at)
            VALUES (?, 'ecosystem_engine', ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            event["type"],
            event.get("description", event.get("reason", event.get("source", ""))),
            event.get("description", ""),
            affected,
            severity,
            financial_impact,
            self.sim_date.isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))

    def _advance_day(self):
        self.sim_day += 1
        self.sim_date += timedelta(days=1)
        self.conn.execute("""
            UPDATE simulation_state SET
                current_day = ?,
                current_date = ?,
                last_run = ?,
                status = 'running',
                updated_at = ?
            WHERE id = 1
        """, (
            self.sim_day,
            self.sim_date.isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))

    def _finalize_day(self, duration_ms, status="success", error=None):
        self.conn.execute("""
            INSERT INTO simulation_log
            (run_date, simulation_day, companies_processed, events_generated,
             revenue_generated, costs_incurred, ebitda_generated, intercompany_flows,
             duration_ms, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.sim_date.isoformat(),
            self.sim_day,
            self.day_log["companies_processed"],
            self.day_log["events_generated"],
            self.day_log["revenue_generated"],
            self.day_log["costs_incurred"],
            self.day_log["ebitda_generated"],
            self.day_log["intercompany_flows"],
            duration_ms,
            status,
            error,
        ))

        self.conn.execute("""
            UPDATE simulation_state SET status = ?, updated_at = ? WHERE id = 1
        """, ("idle" if status == "success" else "error", datetime.now(timezone.utc).isoformat()))

        self.conn.commit()

    def simulate_day(self):
        start = time.time()
        self._open()

        try:
            self._advance_day()
            market = self._get_market_conditions()
            companies = self.conn.execute("SELECT * FROM companies").fetchall()

            for company in companies:
                cid = company["id"]
                cname = company["brand_name"]
                self._seed_random(cid)

                clients = self._get_company_clients(cid)
                daily_revenue = self._get_daily_revenue(cid, clients, market)
                daily_costs = self._get_daily_costs(cid)

                day_events = []

                win = self._generate_client_win(cid, cname, market)
                if win:
                    day_events.append(win)

                loss = self._generate_client_loss(cid, cname, clients, market)
                if loss:
                    day_events.append(loss)

                risk = self._generate_risk_event(cid, cname, market)
                if risk:
                    day_events.append(risk)

                for ev in day_events:
                    self._insert_event(ev)

                result = self._update_company_state(cid, daily_revenue, daily_costs, day_events)

                self.day_log["revenue_generated"] += daily_revenue
                self.day_log["costs_incurred"] += daily_costs
                self.day_log["ebitda_generated"] += result["ebitda"]
                self.day_log["events_generated"] += len(day_events)
                self.day_log["companies_processed"] += 1

            intercompany_flows = self._process_intercompany_flows()
            self.day_log["intercompany_flows"] = intercompany_flows

            duration_ms = int((time.time() - start) * 1000)
            self._finalize_day(duration_ms)

            return {
                "day": self.sim_day,
                "date": self.sim_date.isoformat(),
                "market": self.market,
                "log": dict(self.day_log),
                "duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            self._finalize_day(duration_ms, status="error", error=str(e))
            raise
        finally:
            self._close()

    def simulate_period(self, days):
        results = []
        for i in range(days):
            result = self.simulate_day()
            results.append(result)
        return results

    def get_state(self):
        conn = get_connection(self.db_path)
        state = conn.execute("SELECT * FROM simulation_state WHERE id = 1").fetchone()
        companies = conn.execute("SELECT * FROM companies ORDER BY id").fetchall()
        recent_events = conn.execute(
            "SELECT * FROM events ORDER BY ingested_at DESC LIMIT 20"
        ).fetchall()
        recent_log = conn.execute(
            "SELECT * FROM simulation_log ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        conn.close()

        return {
            "state": dict(state) if state else None,
            "companies": [dict(c) for c in companies],
            "recent_events": [dict(e) for e in recent_events],
            "recent_log": [dict(l) for l in recent_log],
        }

    def get_ecosystem_json(self):
        conn = get_connection(self.db_path)

        companies = []
        for c in conn.execute("SELECT * FROM companies ORDER BY id").fetchall():
            company = {
                "id": c["id"],
                "legalName": c["legal_name"],
                "brandName": c["brand_name"],
                "category": c["category"],
                "yearFounded": c["year_founded"],
                "foundingDate": c["founding_date"],
                "ownershipStatus": c["ownership_status"],
                "mission": c["mission"],
                "vision": c["vision"],
                "headcount": {
                    "2026F": c["headcount_2026f"],
                    "fullTime": c["headcount_full_time"],
                    "contractors": c["headcount_contractors"],
                },
                "leadershipTeam": json.loads(c["leadership_team"] or "[]"),
                "serviceOfferings": json.loads(c["service_offerings"] or "[]"),
                "digitalPresence": json.loads(c["digital_presence"]) if c["digital_presence"] else None,
                "runtimeState": {
                    "cash": c["current_cash"],
                    "health": c["current_health"],
                    "momentum": c["current_momentum"],
                    "dailyRevenue": c["daily_revenue"],
                    "dailyCosts": c["daily_costs"],
                    "dailyEbitda": c["daily_ebitda"],
                    "clientCount": c["client_count"],
                    "activeProjectCount": c["active_project_count"],
                    "lastSimulationDate": c["last_simulation_date"],
                },
                "annualFinancials": [
                    dict(f) for f in conn.execute(
                        "SELECT * FROM company_financials WHERE company_id = ? ORDER BY year",
                        (c["id"],)
                    ).fetchall()
                ],
                "kpis2026F": {
                    k["kpi_key"]: k["kpi_value"] for k in conn.execute(
                        "SELECT * FROM company_kpis WHERE company_id = ?",
                        (c["id"],)
                    ).fetchall()
                },
                "revenueBreakdown2026F": [
                    dict(r) for r in conn.execute(
                        "SELECT * FROM revenue_breakdown WHERE company_id = ?",
                        (c["id"],)
                    ).fetchall()
                ],
            }
            companies.append(company)

        clients = [dict(c) for c in conn.execute("SELECT * FROM clients ORDER BY id").fetchall()]
        projects = [dict(p) for p in conn.execute("SELECT * FROM projects ORDER BY id").fetchall()]
        transactions = [dict(t) for t in conn.execute(
            "SELECT * FROM intercompany_transactions ORDER BY id"
        ).fetchall()]

        gp = conn.execute("SELECT * FROM group_profile WHERE id = 1").fetchone()
        group_profile = dict(gp) if gp else {}
        if group_profile.get("management_cadence"):
            group_profile["managementCadence"] = json.loads(group_profile["management_cadence"])

        alloc = conn.execute("SELECT * FROM allocation_summary WHERE id = 1").fetchone()
        hcf = {}
        if alloc:
            hcf["allocationSummary"] = dict(alloc)

        equity = [dict(e) for e in conn.execute(
            "SELECT * FROM capital_structure WHERE component_type = 'equity'"
        ).fetchall()]
        debt = [dict(d) for d in conn.execute(
            "SELECT * FROM capital_structure WHERE component_type = 'debt'"
        ).fetchall()]
        policy = conn.execute(
            "SELECT policy FROM capital_structure WHERE component_type = 'policy' LIMIT 1"
        ).fetchone()

        hcf["capitalStructureRousseau"] = {
            "commonEquity": equity,
            "debt": debt,
            "cashReservePolicy": policy["policy"] if policy else None,
        }
        hcf["subsidiaryInvestmentsAndLoans"] = [
            dict(i) for i in conn.execute("SELECT * FROM subsidiary_investments ORDER BY id").fetchall()
        ]
        hcf["dividendsAndDistributions"] = [
            dict(d) for d in conn.execute("SELECT * FROM dividends ORDER BY id").fetchall()
        ]

        rollup = conn.execute("SELECT * FROM group_rollup WHERE id = 1").fetchone()
        gr = {}
        if rollup:
            gr = dict(rollup)
            rev_rows = conn.execute("SELECT * FROM company_revenue_rollup ORDER BY company_id").fetchall()
            gr["standaloneRevenue2026F"] = {r["company_id"]: r["standalone_revenue_2026f"] for r in rev_rows}

        funds = [dict(f) for f in conn.execute("SELECT * FROM funds ORDER BY id").fetchall()]
        summary = conn.execute("SELECT * FROM allocation_summary WHERE id = 1").fetchone()
        fund_centre = {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "currency": "EUR",
            "funds": funds,
            "summary": {
                "totalAumEur": summary["fund_centre_aum_eur"] if summary else 0,
                "totalAumFormatted": f"{int(summary['fund_centre_aum_eur'] / 1e6):,} M EUR" if summary else "—",
                "averageYtdReturn": summary["fund_centre_avg_ytd_return"] if summary else 0,
                "averageAnnualisedReturn": summary["fund_centre_avg_annualised_return"] if summary else 0,
            } if summary else {},
        }

        sim_state = conn.execute("SELECT * FROM simulation_state WHERE id = 1").fetchone()

        risk_metrics = self._get_risk_metrics(conn)
        debt_instruments = self._get_debt_instruments(conn)

        conn.close()

        result = {
            "metadata": {
                "asOf": self.sim_date.isoformat() if self.sim_date else datetime.now(timezone.utc).date().isoformat(),
                "currency": "USD",
                "classification": "Living ecosystem — real-time operating data",
                "purpose": "Operating data for group management, planning, and intercompany analysis.",
                "source": "ecosystem_engine_v1",
                "simulationDay": sim_state["current_day"] if sim_state else 0,
                "simulationDate": sim_state["current_date"] if sim_state else None,
                "lastSimulationRun": sim_state["last_run"] if sim_state else None,
                "marketCondition": self.market if hasattr(self, 'market') and self.market else "unknown",
            },
            "reportingDimensions": {
                "companyIds": [c["id"] for c in companies],
                "clientStatus": ["active", "renewal_due", "pipeline", "paused", "closed_won", "closed_lost"],
                "projectStage": ["discovery", "proposal", "contracted", "in_delivery", "at_risk", "complete"],
                "confidence": ["actual", "forecast", "scenario"],
            },
            "groupProfile": group_profile,
            "companies": companies,
            "clientDatabase": clients,
            "majorProjectsPipeline": projects,
            "intercompanyTransactions2026F": transactions,
            "holdingsAndCapitalFlow": hcf,
            "groupRollup": gr,
            "fundCentre": fund_centre,
            "riskMetrics": risk_metrics,
            "debtInstruments": debt_instruments,
        }
        network_map = _get_static_network_map()
        if network_map:
            result["networkMap"] = network_map
        bgc_directory = _get_static_bgc_directory()
        if bgc_directory:
            result["bgcDirectory"] = bgc_directory
        return result

    def _get_risk_metrics(self, conn):
        row = conn.execute(
            "SELECT * FROM risk_metrics ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        if result.get('alerts'):
            result['alerts'] = json.loads(result['alerts'])
        return result

    def _get_debt_instruments(self, conn):
        rows = conn.execute("SELECT * FROM debt_instruments ORDER BY id").fetchall()
        instruments = []
        for r in rows:
            d = dict(r)
            if d.get('covenants'):
                d['covenants'] = json.loads(d['covenants'])
            instruments.append(d)
        return instruments


if __name__ == "__main__":
    engine = EcosystemEngine()
    print("Simulating 7 days...")
    results = engine.simulate_period(7)
    for r in results:
        print(f"  Day {r['day']} ({r['date']}): market={r['market']}, "
              f"revenue=${r['log']['revenue_generated']:,.0f}, "
              f"events={r['log']['events_generated']}, "
              f"duration={r['duration_ms']}ms")

    print("\nCurrent state:")
    state = engine.get_state()
    for c in state["companies"]:
        print(f"  {c['brand_name']:30s}  cash=${c['current_cash']:>12,.0f}  "
              f"health={c['current_health']:5.1f}  "
              f"momentum={c['current_momentum']:+.1f}  "
              f"clients={c['client_count']}")

    print(f"\nRecent events ({len(state['recent_events'])}):")
    for e in state["recent_events"][:5]:
        print(f"  [{e['published_date']}] {e['event_type']}: {e['description'][:60]}")
