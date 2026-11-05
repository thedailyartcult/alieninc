"""
Alien.Inc Ecosystem — JSON → Database Migration
Populates the SQLite database from alieninc-ecosystem.json.
Safe to re-run: uses INSERT OR REPLACE for idempotency.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import get_connection, init_db, is_initialized, DB_PATH, JSON_PATH


def load_json(json_path=None):
    path = json_path or JSON_PATH
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def migrate(data, db_path=None):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc).isoformat()

    _migrate_simulation_state(conn, now)
    _migrate_group_profile(conn, data)
    _migrate_companies(conn, data, now)
    _migrate_financials(conn, data)
    _migrate_kpis(conn, data)
    _migrate_revenue_breakdown(conn, data)
    _migrate_clients(conn, data, now)
    _migrate_projects(conn, data, now)
    _migrate_intercompany_transactions(conn, data, now)
    _migrate_debt_instruments(conn, data, now)
    _migrate_holdings_and_capital(conn, data, now)
    _migrate_fund_centre(conn, data, now)
    _migrate_fund_share_classes(conn, data, now)
    _migrate_group_rollup(conn, data, now)

    conn.commit()
    conn.close()
    print(f"Migration complete at {now}")


def _migrate_simulation_state(conn, now):
    conn.execute("""
        INSERT OR REPLACE INTO simulation_state (id, current_day, current_date, last_run, status, created_at, updated_at)
        VALUES (1, 0, ?, NULL, 'migrated', ?, ?)
    """, (now[:10], now, now))


def _migrate_group_profile(conn, data):
    gp = data.get('groupProfile', {})
    cadence = gp.get('managementCadence', {})
    conn.execute("""
        INSERT OR REPLACE INTO group_profile (id, name, founded, description, history, operating_thesis, management_cadence)
        VALUES (1, ?, ?, ?, ?, ?, ?)
    """, (
        gp.get('name', 'Alien.Inc'),
        gp.get('founded'),
        gp.get('description'),
        gp.get('history'),
        gp.get('operatingThesis'),
        json.dumps(cadence) if cadence else None,
    ))


def _migrate_companies(conn, data, now):
    for c in data.get('companies', []):
        financials = c.get('annualFinancials', [])
        current_cash = financials[-1]['cashEnding'] if financials else 0

        headcount = c.get('headcount', {})
        leadership = c.get('leadershipTeam', [])
        services = c.get('serviceOfferings', [])
        digital = c.get('digitalPresence', {})

        conn.execute("""
            INSERT OR REPLACE INTO companies
            (id, legal_name, brand_name, category, year_founded, founding_date,
             ownership_status, mission, vision,
             headcount_2026f, headcount_full_time, headcount_contractors,
             leadership_team, service_offerings, digital_presence,
             current_cash, current_health, current_momentum,
             client_count, last_simulation_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 100, 0, ?, NULL, ?, ?)
        """, (
            c['id'],
            c.get('legalName', ''),
            c.get('brandName', ''),
            c.get('category'),
            c.get('yearFounded'),
            c.get('foundingDate'),
            c.get('ownershipStatus'),
            c.get('mission'),
            c.get('vision'),
            headcount.get('2026F', 0),
            headcount.get('fullTime', 0),
            headcount.get('contractors', 0),
            json.dumps(leadership),
            json.dumps(services),
            json.dumps(digital) if digital else None,
            current_cash,
            _count_clients(data, c['id']),
            now, now,
        ))


def _count_clients(data, company_id):
    return sum(1 for cl in data.get('clientDatabase', []) if cl.get('companyId') == company_id)


def _migrate_financials(conn, data):
    for c in data.get('companies', []):
        for fin in c.get('annualFinancials', []):
            conn.execute("""
                INSERT OR REPLACE INTO company_financials
                (company_id, year, confidence, revenue, operating_costs, ebitda, cash_ending)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                c['id'],
                fin['year'],
                fin.get('confidence', 'forecast'),
                fin.get('revenue', 0),
                fin.get('operatingCosts', 0),
                fin.get('ebitda', 0),
                fin.get('cashEnding', 0),
            ))


def _migrate_kpis(conn, data):
    for c in data.get('companies', []):
        kpis = c.get('kpis2026F', {})
        for key, value in kpis.items():
            conn.execute("""
                INSERT OR REPLACE INTO company_kpis (company_id, period, kpi_key, kpi_value)
                VALUES (?, '2026F', ?, ?)
            """, (c['id'], key, value))


def _migrate_revenue_breakdown(conn, data):
    for c in data.get('companies', []):
        for rb in c.get('revenueBreakdown2026F', []):
            conn.execute("""
                INSERT OR REPLACE INTO revenue_breakdown
                (company_id, period, service_line_id, amount, share)
                VALUES (?, '2026F', ?, ?, ?)
            """, (c['id'], rb.get('serviceLineId'), rb.get('amount', 0), rb.get('share', 0)))


