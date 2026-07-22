#!/usr/bin/env python3
"""
Alien.Inc Ecosystem — Operations Runner
Designed to be called by cron every 15 minutes.
Runs one operating cycle per execution, with catch-up logic.
"""

import sys
import os
import json
import time
import argparse
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schema import get_connection, init_db, is_initialized, DB_PATH
from ecosystem_engine import EcosystemEngine

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'ecosystem.log')),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger('ecosystem.runner')


def run_once():
    engine = EcosystemEngine()
    result = engine.simulate_day()
    log.info(
        "Day %d (%s): market=%s revenue=$%.0f costs=$%.0f ebitda=$%.0f "
        "events=%d companies=%d intercompany=$%.0f duration=%dms",
        result["day"], result["date"], result["market"],
        result["log"]["revenue_generated"],
        result["log"]["costs_incurred"],
        result["log"]["ebitda_generated"],
        result["log"]["events_generated"],
        result["log"]["companies_processed"],
        result["log"]["intercompany_flows"],
        result["duration_ms"],
    )

    try:
        from risk_engine import RiskEngine
        risk = RiskEngine()
        metrics = risk.calculate_and_record(sim_day=result["day"], sim_date=result["date"])
        if metrics:
            alerts = metrics.get('alerts', '[]')
            if isinstance(alerts, str):
                import json as _json
                alerts = _json.loads(alerts) if alerts else []
            if alerts:
                for a in alerts:
                    log.warning("RISK [%s] %s: %s", a['severity'].upper(), a['type'], a['message'])
            log.info("Risk score: %d/100, covenant: %s, runway: %.1f months",
                     metrics['risk_score'], metrics['covenant_status'],
                     metrics['parent_runway_months'])
    except Exception as e:
        log.warning("Risk calculation skipped: %s", e)

    try:
        from ontology import enrich_entities, detect_cross_company_relationships, detect_risk_patterns
        from action_engine import initialize_rules, evaluate_rules
        initialize_rules()
        enriched = enrich_entities()
        if enriched['enriched'] > 0:
            log.info("Ontology: enriched %d entities", enriched['enriched'])
        cross = detect_cross_company_relationships()
        if cross['cross_links_created'] > 0:
            log.info("Ontology: %d cross-company links", cross['cross_links_created'])
        patterns = detect_risk_patterns()
        if patterns['patterns_detected'] > 0:
            log.info("Ontology: %d risk patterns detected", patterns['patterns_detected'])
            action_result = evaluate_rules(alerts=patterns.get('alerts', []))
            if action_result['executions'] > 0:
                log.info("AIP: %d actions triggered", action_result['executions'])
    except Exception as e:
        log.warning("Ontology/AIP skipped: %s", e)

    return result


def run_gdelt():
    try:
        from gdelt_ingestor import ingest_once, process_pending_events
        log.info("Starting GDELT ingestion...")
        gdelt_count = ingest_once()
        log.info("GDELT: ingested %d news events", gdelt_count)
        if gdelt_count > 0:
            processed = process_pending_events()
            log.info("GDELT: processed %d pending events", processed)
    except Exception as e:
        log.warning("GDELT ingestion failed: %s", e)


def run_catchup(target_days=None):
    conn = get_connection()
    state = conn.execute("SELECT * FROM simulation_state WHERE id = 1").fetchone()
    conn.close()

    if not state:
        log.info("No ecosystem state found — starting fresh")
        return run_once()

    last_date = datetime.strptime(state["current_date"], "%Y-%m-%d").date()
    today = datetime.now(timezone.utc).date()
    days_behind = (today - last_date).days

    if days_behind <= 0:
        log.info("Ecosystem is up to date (day %d, %s)", state["current_day"], last_date)
        return None

    max_catchup = target_days or 30
    days_to_run = min(days_behind, max_catchup)

    log.warning("Ecosystem is %d days behind (last: %s, today: %s) — catching up %d days",
                days_behind, last_date, today, days_to_run)

    engine = EcosystemEngine()
    results = engine.simulate_period(days_to_run)

    for r in results:
        log.info(
            "  Catch-up day %d (%s): market=%s revenue=$%.0f events=%d",
            r["day"], r["date"], r["market"],
            r["log"]["revenue_generated"], r["log"]["events_generated"],
        )

    log.info("Catch-up complete: %d days processed", len(results))
    return results[-1] if results else None


def export_json(output_path=None):
    engine = EcosystemEngine()
    data = engine.get_ecosystem_json()
    path = output_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'ecosystem-live.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)
    log.info("Exported ecosystem JSON to %s (%d companies, %d clients)",
             path, len(data["companies"]), len(data["clientDatabase"]))
    return path


def show_status():
    engine = EcosystemEngine()
    state = engine.get_state()

    sim = state["state"]
    if not sim:
        print("No ecosystem state found. Run 'migrate' first.")
        return

    print()
    print("=" * 72)
    print("  ALIEN.INC LIVING ECOSYSTEM — STATUS")
    print("=" * 72)
    print(f"  Day:          {sim['current_day']}")
    print(f"  Date:         {sim['current_date']}")
    print(f"  Status:       {sim['status']}")
    print(f"  Last run:     {sim['last_run'] or 'never'}")
    print()

    print("  COMPANIES")
    print("  " + "-" * 68)
    for c in state["companies"]:
        health_bar_len = int(c['current_health'] / 5)
        health_bar = "█" * health_bar_len + "░" * (20 - health_bar_len)
        momentum_indicator = "+" if c['current_momentum'] > 0 else "-" if c['current_momentum'] < 0 else "="
        print(f"  {c['brand_name']:28s}  ${c['current_cash']:>12,.0f}  "
              f"[{health_bar}] {c['current_health']:5.1f}  "
              f"{momentum_indicator}{abs(c['current_momentum']):.1f}  "
              f"{c['client_count']} clients")

    print()
    if state["recent_events"]:
        print("  RECENT EVENTS")
        print("  " + "-" * 68)
        for e in state["recent_events"][:10]:
            print(f"  [{e['published_date']}] {e['event_type']:15s}  "
                  f"{(e['description'] or e['title'] or '')[:50]}")
        print()

    if state["recent_log"]:
        print("  OPERATIONS LOG (last 5 runs)")
        print("  " + "-" * 68)
        for l in state["recent_log"][:5]:
            print(f"  Day {l['simulation_day']:4d}  {l['run_date']}  "
                  f"rev=${l['revenue_generated']:>10,.0f}  "
                  f"events={l['events_generated']}  "
                  f"{l['status']}  {l['duration_ms']}ms")

    print()


def main():
    parser = argparse.ArgumentParser(description="Alien.Inc Ecosystem Operations Runner")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "catchup", "status", "export", "init", "gdelt"],
                        help="Command to execute")
    parser.add_argument("--days", type=int, default=30,
                        help="Max days to catch up (default: 30)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path for JSON export")

    args = parser.parse_args()

    if args.command == "init":
        init_db()
        log.info("Database initialized at %s", DB_PATH)
        return

    if not is_initialized():
        log.error("Database not initialized. Run 'init' first.")
        sys.exit(1)

    if args.command == "run":
        run_once()
    elif args.command == "catchup":
        run_catchup(args.days)
    elif args.command == "status":
        show_status()
    elif args.command == "export":
        export_json(args.output)
    elif args.command == "gdelt":
        run_gdelt()


if __name__ == "__main__":
    main()
