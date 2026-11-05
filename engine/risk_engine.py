"""
Alien.Inc Risk Metrics Engine
Calculates and records group-wide risk metrics after each operating cycle.
Tracks debt covenant compliance, subsidiary cash floors, contagion risk,
and fund centre NAV sensitivity.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db'))
from schema import get_connection, DB_PATH

SUBSIDIARY_CASH_FLOOR_MONTHS = 4.0
CONTAGION_ALERT_THRESHOLD = 2
PARENT_RUNWAY_WARNING_MONTHS = 9.0
PARENT_RUNWAY_CRITICAL_MONTHS = 6.0
COVENANT_HEADROOM_WARNING_PCT = 20.0
COVENANT_HEADROOM_CRITICAL_PCT = 10.0


class RiskEngine:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH

    def calculate_and_record(self, sim_day=None, sim_date=None):
        conn = get_connection(self.db_path)
        try:
            metrics = self._calculate(conn)

            alerts = self._generate_alerts(metrics)
            metrics['alerts'] = json.dumps(alerts) if alerts else None
            metrics['risk_score'] = self._calculate_risk_score(metrics, alerts)

            conn.execute("""
                INSERT INTO risk_metrics
                (recorded_at, simulation_day, debt_service_coverage_months,
                 parent_runway_months, avg_subsidiary_runway_months,
                 min_subsidiary_runway_months, min_runway_company_id,
                 contagion_count, total_intercompany_exposure,
                 intercompany_to_parent_cash_pct, fund_centre_nav_index,
                 fund_centre_aum_eur, covenant_headroom_pct,
                 covenant_status, risk_score, alerts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                sim_day or 0,
                metrics['debt_service_coverage_months'],
                metrics['parent_runway_months'],
                metrics['avg_subsidiary_runway_months'],
                metrics['min_subsidiary_runway_months'],
                metrics['min_runway_company_id'],
                metrics['contagion_count'],
                metrics['total_intercompany_exposure'],
                metrics['intercompany_to_parent_cash_pct'],
                metrics['fund_centre_nav_index'],
                metrics['fund_centre_aum_eur'],
                metrics['covenant_headroom_pct'],
                metrics['covenant_status'],
                metrics['risk_score'],
                metrics['alerts'],
            ))

            self._update_covenant_status(conn, metrics)

            conn.commit()
            return metrics
        finally:
            conn.close()

    def _calculate(self, conn):
        companies = conn.execute("SELECT * FROM companies").fetchall()
        parent = None
        subsidiaries = []
        for c in companies:
            if c['id'] == 'rousseau':
                parent = c
            else:
                subsidiaries.append(c)

        parent_cash = parent['current_cash'] or 0
        parent_fin = conn.execute(
            "SELECT * FROM company_financials WHERE company_id = 'rousseau' ORDER BY year DESC LIMIT 1"
        ).fetchone()
        parent_annual_costs = parent_fin['operating_costs'] if parent_fin else 562000
        parent_monthly_burn = parent_annual_costs / 12.0
        parent_runway = parent_cash / parent_monthly_burn if parent_monthly_burn > 0 else 999

        total_debt = conn.execute(
            "SELECT SUM(principal_outstanding) as total FROM debt_instruments"
        ).fetchone()['total'] or 0
        monthly_debt_service = 0
        debts = conn.execute("SELECT * FROM debt_instruments").fetchall()
        for d in debts:
            monthly_debt_service += (d['principal_outstanding'] or 0) * (d['interest_rate'] or 0) / 12.0

        total_monthly_obligation = parent_monthly_burn + monthly_debt_service
        debt_service_coverage = parent_cash / total_monthly_obligation if total_monthly_obligation > 0 else 999

        sub_runways = []
        for s in subsidiaries:
            sub_cash = s['current_cash'] or 0
            sub_fin = conn.execute(
                "SELECT * FROM company_financials WHERE company_id = ? ORDER BY year DESC LIMIT 1",
                (s['id'],)
            ).fetchone()
            sub_costs = sub_fin['operating_costs'] if sub_fin else 0
            sub_monthly = sub_costs / 12.0
            runway = sub_cash / sub_monthly if sub_monthly > 0 else 999
            sub_runways.append({
                'company_id': s['id'],
                'brand_name': s['brand_name'],
                'cash': sub_cash,
                'monthly_costs': sub_monthly,
                'runway': runway,
            })

        avg_sub_runway = sum(r['runway'] for r in sub_runways) / len(sub_runways) if sub_runways else 0
        min_sub = min(sub_runways, key=lambda r: r['runway']) if sub_runways else {'runway': 0, 'company_id': 'none'}
        min_sub_runway = min_sub['runway']
        min_runway_company = min_sub['company_id']

        contagion_count = sum(1 for r in sub_runways if r['runway'] < SUBSIDIARY_CASH_FLOOR_MONTHS)

        intercompany_loans = conn.execute("""
            SELECT SUM(principal_outstanding) as total FROM subsidiary_investments
            WHERE status IN ('outstanding', 'partially_repaid', 'amortizing')
        """).fetchone()
        total_intercompany_exposure = intercompany_loans['total'] if intercompany_loans else 0
        intercompany_to_parent_pct = (total_intercompany_exposure / parent_cash * 100) if parent_cash > 0 else 0

        nav_data = self._calculate_nav_index(conn)
        fund_nav_index = nav_data['weighted_nav_index']
        fund_aum = nav_data['total_aum']

        nav_covenant = conn.execute("""
            SELECT * FROM debt_instruments
            WHERE covenant_metric = 'fund_centre_nav_index' AND instrument_type = 'credit_facility'
            LIMIT 1
        """).fetchone()

        covenant_headroom = None
        covenant_status = 'compliant'
        if nav_covenant:
            threshold = nav_covenant['covenant_threshold'] or 130
            if fund_nav_index > 0:
                covenant_headroom = ((fund_nav_index - threshold) / threshold) * 100
                if fund_nav_index <= threshold:
                    covenant_status = 'breached'
                elif covenant_headroom < COVENANT_HEADROOM_CRITICAL_PCT:
                    covenant_status = 'critical'
                elif covenant_headroom < COVENANT_HEADROOM_WARNING_PCT:
                    covenant_status = 'warning'

        return {
            'debt_service_coverage_months': round(debt_service_coverage, 1),
            'parent_runway_months': round(parent_runway, 1),
            'avg_subsidiary_runway_months': round(avg_sub_runway, 1),
            'min_subsidiary_runway_months': round(min_sub_runway, 1),
            'min_runway_company_id': min_runway_company,
            'contagion_count': contagion_count,
            'total_intercompany_exposure': round(total_intercompany_exposure, 0),
            'intercompany_to_parent_cash_pct': round(intercompany_to_parent_pct, 1),
            'fund_centre_nav_index': round(fund_nav_index, 2),
            'fund_centre_aum_eur': round(fund_aum, 0),
            'covenant_headroom_pct': round(covenant_headroom, 1) if covenant_headroom is not None else None,
            'covenant_status': covenant_status,
            'total_debt': round(total_debt, 0),
            'monthly_debt_service': round(monthly_debt_service, 0),
            'parent_cash': round(parent_cash, 0),
            'subsidiary_runways': sub_runways,
        }

    def _calculate_nav_index(self, conn):
        share_classes = conn.execute("""
            SELECT fsc.*, f.name as fund_name
            FROM fund_share_classes fsc
            JOIN funds f ON fsc.fund_id = f.id
        """).fetchall()

        if not share_classes:
            return {'weighted_nav_index': 100, 'total_aum': 0}

        fund_aums = {}
        for sc in share_classes:
            fid = sc['fund_id']
            if fid not in fund_aums:
                fund_aums[fid] = sc['aum'] or 0

        total_aum = sum(fund_aums.values())

        weighted_nav = 0
        for sc in share_classes:
            fid = sc['fund_id']
            fund_total_aum = fund_aums.get(fid, 0)
            if fund_total_aum == 0:
                continue
            nav = sc['nav'] or 0
            inception_nav = 100
            nav_index = (nav / inception_nav) * 100 if inception_nav > 0 else 100
            share_class_weight = (sc['aum'] or 0) / (fund_total_aum * (1 if fund_total_aum == (sc['aum'] or 0) else 2))
            weighted_nav += nav_index * share_class_weight

        weighted_nav_index = weighted_nav if total_aum > 0 else 100

        weighted_nav = 0
        for fid, aum in fund_aums.items():
            fund_scs = [sc for sc in share_classes if sc['fund_id'] == fid]
            if fund_scs:
                avg_nav = sum(sc['nav'] or 0 for sc in fund_scs) / len(fund_scs)
                nav_index = (avg_nav / 100) * 100
                weighted_nav += nav_index * (aum / total_aum if total_aum > 0 else 0)

        weighted_nav_index = weighted_nav

        return {
            'weighted_nav_index': weighted_nav_index,
            'total_aum': total_aum,
        }

    def _generate_alerts(self, metrics):
        alerts = []

        if metrics['covenant_status'] == 'breached':
            alerts.append({
                'severity': 'critical',
                'type': 'covenant_breach',
                'message': 'DEBT COVENANT BREACHED — weighted fund NAV below 130 threshold. Lender entitled to demand full $185,000 repayment.',
                'metric': 'fund_centre_nav_index',
                'value': metrics['fund_centre_nav_index'],
                'threshold': 130,
            })
        elif metrics['covenant_status'] == 'critical':
            alerts.append({
                'severity': 'critical',
                'type': 'covenant_approaching_breach',
                'message': 'Covenant headroom below 10%% — NAV at %.2f vs 130 threshold' % metrics['fund_centre_nav_index'],
                'metric': 'fund_centre_nav_index',
                'value': metrics['fund_centre_nav_index'],
            })
        elif metrics['covenant_status'] == 'warning':
            alerts.append({
                'severity': 'high',
                'type': 'covenant_warning',
                'message': 'Covenant headroom below 20%% — monitoring fund NAV closely (%.2f vs 130)' % metrics['fund_centre_nav_index'],
                'metric': 'fund_centre_nav_index',
                'value': metrics['fund_centre_nav_index'],
            })

        if metrics['parent_runway_months'] < PARENT_RUNWAY_CRITICAL_MONTHS:
            alerts.append({
                'severity': 'critical',
                'type': 'parent_runway_critical',
                'message': 'Rousseau cash runway below 6 months (%.1f months)' % metrics['parent_runway_months'],
                'metric': 'parent_runway_months',
                'value': metrics['parent_runway_months'],
            })
        elif metrics['parent_runway_months'] < PARENT_RUNWAY_WARNING_MONTHS:
            alerts.append({
                'severity': 'high',
                'type': 'parent_runway_warning',
                'message': 'Rousseau cash runway below 9 months (%.1f months)' % metrics['parent_runway_months'],
                'metric': 'parent_runway_months',
                'value': metrics['parent_runway_months'],
            })

        if metrics['contagion_count'] >= CONTAGION_ALERT_THRESHOLD:
            alerts.append({
                'severity': 'critical',
                'type': 'contagion_alert',
                'message': '%d subsidiaries below %g-month cash floor — cascading failure risk' % (
                    metrics['contagion_count'], SUBSIDIARY_CASH_FLOOR_MONTHS),
                'metric': 'contagion_count',
                'value': metrics['contagion_count'],
            })
        elif metrics['contagion_count'] > 0:
            alerts.append({
                'severity': 'high',
                'type': 'subsidiary_cash_warning',
                'message': '%s runway at %.1f months (below %.0f-month floor)' % (
                    metrics['min_runway_company_id'],
                    metrics['min_subsidiary_runway_months'],
                    SUBSIDIARY_CASH_FLOOR_MONTHS),
                'metric': 'min_subsidiary_runway_months',
                'value': metrics['min_subsidiary_runway_months'],
            })

        if metrics['intercompany_to_parent_cash_pct'] > 80:
            alerts.append({
                'severity': 'high',
                'type': 'intercompany_exposure',
                'message': 'Intercompany loans at %.0f%% of parent cash — high recall concentration' % metrics['intercompany_to_parent_cash_pct'],
                'metric': 'intercompany_to_parent_cash_pct',
                'value': metrics['intercompany_to_parent_cash_pct'],
            })

        return alerts

    def _calculate_risk_score(self, metrics, alerts):
        score = 0
        severity_weights = {'critical': 30, 'high': 15, 'medium': 5, 'low': 2}
        for alert in alerts:
            score += severity_weights.get(alert['severity'], 0)

        if metrics['parent_runway_months'] < PARENT_RUNWAY_WARNING_MONTHS:
            score += 10
        if metrics['contagion_count'] > 0:
            score += metrics['contagion_count'] * 10
        if metrics['covenant_status'] != 'compliant':
            score += 20

        return min(100, score)

    def _update_covenant_status(self, conn, metrics):
        conn.execute("""
            UPDATE debt_instruments
            SET covenant_status = ?,
                covenant_headroom_pct = ?,
                last_checked = ?,
                updated_at = ?
            WHERE covenant_metric = 'fund_centre_nav_index'
        """, (
            metrics['covenant_status'],
            metrics['covenant_headroom_pct'],
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))

    def get_latest(self):
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM risk_metrics ORDER BY recorded_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            if result.get('alerts'):
                result['alerts'] = json.loads(result['alerts'])
            return result
        finally:
            conn.close()

    def get_history(self, limit=30):
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM risk_metrics ORDER BY recorded_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if d.get('alerts'):
                    d['alerts'] = json.loads(d['alerts'])
                results.append(d)
            return results
        finally:
            conn.close()


