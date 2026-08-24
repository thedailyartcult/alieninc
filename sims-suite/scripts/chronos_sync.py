#!/usr/bin/env python3
import argparse
import csv
import io
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = SUITE_ROOT.parent / "panteon" / "backend" / "panteon.db"
DATA_DIR = SUITE_ROOT / "data" / "chronos"

NMC_URL = "https://correlatesofwar.org/wp-content/uploads/NMCv7.zip"
CDB90_URL = "https://github.com/jrnold/CDB90.git"

SCHEMA = """
CREATE TABLE IF NOT EXISTS chronos_sync_meta (
  source TEXT PRIMARY KEY,
  rows INTEGER NOT NULL,
  synced_at TEXT NOT NULL,
  version TEXT
);
CREATE TABLE IF NOT EXISTS chronos_countries (
  ccode INTEGER NOT NULL,
  stateabb TEXT NOT NULL,
  year INTEGER NOT NULL,
  milex REAL, milper REAL, irst REAL, pec REAL, tpop REAL, upop REAL,
  cinc REAL,
  version TEXT,
  PRIMARY KEY (ccode, year)
);
CREATE INDEX IF NOT EXISTS idx_chronos_countries_year ON chronos_countries(year);
CREATE TABLE IF NOT EXISTS chronos_battles (
  isqno INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  war TEXT,
  campaign TEXT,
  location TEXT,
  start_date TEXT,
  end_date TEXT,
  duration_hours REAL,
  postype TEXT,
  terrain TEXT,
  weather TEXT,
  air_superiority INTEGER DEFAULT 0,
  attacker_actors TEXT,
  defender_actors TEXT,
  source TEXT NOT NULL DEFAULT 'CDB90',
  dbpedia TEXT
);
CREATE INDEX IF NOT EXISTS idx_chronos_battles_war ON chronos_battles(war);
CREATE TABLE IF NOT EXISTS chronos_belligerents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  isqno INTEGER NOT NULL REFERENCES chronos_battles(isqno),
  side INTEGER NOT NULL,
  unit_name TEXT,
  commander TEXT,
  strength INTEGER,
  casualties INTEGER,
  final_strength INTEGER,
  cav INTEGER, tank INTEGER, ltank INTEGER, mbt INTEGER, arty INTEGER, aircraft INTEGER,
  result_code TEXT,
  leadership REAL, training REAL, morale REAL, logistics REAL, tech REAL, surprise REAL,
  UNIQUE (isqno, side, unit_name)
);
CREATE INDEX IF NOT EXISTS idx_chronos_belligerents_isqno ON chronos_belligerents(isqno);
CREATE TABLE IF NOT EXISTS chronos_oob (
  oob_id TEXT PRIMARY KEY,
  battle_key TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('attacker','defender')),
  echelon TEXT,
  unit_name TEXT NOT NULL,
  parent TEXT,
  strength INTEGER,
  equipment_json TEXT,
  engagement_fraction REAL DEFAULT 1.0,
  source TEXT,
  confidence TEXT DEFAULT 'verified'
);
"""

ACTOR_ALIASES = {
    "united states of america": "USA", "usa": "USA", "united states": "USA",
    "united kingdom": "UK", "great britain": "UK", "britain": "UK",
    "union of soviet socialist republics": "USSR", "soviet union": "USSR", "ussr": "USSR",
    "russia": "RUS", "germany": "GER", "west germany": "FRG",
    "france": "FRN", "italy": "ITA", "japan": "JPN", "poland": "POL",
    "netherlands": "NET", "belgium": "BEL", "yugoslavia": "YUG",
    "greece": "GRC", "china": "CHN", "romania": "ROM", "hungary": "HUN",
    "bulgaria": "BUL", "finland": "FIN", "austria-hungary": "AUH",
    "austria": "AUS", "prussia": "PRU", "turkey": "TUR", "ottoman empire": "TUR",
    "egypt": "EGY", "israel": "ISR", "india": "IND", "canada": "CAN",
    "australia": "AUL", "new zealand": "NZL", "south africa": "SAF",
    "spain": "SPA", "sweden": "SWE", "norway": "NOR", "denmark": "DEN",
    "portugal": "POR", "switzerland": "SWZ", "czechoslovakia": "CZE",
    "serbia": "SER", "korea": "KOR", "north korea": "PRK", "south korea": "KOR",
    "vietnam": "VNM", "north vietnam": "DRV", "south vietnam": "RVN",
    "iraq": "IRQ", "iran": "IRN", "argentina": "ARG", "brazil": "BRA",
    "mexico": "MEX", "ukraine": "UKR", "ethiopia": "ETH", "sudan": "SUD",
}


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _int(value):
    n = _num(value)
    return int(n) if n is not None else None