def _migrate_clients(conn, data, now):
    for cl in data.get('clientDatabase', []):
        conn.execute("""
            INSERT OR REPLACE INTO clients
            (id, company_id, client_name, industry, country, segment,
             service_line_id, annual_contract_value, status,
             start_date, renewal_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cl['clientId'],
            cl['companyId'],
            cl['clientName'],
            cl.get('industry'),
            cl.get('country'),
            cl.get('segment'),
            cl.get('serviceLineId'),
            cl.get('annualContractValue', 0),
            cl.get('status', 'active'),
            cl.get('startDate'),
            cl.get('renewalDate'),
            now, now,
        ))


def _migrate_projects(conn, data, now):
    for p in data.get('majorProjectsPipeline', []):
        conn.execute("""
            INSERT OR REPLACE INTO projects
            (id, company_id, name, client_id, stage, expected_revenue,
             gross_margin_target, probability, start_date, expected_close_date,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p['projectId'],
            p['companyId'],
            p['name'],
            p.get('clientId'),
            p.get('stage', 'discovery'),
            p.get('expectedRevenue', 0),
            p.get('grossMarginTarget', 0),
            p.get('probability', 0),
            p.get('startDate'),
            p.get('expectedCloseDate'),
            now, now,
        ))


def _migrate_intercompany_transactions(conn, data, now):
    for tx in data.get('intercompanyTransactions2026F', []):
        conn.execute("""
            INSERT OR REPLACE INTO intercompany_transactions
            (id, from_company_id, to_company_id, tx_type, description,
             amount, billing_cadence, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx['transactionId'],
            tx['fromCompanyId'],
            tx['toCompanyId'],
            tx.get('type', 'service_fee'),
            tx.get('description'),
            tx.get('amount', 0),
            tx.get('billingCadence'),
            tx.get('status', 'active'),
            now, now,
        ))


def _migrate_holdings_and_capital(conn, data, now):
    hcf = data.get('holdingsAndCapitalFlow', {})

    cs = hcf.get('capitalStructureRousseau', {})
    for eq in cs.get('commonEquity', []):
        conn.execute("""
            INSERT INTO capital_structure (component_type, holder, ownership_pct)
            VALUES ('equity', ?, ?)
        """, (eq.get('holder'), eq.get('ownershipPct', 0)))

    for debt in cs.get('debt', []):
        conn.execute("""
            INSERT INTO capital_structure (component_type, instrument, principal_outstanding, interest_rate, maturity)
            VALUES ('debt', ?, ?, ?, ?)
        """, (debt.get('instrument'), debt.get('principalOutstanding', 0), debt.get('interestRate', 0), debt.get('maturity')))

    if cs.get('cashReservePolicy'):
        conn.execute("""
            INSERT INTO capital_structure (component_type, policy)
            VALUES ('policy', ?)
        """, (cs['cashReservePolicy'],))

    for inv in hcf.get('subsidiaryInvestmentsAndLoans', []):
        conn.execute("""
            INSERT OR REPLACE INTO subsidiary_investments
            (recipient_company_id, instrument, amount, date, purpose, interest_rate, principal_outstanding, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inv.get('recipientCompanyId'),
            inv.get('instrument'),
            inv.get('amount', 0),
            inv.get('date'),
            inv.get('purpose'),
            inv.get('interestRate', 0),
            inv.get('amount', 0),
            inv.get('status', 'funded'),
        ))

    for div in hcf.get('dividendsAndDistributions', []):
        conn.execute("""
            INSERT INTO dividends (from_company_id, to_company_id, year, amount, basis, status)
            VALUES (?, ?, ?, ?, ?, 'paid')
        """, (
            div.get('fromCompanyId'),
            div.get('toCompanyId'),
            div.get('year'),
            div.get('amount', 0),
            div.get('basis'),
        ))

    alloc = hcf.get('allocationSummary', {})
    if alloc:
        conn.execute("""
            INSERT OR REPLACE INTO allocation_summary
            (id, total_equity_pct, total_debt_outstanding, weighted_avg_debt_rate,
             total_capital_deployed, dividends_received_2025, dividends_forecast_2026,
             subsidiary_cash_position, parent_cash_position, consolidated_cash_position,
             fund_centre_aum_eur, fund_centre_avg_ytd_return, fund_centre_avg_annualised_return,
             liquidity_months, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alloc.get('totalEquityPct', 1.0),
            alloc.get('totalDebtOutstanding', 0),
            alloc.get('weightedAverageDebtRate', 0),
            alloc.get('totalCapitalDeployedToSubsidiaries', 0),
            alloc.get('dividendsReceived2025', 0),
            alloc.get('dividendsForecast2026', 0),
            alloc.get('subsidiaryCashPosition2026F', 0),
            alloc.get('parentCashPosition2026F', 0),
            alloc.get('consolidatedCashPosition2026F', 0),
            alloc.get('fundCentreAumEur', 0),
            alloc.get('fundCentreAverageYtdReturn', 0),
            alloc.get('fundCentreAverageAnnualisedReturn', 0),
            alloc.get('liquidityMonthsOfOperatingCosts', 0),
            now,
        ))


def _migrate_debt_instruments(conn, data, now):
    hcf = data.get('holdingsAndCapitalFlow', {})
    cs = hcf.get('capitalStructureRousseau', {})

    conn.execute("""
        INSERT OR REPLACE INTO debt_instruments
        (id, name, instrument_type, principal_outstanding, interest_rate,
         maturity_date, holder, covenants, covenant_threshold,
         covenant_metric, covenant_status, covenant_headroom_pct,
         last_checked, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        'founder-note',
        'Founder note',
        'promissory_note',
        420000,
        0.045,
        '2028-12-31',
        'Founder group',
        json.dumps({
            "type": "payment_deferral",
            "trigger": "parent_cash_below_6_months_operating_costs",
            "remedy": "immediate_full_repayment_or_restructure",
        }),
        6.0,
        'parent_runway_months',
        'compliant',
        268.0,
        now, now, now,
    ))

    conn.execute("""
        INSERT OR REPLACE INTO debt_instruments
        (id, name, instrument_type, principal_outstanding, interest_rate,
         maturity_date, holder, covenants, covenant_threshold,
         covenant_metric, covenant_status, covenant_headroom_pct,
         last_checked, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        'working-capital-line',
        'Working capital line',
        'credit_facility',
        185000,
        0.0825,
        '2027-06-30',
        'Commercial lender',
        json.dumps({
            "type": "nav_covenant",
            "trigger": "weighted_avg_fund_nav_below_130",
            "remedy": "full_repayment_demanded",
            "description": "Weighted average fund centre NAV index must remain above 130. Breach entitles lender to demand full $185,000 repayment immediately.",
        }),
        130.0,
        'fund_centre_nav_index',
        'compliant',
        None,
        now, now, now,
    ))


def _migrate_fund_centre(conn, data, now):
    fc = data.get('fundCentre', {})
    for fund in fc.get('funds', []):
        conn.execute("""
            INSERT OR REPLACE INTO funds
            (id, name, category, inception_date, nav_latest, nav_currency,
             ytd_return, annualised_return, aum, benchmark, risk_rating, ter,
             status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """, (
            fund.get('id'),
            fund.get('name'),
            fund.get('category'),
            fund.get('inceptionDate'),
            fund.get('navLatest'),
            fund.get('navCurrency', 'EUR'),
            fund.get('ytdReturn'),
            fund.get('annualisedReturn'),
            fund.get('aum'),
            fund.get('benchmark'),
            fund.get('riskRating'),
            fund.get('ter'),
            now,
        ))


def _migrate_fund_share_classes(conn, data, now):
    fc = data.get('fundCentre', {})
    for fund in fc.get('funds', []):
        fund_id = fund.get('id')
        for sc in fund.get('shareClasses', []):
            perf = sc.get('performance', {})
            conn.execute("""
                INSERT INTO fund_share_classes
                (fund_id, name, isin, nav, nav_date, annualised_return,
                 inception_date, ytd_return, one_year_return,
                 three_year_return, five_year_return, ten_year_return,
                 volatility_3y, aum, aum_formatted, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fund_id,
                sc.get('name'),
                sc.get('isin'),
                sc.get('nav', 0),
                sc.get('navDate'),
                sc.get('annualisedReturn', 0),
                sc.get('inceptionDate'),
                perf.get('ytd', 0),
                perf.get('oneYear', 0),
                perf.get('threeYear', 0),
                perf.get('fiveYear', 0),
                perf.get('tenYear'),
                sc.get('volatility3Year', 0),
                sc.get('aum', 0),
                sc.get('aumFormatted'),
                now,
            ))


def _migrate_group_rollup(conn, data, now):
    gr = data.get('groupRollup', {})
    if gr:
        conn.execute("""
            INSERT OR REPLACE INTO group_rollup
            (id, standalone_revenue_total, intercompany_revenue, external_revenue,
             standalone_ebitda_total, largest_external_revenue_company,
             highest_recurring_revenue_company, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        """, (
            gr.get('standaloneRevenueTotal2026F', 0),
            gr.get('estimatedIntercompanyRevenue2026F', 0),
            gr.get('estimatedExternalRevenue2026F', 0),
            gr.get('standaloneEbitdaTotal2026F', 0),
            gr.get('largestExternalRevenueCompany'),
            gr.get('highestRecurringRevenueCompany'),
            now,
        ))

        rev = gr.get('standaloneRevenue2026F', {})
        for company_id, revenue in rev.items():
            conn.execute("""
                INSERT OR REPLACE INTO company_revenue_rollup (company_id, standalone_revenue_2026f, updated_at)
                VALUES (?, ?, ?)
            """, (company_id, revenue, now))


def print_summary(db_path=None):
    conn = get_connection(db_path)
    tables = ['companies', 'clients', 'projects', 'intercompany_transactions',
              'company_financials', 'company_kpis', 'funds', 'fund_share_classes',
              'debt_instruments', 'risk_metrics', 'events', 'simulation_log']
    print("\n=== Database Summary ===")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")
    conn.close()


if __name__ == '__main__':
    if not is_initialized():
        init_db()
        print("Database initialized")

    data = load_json()
    migrate(data)
    print_summary()