if __name__ == "__main__":
    engine = RiskEngine()
    metrics = engine.calculate_and_record(sim_day=0, sim_date=datetime.now(timezone.utc).date().isoformat())

    print("=" * 72)
    print("  RISK METRICS — LATEST ASSESSMENT")
    print("=" * 72)
    print()
    print("  COVENANT STATUS: %s" % metrics['covenant_status'].upper())
    print("  Fund centre NAV index: %.2f (threshold: 130)" % metrics['fund_centre_nav_index'])
    if metrics['covenant_headroom_pct'] is not None:
        print("  Covenant headroom: %.1f%%" % metrics['covenant_headroom_pct'])
    print()
    print("  PARENT (Rousseau):")
    print("    Cash: $%s" % "{:,.0f}".format(metrics['parent_cash']))
    print("    Runway: %.1f months" % metrics['parent_runway_months'])
    print("    Debt service coverage: %.1f months" % metrics['debt_service_coverage_months'])
    print("    Total debt: $%s" % "{:,.0f}".format(metrics['total_debt']))
    print()
    print("  SUBSIDIARIES:")
    print("    Average runway: %.1f months" % metrics['avg_subsidiary_runway_months'])
    print("    Minimum runway: %.1f months (%s)" % (metrics['min_subsidiary_runway_months'], metrics['min_runway_company_id']))
    print("    Contagion count: %d below %.0f-month floor" % (metrics['contagion_count'], SUBSIDIARY_CASH_FLOOR_MONTHS))
    print()
    print("  INTERCOMPANY:")
    print("    Total exposure: $%s" % "{:,.0f}".format(metrics['total_intercompany_exposure']))
    print("    Exposure vs parent cash: %.1f%%" % metrics['intercompany_to_parent_cash_pct'])
    print()
    print("  FUND CENTRE:")
    print("    NAV index: %.2f" % metrics['fund_centre_nav_index'])
    print("    Total AUM: EUR %s" % "{:,.0f}".format(metrics['fund_centre_aum_eur']))
    print()

    alerts = metrics.get('alerts')
    if isinstance(alerts, str):
        alerts = json.loads(alerts) if alerts else []
    if alerts:
        print("  ALERTS (%d):" % len(alerts))
        for a in alerts:
            print("    [%s] %s: %s" % (a['severity'].upper(), a['type'], a['message']))
    else:
        print("  No active alerts.")
    print()
    print("  RISK SCORE: %d/100" % metrics['risk_score'])
    print()