def download_sources(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    nmc_csv = data_dir / "NMC-70-abridged.csv"
    if not nmc_csv.exists():
        print(f"[download] {NMC_URL}")
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "nmc.zip"
            subprocess.run(["curl", "-sL", "--max-time", "120", NMC_URL, "-o", str(zip_path)], check=True)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp)
            extracted = list(Path(tmp).rglob("NMC-70-abridged.csv"))
            if not extracted:
                sys.exit("ERROR: NMC abridged CSV not found in archive")
            shutil.copy(extracted[0], nmc_csv)
    else:
        print("[download] NMC cached")
    cdb90 = data_dir / "cdb90"
    if not cdb90.exists():
        print(f"[download] {CDB90_URL}")
        subprocess.run(["git", "clone", "--depth", "1", CDB90_URL, str(cdb_dir := cdb90)], check=True)
    else:
        print("[download] CDB90 cached")


TERRA1_LABELS = {"F": "flat", "R": "rolling", "G": "rugged"}
TERRA2_LABELS = {"B": "bare", "M": "mixed", "D": "desert", "W": "wooded"}
TERRA3_LABELS = {"M": "marsh", "U": "urban", "D": "dunes"}
WX_LABELS = {"D": "dry", "W": "wet"}


def _terrain_label(terr_rows):
    labels = []
    for code in terr_rows:
        code = str(code or "").strip().upper()
        if code in TERRA1_LABELS:
            labels.append(TERRA1_LABELS[code])
        elif code in TERRA2_LABELS:
            labels.append(TERRA2_LABELS[code])
        elif code in TERRA3_LABELS:
            labels.append(TERRA3_LABELS[code])
    seen = []
    for lb in labels:
        if lb not in seen:
            seen.append(lb)
    return ",".join(seen)


def _weather_label(wx_codes):
    out = []
    for code in wx_codes:
        lb = WX_LABELS.get(str(code or "").strip().upper())
        if lb and lb not in out:
            out.append(lb)
    return ",".join(out)


def sync_nmc(conn: sqlite3.Connection, data_dir: Path) -> int:
    src = data_dir / "NMC-70-abridged.csv"
    rows = []
    with open(src, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append((
                int(r["ccode"]), r["stateabb"], int(r["year"]),
                _num(r.get("milex")), _num(r.get("milper")), _num(r.get("irst")),
                _num(r.get("pec")), _num(r.get("tpop")), _num(r.get("upop")),
                _num(r.get("cinc")), r.get("version") or "7.0",
            ))
    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO chronos_countries
           (ccode, stateabb, year, milex, milper, irst, pec, tpop, upop, cinc, version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(ccode, year) DO UPDATE SET
             stateabb=excluded.stateabb, milex=excluded.milex, milper=excluded.milper,
             irst=excluded.irst, pec=excluded.pec, tpop=excluded.tpop, upop=excluded.upop,
             cinc=excluded.cinc, version=excluded.version""",
        rows,
    )
    version = rows[0][10] if rows else "7.0"
    _meta(cur, "cow_nmc_v7", len(rows), version)
    conn.commit()
    return len(rows)


def _meta(cur, source, rows, version=None):
    cur.execute(
        """INSERT INTO chronos_sync_meta (source, rows, synced_at, version)
           VALUES (?,?,?,?)
           ON CONFLICT(source) DO UPDATE SET rows=excluded.rows,
             synced_at=excluded.synced_at, version=excluded.version""",
        (source, rows, datetime.now(timezone.utc).isoformat(), version),
    )


def sync_cdb90(conn: sqlite3.Connection, data_dir: Path) -> tuple:
    base = data_dir / "cdb90" / "data"

    def load(name):
        with open(base / name, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    battles = load("battles.csv")
    belligerents = load("belligerents.csv")
    actors = load("battle_actors.csv")
    durations = load("battle_durations.csv")
    terrain = load("terrain.csv")
    weather = load("weather.csv")

    dur_by_isq = {int(r["isqno"]): r for r in durations}
    terr_by_isq = {}
    for r in terrain:
        codes = [r.get("terra1"), r.get("terra2"), r.get("terra3")]
        terr_by_isq.setdefault(int(r["isqno"]), []).extend(c for c in codes if c)
    wx_by_isq = {}
    for r in weather:
        wx_by_isq.setdefault(int(r["isqno"]), []).append(r.get("wx1"))

    actors_by_isq = {}
    for r in actors:
        # CDB90 battle_actors.attacker is a boolean flag: 1 = attacking party
        role = "attackers" if str(r["attacker"]).strip() == "1" else "defenders"
        actors_by_isq.setdefault(int(r["isqno"]), {}).setdefault(role, []).append(r["actor"])

    bel_by_isq = {}
    for r in belligerents:
        bel_by_isq.setdefault(int(r["isqno"]), []).append(r)

    # Per-battle ordinal quality assessments from battles.csv. Suffix 'a' =
    # attacker assessment, 'aa' = defender assessment (CDB90 convention).
    aeroa_by_isq = {}
    for b in battles:
        v = _num(b.get("aeroa"))
        aeroa_by_isq[int(b["isqno"])] = int(v) if v is not None else 0

    qual_by_isq = {}
    for b in battles:
        att = {
            "leadership": _num(b.get("leada")),
            "training": _num(b.get("trnga")),
            "morale": _num(b.get("morala")),
            "logistics": _num(b.get("logsa")),
            "tech": _num(b.get("techa")),
            "surprise": _num(b.get("surpa")),
        }
        dfd = {
            "leadership": _num(b.get("leadaa")),
            "training": None,
            "morale": None,
            "logistics": _num(b.get("logsaa")),
            "tech": None,
            "surprise": _num(b.get("surpaa")),
        }
        qual_by_isq[int(b["isqno"])] = {1: att, 0: dfd}

    cur = conn.cursor()
    n_battles = n_bel = 0
    for b in battles:
        isq = int(b["isqno"])
        d = dur_by_isq.get(isq, {})
        a_actors = actors_by_isq.get(isq, {}).get("attackers", [])
        d_actors = actors_by_isq.get(isq, {}).get("defenders", [])
        cur.execute(
            """INSERT INTO chronos_battles
               (isqno, name, war, campaign, location, start_date, end_date,
                duration_hours, postype, terrain, weather, air_superiority,
                attacker_actors, defender_actors, source, dbpedia)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'CDB90',?)
               ON CONFLICT(isqno) DO UPDATE SET
                 name=excluded.name, war=excluded.war, campaign=excluded.campaign,
                 location=excluded.location, start_date=excluded.start_date,
                 end_date=excluded.end_date, duration_hours=excluded.duration_hours,
                 postype=excluded.postype, terrain=excluded.terrain,
                 weather=excluded.weather, attacker_actors=excluded.attacker_actors,
                 defender_actors=excluded.defender_actors, source='CDB90',
                 dbpedia=excluded.dbpedia""",
            (
                isq, b["name"], b.get("war"), b.get("campgn"), b.get("locn"),
                d.get("datetime_min"), d.get("datetime_max"),
                (_num(d.get("duration2")) or 0) * 24 or None,
                b.get("postype"),
                _terrain_label(terr_by_isq.get(isq, [])),
                _weather_label(wx_by_isq.get(isq, [])),
                aeroa_by_isq.get(isq, 0),
                json.dumps(a_actors), json.dumps(d_actors), b.get("dbpedia"),
            ),
        )
        n_battles += 1
        for bel in bel_by_isq.get(isq, []):
            side = int(bel["attacker"])
            q = qual_by_isq.get(isq, {}).get(side, {})
            result_code = None
            for col in ("reso1", "reso2", "reso3"):
                v = bel.get(col)
                if v:
                    result_code = str(v).strip()
                    break
            cur.execute(
                """INSERT INTO chronos_belligerents
                   (isqno, side, unit_name, commander, strength, casualties,
                    final_strength, cav, tank, ltank, mbt, arty, aircraft,
                    result_code, leadership, training, morale, logistics, tech, surprise)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(isqno, side, unit_name) DO UPDATE SET
                     commander=excluded.commander, strength=excluded.strength,
                     casualties=excluded.casualties, final_strength=excluded.final_strength,
                     cav=excluded.cav, tank=excluded.tank, ltank=excluded.ltank,
                     mbt=excluded.mbt, arty=excluded.arty, aircraft=excluded.aircraft,
                     result_code=excluded.result_code, leadership=excluded.leadership,
                     training=excluded.training, morale=excluded.morale,
                     logistics=excluded.logistics, tech=excluded.tech,
                     surprise=excluded.surprise""",
                (
                    isq, side, bel.get("nam"), bel.get("co"),
                    _int(bel.get("str")), _int(bel.get("cas")), _int(bel.get("finst")),
                    _int(bel.get("cav")), _int(bel.get("tank")), _int(bel.get("lt")),
                    _int(bel.get("mbt")), _int(bel.get("arty")), _int(bel.get("fly")),
                    result_code, q.get("leadership"), q.get("training"), q.get("morale"),
                    q.get("logistics"), q.get("tech"), q.get("surprise"),
                ),
            )
            n_bel += 1

    _meta(cur, "cdb90", n_battles, "1990-rev")
    conn.commit()
    return n_battles, n_bel


def sync_oob(conn: sqlite3.Connection, data_dir: Path) -> int:
    src = data_dir / "oob_flagships.json"
    if not src.exists():
        print(f"[sync] no OOB file at {src}, skipping")
        return 0
    payload = json.loads(src.read_text())
    entries = [e for e in payload.get("entries", []) if not e.get("oob_id", "").startswith("_")]
    cur = conn.cursor()
    for e in entries:
        cur.execute(
            """INSERT INTO chronos_oob
               (oob_id, battle_key, side, echelon, unit_name, parent, strength,
                equipment_json, engagement_fraction, source, confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(oob_id) DO UPDATE SET
                 battle_key=excluded.battle_key, side=excluded.side,
                 echelon=excluded.echelon, unit_name=excluded.unit_name,
                 parent=excluded.parent, strength=excluded.strength,
                 equipment_json=excluded.equipment_json,
                 engagement_fraction=excluded.engagement_fraction,
                 source=excluded.source,
                 confidence=excluded.confidence""",
            (
                e["oob_id"], e["battle_key"], e["side"], e.get("echelon"),
                e["unit_name"], e.get("parent"), _int(e.get("strength")),
                json.dumps(e.get("equipment_json") or {}),
                _num(e.get("engagement_fraction")) or 1.0,
                e.get("source"), e.get("confidence", "curated"),
            ),
        )
    _meta(cur, "chronos_oob_flagships", len(entries))
    conn.commit()
    return len(entries)


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive column migrations for pre-existing chronos tables."""
    cur = conn.cursor()
    oob_cols = {r[1] for r in cur.execute("PRAGMA table_info(chronos_oob)").fetchall()}
    if "engagement_fraction" not in oob_cols:
        cur.execute("ALTER TABLE chronos_oob ADD COLUMN engagement_fraction REAL DEFAULT 1.0")
    b_cols = {r[1] for r in cur.execute("PRAGMA table_info(chronos_battles)").fetchall()}
    if "air_superiority" not in b_cols:
        cur.execute("ALTER TABLE chronos_battles ADD COLUMN air_superiority INTEGER DEFAULT 0")
    conn.commit()


def verify(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    out = {}
    out["countries"] = cur.execute("SELECT COUNT(*) FROM chronos_countries").fetchone()[0]
    out["country_years_min"] = cur.execute("SELECT MIN(year) FROM chronos_countries").fetchone()[0]
    out["country_years_max"] = cur.execute("SELECT MAX(year) FROM chronos_countries").fetchone()[0]
    out["battles"] = cur.execute("SELECT COUNT(*) FROM chronos_battles").fetchone()[0]
    out["wwii_battles"] = cur.execute(
        "SELECT COUNT(*) FROM chronos_battles WHERE war LIKE '%WORLD WAR II%'"
    ).fetchone()[0]
    out["belligerents"] = cur.execute("SELECT COUNT(*) FROM chronos_belligerents").fetchone()[0]
    out["with_strength_and_casualties"] = cur.execute(
        """SELECT COUNT(*) FROM chronos_belligerents
           WHERE strength IS NOT NULL AND casualties IS NOT NULL"""
    ).fetchone()[0]
    out["oob_entries"] = cur.execute("SELECT COUNT(*) FROM chronos_oob").fetchone()[0]
    sample = cur.execute(
        """SELECT b.name, bl.side, bl.strength, bl.casualties
           FROM chronos_battles b JOIN chronos_belligerents bl USING(isqno)
           WHERE b.name LIKE 'EL ALAMEIN II%' LIMIT 4"""
    ).fetchall()
    out["alamein_sample"] = sample
    ger1939 = cur.execute(
        """SELECT stateabb, year, milper, irst, cinc FROM chronos_countries
           WHERE stateabb='GER' AND year=1939"""
    ).fetchone()
    out["germany_1939"] = ger1939
    return out


def main():
    ap = argparse.ArgumentParser(description="Chronos historical data sync (idempotent)")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--download", action="store_true", help="Fetch/refresh raw sources")
    ap.add_argument("--sync", action="store_true", help="Import into panteon.db")
    ap.add_argument("--verify", action="store_true", help="Report counts + samples")
    args = ap.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    if not args.download and not args.sync and not args.verify:
        args.download = True
        args.sync = True

    if args.download:
        download_sources(DATA_DIR)

    if args.verify and not args.sync:
        conn = sqlite3.connect(db_path)
        try:
            print(json.dumps(verify(conn), indent=2, default=str))
        finally:
            conn.close()
        return

    if args.sync:
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(SCHEMA)
            _migrate(conn)
            n = sync_nmc(conn, DATA_DIR)
            print(f"[sync] chronos_countries: {n} country-years")
            nb, nbel = sync_cdb90(conn, DATA_DIR)
            print(f"[sync] chronos_battles: {nb}, chronos_belligerents: {nbel}")
            noob = sync_oob(conn, DATA_DIR)
            print(f"[sync] chronos_oob: {noob} flagship entries")
            print(json.dumps(verify(conn), indent=2, default=str))
        finally:
            conn.close()


if __name__ == "__main__":
    main()
